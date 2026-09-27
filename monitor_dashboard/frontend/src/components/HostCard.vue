<template>
  <div class="card clickable" :class="{ offline: !online }" @click="go">
    <div class="card-head">
      <div class="card-title">
        <span class="dot" :class="online ? 'online' : 'offline'"></span>
        <span>{{ name }}</span>
        <span v-if="hostname" class="host mono">{{ hostname }}</span>
      </div>
      <div class="head-badges">
        <span v-if="online && freeCount" class="badge ok-badge">空闲 {{ freeCount }} / {{ gpus.length }} 卡</span>
        <span class="badge" :class="online ? 'ok-badge' : 'crit'">{{ online ? '在线' : '离线' }}</span>
      </div>
    </div>
    <div class="card-body">
      <template v-if="online">
        <!-- 主机级关键指标：CPU / 内存 汽车仪表盘 / host-level CPU + MEM as speedometer gauges -->
        <div class="hc-stats">
          <div class="hc-stat" :class="lvl(cpuPct, 70, 90)">
            <Gauge :value="cpuPct" :warn="70" :crit="90" :size="112" on-panel2 />
            <div class="hc-k">CPU</div>
            <div v-if="loadCaption" class="hc-sub">{{ loadCaption }}</div>
          </div>
          <div class="hc-stat" :class="lvl(mem.percent, 80, 95)">
            <Gauge :value="mem.percent" :warn="80" :crit="95" :size="112" on-panel2 />
            <div class="hc-k">内存 / MEM</div>
            <div class="hc-sub mono">{{ num(mem.used_gb) }} / {{ num(mem.total_gb) }} GB</div>
          </div>
        </div>

        <!-- 每张 GPU 的完整信息（不做"最热"聚合）/ Full per-GPU info (no "hottest" aggregation). -->
        <template v-if="gpus.length">
          <div class="section-cap">
            <span>GPU</span>
            <span class="sc-meta">{{ gpus.length }} 卡<template v-if="freeCount"> · 空闲 {{ freeCount }}</template></span>
          </div>
          <div class="gpu-list">
            <GpuPanel v-for="g in gpus" :key="g.index" :g="g" :show-procs="false" compact />
          </div>
        </template>
        <div v-else class="inforow"><span class="lbl">GPU</span>未检测到 GPU / no GPU detected</div>
      </template>
      <template v-else>
        <div class="inforow"><span class="lbl">错误 / error</span>{{ entry.error || '无法连接 / unreachable' }}</div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import GpuPanel from './GpuPanel.vue'
import Gauge from './Gauge.vue'
import { num, level, isFree, loadPct } from '../util.js'

const props = defineProps({
  name: String,
  entry: { type: Object, default: () => ({}) },
})
const router = useRouter()

const online = computed(() => props.entry.status === 'online')
const d = computed(() => props.entry.data || {})
const hostname = computed(() => (d.value.system || {}).hostname || '')
const cpu = computed(() => d.value.cpu || {})
const cpuPct = computed(() => cpu.value.percent)
// #1：负载归一化为占核百分比，标注核数，避免裸数字费解。 / Normalize load to % of cores + show core count.
const loadCaption = computed(() => {
  const la = cpu.value.load_avg
  const cores = cpu.value.logical_cores
  if (!Array.isArray(la) || !la.length) return ''
  const p = loadPct(la[0], cores)
  return p != null ? `负载 ${la[0]} (${Math.round(p)}% of ${cores}核)` : `负载 ${la[0]}`
})
const mem = computed(() => d.value.memory || {})
const gpus = computed(() => d.value.gpus || [])
// 空闲卡计数去抖，避免抖动时徽章一闪一闪。 / Debounced free count to avoid flicker.
const rawFreeCount = computed(() => gpus.value.filter(isFree).length)
const freeCount = ref(rawFreeCount.value)
let ft = null
watch(rawFreeCount, (v) => { clearTimeout(ft); ft = setTimeout(() => { freeCount.value = v }, 12000) })
onUnmounted(() => clearTimeout(ft))

function lvl(v, w, c) { return level(v, w, c) }
function go() { router.push('/host/' + encodeURIComponent(props.name)) }
</script>
