<template>
  <main class="container">
    <div class="page-head">
      <h1>
        <router-link to="/" class="navlink"><Icon name="arrow-left" :size="15" />总览</router-link>
        <span>{{ name }}</span>
        <span v-if="hostname" class="badge mono">{{ hostname }}</span>
      </h1>
      <div class="filters">
        <span class="pill" :class="online ? 'online' : 'offline'">{{ online ? '在线 / online' : '离线 / offline' }}</span>
      </div>
    </div>

    <div v-if="!online" class="empty-hint">主机当前离线，下方仅显示历史数据 / host offline — history only.</div>

    <div class="panel-stack">
      <!-- 概览：仪表盘 + 饼图 + 关键指标卡 / Overview -->
      <div class="panel" v-if="online" :style="{ order: ord('overview') }" :class="{ dragging: dragKey === 'overview' }"
           @dragover="onDragOver('overview', $event)" @drop.prevent="onDrop">
        <div class="panel-head">
          <span class="ph-title"><span class="drag-handle" draggable="true" title="拖动排序 / drag to reorder" @dragstart="onDragStart('overview', $event)" @dragend="onDragEnd"><Icon name="grip" :size="16" /></span><Icon name="grid" :size="16" class="ph-ic" /> 概览 / Overview</span>
          <span class="caption">{{ sysLine }}</span>
        </div>
        <div class="panel-body">
          <div class="gauge-row">
            <div class="gauge-cell">
              <Gauge :value="cpuPct" label="CPU" :warn="70" :crit="90" :size="128" color="var(--c-cpu)" />
              <div v-if="loadSub" class="gauge-sub">{{ loadSub }}</div>
            </div>
            <div class="gauge-cell">
              <Gauge :value="mem.percent" label="内存" :warn="80" :crit="95" :size="128" color="var(--c-mem)" />
              <div class="gauge-sub mono">{{ num(mem.used_gb) }} / {{ num(mem.total_gb) }} GB</div>
            </div>
            <div class="stat-row" style="flex:1; min-width:280px">
              <StatCard k="1 分钟负载" :v="load1txt" :sub="loadSub" :level="loadLevel" />
              <StatCard k="空闲 GPU" :v="freeCount + ' / ' + liveGpus.length" :level="freeCount ? 'ok' : ''" />
              <StatCard k="网络 ↑/↓ Mbps" :v="netNow" />
              <StatCard k="磁盘 R/W MB/s" :v="dioNow" />
              <StatCard k="连接数" :v="conns" />
              <StatCard k="在线时长" :v="uptime" />
            </div>
          </div>
        </div>
      </div>

      <!-- CPU：每核热力 + 频率/核数 / CPU: per-core heat + freq/cores -->
      <div class="panel" v-if="online && cpu.percent != null" :style="{ order: ord('cpu') }" :class="{ dragging: dragKey === 'cpu' }"
           @dragover="onDragOver('cpu', $event)" @drop.prevent="onDrop">
        <div class="panel-head">
          <span class="ph-title"><span class="drag-handle" draggable="true" title="拖动排序 / drag to reorder" @dragstart="onDragStart('cpu', $event)" @dragend="onDragEnd"><Icon name="grip" :size="16" /></span><Icon name="cpu" :size="16" class="ph-ic" /> CPU</span>
        </div>
        <div class="panel-body">
          <div class="stat-row">
            <StatCard k="物理核 / phys" :v="cpu.physical_cores ?? '—'" />
            <StatCard k="逻辑核 / logical" :v="cpu.logical_cores ?? '—'" />
            <StatCard k="频率 / freq" :v="cpu.freq_mhz ? int(cpu.freq_mhz) + ' MHz' : '—'" />
            <StatCard k="负载 1/5/15 分钟" :v="loadAll" />
          </div>
          <div v-if="perCore.length" class="caption" style="margin:16px 0 6px">每核利用率 / per-core util</div>
          <div v-if="perCore.length" class="cores">
            <div class="core" v-for="(c, i) in perCore" :key="i" :title="'core ' + i + ': ' + int(c) + '%'">
              <span :style="{ height: pct(c) + '%', background: coreColor(c) }"></span>
              <span v-if="perCore.length <= 32" class="cl">{{ int(c) }}</span>
            </div>
          </div>
        </div>
      </div>
      <!-- 存储：各分区进度条 / Storage: per-partition bar-gauge -->
      <div class="panel" v-if="online && disks.length" :style="{ order: ord('storage') }" :class="{ dragging: dragKey === 'storage' }"
           @dragover="onDragOver('storage', $event)" @drop.prevent="onDrop">
        <div class="panel-head">
          <span class="ph-title"><span class="drag-handle" draggable="true" title="拖动排序 / drag to reorder" @dragstart="onDragStart('storage', $event)" @dragend="onDragEnd"><Icon name="grip" :size="16" /></span><Icon name="disk" :size="16" class="ph-ic" /> 存储 / Storage</span>
        </div>
        <div class="panel-body"><BarGauge :items="diskItems" /></div>
      </div>

      <!-- 网络：累计流量 + 分网卡 + 错误丢包 / Network -->
      <div class="panel" v-if="online && net.send_mbps != null" :style="{ order: ord('network') }" :class="{ dragging: dragKey === 'network' }"
           @dragover="onDragOver('network', $event)" @drop.prevent="onDrop">
        <div class="panel-head">
          <span class="ph-title"><span class="drag-handle" draggable="true" title="拖动排序 / drag to reorder" @dragstart="onDragStart('network', $event)" @dragend="onDragEnd"><Icon name="grip" :size="16" /></span><Icon name="network" :size="16" class="ph-ic" /> 网络 / Network</span>
          <span class="badge" :class="errDrop ? 'crit' : 'ok-badge'">{{ errDrop ? ('错误/丢包 ' + errDrop) : '无错误 / clean' }}</span>
        </div>
        <div class="panel-body">
          <div class="stat-row">
            <StatCard k="上行 / up" :v="int(net.send_mbps) + ' Mbps'" />
            <StatCard k="下行 / down" :v="int(net.recv_mbps) + ' Mbps'" />
            <StatCard k="累计发送 / sent" :v="num(net.total_sent_gb) + ' GB'" />
            <StatCard k="累计接收 / recv" :v="num(net.total_recv_gb) + ' GB'" />
          </div>
          <template v-if="nics.length">
            <div class="caption" style="margin:16px 0 6px">分网卡 / per-NIC</div>
            <div class="section-grid">
              <div v-for="n in nics" :key="n.name" class="statcard">
                <span class="sc-k">{{ n.name }}</span>
                <span class="sc-sub">↑ {{ num(n.sent_gb) }} GB · ↓ {{ num(n.recv_gb) }} GB</span>
                <span v-if="n.bad" class="badge crit" style="align-self:flex-start; margin-top:4px">err {{ n.err }} · drop {{ n.drop }}</span>
              </div>
            </div>
          </template>
        </div>
      </div>
      <!-- 磁盘 IO：累计读写 / Disk IO totals -->
      <div class="panel" v-if="online && dio.read_mbps != null" :style="{ order: ord('diskio') }" :class="{ dragging: dragKey === 'diskio' }"
           @dragover="onDragOver('diskio', $event)" @drop.prevent="onDrop">
        <div class="panel-head">
          <span class="ph-title"><span class="drag-handle" draggable="true" title="拖动排序 / drag to reorder" @dragstart="onDragStart('diskio', $event)" @dragend="onDragEnd"><Icon name="grip" :size="16" /></span><Icon name="activity" :size="16" class="ph-ic" /> 磁盘 IO / Disk IO</span>
        </div>
        <div class="panel-body">
          <div class="stat-row">
            <StatCard k="读 / read" :v="num(dio.read_mbps) + ' MB/s'" />
            <StatCard k="写 / write" :v="num(dio.write_mbps) + ' MB/s'" />
            <StatCard k="累计读 / read" :v="num(dio.total_read_gb) + ' GB'" />
            <StatCard k="累计写 / write" :v="num(dio.total_write_gb) + ' GB'" />
          </div>
        </div>
      </div>

      <!-- 历史趋势（时间范围仅对本区有效，置于右上）/ History (range affects this panel only) -->
      <div class="panel" :style="{ order: ord('history') }" :class="{ dragging: dragKey === 'history' }"
           @dragover="onDragOver('history', $event)" @drop.prevent="onDrop">
        <div class="panel-head">
          <span class="ph-title"><span class="drag-handle" draggable="true" title="拖动排序 / drag to reorder" @dragstart="onDragStart('history', $event)" @dragend="onDragEnd"><Icon name="grip" :size="16" /></span><Icon name="chart" :size="16" class="ph-ic" /> 历史趋势 / History</span>
          <div class="ph-actions">
            <div class="seg">
              <button v-for="r in RANGES" :key="r" :class="{ active: range === r }" @click="setRange(r)">{{ r }}</button>
            </div>
          </div>
        </div>
        <div class="panel-body">
          <div v-if="loadErr" class="inforow crit-txt">加载历史失败 / failed to load history: {{ loadErr }}</div>
          <div class="chart-grid">
            <MetricChart title="CPU 利用率 / CPU %" unit="%" :yMax="100" :ts="H.ts" :series="[{ name: 'CPU', data: H.cpu }]" />
            <MetricChart title="内存利用率 / Memory %" unit="%" :yMax="100" :ts="H.ts" :series="[{ name: '内存 / mem', data: H.mem_pct }]" />
            <MetricChart title="网络 / Network (Mbps · 上+ / 下−)" unit=" Mbps" :ts="H.ts" :series="netSeries" mirror />
            <MetricChart title="磁盘 IO / Disk IO (MB/s · 读+ / 写−)" unit=" MB/s" :ts="H.ts" :series="diskSeries" mirror />
            <MetricChart title="GPU 利用率 / GPU Util %" unit="%" :yMax="100" :ts="gpuTs" :series="gpuSeries('util')" :area="false" />
            <MetricChart title="GPU 显存 / GPU VRAM %" unit="%" :yMax="100" :ts="gpuTs" :series="gpuSeries('mem_pct')" :area="false" />
            <MetricChart title="GPU 温度 / GPU Temp °C" unit="°C" :ts="gpuTs" :series="gpuSeries('temp')" :area="false" />
            <MetricChart title="GPU 功耗 / GPU Power W" unit="W" :ts="gpuTs" :series="gpuSeries('power')" :area="false" />
          </div>
        </div>
      </div>

      <!-- 实时 GPU 与进程 / live GPU + processes -->
      <div class="panel" v-if="online" :style="{ order: ord('gpu') }" :class="{ dragging: dragKey === 'gpu' }"
           @dragover="onDragOver('gpu', $event)" @drop.prevent="onDrop">
        <div class="panel-head">
          <span class="ph-title"><span class="drag-handle" draggable="true" title="拖动排序 / drag to reorder" @dragstart="onDragStart('gpu', $event)" @dragend="onDragEnd"><Icon name="grip" :size="16" /></span><Icon name="gpu" :size="16" class="ph-ic" /> 实时 GPU / Live GPUs</span>
        </div>
        <div class="panel-body">
          <GpuPanel v-for="g in liveGpus" :key="g.index" :g="g" />
          <div v-if="!liveGpus.length" class="muted">此主机无 GPU / no GPUs on this host.</div>
        </div>
      </div>
    </div>
  </main>
