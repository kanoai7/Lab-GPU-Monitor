// 主题状态：暗/亮，持久化到 localStorage，跨会话记忆。 / Theme state: dark/light, persisted to localStorage.
import { ref } from 'vue'

const KEY = 'lgm-theme'
function initial() {
  try {
    const v = localStorage.getItem(KEY)
    if (v === 'light' || v === 'dark') return v
  } catch (e) {}
  return 'dark'
}

export const themeName = ref(initial())

export function toggleTheme() {
  themeName.value = themeName.value === 'dark' ? 'light' : 'dark'
  try { localStorage.setItem(KEY, themeName.value) } catch (e) {}
}
