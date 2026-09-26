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
