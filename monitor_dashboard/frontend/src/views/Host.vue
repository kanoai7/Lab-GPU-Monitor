<template>
  <main class="container">
    <div class="page-head">
      <h1>
        <router-link to="/" class="navlink">← 总览</router-link>
        &nbsp;{{ name }}
        <span v-if="hostname" class="muted mono">{{ hostname }}</span>
      </h1>
      <div class="filters">
        <span class="pill" :class="online ? 'online' : 'offline'">{{ online ? '在线 / online' : '离线 / offline' }}</span>
        <div class="seg">
          <button v-for="r in RANGES" :key="r" :class="{ active: range === r }" @click="setRange(r)">{{ r }}</button>
        </div>
      </div>
    </div>

    <div v-if="loadErr" class="empty-hint">加载历史失败 / failed to load history: {{ loadErr }}</div>

    <!-- 历史多折线 / history multi-line charts -->
    <div class="chart-grid">
      <MetricChart title="CPU 利用率 / CPU %" unit="%" :yMax="100" :ts="H.ts" :series="[{ name: 'CPU', data: H.cpu }]" />
      <MetricChart title="内存 / Memory (GB)" unit=" GB" :ts="H.ts" :series="memSeries" />
      <MetricChart title="网络 / Network (Mbps)" unit=" Mbps" :ts="H.ts" :series="netSeries" />
      <MetricChart title="磁盘 IO / Disk IO (Mbps)" unit=" Mbps" :ts="H.ts" :series="diskSeries" />
      <MetricChart title="GPU 利用率 / GPU Util %" unit="%" :yMax="100" :ts="gpuTs" :series="gpuSeries('util')" />
      <MetricChart title="GPU 显存 / GPU VRAM %" unit="%" :yMax="100" :ts="gpuTs" :series="gpuSeries('mem_pct')" />
      <MetricChart title="GPU 温度 / GPU Temp °C" unit="°C" :ts="gpuTs" :series="gpuSeries('temp')" />
      <MetricChart title="GPU 功耗 / GPU Power W" unit="W" :ts="gpuTs" :series="gpuSeries('power')" />
    </div>

    <!-- 实时 GPU 与进程 / live GPU + processes -->
    <div class="panel" v-if="online">
      <h2>实时 GPU / Live GPUs</h2>
      <GpuPanel v-for="g in liveGpus" :key="g.index" :g="g" />
      <div v-if="!liveGpus.length" class="muted">此主机无 GPU / no GPUs on this host.</div>
    </div>
  </main>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import MetricChart from '../components/MetricChart.vue'
import GpuPanel from '../components/GpuPanel.vue'
import { api } from '../api.js'

const RANGES = ['1h', '6h', '24h', '7d']
const route = useRoute()
const name = computed(() => route.params.name)

const range = ref('6h')
const H = reactive({ ts: [], cpu: [], mem_used: [], mem_avail: [], swap_used: [], net_up: [], net_down: [], disk_r: [], disk_w: [], gpus: [] })
const live = reactive({ status: '', data: {} })
const loadErr = ref('')
let histTimer = null, liveTimer = null

const online = computed(() => live.status === 'online')
const hostname = computed(() => (live.data.system || {}).hostname || '')
const liveGpus = computed(() => live.data.gpus || [])

const memSeries = computed(() => [
  { name: '已用 / used', data: H.mem_used },
  { name: '可用 / avail', data: H.mem_avail },
  { name: 'swap', data: H.swap_used },
])
const netSeries = computed(() => [
  { name: '上行 / up', data: H.net_up },
  { name: '下行 / down', data: H.net_down },
])
const diskSeries = computed(() => [
  { name: '读 / read', data: H.disk_r },
  { name: '写 / write', data: H.disk_w },
])
const gpuTs = computed(() => (H.gpus[0] ? H.gpus[0].ts : []))
function gpuSeries(field) {
  return H.gpus.map((g) => ({ name: '#' + g.idx + ' ' + (g.name || ''), data: g[field] }))
}

async function loadHistory() {
  try {
    const d = await api.history(name.value, range.value)
    Object.assign(H, { ts: [], cpu: [], mem_used: [], mem_avail: [], swap_used: [], net_up: [], net_down: [], disk_r: [], disk_w: [], gpus: [] }, d)
    loadErr.value = ''
  } catch (e) { loadErr.value = String(e.message || e) }
}
async function loadLive() {
  try {
    const res = await api.data()
    const e = (res.servers || {})[name.value] || {}
    live.status = e.status || 'offline'
    live.data = e.data || {}
  } catch (e) { live.status = 'offline' }
}
function setRange(r) { range.value = r }

watch(range, loadHistory)
onMounted(() => {
  loadHistory(); loadLive()
  histTimer = setInterval(loadHistory, 15000)
  liveTimer = setInterval(loadLive, 3000)
})
onUnmounted(() => { clearInterval(histTimer); clearInterval(liveTimer) })
</script>
