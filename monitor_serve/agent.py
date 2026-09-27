# 文件名 / File: agent.py
# 依赖 / Dependencies: pip install flask pynvml psutil
# 功能：一个轻量级的全功能监控 Agent。 / A lightweight full-featured monitoring agent.
# 暴露一个 "/metrics" 端点，包含 GPU, CPU, 内存, 磁盘, 和网络信息。 / Exposes a "/metrics" endpoint with GPU, CPU, memory, disk, and network info.

from flask import Flask, jsonify
from pynvml import *
import psutil
import platform
import time
import datetime
import os
from threading import Lock, Thread

# --- 全局变量和锁 / Global variables and lock ---
app = Flask(__name__)
# 端口可用环境变量覆盖，默认 9527（与实验室真机既有部署一致，服务配置无需改动）/ Port overridable via env var, default 9527 (matches the lab machines' existing deployment; no service-config change needed)
AGENT_PORT = int(os.environ.get("AGENT_PORT", "9527"))  # 监控 Agent 监听端口 / Metrics agent listening port
# 后台采样间隔（秒），可用环境变量覆盖 / Background sampling interval (seconds), overridable via env var
SAMPLE_INTERVAL = float(os.environ.get("AGENT_SAMPLE_INTERVAL", "2"))
nvml_initialized = False
nvml_lock = Lock() # pynvml 建议在多线程中使用锁 / pynvml recommends using a lock in multithreading

# 用于计算网络速度 / Used to compute network speed
last_net_stats = None
last_net_time = None
net_lock = Lock()

# 用于计算磁盘读写速率（与网络同理，仅由单一采样线程独占更新） / Used to compute disk read/write rates (like network, updated solely by the single sampler thread)
last_disk_io = None
last_disk_time = None
disk_lock = Lock()

process_info_cache = {}

# --- 后台采样快照 / Background sampling snapshot ---
# 采样线程按固定间隔采集一次，/metrics 只返回最近一次快照。 / A sampler thread collects once per fixed interval; /metrics just returns the latest snapshot.
# 好处：解耦"轮询频率"与"采集频率"，封顶 CPU 开销，并修复多个轮询端同时请求时网速/CPU 计算错乱的问题。 / Benefits: decouples poll frequency from sample frequency, caps CPU cost, and fixes net-speed/CPU corruption when multiple pollers hit the agent at once.
latest_snapshot = {"status": "starting", "message": "Agent is warming up..."}
snapshot_lock = Lock()

# --- 辅助函数：格式化字节 / Helper functions: format bytes ---
def bytes_to_gb(b):
    return round(b / (1024**3), 2)

def bytes_to_mb(b):
    return round(b / (1024**2), 2)

# 降频原因位标志 -> 简短名称。不同 pynvml 版本常量名可能缺失，用 globals() 容错查找。 / Throttle-reason bit flags -> short names. Constant names vary across pynvml versions; look them up via globals() to tolerate absence.
_THROTTLE_FLAGS = [
    ("GpuIdle", "nvmlClocksThrottleReasonGpuIdle"),
    ("AppClocksSetting", "nvmlClocksThrottleReasonApplicationsClocksSetting"),
    ("SwPowerCap", "nvmlClocksThrottleReasonSwPowerCap"),
    ("HwSlowdown", "nvmlClocksThrottleReasonHwSlowdown"),
    ("SyncBoost", "nvmlClocksThrottleReasonSyncBoost"),
    ("SwThermalSlowdown", "nvmlClocksThrottleReasonSwThermalSlowdown"),
    ("HwThermalSlowdown", "nvmlClocksThrottleReasonHwThermalSlowdown"),
    ("HwPowerBrakeSlowdown", "nvmlClocksThrottleReasonHwPowerBrakeSlowdown"),
    ("DisplayClockSetting", "nvmlClocksThrottleReasonDisplayClockSetting"),
]

