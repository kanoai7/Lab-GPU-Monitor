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
import { pct as clampPct, metricColor } from '../util.js'

const props = defineProps({
  items: { type: Array, default: () => [] },  // [{label, pct, text, warn, crit, color}]
})
function clamp(v) { return clampPct(v) }
function colorOf(it) {
  // it.color 作为该指标正常区间的底色；越过 warn/crit 才转琥珀/红。 / it.color is the base hue; warn/crit escalate.
  return metricColor(it.pct, it.warn, it.crit, it.color)
}
</script>
