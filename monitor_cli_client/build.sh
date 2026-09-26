#!/usr/bin/env bash
# CLI 客户端单文件打包脚本（Linux / macOS）。 / Single-file build script for the CLI client (Linux / macOS).
# 产物：dist/gpu-monitor-cli —— 双击/直接运行即进入 TUI，不依赖目标机 Python。 / Output: dist/gpu-monitor-cli — launches the TUI on run, no Python needed on the target.
# 用法 / Usage:  bash build.sh
# 注意 / Note: PyInstaller 不能跨平台交叉编译——请在与部署目标相同的 OS + 架构上打包。 / PyInstaller cannot cross-compile — build on the same OS + arch as the deploy target.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

echo "== 实验室 GPU 监控 · CLI 打包 / Lab GPU Monitor · CLI build =="

if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 python3，请先安装。/ python3 not found, please install it first." >&2
  exit 1
fi

echo "-- 安装依赖 + PyInstaller / Installing deps + PyInstaller..."
python3 -m pip install --upgrade pip >/dev/null
python3 -m pip install -r requirements.txt >/dev/null
python3 -m pip install pyinstaller >/dev/null

echo "-- 打包中 / Building (onefile)..."
# textual/rich 需连同其 .tcss/数据文件一起收集 / textual & rich ship .tcss/data files that must be collected
python3 -m PyInstaller --noconfirm --clean -F \
  --name gpu-monitor-cli \
  --collect-all textual \
  --collect-all rich \
  main.py

echo "== 完成 / Done =="
echo "产物 / Output: $HERE/dist/gpu-monitor-cli"
echo "运行 / Run:  ./dist/gpu-monitor-cli            # 直接进入 TUI / launches the TUI"
echo "高级 / Advanced: --once | --export json|csv [--out FILE] | --agents \"name=host:port,...\" | --version"
