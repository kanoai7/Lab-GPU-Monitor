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
        <div class="stats">
          <div class="stat">
            <span class="stat-k">CPU</span>
            <span class="stat-v" :class="lvlTxt(cpuPct, 70, 90)">{{ int(cpuPct) }}%</span>
          </div>
          <div class="stat">
            <span class="stat-k">内存 / MEM</span>
            <span class="stat-v" :class="lvlTxt(memPct, 80, 95)">{{ int(memPct) }}%</span>
          </div>
          <div class="stat">
            <span class="stat-k">GPU 数</span>
            <span class="stat-v">{{ gpus.length }}</span>
          </div>
          <div class="stat">
            <span class="stat-k">最热 GPU</span>
            <span class="stat-v" :class="lvlTxt(hotTemp, 75, 85)">{{ int(hotTemp) }}°C</span>
          </div>
        </div>

        <div class="metric">
          <div class="metric-top"><span>CPU 近况 / recent</span><b class="mono">{{ int(cpuPct) }}%</b></div>
          <div class="spark">{{ spark(sparks.cpu) }}</div>
        </div>
        <div class="metric">
          <div class="metric-top"><span>最热 GPU 利用率 / hottest util</span><b class="mono">{{ int(hotUtil) }}%</b></div>
          <div class="spark">{{ spark(sparks.gpu) }}</div>
        </div>
      </template>
      <template v-else>
        <div class="inforow"><span class="lbl">错误 / error</span>{{ entry.error || '无法连接 / unreachable' }}</div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { int, spark, isFree, level } from '../util.js'

const props = defineProps({
  name: String,
  entry: { type: Object, default: () => ({}) },
  sparks: { type: Object, default: () => ({ cpu: [], gpu: [] }) },
})
const router = useRouter()

const online = computed(() => props.entry.status === 'online')
const d = computed(() => props.entry.data || {})
const hostname = computed(() => (d.value.system || {}).hostname || '')
const cpuPct = computed(() => (d.value.cpu || {}).percent)
const memPct = computed(() => (d.value.memory || {}).percent)
const gpus = computed(() => d.value.gpus || [])
const freeCount = computed(() => gpus.value.filter(isFree).length)
const hotTemp = computed(() => gpus.value.reduce((m, g) => Math.max(m, g.temperature || 0), 0) || null)
const hotUtil = computed(() => gpus.value.reduce((m, g) => Math.max(m, g.utilization || 0), 0) || null)

function lvlTxt(v, w, c) {
  const l = level(v, w, c)
  return l === 'crit' ? 'crit-txt' : l === 'warn' ? 'warn-txt' : ''
}
function go() { router.push('/host/' + encodeURIComponent(props.name)) }
</script>
