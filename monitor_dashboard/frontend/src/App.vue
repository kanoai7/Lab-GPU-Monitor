<template>
  <header class="topbar">
    <div class="brand">
      <span class="brand-mark"><Icon name="logo" :size="20" /></span>
      <span class="brand-name">{{ title }}</span>
    </div>
    <nav class="topnav">
      <router-link class="navlink" :class="{ active: $route.name === 'overview' }" to="/"><Icon name="grid" :size="16" /><span>总览 / Overview</span></router-link>
      <router-link class="navlink" :class="{ active: $route.name === 'settings' }" to="/settings"><Icon name="settings" :size="16" /><span>设置 / Settings</span></router-link>
      <a v-if="authOn" class="navlink" href="/logout"><Icon name="logout" :size="16" /><span>登出 / Logout</span></a>
      <button class="icon-btn" :title="themeName === 'dark' ? '切换到亮色 / Switch to light' : '切换到暗色 / Switch to dark'" @click="toggleTheme">
        <Icon :name="themeName === 'dark' ? 'sun' : 'moon'" :size="18" />
      </button>
    </nav>
  </header>

  <router-view v-slot="{ Component }">
    <transition name="fade" mode="out-in">
      <component :is="Component" />
    </transition>
  </router-view>

  <div class="footer">Lab GPU Monitor · v2.0</div>
</template>

<script setup>
import { ref, watchEffect, onMounted } from 'vue'
import { themeName, toggleTheme } from './theme.js'
import { api } from './api.js'
import Icon from './components/Icon.vue'

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
