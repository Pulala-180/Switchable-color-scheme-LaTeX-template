#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
lonetrail.py —— 孤星模板一图流：换模板 / 编译 / 渲素材 / 换肤，全部收在一个脚本里。

  两个主功能（对应根目录两个 bat）：

  python tools/lonetrail.py quick    ① 正文单次编译：只编一遍
  python tools/lonetrail.py build    ② 换模板：同步模板 → 问主题 → 渲染素材 → 正文编译三遍

  附加：

  python tools/lonetrail.py theme                    ③ 换肤：改主题号 → 渲染素材 → 编译三遍
  python tools/lonetrail.py theme 074 --no-build     只改主题号，不编译
  python tools/lonetrail.py theme --list             列出 themes.tex 里的全部主题
  python tools/lonetrail.py refresh                  只重渲改过的素材（SHA-256 比对）

  通用参数：

  --project <目录>        指定工程目录（默认本脚本的上一级）
  --template <目录>       指定模板目录（默认本脚本的上一级，用于同步）
  --passes N              正文编译遍数（quick 默认 1，其余默认 3）
  --asset-passes N        每个素材渲染几遍（默认 1）
  --jobs N                并行渲染素材数（默认 8）
  --no-theme              不弹主题输入，直接用 main.tex 现有的主题号
  --no-open               编译完不自动打开 PDF
  --no-cache              忽略素材缓存，强制全部重渲
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stdin, "reconfigure"):
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ROOT = DEFAULT_ROOT
ASSET_SRC = os.path.join(ROOT, "assets", "tikz")
ASSET_OUT = os.path.join(ROOT, "assets", "pdf")
TMP_DIR = os.path.join(ASSET_OUT, "_tmp")
MAIN_TEX = os.path.join(ROOT, "main.tex")


def set_root(path):
    global ROOT, ASSET_SRC, ASSET_OUT, TMP_DIR, MAIN_TEX
    ROOT = os.path.abspath(path)
    ASSET_SRC = os.path.join(ROOT, "assets", "tikz")
    ASSET_OUT = os.path.join(ROOT, "assets", "pdf")
    TMP_DIR = os.path.join(ASSET_OUT, "_tmp")
    MAIN_TEX = os.path.join(ROOT, "main.tex")


# ==============================================================================
# 素材清单
# ==============================================================================
BG_ASSETS = ["main_bg", "contents_bg", "cover_bg"]
ASSETS = BG_ASSETS + [
    "box1_1", "box1_2", "box2_1", "box2_2", "box3_1", "box3_2", "box4_1", "box4_2",
    "definition_1", "definition_2", "theorem_1", "theorem_2",
    "proposition_1", "proposition_2", "corollary_1", "corollary_2",
    "lemma_1", "lemma_2", "example_1", "example_2",
    "exercise_1", "exercise_2", "question_2",
    "separator_1", "cover_sep",
]
MARK_COLORS = ["definition", "theorem", "proposition", "corollary", "lemma", "example"]
ASSETS += ["mark_" + c for c in MARK_COLORS]

# 素材模板里的相对路径都从工程根解析，保证拷到哪儿都能渲。
# 末尾空后缀=整串替换系统 TEXINPUTS，避免拉到用户 texmf 树里的同名 main.aux
TEX_SEARCH = ".;./palettes//;./assets//;"

# 用户 texmf 树（~/texmf）里若残留别的模板的 main.aux / main.toc，
# 会和本工程同名文件抢位置。把 TEXMFHOME 指到工程内的空目录即可摘掉它。
# 注意：设成空字符串会被 kpathsea 当成“未设置”而回退到 ~/texmf，必须给个真实存在的空目录。
XELATEX_FLAGS = ["-no-shell-escape"]


def tex_env():
    env = dict(os.environ)
    # 末尾空后缀 = 整串替换，干掉系统里残留的 TEXINPUTS
    env["TEXINPUTS"] = TEX_SEARCH
    empty_texmf = os.path.join(TMP_DIR, "_empty_texmf")
    os.makedirs(empty_texmf, exist_ok=True)
    env["TEXMFHOME"] = empty_texmf
    return env


