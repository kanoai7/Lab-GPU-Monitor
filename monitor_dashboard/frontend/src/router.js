// 路由：总览 / 主机详情 / 设置。history 模式，base 与 Flask SPA 壳一致（/）。
// Router: overview / host detail / settings. History mode, base '/'.
import { createRouter, createWebHistory } from 'vue-router'
import Overview from './views/Overview.vue'
import Host from './views/Host.vue'
import Settings from './views/Settings.vue'

const routes = [
  { path: '/', name: 'overview', component: Overview },
  { path: '/host/:name', name: 'host', component: Host, props: true },
  { path: '/settings', name: 'settings', component: Settings },
]

export default createRouter({
  history: createWebHistory('/'),
  routes,
})
