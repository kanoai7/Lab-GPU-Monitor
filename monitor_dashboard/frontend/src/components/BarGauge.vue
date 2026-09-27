<template>
  <div class="bargauge">
    <div class="bg-item" v-for="(it, i) in items" :key="i">
      <div class="bg-top">
        <span class="bg-label" :title="it.label">{{ it.label }}</span>
        <span class="bg-val">{{ it.text }}</span>
      </div>
      <div class="bg-track">
        <span :style="{ width: clamp(it.pct) + '%', background: colorOf(it) }"></span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { pct as clampPct, lvlColor } from '../util.js'

const props = defineProps({
  items: { type: Array, default: () => [] },  // [{label, pct, text, warn, crit, color}]
})
function clamp(v) { return clampPct(v) }
function colorOf(it) {
  if (it.color) return it.color
  if (it.warn != null && it.crit != null) return lvlColor(it.pct, it.warn, it.crit)
  return 'var(--accent)'
}
</script>