def _decode_throttle_reasons(bitmask):
    """把降频原因位掩码解码为激活原因的名称列表。 / Decode the throttle-reason bitmask into a list of active reason names."""
    names = []
    g = globals()
    for label, const_name in _THROTTLE_FLAGS:
        flag = g.get(const_name)
        if flag is not None and (bitmask & flag):
            names.append(label)
    return names

# 兼容不同驱动/pynvml 版本的 GPU 进程查询：新驱动用无版本号函数即可，旧驱动（如 470）需 _v2。
# Version-tolerant GPU process query: unversioned works on newer drivers; old drivers (e.g. 470) need _v2.
# 内部容错，任一失败返回空列表，绝不让进程枚举拖垮整轮采样。 / Fully guarded — a failure yields [] and never aborts the sample.
def _running_gpu_processes(handle):
    g = globals()
    procs = []
    for base in ("nvmlDeviceGetComputeRunningProcesses", "nvmlDeviceGetGraphicsRunningProcesses"):
        for suffix in ("", "_v3", "_v2"):   # 先试无版本号（既有真机已验证），失败再回退版本化。 / try unversioned first, then versioned fallbacks
            fn = g.get(base + suffix)
            if fn is None:
                continue
            try:
                procs += list(fn(handle))
                break
            except Exception:
                continue
    return procs