def pause_exit(code=0):
    """双击运行时别让窗口一闪而过；管道里调用时直接返回"""
    try:
        if sys.stdin and sys.stdin.isatty() and sys.stdout.isatty():
            input("\n按回车键关闭窗口…")
    except (EOFError, KeyboardInterrupt, OSError):
        pass
    sys.exit(code)

FRAME = r"""\documentclass[border=0pt]{standalone}
\usepackage{tikz}
\usepackage{xcolor}
\usepackage{amsmath}
\usetikzlibrary{calc,patterns,patterns.meta,decorations.pathmorphing,
  decorations.markings,decorations.text,shapes.geometric,arrows.meta,fadings,shadings}
\input{palettes/themes.tex}
\SelectTheme{%(theme)s}
\begin{document}
\input{assets/tikz/%(name)s.tex}
\end{document}
"""

MARK_FRAME = r"""\documentclass[border=0pt]{standalone}
\usepackage{tikz}
\usepackage{xcolor}
\usetikzlibrary{calc}
\input{palettes/themes.tex}
\SelectTheme{%(theme)s}
\input{assets/tikz/box_corner_mark.tex}
\begin{document}
\BoxCornerMark[%(color)s]
\end{document}
"""

BAR_W = 28


def bar(done, total, width=BAR_W):
    if total <= 0:
        return "[" + "-" * width + "]"
    n = min(int(width * done / total), width)
    return "[" + "#" * n + "-" * (width - n) + "]"


# ==============================================================================
# 主题号读写
# ==============================================================================
def read_theme():
    with open(MAIN_TEX, encoding="utf-8") as f:
        m = re.search(r"\\SelectTheme\{([^}]*)\}", f.read())
    return m.group(1).strip() if m else "001"


def write_theme(theme):
    with open(MAIN_TEX, encoding="utf-8") as f:
        s = f.read()
    s = re.sub(r"\\SelectTheme\{[^}]*\}", "\\\\SelectTheme{%s}" % theme, s)
    with open(MAIN_TEX, "w", encoding="utf-8", newline="\n") as f:
        f.write(s)


DEFAULT_COLORS = {
    "qiancheng": r"\definecolor{qiancheng}{RGB}{227, 101, 53}",
    "lv": r"\definecolor{lv}{RGB}{131, 187, 170}",
    "huang": r"\definecolor{huang}{RGB}{227, 164, 60}",
    "hong": r"\definecolor{hong}{RGB}{149, 44, 38}",
    "qianbai": r"\definecolor{qianbai}{RGB}{248, 243, 231}",
    "mibai": r"\definecolor{mibai}{RGB}{244, 237, 218}",
    "heise": r"\definecolor{heise}{RGB}{0, 0, 0}",
    "definition": r"\definecolor{definition}{RGB}{245, 164, 0}",
    "theorem": r"\definecolor{theorem}{RGB}{222, 4, 20}",
    "proposition": r"\definecolor{proposition}{RGB}{177, 0, 129}",
    "corollary": r"\definecolor{corollary}{RGB}{133, 194, 72}",
    "lemma": r"\definecolor{lemma}{RGB}{233, 93, 157}",
    "example": r"\definecolor{example}{RGB}{0, 153, 216}",
}

WORDNUM = {
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine"
}


def make_tex_cmd_name(theme_id):
    """将任意主题标识符转换为合法的 TeX 字母命令名"""
    res = []
    for ch in str(theme_id).lower():
        if ch in WORDNUM:
            res.append(WORDNUM[ch])
        elif ch.isalpha():
            res.append(ch)
        else:
            res.append("x")
    return "LoneTrailThemeDef@theme" + "".join(res)


