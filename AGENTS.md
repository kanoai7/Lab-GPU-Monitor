# 实验室 GPU 集群监控项目 (Lab GPU Monitor)

> 本文件是项目的初始化说明与协作约定（"init"）。记录**项目核心要求**、**架构现状**与**后续改进建议**。
> 每轮工作开始前先读本文件，结束后按需更新。

---

## 一、项目概述

自建实验室 GPU 服务器集群监控系统，用于实时查看多台服务器的 GPU / CPU / 内存 / 磁盘 / 网络 / 进程状态。
采用 **Agent（被监控端） + 采集展示端（CLI / Web 仪表盘）** 的分离架构。

## 二、架构现状（截至 git 初始化时，未做任何代码修改）

### 1. `monitor-serve/` — 监控 Agent（部署在每台被监控服务器上）
- `monitor.py`：Flask 服务，暴露 `GET /metrics`，监听 `0.0.0.0:9527`。
  - 采集：GPU（`pynvml`）、CPU/内存/磁盘/网络（`psutil`）、系统信息。
  - GPU 进程带缓存，忽略显存 < 20MB 的进程；退出时 `nvmlShutdown()`。
  - 依赖：`flask`、`pynvml`、`psutil`。当前 `app.run(debug=True)`。
- `gpu_monitor.service`：Linux systemd 部署单元（指向 conda/pip 环境的 python，`Restart=always`）。

### 2. `monitor_cli_client/` — Windows CLI 客户端
- `main_v4.py`：并发轮询多台 Agent，终端分页展示（首页/系统/GPU/进程/存储/设置）。
  - 键盘导航（M/S/G/P/D/E/R/Q），跨平台按键监听（Windows `msvcrt` / *nix `termios`）。
  - 使用 PyInstaller 打包为 exe。
  - Agent 列表按**主机名**配置（`4ka3090` / `2ka3090` / `olda800` / `newa800`）。

### 3. `monitor_dashboard/` — Web 仪表盘（中央展示，v2.0 已重做为 SPA + 历史）
- `dashboard.py`：后台线程并发轮询所有 Agent（`update_data_loop`），Flask + waitress 提供 API 与 SPA，监听 `0.0.0.0:48080`。
  - Agent 列表 / 轮询间隔 / 告警 / 展示 / 历史保留 / 鉴权均走运行时 `config.json`（含 `secret_key`/`password_hash`，**勿提交**），设置页热改。
  - 鉴权：单一共享密码（werkzeug 哈希 + 签名会话），`login_required`（页面跳登录、`/api/*` 返回 401）。
  - API：`/api/data`（实时快照）、`/api/history?host=&range=1h|6h|24h|7d`（时序）、`/api/config`（读写，白名单）、`/api/health`。
  - `/`、`/settings`、`/host/<name>` 返回已构建的 SPA 壳（`static/dist/index.html`）；`/login`、`/logout` 仍服务端渲染。
  - **提交时 `debug=False`（waitress 优先）**。
- `history.py`：SQLite 历史存储，**当有界缓存用**（WAL；`res=0` 原始，`res=60` 1 分钟均值）。后台线程把超过 `retain_raw_hours` 的原始样本降采样、删除超过 `retain_rollup_days` 的数据，体积有上限。运行时产物 `history.db*` 勿提交。
- `frontend/`：**Vue 3 + Vite** 工程（Vue Router + Apache ECharts via `vue-echarts`，手写 CSS 主题，未用组件库）。`src/` 下 `views/`（Overview/Host/Settings）+ `components/`（HostCard/MetricChart/GpuPanel/ProcTable）。`node_modules/` 勿提交。
  - 总览：主机卡片墙 + sparkline + 文本筛选 / 只看空闲卡；点击进主机详情。
  - 主机详情：时间范围选择 + ECharts 多折线（CPU / 内存 / 网络 / 磁盘 IO / 各 GPU util·显存·温度·功耗）+ 实时 GPU 块与进程表（cwd 原样，见 [[proc-cwd-identity]]）。
- `static/dist/`：`npm run build` 产物，**随仓库提交**（部署端只需 pip + 运行 `dashboard.py`，无需 node；仅改前端才需 `cd frontend && npm i && npm run build`）。
- `static/style.css`：仅登录页（`login.html`）使用。

## 三、核心要求 / 协作约定（必须遵守）

1. **分步进行**：一步一步来，每轮任务范围明确。
2. **严格按指令行事**，不擅自扩大改动范围；目录树注释仅为改进建议，不在被指定前实现。
3. **每轮修改后必须检查与调试代码**（`py_compile` 语法检查 / 尽可能运行验证）。
4. **Dashboard 的 debug 模式规则**：
   - **要提交（commit）时** → 关闭：`app.run(..., debug=False)`。
   - **不提交 / 或提交完成后** → 开启：`app.run(..., debug=True)`，便于本地检查效果。
