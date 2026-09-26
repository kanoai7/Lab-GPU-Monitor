// API 封装：统一 fetch，401 跳登录页；轮询实时快照 / 按需拉历史。
// API layer: unified fetch, 401 -> login page; poll live snapshot / pull history on demand.

async function jget(url) {
  const r = await fetch(url, { headers: { Accept: 'application/json' } })
  if (r.status === 401) {
    window.location.href = '/login?next=' + encodeURIComponent(location.pathname)
    throw new Error('unauthorized')
  }
  if (!r.ok) throw new Error('HTTP ' + r.status)
  return r.json()
}

async function jpost(url, body) {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body || {}),
  })
  if (r.status === 401) {
    window.location.href = '/login?next=' + encodeURIComponent(location.pathname)
    throw new Error('unauthorized')
  }
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.error || 'HTTP ' + r.status)
  return data
}

export const api = {
  data: () => jget('/api/data'),
  history: (host, range) =>
    jget(`/api/history?host=${encodeURIComponent(host)}&range=${encodeURIComponent(range)}`),
  getConfig: () => jget('/api/config'),
  saveConfig: (body) => jpost('/api/config', body),
}
