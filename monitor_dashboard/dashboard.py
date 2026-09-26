# 文件名 / File: dashboard.py
# 中央仪表盘：后台并发轮询所有 Agent，提供 Web UI + JSON API，支持配置页与单一共享密码鉴权。
# Central dashboard: concurrently polls all Agents in the background, serves a web UI + JSON API,
# with a settings page and single-shared-password authentication.
#
# 配置存放在同目录 config.json（可用 DASHBOARD_CONFIG 环境变量覆盖路径）。 / Config lives in config.json next to this file (path overridable via DASHBOARD_CONFIG).

import os
import json
import time
import secrets
import threading
from functools import wraps
from concurrent.futures import ThreadPoolExecutor

import requests
from flask import (Flask, jsonify, render_template, request, redirect,
                   url_for, session, flash)
from werkzeug.security import generate_password_hash, check_password_hash

# --- 路径与配置 / Paths and configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.environ.get("DASHBOARD_CONFIG", os.path.join(BASE_DIR, "config.json"))

# 默认配置：agents 默认为空，避免任何"必须先改源码"的步骤，新手可在设置页添加。
# Default config: agents empty by default so there's no "edit the source first" step; add them in the settings page.
DEFAULT_CONFIG = {
    "title": "Lab GPU Monitor",
    "port": 48080,
    "poll_interval": 2,
    "theme": "dark",            # 站点默认深色 / Site default: dark
    "agents": {},               # name -> {"host": "...", "port": 48210} 或 {"url": "..."}
    "auth_enabled": False,
    "password_hash": "",
    "secret_key": "",
    "alerts": {"gpu_temp": 85, "gpu_mem_percent": 95, "disk_percent": 90},
    "display": {"show_processes": True, "show_offline": True, "compact": False},
}

config_lock = threading.Lock()
CONFIG = {}


def _merge_defaults(cfg):
    """用默认值补齐缺失字段（浅合并 + 一层嵌套） / Fill missing fields from defaults (shallow + one nested level)."""
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg or {})
    for k in ("alerts", "display"):
        d = dict(DEFAULT_CONFIG[k])
        d.update(merged.get(k) or {})
        merged[k] = d
    return merged


def save_config(cfg):
    """线程安全地把配置写回磁盘。 / Persist config to disk in a thread-safe way."""
    with config_lock:
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_PATH)  # 原子替换，避免写一半损坏 / Atomic replace, avoid half-written corruption


def load_config():
    """加载配置；首次运行自动生成默认 config.json，并补齐 secret_key。 / Load config; auto-create default config.json on first run and ensure secret_key."""
    global CONFIG
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[Warn] 读取配置失败，使用默认值 / failed to read config, using defaults: {e}")
    cfg = _merge_defaults(cfg)
    # 首次运行自动生成签名密钥并持久化 / Auto-generate and persist a signing key on first run
    if not cfg.get("secret_key"):
        cfg["secret_key"] = secrets.token_hex(32)
    CONFIG = cfg
    try:
        save_config(cfg)  # 回写（首次会落地默认文件） / Write back (materializes the default file on first run)
    except OSError as e:
        print(f"[Warn] 无法写入配置文件 {CONFIG_PATH} / cannot write config file: {e}")
    return cfg


def agent_url(entry):
    """由配置条目得到 /metrics URL，兼容 {'url':...} 与 {'host':..,'port':..}。 / Build the /metrics URL from a config entry, supporting both {'url':...} and {'host':..,'port':..}."""
    if entry.get("url"):
        return entry["url"]
    host = entry.get("host", "")
    port = entry.get("port", 48210)
    return f"http://{host}:{port}/metrics"


# --- 后台数据抓取 / Background data fetching ---
global_data_store = {}
data_lock = threading.Lock()


def fetch_single_agent(server_name, url, timeout):
    """抓取单个 Agent 数据，成功/失败都返回标准化结果。 / Fetch one Agent; return a normalized result on success or failure."""
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return server_name, {"status": "online", "data": response.json()}
    except requests.exceptions.RequestException as e:
        return server_name, {"status": "offline", "error": str(e), "data": {}}


def update_data_loop():
    """后台线程：每轮读取当前配置的 Agent 列表并发抓取（设置页改动即时生效）。 / Background thread: each round reads the current agent list and fetches concurrently (settings edits take effect immediately)."""
    global global_data_store
    while True:
        start_time = time.time()
        with config_lock:
            agents = dict(CONFIG.get("agents", {}))
            poll_interval = float(CONFIG.get("poll_interval", 2))
        timeout = max(1.0, poll_interval - 0.5)

        temp = {}
        if agents:
            # max_workers 至少为 1，避免空列表时 ThreadPoolExecutor 抛 ValueError。 / max_workers >= 1 to avoid ValueError from an empty agent list.
            with ThreadPoolExecutor(max_workers=max(1, len(agents))) as executor:
                futures = [executor.submit(fetch_single_agent, name, agent_url(cfg), timeout)
                           for name, cfg in agents.items()]
                for fut in futures:
                    try:
                        name, result = fut.result()
                        temp[name] = result
                    except Exception as e:
                        print(f"[Error] 抓取线程异常 / fetch thread error: {e}")

        with data_lock:
            global_data_store = temp

        elapsed = time.time() - start_time
        if elapsed < poll_interval:
            time.sleep(poll_interval - elapsed)


