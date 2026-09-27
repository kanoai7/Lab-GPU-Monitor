<template>
  <div class="donut-wrap">
    <div class="donut" :style="{ width: size + 'px', height: size + 'px', '--donut-stops': stops }">
      <div class="donut-center">
        <div class="dc-v">{{ centerValue }}</div>
        <div v-if="centerLabel" class="dc-k">{{ centerLabel }}</div>
      </div>
    </div>
    <div class="legend">
      <div class="lg" v-for="s in segments" :key="s.label">
        <span class="sw" :style="{ background: s.color }"></span>
        <span>{{ s.label }}</span>
        <span class="lg-v">{{ fmt(s.value) }}{{ unit }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  segments: { type: Array, default: () => [] },  // [{label, value, color}]
  size: { type: Number, default: 120 },
  unit: { type: String, default: '' },
  centerValue: { type: String, default: '' },
  centerLabel: { type: String, default: '' },
  digits: { type: Number, default: 1 },
})

const total = computed(() => props.segments.reduce((a, s) => a + (s.value > 0 ? s.value : 0), 0) || 1)
const stops = computed(() => {
  let acc = 0
  const parts = []
  for (const s of props.segments) {
    const v = s.value > 0 ? s.value : 0
    const from = (acc / total.value) * 100
    acc += v
    const to = (acc / total.value) * 100
    parts.push(`${s.color} ${from}% ${to}%`)
  }
  return parts.join(', ')
})
function fmt(v) { return (typeof v === 'number' && isFinite(v)) ? v.toFixed(props.digits) : '—' }
</script>
