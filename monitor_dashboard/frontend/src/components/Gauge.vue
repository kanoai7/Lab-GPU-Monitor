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
import { metricColor } from '../util.js'

const props = defineProps({
  value: { type: Number, default: null },   // 原始值 / raw value
  max: { type: Number, default: 100 },
  unit: { type: String, default: '%' },
  label: { type: String, default: '' },
  size: { type: Number, default: 104 },
  warn: { type: Number, default: null },
  crit: { type: Number, default: null },
  color: { type: String, default: '' },      // 指标底色 / metric base hue
  onPanel2: { type: Boolean, default: false },
})

const valid = computed(() => typeof props.value === 'number' && isFinite(props.value))
const fillPct = computed(() => valid.value ? Math.max(0, Math.min(100, (props.value / props.max) * 100)) : 0)
const display = computed(() => valid.value ? Math.round(props.value) + props.unit : '—')
// 正常区间显示指标底色，越过 warn/crit 才转琥珀/红。 / Base hue normally; warn/crit escalate.
const color = computed(() => metricColor(props.value, props.warn, props.crit, props.color || 'var(--accent)'))
</script>
