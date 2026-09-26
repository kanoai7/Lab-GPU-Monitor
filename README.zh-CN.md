# 实验室 GPU 监控 (Lab GPU Monitor)

[English](README.md) | 简体中文

一套轻量级的实验室 GPU 服务器集群监控系统。可采集多台服务器的 GPU、CPU、内存、
磁盘、网络以及各 GPU 上的进程信息，支持终端 CLI 或网页仪表盘两种查看方式。

## 适用规模

面向小型实验室——单机到低几十台服务器，按需轮询。
更大规模请改用 push 方案，例如 NVIDIA DCGM-Exporter + Prometheus + Grafana。

## 架构

| 组件       | 路径                  | 职责                                                | 端口    |
|------------|-----------------------|-----------------------------------------------------|---------|
| Agent      | `monitor_serve/`      | 部署在每台被监控服务器上，暴露 `GET /metrics`        | `48210` |
| 网页仪表盘 | `monitor_dashboard/`  | 中央主机，轮询所有 Agent，提供网页 UI + `/api/data`  | `48080` |
| CLI 客户端 | `monitor_cli_client/` | 终端客户端，轮询所有 Agent，支持键盘导航             | —       |

三个组件都**无需改源码**即可运行——Agent 均在运行时配置（仪表盘设置页、CLI 设置页，
或 `config.json` 文件）。三者都优先使用生产级 WSGI 服务器 **waitress**，未安装时自动
回退到 Flask 开发服务器。

## 快速开始

### 1. Agent（每台被监控服务器）
```bash
cd monitor_serve
pip install -r requirements.txt
python agent.py            # 监听 0.0.0.0:48210
```
环境变量：`AGENT_PORT`（默认 `48210`）、`AGENT_SAMPLE_INTERVAL`（后台采样间隔秒数，默认 `2`）。
后台线程按间隔采样一次，`/metrics` 只返回最近快照，因此多个轮询端同时请求也不会打乱
网速 / CPU 的计算。

Linux + systemd 上如需常驻服务，运行安装脚本（自动建 venv、装依赖、生成并启用服务，
修改防火墙前会先询问）：
```bash
bash install.sh
```
或用 PyInstaller 打包为单个二进制（`pyinstaller -F agent.py`），免去目标机的 Python 环境。

### 2. 网页仪表盘（中央主机）
```bash
cd monitor_dashboard
pip install -r requirements.txt
python dashboard.py        # 打开 http://<host>:48080
```
首次启动会在 `dashboard.py` 同目录自动生成 `config.json`（路径可用 `DASHBOARD_CONFIG`
覆盖）。打开网页进入**设置**页，用主机/IP 或完整 URL 添加 Agent，无需改源码。
需要常驻服务时，在该目录运行 `bash install.sh`。

### 3. CLI 客户端
```bash
cd monitor_cli_client
pip install -r requirements.txt
python main.py             # 快捷键：M/S/G/P/D/E · R 重连 · Q 退出
```
首次运行会直接进入设置页：按 **A** 添加 Agent，**X** 删除，**+/-** 调整刷新频率。设置会
保存到便携的 `config.json`（打包后在可执行文件同目录，否则在用户目录；路径可用
`MONITOR_CLI_CONFIG` 覆盖）。用 `pyinstaller -F main.py` 打包为单个 Windows 可执行文件。

## 配置
- **Agent 列表**：运行时添加——设置页（仪表盘/CLI）或 `config.json`。每条形如
  `{"host": "192.168.3.10", "port": 48210}` 或 `{"url": "http://host:48210/metrics"}`。
- **端口**：Agent `48210`（`AGENT_PORT` 环境变量）；仪表盘 `48080`（写在 `config.json`，
  设置页可改，重启后生效）。
- **`config.json`** 保存运行时状态（Agent 列表、告警阈值，仪表盘还含 `secret_key` 与密码
  哈希）。该文件已被 git 忽略，切勿提交。

## 鉴权
仪表盘支持可选的「单一共享密码」鉴权。在**设置 → 安全**中设置密码并开启鉴权后，
网页需登录访问，未带会话的 API 调用返回 `401`。Agent 的 `/metrics` 端点默认不鉴权——
请将 Agent 置于可信网络内，或仅经由仪表盘访问。

## 环境要求
Python 3.8+。各组件依赖分别列在其目录下的 `requirements.txt` 中。
`pynvml`（仅 Agent 需要）依赖已安装的 NVIDIA 驱动。

## 许可证
[MIT](LICENSE)。
