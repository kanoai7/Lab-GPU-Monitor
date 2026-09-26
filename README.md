# Lab GPU Monitor

English | [简体中文](README.zh-CN.md)

A lightweight monitoring system for a lab GPU server cluster. It reports GPU, CPU,
memory, disk, network and per-GPU process information across multiple servers,
viewable from a terminal CLI or a web dashboard.

## Scope

Built for a small lab — a single machine up to a few dozen servers, polled on demand.
For larger fleets, use a push-based stack such as NVIDIA DCGM-Exporter + Prometheus + Grafana.

## Architecture

| Component     | Path                  | Role                                                     | Port    |
|---------------|-----------------------|----------------------------------------------------------|---------|
| Agent         | `monitor_serve/`      | Runs on each monitored server; exposes `GET /metrics`    | `48210` |
| Web dashboard | `monitor_dashboard/`  | Central host; polls all agents, serves web UI + `/api/data` | `48080` |
| CLI client    | `monitor_cli_client/` | Terminal client; polls all agents, keyboard navigation   | —       |

No source editing is required to run any component — agents are configured at runtime
(the dashboard's Settings page, the CLI's settings page, or a `config.json` file).
All three prefer the production WSGI server **waitress**, falling back to the Flask
dev server automatically if it is not installed.

## Quick start

### 1. Agent (on each monitored server)
```bash
cd monitor_serve
pip install -r requirements.txt
python agent.py            # listens on 0.0.0.0:48210
```
Environment overrides: `AGENT_PORT` (default `48210`) and `AGENT_SAMPLE_INTERVAL`
(background sampling interval in seconds, default `2`). A background thread samples
once per interval and `/metrics` returns the latest snapshot, so many pollers hitting
one agent cannot corrupt the network-speed / CPU math.

For a persistent service on Linux + systemd, run the installer (creates a venv,
installs deps, generates and enables a unit, asks before touching the firewall):
```bash
bash install.sh
```
Or build a single binary with PyInstaller (`pyinstaller -F agent.py`) to run without a
Python environment on the target.

### 2. Web dashboard (central host)
```bash
cd monitor_dashboard
pip install -r requirements.txt
python dashboard.py        # open http://<host>:48080
```
On first launch a `config.json` is created next to `dashboard.py` (path overridable via
`DASHBOARD_CONFIG`). Open the site, go to **Settings**, and add your agents by host/IP or
full URL — no source editing. For a systemd service, `bash install.sh` inside the folder.

### 3. CLI client
```bash
cd monitor_cli_client
pip install -r requirements.txt
python main.py             # keys: M/S/G/P/D/E · R reconnect · Q quit
```
On first run the CLI opens its settings page: press **A** to add an agent, **X** to remove
one, **+/-** to change the refresh rate. Settings are saved to a portable `config.json`
(next to the executable when frozen, else a per-user directory; path overridable via
`MONITOR_CLI_CONFIG`). Build a single Windows executable with `pyinstaller -F main.py`.

## Configuration
- **Agents**: added at runtime — Settings page (dashboard/CLI) or `config.json`. Each entry
  is either `{"host": "192.168.3.10", "port": 48210}` or `{"url": "http://host:48210/metrics"}`.
- **Ports**: agent `48210` (`AGENT_PORT` env); dashboard `48080` (in `config.json`, editable
  in Settings, applied on restart).
- **`config.json`** holds runtime state (agents, thresholds, and for the dashboard a
  `secret_key` and password hash). It is git-ignored and should never be committed.

## Authentication
The dashboard supports optional single-shared-password auth. In **Settings → Security**,
set a password and enable auth; the dashboard then requires login and returns `401` for
API calls without a session. The agent's `/metrics` endpoint is unauthenticated by design —
keep agents on a trusted network or behind the dashboard.

## Requirements
Python 3.8+. Dependencies are listed per component in each `requirements.txt`.
`pynvml` (agent only) requires the NVIDIA driver to be installed.

## License
[MIT](LICENSE).
