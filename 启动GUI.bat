@echo off
title MiNote Sync Pro Launcher

echo 正在启动 MiNote Sync Pro GUI...
echo.

REM 检查 Python 是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误：未检测到 Python，请先安装 Python 3.7 或更高版本
    pause
    exit /b 1
)

REM 检查必需的包
echo 检查依赖包...
python -c "import pyperclip" >nul 2>&1
if %errorlevel% neq 0 (
    echo 正在安装 pyperclip...
    pip install pyperclip
)

REM 启动 GUI
echo 启动 GUI 程序...
python gui.py

pause