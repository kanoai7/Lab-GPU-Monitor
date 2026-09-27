<template>
  <!-- 统一内联 SVG 图标：描边风（currentColor 跟随文字/主题色），24 网格。 -->
  <!-- Unified inline SVG icons: stroke style following currentColor, 24-grid. -->
  <svg
    :width="size" :height="size" viewBox="0 0 24 24"
    fill="none" stroke="currentColor" :stroke-width="sw"
    stroke-linecap="round" stroke-linejoin="round"
    class="icon" :class="'icon-' + name" aria-hidden="true"
  >
    <!-- logo / cpu 芯片：GPU 监控主题标记 -->
    <template v-if="name === 'logo'">
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <rect x="9" y="9" width="6" height="6" rx="1" />
      <path d="M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2" />
    </template>
    <!-- grid / 总览 -->
    <template v-else-if="name === 'grid'">
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </template>
    <!-- settings / 设置（推子/滑块） -->
    <template v-else-if="name === 'settings'">
      <path d="M20 7h-9M14 17H5" />
      <circle cx="17" cy="17" r="3" />
      <circle cx="7" cy="7" r="3" />
    </template>
    <!-- sun / 亮色 -->
    <template v-else-if="name === 'sun'">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </template>
    <!-- moon / 暗色 -->
    <template v-else-if="name === 'moon'">
      <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
    </template>
    <!-- logout / 登出 -->
    <template v-else-if="name === 'logout'">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
    </template>
    <!-- close / 关闭·删除 -->
    <template v-else-if="name === 'close'">
      <path d="M18 6 6 18M6 6l12 12" />
    </template>
    <!-- cpu / 处理器 -->
    <template v-else-if="name === 'cpu'">
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <rect x="9" y="9" width="6" height="6" rx="1" />
      <path d="M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2" />
    </template>
    <!-- memory / 内存条 -->
    <template v-else-if="name === 'memory'">
      <path d="M2 7a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v1.1a2 2 0 0 0 0 3.8V17a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-5.1a2 2 0 0 0 0-3.8Z" />
      <path d="M6 19v-3M10 19v-3M14 19v-3M18 19v-3M8 11V9M12 11V9M16 11V9M2 15h20" />
    </template>
    <!-- gpu / 显卡（带风扇） -->
    <template v-else-if="name === 'gpu'">
      <rect x="2" y="7" width="20" height="10" rx="2" />
      <circle cx="8" cy="12" r="3.2" />
      <path d="M14 10.5h5M14 13.5h5" />
    </template>
    <!-- disk / 硬盘 -->
    <template v-else-if="name === 'disk'">
      <path d="M22 12H2" />
      <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
      <path d="M6 16h.01M10 16h.01" />
    </template>
    <!-- network / 网络（上下行） -->
    <template v-else-if="name === 'network'">
      <path d="M8 3v18M4 7l4-4 4 4M16 21V3M20 17l-4 4-4-4" />
    </template>
    <!-- activity / 磁盘 IO·速率 -->
    <template v-else-if="name === 'activity'">
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </template>
    <!-- chart / 历史趋势 -->
    <template v-else-if="name === 'chart'">
      <path d="M3 3v18h18" />
      <path d="m19 9-5 5-4-4-3 3" />
    </template>
    <!-- thermometer / 温度 -->
    <template v-else-if="name === 'thermometer'">
      <path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z" />
    </template>
    <!-- zap / 功耗 -->
    <template v-else-if="name === 'zap'">
      <path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z" />
    </template>
    <!-- check / 在线 -->
    <template v-else-if="name === 'check'">
      <path d="M20 6 9 17l-5-5" />
    </template>
    <!-- arrow-left / 返回 -->
    <template v-else-if="name === 'arrow-left'">
      <path d="M19 12H5M12 19l-7-7 7-7" />
    </template>
    <!-- grip / 拖动手柄 -->
    <template v-else-if="name === 'grip'">
      <g fill="currentColor" stroke="none">
        <circle cx="9" cy="5" r="1.3" /><circle cx="9" cy="12" r="1.3" /><circle cx="9" cy="19" r="1.3" />
        <circle cx="15" cy="5" r="1.3" /><circle cx="15" cy="12" r="1.3" /><circle cx="15" cy="19" r="1.3" />
      </g>
    </template>
  </svg>
</template>

<script setup>
const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 18 },
  // 描边粗细：小尺寸略加粗更清晰。 / Slightly thicker stroke at small sizes for clarity.
  sw: { type: [Number, String], default: 2 },
})
</script>

<style scoped>
.icon { display: inline-block; flex: none; vertical-align: middle; }
</style>
