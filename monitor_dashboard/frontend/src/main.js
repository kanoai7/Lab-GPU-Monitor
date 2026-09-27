// 应用入口：注册 ECharts 需要的模块（按需，控体积），挂载 App。
// App entry: register the ECharts modules we use (tree-shaken), mount App.
import { createApp } from 'vue'
import App from './App.vue'
import router from './router.js'

import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  MarkLineComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

// 字体：随构建打包（离线可用，部署端无需 CDN）。 / Fonts bundled into the build (offline, no CDN).
import '@fontsource-variable/inter'
import '@fontsource-variable/jetbrains-mono'
// 中文正文字体：思源黑体（Noto Sans SC），随构建打包、按字重变量、按需子集加载。
// Chinese body font (Noto Sans SC), bundled + variable-weight + unicode-range subset.
import '@fontsource-variable/noto-sans-sc'

use([
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  MarkLineComponent,
  CanvasRenderer,
])

import './styles.css'

createApp(App).use(router).mount('#app')
