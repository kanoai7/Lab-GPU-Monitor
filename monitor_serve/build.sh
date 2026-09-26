#!/usr/bin/env bash
# Agent 单文件打包脚本（Linux / macOS）。 / Single-file build script for the agent (Linux / macOS).
# 产物：dist/agent —— 一个不依赖目标机 Python 环境的独立可执行文件。 / Output: dist/agent — a standalone executable that needs no Python on the target.
# 用法 / Usage:  bash build.sh
# 注意 / Note: PyInstaller 不能跨平台/跨架构交叉编译——请在与部署目标相同的 OS + 架构 + glibc 上打包。 / PyInstaller cannot cross-compile — build on the same OS + arch + glibc as the deploy target.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

echo "== 实验室 GPU 监控 · Agent 打包 / Lab GPU Monitor · Agent build =="

if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 python3，请先安装。/ python3 not found, please install it first." >&2
  exit 1
fi

echo "-- 安装依赖 + PyInstaller / Installing deps + PyInstaller..."
python3 -m pip install --upgrade pip >/dev/null
python3 -m pip install -r requirements.txt >/dev/null
python3 -m pip install pyinstaller >/dev/null

echo "-- 打包中 / Building (onefile)..."
python3 -m PyInstaller --noconfirm --clean -F \
  --name agent \
  --hidden-import waitress \
  agent.py

echo "== 完成 / Done =="
echo "产物 / Output: $HERE/dist/agent"
echo "运行 / Run:  ./dist/agent            # 默认监听 0.0.0.0:48210 / listens on 0.0.0.0:48210 by default"
echo "端口/间隔可用环境变量覆盖 / Override port & interval via env: AGENT_PORT=48210 AGENT_SAMPLE_INTERVAL=2 ./dist/agent"
