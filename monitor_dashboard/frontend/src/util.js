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
