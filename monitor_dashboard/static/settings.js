// Lab GPU Monitor — settings page / 设置页
// 读取 GET /api/config 填充表单，保存时 POST /api/config。 / Loads config via GET /api/config; saves via POST.

(function () {
  "use strict";
  const root = document.documentElement;
  try { const s = localStorage.getItem("theme"); if (s) root.setAttribute("data-theme", s); } catch (e) {}
  const toggle = document.getElementById("theme-toggle");
  if (toggle) toggle.addEventListener("click", function () {
    const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch (e) {}
  });

  const $ = (id) => document.getElementById(id);
  const rowsEl = $("agent-rows");

  function addAgentRow(name, entry) {
    entry = entry || {};
    const host = entry.url ? entry.url : (entry.host || "");
    const port = entry.url ? "" : (entry.port || 48210);
    const div = document.createElement("div");
    div.className = "agent-row";
    div.innerHTML =
      '<input class="field name" placeholder="名称 / name" value="' + (name || "").replace(/"/g, "&quot;") + '">' +
      '<input class="field host" placeholder="主机名/IP 或完整 URL / host or full URL" value="' + String(host).replace(/"/g, "&quot;") + '">' +
      '<input class="field port" type="number" placeholder="48210" value="' + port + '">' +
      '<button class="btn btn-del" type="button" title="删除 / remove">✕</button>';
    div.querySelector(".btn-del").addEventListener("click", () => div.remove());
    rowsEl.appendChild(div);
  }

  function load(cfg) {
    $("s-title").value = cfg.title || "";
    $("s-poll").value = cfg.poll_interval || 2;
    $("s-theme").value = cfg.theme || "dark";
    const d = cfg.display || {};
    $("d-proc").checked = d.show_processes !== false;
    $("d-offline").checked = d.show_offline !== false;
    $("d-compact").checked = !!d.compact;
    const a = cfg.alerts || {};
    $("a-temp").value = a.gpu_temp != null ? a.gpu_temp : 85;
    $("a-mem").value = a.gpu_mem_percent != null ? a.gpu_mem_percent : 95;
    $("a-disk").value = a.disk_percent != null ? a.disk_percent : 90;
    $("sec-enabled").checked = !!cfg.auth_enabled;
    $("sec-note").textContent = cfg.has_password
      ? "已设置密码。/ Password is set."
      : "尚未设置密码，启用鉴权前请先在下方设置。/ No password yet — set one below before enabling auth.";
    rowsEl.innerHTML = "";
    const agents = cfg.agents || {};
    Object.keys(agents).forEach((n) => addAgentRow(n, agents[n]));
    if (!Object.keys(agents).length) addAgentRow("", {});
  }

  function collectAgents() {
    const agents = {};
    rowsEl.querySelectorAll(".agent-row").forEach((row) => {
      const name = row.querySelector(".name").value.trim();
      const host = row.querySelector(".host").value.trim();
      const port = parseInt(row.querySelector(".port").value, 10) || 48210;
      if (!name || !host) return;
      agents[name] = /^https?:\/\//i.test(host) ? { url: host } : { host: host, port: port };
    });
    return agents;
  }

  async function save() {
    const msg = $("save-msg");
    const body = {
      title: $("s-title").value.trim() || "Lab GPU Monitor",
      poll_interval: Math.max(1, parseInt($("s-poll").value, 10) || 2),
      theme: $("s-theme").value,
      agents: collectAgents(),
      display: {
        show_processes: $("d-proc").checked,
        show_offline: $("d-offline").checked,
        compact: $("d-compact").checked,
      },
      alerts: {
        gpu_temp: parseInt($("a-temp").value, 10) || 85,
        gpu_mem_percent: parseInt($("a-mem").value, 10) || 95,
        disk_percent: parseInt($("a-disk").value, 10) || 90,
      },
      auth_enabled: $("sec-enabled").checked,
    };
    const pw = $("sec-pw").value;
    if (pw) body.new_password = pw;

    msg.textContent = "保存中… / saving…";
    try {
      const res = await fetch("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.status === 401) { window.location.href = "/login"; return; }
      const data = await res.json();
      if (!res.ok) { msg.textContent = "错误 / Error: " + (data.error || res.status); return; }
      $("sec-pw").value = "";
      msg.textContent = "已保存 / Saved ✓ " + (data.note || "");
      root.setAttribute("data-theme", body.theme);
      try { localStorage.setItem("theme", body.theme); } catch (e) {}
    } catch (e) {
      msg.textContent = "保存失败 / save failed: " + e;
    }
  }

  $("add-agent").addEventListener("click", () => addAgentRow("", {}));
  $("save-btn").addEventListener("click", save);

  fetch("/api/config", { cache: "no-store" })
    .then((r) => { if (r.status === 401) { window.location.href = "/login"; return {}; } return r.json(); })
    .then(load)
    .catch(() => { $("save-msg").textContent = "无法加载配置 / failed to load config"; });
})();

