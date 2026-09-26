#!/usr/bin/env bash
# 监控 Agent 一键安装脚本（Linux + systemd）。 / One-shot installer for the monitoring Agent (Linux + systemd).
# 作用：建虚拟环境、装依赖、生成并启用 systemd 服务，监听 48210。 / Creates a venv, installs deps, generates + enables a systemd service on port 48210.
# 用法 / Usage:  bash install.sh
# 非破坏性：修改防火墙前会先征询同意。 / Non-destructive: asks before touching the firewall.
set -euo pipefail

PORT="${AGENT_PORT:-48210}"
SVC_NAME="gpu-monitor-agent"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_USER="$(id -un)"
PYBIN="$HERE/.venv/bin/python"

echo "== 实验室 GPU 监控 · Agent 安装 / Lab GPU Monitor · Agent installer =="
echo "目录 / Dir: $HERE"
echo "用户 / User: $RUN_USER   端口 / Port: $PORT"

# 1) 系统检查 / System checks
if [ "$(uname -s)" != "Linux" ]; then
  echo "本脚本仅支持 Linux。/ This script supports Linux only." >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 python3，请先安装。/ python3 not found, please install it first." >&2
  exit 1
fi
if command -v nvidia-smi >/dev/null 2>&1; then
  echo "[OK] 检测到 NVIDIA 驱动 / NVIDIA driver detected."
else
  echo "[提示/Note] 未检测到 nvidia-smi：无 GPU 或驱动未装，Agent 仍会上报 CPU/内存/磁盘。"
  echo "            nvidia-smi not found: no GPU or driver missing; the agent still reports CPU/mem/disk."
fi

# 2) 虚拟环境 + 依赖 / venv + dependencies
echo "-- 创建虚拟环境并安装依赖 / Creating venv and installing dependencies..."
python3 -m venv "$HERE/.venv"
"$PYBIN" -m pip install --upgrade pip >/dev/null
"$PYBIN" -m pip install -r "$HERE/requirements.txt"

# 3) 生成 systemd 单元 / Generate the systemd unit
UNIT_PATH="/etc/systemd/system/${SVC_NAME}.service"
echo "-- 将安装 systemd 服务 / Will install systemd service: $UNIT_PATH"
read -r -p "继续安装并开机自启？/ Install and enable on boot? [y/N] " ans
if [ "${ans,,}" != "y" ]; then
  echo "已跳过 systemd 安装。可手动运行：$PYBIN $HERE/agent.py"
  echo "Skipped systemd. Run manually: $PYBIN $HERE/agent.py"
  exit 0
fi

TMP_UNIT="$(mktemp)"
cat > "$TMP_UNIT" <<EOF
[Unit]
Description=Lab GPU Monitor Agent (agent.py)
After=network.target

[Service]
User=$RUN_USER
WorkingDirectory=$HERE
Environment="AGENT_PORT=$PORT"
ExecStart=$PYBIN $HERE/agent.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo cp "$TMP_UNIT" "$UNIT_PATH"
rm -f "$TMP_UNIT"
sudo systemctl daemon-reload
sudo systemctl enable --now "$SVC_NAME"
echo "[OK] 服务已启动 / service started: systemctl status $SVC_NAME"

# 4) 防火墙（可选，需明确同意）/ Firewall (optional, explicit consent required)
if command -v ufw >/dev/null 2>&1 && sudo ufw status | grep -q "active"; then
  read -r -p "检测到 ufw，放行端口 $PORT？/ ufw detected, open port $PORT? [y/N] " fw
  if [ "${fw,,}" = "y" ]; then
    sudo ufw allow "${PORT}/tcp"
    echo "[OK] 已放行 $PORT/tcp"
  else
    echo "未修改防火墙，请自行放行 $PORT。/ Firewall unchanged; open $PORT yourself."
  fi
else
  echo "[提示/Note] 如有防火墙，请放行 TCP $PORT。/ If a firewall is present, open TCP $PORT."
fi

echo "== 完成 / Done =="
echo "验证 / Verify: curl http://127.0.0.1:$PORT/metrics"