def parse_theme_file(filepath):
    """解析单个 palettes/tex/*.tex 文件，提取主题编号、说明、颜色定义及别名"""
    fn = os.path.splitext(os.path.basename(filepath))[0]
    if fn.startswith("theme_"):
        tid = fn[6:]
    else:
        tid = fn

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # 提取主题名称 / 说明
    name = ""
    m_name = re.search(r"^%\s*Name:\s*(.+)$", content, re.M)
    if m_name:
        name = m_name.group(1).strip()
    else:
        m_theme = re.search(r"^%\s*(?:Baseline\s+)?Theme:\s*[^|]+\|\s*(.+)$", content, re.M)
        if m_theme:
            name = m_theme.group(1).strip()
        else:
            name = tid

    # 提取历史别名（如 Formerly theme_002 或 Old: theme_002）
    aliases = set()
    m_old = re.findall(r"(?:Formerly|Old:?)\s*(theme_\w+|\w+)", content, re.I)
    for a in m_old:
        aliases.add(a.strip())

    # 提取定义的颜色
    colors = {}
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("%"):
            continue
        m_col = re.search(r"\\definecolor\{([^}]+)\}", line)
        if m_col:
            cname = m_col.group(1).strip()
            clean_line = line.split("%")[0].strip()
            if not clean_line.endswith("%"):
                clean_line += "%"
            colors[cname] = clean_line

    # 保证 13 项核心 token 完整，避免 xelatex 缺色报错
    final_colors = []
    for cname in DEFAULT_COLORS:
        if cname in colors:
            final_colors.append(colors[cname])
        else:
            final_colors.append(DEFAULT_COLORS[cname] + "%")
    for cname, cline in colors.items():
        if cname not in DEFAULT_COLORS:
            final_colors.append(cline)

    return {
        "id": tid,
        "name": name,
        "filename": os.path.basename(filepath),
        "aliases": aliases,
        "colors": final_colors,
    }


def generate_themes_tex(themes):
    """根据扫描到的主题列表动态生成 palettes/themes.tex 完整内容"""
    lines = [
        "% ==============================================================================",
        "%         明日方舟·孤星 (Arknights Lone Trail) 精选高定主题配色总控单文件",
        "%                        palettes/themes.tex",
        f"%              总计收录 {len(themes)} 套主题（自动同步自 palettes/tex/）",
        "% ==============================================================================",
        "%",
        "% 【使用方法】在主文档 main.tex 中引入并选用主题：",
        "%    \\input{styles/settings.tex}",
        "%    \\input{palettes/themes.tex}",
        "%    \\SelectTheme{001}         % 直接输入主题编号",
        "%    \\input{styles/boxes.tex}",
        "%",
        "% ==============================================================================",
        "",
        "\\makeatletter",
        "% ------------------------------------------------------------------------------",
        "% 主题调度选择器",
        "% ------------------------------------------------------------------------------",
        "\\newcommand{\\SelectTheme}[1]{%",
        "  \\@ifundefined{LoneTrailTheme@#1}{%",
        "    \\PackageWarning{LoneTrailThemes}{Theme '#1' not recognized! Falling back to 001.}%",
        "    \\csname LoneTrailTheme@001\\endcsname",
        "  }{%",
        "    \\csname LoneTrailTheme@#1\\endcsname",
        "  }%",
        "}",
        "",
    ]

    for t in themes:
        tid = t["id"]
        tname = t["name"]
        cmd_name = make_tex_cmd_name(tid)

        lines.append("% ------------------------------------------------------------------------------")
        lines.append(f"% Theme: theme_{tid} | {tname}")
        lines.append("% ------------------------------------------------------------------------------")
        lines.append(f"\\newcommand{{\\{cmd_name}}}{{%")
        for c in t["colors"]:
            lines.append(f"  {c}")
        lines.append("}")

        registered = set()

        def add_alias(alias_str):
            if alias_str and alias_str not in registered:
                registered.add(alias_str)
                lines.append(f"\\@namedef{{LoneTrailTheme@{alias_str}}}{{\\{cmd_name}}}")

        add_alias(tid)
        add_alias(f"theme_{tid}")
        if tid.isdigit():
            add_alias(str(int(tid)))

        if tid == "000":
            add_alias("orange")
            add_alias("baseline_orange")
            add_alias("theme_000_baseline_orange")

        for extra in sorted(t["aliases"]):
            add_alias(extra)

        lines.append("")

    lines.append("\\makeatother")
    lines.append("")
    return "\n".join(lines)


