# 文件名 / File: main.py
# 实验室 GPU 监控 · 终端客户端（Textual 重写）。 / Lab GPU Monitor · terminal client (Textual rewrite).
# 依赖 / Dependencies: pip install requests textual
# 双击即用：无参数直接进入交互式 TUI；也支持 --once / --export / --version 等可选高级 flag。
# Double-click to run: no args launches the interactive TUI; optional advanced flags --once / --export / --version are also supported.

import argparse
import csv
import io
import json
import os
import sys
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests

# 版本号（应用内「关于」与 --version 共用） / Version string (shared by in-app About and --version)
APP_VERSION = "v1.2"

# --- 配置 / Configuration ---
# 配置外置到 config.json：无需改源码即可增删 Agent、改刷新率/主题/阈值等。
# Config is externalized to config.json: manage agents, refresh rate, theme, thresholds, etc. without editing source.
# 打包成 exe 后，优先用 exe 同目录的 config.json（便携）；不可写时回退到用户目录。
# When packaged as an exe, prefer config.json next to the exe (portable); fall back to the user's home dir if not writable.
APP_NAME = "lab-gpu-monitor"
CONFIG_FILENAME = "config.json"

DEFAULT_CONFIG = {
    "refresh_rate": 10,          # 后台轮询间隔（秒） / Background poll interval (seconds)
    "ui_refresh": 1,             # 界面重绘节流（秒） / UI redraw throttle (seconds)
    "timeout": 2.0,              # 单 Agent 请求超时（秒） / Per-agent request timeout (seconds)
    "retries": 1,                # 失败重试次数（指数退避） / Retry count on failure (exponential backoff)
    "token": "",                 # 可选：Agent 若加鉴权则带 Bearer / Optional: Bearer token if the agent requires auth
    "agents": {},                # name -> {"url": ...} 或 {"host": ..., "port": 48210}
    "appearance": {
        "theme": "dark",         # dark | light
        "accent": "cyan",        # 强调色 / accent color
        "colorblind": False,     # 色盲友好调色板 / colorblind-friendly palette
        "density": "comfortable",  # comfortable | compact
        "agent_colors": {},      # name -> 颜色覆盖（缺省 auto 按调色板分配） / per-agent color override (auto by palette when unset)
    },
    "thresholds": {
        "gpu_temp": 80,          # ℃
        "gpu_mem_percent": 90,   # %
        "cpu_percent": 90,
        "mem_percent": 90,
        "disk_percent": 90,
        "bell": False,           # 超限响铃 / ring the terminal bell on breach
    },
    "display": {
        "sort_key": "index",     # index | util | mem | temp
        "filter_user": "",       # 进程页按用户名过滤 / filter processes by username
        "show_process_detail": True,  # 进程页显示命令行 / show cmdline on the process page
    },
}


def _app_dir():
    """程序所在目录（打包后为 exe 目录，否则为脚本目录）。 / Program dir (exe dir when frozen, else script dir)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _user_dir():
    """用户级配置目录，作为程序目录不可写时的回退。 / Per-user config dir, fallback when program dir isn't writable."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_NAME)


def _dir_writable(d):
    try:
        os.makedirs(d, exist_ok=True)
        test = os.path.join(d, ".write_test")
        with open(test, "w") as f:
            f.write("")
        os.remove(test)
        return True
    except OSError:
        return False


def config_path():
    """决定 config.json 路径：环境变量覆盖 > 程序目录 > 用户目录。 / Resolve config.json path: env override > program dir > user dir."""
    override = os.environ.get("MONITOR_CLI_CONFIG")
    if override:
        return override
    app_dir = _app_dir()
    existing = os.path.join(app_dir, CONFIG_FILENAME)
    if os.path.exists(existing) or _dir_writable(app_dir):
        return existing
    return os.path.join(_user_dir(), CONFIG_FILENAME)


def _deep_merge(base, override):
    """把 override 深合并进 base 的副本（仅对 dict 递归），用于补齐嵌套默认值。 / Deep-merge override into a copy of base (recursing into dicts) to fill nested defaults."""
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config():
    """加载配置；缺文件则用默认，缺字段（含嵌套）则补齐。 / Load config; use defaults if missing and fill missing (incl. nested) fields."""
    path = config_path()
    cfg = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[警告/Warn] 读取配置失败，使用默认值 / failed to read config, using defaults: {e}")
    merged = _deep_merge(DEFAULT_CONFIG, cfg or {})
    merged["agents"] = dict(merged.get("agents") or {})
    return merged, path


def save_config(cfg, path):
    """原子写回配置文件。 / Atomically write the config back to disk."""
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def agent_url(entry):
    """由配置条目得到 /metrics URL，兼容 {'url':...} 与 {'host':..,'port':..}。 / Build /metrics URL, supporting {'url':...} and {'host':..,'port':..}."""
    if entry.get("url"):
        return entry["url"]
    host = entry.get("host", "")
    port = entry.get("port", 48210)
    return f"http://{host}:{port}/metrics"


