@echo off
chcp 65001 >nul
title LoneTrail - Quick Build (1 pass)
cd /d "%~dp0"
set "PY_CMD=python"
where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if not errorlevel 1 set "PY_CMD=py"
)
%PY_CMD% "tools\lonetrail.py" quick --project "%~dp0." --passes 1 %*
echo.
pause
