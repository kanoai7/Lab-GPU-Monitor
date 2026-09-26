@echo off
REM CLI 客户端单文件打包脚本（Windows）。 / Single-file build script for the CLI client (Windows).
REM 产物：dist\gpu-monitor-cli.exe —— 双击即用、不依赖目标机 Python。 / Output: dist\gpu-monitor-cli.exe — double-click to run, no Python needed on the target.
REM 用法 / Usage:  双击本文件，或在命令行执行 build.bat / double-click this file, or run build.bat
REM 注意 / Note: PyInstaller 不能跨平台交叉编译；此脚本产出 Windows exe。 / PyInstaller cannot cross-compile; this produces a Windows exe.
setlocal
cd /d "%~dp0"

echo == Lab GPU Monitor . CLI build ==

where python >nul 2>&1
if errorlevel 1 (
  echo Python not found. Please install Python first.
  pause
  exit /b 1
)

echo -- Installing deps + PyInstaller...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

echo -- Building (onefile)...
REM textual/rich ship .tcss/data files that must be collected
python -m PyInstaller --noconfirm --clean -F --name gpu-monitor-cli --collect-all textual --collect-all rich main.py

echo == Done ==
echo Output: %~dp0dist\gpu-monitor-cli.exe
echo Run: dist\gpu-monitor-cli.exe   (launches the TUI)
echo Advanced: --once ^| --export json^|csv [--out FILE] ^| --agents "name=host:port,..." ^| --version
pause
