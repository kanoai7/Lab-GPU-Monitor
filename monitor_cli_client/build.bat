@echo off
REM CLI client single-file build script for Windows.
REM Output: dist\gpu-monitor-cli.exe
REM Usage: double-click this file, or run build.bat
REM PyInstaller cannot cross-compile; this produces a Windows exe.

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

echo -- Building onefile...
REM textual/rich ship data files that must be collected
python -m PyInstaller --noconfirm --clean -F --name gpu-monitor-cli --collect-all textual --collect-all rich main.py

echo == Done ==
echo Output: %~dp0dist\gpu-monitor-cli.exe
echo Run: dist\gpu-monitor-cli.exe
echo Advanced: --once ^| --export json^|csv [--out FILE] ^| --agents "name=host:port,..." ^| --version
pause
