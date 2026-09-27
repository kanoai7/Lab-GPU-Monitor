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
import { cssVar } from '../util.js'

const props = defineProps({
  title: String,
  ts: { type: Array, default: () => [] },       // epoch 秒 / epoch seconds
  series: { type: Array, default: () => [] },     // [{name, data:[...]}]
  unit: { type: String, default: '' },
  yMax: { type: Number, default: null },
  smooth: { type: Boolean, default: true },       // #3 抖动：轻平滑 / gentle smoothing
  area: { type: Boolean, default: true },         // 面积填充 / area fill
  mirror: { type: Boolean, default: false },      // #4 上下镜像（上行+ / 下行-）/ mirror second series downward
})

// 调色板（多折线区分）。 / Palette for multi-line separation.
const PALETTE = ['#4c8dff', '#3fb950', '#d99a2b', '#f8604f', '#a371f7', '#39c5cf', '#db61a2', '#e3b341']

function hexToRgba(hex, a) {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
  if (!m) return hex
  return `rgba(${parseInt(m[1], 16)},${parseInt(m[2], 16)},${parseInt(m[3], 16)},${a})`
}

const option = computed(() => {
  themeName.value // 依赖主题触发重算 / depend on theme to recompute
  const text = cssVar('--muted', '#8b949e')
  const border = cssVar('--border', '#2a3038')
  const labels = props.ts.map((t) => new Date(t * 1000))
  const multi = props.series.length > 1
  const areaTopOpacity = multi && !props.mirror ? 0.10 : 0.30
  return {
    animation: false,
    color: PALETTE,
    grid: { left: 50, right: 16, top: multi ? 30 : 14, bottom: 28 },
    tooltip: {
      trigger: 'axis', confine: true,
      axisPointer: { type: 'cross', label: { backgroundColor: cssVar('--panel-3', '#555') } },
      valueFormatter: (v) => (v == null ? '—' : (Math.round(Math.abs(v) * 10) / 10) + props.unit),
    },
    legend: multi ? { top: 0, textStyle: { color: text }, type: 'scroll' } : undefined,
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: border } },
      axisLabel: { color: text, hideOverlap: true },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value', max: props.yMax, min: props.mirror ? undefined : (props.yMax ? 0 : undefined),
      axisLabel: { color: text, formatter: (v) => Math.abs(v) + props.unit },
      splitLine: { lineStyle: { color: border, opacity: 0.35 } },
    },
    series: props.series.map((s, i) => {
      const col = PALETTE[i % PALETTE.length]
      const sign = (props.mirror && i === 1) ? -1 : 1
      return {
        name: s.name, type: 'line', showSymbol: false,
        smooth: props.smooth ? 0.3 : false, sampling: 'lttb',
        lineStyle: { width: 1.8 },
        areaStyle: props.area ? {
          opacity: 1,
          color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [{ offset: 0, color: hexToRgba(col, areaTopOpacity) }, { offset: 1, color: hexToRgba(col, 0) }] },
        } : undefined,
        data: labels.map((d, j) => [d, s.data[j] == null ? null : s.data[j] * sign]),
      }
    }),
  }
})
</script>
