# 实验室 GPU 监控 (Lab GPU Monitor)

[English](README.md) | 简体中文

一套轻量级的实验室 GPU 服务器集群监控系统。可采集多台服务器的 GPU、CPU、内存、
磁盘、网络以及各 GPU 上的进程信息，支持终端 CLI 或网页仪表盘两种查看方式。

## 架构

| 组件       | 路径                  | 职责                                                | 端口    |
|------------|-----------------------|-----------------------------------------------------|---------|
| Agent      | `monitor_serve/`      | 部署在每台被监控服务器上，暴露 `GET /metrics`        | `48210` |
| 网页仪表盘 | `monitor_dashboard/`  | 中央主机，轮询所有 Agent，提供网页 UI + `/api/data`  | `48080` |
| CLI 客户端 | `monitor_cli_client/` | 终端客户端，轮询所有 Agent，支持键盘导航             | —       |

## 快速开始

### 1. Agent（每台被监控服务器）
```bash
cd monitor_serve
pip install -r requirements.txt
python agent.py            # 监听 0.0.0.0:48210
```
Linux 上如需常驻服务，可参照并安装 `gpu_monitor.service`（systemd）。

### 2. 网页仪表盘（中央主机）
编辑 `dashboard.py` 中的 `SERVER_AGENTS`，把 `<agent-0X-host>` 占位符替换为实际的
主机名或 IP，然后：
```bash
cd monitor_dashboard
pip install -r requirements.txt
python dashboard.py        # 打开 http://<host>:48080
```

### 3. CLI 客户端
同样先编辑 `main.py` 中的 `SERVER_AGENTS`，然后：
```bash
cd monitor_cli_client
pip install -r requirements.txt
python main.py             # 快捷键：M/S/G/P/D/E · R 重连 · Q 退出
```
用 PyInstaller 打包为单个 Windows 可执行文件：`pyinstaller -F main.py`。

## 配置
- 把 `dashboard.py` 与 `main.py` 中的 `<agent-0X-host>` 占位符替换为真实主机。
- 默认端口：Agent `48210`（`AGENT_PORT`），仪表盘 `48080`（`DASHBOARD_PORT`）。

## 环境要求
Python 3.8+。各组件依赖分别列在其目录下的 `requirements.txt` 中。
`pynvml`（仅 Agent 需要）依赖已安装的 NVIDIA 驱动。
