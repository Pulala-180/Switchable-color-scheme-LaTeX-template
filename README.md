# 可切换配色 · 明日方舟·孤星 LaTeX 笔记模板

Arknights Lone Trail 风格学术笔记 / 作业报告模板，基于 XeLaTeX 编译。

> **致谢**：本项目基于 [ARKNIGHT-LONETRAIL-LATEX-TEMPLATE](https://github.com/M0nster-3/ARKNIGHT-LONETRAIL-LATEX-TEMPLATE) 修改而来，致敬原作者的惊艳设计。

---

## ⚡ 30 秒极简上手

1. **环境准备**：安装好 **TeX Live**（推荐 2023+，需包含 `xelatex`）与 **Python 3.8+**。
2. **日常写笔记**：在 `chapters/` 目录下编写各章内容，在 `main.tex` 中修改封面信息。
3. **一键编译（根目录下两个脚本）**：
   - ⚡ **【正文单次编译】.bat**：**日常码字推荐！** 仅编译正文 1 遍（约 5 秒），最快查看排版改动。
   - 🎨 **【换模板并编译】.bat**：**切换与管理配色必备！** 自动列出全部可用主题与当前应用主题，输入编号回车即自动重渲矢量素材并完成编译。

---

## 🎨 换肤与自定义主题

### 1. 切换主题（142 套精选高定配色）

* 📑 **完整成品 PDF 样例文档目录**：所有 143 套（含 000 原版基准）真实编译生成的完整 PDF 实例文档已归档保存在 **`palettes/PDF Previews/`**（例如 `theme_000.pdf`、`theme_008.pdf` 等，内含 `000_主题PDF完整索引表.txt`）。可直接在此打开查验任意主题下实际公式、定理盒、三色条带及矢量底纹的最终排版呈现！
* 🖼️ **主题效果预览图目录**：所有主题的真实排版效果长图保存在 **`palettes/PNG previews/`**（例如 `theme_000.png`、`theme_008.png` 等），挑选配色时可直接在此打开快速看图选色！
* ⚡ **一键交互换肤**：双击运行 **【换模板并编译】.bat**，终端将清晰展示全部主题与当前应用主题：
  - **直接回车**：保持当前主题继续编译。
  - **输入编号或名称**（如 `000` ~ `142`，或名称关键字如 `赛博`、`梅耶`）：自动切换主题、重新渲染标题盒与背景素材，并完成正文编译。
  *(也可以随时在 `main.tex` 中直接修改 `\SelectTheme{008}`)*

### 2. 自制或增删主题（全自动检测同步）

* 📄 **官方规范范本**：`palettes/tex/theme_template.tex`（内含详细位置说明与选色建议）。
* ✏️ **三步自制主题**：
  1. 复制 `theme_template.tex` 并重命名（如 `theme_143.tex` 或 `theme_myblue.tex`）；
  2. 参考下方速查表修改 RGB 纯数值（0~255）；
  3. 双击运行 **【换模板并编译】.bat** 即可全自动识别生效！

#### 🎨 孤星色彩速查与避坑指南

| 颜色名称 | 出现位置 / 作用 | 选色建议与避坑 |
| :--- | :--- | :--- |
| **`qiancheng`** | 封面主标题、大章节标题、页眉页脚线、标题盒 | **中深主色**（明度 30%~55%），保证浅底上对比分明，切忌过浅 |
| **`lv` / `huang` / `hong`** | 封面及正文经典三色条带（左/中/右） | **明度均衡**（冷/暖/点睛三段式），避免某一颜色过于刺眼 |
| **`qianbai`** | 页面物理纸张底色 | **极高明度**（RGB 242~252），可微偏暖米或冷灰，切忌偏灰暗 |
| **`mibai`** | 背景网格点阵、暗纹水印 | **仅比 `qianbai` 深 3%~8%**，作为背景呼吸感，太深会干扰阅读 |
| **`heise`** | 正文字体颜色（段落、公式、表格） | **极低明度**（RGB 0~35），推荐纯黑或深墨色，确保久读不累 |
| **6大定理色** | 定义/定理/命题/推论/引理/例题盒子 | **色相错开 + 中等明度**（40%~60%），读者扫一眼即可秒辨环境 |

> [!TIP]
> 删除旧主题只需直接在 `palettes/tex/` 目录中删除对应文件，运行脚本自动清理同步。

---

## 📝 封面与基本设置（main.tex）

在 `main.tex` 的「封面信息」区域直接修改即可：

```tex
% --- 封面信息设置 ---
\newcommand{\LoneTitleI}{Measure Theory}              % 封面主标题（英文/上层大字）
\newcommand{\LoneTitleII}{测度论}                     % 封面副标题（中文/下层小字）
\newcommand{\LoneAuthor}{@Mikukawaii2}                % 作者署名

% 课程信息（显示在封面中下方）
\newcommand{\LoneCourseI}{课程名称}                   % 课程名称 I（中文）
\newcommand{\LoneCourseII}{Measure Theory}            % 课程名称 II（英文）

% 学生姓名与学号（显示在封面信息表）
\newcommand{\LoneStudentName}{pulala}                 % 学生姓名
\newcommand{\LoneStudentID}{0123456789}               % 学号

% 日期（显示在封面信息表最后一行）
\newcommand{\LoneDate}{Friday 16\textsuperscript{th} October, 2026} % 封面日期

% 参考文献（封面左下角，最多三条）
\newcommand{\LoneRefA}{1.Jech."Set Theory".3rd ed,Springer,2003}
\newcommand{\LoneRefB}{2.Kechris."Classical Descriptive Set Theory".Springer,1995}
\newcommand{\LoneRefC}{3.Engelking."General Topology".Heldermann Veriag,1989}
\newcommand{\LoneAcknowledgements}{\#.Rhine Lab Pioneer Project}

% --- 封面与目录显示开关（注释对应行即可隐藏）---
\DisplayCover    % 显示封面（注释掉则不显示）
\DisplayTOC      % 显示目录（注释掉则不显示）
```

---

## 📂 目录结构速览

```text
├── 【换模板并编译】.bat    交互式切换/管理配色并编译
├── 【正文单次编译】.bat    极速单次编译正文（约5秒）
├── main.tex              主入口：导言区、封面信息、正文入口
├── chapters/             正文各章节（写笔记主战场）
├── styles/               版式定义（宏包、盒子、封面样式）
├── palettes/
│   ├── tex/              单套主题独立配色文件（新增/删除主题放这里）
│   ├── themes.tex        主题配色总控（脚本启动全自动同步，无需手动改）
│   ├── PNG previews/     各主题高清效果预览长图（如 theme_000.png）
│   └── PDF Previews/     全套 143 款主题完整编译产出的 PDF 样例文档与索引表
├── assets/
│   ├── fonts/            模板自带字体（Avant Garde + 思源黑体）
│   ├── tikz/             矢量素材源文件
│   └── pdf/              预渲染素材 PDF（脚本自动生成）
└── tools/
    └── lonetrail.py      底层编译与主题同步内核
```

---

## 💡 常见问题与避坑

1. **改了配色后，为什么标题盒和封面背景颜色没变？**  
   因为标题盒、角标和封面背景为**矢量预渲染素材**。日常单次编译不会刷新素材，**必须运行一次【换模板并编译】.bat** 才会自动完成素材重绘。
2. **提示“目标 PDF 被占用”或保存失败？**  
   福昕（Foxit）、Adobe Acrobat 等阅读器正在打开 `main.pdf` 或 `assets/pdf/*.pdf` 锁定了文件。关掉阅读器后重新运行脚本即可。

---

<details>
<summary><b>🛠️ 进阶用户：命令行与脚本参数（点击展开）</b></summary>

支持直接使用 Python 调用底层工具 `tools/lonetrail.py`：

```bash
python tools/lonetrail.py quick              # 仅编译正文 1 遍
python tools/lonetrail.py build              # 完整换肤并编译正文 3 遍
python tools/lonetrail.py theme 042          # 直接指定切换为 042 主题并编译
python tools/lonetrail.py theme --list       # 打印全部主题清单及当前应用
python tools/lonetrail.py refresh            # 仅重渲有改动的素材文件
```
常用可选参数：
- `--passes N`：正文编译遍数
- `--no-open`：编译后不自动启动 PDF 阅读器
- `--jobs N`：素材并行渲染线程数（默认 8）
</details>

---

## 📜 字体与许可

- **ITC Avant Garde Gothic Bold**：商业字体，版权归 Monotype / ITC 所有，仅供个人学习研究。
- **思源黑体（Source Han Sans）**：遵循 SIL Open Font License (OFL)。
- 模板代码遵循原项目开源许可，原项目版权归原作者所有。