# --- 1. GPU 指标 / GPU metrics ---
def get_gpu_metrics():
    global process_info_cache # 声明使用全局缓存 / Declare use of global cache
    with nvml_lock:
        try:
            global nvml_initialized
            if not nvml_initialized:
                nvmlInit()
                nvml_initialized = True
            
            gpus_data = []
            device_count = nvmlDeviceGetCount()
            current_active_pids = set() # 用于记录当前所有GPU上的活跃PID，以便清理过期缓存 / Track active PIDs across all GPUs to clean up stale cache
            
            for i in range(device_count):
                handle = nvmlDeviceGetHandleByIndex(i)
                name = nvmlDeviceGetName(handle)
                
                # ... [保留此处原有的温度、功耗计算代码] ... / [Keep the existing temperature and power calculation code here]
                try:
                    temp = nvmlDeviceGetTemperature(handle, NVML_TEMPERATURE_GPU)
                except NVMLError:
                    temp = 0
                
                try:
                    power_draw = nvmlDeviceGetPowerUsage(handle) / 1000.0
                    power_limit = nvmlDeviceGetEnforcedPowerLimit(handle) / 1000.0
                    power_percent = (power_draw / power_limit * 100) if power_limit > 0 else 0
                except NVMLError:
                    power_draw, power_limit, power_percent = 0, 0, 0
                
                # 新增：风扇转速百分比（部分数据中心卡/被动散热卡不支持，需容错） / New: fan speed percent (unsupported on some datacenter/passively-cooled cards, guard required)
                try:
                    fan_speed = nvmlDeviceGetFanSpeed(handle)
                except NVMLError:
                    fan_speed = None

                # 新增：核心/显存频率（MHz）。不同代际/驱动可能不支持，容错。 / New: SM/memory clocks (MHz). Not supported on all gens/drivers, guarded.
                try:
                    sm_clock_mhz = nvmlDeviceGetClockInfo(handle, NVML_CLOCK_SM)
                    mem_clock_mhz = nvmlDeviceGetClockInfo(handle, NVML_CLOCK_MEM)
                except Exception:
                    sm_clock_mhz, mem_clock_mhz = None, None

                # 新增：降频原因。函数名/常量随 pynvml 版本变化，广义容错。 / New: throttle reasons. Function/const names vary by pynvml version, broadly guarded.
                try:
                    throttle_bits = nvmlDeviceGetCurrentClocksThrottleReasons(handle)
                    throttle_reasons = _decode_throttle_reasons(throttle_bits)
                except Exception:
                    throttle_reasons = None

                # 新增：易失性 ECC 不可纠正错误计数（消费级卡通常不支持，返回 None）。 / New: volatile uncorrected ECC error count (usually unsupported on consumer cards -> None).
                try:
                    ecc_uncorrected = nvmlDeviceGetTotalEccErrors(
                        handle, NVML_MEMORY_ERROR_TYPE_UNCORRECTED, NVML_VOLATILE_ECC)
                except Exception:
                    ecc_uncorrected = None

                mem_info = nvmlDeviceGetMemoryInfo(handle)
                mem_used = bytes_to_mb(mem_info.used)
                mem_total = bytes_to_mb(mem_info.total)
                mem_percent = (mem_used / mem_total * 100) if mem_total > 0 else 0
                
                util = nvmlDeviceGetUtilizationRates(handle)
                
                # --- 新增/修改：带有缓存机制的进程信息获取 / New/Modified: process info retrieval with caching ---
                processes = []
                nvml_procs = _running_gpu_processes(handle)

                # 新增（可选）：每进程 GPU 利用率。较新驱动才支持，且需缓冲区内有采样，广义容错。 / New (optional): per-process GPU utilization. Newer drivers only, needs samples in buffer, broadly guarded.
                proc_util_map = {}
                try:
                    for s in nvmlDeviceGetProcessUtilization(handle, 0):
                        proc_util_map[s.pid] = {"sm": s.smUtil, "mem": s.memUtil}
                except Exception:
                    proc_util_map = {}
                
                for p in nvml_procs:
                    pid = p.pid
                    mem_usage_mb = bytes_to_mb(p.usedGpuMemory if p.usedGpuMemory else 0)
                    
                    # 新增：如果进程占用显存小于 20MB (通常是 Xorg 等系统进程)，直接忽略 / New: ignore processes using less than 20MB of GPU memory (usually system processes like Xorg)
                    # 真正的深度学习任务通常显存占用都会大于几百MB / Real deep learning tasks usually use hundreds of MB or more
                    if mem_usage_mb < 20:
                        continue
                    current_active_pids.add(pid)

                    # 缓存逻辑：如果 PID 不在缓存中，才执行耗时的 psutil 系统调用 / Cache logic: only run the costly psutil system call if the PID is not cached
                    if pid not in process_info_cache:
                        proc_data = {
                            "cwd": "unknown",
                            "create_time": "unknown",
                            "username": "unknown",
                            "name": "unknown",
                            "cmdline": "",
                        }
                        try:
                            ps_proc = psutil.Process(pid)
                            with ps_proc.oneshot(): # 进一步优化瞬间的读取性能 / Further optimize instantaneous read performance
                                proc_data["cwd"] = ps_proc.cwd()
                                create_time = datetime.datetime.fromtimestamp(ps_proc.create_time())
                                proc_data["create_time"] = create_time.isoformat()
                                # 新增：进程归属人 / 名称 / 命令行（均为 PID 生命周期内不变的信息，可安全缓存） / New: process owner / name / cmdline (all constant over a PID's lifetime, safe to cache)
                                try:
                                    proc_data["username"] = ps_proc.username()
                                except Exception:
                                    pass
                                try:
                                    proc_data["name"] = ps_proc.name()
                                except Exception:
                                    pass
                                try:
                                    cmdline = " ".join(ps_proc.cmdline())
                                    # 截断过长命令行，避免 JSON 膨胀 / Truncate overly long cmdlines to avoid JSON bloat
                                    proc_data["cmdline"] = cmdline[:512]
                                except Exception:
                                    pass
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                        # 写入缓存 / Write to cache
                        process_info_cache[pid] = proc_data

                    # 从缓存和 NVML 构建返回数据 / Build return data from cache and NVML
                    cached = process_info_cache[pid]
                    putil = proc_util_map.get(pid)
                    proc_info = {
                        "pid": pid,
                        "gpu_memory_usage_mb": bytes_to_mb(p.usedGpuMemory if p.usedGpuMemory else 0),
                        "cwd": cached["cwd"],
                        "create_time": cached["create_time"],
                        "username": cached.get("username", "unknown"),
                        "name": cached.get("name", "unknown"),
                        "cmdline": cached.get("cmdline", ""),
                        "gpu_util": putil["sm"] if putil else None,   # 每进程 SM 利用率 %（不支持时为 None） / Per-process SM utilization % (None if unsupported)
                        "gpu_mem_util": putil["mem"] if putil else None,  # 每进程显存带宽利用率 % / Per-process memory-bandwidth utilization %
                    }
                    processes.append(proc_info)
                
                gpu_info = {
                    'index': i,
                    'name': name.decode('utf-8') if isinstance(name, bytes) else name,
                    'temperature': temp,
                    'fan_speed': fan_speed,
                    'sm_clock_mhz': sm_clock_mhz,        # 核心频率 MHz / SM clock MHz
                    'mem_clock_mhz': mem_clock_mhz,      # 显存频率 MHz / Memory clock MHz
                    'throttle_reasons': throttle_reasons,  # 当前降频原因名称列表 / Active throttle reason names
                    'ecc_uncorrected': ecc_uncorrected,  # 易失性不可纠正 ECC 错误数 / Volatile uncorrected ECC errors
                    'utilization': util.gpu,
                    'memory_utilization': util.memory,
                    'memory_used': mem_used,
                    'memory_total': mem_total,
                    'memory_percent': round(mem_percent, 1),
                    'power_draw': round(power_draw, 1),
                    'power_limit': round(power_limit, 1),
                    'power_percent': round(power_percent, 1),
                    'processes': processes # 将进程列表加入到最终的 JSON 节点中 / Add the process list to the final JSON node
                }
                gpus_data.append(gpu_info)
                
            # --- 缓存清理 / Cache cleanup ---
            # 遍历完所有显卡后，清理掉已经不存在的 PID 缓存，防止字典无限膨胀导致内存泄漏 / After iterating all GPUs, remove non-existent PID caches to prevent the dict from growing unbounded and leaking memory
            process_info_cache = {k: v for k, v in process_info_cache.items() if k in current_active_pids}
                
            return gpus_data
        except NVMLError as e:
            return []

