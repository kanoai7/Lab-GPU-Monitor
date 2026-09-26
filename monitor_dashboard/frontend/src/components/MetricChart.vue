<template>
  <div class="chart-panel">
    <h3>{{ title }}</h3>
    <v-chart class="echart" :option="option" :theme="null" autoresize />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { themeName } from '../theme.js'

const props = defineProps({
  title: String,
  ts: { type: Array, default: () => [] },       // epoch 秒 / epoch seconds
  series: { type: Array, default: () => [] },     // [{name, data:[...]}]
  unit: { type: String, default: '' },
  yMax: { type: Number, default: null },
})

// 调色板（多折线区分）。 / Palette for multi-line separation.
const PALETTE = ['#3b82f6', '#3fb950', '#d29922', '#f85149', '#a371f7', '#39c5cf', '#db61a2', '#e3b341']

function cssVar(name, fallback) {
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
    return v || fallback
  } catch (e) { return fallback }
}

const option = computed(() => {
  themeName.value // 依赖主题触发重算 / depend on theme to recompute
  const text = cssVar('--muted', '#8b949e')
  const border = cssVar('--border', '#2a3038')
  const labels = props.ts.map((t) => new Date(t * 1000))
  const multi = props.series.length > 1
  return {
    animation: false,
    color: PALETTE,
    grid: { left: 48, right: 14, top: multi ? 30 : 12, bottom: 28 },
    tooltip: {
      trigger: 'axis',
      confine: true,
      axisPointer: { type: 'cross', label: { backgroundColor: '#555' } },
      valueFormatter: (v) => (v == null ? '—' : (Math.round(v * 10) / 10) + props.unit),
    },
    legend: multi ? { top: 0, textStyle: { color: text }, type: 'scroll' } : undefined,
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: border } },
      axisLabel: { color: text, hideOverlap: true },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      max: props.yMax,
      axisLabel: { color: text, formatter: (v) => v + props.unit },
      splitLine: { lineStyle: { color: border, opacity: 0.4 } },
    },
    series: props.series.map((s, i) => ({
      name: s.name,
      type: 'line',
      showSymbol: false,
      smooth: false,
      lineStyle: { width: 1.6 },
      areaStyle: multi ? undefined : { opacity: 0.08 },
      data: labels.map((d, j) => [d, s.data[j] == null ? null : s.data[j]]),
    })),
  }
})
</script>
