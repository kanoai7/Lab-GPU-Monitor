<template>
  <header class="topbar">
    <div class="brand">
      <span class="brand-mark">◆</span>
      <span class="brand-name">{{ title }}</span>
    </div>
    <nav class="topnav">
      <router-link class="navlink" :class="{ active: $route.name === 'overview' }" to="/">总览 / Overview</router-link>
      <router-link class="navlink" :class="{ active: $route.name === 'settings' }" to="/settings">⚙ 设置 / Settings</router-link>
      <a v-if="authOn" class="navlink" href="/logout">登出 / Logout</a>
      <button class="icon-btn" title="切换主题 / Toggle theme" @click="toggleTheme">🌓</button>
    </nav>
  </header>

  <router-view />

  <div class="footer">Lab GPU Monitor · v2.0</div>
</template>

<script setup>
import { ref, watchEffect, onMounted } from 'vue'
import { themeName, toggleTheme } from './theme.js'
import { api } from './api.js'

const title = ref('Lab GPU Monitor')
const authOn = ref(false)

// 主题写入 <html data-theme>，样式表按属性切换。 / Reflect theme onto <html data-theme>.
watchEffect(() => {
  document.documentElement.setAttribute('data-theme', themeName.value)
})

onMounted(async () => {
  try {
    const c = await api.getConfig()
    if (c.title) title.value = c.title
    authOn.value = !!c.auth_enabled
    document.title = c.title || 'Lab GPU Monitor'
  } catch (e) { /* 401 已在 api 层跳转 / 401 handled in api layer */ }
})
</script>
