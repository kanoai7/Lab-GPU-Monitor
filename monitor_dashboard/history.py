# 文件名 / File: history.py
# SQLite 历史存储（当作有界缓存用）：后台 poller 每轮把各主机关键标量写入，
# 定期把超过保留期的原始样本压成 1 分钟均值（降采样），再删除更久远的数据——体积有上限。
# SQLite history store (used as a bounded cache): the poller records key scalars each round;
# a maintenance thread downsamples raw samples older than the retention window into 1-minute
# averages, then prunes anything older than the rollup window — so the DB size stays bounded.

import time
import sqlite3
import threading

_conn = None
_lock = threading.Lock()

# 时间范围（秒）/ time ranges in seconds
RANGES = {"1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800}


def _num(v):
    """只保留数字，其它（None/字符串）返回 None，避免脏数据入库。 / Keep numbers only; None otherwise."""
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def init(db_path):
    """建立连接与表结构（WAL 提升并发写读）。 / Open connection and create schema (WAL for concurrent read/write)."""
    global _conn
    _conn = sqlite3.connect(db_path, check_same_thread=False)
    _conn.execute("PRAGMA journal_mode=WAL;")
    _conn.execute("PRAGMA synchronous=NORMAL;")
    _conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS host_samples (
            host TEXT, ts INTEGER, res INTEGER,
            cpu REAL, mem_pct REAL, mem_used REAL, mem_avail REAL, swap_used REAL,
            net_up REAL, net_down REAL, disk_r REAL, disk_w REAL, load1 REAL
        );
        CREATE INDEX IF NOT EXISTS ix_host ON host_samples(host, ts);
        CREATE TABLE IF NOT EXISTS gpu_samples (
            host TEXT, idx INTEGER, ts INTEGER, res INTEGER,
            util REAL, mem_pct REAL, mem_used REAL, temp REAL, power REAL
        );
        CREATE INDEX IF NOT EXISTS ix_gpu ON gpu_samples(host, idx, ts);
        CREATE TABLE IF NOT EXISTS gpu_meta (host TEXT, idx INTEGER, name TEXT, PRIMARY KEY(host, idx));
        """
    )
    _conn.commit()


def record(servers, ts=None):
    """把一轮快照中在线主机的关键标量写入（res=0 原始）。 / Persist one round of online-host scalars (res=0 raw)."""
    if _conn is None:
        return
    ts = int(ts or time.time())
    hrows, grows, metas = [], [], []
    for host, entry in (servers or {}).items():
        if entry.get("status") != "online":
            continue
        d = entry.get("data") or {}
        cpu, mem = d.get("cpu") or {}, d.get("memory") or {}
        net, dio = d.get("network") or {}, d.get("disk_io") or {}
        load = cpu.get("load_avg")
        load1 = _num(load[0]) if isinstance(load, (list, tuple)) and load else None
        hrows.append((host, ts, 0, _num(cpu.get("percent")), _num(mem.get("percent")),
                      _num(mem.get("used_gb")), _num(mem.get("available_gb")), _num(mem.get("swap_used_gb")),
                      _num(net.get("send_mbps")), _num(net.get("recv_mbps")),
                      _num(dio.get("read_mbps")), _num(dio.get("write_mbps")), load1))
        for g in (d.get("gpus") or []):
            idx = g.get("index")
            if idx is None:
                continue
            grows.append((host, idx, ts, 0, _num(g.get("utilization")), _num(g.get("memory_percent")),
                          _num(g.get("memory_used")), _num(g.get("temperature")), _num(g.get("power_draw"))))
            if g.get("name"):
                metas.append((host, idx, g.get("name")))
    if not hrows and not grows:
        return
    with _lock:
        _conn.executemany("INSERT INTO host_samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", hrows)
        _conn.executemany("INSERT INTO gpu_samples VALUES (?,?,?,?,?,?,?,?,?)", grows)
        if metas:
            _conn.executemany("INSERT OR REPLACE INTO gpu_meta VALUES (?,?,?)", metas)
        _conn.commit()


def _cols(rows, n):
    """把行集拆成 n 列的并列数组（ts + 各指标）。 / Split rows into n parallel column arrays."""
    out = [[] for _ in range(n)]
    for r in rows:
        for i in range(n):
            out[i].append(r[i])
    return out


def query(host, rng="6h"):
    """按时间范围返回该主机的时序列（ECharts 直接用的并列数组）。 / Time-series columns for a host."""
    if _conn is None:
        return {"ts": [], "gpus": []}
    since = int(time.time()) - RANGES.get(rng, RANGES["6h"])
    with _lock:
        hs = _conn.execute(
            "SELECT ts, cpu, mem_pct, mem_used, mem_avail, swap_used, net_up, net_down, disk_r, disk_w, load1 "
            "FROM host_samples WHERE host=? AND ts>=? ORDER BY ts", (host, since)).fetchall()
        idxs = [r[0] for r in _conn.execute(
            "SELECT DISTINCT idx FROM gpu_samples WHERE host=? AND ts>=? ORDER BY idx", (host, since)).fetchall()]
        names = dict(_conn.execute("SELECT idx, name FROM gpu_meta WHERE host=?", (host,)).fetchall())
        gpus = []
        for idx in idxs:
            gr = _conn.execute(
                "SELECT ts, util, mem_pct, mem_used, temp, power FROM gpu_samples "
                "WHERE host=? AND idx=? AND ts>=? ORDER BY ts", (host, idx, since)).fetchall()
            c = _cols(gr, 6)
            gpus.append({"idx": idx, "name": names.get(idx, "GPU %d" % idx),
                         "ts": c[0], "util": c[1], "mem_pct": c[2], "mem_used": c[3], "temp": c[4], "power": c[5]})
    hc = _cols(hs, 11)
    return {"ts": hc[0], "cpu": hc[1], "mem_pct": hc[2], "mem_used": hc[3], "mem_avail": hc[4],
            "swap_used": hc[5], "net_up": hc[6], "net_down": hc[7], "disk_r": hc[8], "disk_w": hc[9],
            "load1": hc[10], "gpus": gpus}


def _downsample_prune(retain_raw_hours, retain_rollup_days):
    """把超过 raw 保留期的原始样本压成 1 分钟均值，再删更久远数据。 / Roll up old raw to 1-min avg, then prune."""
    if _conn is None:
        return
    now = int(time.time())
    raw_cut = now - int(retain_raw_hours * 3600)
    rollup_cut = now - int(retain_rollup_days * 86400)
    bucket_max = (now // 60) - 1  # 只压已完整结束的分钟桶 / only fully-elapsed minute buckets
    with _lock:
        # host：按分钟桶求均值写回 res=60，删对应 res=0 / roll up host raw into 1-min averages
        _conn.execute(
            "INSERT INTO host_samples SELECT host, (ts/60)*60 AS b, 60, "
            "AVG(cpu), AVG(mem_pct), AVG(mem_used), AVG(mem_avail), AVG(swap_used), "
            "AVG(net_up), AVG(net_down), AVG(disk_r), AVG(disk_w), AVG(load1) "
            "FROM host_samples WHERE res=0 AND ts<? AND (ts/60)<=? GROUP BY host, b",
            (raw_cut, bucket_max))
        _conn.execute("DELETE FROM host_samples WHERE res=0 AND ts<? AND (ts/60)<=?", (raw_cut, bucket_max))
        # gpu：同样按 (host, idx, 分钟桶) / same rollup per gpu
        _conn.execute(
            "INSERT INTO gpu_samples SELECT host, idx, (ts/60)*60 AS b, 60, "
            "AVG(util), AVG(mem_pct), AVG(mem_used), AVG(temp), AVG(power) "
            "FROM gpu_samples WHERE res=0 AND ts<? AND (ts/60)<=? GROUP BY host, idx, b",
            (raw_cut, bucket_max))
        _conn.execute("DELETE FROM gpu_samples WHERE res=0 AND ts<? AND (ts/60)<=?", (raw_cut, bucket_max))
        # 删除超过 rollup 保留期的一切 / prune everything older than the rollup window
        _conn.execute("DELETE FROM host_samples WHERE ts<?", (rollup_cut,))
        _conn.execute("DELETE FROM gpu_samples WHERE ts<?", (rollup_cut,))
        _conn.commit()


def start_maintenance(get_cfg, interval=60):
    """起后台线程周期性降采样+裁剪；get_cfg() 返回当前 history 配置。 / Periodic downsample+prune thread."""
    def loop():
        while True:
            time.sleep(interval)
            try:
                cfg = get_cfg() or {}
                _downsample_prune(cfg.get("retain_raw_hours", 6), cfg.get("retain_rollup_days", 7))
            except Exception as e:
                print(f"[Warn] 历史维护线程异常 / history maintenance error: {e}")
    threading.Thread(target=loop, daemon=True).start()
