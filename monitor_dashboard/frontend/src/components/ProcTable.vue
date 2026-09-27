<template>
  <div class="procs">
    <div class="proc" v-for="p in procs" :key="p.pid">
      <div>
        <b>PID {{ p.pid }}</b>
        <span v-if="p.username"> · {{ p.username }}</span>
        <span v-if="p.name"> · {{ p.name }}</span>
        · {{ memGB(p) }}
        <span v-if="typeof p.gpu_util === 'number'"> · GPU {{ p.gpu_util }}%</span>
        <span v-if="idle(p)" class="badge warn" style="margin-left:6px">空转 / idle?</span>
      </div>
      <div class="cwd" :title="p.cmdline || ''">{{ p.cwd || '—' }}</div>
    </div>
  </div>
</template>

<script setup>
defineProps({ procs: { type: Array, default: () => [] } })
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
