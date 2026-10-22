@echo off
chcp 65001 >nul
title LoneTrail - Switch Template + Build
cd /d "%~dp0"
set "PY_CMD=python"
where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if not errorlevel 1 set "PY_CMD=py"
)
%PY_CMD% "tools\lonetrail.py" build --project "%~dp0." --passes 3 %*
echo.
pause