# --- 2. CPU 指标 / CPU metrics ---
def get_cpu_metrics():
    try:
        data = {
            "percent": psutil.cpu_percent(interval=None), # 非阻塞：返回自上次调用以来的均值 / Non-blocking: mean since last call
            "per_core": psutil.cpu_percent(interval=None, percpu=True), # 每核占用 / Per-core usage
            "physical_cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(logical=True),
        }
        # 系统平均负载 1/5/15 分钟；Windows 上 psutil 为模拟值，需容错 / Load average 1/5/15 min; emulated on Windows by psutil, guard required
        try:
            la1, la5, la15 = psutil.getloadavg()
            data["load_avg"] = [round(la1, 2), round(la5, 2), round(la15, 2)]
        except (AttributeError, OSError):
            data["load_avg"] = None
        # CPU 频率（部分平台/虚拟机不提供，需容错） / CPU frequency (unavailable on some platforms/VMs, guard required)
        try:
            freq = psutil.cpu_freq()
            data["freq_mhz"] = round(freq.current, 0) if freq else None
        except Exception:
            data["freq_mhz"] = None
        return data
    except Exception as e:
        return {"error": str(e)}

# --- 3. 内存 (RAM) 指标 / Memory (RAM) metrics ---
def get_memory_metrics():
    try:
        mem = psutil.virtual_memory()
        data = {
            "total_gb": bytes_to_gb(mem.total),
            "used_gb": bytes_to_gb(mem.used),
            "available_gb": bytes_to_gb(mem.available),  # 新增：真正可用（含可回收缓存）内存 / New: truly available (incl. reclaimable cache) memory
            "percent": mem.percent,
        }
        # 新增：交换分区 (swap) / New: swap partition
        try:
            swap = psutil.swap_memory()
            data["swap_total_gb"] = bytes_to_gb(swap.total)
            data["swap_used_gb"] = bytes_to_gb(swap.used)
            data["swap_percent"] = swap.percent
        except Exception:
            pass
        return data
    except Exception as e:
        return {"error": str(e)}

