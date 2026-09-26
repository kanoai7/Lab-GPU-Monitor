// Vite 配置：产物直接输出到 Flask 托管的 static/dist；base 指向 /static/dist/ 让资源走 Flask 静态路由。
// Vite config: build straight into Flask-served static/dist; base points at /static/dist/ so assets use Flask's static route.
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: '/static/dist/',
  build: {
    outDir: '../static/dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1500,
  },
  server: {
    // 本地 npm run dev 时把 API 代理到 Flask（默认 48080）。 / Proxy API to Flask during local dev.
    proxy: {
      '/api': 'http://127.0.0.1:48080',
      '/login': 'http://127.0.0.1:48080',
      '/logout': 'http://127.0.0.1:48080',
    },
  },
})