</template>
<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import MetricChart from '../components/MetricChart.vue'
import GpuPanel from '../components/GpuPanel.vue'
import Gauge from '../components/Gauge.vue'
import BarGauge from '../components/BarGauge.vue'
import StatCard from '../components/StatCard.vue'
import Icon from '../components/Icon.vue'
import { api } from '../api.js'
import { int, num, pct, level, metricColor, isFree, loadPct } from '../util.js'

const RANGES = ['1h', '6h', '24h', '7d']
const route = useRoute()
const name = computed(() => route.params.name)

const range = ref('6h')
const H = reactive({ ts: [], cpu: [], mem_pct: [], mem_used: [], mem_avail: [], swap_used: [],
  net_up: [], net_down: [], disk_r: [], disk_w: [], load1: [], gpus: [] })
const live = reactive({ status: '', data: {} })
const loadErr = ref('')
let histTimer = null, liveTimer = null

const online = computed(() => live.status === 'online')
const D = computed(() => live.data || {})
const hostname = computed(() => (D.value.system || {}).hostname || '')
const cpu = computed(() => D.value.cpu || {})
const mem = computed(() => D.value.memory || {})
const dio = computed(() => D.value.disk_io || {})
const net = computed(() => D.value.network || {})
const disks = computed(() => D.value.disks || [])
const liveGpus = computed(() => D.value.gpus || [])
const perCore = computed(() => cpu.value.per_core || [])
const cpuPct = computed(() => cpu.value.percent)
const freeCount = computed(() => liveGpus.value.filter(isFree).length)