# --- 4. 存储 (Disk) 指标 / Storage (Disk) metrics ---
def get_disk_metrics():
    disks = []
    try:
        # 获取所有磁盘分区 (all=False 通常会过滤掉一部分，但不同系统表现不一) / Get all disk partitions (all=False usually filters some out, but behavior varies by system)
        partitions = psutil.disk_partitions(all=False)

        # 定义需要忽略的挂载特征 / Define mount characteristics to ignore
        # squashfs: Snap 包使用的只读文件系统 / squashfs: read-only filesystem used by Snap packages
        # tmpfs / devtmpfs / overlay: 内存文件系统或 Docker 覆盖层，通常不关注物理容量 / tmpfs / devtmpfs / overlay: in-memory filesystems or Docker overlays, physical capacity usually irrelevant
        ignored_fstypes = {'squashfs', 'tmpfs', 'devtmpfs', 'overlay'}

        seen_devices = set()

        for p in partitions:
            # 综合过滤逻辑： / Combined filtering logic:
            # 1. 过滤掉没有 fstype 的空设备 / 1. Filter out empty devices without fstype
            # 2. 过滤 cdrom 光驱 / 2. Filter out cdrom drives
            # 3. 过滤 fstype 在黑名单中的文件系统 (核心：干掉 squashfs) / 3. Filter out filesystems whose fstype is blacklisted (key: drop squashfs)
            # 4. 过滤 /dev/loop 开头的虚拟环回设备 / 4. Filter out virtual loopback devices starting with /dev/loop
            if (not p.fstype or
                'cdrom' in p.opts or
                p.fstype.lower() in ignored_fstypes or
                p.device.startswith('/dev/loop')):
                continue

            # 新增：设备去重。如果这块硬盘（如 /dev/sda2）已经被记录过，直接跳过其子挂载点 / New: device dedup. If this disk (e.g. /dev/sda2) is already recorded, skip its sub-mountpoints
            if p.device in seen_devices:
                continue

            try:
                usage = psutil.disk_usage(p.mountpoint)

                if usage.total == 0:
                    continue

                # 记录该设备，防止重复 / Record this device to avoid duplicates
                seen_devices.add(p.device)
                disks.append({
                    "device": p.device,
                    "mountpoint": p.mountpoint,
                    "fstype": p.fstype,
                    "total_gb": bytes_to_gb(usage.total),
                    "used_gb": bytes_to_gb(usage.used),
                    "percent": usage.percent
                })
            except Exception:
                continue # 忽略访问不到的驱动器 / Ignore inaccessible drives
        return disks
    except Exception as e:
        return [{"error": str(e)}]

# --- 4b. 磁盘 I/O 速率（瞬时读写，与网络同理靠差值计算） / Disk I/O rates (instantaneous read/write, delta-based like network) ---
def get_disk_io_metrics():
    global last_disk_io, last_disk_time
    with disk_lock:
        try:
            current = psutil.disk_io_counters()
        except Exception as e:
            return {"error": str(e)}
        if current is None:
            return None

        current_time = time.time()
        read_mbps = 0
        write_mbps = 0

        if last_disk_io is not None:
            time_delta = current_time - last_disk_time
            if time_delta > 0:
                read_delta = current.read_bytes - last_disk_io.read_bytes
                write_delta = current.write_bytes - last_disk_io.write_bytes
                # 速率 MB/s（字节量，非比特） / Rate in MB/s (bytes, not bits)
                read_mbps = round((read_delta / time_delta) / (1024**2), 2)
                write_mbps = round((write_delta / time_delta) / (1024**2), 2)

        last_disk_io = current
        last_disk_time = current_time

        return {
            "read_mbps": read_mbps,   # 瞬时读取速率 MB/s / Instantaneous read rate MB/s
            "write_mbps": write_mbps,  # 瞬时写入速率 MB/s / Instantaneous write rate MB/s
            "total_read_gb": bytes_to_gb(current.read_bytes),
            "total_write_gb": bytes_to_gb(current.write_bytes),
        }

