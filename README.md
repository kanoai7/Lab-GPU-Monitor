# Lab GPU Monitor

English | [简体中文](README.zh-CN.md)

A lightweight monitoring system for a lab GPU server cluster. It reports GPU, CPU,
memory, disk, network and per-GPU process information across multiple servers,
viewable from a terminal CLI or a web dashboard.

## Architecture

| Component     | Path                  | Role                                                     | Port    |
|---------------|-----------------------|----------------------------------------------------------|---------|
| Agent         | `monitor_serve/`      | Runs on each monitored server; exposes `GET /metrics`    | `48210` |
| Web dashboard | `monitor_dashboard/`  | Central host; polls all agents, serves web UI + `/api/data` | `48080` |
| CLI client    | `monitor_cli_client/` | Terminal client; polls all agents, keyboard navigation   | —       |

## Quick start

### 1. Agent (on each monitored server)
```bash
cd monitor_serve
pip install -r requirements.txt
python agent.py            # listens on 0.0.0.0:48210
```
For a persistent service on Linux, adapt and install `gpu_monitor.service` (systemd).

### 2. Web dashboard (central host)
Edit `SERVER_AGENTS` in `dashboard.py`, replacing the `<agent-0X-host>` placeholders
with your agents' hostnames or IPs. Then:
```bash
cd monitor_dashboard
pip install -r requirements.txt
python dashboard.py        # open http://<host>:48080
```

### 3. CLI client
Edit `SERVER_AGENTS` in `main.py` the same way, then:
```bash
cd monitor_cli_client
pip install -r requirements.txt
python main.py             # keys: M/S/G/P/D/E · R reconnect · Q quit
```
Build a single Windows executable with PyInstaller: `pyinstaller -F main.py`.

## Configuration
- Replace the `<agent-0X-host>` placeholders in `dashboard.py` and `main.py` with real hosts.
- Default ports: agent `48210` (`AGENT_PORT`), dashboard `48080` (`DASHBOARD_PORT`).

## Requirements
Python 3.8+. Dependencies are listed per component in each `requirements.txt`.
`pynvml` (agent only) requires the NVIDIA driver to be installed.