// 负载归一化 / normalized load.
const load = computed(() => cpu.value.load_avg)
const load1txt = computed(() => Array.isArray(load.value) && load.value.length ? String(load.value[0]) : '—')
const loadAll = computed(() => Array.isArray(load.value) ? load.value.map((x) => num(x, 2)).join(' / ') : '—')
const loadPctVal = computed(() => (Array.isArray(load.value) && load.value.length) ? loadPct(load.value[0], cpu.value.logical_cores) : null)
const loadSub = computed(() => loadPctVal.value != null ? Math.round(loadPctVal.value) + '% of ' + cpu.value.logical_cores + '核' : '')
const loadLevel = computed(() => loadPctVal.value != null ? level(loadPctVal.value, 70, 100) : '')

const netNow = computed(() => int(net.value.send_mbps) + ' / ' + int(net.value.recv_mbps))
const dioNow = computed(() => num(dio.value.read_mbps) + ' / ' + num(dio.value.write_mbps))
const conns = computed(() => typeof net.value.connections === 'number' ? net.value.connections : '—')
const uptime = computed(() => (D.value.system || {}).uptime_str || '—')
const sysLine = computed(() => {
  const s = D.value.system || {}
  const parts = []
  if (s.platform) parts.push(s.platform)
  if (Array.isArray(s.users) && s.users.length) parts.push('用户: ' + s.users.join(', '))
  return parts.join('  ·  ')
})
const errDrop = computed(() => {
  const n = net.value
  return (n.errin || 0) + (n.errout || 0) + (n.dropin || 0) + (n.dropout || 0)
})
const nics = computed(() => {
  const pn = net.value.per_nic
  if (!pn || typeof pn !== 'object') return []
  return Object.entries(pn).map(([nm, v]) => {
    const err = (v.errin || 0) + (v.errout || 0), drop = (v.dropin || 0) + (v.dropout || 0)
    return { name: nm, sent_gb: v.sent_gb, recv_gb: v.recv_gb, err, drop, bad: err + drop > 0 }
  })
})
const diskItems = computed(() => disks.value.filter((d) => !d.error).map((d) => ({
  label: (d.mountpoint || d.device || '') + (d.device && d.mountpoint ? '  (' + d.device + ')' : ''),
  pct: d.percent, text: num(d.used_gb) + ' / ' + num(d.total_gb) + ' GB · ' + int(d.percent) + '%',
  warn: 80, crit: 95, color: 'var(--c-disk)',
})))
function coreColor(c) { return metricColor(c, 60, 90, 'var(--c-cpu)') }

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