# --- 5. 网络 (Network) 指标 (计算瞬时速度) / Network metrics (compute instantaneous speed) ---
def get_network_metrics():
    global last_net_stats, last_net_time
    with net_lock:
        current_stats = psutil.net_io_counters()
        current_time = time.time()

        # 默认值 / Default values
        send_mbps = 0
        recv_mbps = 0

        if last_net_stats is not None:
            time_delta = current_time - last_net_time
            if time_delta > 0:
                send_delta = current_stats.bytes_sent - last_net_stats.bytes_sent
                recv_delta = current_stats.bytes_recv - last_net_stats.bytes_recv

                # 速度 (Bytes/s) / Speed (Bytes/s)
                send_speed = send_delta / time_delta
                recv_speed = recv_delta / time_delta

                # 速度 (MB/s) / Speed (MB/s)
                send_mbps = round((send_speed * 8) / (1024**2), 2)
                recv_mbps = round((recv_speed * 8) / (1024**2), 2)

        # 更新全局变量 / Update global variables
        last_net_stats = current_stats
        last_net_time = current_time

        result = {
            "send_mbps": send_mbps, # 瞬时发送速度 (Mb/s) / Instantaneous send speed (Mb/s)
            "recv_mbps": recv_mbps, # 瞬时接收速度 (Mb/s) / Instantaneous receive speed (Mb/s)
            "total_sent_gb": bytes_to_gb(current_stats.bytes_sent),
            "total_recv_gb": bytes_to_gb(current_stats.bytes_recv),
            # 新增：累计错误/丢包计数（聚合），排查链路质量 / New: cumulative error/drop counts (aggregate) for link-quality triage
            "errin": current_stats.errin,
            "errout": current_stats.errout,
            "dropin": current_stats.dropin,
            "dropout": current_stats.dropout,
        }

        # 新增：分网卡累计流量与错误/丢包（回环 lo 跳过） / New: per-NIC cumulative traffic and error/drop (skip loopback lo)
        try:
            per_nic = {}
            for nic, s in psutil.net_io_counters(pernic=True).items():
                if nic == "lo" or nic.startswith("Loopback"):
                    continue
                per_nic[nic] = {
                    "sent_gb": bytes_to_gb(s.bytes_sent),
                    "recv_gb": bytes_to_gb(s.bytes_recv),
                    "errin": s.errin,
                    "errout": s.errout,
                    "dropin": s.dropin,
                    "dropout": s.dropout,
                }
            result["per_nic"] = per_nic
        except Exception:
            result["per_nic"] = None

        # 新增：网络连接数（部分平台需权限，容错） / New: network connection count (needs privileges on some platforms, guarded)
        try:
            result["connections"] = len(psutil.net_connections(kind="inet"))
        except Exception:
            result["connections"] = None

        return result

# --- 6. 系统 (System) 指标 / System metrics ---
def get_system_metrics():
    try:
        boot_time = psutil.boot_time()
        uptime_seconds = int(time.time() - boot_time)
        uptime_str = str(datetime.timedelta(seconds=uptime_seconds))

        data = {
            "hostname": platform.node(), # 新增：主机名，便于识别是哪台 Agent / New: hostname, to identify which agent this is
            "platform": platform.platform(),
            "boot_time": datetime.datetime.fromtimestamp(boot_time).isoformat(),
            "uptime_str": uptime_str
        }

        # 新增：登录用户列表（去重用户名） / New: logged-in users (deduplicated usernames)
        try:
            data["users"] = sorted({u.name for u in psutil.users()})
        except Exception:
            data["users"] = None

        # 新增：温度传感器（主要为 Linux；Windows/无传感器时为 None） / New: temperature sensors (mainly Linux; None on Windows / when unavailable)
        try:
            temps = {}
            raw = getattr(psutil, "sensors_temperatures", lambda: {})()
            for chip, entries in (raw or {}).items():
                readings = [round(e.current, 1) for e in entries if e.current is not None]
                if readings:
                    temps[chip] = max(readings)  # 每个芯片取最高温，客户端按需展示 / Take the max temp per chip; client shows as needed
            data["sensors_temp"] = temps or None
        except Exception:
            data["sensors_temp"] = None

        return data
    except Exception as e:
        return {"error": str(e)}