# --- 数据获取（健壮性：超时 + 退避重试 + 计时得延迟） / Data fetching (robustness: timeout + backoff retries + measured latency) ---
def fetch_single_agent(name, url, timeout=2.0, retries=1, token=""):
    """获取单个 Agent 数据；返回 status/data/latency_ms/error。 / Fetch one agent; returns status/data/latency_ms/error."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    last_err = "未知 / unknown"
    for attempt in range(max(1, retries + 1)):
        t0 = time.time()
        try:
            resp = requests.get(url, timeout=timeout, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            latency_ms = int((time.time() - t0) * 1000)
            return name, {"status": "online", "data": data, "latency_ms": latency_ms,
                          "updated": datetime.now()}
        except requests.exceptions.Timeout:
            last_err = "超时 / timeout"
        except requests.exceptions.RequestException:
            last_err = "连接失败 / connection failed"
        except json.JSONDecodeError:
            last_err = "数据解析失败 / bad JSON"
        # 指数退避（最后一次尝试后不再睡） / Exponential backoff (no sleep after the final attempt)
        if attempt < retries:
            time.sleep(0.25 * (2 ** attempt))
    return name, {"status": "offline", "data": None, "latency_ms": None,
                  "updated": datetime.now(), "error": last_err}


def fetch_all(agents, timeout=2.0, retries=1, token=""):
    """并发抓取所有 Agent；单台掉线不拖累其它。 / Fetch all agents concurrently; one down doesn't block the rest."""
    tasks = [(name, agent_url(cfg)) for name, cfg in agents.items()]
    store = {}
    if not tasks:
        return store
    with ThreadPoolExecutor(max_workers=min(32, len(tasks))) as ex:
        futs = [ex.submit(fetch_single_agent, n, u, timeout, retries, token) for n, u in tasks]
        for fut in futs:
            name, result = fut.result()
            store[name] = result
    return store


# --- 格式化辅助 / Formatting helpers ---
_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def spark(values, width=12):
    """把一串数值渲染为迷你趋势 sparkline（0-100 归一）。 / Render a series as a mini sparkline (normalized 0-100)."""
    vals = [v for v in values if v is not None]
    if not vals:
        return " " * width
    vals = vals[-width:]
    lo, hi = 0.0, max(100.0, max(vals))
    span = (hi - lo) or 1.0
    out = []
    for v in vals:
        idx = int((v - lo) / span * (len(_SPARK_CHARS) - 1))
        out.append(_SPARK_CHARS[max(0, min(len(_SPARK_CHARS) - 1, idx))])
    return "".join(out)


def fmt_gb(gb):
    if gb is None:
        return "N/A"
    return f"{gb/1024:.1f}T" if gb >= 1024 else f"{gb:.1f}G"


def gpu_free_mb(gpu):
    """GPU 空闲显存 MB。 / Free GPU memory in MB."""
    total = gpu.get("memory_total") or 0
    used = gpu.get("memory_used") or 0
    return max(0.0, total - used)
# --- 快照提取（headless 与 TUI 共用） / Snapshot extractors (shared by headless & TUI) ---
def iter_gpus(store):
    """遍历所有在线 Agent 的 GPU，产出 (agent_name, gpu_dict)。 / Yield (agent_name, gpu_dict) across all online agents."""
    for name, res in store.items():
        if res.get("status") != "online" or not res.get("data"):
            continue
        for g in (res["data"].get("gpus") or []):
            yield name, g


def iter_processes(store):
    """遍历所有 GPU 进程，产出 (agent_name, gpu_index, proc_dict)。 / Yield (agent, gpu_index, proc) for all GPU processes."""
    for name, g in iter_gpus(store):
        for p in (g.get("processes") or []):
            yield name, g.get("index"), p


def parse_agents_override(spec):
    """解析 --agents "name=host:port,..." 为 agents dict。 / Parse --agents "name=host:port,..." into an agents dict."""
    agents = {}
    for item in (spec or "").split(","):
        item = item.strip()
        if not item or "=" not in item:
            continue
        name, addr = item.split("=", 1)
        name, addr = name.strip(), addr.strip()
        if ":" in addr:
            host, port = addr.rsplit(":", 1)
            try:
                agents[name] = {"host": host, "port": int(port)}
            except ValueError:
                agents[name] = {"host": host, "port": 48210}
        else:
            agents[name] = {"host": addr, "port": 48210}
    return agents


def run_once(store):
    """把一次抓取结果打印为纯文本摘要（headless）。 / Print a plain-text summary of one fetch (headless)."""
    lines = []
    for name, res in store.items():
        if res.get("status") == "online":
            d = res["data"]
            gpus = d.get("gpus") or []
            sysm = d.get("system") or {}
            host = sysm.get("hostname", "?")
            lines.append(f"● {name} [{host}]  在线/online  {res.get('latency_ms')}ms  GPUs={len(gpus)}")
            for g in gpus:
                mt, mu = g.get("memory_total") or 0, g.get("memory_used") or 0
                pct = (mu / mt * 100) if mt else 0
                lines.append(
                    f"    GPU{g.get('index')} {g.get('name','?')}  util={g.get('utilization')}%"
                    f"  mem={mu:.0f}/{mt:.0f}MB({pct:.0f}%)  temp={g.get('temperature')}C"
                    f"  {g.get('sm_clock_mhz')}/{g.get('mem_clock_mhz')}MHz"
                    f"  procs={len(g.get('processes') or [])}")
        else:
            lines.append(f"○ {name}  离线/offline  ({res.get('error','?')})")
    print("\n".join(lines) if lines else "（无 Agent / no agents configured）")