def sync_themes(root_dir=None):
    """自动扫描 palettes/tex/ 目录下的所有模板并同步更新 palettes/themes.tex。
    增删或修改主题后即可自动同步，保证正常编译与显示。"""
    if root_dir is None:
        root_dir = ROOT
    tex_dir = os.path.join(root_dir, "palettes", "tex")
    themes_tex_path = os.path.join(root_dir, "palettes", "themes.tex")
    if not os.path.isdir(tex_dir):
        return []

    themes = []
    for fn in sorted(os.listdir(tex_dir)):
        if fn.endswith(".tex"):
            p = os.path.join(tex_dir, fn)
            themes.append(parse_theme_file(p))

    def sort_key(t):
        tid = t["id"]
        if tid.isdigit():
            return (0, int(tid), tid)
        return (1, 0, tid)

    themes.sort(key=sort_key)
    new_tex = generate_themes_tex(themes)

    old_tex = ""
    if os.path.exists(themes_tex_path):
        try:
            with open(themes_tex_path, "r", encoding="utf-8", errors="ignore") as f:
                old_tex = f.read()
        except Exception:
            old_tex = ""

    if new_tex.strip() != old_tex.strip():
        with open(themes_tex_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_tex)
        print("[模板] 已自动同步 palettes/themes.tex（识别到 palettes/tex/ 共 %d 套主题）" % len(themes))

    return themes


def load_themes():
    """获取所有主题列表（启动时自动识别 palettes/tex/ 增删改动并同步 themes.tex）"""
    themes = sync_themes(ROOT)
    return [{"id": t["id"], "name": t["name"]} for t in themes]


def resolve_theme(themes, choice):
    """数字 / 名字 / 模糊名 → (命中的主题或 None, 候选列表)"""
    c = choice.strip()
    if not c:
        return None, []

    key = c.lower().replace("-", "_").replace(" ", "_")
    for t in themes:
        if key == t["id"].lower():
            return t, []
        if key == t["id"].split("_", 1)[-1].lower():
            return t, []

    # 去掉 theme_ 前缀匹配
    if key.startswith("theme_"):
        raw_key = key[6:]
        for t in themes:
            if raw_key == t["id"].lower():
                return t, []

    # 000 / orange / baseline_orange 兼容
    if key in ("orange", "baseline_orange"):
        for t in themes:
            if t["id"] == "000":
                return t, []

    # 数字匹配（支持 0, 1, 000, 001 等各种位宽）
    if re.fullmatch(r"\d{1,3}", c):
        target_int = int(c)
        for t in themes:
            if t["id"].isdigit() and int(t["id"]) == target_int:
                return t, []

    for t in themes:
        if c.lower() == t["name"].lower():
            return t, []
    hits = [t for t in themes if c.lower() in t["name"].lower()]
    return (hits[0], []) if len(hits) == 1 else (None, hits)


