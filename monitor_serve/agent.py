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
from threading import Lock

# --- 全局变量和锁 / Global variables and lock ---
app = Flask(__name__)
AGENT_PORT = 48210  # 监控 Agent 监听端口 / Metrics agent listening port
nvml_initialized = False
nvml_lock = Lock() # pynvml 建议在多线程中使用锁 / pynvml recommends using a lock in multithreading

# 用于计算网络速度 / Used to compute network speed
last_net_stats = None
last_net_time = None
net_lock = Lock()

process_info_cache = {}

# --- 辅助函数：格式化字节 / Helper functions: format bytes ---
def bytes_to_gb(b):
    return round(b / (1024**3), 2)

def bytes_to_mb(b):
    return round(b / (1024**2), 2)

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
                
                mem_info = nvmlDeviceGetMemoryInfo(handle)
                mem_used = bytes_to_mb(mem_info.used)
                mem_total = bytes_to_mb(mem_info.total)
                mem_percent = (mem_used / mem_total * 100) if mem_total > 0 else 0
                
                util = nvmlDeviceGetUtilizationRates(handle)
                
                # --- 新增/修改：带有缓存机制的进程信息获取 / New/Modified: process info retrieval with caching ---
                processes = []
                nvml_procs = nvmlDeviceGetComputeRunningProcesses(handle) + \
                             nvmlDeviceGetGraphicsRunningProcesses(handle)
                
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
                        proc_data = {"cwd": "unknown", "create_time": "unknown"}
                        try:
                            ps_proc = psutil.Process(pid)
                            with ps_proc.oneshot(): # 进一步优化瞬间的读取性能 / Further optimize instantaneous read performance
                                proc_data["cwd"] = ps_proc.cwd()
                                create_time = datetime.datetime.fromtimestamp(ps_proc.create_time())
                                proc_data["create_time"] = create_time.isoformat()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                        # 写入缓存 / Write to cache
                        process_info_cache[pid] = proc_data

                    # 从缓存和 NVML 构建返回数据 / Build return data from cache and NVML
                    proc_info = {
                        "pid": pid,
                        "gpu_memory_usage_mb": bytes_to_mb(p.usedGpuMemory if p.usedGpuMemory else 0),
                        "cwd": process_info_cache[pid]["cwd"],
                        "create_time": process_info_cache[pid]["create_time"]
                    }
                    processes.append(proc_info)
                
                gpu_info = {
                    'index': i,
                    'name': name.decode('utf-8') if isinstance(name, bytes) else name,
                    'temperature': temp,
                    'utilization': util.gpu,
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
        return {
            "percent": psutil.cpu_percent(interval=None), # 非阻塞 / Non-blocking
            "physical_cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(logical=True)
        }
    except Exception as e:
        return {"error": str(e)}

# --- 3. 内存 (RAM) 指标 / Memory (RAM) metrics ---
def get_memory_metrics():
    try:
        mem = psutil.virtual_memory()
        return {
            "total_gb": bytes_to_gb(mem.total),
            "used_gb": bytes_to_gb(mem.used),
            "percent": mem.percent
        }
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

        return {
            "send_mbps": send_mbps, # 瞬时发送速度 (Mb/s) / Instantaneous send speed (Mb/s)
            "recv_mbps": recv_mbps, # 瞬时接收速度 (Mb/s) / Instantaneous receive speed (Mb/s)
            "total_sent_gb": bytes_to_gb(current_stats.bytes_sent),
            "total_recv_gb": bytes_to_gb(current_stats.bytes_recv)
        }

# --- 6. 系统 (System) 指标 / System metrics ---
def get_system_metrics():
    try:
        boot_time = psutil.boot_time()
        uptime_seconds = int(time.time() - boot_time)
        uptime_str = str(datetime.timedelta(seconds=uptime_seconds))
        
        return {
            "platform": platform.platform(),
            "boot_time": datetime.datetime.fromtimestamp(boot_time).isoformat(),
            "uptime_str": uptime_str
        }
    except Exception as e:
        return {"error": str(e)}


# --- 根端点: /metrics / Root endpoint: /metrics ---
@app.route('/metrics')
def get_all_metrics():
    """
    将所有指标汇总到一个JSON中
    Aggregate all metrics into a single JSON.
    """
    all_data = {
        "timestamp": time.time(),
        "system": get_system_metrics(),
        "cpu": get_cpu_metrics(),
        "memory": get_memory_metrics(),
        "gpus": get_gpu_metrics(),
        "disks": get_disk_metrics(),
        "network": get_network_metrics()
    }
    return jsonify(all_data)

@app.route('/')
def index():
    return "GPU/System Metrics Agent (v2) is running. Visit /metrics to see data."

if __name__ == '__main__':
    # 导入 datetime 仅用于系统指标 / Import datetime only for system metrics
    import datetime

    try:
        # 在启动时预热网络统计 / Warm up network stats at startup
        get_network_metrics()

        print(f"启动全功能监控 Agent，监听 0.0.0.0:{AGENT_PORT}... / Starting full monitor agent on 0.0.0.0:{AGENT_PORT}...")
        # 建议使用生产级WSGI服务器, 如 Gunicorn 或 Waitress / Recommend a production-grade WSGI server such as Gunicorn or Waitress
        # from waitress import serve
        # serve(app, host='0.0.0.0', port=AGENT_PORT)
        app.run(host='0.0.0.0', port=AGENT_PORT, debug=True)

    finally:
        # 如果服务关闭, 确保 NVML 也关闭 / If the service shuts down, ensure NVML is shut down too
        if nvml_initialized:
            with nvml_lock:
                try:
                    nvmlShutdown()
                    print("NVML 已关闭。")
                except:
                    pass