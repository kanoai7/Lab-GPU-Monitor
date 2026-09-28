// 展示辅助：数值格式化、阈值分级、空闲卡判定、sparkline。 / Display helpers.

export function num(v, d = 1) {
  return (typeof v === 'number' && isFinite(v)) ? v.toFixed(d) : '—'
}
export function int(v) {
  return (typeof v === 'number' && isFinite(v)) ? Math.round(v) : '—'
}
export function pct(v) {
  return (typeof v === 'number' && isFinite(v)) ? Math.max(0, Math.min(100, v)) : 0
}

// 阈值分级：>=crit 危, >=warn 警, 否则正常。 / Threshold level.
export function level(v, warn, crit) {
  if (typeof v !== 'number' || !isFinite(v)) return ''
  if (v >= crit) return 'crit'
  if (v >= warn) return 'warn'
  return 'ok'
}

// 阈值对应的 CSS 颜色变量（纯严重度：绿/黄/红）。 / Threshold -> severity color var.
export function lvlColor(v, warn, crit) {
  const l = level(v, warn, crit)
  return l === 'crit' ? 'var(--crit)' : l === 'warn' ? 'var(--warn)' : l === 'ok' ? 'var(--ok)' : 'var(--muted)'
}

// 指标着色：正常区间用该指标的专属底色 base（CPU/内存/显存/GPU… 各不相同），
// 仅当越过 warn/crit 才升级为琥珀/红。这样颜色同时表达「是什么指标」与「热不热」，而非整页同色。
// Metric coloring: normal range uses the metric's own base hue; only warn/crit escalate to amber/red.
export function metricColor(v, warn, crit, base) {
  if (typeof v === 'number' && isFinite(v) && warn != null && crit != null) {
    if (v >= crit) return 'var(--crit)'
    if (v >= warn) return 'var(--warn)'
  }
  return base || 'var(--accent)'
}

// 读取 CSS 变量当前值（供 ECharts 等需要具体色值处使用）。 / Read a live CSS var value.
export function cssVar(name, fallback = '') {
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
    return v || fallback
  } catch (e) { return fallback }
}

// 负载归一化为占核百分比（load1 / 逻辑核数 * 100）。 / Normalize load to % of cores.
export function loadPct(load1, cores) {
  if (typeof load1 !== 'number' || typeof cores !== 'number' || cores <= 0) return null
  return (load1 / cores) * 100
}

// 空闲卡：利用率 <=5% 且至少一半显存空闲。 / Free GPU: util<=5% and >=half VRAM free.
export function isFree(g) {
  const util = g.utilization
  const memPct = g.memory_percent
  if (typeof util !== 'number' || util > 5) return false
  if (typeof memPct === 'number' && memPct > 50) return false
  return true
}

const SPARK = '▁▂▃▄▅▆▇█'
export function spark(arr) {
  if (!arr || !arr.length) return ''
  const nums = arr.filter((x) => typeof x === 'number' && isFinite(x))
  if (!nums.length) return ''
  const min = Math.min(...nums), max = Math.max(...nums)
  const span = max - min || 1
  return arr.map((x) => {
    if (typeof x !== 'number' || !isFinite(x)) return ' '
    const i = Math.round(((x - min) / span) * (SPARK.length - 1))
    return SPARK[Math.max(0, Math.min(SPARK.length - 1, i))]
  }).join('')
}

export function fmtBytes(gb) {
  if (typeof gb !== 'number' || !isFinite(gb)) return '—'
  if (gb >= 1024) return (gb / 1024).toFixed(2) + ' TB'
  return gb.toFixed(1) + ' GB'
}

// GPU 显存由 agent 以 MB 上报；显示时换算成 GB。 / GPU VRAM is reported in MB by the agent; show as GB.
export function gbFromMb(mb, d = 1) {
  return (typeof mb === 'number' && isFinite(mb)) ? (mb / 1024).toFixed(d) : '—'
}

// 归一化 agent 字段：取不到权限时 agent 会填字符串 "unknown"，一律当作缺失，返回 null。
// Normalize an agent-provided string field: the agent fills "unknown" when it lacks permission; treat it (and empty) as missing.
export function cleanStr(v) {
  if (typeof v !== 'string') return null
  const s = v.trim()
  return (s && s.toLowerCase() !== 'unknown') ? s : null
}

// 进程启动时间：agent 以 ISO 字符串上报 create_time（无权限时为 "unknown"）。
// 展示为紧凑的 MM-DD HH:MM（同 agent 本地时区）；无效/缺失返回 ''。
// Process start time: agent reports create_time as an ISO string ("unknown" when denied).
// Render as compact MM-DD HH:MM (agent-local time); '' when missing/invalid.
export function fmtStart(iso) {
  const s = cleanStr(iso)
  if (!s) return ''
  const d = new Date(s)
  if (isNaN(d.getTime())) return ''
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

// 显示服务器 / 桌面进程：占少量显存但不是 GPU 工作负载，不算"谁在用卡"，从进程列表剔除。
// Display-server / desktop processes: they hold a little VRAM but aren't GPU workloads, so drop them from the process list.
const SYSTEM_PROC_NAMES = /^(xorg|xwayland|x|gnome-shell|gdm|kwin_x11|kwin_wayland|plasmashell)$/i
export function isSystemProc(p) {
  return SYSTEM_PROC_NAMES.test(String((p && p.name) || '').trim())
}
export function realGpuProcs(list) {
  return (list || []).filter((p) => !isSystemProc(p))
}
