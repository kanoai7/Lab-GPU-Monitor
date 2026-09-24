import requests
import time
import threading
import os
import sys
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import json

# --- 平台特定的非阻塞按键监听 / Platform-specific non-blocking key listener ---
try:
    # Windows
    import msvcrt
    def get_key():
        """获取单个按键 (非阻塞, Windows)
        Get a single keypress (non-blocking, Windows)"""
        if msvcrt.kbhit():
            key = msvcrt.getch()
            try:
                return key.decode('utf-8').lower()
            except UnicodeDecodeError:
                return key # 返回原始字节 / Return the raw bytes
        return None
    
    def setup_terminal():
        pass # Windows 不需要设置 / Windows needs no setup
    
    def cleanup_terminal():
        pass # Windows 不需要清理 / Windows needs no cleanup

except ImportError:
    # Linux / macOS
    import tty
    import termios
    import select

    original_termios_settings = None

    def setup_terminal():
        """将终端设置为原始模式
        Set the terminal to raw mode"""
        global original_termios_settings
        fd = sys.stdin.fileno()
        original_termios_settings = termios.tcgetattr(fd)
        tty.setraw(sys.stdin.fileno())

    def cleanup_terminal():
        """恢复终端的原始设置
        Restore the terminal's original settings"""
        if original_termios_settings:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, original_termios_settings)

    def get_key():
        """获取单个按键 (非阻塞, Linux/Mac)
        Get a single keypress (non-blocking, Linux/Mac)"""
        if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
            return sys.stdin.read(1).lower()
        return None

# --- 配置 / Configuration ---
SERVER_AGENTS = {
    "server-01": {"url": "http://<agent-01-host>:48210/metrics"},
    "server-02": {"url": "http://<agent-02-host>:48210/metrics"},
    "server-03": {"url": "http://<agent-03-host>:48210/metrics"},
    "server-04": {"url": "http://<agent-04-host>:48210/metrics"},
}

# --- 颜色定义 / Color definitions ---
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'
    GRAY = '\033[90m'

ANSI_ESCAPE_PATTERN = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def get_visible_length(s):
    return len(ANSI_ESCAPE_PATTERN.sub('', s))

# --- 辅助函数 / Helper functions ---
def format_bar(percentage, width=15, color=Colors.GREEN):
    """创建进度条
    Build a progress bar"""
    if percentage is None:
        percentage = 0
    filled = int(width * percentage / 100)
    bar = '█' * filled + '░' * (width - filled)
    return f"{color}{bar}{Colors.END}"

def get_temp_color(temp):
    """根据温度获取颜色
    Pick a color based on temperature"""
    if temp is None: return Colors.GRAY
    if temp < 60: return Colors.GREEN
    elif temp < 80: return Colors.YELLOW
    else: return Colors.RED

def get_util_color(util):
    """根据使用率获取颜色
    Pick a color based on utilization"""
    if util is None: return Colors.GRAY
    if util < 30: return Colors.GREEN
    elif util < 70: return Colors.YELLOW
    else: return Colors.RED

def format_size_gb(size_gb):
    """格式化 GB 大小 (GB 或 TB)
    Format a size in GB (as GB or TB)"""
    if size_gb is None: return "N/A"
    if size_gb < 1024:
        return f"{size_gb:.1f}G"
    else:
        return f"{size_gb / 1024:.1f}T"