def export_snapshot(store, fmt, out=None):
    """把一次抓取结果导出为 JSON 或 CSV（GPU 逐行）。 / Export one fetch as JSON or per-GPU CSV rows."""
    if fmt == "json":
        payload = {name: {k: (v.isoformat() if isinstance(v, datetime) else v)
                          for k, v in res.items()} for name, res in store.items()}
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:  # csv：GPU 逐行 / one row per GPU
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["agent", "gpu_index", "name", "util%", "mem_used_mb", "mem_total_mb",
                    "mem%", "temp_c", "power_w", "sm_mhz", "mem_mhz", "throttle", "ecc", "procs"])
        for name, g in iter_gpus(store):
            mt, mu = g.get("memory_total") or 0, g.get("memory_used") or 0
            w.writerow([name, g.get("index"), g.get("name"), g.get("utilization"),
                        f"{mu:.0f}", f"{mt:.0f}", g.get("memory_percent"), g.get("temperature"),
                        g.get("power_draw"), g.get("sm_clock_mhz"), g.get("mem_clock_mhz"),
                        "|".join(g.get("throttle_reasons") or []), g.get("ecc_uncorrected"),
                        len(g.get("processes") or [])])
        text = buf.getvalue()
    if out:
        with open(out, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        print(f"已导出 / exported: {out}")
    else:
        print(text)
# --- Textual TUI（工厂函数：仅交互模式导入 textual，headless 无此依赖） / Textual TUI (factory: import textual only for interactive mode; headless has no such dep) ---
def run_tui(cfg, cfg_path):
    from collections import defaultdict

    from rich.console import Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from textual import work
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, VerticalScroll
    from textual.widgets import (Button, DataTable, Footer, Header, Input, Label,
                                 Select, Static, Switch, TabbedContent, TabPane)

    THEMES = {"dark": "textual-dark", "light": "textual-light"}
    # 每 agent 分色调色板；色盲模式用 IBM 安全色板 / Per-agent palette; colorblind mode uses IBM-safe palette
    PALETTE = ["cyan", "green", "magenta", "yellow", "bright_blue", "red", "bright_green", "orange1"]
    PALETTE_CB = ["#648FFF", "#785EF0", "#DC267F", "#FE6100", "#FFB000", "#009E73"]
    COLOR_OPTS = ["auto", "cyan", "green", "magenta", "yellow", "blue", "red", "white", "orange1"]


    class MonitorApp(App):
        CSS = """
        Screen { layers: base; }
        DataTable { height: 1fr; }
        #sys_body, #settings_body { padding: 1 2; }
        .section-title { text-style: bold; color: $accent; margin: 1 0 0 0; }
        .hint { color: $text-muted; }
        .breach { color: red; text-style: bold; }
        Input.small { width: 40; }
        #agent_add_row { height: auto; }
        #agent_add_row Input { width: 1fr; margin-right: 1; }
        #agent_add_row .add-agent { width: 14; min-width: 14; }
        .settings-row { height: auto; margin: 0 0 1 0; }
        .settings-row Label { width: 22; }
        .settings-row Input { width: 16; }
        #agents_list { height: auto; max-height: 16; }
        .agent-row { height: 3; margin: 0 0 1 0; align: left middle; }
        .agent-row Label { width: 1fr; content-align: left middle; }
        .agent-row .agent-color { width: 14; margin-left: 1; }
        .agent-row .del-agent { width: 14; min-width: 14; margin-left: 1; }
        Button.del-agent, Button.add-agent { color: $text; text-style: bold; }
        """

        BINDINGS = [
            ("m", "show_tab('tab-overview')", "总览/Overview"),
            ("g", "show_tab('tab-gpu')", "GPU"),
            ("e", "show_tab('tab-free')", "空闲/Free"),
            ("p", "show_tab('tab-proc')", "进程/Proc"),
            ("s", "show_tab('tab-sys')", "系统/System"),
            ("d", "show_tab('tab-storage')", "存储/Storage"),
            ("t", "show_tab('tab-settings')", "设置/Settings"),
            ("o", "cycle_sort", "排序/Sort"),
            ("f", "focus_filter", "过滤/Filter"),
            ("slash", "focus_search", "搜索/Search"),
            ("r", "refresh_now", "刷新/Refresh"),
            ("ctrl+t", "toggle_theme", "主题/Theme"),
            ("q", "quit", "退出/Quit"),
        ]

        SORT_KEYS = ["index", "util", "mem", "temp"]
        def __init__(self):
            super().__init__()
            self.cfg = cfg
            self.cfg_path = cfg_path
            self.store = {}
            self.hist = defaultdict(lambda: deque(maxlen=40))  # (agent,idx,metric) -> series
            self.sort_key = cfg["display"].get("sort_key", "index")
            self.filter_user = cfg["display"].get("filter_user", "")
            self.search_q = ""
            self._stop = threading.Event()
            self._poke = threading.Event()

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with TabbedContent(initial="tab-overview", id="tabs"):
                with TabPane("总览/Overview", id="tab-overview"):
                    yield DataTable(id="tbl_overview", zebra_stripes=True)
                with TabPane("GPU", id="tab-gpu"):
                    yield DataTable(id="tbl_gpu", zebra_stripes=True)
                with TabPane("空闲/Free", id="tab-free"):
                    yield DataTable(id="tbl_free", zebra_stripes=True)
                with TabPane("进程/Proc", id="tab-proc"):
                    with Horizontal(classes="settings-row"):
                        yield Label("过滤用户/Filter user:")
                        yield Input(value=self.filter_user, id="proc_filter", classes="small")
                        yield Label(" 搜索/Search PID|user:")
                        yield Input(value="", id="proc_search", classes="small")
                    yield DataTable(id="tbl_proc", zebra_stripes=True)
                with TabPane("系统/System", id="tab-sys"):
                    yield VerticalScroll(Static(id="sys_body"))
                with TabPane("存储/Storage", id="tab-storage"):
                    yield DataTable(id="tbl_storage", zebra_stripes=True)
                with TabPane("设置/Settings", id="tab-settings"):
                    yield VerticalScroll(id="settings_body")
            yield Footer()

        def on_mount(self):
            self.theme = THEMES.get(self.cfg["appearance"].get("theme", "dark"), "textual-dark")
            self._setup_tables()
            self._build_settings()
            self.poll_worker()
            if not self.cfg["agents"]:
                self.query_one("#tabs", TabbedContent).active = "tab-settings"
        # --- 表头 / Table columns ---
        def _setup_tables(self):
            self.query_one("#tbl_overview", DataTable).add_columns(
                "Agent", "主机/Host", "状态/Status", "延迟/ms", "更新/Updated", "GPUs", "GPU↑", "CPU%", "Mem%")
            self.query_one("#tbl_gpu", DataTable).add_columns(
                "Agent", "#", "名称/Name", "Util%", "趋势/Trend", "显存/Mem", "Mem%",
                "温度/Temp", "功耗/W", "风扇/Fan", "SM/MEM MHz", "降频/Throttle", "ECC")
            self.query_one("#tbl_free", DataTable).add_columns(
                "Agent", "#", "名称/Name", "空闲/Free", "Util%", "状态/Status")
            self.query_one("#tbl_proc", DataTable).add_columns(
                "Agent", "GPU", "PID", "用户/User", "进程/Name", "显存MB", "GPU%", "目录·命令/CWD·Cmd")
            self.query_one("#tbl_storage", DataTable).add_columns(
                "Agent", "设备/Device", "挂载/Mount", "FS", "已用/Used", "总/Total", "Used%", "读MB/s", "写MB/s")

        # --- 后台轮询 / Background polling ---
        @work(thread=True, exclusive=True, group="poll")
        def poll_worker(self):
            while not self._stop.is_set():
                store = fetch_all(self.cfg["agents"], timeout=self.cfg.get("timeout", 2.0),
                                  retries=self.cfg.get("retries", 1), token=self.cfg.get("token", ""))
                self.call_from_thread(self.apply_store, store)
                self._poke.wait(timeout=max(1, int(self.cfg.get("refresh_rate", 10))))
                self._poke.clear()

        def action_refresh_now(self):
            self._poke.set()

        def apply_store(self, store):
            self.store = store
            for name, g in iter_gpus(store):
                idx = g.get("index")
                self.hist[(name, idx, "util")].append(g.get("utilization"))
                self.hist[(name, idx, "temp")].append(g.get("temperature"))
            self._bell_if_breach()
            self._refresh_all()

        def _refresh_all(self):
            self._fill_overview()
            self._fill_gpu()
            self._fill_free()
            self._fill_proc()
            self._fill_sys()
            self._fill_storage()
        # --- 阈值高亮辅助 / Threshold-highlight helper ---
        def _cell(self, text, breach=False):
            return Text(str(text), style="red bold") if breach else str(text)

        def _th(self, key):
            return self.cfg["thresholds"].get(key, 999)

        # --- 每 agent 分色 / Per-agent color ---
        def _agent_color(self, name):
            override = (self.cfg["appearance"].get("agent_colors") or {}).get(name)
            if override and override != "auto":
                return override
            palette = PALETTE_CB if self.cfg["appearance"].get("colorblind") else PALETTE
            names = list(self.cfg["agents"].keys())
            idx = names.index(name) if name in names else 0
            return palette[idx % len(palette)]

        def _agent_cell(self, name):
            return Text(name, style=f"{self._agent_color(name)} bold")

        @staticmethod
        def _opt(val, suffix="", fmt=None):
            """缺失/None 显示「—」，避免误导性的 0。 / Show em-dash for missing/None instead of a misleading 0."""
            if val is None:
                return "—"
            return (fmt(val) if fmt else str(val)) + suffix

        def _fill_overview(self):
            t = self.query_one("#tbl_overview", DataTable)
            t.clear()
            for name in self.cfg["agents"]:
                res = self.store.get(name, {})
                if res.get("status") == "online":
                    d = res["data"]
                    sysm, cpu, mem = d.get("system") or {}, d.get("cpu") or {}, d.get("memory") or {}
                    gpus = d.get("gpus") or []
                    gutil = max([g.get("utilization") or 0 for g in gpus], default=0)
                    updated = res["updated"].strftime("%H:%M:%S")
                    cpu_p, mem_p = cpu.get("percent") or 0, mem.get("percent") or 0
                    t.add_row(self._agent_cell(name), sysm.get("hostname", "?"),
                              Text("● 在线/online", style="green"),
                              str(res.get("latency_ms")), updated, str(len(gpus)),
                              f"{gutil:.0f}%",
                              self._cell(f"{cpu_p:.0f}%", cpu_p >= self._th("cpu_percent")),
                              self._cell(f"{mem_p:.0f}%", mem_p >= self._th("mem_percent")))
                else:
                    t.add_row(self._agent_cell(name), "-", Text("○ 离线/offline", style="red"),
                              "-", "-", "-", "-", "-", "-")

        def _fill_gpu(self):
            t = self.query_one("#tbl_gpu", DataTable)
            t.clear()
            rows = sorted(iter_gpus(self.store), key=self._gpu_sort_key)
            for name, g in rows:
                idx = g.get("index")
                mu, mt = g.get("memory_used") or 0, g.get("memory_total") or 0
                mem_p = g.get("memory_percent") or 0
                temp = g.get("temperature")
                throttle = ",".join(g.get("throttle_reasons") or []) or "-"
                ecc = g.get("ecc_uncorrected")
                trend = spark(list(self.hist[(name, idx, "util")]), width=12)
                sm, mc = g.get("sm_clock_mhz"), g.get("mem_clock_mhz")
                clocks = f"{sm}/{mc}" if sm is not None or mc is not None else "—"
                fan = g.get("fan_speed")
                t.add_row(
                    self._agent_cell(name), str(idx), g.get("name", "?"),
                    f"{g.get('utilization') or 0:.0f}%", trend,
                    f"{mu:.0f}/{mt:.0f}M",
                    self._cell(f"{mem_p:.0f}%", mem_p >= self._th("gpu_mem_percent")),
                    self._cell(f"{temp}C" if temp is not None else "N/A",
                               temp is not None and temp >= self._th("gpu_temp")),
                    f"{g.get('power_draw') or 0:.0f}", f"{fan}" if fan is not None else "—",
                    clocks,
                    self._cell(throttle, throttle != "-"),
                    self._cell(ecc, bool(ecc)) if ecc is not None else "—")
        def _gpu_sort_key(self, item):
            name, g = item
            k = self.sort_key
            if k == "util":
                return (-(g.get("utilization") or 0), name, g.get("index") or 0)
            if k == "mem":
                return (-(g.get("memory_percent") or 0), name, g.get("index") or 0)
            if k == "temp":
                return (-(g.get("temperature") or 0), name, g.get("index") or 0)
            return (name, g.get("index") or 0)

        def _fill_free(self):
            t = self.query_one("#tbl_free", DataTable)
            t.clear()
            rows = sorted(iter_gpus(self.store), key=lambda it: -gpu_free_mb(it[1]))
            for name, g in rows:
                free = gpu_free_mb(g)
                util = g.get("utilization") or 0
                available = util < 10 and free > 1024  # 空闲判据：低利用率 + 充足显存 / idle: low util + ample free mem
                status = Text("✓ 可用/available", style="green bold") if available else Text("忙/busy", style="yellow")
                t.add_row(self._agent_cell(name), str(g.get("index")), g.get("name", "?"),
                          f"{free/1024:.1f}G" if free >= 1024 else f"{free:.0f}M",
                          f"{util:.0f}%", status)

        def _fill_proc(self):
            t = self.query_one("#tbl_proc", DataTable)
            t.clear()
            show_cmd = self.cfg["display"].get("show_process_detail", True)
            q = (self.search_q or "").strip().lower()
            fu = (self.filter_user or "").strip().lower()
            for name, gidx, p in iter_processes(self.store):
                user = (p.get("username") or "").lower()
                cwd = p.get("cwd") or ""
                if fu and fu not in user:
                    continue
                if q and q not in str(p.get("pid")) and q not in user and q not in cwd.lower():
                    continue
                gutil = p.get("gpu_util")
                memmb = p.get("gpu_memory_usage_mb") or 0
                idle = (gutil is not None and gutil < 5 and memmb > 500)  # 占卡空转 / holds mem but idle
                # 进程名：新 agent 有 name；老 agent 无，退回 cwd 末段 / name from new agent; fall back to cwd basename for old agent
                pname = p.get("name") or (os.path.basename(cwd) if cwd else "") or "—"
                # 详情：cwd 全写出来供肉眼判断 + 命令行（若有） / detail: full cwd for eyeballing + cmdline if present
                detail = cwd or "—"
                if show_cmd and p.get("cmdline") and p.get("cmdline") != pname:
                    detail = f"{cwd}  ({p.get('cmdline')})" if cwd else p.get("cmdline")
                t.add_row(self._agent_cell(name), str(gidx), str(p.get("pid")),
                          self._cell(p.get("username") or "—", idle),
                          pname, f"{memmb:.0f}",
                          self._cell(f"{gutil}%" if gutil is not None else "N/A", idle),
                          detail[:100])
        def _fill_sys(self):
            body = self.query_one("#sys_body", Static)
            panels = []
            for name in self.cfg["agents"]:
                res = self.store.get(name, {})
                color = self._agent_color(name)
                if res.get("status") != "online":
                    panels.append(Panel(
                        Text(f"○ 离线/offline   ({res.get('error', '?')})", style="red"),
                        title=f"[b {color}]{name}[/]", title_align="left",
                        border_style="red", padding=(0, 1)))
                    continue
                d = res["data"]
                cpu, mem = d.get("cpu") or {}, d.get("memory") or {}
                dio, net, sysm = d.get("disk_io"), d.get("network") or {}, d.get("system") or {}

                def fv(v, unit="", nd=None):
                    if v is None:
                        return "—"
                    if nd is not None and isinstance(v, (int, float)):
                        return f"{v:.{nd}f}{unit}"
                    return f"{v}{unit}"

                # 两列网格：左＝分组标签（加粗·分色），右＝对齐的数值 / 2-col grid: bold label + aligned value
                g = Table.grid(padding=(0, 2))
                g.add_column(justify="right", style=f"bold {color}", width=9, no_wrap=True)
                g.add_column(ratio=1)

                cores = cpu.get("per_core") or []
                sp = f"   [dim]{spark(cores, width=min(32, len(cores)))}[/dim]" if cores else ""
                la = cpu.get("load_avg")
                g.add_row("CPU", Text.from_markup(f"[b]{fv(cpu.get('percent'), '%', 0)}[/b]{sp}"))
                g.add_row("", Text.from_markup(
                    f"[dim]负载/load[/dim] {('/'.join(map(str, la)) if la else '—')}    "
                    f"[dim]频率/freq[/dim] {fv(cpu.get('freq_mhz'), 'MHz', 0)}    "
                    f"[dim]核/cores[/dim] {fv(cpu.get('physical_cores'))}/{fv(cpu.get('logical_cores'))}"))

                g.add_row("内存/Mem", Text.from_markup(
                    f"[b]{fv(mem.get('used_gb'), 'G', 1)}/{fv(mem.get('total_gb'), 'G', 1)}[/b] "
                    f"({fv(mem.get('percent'), '%', 0)})    "
                    f"[dim]可用/avail[/dim] {fv(mem.get('available_gb'), 'G', 1)}    "
                    f"[dim]swap[/dim] {fv(mem.get('swap_used_gb'), 'G', 1)}/{fv(mem.get('swap_total_gb'), 'G', 1)}"))

                if dio:
                    g.add_row("磁盘IO", Text.from_markup(
                        f"[dim]读/read[/dim] {fv(dio.get('read_mbps'), '', 1)}    "
                        f"[dim]写/write[/dim] {fv(dio.get('write_mbps'), '', 1)} MB/s"))
                else:
                    g.add_row("磁盘IO", Text("— (旧 agent 未上报 / not reported)", style="dim"))

                g.add_row("网络/Net", Text.from_markup(
                    f"↑{fv(net.get('send_mbps'), '', 2)} ↓{fv(net.get('recv_mbps'), '', 2)} Mb/s    "
                    f"[dim]err[/dim] {fv(net.get('errin'))}/{fv(net.get('errout'))}    "
                    f"[dim]drop[/dim] {fv(net.get('dropin'))}/{fv(net.get('dropout'))}    "
                    f"[dim]连接/conn[/dim] {fv(net.get('connections'))}"))
                nics = net.get("per_nic") or {}
                if nics:
                    g.add_row("", Text.from_markup(f"[dim]网卡/NICs[/dim] " + ", ".join(sorted(nics.keys()))))

                sensors = sysm.get("sensors_temp")
                if sensors:
                    g.add_row("传感器", Text(" · ".join(f"{k} {v}℃" for k, v in sensors.items())))
                users = sysm.get("users")
                if users:
                    g.add_row("登录用户", Text(", ".join(users)))

                title = (f"[b {color}]● {name}[/]  [green]在线/online[/green]  "
                         f"[dim]{sysm.get('hostname', '?')} · up {sysm.get('uptime_str', '?')}[/dim]")
                panels.append(Panel(g, title=title, title_align="left",
                                    border_style=color, padding=(0, 1)))
            body.update(Group(*panels) if panels else Text("（无 Agent / no agents）", style="dim"))

        def _fill_storage(self):
            t = self.query_one("#tbl_storage", DataTable)
            t.clear()
            for name in self.cfg["agents"]:
                res = self.store.get(name, {})
                if res.get("status") != "online":
                    continue
                d = res["data"]
                dio = d.get("disk_io")
                r = f"{dio.get('read_mbps',0):.1f}" if dio else "—"
                w = f"{dio.get('write_mbps',0):.1f}" if dio else "—"
                for disk in (d.get("disks") or []):
                    if "error" in disk:
                        continue
                    pct = disk.get("percent") or 0
                    t.add_row(self._agent_cell(name), disk.get("device", "?"), disk.get("mountpoint", "?"),
                              disk.get("fstype", "?"), f"{disk.get('used_gb',0):.0f}G",
                              f"{disk.get('total_gb',0):.0f}G",
                              self._cell(f"{pct:.0f}%", pct >= self._th("disk_percent")), r, w)
        # --- 交互动作 / Interactive actions ---
        def action_show_tab(self, tab):
            self.query_one("#tabs", TabbedContent).active = tab

        def action_cycle_sort(self):
            i = (self.SORT_KEYS.index(self.sort_key) + 1) % len(self.SORT_KEYS)
            self.sort_key = self.SORT_KEYS[i]
            self.cfg["display"]["sort_key"] = self.sort_key
            self._save()
            self.notify(f"排序/Sort: {self.sort_key}")
            self._fill_gpu()

        def action_focus_filter(self):
            self.query_one("#tabs", TabbedContent).active = "tab-proc"
            self.query_one("#proc_filter", Input).focus()

        def action_focus_search(self):
            self.query_one("#tabs", TabbedContent).active = "tab-proc"
            self.query_one("#proc_search", Input).focus()

        def action_toggle_theme(self):
            cur = self.cfg["appearance"].get("theme", "dark")
            new = "light" if cur == "dark" else "dark"
            self.cfg["appearance"]["theme"] = new
            self.theme = THEMES[new]
            self._save()
            self.notify(f"主题/Theme: {new}")

        def on_input_changed(self, event):
            if event.input.id == "proc_filter":
                self.filter_user = event.value
                self.cfg["display"]["filter_user"] = event.value
                self._fill_proc()
            elif event.input.id == "proc_search":
                self.search_q = event.value
                self._fill_proc()

        def _bell_if_breach(self):
            if not self.cfg["thresholds"].get("bell"):
                return
            for _, g in iter_gpus(self.store):
                temp = g.get("temperature")
                if (temp is not None and temp >= self._th("gpu_temp")) or \
                   (g.get("memory_percent") or 0) >= self._th("gpu_mem_percent"):
                    self.bell()
                    return

        def _save(self):
            try:
                save_config(self.cfg, self.cfg_path)
            except OSError as e:
                self.notify(f"保存失败/save failed: {e}", severity="error")

        def on_unmount(self):
            self._stop.set()
            self._poke.set()
        # --- 设置页 / Settings page ---
        def _row(self, label, widget):
            return Horizontal(Label(label), widget, classes="settings-row")

        def _build_settings(self):
            body = self.query_one("#settings_body", VerticalScroll)
            ap, th, dp = self.cfg["appearance"], self.cfg["thresholds"], self.cfg["display"]
            widgets = [
                Static("监控源 / Agents", classes="section-title"),
                VerticalScroll(id="agents_list"),
                Horizontal(
                    Input(placeholder="名称/name", id="ag_name"),
                    Input(placeholder="主机/host", id="ag_host"),
                    Input(placeholder="端口/port 48210", id="ag_port"),
                    Button("＋ 添加", id="agent_add", classes="add-agent", variant="primary"),
                    id="agent_add_row", classes="settings-row"),
                Static("轮询 / Polling", classes="section-title"),
                self._row("刷新间隔/refresh (s)", Input(value=str(self.cfg.get("refresh_rate", 10)), id="set_refresh")),
                self._row("超时/timeout (s)", Input(value=str(self.cfg.get("timeout", 2.0)), id="set_timeout")),
                self._row("重试/retries", Input(value=str(self.cfg.get("retries", 1)), id="set_retries")),
                self._row("Token", Input(value=str(self.cfg.get("token", "")), id="set_token", password=True)),
                Static("外观 / Appearance", classes="section-title"),
                self._row("主题/theme", Select([("dark", "dark"), ("light", "light")],
                                              value=ap.get("theme", "dark"), id="set_theme", allow_blank=False)),
                self._row("强调色/accent", Input(value=str(ap.get("accent", "cyan")), id="set_accent")),
                self._row("色盲友好/colorblind", Switch(value=bool(ap.get("colorblind", False)), id="set_colorblind")),
                self._row("密度/density", Select([("comfortable", "comfortable"), ("compact", "compact")],
                                               value=ap.get("density", "comfortable"), id="set_density", allow_blank=False)),
                Static("展示 / Display", classes="section-title"),
                self._row("默认排序/sort", Select([(k, k) for k in self.SORT_KEYS],
                                               value=dp.get("sort_key", "index"), id="set_sort", allow_blank=False)),
                self._row("进程详情/proc detail", Switch(value=bool(dp.get("show_process_detail", True)), id="set_procdetail")),
                self._row("默认过滤用户/filter user", Input(value=str(dp.get("filter_user", "")), id="set_filteruser")),
                Static("告警阈值 / Alert thresholds", classes="section-title"),
                self._row("GPU 温度/temp ℃", Input(value=str(th.get("gpu_temp", 80)), id="set_gputemp")),
                self._row("GPU 显存/mem %", Input(value=str(th.get("gpu_mem_percent", 90)), id="set_gpumem")),
                self._row("CPU %", Input(value=str(th.get("cpu_percent", 90)), id="set_cpu")),
                self._row("内存/mem %", Input(value=str(th.get("mem_percent", 90)), id="set_mem")),
                self._row("磁盘/disk %", Input(value=str(th.get("disk_percent", 90)), id="set_disk")),
                self._row("超限响铃/bell", Switch(value=bool(th.get("bell", False)), id="set_bell")),
                Button("保存设置 / Save", id="settings_save", variant="success"),
                Static("", id="settings_msg", classes="hint"),
                Static("关于 / About", classes="section-title"),
                Static(f"版本/Version {APP_VERSION}\n配置/Config: {self.cfg_path}", classes="hint"),
            ]
            body.mount(*widgets)
            self._render_agents_list()

        def _render_agents_list(self):
            box = self.query_one("#agents_list", VerticalScroll)
            box.remove_children()
            if not self.cfg["agents"]:
                box.mount(Static("（暂无 Agent，请在下方添加 / no agents yet, add below）", classes="hint"))
            for name, entry in self.cfg["agents"].items():
                cur = (self.cfg["appearance"].get("agent_colors") or {}).get(name, "auto")
                color = self._agent_color(name)
                box.mount(Horizontal(
                    Label(Text(f"● {name}", style=f"{color} bold") + Text(f"  →  {agent_url(entry)}")),
                    Select([(c, c) for c in COLOR_OPTS], value=cur if cur in COLOR_OPTS else "auto",
                           name=name, classes="agent-color", allow_blank=False),
                    Button("✕ 删除", name=name, classes="del-agent", variant="error"),
                    classes="agent-row"))

        def on_select_changed(self, event):
            sel = event.select
            if not sel.has_class("agent-color"):
                return  # 其它 Select（主题/密度等）在保存时统一读取 / other selects are read on Save
            colors = self.cfg["appearance"].setdefault("agent_colors", {})
            new = None if event.value == "auto" else event.value
            if new == colors.get(sel.name):
                return  # 无变化（含初始挂载事件） / no change (incl. initial mount event)
            if new is None:
                colors.pop(sel.name, None)
            else:
                colors[sel.name] = new
            self._save()
            self._refresh_all()

        def on_button_pressed(self, event):
            bid = event.button.id
            if event.button.has_class("del-agent"):
                self.cfg["agents"].pop(event.button.name, None)
                self._save()
                self._render_agents_list()
                self._poke.set()
            elif bid == "agent_add":
                name = self.query_one("#ag_name", Input).value.strip()
                host = self.query_one("#ag_host", Input).value.strip()
                port = self.query_one("#ag_port", Input).value.strip() or "48210"
                if not name or not host:
                    self.notify("需填名称与主机 / name & host required", severity="warning")
                    return
                try:
                    port_i = int(port)
                except ValueError:
                    self.notify("端口无效 / invalid port", severity="warning")
                    return
                self.cfg["agents"][name] = {"host": host, "port": port_i}
                self._save()
                for wid in ("#ag_name", "#ag_host", "#ag_port"):
                    self.query_one(wid, Input).value = ""
                self._render_agents_list()
                self._poke.set()
                self.notify(f"已添加/added {name}")
            elif bid == "settings_save":
                self._save_settings()

        def _num(self, wid, cast, default):
            try:
                return cast(self.query_one(wid, Input).value.strip())
            except (ValueError, TypeError):
                return default

        def _save_settings(self):
            c = self.cfg
            c["refresh_rate"] = max(1, self._num("#set_refresh", int, c["refresh_rate"]))
            c["timeout"] = max(0.5, self._num("#set_timeout", float, c["timeout"]))
            c["retries"] = max(0, self._num("#set_retries", int, c["retries"]))
            c["token"] = self.query_one("#set_token", Input).value.strip()
            ap = c["appearance"]
            ap["theme"] = self.query_one("#set_theme", Select).value
            ap["accent"] = self.query_one("#set_accent", Input).value.strip() or "cyan"
            ap["colorblind"] = self.query_one("#set_colorblind", Switch).value
            ap["density"] = self.query_one("#set_density", Select).value
            dp = c["display"]
            dp["sort_key"] = self.query_one("#set_sort", Select).value
            dp["show_process_detail"] = self.query_one("#set_procdetail", Switch).value
            dp["filter_user"] = self.query_one("#set_filteruser", Input).value.strip()
            th = c["thresholds"]
            th["gpu_temp"] = self._num("#set_gputemp", int, th["gpu_temp"])
            th["gpu_mem_percent"] = self._num("#set_gpumem", int, th["gpu_mem_percent"])
            th["cpu_percent"] = self._num("#set_cpu", int, th["cpu_percent"])
            th["mem_percent"] = self._num("#set_mem", int, th["mem_percent"])
            th["disk_percent"] = self._num("#set_disk", int, th["disk_percent"])
            th["bell"] = self.query_one("#set_bell", Switch).value
            self.sort_key = dp["sort_key"]
            self.filter_user = dp["filter_user"]
            self.query_one("#proc_filter", Input).value = dp["filter_user"]
            self.theme = THEMES.get(ap["theme"], "textual-dark")
            self._save()
            self._poke.set()
            self.query_one("#settings_msg", Static).update("已保存 ✓ / saved")
            self._render_agents_list()
            self._refresh_all()
    MonitorApp().run()


# --- 入口 / Entry point ---
def main():
    parser = argparse.ArgumentParser(
        prog="gpu-monitor-cli",
        description="实验室 GPU 监控终端客户端 / Lab GPU Monitor terminal client")
    parser.add_argument("--version", action="store_true", help="打印版本并退出 / print version and exit")
    parser.add_argument("--once", action="store_true", help="抓取一次并打印摘要后退出 / fetch once, print summary, exit")
    parser.add_argument("--export", choices=["json", "csv"], help="导出一次快照 / export one snapshot")
    parser.add_argument("--out", help="导出目标文件（默认打印到 stdout） / output file (default: stdout)")
    parser.add_argument("--agents", help='临时覆盖 Agent 列表 "name=host:port,..." / temporary agent override')
    args = parser.parse_args()

    if args.version:
        print(f"gpu-monitor-cli {APP_VERSION}")
        return

    cfg, path = load_config()
    if args.agents:
        cfg["agents"] = parse_agents_override(args.agents)

    if args.once or args.export:
        store = fetch_all(cfg["agents"], timeout=cfg.get("timeout", 2.0),
                          retries=cfg.get("retries", 1), token=cfg.get("token", ""))
        if args.export:
            export_snapshot(store, args.export, args.out)
        else:
            run_once(store)
        return

    run_tui(cfg, path)


if __name__ == "__main__":
    main()