# ==============================================================================
# 素材渲染
# ==============================================================================
def render_one(name, theme, passes=1):
    """渲染一个素材；passes 为 xelatex 调用次数"""
    os.makedirs(TMP_DIR, exist_ok=True)
    tmp = os.path.join(TMP_DIR, name + ".tex")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        if name.startswith("mark_"):
            f.write(MARK_FRAME % {"theme": theme, "color": name[len("mark_"):]})
        else:
            if not os.path.exists(os.path.join(ASSET_SRC, name + ".tex")):
                return name, None, "素材不存在"
            f.write(FRAME % {"theme": theme, "name": name})

    built = os.path.join(TMP_DIR, name + ".pdf")
    if os.path.exists(built):
        os.remove(built)

    env = tex_env()

    for _ in range(max(1, passes)):
        p = subprocess.run(
            ["xelatex"] + XELATEX_FLAGS +
            ["-interaction=nonstopmode", "-halt-on-error",
             "-output-driver=xdvipdfmx -V 4 -z 0",
             "-output-directory=" + TMP_DIR, os.path.basename(tmp)],
            cwd=ROOT, env=env, capture_output=True, text=True, errors="ignore")
        if p.returncode != 0 or not os.path.exists(built):
            err = "编译失败"
            log = os.path.join(TMP_DIR, name + ".log")
            if os.path.exists(log):
                with open(log, encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if line.startswith("!"):
                            err = line.strip()
                            break
            if os.path.exists(built):
                os.remove(built)
            return name, None, err
    return name, built, None


def build_assets(theme, names=None, jobs=8, passes=1):
    """渲染素材（默认全部），返回 (ok, 已成功渲染的名字列表)"""
    os.makedirs(ASSET_OUT, exist_ok=True)
    os.makedirs(TMP_DIR, exist_ok=True)
    todo = list(names or ASSETS)
    total = len(todo)
    print("\n[素材] 渲染 %d 个   theme=%s   每个 %d 遍" % (total, theme, passes))
    t0 = time.time()
    done = 0
    failed, ok_names = [], []

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(render_one, n, theme, passes) for n in todo]
        for fut in futures:
            name, built, err = fut.result()
            done += 1
            if built:
                dst = os.path.join(ASSET_OUT, name + ".pdf")
                try:
                    if os.path.exists(dst):
                        os.remove(dst)
                    shutil.copyfile(built, dst)
                    ok_names.append(name)
                except PermissionError:
                    failed.append((name, "目标 PDF 被占用，关掉阅读器再试"))
            else:
                failed.append((name, err))
            sys.stdout.write("\r    %s %3d/%d  %-16s" %
                             (bar(done, total), done, total, name))
            sys.stdout.flush()

    sys.stdout.write("\n")
    print("    完成 %d/%d，用时 %.1fs" % (total - len(failed), total, time.time() - t0))
    for name, err in failed:
        print("    [失败] %-16s %s" % (name, err))
    return (not failed), ok_names


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def refresh_changed(theme, jobs=8, passes=1):
    """只重渲改过的素材（三个整页背景除外）"""
    cache_path = os.path.join(TMP_DIR, ".asset_hash.json")
    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            pass

    todo, hashes = [], {}
    for name in ASSETS:
        if name in BG_ASSETS:
            continue
        src = os.path.join(ASSET_SRC, name + ".tex")
        if not os.path.exists(src):
            continue
        h = sha256(src)
        dst = os.path.join(ASSET_OUT, name + ".pdf")
        if cache.get(name) == h and os.path.exists(dst):
            continue
        todo.append(name)
        hashes[name] = h

    if not todo:
        print("\n[素材] 全部没变，跳过。")
        return True

    ok, ok_names = build_assets(theme, todo, jobs, passes)
    for n in ok_names:
        cache[n] = hashes[n]
    os.makedirs(TMP_DIR, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1, sort_keys=True)
    return ok


# ==============================================================================
# 正文编译
# ==============================================================================
PASS_RE = re.compile(r"^\[(\d+)\]", re.M)


def compile_pass(idx, passes):
    label = "    第 %d/%d 遍" % (idx, passes)
    t0 = time.time()
    env = tex_env()
    proc = subprocess.Popen(
        ["xelatex"] + XELATEX_FLAGS + ["-interaction=nonstopmode", "main.tex"],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, errors="ignore", bufsize=1)

    buf = []
    state = {"page": 0}
    EST_PAGES = 40

    def reader():
        for line in proc.stdout:
            buf.append(line)
            m = PASS_RE.match(line.strip())
            if m:
                state["page"] = int(m.group(1))
                sys.stdout.write("\r%s  %s 第 %d 页      " %
                                 (label, bar(state["page"], EST_PAGES), state["page"]))
                sys.stdout.flush()

    th = threading.Thread(target=reader)
    th.start()
    proc.wait()
    th.join()

    log = "".join(buf)
    found = PASS_RE.findall(log)
    pages = max((int(x) for x in found), default=state["page"])
    dt = time.time() - t0

    if proc.returncode != 0:
        sys.stdout.write("\r%s  [失败] %.1fs%s\n" % (label, dt, " " * 24))
        for line in log.splitlines():
            if line.startswith("!"):
                print("      " + line)
        return False

    sys.stdout.write("\r%s  %s %2d 页  %.1fs%s\n" %
                     (label, bar(1, 1), pages, dt, " " * 16))
    return True


