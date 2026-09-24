// 文件名 / File: ~/code/monitor_dashboard/static/app.js (v3 - 状态化和可折叠 / stateful & collapsible)

const API_URL = '/api/data';
const REFRESH_INTERVAL = 2000; // 刷新间隔 (毫秒) / Refresh interval (ms)

// --- DOM 元素 / DOM elements ---
const mainContainer = document.getElementById('dashboard-container');
const lastUpdated = document.getElementById('last-updated');

// --- 辅助函数 (无变化) / Helper functions (unchanged) ---
function getProgressColor(percent) {
    if (percent >= 85) return 'danger';
    if (percent >= 60) return 'warn';
    return 'normal';
}

function createProgressBar(percent) {
    const p = Math.max(0, Math.min(100, Math.round(percent)));
    const colorClass = getProgressColor(p);
    return `
        <div class="progress-bar-container">
            <div class="progress-bar-fill ${colorClass}" style="width: ${p}%;">
                ${p > 10 ? p + '%' : ''}
            </div>
        </div>
    `;
}

// --- [新] 核心逻辑：创建卡片“骨架” / [New] Core logic: build the card "skeleton" ---
// 此函数只在页面加载时运行一次 / This function runs only once on page load
function createServerCardSkeleton(serverName) {
    
    // *** 这是您要求的默认状态 / *** This is the requested default state ***
    const networkClass = ''; // 默认展开 / Expanded by default
    const gpuClass = '';     // 默认展开 / Expanded by default
    const diskClass = 'collapsed'; // 默认折叠 / Collapsed by default

    // 我们使用 'data-hook' 属性作为“锚点”，以便稍后找到这些元素进行更新 / We use the 'data-hook' attribute as an "anchor" to locate these elements for later updates
    return `
    <div class="server-card" id="card-${serverName}">
        <div class="server-card-header">
            <span class="server-name">${serverName}</span>
            <span class="status-badge" data-hook="status">● ...</span>
        </div>
        
        <div class="metrics-grid">
            <div class="metric-item">
                <h4 data-hook="cpu-label">CPU (...)</h4>
                <div class="metric-value" data-hook="cpu-percent">...%</div>
                <div data-hook="cpu-progress">${createProgressBar(0)}</div>
            </div>
            <div class="metric-item">
                <h4>内存 (RAM)</h4>
                <div class="metric-value" data-hook="ram-label">... / ... GB</div>
                <div data-hook="ram-progress">${createProgressBar(0)}</div>
            </div>
        </div>

        <div class="collapsible-section ${networkClass}">
            <div class="section-header">
                <h3>网络</h3>
                <span class="toggle-icon">▼</span>
            </div>
            <div class="section-content" data-hook="network-content">
                </div>
        </div>

        <div class="collapsible-section ${gpuClass}">
            <div class="section-header">
                <h3>GPUs</h3>
                <span class="toggle-icon">▼</span>
            </div>
            <div class="section-content" data-hook="gpu-content">
                </div>
        </div>

        <div class="collapsible-section ${diskClass}">
            <div class="section-header">
                <h3>存储</h3>
                <span class="toggle-icon">▼</span>
            </div>
            <div class="section-content" data-hook="disk-content">
                </div>
        </div>
        
        <div class="system-section" data-hook="system-content">
            </div>
    </div>
    `;
}

