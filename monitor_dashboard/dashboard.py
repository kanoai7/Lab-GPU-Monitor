# 文件名: ~/code/monitor_dashboard/dashboard.py / File: ~/code/monitor_dashboard/dashboard.py
#
#
#
#
# 这是中央仪表盘服务器。 / This is the central dashboard server.
# 它在后台轮询所有 Agent，并通过 DASHBOARD_PORT 端口提供一个 Web 界面和 API。 / It polls all Agents in the background and serves a web UI and API on the DASHBOARD_PORT port.
#
#
#

import time
import threading
import requests
from flask import Flask, jsonify, render_template
from concurrent.futures import ThreadPoolExecutor

# --- 配置 --- / --- Configuration ---

# 1. Agent 列表 (Agent 运行在占位主机上) / 1. Agent list (Agents run on placeholder hosts)
SERVER_AGENTS = {
    "server-01": {"url": "http://<agent-01-host>:48210/metrics"},
    "server-02": {"url": "http://<agent-02-host>:48210/metrics"},
    "server-03": {"url": "http://<agent-03-host>:48210/metrics"},
    "server-04": {"url": "http://<agent-04-host>:48210/metrics"},
}

# 2. 仪表盘设置 / 2. Dashboard settings
DASHBOARD_PORT = 48080  # Web 仪表盘的访问端口 / Access port for the web dashboard
POLL_INTERVAL = 1      # 几秒钟轮询一次 Agent / How many seconds between Agent polls

# --- 全局变量 --- / --- Global variables ---

# 这个字典将存储从所有 Agent 获取的最新数据 / This dict stores the latest data fetched from all Agents
# 我们使用一个锁来确保线程安全 / We use a lock to ensure thread safety
global_data_store = {}
data_lock = threading.Lock()


# --- 后台数据抓取 --- / --- Background data fetching ---

def fetch_single_agent(server_name, url):
    """
    抓取单个 Agent 的数据。
    Fetch data from a single Agent.
    返回一个标准化的结果，无论成功还是失败。
    Return a normalized result whether it succeeds or fails.
    """
    try:
        # 超时应小于 POLL_INTERVAL / Timeout should be less than POLL_INTERVAL
        response = requests.get(url, timeout=1.5)
        response.raise_for_status() # 确保是 200 OK / Ensure it is 200 OK

        # 成功: 返回状态和 Agent 提供的完整数据 / Success: return status and the full data provided by the Agent
        return server_name, {"status": "online", "data": response.json()}

    except requests.exceptions.RequestException as e:
        # 失败: 返回 'offline' 状态和一个空数据体 / Failure: return 'offline' status and an empty data body
        print(f"[Warn] 无法连接到 Agent {server_name}: {e}")
        return server_name, {"status": "offline", "data": {}}

def update_data_loop():
    """
    一个在后台线程中永久运行的循环。
    A loop that runs forever in a background thread.
    它使用线程池并发地抓取所有 Agent。
    It uses a thread pool to fetch all Agents concurrently.
    """
    # 创建一个与 Agent 数量匹配的线程池 / Create a thread pool matching the number of Agents
    with ThreadPoolExecutor(max_workers=len(SERVER_AGENTS)) as executor:
        while True:
            start_time = time.time()

            # 提交所有并发任务 / Submit all concurrent tasks
            futures = []
            for name, config in SERVER_AGENTS.items():
                futures.append(executor.submit(fetch_single_agent, name, config['url']))

            # 收集结果 / Collect the results
            temp_data_store = {}
            for future in futures:
                try:
                    server_name, result = future.result()
                    temp_data_store[server_name] = result
                except Exception as e:
                    # 捕获 `fetch_single_agent` 本身的异常 (虽然不应发生) / Catch exceptions from `fetch_single_agent` itself (though it should not happen)
                    print(f"[Error] 抓取线程池异常: {e}")

            # 用获取的新数据，线程安全地更新全局变量 / Update the global variable in a thread-safe way with the newly fetched data
            with data_lock:
                global global_data_store
                global_data_store = temp_data_store

            # 确保循环至少花费 POLL_INTERVAL 秒 / Ensure each loop takes at least POLL_INTERVAL seconds
            time_spent = time.time() - start_time
            if time_spent < POLL_INTERVAL:
                time.sleep(POLL_INTERVAL - time_spent)


# --- Flask Web 应用 --- / --- Flask web application ---

# 初始化 Flask 应用 / Initialize the Flask application
app = Flask(__name__)

@app.route('/')
def get_index_page():
    """
    提供 Web 界面 (index.html)。
    Serve the web UI (index.html).
    Flask 会自动在 'templates' 文件夹中查找此文件。
    Flask automatically looks for this file in the 'templates' folder.
    """
    return render_template('index.html')

@app.route('/api/data')
def get_api_data():
    """
    提供 API 端点。
    Serve the API endpoint.
    前端 JavaScript 将调用此 API 来获取要显示的数据。
    The frontend JavaScript calls this API to get the data to display.
    """
    # 线程安全地读取全局数据 / Read the global data in a thread-safe way
    with data_lock:
        # 返回全局数据存储的 *副本* / Return a *copy* of the global data store
        return jsonify(dict(global_data_store))

if __name__ == '__main__':
    print("启动后台数据抓取线程...")
    # 将 update_data_loop 作为一个守护线程启动 / Start update_data_loop as a daemon thread
    # 'daemon=True' 意味着当主程序退出时，该线程也会自动退出 / 'daemon=True' means the thread exits automatically when the main program exits
    data_thread = threading.Thread(target=update_data_loop, daemon=True)
    data_thread.start()

    print(f"Flask 仪表盘启动，监听 http://0.0.0.0:{DASHBOARD_PORT}")

    # 启动 Web 服务器 / Start the web server
    # 警告: app.run() 仅用于开发。 / Warning: app.run() is for development only.
    # 对于生产环境, 请使用 Gunicorn 或 Waitress。 / For production, use Gunicorn or Waitress.
    # pip install waitress
    # from waitress import serve
    # serve(app, host='0.0.0.0', port=DASHBOARD_PORT)

    app.run(host='0.0.0.0', port=DASHBOARD_PORT, debug=False)