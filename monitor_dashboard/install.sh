#!/usr/bin/env bash
# 中央仪表盘一键安装脚本（Linux + systemd）。 / One-shot installer for the central dashboard (Linux + systemd).
# 作用：建虚拟环境、装依赖、生成并启用 systemd 服务，监听 48080。 / Creates a venv, installs deps, generates + enables a systemd service on port 48080.
# 用法 / Usage:  bash install.sh
# 首次启动会自动生成 config.json（含签名密钥），请在设置页添加 Agent。 / First launch auto-creates config.json (with a signing key); add agents in the settings page.
set -euo pipefail

PORT="${DASHBOARD_PORT:-48080}"
SVC_NAME="gpu-monitor-dashboard"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_USER="$(id -un)"
PYBIN="$HERE/.venv/bin/python"

echo "== 实验室 GPU 监控 · Dashboard 安装 / Lab GPU Monitor · Dashboard installer =="
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
  echo "已跳过 systemd 安装。可手动运行：$PYBIN $HERE/dashboard.py"
  echo "Skipped systemd. Run manually: $PYBIN $HERE/dashboard.py"
  exit 0
fi

TMP_UNIT="$(mktemp)"
cat > "$TMP_UNIT" <<EOF
[Unit]
Description=Lab GPU Monitor Dashboard (dashboard.py)
After=network.target

[Service]
User=$RUN_USER
WorkingDirectory=$HERE
ExecStart=$PYBIN $HERE/dashboard.py
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
echo "打开 / Open: http://<本机IP/this-host-ip>:$PORT  然后在设置页添加 Agent / then add agents in Settings"
echo "提示 / Note: 前端已随仓库提交（static/dist），部署无需 node。仅当修改前端源码（frontend/）时才需："
echo "  Frontend is pre-built and committed (static/dist); deployment needs no node. Only to change the frontend:"
echo "    cd $HERE/frontend && npm install && npm run build"
