<template>
  <main class="container settings">
    <div class="page-head"><h1>设置 / Settings</h1></div>

    <div class="panel pad">
      <h2>通用 / General</h2>
      <div class="row"><span>站点名称 / Site title</span><input class="field" v-model="cfg.title" /></div>
      <div class="row"><span>后台轮询间隔（秒）/ Poll interval (s)</span>
        <input class="field" type="number" min="1" step="1" v-model.number="cfg.poll_interval" /></div>
      <div class="row"><span>端口 / Port（改后需重启 / restart to apply）</span>
        <input class="field" type="number" v-model.number="cfg.port" /></div>
    </div>

    <div class="panel pad">
      <h2>监控源 / Agents</h2>
      <div class="agent-row" v-for="(a, i) in agentList" :key="i">
        <input class="field" placeholder="名称 / name" v-model="a.name" />
        <input class="field" placeholder="主机 / host" v-model="a.host" />
        <input class="field port" placeholder="端口" type="number" v-model.number="a.port" />
        <button class="btn btn-del" title="删除 / remove" @click="agentList.splice(i, 1)"><Icon name="close" :size="14" /></button>
      </div>
      <button class="btn" @click="agentList.push({ name: '', host: '', port: 9527 })">+ 添加 Agent / Add</button>
    </div>

    <div class="panel pad">
      <h2>外观 / Appearance</h2>
      <div class="row"><span>默认主题 / Default theme</span>
        <select class="field" v-model="cfg.theme"><option value="dark">暗色 / dark</option><option value="light">浅色 / light</option></select>
      </div>
    </div>

    <div class="panel pad">
      <h2>告警阈值 / Alert thresholds</h2>
      <div class="row"><span>GPU 温度 / GPU temp (°C)</span><input class="field" type="number" v-model.number="cfg.alerts.gpu_temp" /></div>
      <div class="row"><span>GPU 显存 / GPU mem (%)</span><input class="field" type="number" v-model.number="cfg.alerts.gpu_mem_percent" /></div>
      <div class="row"><span>磁盘 / Disk (%)</span><input class="field" type="number" v-model.number="cfg.alerts.disk_percent" /></div>
    </div>

    <div class="panel pad">
      <h2>展示 / Display</h2>
      <label class="check"><input type="checkbox" v-model="cfg.display.show_processes" /> 显示进程 / show processes</label>
      <label class="check"><input type="checkbox" v-model="cfg.display.show_offline" /> 显示离线主机 / show offline hosts</label>
    </div>

    <div class="panel pad">
      <h2>历史保留 / History retention</h2>
      <label class="check"><input type="checkbox" v-model="cfg.history.enabled" /> 记录历史 / record history</label>
      <div class="row"><span>原始保留（小时）/ raw hours</span><input class="field" type="number" min="1" v-model.number="cfg.history.retain_raw_hours" /></div>
      <div class="row"><span>降采样保留（天）/ rollup days</span><input class="field" type="number" min="1" v-model.number="cfg.history.retain_rollup_days" /></div>
    </div>

    <div class="panel pad">
      <h2>安全 / Security</h2>
      <label class="check"><input type="checkbox" v-model="cfg.auth_enabled" /> 启用登录鉴权 / enable auth</label>
      <div class="row"><span>{{ cfg.has_password ? '修改密码 / change password' : '设置密码 / set password' }}</span>
        <input class="field" type="password" placeholder="新密码 / new password" v-model="newPassword" /></div>
      <div class="muted" v-if="cfg.auth_enabled && !cfg.has_password && !newPassword">启用鉴权前需先设置密码 / set a password before enabling auth</div>
    </div>

    <div class="save-bar">
      <span class="muted">{{ hint }}</span>
      <button class="btn btn-primary" :disabled="saving" @click="save">{{ saving ? '保存中… / saving…' : '保存 / Save' }}</button>
    </div>

    <div v-if="toast" class="toast" :class="toastCls">{{ toast }}</div>
  </main>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { api } from '../api.js'
import Icon from '../components/Icon.vue'

const cfg = reactive({
  title: '', port: 48080, poll_interval: 2, theme: 'dark',
  auth_enabled: false, has_password: false,
  alerts: { gpu_temp: 85, gpu_mem_percent: 95, disk_percent: 90 },
  display: { show_processes: true, show_offline: true, compact: false },
  history: { enabled: true, retain_raw_hours: 6, retain_rollup_days: 7 },
})
const agentList = reactive([])
const newPassword = ref('')
const saving = ref(false)
const toast = ref('')
const toastCls = ref('ok')
const hint = ref('')

function flash(msg, ok = true) {
  toast.value = msg; toastCls.value = ok ? 'ok' : 'err'
  setTimeout(() => { toast.value = '' }, 2600)
}

onMounted(async () => {
  try {
    const c = await api.getConfig()
    Object.assign(cfg, {
      title: c.title || '', port: c.port, poll_interval: c.poll_interval, theme: c.theme || 'dark',
      auth_enabled: !!c.auth_enabled, has_password: !!c.has_password,
      alerts: { ...cfg.alerts, ...(c.alerts || {}) },
      display: { ...cfg.display, ...(c.display || {}) },
      history: { ...cfg.history, ...(c.history || {}) },
    })
    agentList.length = 0
    for (const [nm, a] of Object.entries(c.agents || {})) {
      agentList.push({ name: nm, host: a.host || '', port: a.port || 9527, url: a.url || '' })
    }
  } catch (e) { flash('加载配置失败 / load failed: ' + e.message, false) }
})

async function save() {
  // 组装 agents 字典（跳过空名）。 / Build agents dict, skip empty names.
  const agents = {}
  for (const a of agentList) {
    const nm = (a.name || '').trim()
    if (!nm) continue
    agents[nm] = a.url ? { url: a.url } : { host: (a.host || '').trim(), port: Number(a.port) || 9527 }
  }
  if (cfg.auth_enabled && !cfg.has_password && !newPassword.value) {
    flash('启用鉴权前需先设置密码 / set a password first', false); return
  }
  const body = {
    title: cfg.title, port: Number(cfg.port), poll_interval: Number(cfg.poll_interval), theme: cfg.theme,
    agents, alerts: cfg.alerts, display: cfg.display, history: cfg.history,
    auth_enabled: cfg.auth_enabled,
  }
  if (newPassword.value) body.new_password = newPassword.value
  saving.value = true
  try {
    const r = await api.saveConfig(body)
    hint.value = r.note || ''
    if (newPassword.value) { cfg.has_password = true; newPassword.value = '' }
    flash('已保存 / saved')
  } catch (e) {
    flash('保存失败 / save failed: ' + e.message, false)
  } finally { saving.value = false }
}
</script>