// --- [新] 核心逻辑：更新卡片内容 / [New] Core logic: update card content ---
// 此函数在每次刷新时运行 / This function runs on every refresh
function updateServerCard(serverName, serverInfo) {
    const card = document.getElementById(`card-${serverName}`);
    if (!card) return; // 如果卡片不存在，跳过 / Skip if the card does not exist

    const statusBadge = card.querySelector('[data-hook="status"]');

    // --- 状态 1: 离线 / State 1: offline ---
    if (serverInfo.status === 'offline') {
        card.classList.add('offline');
        statusBadge.textContent = '离线';
        statusBadge.className = 'status-badge offline';
        // 隐藏所有数据区域 / Hide all data sections
        card.querySelectorAll('.metrics-grid, .collapsible-section, .system-section').forEach(el => el.style.display = 'none');
        return;
    }

    // --- 状态 2: 在线 / State 2: online ---
    card.classList.remove('offline');
    statusBadge.textContent = '在线';
    statusBadge.className = 'status-badge online';
    // 确保所有数据区域可见 / Ensure all data sections are visible
    card.querySelectorAll('.metrics-grid, .collapsible-section, .system-section').forEach(el => el.style.display = '');

    const metrics = serverInfo.data || {};

    // --- 更新 CPU/RAM / Update CPU/RAM ---
    const cpu = metrics.cpu || {};
    const ram = metrics.memory || {};
    card.querySelector('[data-hook="cpu-label"]').textContent = `CPU (${cpu.physical_cores || '?'}核 / ${cpu.logical_cores || '?'}线程)`;
    card.querySelector('[data-hook="cpu-percent"]').textContent = `${(cpu.percent || 0).toFixed(1)}%`;
    card.querySelector('[data-hook="cpu-progress"]').innerHTML = createProgressBar(cpu.percent || 0);
    card.querySelector('[data-hook="ram-label"]').textContent = `${(ram.used_gb || 0).toFixed(1)} / ${(ram.total_gb || 0).toFixed(1)} GB`;
    card.querySelector('[data-hook="ram-progress"]').innerHTML = createProgressBar(ram.percent || 0);

    // --- 更新 网络 (重建内部) / Update network (rebuild contents) ---
    const network = metrics.network || {};
    card.querySelector('[data-hook="network-content"]').innerHTML = `
        <div class="network-grid">
            <div class="network-item"><span>⬇️ 接收</span><strong>${(network.recv_mbps || 0).toFixed(2)} Mb/s</strong></div>
            <div class="network-item"><span>⬆️ 发送</span><strong>${(network.send_mbps || 0).toFixed(2)} Mb/s</strong></div>
            <div class="network-item"><span>⬇️ 总计</span><strong>${(network.total_recv_gb || 0).toFixed(1)} GB</strong></div>
            <div class="network-item"><span>⬆️ 总计</span><strong>${(network.total_sent_gb || 0).toFixed(1)} GB</strong></div>
        </div>`;

    // --- 更新 GPUs (重建内部) / Update GPUs (rebuild contents) ---
    const gpus = metrics.gpus || [];
    const gpuContainer = card.querySelector('[data-hook="gpu-content"]');
    if (gpus.length > 0) {
        gpuContainer.innerHTML = gpus.map(gpu => {
            // --- [新增] 生成进程列表 HTML / [Added] Build process list HTML ---
            let processesHtml = '';
            if (gpu.processes && gpu.processes.length > 0) {
                const procList = gpu.processes.map(p => {
                    // 格式化时间 / Format the time
                    let timeStr = '未知';
                    if (p.create_time && p.create_time !== 'unknown') {
                        const date = new Date(p.create_time);
                        // 提取格式类似: 4/22 01:33 / Produce a format like: 4/22 01:33
                        timeStr = `${date.getMonth() + 1}/${date.getDate()} ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
                    }
                    
                    return `
                        <div class="process-item">
                            <div class="proc-header">
                                <span class="proc-pid">PID: ${p.pid}</span>
                                <span class="proc-mem">${Math.round(p.gpu_memory_usage_mb)} MB</span>
                            </div>
                            <div class="proc-cwd" title="${p.cwd}">📁 ${p.cwd}</div>
                            <div class="proc-time">🕒 启动于: ${timeStr}</div>
                        </div>
                    `;
                }).join('');

                processesHtml = `
                    <div class="gpu-processes">
                        <div class="process-title">活跃进程 (${gpu.processes.length}):</div>
                        ${procList}
                    </div>
                `;
            }

            // 返回单个 GPU 的完整 HTML / Return the full HTML for a single GPU
            return `
                <div class="gpu-item">
                    <div class="gpu-name">[${gpu.index}] ${gpu.name}</div>
                    <div class="gpu-stats">
                        <span>负载: <strong>${gpu.utilization || 0}%</strong></span>
                        <span>温度: <strong>${gpu.temperature || 0}°C</strong></span>
                        <span>功耗: <strong>${gpu.power_draw || 0}W / ${gpu.power_limit || 0}W</strong></span>
                    </div>
                    <div class="gpu-mem">
                        <span class="sub-text">显存: ${gpu.memory_used.toFixed(0)} / ${gpu.memory_total.toFixed(0)} MB</span>
                        ${createProgressBar(gpu.memory_percent || 0)}
                    </div>
                    <div class="gpu-power" style="display: none;">
                        <span class="sub-text">功耗: ${gpu.power_percent.toFixed(1)}%</span>
                        ${createProgressBar(gpu.power_percent || 0)}
                    </div>
                    ${processesHtml} </div>
            `;
        }).join('');
    } else {
        gpuContainer.innerHTML = `<div class="sub-text">未检测到 GPU</div>`;
    }
    
    // --- 更新 存储 (重建内部) / Update storage (rebuild contents) ---
    const disks = metrics.disks || [];
    const diskContainer = card.querySelector('[data-hook="disk-content"]');
    if (disks.length > 0) {
        diskContainer.innerHTML = disks.map(disk => `
            <div class="disk-item">
                <div class="disk-name">${disk.mountpoint} (${disk.fstype || 'N/A'})</div>
                <span class="sub-text">${disk.used_gb.toFixed(1)} / ${disk.total_gb.toFixed(1)} GB</span>
                ${createProgressBar(disk.percent)}
            </div>
        `).join('');
    } else {
        diskContainer.innerHTML = `<div class="sub-text">未检测到存储</div>`;
    }

    // --- 更新 系统信息 / Update system info ---
    const system = metrics.system || {};
    card.querySelector('[data-hook="system-content"]').innerHTML = `
        <div class="system-item"><strong>系统:</strong> ${system.platform || 'N/A'}</div>
        <div class="system-item"><strong>已运行:</strong> ${system.uptime_str || 'N/A'}</div>
    `;
}

/**
 * [新] 更新所有卡片的数据 / [New] Update the data of all cards
 */
function updateAllCards(data) {
    for (const serverName in data) {
        if (document.getElementById(`card-${serverName}`)) {
            updateServerCard(serverName, data[serverName]);
        }
    }
}

/**
 * [新] 主数据循环 / [New] Main data loop
 */
async function fetchAndUpdateLoop() {
    try {
        const response = await fetch(API_URL);
        if (!response.ok) {
            throw new Error(`API 请求失败: ${response.status}`);
        }
        const data = await response.json();
        
        // 成功获取数据，调用渲染函数
        updateAllCards(data);
        lastUpdated.textContent = `最后更新: ${new Date().toLocaleTimeString()}`;
        
    } catch (error) {
        console.error('获取或渲染数据失败:', error);
        lastUpdated.textContent = `更新失败: ${error.message}`;
    }
}

/**
 * [新] 页面初始化函数 / [New] Page initialization function
 */
async function init() {
    lastUpdated.textContent = '正在加载...';
    try {
        // 1. 首次获取数据以确定服务器列表 / 1. Fetch data once to determine the server list
        const response = await fetch(API_URL);
        if (!response.ok) throw new Error(`API 失败: ${response.status}`);
        const data = await response.json();

        // 2. 创建卡片骨架 / 2. Create the card skeletons
        const serverNames = Object.keys(data).sort();
        mainContainer.innerHTML = ''; // 清空 '加载中...' / Clear the 'loading...' placeholder
        for (const serverName of serverNames) {
            mainContainer.insertAdjacentHTML('beforeend', createServerCardSkeleton(serverName));
        }
        
        // 3. 立即用数据填充骨架 / 3. Immediately populate the skeletons with data
        updateAllCards(data);
        lastUpdated.textContent = `最后更新: ${new Date().toLocaleTimeString()}`;

        // 4. [新] 添加折叠点击事件监听器 / 4. [New] Add collapse click event listener
        // 我们只在父容器上添加 *一个* 监听器 (事件委托) / We add only *one* listener on the parent container (event delegation)
        mainContainer.addEventListener('click', (e) => {
            const header = e.target.closest('.section-header');
            if (header) {
                const section = header.closest('.collapsible-section');
                if (section) {
                    section.classList.toggle('collapsed');
                }
            }
        });

        // 5. 启动定时刷新循环 / 5. Start the periodic refresh loop
        setInterval(fetchAndUpdateLoop, REFRESH_INTERVAL);

    } catch (error) {
        console.error('初始化失败:', error);
        mainContainer.innerHTML = `
            <div class="server-card offline" style="grid-column: 1 / -1;">
                <div class="offline-message">
                    <strong>错误: 无法连接到仪表盘后端。</strong>
                    <br>(${error})
                </div>
            </div>
        `;
    }
}

// --- 启动应用 / Start the app ---
init();