def build_pdf(passes):
    print("\n[正文] 编译 main.tex   %d 遍" % passes)
    return all([compile_pass(i, passes) for i in range(1, passes + 1)])


# ==============================================================================
# 模板同步
# ==============================================================================
SYNC_ITEMS = ["styles", "palettes", "tools", "assets/tikz", "assets/pdf",
              "assets/fonts", "README.md"]
PROTECTED = ("chapters", "figures", "main.tex", "_archive", "assets/pdf/_tmp")


def _is_protected(rel):
    return any(rel == p or rel.startswith(p + "/") for p in PROTECTED)


def sync_template(template, project, dry=False):
    """把模板的版式/配色/脚本/素材同步进工程；正文与 main.tex 不动"""
    if os.path.abspath(template) == os.path.abspath(project):
        print("\n[模板] 工程就是模板本身，跳过同步。")
        return True

    plan = []
    for item in SYNC_ITEMS:
        src_root = os.path.join(template, item)
        if not os.path.exists(src_root):
            continue
        if os.path.isfile(src_root):
            plan.append((src_root, os.path.join(project, item)))
            continue
        for dirpath, dirnames, filenames in os.walk(src_root):
            dirnames[:] = [d for d in dirnames
                           if d not in ("__pycache__", "_tmp") and not d.startswith(".")]
            for fn in filenames:
                if fn.startswith("."):
                    continue
                src = os.path.join(dirpath, fn)
                rel = os.path.relpath(src, template).replace("\\", "/")
                if _is_protected(rel):
                    continue
                plan.append((src, os.path.join(project, rel)))

    changed = []
    for src, dst in plan:
        if not os.path.exists(dst):
            changed.append((src, dst, "新增"))
        elif sha256(src) != sha256(dst):
            changed.append((src, dst, "更新"))

    print("\n[模板] 从 %s 同步" % template)
    print("       模板文件 %d 个，需要更新 %d 个" % (len(plan), len(changed)))

    if not changed:
        print("       已是最新，无需同步。")
        return True

    for _, dst, act in changed:
        print("  [%s] %s" % (act, os.path.relpath(dst, project)))
    if dry:
        print("       (dry-run，未写入)")
        return True

    for src, dst, _ in changed:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    print("       同步完成（main.tex / chapters / figures 未动）")
    return True


# ==============================================================================
# 各功能
# ==============================================================================
def banner(title, extra=""):
    print("=" * 60)
    print("  孤星模板 · %s" % title)
    if extra:
        print("  %s" % extra)
    print("=" * 60)


def display_all_themes(themes, cur):
    print("\n" + "-" * 60)
    print("【当前所有主题】（共 %d 套）：" % len(themes))
    for t in themes:
        tid = t["id"]
        tname = t["name"]
        is_cur = (tid == cur) or (cur.isdigit() and tid.isdigit() and int(cur) == int(tid))
        mark = "  <-- 当前应用" if is_cur else ""
        print("  %-12s %s%s" % (tid, tname, mark))
    print("-" * 60)
    cur_t = next((t for t in themes if t["id"] == cur or (cur.isdigit() and t["id"].isdigit() and int(cur) == int(t["id"]))), None)
    if cur_t:
        print("当前应用主题：%s - %s" % (cur, cur_t["name"]))
    else:
        print("当前应用主题：%s" % cur)


