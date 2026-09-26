<template>
  <main class="container">
    <div class="filters" style="margin-bottom:16px">
      <input v-model="filter" class="field sm" type="text" placeholder="筛选：服务器 / 用户 / 目录 / GPU … / filter" />
      <label class="chip"><input type="checkbox" v-model="freeOnly" /> 只看空闲卡 / free only</label>
      <span class="pill" :class="pillClass">{{ pillText }}</span>
    </div>

    <div v-if="!hasAgents" class="empty-hint">
      还没有配置任何 Agent。请到 <router-link to="/settings">设置</router-link> 添加。<br />
      No agents configured yet — add them in <router-link to="/settings">Settings</router-link>.
    </div>
    <div v-else-if="!visibleNames.length" class="empty-hint">无匹配结果 / No matching hosts.</div>

    <div class="cards">
      <HostCard v-for="n in visibleNames" :key="n" :name="n" :entry="servers[n]" :sparks="sparks[n] || {}" />
    </div>
  </main>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import HostCard from '../components/HostCard.vue'
import { api } from '../api.js'
import { isFree } from '../util.js'

const servers = reactive({})
const sparks = reactive({})     // name -> {cpu:[], gpu:[]}
const filter = ref('')
const freeOnly = ref(loadFreeOnly())
const pollMs = ref(2000)
const status = ref('syncing')
let timer = null

const RING = 30
function loadFreeOnly() { try { return localStorage.getItem('lgm-free-only') === '1' } catch (e) { return false } }
function pushRing(name, cpu, gpu) {
  if (!sparks[name]) sparks[name] = { cpu: [], gpu: [] }
  const s = sparks[name]
  s.cpu.push(cpu); s.gpu.push(gpu)
  if (s.cpu.length > RING) s.cpu.shift()
  if (s.gpu.length > RING) s.gpu.shift()
}

const hasAgents = computed(() => Object.keys(servers).length > 0)
const pillText = computed(() => status.value === 'ok' ? '已同步 / synced' : status.value === 'err' ? '连接失败 / error' : '同步中… / syncing…')
const pillClass = computed(() => status.value === 'ok' ? 'online' : status.value === 'err' ? 'offline' : '')

function matches(name) {
  const q = filter.value.trim().toLowerCase()
  const e = servers[name] || {}
  if (freeOnly.value) {
    const gpus = (e.data || {}).gpus || []
    if (!gpus.some(isFree)) return false
  }
  if (!q) return true
  if (name.toLowerCase().includes(q)) return true
  const d = e.data || {}
  if (((d.system || {}).hostname || '').toLowerCase().includes(q)) return true
  for (const g of (d.gpus || [])) {
    if ((g.name || '').toLowerCase().includes(q)) return true
    for (const p of (g.processes || [])) {
      if (String(p.username || '').toLowerCase().includes(q)) return true
      if (String(p.cwd || '').toLowerCase().includes(q)) return true
      if (String(p.name || '').toLowerCase().includes(q)) return true
    }
  }
  return false
}
const visibleNames = computed(() => Object.keys(servers).sort().filter(matches))

async function refresh() {
  try {
    const res = await api.data()
    const s = res.servers || {}
    for (const k of Object.keys(servers)) if (!(k in s)) delete servers[k]
    for (const [k, v] of Object.entries(s)) {
      servers[k] = v
      if (v.status === 'online') {
        const d = v.data || {}
        const cpu = (d.cpu || {}).percent
        const gpu = (d.gpus || []).reduce((m, g) => Math.max(m, g.utilization || 0), 0)
        pushRing(k, typeof cpu === 'number' ? cpu : null, typeof gpu === 'number' ? gpu : null)
      }
    }
    if (res.config && res.config.poll_interval) pollMs.value = Math.max(1000, res.config.poll_interval * 1000)
    status.value = 'ok'
  } catch (e) {
    status.value = 'err'
  }
}

onMounted(() => {
  refresh()
  timer = setInterval(refresh, pollMs.value)
})
onUnmounted(() => clearInterval(timer))

import { watch } from 'vue'
watch(freeOnly, (v) => { try { localStorage.setItem('lgm-free-only', v ? '1' : '0') } catch (e) {} })
watch(pollMs, (v) => { clearInterval(timer); timer = setInterval(refresh, v) })
</script>