// 面板可拖拽排序，顺序全局持久化（对所有主机一致）（#6）/ draggable panels, order persisted globally.
const PANEL_KEYS = ['overview', 'cpu', 'storage', 'network', 'diskio', 'history', 'gpu']
const LS_ORDER = 'lgm-panel-order'
function loadOrder() {
  try {
    const s = JSON.parse(localStorage.getItem(LS_ORDER) || 'null')
    if (Array.isArray(s)) {
      const known = s.filter((k) => PANEL_KEYS.includes(k))
      return [...known, ...PANEL_KEYS.filter((k) => !known.includes(k))]
    }
  } catch (e) {}
  return [...PANEL_KEYS]
}
const panelOrder = ref(loadOrder())
const dragKey = ref('')
function ord(k) { return panelOrder.value.indexOf(k) }
function onDragStart(k, ev) {
  dragKey.value = k
  try {
    ev.dataTransfer.effectAllowed = 'move'
    const panel = ev.currentTarget.closest('.panel')
    if (panel) ev.dataTransfer.setDragImage(panel, 24, 16)
  } catch (e) {}
}
function onDragOver(k, ev) {
  ev.preventDefault()
  const from = dragKey.value
  if (!from || from === k) return
  const rect = ev.currentTarget.getBoundingClientRect()
  const after = ev.clientY > rect.top + rect.height / 2
  const arr = panelOrder.value.filter((x) => x !== from)
  let idx = arr.indexOf(k)
  if (after) idx += 1
  arr.splice(idx, 0, from)
  panelOrder.value = arr
}
function persistOrder() { try { localStorage.setItem(LS_ORDER, JSON.stringify(panelOrder.value)) } catch (e) {} }
function onDrop() { persistOrder() }
function onDragEnd() { dragKey.value = ''; persistOrder() }

async function loadHistory() {
  try {
    const d = await api.history(name.value, range.value)
    Object.assign(H, { ts: [], cpu: [], mem_pct: [], mem_used: [], mem_avail: [], swap_used: [],
      net_up: [], net_down: [], disk_r: [], disk_w: [], load1: [], gpus: [] }, d)
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

