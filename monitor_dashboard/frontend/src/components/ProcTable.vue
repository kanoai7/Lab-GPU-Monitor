<template>
  <div class="procs">
    <div class="proc" v-for="p in procs" :key="p.pid">
      <div>
        <b>PID {{ p.pid }}</b>
        <span v-if="val(p.username)"> · {{ val(p.username) }}</span>
        <span v-if="val(p.name)"> · {{ val(p.name) }}</span>
        · {{ memGB(p) }}
        <span v-if="typeof p.gpu_util === 'number'"> · GPU {{ p.gpu_util }}%</span>
        <span v-if="idle(p)" class="badge warn" style="margin-left:6px">空转 / idle?</span>
      </div>
      <div class="cwd" :title="val(p.cmdline) || ''">{{ val(p.cwd) || '—' }}</div>
    </div>
  </div>
</template>

<script setup>
import { cleanStr as val } from '../util.js'
defineProps({ procs: { type: Array, default: () => [] } })
// val()：把 agent 的 "unknown"/空归一化为缺失（→ 省略或显示 —）。见 util.cleanStr。
// 显存占用：MB→GB 展示。 / VRAM usage MB->GB.
function memGB(p) {
  const mb = p.gpu_memory_usage_mb
  if (typeof mb !== 'number') return '—'
  return mb >= 1024 ? (mb / 1024).toFixed(1) + ' GB' : Math.round(mb) + ' MB'
}
// 占卡空转：占了显存但 GPU 利用率为 0。 / Holding VRAM but 0% util.
function idle(p) {
  return typeof p.gpu_util === 'number' && p.gpu_util === 0 && (p.gpu_memory_usage_mb || 0) > 0
}
</script>
