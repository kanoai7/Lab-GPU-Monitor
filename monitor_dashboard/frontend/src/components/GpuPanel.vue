<template>
  <div class="gpu" :class="{ free: free }">
    <div class="gpu-name">
      <span><span class="idx">#{{ g.index }}</span> {{ g.name || 'GPU' }}
        <span v-if="free" class="flag free">空闲 / FREE</span>
      </span>
      <span class="head-badges">
        <span v-if="!compact" class="badge" :class="tempCls">{{ int(g.temperature) }}°C</span>
        <span v-if="!compact" class="badge">{{ int(g.power_draw) }} / {{ int(g.power_limit) }} W</span>
      </span>
    </div>

    <BarGauge :items="bars" />

    <!-- 小卡：谁在用卡（cwd 原样）/ compact: who's using it (cwd as-is) -->
    <div v-if="compact" class="gpu-cwds">
      <div v-for="(c, i) in cwds" :key="i" class="cwd-row" :title="c.full">
        <div class="cwd-meta">
          <span v-if="c.mem" class="cwd-mem mono">{{ c.mem }}</span>
          <span v-if="c.user" class="cwd-user">{{ c.user }}</span>
        </div>
        <div class="cwd-path mono">{{ c.path }}</div>
      </div>
      <div v-if="!cwds.length" class="cwd-idle">空闲 · 无进程 / idle</div>
    </div>

    <template v-if="!compact">
      <div class="gpu-chips">
        <span v-if="num0(g.fan_speed) !== null" class="badge">风扇 {{ int(g.fan_speed) }}%</span>
        <span v-if="num0(g.memory_utilization) !== null" class="badge">显存带宽 {{ int(g.memory_utilization) }}%</span>
        <span v-if="throttle" class="badge warn" :title="throttle">降频 / throttling</span>
        <span v-if="eccBad" class="badge crit">ECC {{ g.ecc_uncorrected }}</span>
      </div>

      <div class="gpu-extra">
        <span v-if="num0(g.sm_clock_mhz) !== null">核心频率 <b>{{ int(g.sm_clock_mhz) }} MHz</b></span>
        <span v-if="num0(g.mem_clock_mhz) !== null">显存频率 <b>{{ int(g.mem_clock_mhz) }} MHz</b></span>
        <span v-if="num0(g.power_percent) !== null">功耗占比 <b>{{ int(g.power_percent) }}%</b></span>
      </div>

      <ProcTable v-if="showProcs && procs.length" :procs="procs" />
    </template>
  </div>
</template>

<script setup>
import { computed, ref, watch, onUnmounted } from 'vue'
import ProcTable from './ProcTable.vue'
import BarGauge from './BarGauge.vue'
import { int, level, isFree, gbFromMb, realGpuProcs, cleanStr } from '../util.js'

const props = defineProps({
  g: { type: Object, default: () => ({}) },
  showProcs: { type: Boolean, default: true },
  compact: { type: Boolean, default: false },  // 总览小卡：仅显存 + 功耗 / overview mini: VRAM + power only
})

// 空闲判定去抖：占用抖动时不要绿色一闪一闪，稳定 ~12s 才切换。 / Debounce free flag to stop green flicker.
const FREE_DEBOUNCE_MS = 12000
const rawFree = computed(() => isFree(props.g))
const free = ref(rawFree.value)
let ft = null
watch(rawFree, (v) => {
  clearTimeout(ft)
  ft = setTimeout(() => { free.value = v }, FREE_DEBOUNCE_MS)
})
onUnmounted(() => clearTimeout(ft))

const tempCls = computed(() => {
  const l = level(props.g.temperature, 75, 85)
  // 正常温度用中性徽标，绿色只留给「空闲」。 / Normal temp stays neutral; green is reserved for "free".
  return l === 'crit' ? 'crit' : l === 'warn' ? 'warn' : ''
})
const bars = computed(() => {
  const vram = { label: '显存 / VRAM', pct: props.g.memory_percent,
    text: `${gbFromMb(props.g.memory_used)} / ${gbFromMb(props.g.memory_total)} GB`, warn: 80, crit: 95, color: 'var(--c-vram)' }
  if (props.compact) return [vram]
  return [
    { label: '利用率 / Util', pct: props.g.utilization, text: int(props.g.utilization) + '%', warn: 60, crit: 90, color: 'var(--c-gpu)' },
    vram,
  ]
})
// 小卡：显存条下列出「谁在用卡」——以 cwd 为身份，原样展示（[[proc-cwd-identity]]）。剔除 Xorg 等系统进程。
// Compact card: under the VRAM bar, list who's using the GPU — identity = cwd, shown as-is. System procs (Xorg…) filtered.
const procs = computed(() => realGpuProcs(props.g.processes))
const cwds = computed(() => procs.value.map((p) => ({
  path: cleanStr(p.cwd) || cleanStr(p.name) || '—',
  full: cleanStr(p.cmdline) || cleanStr(p.cwd) || '',
  mem: memShort(p.gpu_memory_usage_mb),
  user: cleanStr(p.username) || '',
})))
function memShort(mb) {
  if (typeof mb !== 'number') return ''
  return mb >= 1024 ? (mb / 1024).toFixed(1) + 'G' : Math.round(mb) + 'M'
}
// 降频原因：过滤掉正常的 GpuIdle / None，剩余才提示。 / Throttle reasons minus benign idle.
const throttle = computed(() => {
  const r = props.g.throttle_reasons
  if (!Array.isArray(r) || !r.length) return ''
  const bad = r.filter((x) => x && !/idle|none/i.test(String(x)))
  return bad.length ? bad.join(', ') : ''
})
const eccBad = computed(() => typeof props.g.ecc_uncorrected === 'number' && props.g.ecc_uncorrected > 0)
function num0(v) { return (typeof v === 'number' && isFinite(v)) ? v : null }
</script>