# --- Flask 应用 / Flask application ---
app = Flask(__name__)


def auth_required():
    with config_lock:
        return bool(CONFIG.get("auth_enabled")) and bool(CONFIG.get("password_hash"))


def login_required(view):
    """鉴权开启且未登录时，页面重定向到登录页、API 返回 401。 / When auth is on and not logged in, redirect pages to login and return 401 for APIs."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if auth_required() and not session.get("logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    if not auth_required():
        return redirect(url_for("get_index_page"))
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        with config_lock:
            ok = check_password_hash(CONFIG.get("password_hash", ""), password)
        if ok:
            session["logged_in"] = True
            session.permanent = True
            nxt = request.args.get("next") or url_for("get_index_page")
            return redirect(nxt)
        error = "密码错误 / Wrong password"
    return render_template("login.html", error=error, title=CONFIG.get("title"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def get_index_page():
    with config_lock:
        title, theme = CONFIG.get("title"), CONFIG.get("theme")
    return render_template("index.html", title=title, theme=theme, auth_on=auth_required())


@app.route("/settings")
@login_required
def get_settings_page():
    with config_lock:
        title, theme = CONFIG.get("title"), CONFIG.get("theme")
    return render_template("settings.html", title=title, theme=theme, auth_on=auth_required())


@app.route("/api/data")
@login_required
def get_api_data():
    with data_lock:
        payload = dict(global_data_store)
    with config_lock:
        return jsonify({
            "servers": payload,
            "config": {"title": CONFIG.get("title"), "theme": CONFIG.get("theme"),
                       "alerts": CONFIG.get("alerts"), "display": CONFIG.get("display"),
                       "poll_interval": CONFIG.get("poll_interval")},
        })


def _public_config():
    """去掉敏感字段的配置副本，供设置页读取。 / Config copy with sensitive fields stripped, for the settings page."""
    with config_lock:
        c = dict(CONFIG)
    c.pop("secret_key", None)
    c.pop("password_hash", None)
    c["has_password"] = bool(CONFIG.get("password_hash"))
    return c


@app.route("/api/config", methods=["GET", "POST"])
@login_required
def api_config():
    if request.method == "GET":
        return jsonify(_public_config())

    body = request.get_json(silent=True) or {}
    with config_lock:
        cfg = dict(CONFIG)
        # 只接受白名单字段，绝不接受 secret_key / password_hash 原文 / Whitelist only; never accept raw secret_key / password_hash
        for key in ("title", "theme", "agents", "alerts", "display", "poll_interval", "port"):
            if key in body:
                cfg[key] = body[key]
        if "auth_enabled" in body:
            cfg["auth_enabled"] = bool(body["auth_enabled"])
        # 修改密码：只接收明文并即时哈希，不回显 / Password change: accept plaintext only, hash immediately, never echo
        new_pw = body.get("new_password")
        if new_pw:
            cfg["password_hash"] = generate_password_hash(new_pw)
        # 开启鉴权但从未设置过密码则拒绝 / Reject enabling auth when no password was ever set
        if cfg.get("auth_enabled") and not cfg.get("password_hash"):
            return jsonify({"error": "启用鉴权前需先设置密码 / set a password before enabling auth"}), 400
        CONFIG.clear()
        CONFIG.update(cfg)
    try:
        save_config(cfg)
    except OSError as e:
        return jsonify({"error": f"保存失败 / save failed: {e}"}), 500
    return jsonify({"ok": True, "note": "端口修改需重启生效 / port change requires a restart"})


@app.route("/api/health")
def api_health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    load_config()
    app.secret_key = CONFIG.get("secret_key") or secrets.token_hex(32)
    port = int(CONFIG.get("port", 48080))

    print("启动后台数据抓取线程... / Starting background data-fetch thread...")
    threading.Thread(target=update_data_loop, daemon=True).start()
    print(f"仪表盘启动，监听 http://0.0.0.0:{port} / Dashboard on http://0.0.0.0:{port}")

    # 生产优先 waitress，未安装回退 Flask 开发服务器（提交时保持 debug=False）。
    # Prefer waitress; fall back to the Flask dev server if absent (keep debug=False when committing).
    try:
        from waitress import serve
        serve(app, host="0.0.0.0", port=port, threads=8)
    except ImportError:
        print("未安装 waitress，回退 Flask 开发服务器 / waitress not installed, using Flask dev server")
        app.run(host="0.0.0.0", port=port, debug=False)