class CLIMonitor:
    def __init__(self):
        self.server_data = {}
        self.data_lock = threading.Lock()
        self.display_lock = threading.Lock() 
        self.running = True
        
        # 页面控制 / Page control
        self.current_page = 'main' # 'main', 'system', 'gpu', 'storage', 'settings'
        
        # 状态 / Status
        self.last_update_time = None
        self.status_message = ""
        
        # 设置 / Settings
        self.refresh_rate = 10
        
        # 线程 / Threads
        self.data_thread = None
        self.display_thread = None

    def clear_screen(self):
        """清屏
        Clear the screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    # --- 数据获取 / Data fetching ---
    
    def fetch_single_agent(self, server_name, url):
        """使用 requests 获取单个 Agent 的数据
        Fetch a single agent's data via requests"""
        try:
            response = requests.get(url, timeout=2.0)
            response.raise_for_status() 
            return server_name, {"status": "online", "data": response.json()}
        except requests.exceptions.Timeout:
            return server_name, {"status": "offline", "error": "超时"}
        except requests.exceptions.RequestException as e:
            return server_name, {"status": "offline", "error": "连接失败"}
        except json.JSONDecodeError:
            return server_name, {"status": "offline", "error": "数据解析失败"}

    def update_all_data(self):
        """使用 ThreadPoolExecutor 并发地获取所有 Agent 数据
        Fetch all agents' data concurrently with a ThreadPoolExecutor"""
        def fetch_server_data(server_name_url):
            server_name, url = server_name_url
            return self.fetch_single_agent(server_name, url)
        
        tasks = [(name, config['url']) for name, config in SERVER_AGENTS.items()]
        
        temp_data_store = {}
        with ThreadPoolExecutor(max_workers=len(tasks) or 1) as executor:
            futures = executor.map(fetch_server_data, tasks)
            for server_name, result in futures:
                temp_data_store[server_name] = result

        with self.data_lock:
            self.server_data = temp_data_store
        
        self.last_update_time = datetime.now()
        self.status_message = f"数据已于 {self.last_update_time.strftime('%H:%M:%S')} 刷新"

    def _data_fetch_loop(self):
        """(线程) 负责定时获取数据
        (Thread) Periodically fetch data"""
        while self.running:
            try:
                self.update_all_data()
                start_sleep = time.time()
                while time.time() - start_sleep < self.refresh_rate:
                    if not self.running: return
                    time.sleep(0.1)
            except Exception as e:
                with self.display_lock:
                    print(f"数据获取线程出错: {e}")
                time.sleep(self.refresh_rate) 

    # --- 页面显示 / Page rendering ---

    def print_header(self, page_title: str): # page_title 参数现在被忽略了 / The page_title argument is now ignored
        """【已修改】ASCII Art 标题 (Req 3)
        [Modified] ASCII art title (Req 3)"""
        ASCII_TITLE = [
            r"  ____ ____  _   _ ",
            r" / ___|  _ \| | | |",
            r"| |  _| |_) | | | |",
            r"| |_| |  __/| |_| |",
            r" \____|_|    \___/ ",
        ]
        
        # 居中打印 (总宽 50) / Print centered (total width 50)
        print(f"{Colors.BOLD}{Colors.CYAN}") # 开始颜色 / Begin color
        for line in ASCII_TITLE:
            print(f"{line:^56}") # :^50 将字符串在 50 个字符宽度内居中 / :^50 centers the string within a 50-char width
        print(f"{Colors.END}") # 结束颜色 / End color
        print() # 留出一个空行 / Leave a blank line

    def print_footer(self, current_page):
        
        # 辅助函数: / Helper function:
        # key = 'M', suffix = 'ain', page_name = 'main'
        def format_menu_item(key, suffix, page_name):
            if page_name == current_page:
                # 高亮 / Highlighted: e.g., [M]ain in Yellow
                return f"{Colors.BOLD}{Colors.YELLOW}[{key}]{suffix}{Colors.END}"
            else:
                # 默认 / Default: e.g., [M] in Bold, ain in Gray
                return f"{Colors.BOLD}[{key}]{Colors.END}{Colors.GRAY}{suffix}{Colors.END}"

        # 获取样式 / Get styles
        m_item = format_menu_item("M", "ain", "main")
        s_item = format_menu_item("S", "ystem", "system")
        g_item = format_menu_item("G", "PU", "gpu")
        p_item = format_menu_item("P", "rocess", "processes") # <--- 新增 P 键 / Added the P key
        d_item = format_menu_item("D", "isk", "storage")
        e_item = format_menu_item("E", "ettings", "settings")
        r_item = f"{Colors.BOLD}[R]{Colors.END}{Colors.GRAY}econnect{Colors.END}"
        q_item = f"{Colors.BOLD}[Q]{Colors.END}{Colors.GRAY}uit{Colors.END}"

        # 重新排版: 第一行放入 M, S, G, P / Re-layout: first row holds M, S, G, P
        line1_items = [
            (m_item, get_visible_length(m_item)),
            (s_item, get_visible_length(s_item)),
            (p_item, get_visible_length(p_item)), # P 移到第三列 / P moved to the third column
            (g_item, get_visible_length(g_item))  # G 移到第四列 / G moved to the fourth column
        ]
        
        # 第二行放入 D, E, R, Q / Second row holds D, E, R, Q
        line2_items = [
            (d_item, get_visible_length(d_item)),
            (e_item, get_visible_length(e_item)),
            (r_item, get_visible_length(r_item)),
            (q_item, get_visible_length(q_item)),
        ]
        
        # --- 修改部分：统一两行的列宽配置 / Modified: unify the column-width config for both rows ---
        # 保证第三列足够宽 (14字符)，完美容纳 Process 和 Reconnect / Keep the third column wide enough (14 chars) to fit Process and Reconnect
        col_widths = [10, 12, 14, 10] 
        
        line1 = ""
        line1 += f"{line1_items[0][0]}{' ' * (col_widths[0] - line1_items[0][1])}"
        line1 += f" | {line1_items[1][0]}{' ' * (col_widths[1] - line1_items[1][1])}"
        line1 += f" | {line1_items[2][0]}{' ' * (col_widths[2] - line1_items[2][1])}"
        line1 += f" | {line1_items[3][0]}" 
        
        line2 = ""
        line2 += f"{line2_items[0][0]}{' ' * (col_widths[0] - line2_items[0][1])}"
        line2 += f" | {line2_items[1][0]}{' ' * (col_widths[1] - line2_items[1][1])}"
        line2 += f" | {line2_items[2][0]}{' ' * (col_widths[2] - line2_items[2][1])}"
        line2 += f" | {line2_items[3][0]}"

        # 打印 / Print
        print(f"\n{Colors.GRAY}{'-' * 55}{Colors.END}") # 稍微加长底部分隔线，配合更长的工作目录 / Lengthen the bottom divider a bit to match the longer working directory
        print(f"{line1}") 
        print(f"{line2}")
        print(f"{Colors.YELLOW}{self.status_message}{Colors.END}")

    def display_main_menu(self, data_copy):
        """(页面 1) 显示主菜单
        (Page 1) Show the main menu"""
        print(f"{Colors.BOLD}欢迎使用硬件监控系统 (CLI版){Colors.END}\n")
        print("请使用键盘快捷键在页面间导航：\n")
        print(f"  {Colors.BOLD}[S]{Colors.END} - {Colors.CYAN}系统信息{Colors.END} (CPU, 内存, 网络, 概览)")
        print(f"  {Colors.BOLD}[G]{Colors.END} - {Colors.CYAN}GPU 监控{Colors.END} (您请求的 GPU 视图)")
        print(f"  {Colors.BOLD}[P]{Colors.END} - {Colors.CYAN}进程监控{Colors.END} (查看 GPU 上的活跃任务)")
        print(f"  {Colors.BOLD}[D]{Colors.END} - {Colors.CYAN}存储信息{Colors.END} (Disks)")
        print(f"  {Colors.BOLD}[E]{Colors.END} - {Colors.CYAN}设置{Colors.END} (Settings)\n")
        
        print(f"{Colors.BOLD}服务器状态:{Colors.END}")
        if not data_copy:
            print(f"  {Colors.YELLOW}正在加载数据...{Colors.END}")
            return
            
        for name, info in data_copy.items():
            if info['status'] == 'online':
                print(f"  - {name}: {Colors.GREEN}[在线]{Colors.END}")
            else:
                print(f"  - {name}: {Colors.RED}[离线] {Colors.END}({info.get('error', 'N/A')})")

    def display_system_info(self, data_copy):
        """(页面 2) 显示系统信息页
        (Page 2) Show the system info page"""
        
        if not data_copy:
            print(f"  {Colors.YELLOW}正在加载数据...{Colors.END}")
            return

        for name, info in data_copy.items():
            print(f"{Colors.BOLD}{Colors.BLUE}┌─ {name} {Colors.END}", end="")
            if info['status'] == 'online':
                print(f"{Colors.GREEN}[在线]{Colors.END}")
                d = info['data']
                
                # ... (内部逻辑不变) ... / ... (internal logic unchanged) ...
                sys_info = d.get("system", {})
                uptime = sys_info.get("uptime_str", "N/A")
                platform = sys_info.get("platform", "N/A")
                cpu = d.get("cpu", {})
                cpu_p = cpu.get("percent", 0)
                cpu_bar = format_bar(cpu_p, 20, get_util_color(cpu_p))
                mem = d.get("memory", {})
                mem_p = mem.get("percent", 0)
                mem_bar = format_bar(mem_p, 20, get_util_color(mem_p * 1.5))
                net = d.get("network", {})
                
                print(f"{Colors.BLUE}│{Colors.END}  {Colors.WHITE}平台:{Colors.END}   {platform}")
                print(f"{Colors.BLUE}│{Colors.END}  {Colors.WHITE}运行:{Colors.END}   {uptime}")
                print(f"{Colors.BLUE}│{Colors.END}  {Colors.WHITE}CPU:{Colors.END}    [{cpu_p:5.1f}%] {cpu_bar} ({cpu.get('logical_cores')} 核)")
                print(f"{Colors.BLUE}│{Colors.END}  {Colors.WHITE}内存:{Colors.END}   [{mem_p:5.1f}%] {mem_bar} ({format_size_gb(mem.get('used_gb'))} / {format_size_gb(mem.get('total_gb'))})")
                print(f"{Colors.BLUE}│{Colors.END}  {Colors.WHITE}网络↓:{Colors.END}  {net.get('recv_mbps', 0):.2f} Mbps  (总: {net.get('total_recv_gb', 0):.2f} GB)")
                print(f"{Colors.BLUE}│{Colors.END}  {Colors.WHITE}网络↑:{Colors.END}  {net.get('send_mbps', 0):.2f} Mbps  (总: {net.get('total_sent_gb', 0):.2f} GB)")

            else:
                print(f"{Colors.RED}[离线] - {info.get('error', 'N/A')}{Colors.END}")
            
            # 【已修改】Req 3: 宽度 50 / [Modified] Req 3: width 50
            print(f"{Colors.BLUE}└{'─' * 48}{Colors.END}") # 50 - 2 (┌─)

    def display_gpu_info(self, data_copy):
        """(页面 3) 【已修改】为所有服务器添加统一的闭合边框
        (Page 3) [Modified] Add a uniform closing border for every server"""
        # self.print_header("显卡") # <--- 确保这行已被删除或注释掉 / Make sure this line is deleted or commented out

        if not data_copy:
            print(f"  {Colors.YELLOW}正在加载数据...{Colors.END}")
            return
            
        for server_name, server_info in data_copy.items():
            status_color = Colors.GREEN if server_info['status'] == 'online' else Colors.RED
            status_text = "在线" if server_info['status'] == 'online' else f"离线 ({server_info.get('error', 'N/A')})"
            
            print(f"{Colors.BOLD}{Colors.BLUE}┌─ {server_name} {status_color}[{status_text}]{Colors.END}")
            
            gpu_list = server_info.get('data', {}).get('gpus', [])
            
            if server_info['status'] == 'offline' or not gpu_list:
                print(f"{Colors.RED}│  连接失败或无GPU数据{Colors.END}")
                # (注意: 我们不再在这里打印 '└'，它将在下面统一处理) / (Note: we no longer print '└' here; it is handled uniformly below)
            else:
                # 【修改】循环打印所有 GPU，全部使用 ├ 和 │ / [Modified] Loop and print all GPUs, all using ├ and │
                for i, gpu in enumerate(gpu_list):
                    gpu_name = gpu.get('name', 'N/A')
                    gpu_name = gpu_name[:30] + "..." if len(gpu_name) > 30 else gpu_name
                    
                    # 【修改】'line_char' 始终是 '├' / [Modified] 'line_char' is always '├'
                    line_char = "├" 
                    
                    print(f"{Colors.BLUE}{line_char}─ GPU {gpu.get('index', '?')}: {Colors.WHITE}{gpu_name}{Colors.END}")
                    
                    # 【修改】'prefix' 始终是 '│ ' / [Modified] 'prefix' is always '│ '
                    prefix = f"{Colors.BLUE}│{Colors.END} "
                    
                    # (以下是显卡信息打印) / (GPU info is printed below)
                    temp = gpu.get('temperature')
                    temp_color = get_temp_color(temp) 
                    power = gpu.get('power_draw')
                    power_limit = gpu.get('power_limit')
                    util = gpu.get('utilization')
                    util_color = get_util_color(util) 
                    
                    print(f"{prefix}{Colors.END}温度: {temp_color}{temp:>3.0f}°C{Colors.END}" if temp is not None else "", end='  ')
                    print(f"{Colors.END}功耗: {Colors.MAGENTA}{power:>5.1f}/{power_limit:>5.1f}W{Colors.END}" if power is not None else "", end='  ')
                    print(f"{Colors.END}使用率: {util_color}{util:>3.0f}%{Colors.END}" if util is not None else "")

                    mem_used = gpu.get('memory_used')
                    mem_total = gpu.get('memory_total')
                    mem_perc = gpu.get('memory_percent')
                    
                    if mem_perc is not None:
                        mem_bar = format_bar(mem_perc, 15, Colors.YELLOW)
                        print(f"{prefix}{Colors.END}显存: {Colors.YELLOW}{mem_used:>5.0f}MB / {mem_total:>5.0f}MB ({mem_perc:>3.1f}%){Colors.END} {mem_bar}")
                    
                    # 【修改】在 GPU 之间添加 '│' 分隔符 (如果不是最后一块) / [Modified] Add a '│' separator between GPUs (unless it is the last one)
                    if i < len(gpu_list) - 1:
                        print(f"{Colors.BLUE}│{Colors.END}")
            
            # 【修改】无论在线还是离线，都在最后统一打印闭合线 / [Modified] Print the closing line uniformly at the end, whether online or offline
            print(f"{Colors.BLUE}└{'─' * 48}{Colors.END}")

    def display_processes_info(self, data_copy):
        """(页面 6) 显示 GPU 进程信息
        (Page 6) Show GPU process info"""
        if not data_copy:
            print(f"  {Colors.YELLOW}正在加载数据...{Colors.END}")
            return

        for server_name, server_info in data_copy.items():
            status_color = Colors.GREEN if server_info['status'] == 'online' else Colors.RED
            status_text = "在线" if server_info['status'] == 'online' else f"离线 ({server_info.get('error', 'N/A')})"
            
            print(f"{Colors.BOLD}{Colors.BLUE}┌─ {server_name} {status_color}[{status_text}]{Colors.END}")
            
            if server_info['status'] == 'offline':
                print(f"{Colors.RED}│  连接失败{Colors.END}")
                print(f"{Colors.BLUE}└{'─' * 48}{Colors.END}")
                continue
            
            gpu_list = server_info.get('data', {}).get('gpus', [])
            if not gpu_list:
                print(f"{Colors.RED}│  无GPU数据{Colors.END}")
            else:
                # 【修改点 1】：将表头移到 GPU 循环外部，每台服务器只打印一次 / [Change 1] Move the header outside the GPU loop so it prints once per server
                print(f"{Colors.BLUE}│{Colors.END}  {Colors.CYAN}{'PID':<8} {'内存':<7} {'启动时间':<12} {'工作目录'}{Colors.END}")
                
                for i, gpu in enumerate(gpu_list):
                    gpu_name = gpu.get('name', 'N/A')
                    gpu_name = gpu_name[:25] + "..." if len(gpu_name) > 25 else gpu_name
                    print(f"{Colors.BLUE}├─ GPU {gpu.get('index', '?')}: {Colors.WHITE}{gpu_name}{Colors.END}")
                    
                    processes = gpu.get('processes', [])
                    if not processes:
                        print(f"{Colors.BLUE}│{Colors.END}  {Colors.GRAY}(无活跃进程){Colors.END}")
                    else:
                        for p in processes:
                            pid = str(p.get('pid', 'N/A'))
                            mem = f"{p.get('gpu_memory_usage_mb', 0):.0f}M"
                            
                            # 格式化时间 / Format the time
                            create_time = p.get('create_time', 'unknown')
                            time_str = '未知'
                            if create_time and create_time != 'unknown':
                                try:
                                    dt = datetime.fromisoformat(create_time)
                                    time_str = dt.strftime('%m/%d %H:%M')
                                except ValueError:
                                    time_str = create_time[:11]
                            
                            cwd = p.get('cwd', 'unknown')

                            # 【修改点 2】：拆分为两行打印 / [Change 2] Split into two printed lines
                            # 第一行展示 PID、内存和时间 / First line shows PID, memory and time
                            print(f"{Colors.BLUE}│{Colors.END}  {pid:<8} {Colors.YELLOW}{mem:<7}{Colors.END} {Colors.GRAY}{time_str:<12}{Colors.END}")
                            # 第二行紧贴左侧边框展示完整工作目录 / Second line shows the full working directory flush against the left border
                            print(f"{Colors.BLUE}│{Colors.END}{cwd}")
                            
                    if i < len(gpu_list) - 1:
                        print(f"{Colors.BLUE}│{Colors.END}") 
            
            print(f"{Colors.BLUE}└{'─' * 48}{Colors.END}")

    def display_storage_info(self, data_copy):
        """(页面 4) 【已修改】修复中英文对齐
        (Page 4) [Modified] Fix Chinese/English alignment"""
        # self.print_header("存储") # <--- 确保这行已被删除 / Make sure this line is deleted

        if not data_copy:
            print(f"  {Colors.YELLOW}正在加载数据...{Colors.END}")
            return

        for name, info in data_copy.items():
            print(f"{Colors.BOLD}{Colors.BLUE}┌─ {name} {Colors.END}", end="")
            if info['status'] == 'online':
                print(f"{Colors.GREEN}[在线]{Colors.END}")
                disks = info['data'].get('disks', [])
                
                filtered_disks = [
                    d for d in disks 
                    if d.get('fstype') not in ('squashfs', 'tmpfs', 'devtmpfs') 
                    and d.get('total_gb', 0) > 0.1
                ]
                
                # --- 新的对齐布局 / New alignment layout ---
                # 布局 (总宽 48): 15 (挂载点) + 7 (使用率) + 12 (总计) + 10 (进度) + 4 (分隔符) = 48 / Layout (total width 48): 15 (mount) + 7 (usage) + 12 (total) + 10 (bar) + 4 (separators) = 48
                col1_w, col2_w, col3_w, col4_w = 15, 7, 12, 10
                
                # 手动计算中文宽度 (1个中文=2个英文) / Manually compute CJK width (1 CJK char = 2 ASCII chars)
                header1 = '挂载点' + ' ' * (col1_w - 6)    # '挂载点' (3*2=6) / mount point
                header2 = '使用率' + ' ' * (col2_w - 6)    # '使用率' (3*2=6) / usage
                header3 = '已用/总计' + ' ' * (col3_w - 10) # '已用/总计' (5*2=10) / used/total
                header4 = '进度条' + ' ' * (col4_w - 6)      # '进度条' (3*2=6) / progress bar

                print(f"{Colors.BLUE}│ {Colors.WHITE}{header1} {header2} {header3} {header4}{Colors.END}")
                print(f"{Colors.BLUE}│ {'-'*col1_w} {'-'*col2_w} {'-'*col3_w} {'-'*col4_w}")
                
                for d in filtered_disks:
                    perc = d.get('percent', 0)
                    perc_color = get_util_color(perc * 1.2)
                    
                    bar = format_bar(perc, col4_w, perc_color) 
                    
                    used = format_size_gb(d.get('used_gb'))
                    total = format_size_gb(d.get('total_gb'))
                    
                    # --- 数据行 / Data row ---
                    col1_data = d.get('mountpoint', 'N/A')
                    # f-string 格式化 (e.g., " 89.4%" or "100.0%") / f-string formatting
                    col2_data_str = f"{perc:6.1f}%" 
                    col3_data_str = f"{used}/{total}"
                    
                    # 打印并应用 padding / Print and apply padding
                    print(f"{Colors.BLUE}│ {Colors.CYAN}{col1_data:<{col1_w}.{col1_w}}{Colors.END} "  # 15 字符 / 15 chars
                          f"{perc_color}{col2_data_str:<{col2_w}}{Colors.END} " # 7 字符 / 7 chars
                          f"{col3_data_str:<{col3_w}.{col3_w}}{Colors.END} " # 12 字符 / 12 chars
                          f"{bar}{Colors.END}") # 10 字符 / 10 chars
            else:
                print(f"{Colors.RED}[离线] - {info.get('error', 'N/A')}{Colors.END}")
            
            print(f"{Colors.BLUE}└{'─' * 48}{Colors.END}")
            
    def display_settings(self, data_copy):
        """(页面 5) 【已修改】清理设置页面 (Req 4)
        (Page 5) [Modified] Tidy up the settings page (Req 4)"""
        # self.print_header("设置") # <--- 确保这行已被删除 / Make sure this line is deleted
        
        # 【修改】顶格开始, 移除 "1." 和子文本 / [Modified] Start flush-left, remove "1." and the sub-text
        print(f"{Colors.WHITE}数据刷新频率:{Colors.END} {Colors.YELLOW}{self.refresh_rate} 秒{Colors.END}")
        
        # 【修改】移除空行 / [Modified] Remove the blank line
        print(f"{Colors.BOLD}服务器 Agent 列表:{Colors.END}\n")
        for name, config in SERVER_AGENTS.items():
            print(f"  {Colors.CYAN}- {name}:{Colors.END}")
            print(f"    {config['url']}")

    def _display_loop(self):
        """(线程) 负责定时刷新屏幕
        (Thread) Periodically refresh the screen"""
        
        # 【已添加】Req 1: 页面标题映射 / [Added] Req 1: page title map
        page_title_map = {
            'main': '首页',
            'system': '系统',
            'gpu': '显卡',
            'processes': '进程',
            'storage': '存储',
            'settings': '设置',
        }
        
        while self.running:
            with self.data_lock:
                data_copy = dict(self.server_data)

            with self.display_lock:
                self.clear_screen()
                
                page_title = page_title_map.get(self.current_page, "未知")
                self.print_header(page_title)
                
                if self.current_page == 'main':
                    self.display_main_menu(data_copy)
                elif self.current_page == 'system':
                    self.display_system_info(data_copy)
                elif self.current_page == 'gpu':
                    self.display_gpu_info(data_copy)
                elif self.current_page == 'processes':
                    self.display_processes_info(data_copy)
                elif self.current_page == 'storage':
                    self.display_storage_info(data_copy)
                elif self.current_page == 'settings':
                    self.display_settings(data_copy)
                
                # 【已修改】Req 2: 传递当前页面以高亮 / [Modified] Req 2: pass the current page for highlighting
                self.print_footer(self.current_page)
            
            time.sleep(1) 

    def _input_loop(self):
        """(主线程) 负责监听键盘输入
        (Main thread) Listen for keyboard input"""
        while self.running:
            try:
                key = get_key() 
                
                if key:
                    if key == 'q' or key == '\x03': 
                        self.status_message = "正在退出..."
                        self.running = False
                        break
                    
                    elif key == 'r':
                        # 【已修改】Req 4: 修改状态消息 / [Modified] Req 4: update the status message
                        self.status_message = "正在重新连接所有 Agent..."
                        threading.Thread(target=self.update_all_data).start()
                    
                    elif key == 'm':
                        self.current_page = 'main'
                        self.status_message = "已切换到 [首页]"
                    
                    elif key == 's':
                        self.current_page = 'system'
                        self.status_message = "已切换到 [系统]"
                    
                    elif key == 'g':
                        self.current_page = 'gpu'
                        self.status_message = "已切换到 [显卡]"

                    elif key == 'p':
                        self.current_page = 'processes'
                        self.status_message = "已切换到 [进程]"
                        
                    elif key == 'd':
                        self.current_page = 'storage'
                        self.status_message = "已切换到 [存储]"
                        
                    elif key == 'e':
                        self.current_page = 'settings'
                        self.status_message = "已切换到 [设置]"
                
                time.sleep(0.05) 
                
            except KeyboardInterrupt:
                self.status_message = "收到 Ctrl+C，正在退出..."
                self.running = False
            
    def start(self):
        """启动监控
        Start the monitor"""
        setup_terminal() 
        
        try:
            print(f"{Colors.YELLOW}正在启动监控系统...{Colors.END}")
            print(f"{Colors.GRAY}正在获取初始数据...{Colors.END}")
            
            self.update_all_data()
            
            self.data_thread = threading.Thread(target=self._data_fetch_loop)
            self.data_thread.daemon = True 
            self.data_thread.start()
            
            self.display_thread = threading.Thread(target=self._display_loop)
            self.display_thread.daemon = True
            self.display_thread.start()
            
            self._input_loop()

        finally:
            self.running = False
            cleanup_terminal() 
            self.clear_screen()
            print(f"{Colors.GREEN}监控已停止。{Colors.END}")
            if self.data_thread: self.data_thread.join(timeout=0.5)
            if self.display_thread: self.display_thread.join(timeout=0.5)

# --- 入口 / Entry point ---
def main():
    monitor = CLIMonitor()
    monitor.start()

if __name__ == '__main__':
    main()