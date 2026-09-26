<template>
  <div class="gpu" :class="{ free: free }">
    <div class="gpu-name">
      <span><span class="idx">#{{ g.index }}</span> {{ g.name || 'GPU' }}
        <span v-if="free" class="flag free">空闲 / FREE</span>
      </span>
      <span class="head-badges">
        <span class="badge" :class="tempCls">{{ int(g.temperature) }}°C</span>
        <span class="badge">{{ int(g.power_draw) }}W</span>
      </span>
    </div>

    <div class="metric">
      <div class="metric-top"><span>利用率 / Util</span><b class="mono">{{ int(g.utilization) }}%</b></div>
      <div class="bar" :class="lvl(g.utilization, 60, 90)"><span :style="{ width: pct(g.utilization) + '%' }"></span></div>
    </div>
    <div class="metric">
      <div class="metric-top">
        <span>显存 / VRAM</span>
        <b class="mono">{{ num(g.memory_used) }} / {{ num(g.memory_total) }} GB</b>
      </div>
      <div class="bar" :class="lvl(g.memory_percent, 80, 95)"><span :style="{ width: pct(g.memory_percent) + '%' }"></span></div>
    </div>

    <ProcTable v-if="showProcs && (g.processes || []).length" :procs="g.processes" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import ProcTable from './ProcTable.vue'
import { int, num, pct, level, isFree } from '../util.js'

const props = defineProps({
  g: { type: Object, default: () => ({}) },
  showProcs: { type: Boolean, default: true },
})
const free = computed(() => isFree(props.g))
const tempCls = computed(() => {
  const l = level(props.g.temperature, 75, 85)
  return l === 'crit' ? 'crit' : l === 'warn' ? 'warn' : 'ok-badge'
})
function lvl(v, w, c) { return level(v, w, c) }
</script>