def ask_theme(themes, cur):
    display_all_themes(themes, cur)
    while True:
        try:
            choice = input("\n输入要切换的主题进行，回车进行编译（直接回车保持当前 %s）：" % cur).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None, True
        if not choice:
            return None, False
        if choice.lower() in ("q", "quit", "exit"):
            return None, True
        t, hits = resolve_theme(themes, choice)
        if t:
            return t, False
        if hits:
            print("\n[*] '%s' 匹配到多套主题，请进一步指定：" % choice)
            for h in hits[:12]:
                print("    [%s] %s" % (h["id"], h["name"]))
            if len(hits) > 12:
                print("    ... 共 %d 项" % len(hits))
        else:
            print("\n[-] 没有找到主题 '%s'，请重新输入（共 %d 套可选）" % (choice, len(themes)))


def theme_span(themes):
    if not themes:
        return "?~?"
    nums = [t["id"] for t in themes if t["id"].isdigit()]
    lo = min(nums, key=lambda x: int(x)) if nums else "000"
    hi = max(nums, key=lambda x: int(x)) if nums else "000"
    has_custom = any(not t["id"].isdigit() for t in themes)
    return ("%s~%s" % (lo, hi)) if not has_custom else ("%s~%s (+自定)" % (lo, hi))


def pick_theme(args):
    """需要换肤的命令统一入口：返回 (主题号, 是否失败)"""
    if args.no_theme:
        return read_theme(), False

    themes = load_themes()
    cur = read_theme()
    span = theme_span(themes)
    n = len(themes)

    target = None
    if args.choice:
        target, hits = resolve_theme(themes, args.choice)
        if not target:
            if hits:
                print("\n[*] 匹配到 %d 个，请输入具体编号：" % len(hits))
                for h in hits[:12]:
                    print("    [%s] %s" % (h["id"], h["name"]))
            else:
                print("\n[-] 没找到主题 '%s'（共 %d 套）" % (args.choice, n))
            return None, True
    else:
        target, cancelled = ask_theme(themes, cur)
        if cancelled:
            return None, True

    if target:
        write_theme(target["id"])
        print("\n[+] 切换主题 → %s - %s" % (target["id"], target["name"]))
        return target["id"], False

    cur_t = next((t for t in themes if t["id"] == cur or (cur.isdigit() and t["id"].isdigit() and int(cur) == int(t["id"]))), None)
    if cur_t:
        print("\n[=] 保持当前应用主题 %s - %s" % (cur, cur_t["name"]))
    else:
        print("\n[=] 保持当前应用主题 %s" % cur)
    return cur, False


def open_pdf(args, ok):
    """编译完成后打开 PDF"""
    if args.no_open or not ok:
        return
    path = os.path.join(ROOT, "main.pdf")
    if not os.path.exists(path):
        return
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        print("  已打开 %s" % path)
    except Exception as e:
        print("  [!] 打开 PDF 失败：%s" % e)


def cmd_build(args, passes):
    """① 换模板 → 问主题 → 渲染素材 → 正文编译三遍"""
    banner("换模板并编译",
           "同步模板 → 渲染素材(%d 遍/个) → 正文编译 %d 遍" % (args.asset_passes, passes))
    sync_ok = sync_template(args.template, ROOT, args.dry_run)
    num, theme_err = pick_theme(args)
    if theme_err:
        return False
    ok = build_assets(num, jobs=args.jobs, passes=args.asset_passes)[0]
    return build_pdf(passes) and ok and sync_ok


def cmd_quick(args, passes):
    """② 正文单次编译，只编一遍"""
    banner("正文单次编译", "只编 %d 遍" % passes)
    return build_pdf(passes)


def cmd_refresh(args, passes):
    banner("刷新素材", "只重渲改过的素材（三个背景除外）")
    return refresh_changed(read_theme(), args.jobs, args.asset_passes)