# --- 后台采样 / Background sampling ---
def sample_all():
    """采集一次全部指标 / Collect all metrics once."""
    return {
        "timestamp": time.time(),
        "system": get_system_metrics(),
        "cpu": get_cpu_metrics(),
        "memory": get_memory_metrics(),
        "gpus": get_gpu_metrics(),
        "disks": get_disk_metrics(),
        "disk_io": get_disk_io_metrics(),
        "network": get_network_metrics()
    }

def sampler_loop():
    """后台采样线程：按固定间隔刷新全局快照。 / Background sampler thread: refresh the global snapshot at a fixed interval."""
    global latest_snapshot
    while True:
        try:
            snap = sample_all()
            with snapshot_lock:
                latest_snapshot = snap
        except Exception as e:
            # 采样失败则保留上一次快照，不让线程退出。 / On failure keep the previous snapshot; don't let the thread die.
            print(f"[sampler] 采样出错 / sampling error: {e}")
        time.sleep(SAMPLE_INTERVAL)


# --- 根端点: /metrics / Root endpoint: /metrics ---
@app.route('/metrics')
def get_all_metrics():
    """
    返回最近一次后台采样快照（不再每次请求现采，从而封顶 CPU 并保证网速/CPU 计算一致）。
    Return the latest background-sampled snapshot (no per-request sampling: caps CPU and keeps net/CPU math consistent).
    """
    with snapshot_lock:
        return jsonify(latest_snapshot)

@app.route('/')
def index():
    return "GPU/System Metrics Agent (v1.1) is running. Visit /metrics to see data."

if __name__ == '__main__':
    try:
        # 预热网络与 CPU 统计，并做一次首采样，避免首个请求拿到占位数据 / Warm up net & CPU stats and take a first sample so early requests don't get placeholder data
        get_network_metrics()
        get_cpu_metrics()
        get_disk_io_metrics()

        # 启动后台采样线程（守护线程，随主进程退出） / Start background sampler thread (daemon, exits with the main process)
        Thread(target=sampler_loop, daemon=True).start()

        print(f"启动全功能监控 Agent，监听 0.0.0.0:{AGENT_PORT}（采样间隔 {SAMPLE_INTERVAL}s） / Starting full monitor agent on 0.0.0.0:{AGENT_PORT} (sample interval {SAMPLE_INTERVAL}s)...")

        # 优先使用生产级 WSGI 服务器 waitress（跨平台、单进程多线程，契合 Agent 的跨请求全局状态）；未安装则回退 Flask 开发服务器。
        # Prefer the production WSGI server waitress (cross-platform, single-process multi-threaded, fits the agent's cross-request global state); fall back to the Flask dev server if not installed.
        try:
            from waitress import serve
            serve(app, host='0.0.0.0', port=AGENT_PORT, threads=8)
        except ImportError:
            print("未安装 waitress，回退到 Flask 开发服务器（生产环境请 pip install waitress） / waitress not installed, falling back to the Flask dev server (pip install waitress for production)")
            app.run(host='0.0.0.0', port=AGENT_PORT)

    finally:
        # 如果服务关闭, 确保 NVML 也关闭 / If the service shuts down, ensure NVML is shut down too
        if nvml_initialized:
            with nvml_lock:
                try:
                    nvmlShutdown()
                    print("NVML 已关闭。")
                except:
                    pass