5. **Git**：已 `git init`（分支 `master`），**当前不提交**，待后续指令。
6. 涉及不可逆或对外操作前先确认。
7. **面向新手、简化优先**：部署、搭建、使用的全流程尽可能简化，方便新手操作。
   - CLI 打包为**双击即用**的 exe / 二进制，不依赖命令行启动项。
   - 所有配置走**应用内设置页 + 配置文件**持久化；命令行参数仅作可选的高级覆盖，绝不作为必需路径。
   - 版本 / 关于等信息在**应用内**展示。
8. 所有的cli回复必须用中文。

## 四、后续改进建议（Backlog — 非当前任务，源自目录注释与通读观察）

### monitor-serve
- [ ] 探讨"不依赖 Python"的分发方式（打包为独立二进制，或用 Go/Rust 重写 Agent）。
- [ ] **WSGI 服务化**：用 `waitress` 替代 `app.run`，且必须**单进程多线程**（waitress 默认即是；勿用 gunicorn 多 worker）——agent 持有跨请求的全局状态（网速差值 `last_net_stats`、PID 缓存、`nvml_initialized`），多进程会各算各的、导致网速错乱。`app.run(debug=True)` 仅本地调试用。
- [ ] **后台采样快照**：起后台线程每 N 秒采集一次并存为 `latest_snapshot`，`/metrics` 只返回快照。收益：采集成本与客户端轮询频率解耦、CPU 封顶；网速差值由单一采样线程独占计算，**修复多客户端（dashboard + CLI 同时轮询）时的网速错乱**。代价：数据最多 N 秒陈旧 + 一个后台线程。
- [ ] **扩展监控内容**（不增加资源占用为前提，尽量在现有 `pynvml` / `psutil` / `platform` 内；多发出来，客户端按需展示）：
  - GPU 进程：**属主用户名** `Process.username()`、**进程名/命令行** `.name()` / `.cmdline()`（可进 PID 缓存，零额外每次开销）；可选（依赖较新驱动/成本略高）：每进程 GPU 利用率 `nvmlDeviceGetProcessUtilization`、风扇转速、核心/显存频率、降频原因、ECC 错误、显存/热点温度。
  - CPU：per-core 利用率 `cpu_percent(percpu=True)`、负载均值 `os.getloadavg()`（Linux）、频率 `cpu_freq()`。
  - 内存：swap `swap_memory()`、`available` 可用量。
  - 磁盘：读写速率 `disk_io_counters()`。
  - 网络：分网卡 `net_io_counters(pernic=True)`、错误/丢包 `errin/errout/dropin/dropout`、连接数。
  - 系统：主机名、登录用户 `users()`、CPU/主板温度 `sensors_temperatures()`（Linux）。
- [ ] **部署与分发**：主力 **systemd + venv**（比 conda 链路更轻）；免环境分发用 **PyInstaller onefile**（单二进制 + unit 文件，需按目标机架构/glibc 分别打包）。Docker 不适合本 agent——读宿主机进程属主/cwd 需 `--pid=host` 提权，反而破坏隔离。
- [ ] 代码小问题：`__main__` 内重复 `import datetime`（模块顶部已 import）。

### monitor_cli_client（本轮讨论确定的升级方向）

**定位**：个人 / 即开即用 / 终端原生的"快速查看端"；dashboard 为共享中央端。不限 Windows——`msvcrt`(Win) / `termios`(*nix) 已分开，Linux 终端可直接运行或打包为 Linux 二进制。