def cmd_theme(args, passes):
    """③ 换肤并编译：改主题号 → 渲染素材 → 编译"""
    themes = load_themes()
    cur = read_theme()

    if args.list:
        display_all_themes(themes, cur)
        return True

    banner("换肤并编译", "当前应用主题：%s" % cur)

    num, theme_err = pick_theme(args)
    if theme_err:
        return False

    if args.no_build:
        print("\n[!] --no-build：只改了 main.tex")
        return True

    ok = build_assets(num, jobs=args.jobs, passes=args.asset_passes)[0]
    return build_pdf(passes) and ok


COMMANDS = {
    "build": cmd_build,
    "quick": cmd_quick,
    "theme": cmd_theme,
    "refresh": cmd_refresh,
}
DESC = {
    "build": "② 换模板并编译：同步模板 → 问主题 → 渲染素材 → 正文编译三遍",
    "quick": "① 正文单次编译：只编一遍",
    "theme": "③ 换肤并编译：改主题号 → 渲染素材 → 编译",
    "refresh": "只重渲改过的素材",
}


def main():
    ap = argparse.ArgumentParser(
        description="孤星模板一图流",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join("  %-8s %s" % (k, v) for k, v in DESC.items()))
    ap.add_argument("command", nargs="?", choices=list(COMMANDS), help="功能")
    ap.add_argument("choice", nargs="?", help="theme 子命令的主题号或名字")
    ap.add_argument("--project", "-p", default=DEFAULT_ROOT, help="工程目录")
    ap.add_argument("--template", "-t", default=DEFAULT_ROOT, help="模板目录（用于同步）")
    ap.add_argument("--passes", type=int, default=None, help="正文编译遍数")
    ap.add_argument("--asset-passes", type=int, default=1, help="每个素材渲染几遍（默认 1）")
    ap.add_argument("--jobs", "-j", type=int, default=8, help="并行渲染素材数")
    ap.add_argument("--list", "-l", action="store_true", help="theme：列出全部主题")
    ap.add_argument("--no-build", action="store_true", help="theme：只改主题号不编译")
    ap.add_argument("--dry-run", "-n", action="store_true", help="只列出要同步的文件，不写")
    ap.add_argument("--no-theme", action="store_true", help="不弹主题输入，沿用 main.tex 里的主题号")
    ap.add_argument("--no-open", action="store_true", help="编译完不自动打开 PDF")
    ap.add_argument("--no-cache", action="store_true", help="忽略素材缓存，强制全部重渲")
    args = ap.parse_args()

    if not args.command:
        print("\n孤星模板 用法：")
        for k, v in DESC.items():
            print("  python tools/lonetrail.py %-8s %s" % (k, v))
        return 0

    args.template = os.path.abspath(args.template)
    set_root(args.project)
    if not os.path.exists(MAIN_TEX):
        print("[-] %s 里没有 main.tex" % ROOT)
        return 1
    # 每次启动时，自动扫描识别 palettes/tex/ 并同步更新 palettes/themes.tex
    sync_themes(ROOT)
    if not os.path.exists(os.path.join(ROOT, "palettes", "themes.tex")):
        print("[-] %s 里没有 palettes/themes.tex" % ROOT)
        return 1

    if args.no_cache:
        try:
            os.remove(os.path.join(TMP_DIR, ".asset_hash.json"))
        except OSError:
            pass

    passes = args.passes if args.passes else (1 if args.command == "quick" else 3)
    t0 = time.time()

    ok = COMMANDS[args.command](args, passes)

    print("=" * 60)
    if ok:
        print("  完成 → %s  （总耗时 %.1fs）" % (os.path.join(ROOT, "main.pdf"), time.time() - t0))
        open_pdf(args, ok)
    else:
        print("  失败，见上方错误")
    print("=" * 60)
    return 0 if ok else 1


def run():
    """包一层：双击 bat 运行时异常也别一闪而过"""
    try:
        code = main()
    except KeyboardInterrupt:
        code = 1
    except Exception as e:
        import traceback
        traceback.print_exc()
        code = 1
    pause_exit(code)


if __name__ == "__main__":
    run()
