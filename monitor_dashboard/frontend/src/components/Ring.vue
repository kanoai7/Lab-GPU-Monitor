<template>
  <div class="ring" :class="{ 'on-2': onPanel2 }"
       :style="{ width: size + 'px', height: size + 'px', '--ring-val': fillPct, '--ring-col': color }">
    <div class="ring-inner">
      <div class="rv" :style="{ fontSize: Math.round(size * 0.24) + 'px' }">{{ display }}</div>
      <div v-if="label" class="rk">{{ label }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { pct as clampPct, lvlColor } from '../util.js'

const props = defineProps({
  value: { type: Number, default: null },   // 原始值 / raw value
  max: { type: Number, default: 100 },
  unit: { type: String, default: '%' },
  label: { type: String, default: '' },
  size: { type: Number, default: 84 },
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
