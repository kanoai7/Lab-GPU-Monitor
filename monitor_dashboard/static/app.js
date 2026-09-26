// Lab GPU Monitor — dashboard frontend / 仪表盘前端
// 轮询 /api/data，渲染每台服务器的卡片。 / Polls /api/data and renders a card per server.

(function () {
  "use strict";

  // --- 主题：localStorage 优先，否则用服务端渲染的默认值 / Theme: localStorage first, else server-rendered default ---
  const root = document.documentElement;
  try {
    const saved = localStorage.getItem("theme");
    if (saved) root.setAttribute("data-theme", saved);
  } catch (e) {}
  const toggle = document.getElementById("theme-toggle");
  if (toggle) {
    toggle.addEventListener("click", function () {
      const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("theme", next); } catch (e) {}
    });
  }

  const cardsEl = document.getElementById("cards");
  const emptyEl = document.getElementById("empty-hint");
  const pill = document.getElementById("status-pill");
  let alerts = { gpu_temp: 85, gpu_mem_percent: 95, disk_percent: 90 };
  let display = { show_processes: true, show_offline: true, compact: false };
  let pollInterval = 2000;

  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const num = (v, d = 0) => (typeof v === "number" ? v.toFixed(d) : "—");

  function level(value, warnAt, critAt) {
    if (value >= critAt) return "crit";
    if (value >= warnAt) return "warn";
    return "ok";
  }

  function bar(label, used, total, unit, pct, lvl) {
    const w = Math.max(0, Math.min(100, pct || 0));
    return `<div class="metric">
      <div class="metric-top"><span>${esc(label)}</span>
        <span><b>${used}</b>${total != null ? " / " + total + " " + unit : (unit || "")} · ${num(pct, 0)}%</span></div>
      <div class="bar ${lvl}"><span style="width:${w}%"></span></div></div>`;
  }

  function gpuBlock(g) {
    const memLvl = level(g.memory_percent || 0, alerts.gpu_mem_percent - 15, alerts.gpu_mem_percent);
    const tempBadge = (g.temperature || 0) >= alerts.gpu_temp ? "crit"
      : (g.temperature || 0) >= alerts.gpu_temp - 10 ? "warn" : "";
    let procs = "";
    if (display.show_processes && g.processes && g.processes.length) {
      procs = '<div class="procs">' + g.processes.map((p) =>
        `<div class="proc"><b>${esc(p.username || "?")}</b> · pid ${p.pid} · ${num(p.gpu_memory_usage_mb, 0)}MB · ${esc((p.name || p.cmdline || "").slice(0, 40))}</div>`
      ).join("") + "</div>";
    }
    return `<div class="gpu">
      <div class="gpu-name"><span><span class="idx">#${g.index}</span> ${esc(g.name)}</span>
        <span class="badge ${tempBadge}">${num(g.temperature, 0)}℃${g.fan_speed != null ? " · " + g.fan_speed + "%" : ""}</span></div>
      ${bar("利用率 / Util", num(g.utilization, 0), null, "%", g.utilization, level(g.utilization || 0, 101, 102))}
      ${bar("显存 / VRAM", num(g.memory_used, 0), num(g.memory_total, 0), "MB", g.memory_percent, memLvl)}
      <div class="kv"><span>功耗 / Power <b>${num(g.power_draw, 0)}/${num(g.power_limit, 0)}W</b></span></div>
      ${procs}</div>`;
  }

  function serverCard(name, entry) {
    const online = entry.status === "online";
    const d = entry.data || {};
    if (!online) {
      return `<div class="card offline"><div class="card-head">
        <span class="card-title"><span class="dot offline"></span>${esc(name)}</span>
        <span class="badge crit">离线 / offline</span></div>
        <div class="card-body"><p class="muted">${esc(entry.error || "无法连接 / unreachable")}</p></div></div>`;
    }
    const sys = d.system || {}, cpu = d.cpu || {}, mem = d.memory || {}, net = d.network || {};
    const gpus = (d.gpus || []).map(gpuBlock).join("");
    const disks = (d.disks || []).map((dk) =>
      bar(esc(dk.mountpoint || dk.device), num(dk.used_gb, 0), num(dk.total_gb, 0), "GB", dk.percent,
        level(dk.percent || 0, alerts.disk_percent - 10, alerts.disk_percent))).join("");
    return `<div class="card"><div class="card-head">
        <span class="card-title"><span class="dot online"></span>${esc(name)}</span>
        <span class="muted mono">${esc(sys.hostname || "")}</span></div>
      <div class="card-body">
        ${bar("CPU", num(cpu.percent, 0), null, "%", cpu.percent, level(cpu.percent || 0, 80, 95))}
        ${bar("内存 / RAM", num(mem.used_gb, 0), num(mem.total_gb, 0), "GB", mem.percent, level(mem.percent || 0, 80, 95))}
        <div class="kv"><span>↑ <b>${num(net.send_mbps, 1)}</b> Mb/s</span><span>↓ <b>${num(net.recv_mbps, 1)}</b> Mb/s</span>
          <span>负载 / Load <b>${cpu.load_avg ? cpu.load_avg.join(" ") : "—"}</b></span>
          <span>运行 / Up <b>${esc(sys.uptime_str || "—")}</b></span></div>
        ${gpus ? '<div class="subhead">GPU</div>' + gpus : ""}
        ${disks ? '<div class="subhead">磁盘 / Disks</div>' + disks : ""}
      </div></div>`;
  }

  async function refresh() {
    try {
      const res = await fetch("/api/data", { cache: "no-store" });
      if (res.status === 401) { window.location.href = "/login"; return; }
      const payload = await res.json();
      const servers = payload.servers || {};
      const cfg = payload.config || {};
      if (cfg.alerts) alerts = Object.assign(alerts, cfg.alerts);
      if (cfg.display) display = Object.assign(display, cfg.display);
      if (cfg.poll_interval) pollInterval = Math.max(1, cfg.poll_interval) * 1000;

      const names = Object.keys(servers).sort();
      const visible = names.filter((n) => display.show_offline || servers[n].status === "online");
      emptyEl.hidden = names.length !== 0;
      cardsEl.innerHTML = visible.map((n) => serverCard(n, servers[n])).join("");

      const onlineCount = names.filter((n) => servers[n].status === "online").length;
      pill.textContent = `${onlineCount}/${names.length} 在线 / online · ${new Date().toLocaleTimeString()}`;
      pill.className = "pill " + (onlineCount === names.length && names.length ? "online" : onlineCount ? "stale" : "");
    } catch (e) {
      pill.textContent = "同步失败 / sync failed";
      pill.className = "pill stale";
    } finally {
      setTimeout(refresh, pollInterval);
    }
  }

  refresh();
})();