**配置方案（跨平台、双击即用一键启动，命令行参数仅作可选覆盖）**：
- 主路径：双击启动 → **应用内可写设置页** → 持久化到 `config.json`（当前设置页为只读，需改造）。
- 默认「便携模式」：`config.json` 放在 exe / 二进制**同目录**；定位逻辑跨平台一致——冻结态 `getattr(sys, 'frozen', False)` 用 `os.path.dirname(sys.executable)`，否则用脚本目录；首次运行从内置默认拷出生成。
- 回退「每用户目录」（仅当同目录不可写）：Windows `%APPDATA%\LabGpuMonitor\`；Linux `$XDG_CONFIG_HOME` 或 `~/.config/lab-gpu-monitor/`；可用 `platformdirs` 自动定位。
- 版本 / 关于在**应用内**展示；`--version` / `--once` / `--agents` 等仅作可选高级 flag，不挡新手双击流程。
- 待定（后续测试落实）：agent 列表编辑用「首次运行向导」还是设置页「打开配置文件」，或两者都做。

**功能升级项（后续具体测试落实，按优先级）**：
- [ ] 可写设置页：agent 列表、刷新间隔、阈值、主题等可改并持久化（替换当前只读设置页）。
- [ ] TUI 框架化：用 `rich` / `textual` 取代手写 ANSI + 全屏 clear，实现无闪烁局部刷新、表格、resize、滚动。
- [ ] 空闲卡查找：按空闲显存排序的"可用 GPU"视图（实验室高频需求）。
- [ ] 排序 / 过滤 / 搜索：按 util / 显存 / 温度排序，按用户名过滤，搜 PID / 用户。
- [ ] 健壮性：每 agent 独立超时 + 重试退避，单台掉线不拖垮整轮；显式展示在线 / 离线 + 延迟 + 最后更新时间。
- [ ] 阈值告警 / watch 模式：温度、显存超限高亮或响铃；"占卡空转"提醒。
- [ ] 迷你趋势图：内存环形缓冲 + sparkline（util / 温度近 N 采样），无需数据库。
- [ ] 非交互模式：`--once` 打印一次即退出；导出当前视图为 JSON / CSV。
- [ ] 共享配置源：agent 列表与 dashboard / agent 统一（见"全局"）。
- [ ] 杂项：`--version`、配色 / 色盲友好主题、agent 若加鉴权则支持 token。

### monitor_dashboard（本轮讨论确定的升级方向）

> ⚠️ **已被 v2.0 推翻（2026-09-26）**：下方"零构建 / 不引 DB / 纯手写 CSS"的方向在 v2.0 完全重做时作废——改为 **Vue 3 + Vite 构建 + ECharts 多折线 + SQLite 历史缓存**（见"二、3"现状）。保留本段仅作决策留痕。鉴权 / 有状态化 / 移动适配 / 完整设置页等目标仍成立，已在 v2.0 中实现。

**整体风格**：改为国外简约 **SaaS 风**（大量留白、克制配色、单一强调色、细边框替代重卡片、系统字体栈 / Inter）。实现坚持**零构建**：精修手写 CSS，不引 JS 框架 / 打包工具链，保持纯 Flask + 静态文件。明 / 暗两套主题、**整站统一**由设置页选择（默认暗色，沿用现状 + 监控护眼；可切浅色 SaaS 基调）。

**有状态化**：dashboard 从"只读展示"升级为"有状态服务"——服务端持久化一份 `config.json`（不引 DB）。设置页 → `POST /api/config`（需登录）→ 校验 → 写 `config.json` → 后台轮询线程热加载 + 前端刷新。配置 schema 尽量与 CLI 共用（见全局"共享配置源"）。

**完整设置页（分区，常见 SaaS 布局：左侧导航 / 顶部标签）**：
- **通用**：站点名称（替换硬编码标题 / `lab-code`）、时区、语言（zh / en，可选）。
- **监控源（Agents）**：agent 列表增 / 删 / 改（名称 + 主机 + 端口 + 启用开关）、后台轮询间隔、单 agent 超时；保存后热加载轮询目标。
- **外观（整站统一，服务端全局）**：主题（明 / 暗）、强调色、背景（纯色 / 图片：URL 或上传）、信息密度（紧凑 / 舒适，可选）。
- **展示**：显示哪些面板 / 列（GPU / CPU / 内存 / 磁盘 / 网络 / 进程）、默认排序（util / 显存 / 温度）、进程详情（用户 / cwd / 命令行）开关、前端 UI 刷新频率（独立于后台轮询）。
- **告警（可选，先做视觉）**：GPU 温度 / 显存占用等阈值超限高亮。
- **安全**：鉴权开关、修改共享密码、会话时长。
- **关于**：版本、各 agent 在线 / 离线 + 延迟 + 最后更新时间。

**鉴权（单一共享密码，档 2）**：
- 登录页：密码 → `POST /login` → 校验存储的**密码哈希**（用 Flask 自带 werkzeug 的 `generate_password_hash` / `check_password_hash`，无需新依赖）→ 签名会话 cookie → 跳转。
- 除 `/login` 外所有路由（`/`、`/api/data`、`/api/config`）需有效会话。
- 配置项 `auth_enabled`（可关，纯内网 / 新手模式）；首次运行引导设置密码（或内置默认密码 + 强制修改）。
- `SECRET_KEY` 首次运行自动生成并持久化（签 cookie 用）。
- **单密码的局限**：无"只读 / 管理"之分——凡登录者皆可改配置。如需查看 / 管理分权，需双密码或账号体系（超出本轮范围，记为后续可选）。
- **两层鉴权说明**：本轮登录只保护 dashboard 聚合视图；**agent 的 `/metrics` 仍敞开**，假定其处于可信内网。agent 侧 token 鉴权仍属全局 backlog（`/metrics` 无鉴权那条）。

**新手友好**：首次运行引导（设密码 + 填 agent 列表）；全程网页内可配，无需改代码 / 命令行。

**移动设备适配**：响应式布局，手机 / 平板可正常查看与操作——单列堆叠、可触控的折叠区块、够大的点按目标、表格横向滚动或转卡片式；设置页在窄屏下同样可用。坚持零构建（纯 CSS 媒体查询 + 弹性布局，不引框架）。

### 全局
- [ ] 三端共用一份 Agent 列表 / 配置源，避免多处硬编码。
- [ ] `/metrics`、`/api/data` 无鉴权，若需对外暴露应加访问控制。
- [ ] **适用规模边界**：面向单机 ~ 低几十台的小实验室；更大规模转向 push 模式或专业方案（NVIDIA **DCGM-Exporter + Prometheus + Grafana**）。定位：零基础设施、单文件、不落盘的轻量替代。
