<template>
  <!-- 汽车仪表盘式弧形表：270° 弧、底部开口，中心显示读数。 / Speedometer-style 270° arc gauge, open at bottom. -->
  <div class="gauge" :class="{ 'on-2': onPanel2 }"
       :style="{ width: size + 'px', height: size + 'px', '--g-val': fillPct, '--g-col': color }">
    <div class="gauge-inner">
      <div class="gv" :style="{ fontSize: Math.round(size * 0.26) + 'px' }">{{ display }}</div>
      <div v-if="label" class="gk">{{ label }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { lvlColor } from '../util.js'

const props = defineProps({
  value: { type: Number, default: null },   // 原始值 / raw value
  max: { type: Number, default: 100 },
  unit: { type: String, default: '%' },
  label: { type: String, default: '' },
  size: { type: Number, default: 104 },
  warn: { type: Number, default: null },
  crit: { type: Number, default: null },
  color: { type: String, default: '' },      // 覆盖色 / override color
  onPanel2: { type: Boolean, default: false },
})

const valid = computed(() => typeof props.value === 'number' && isFinite(props.value))
const fillPct = computed(() => valid.value ? Math.max(0, Math.min(100, (props.value / props.max) * 100)) : 0)
const display = computed(() => valid.value ? Math.round(props.value) + props.unit : '—')
const color = computed(() => {
  if (props.color) return props.color
  if (props.warn != null && props.crit != null) return lvlColor(props.value, props.warn, props.crit)
  return 'var(--accent)'
})
</script>
