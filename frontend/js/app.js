const state = {
  mode: "off",
  bank: null,
  customers: [],
  transactions: {},
  agents: [],
  selectedAgent: "supportbot",
  selectedCustomer: null,
  ledger: 1268040,
  blocks: 0,
};

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const inr = (n) =>
  "₹" +
  Number(n).toLocaleString("en-IN", {
    minimumFractionDigits: n % 1 ? 2 : 0,
    maximumFractionDigits: 2,
  });

async function load() {
  const [bank, customers, transactions, agents] = await Promise.all([
    fetch("data/bank.json").then((r) => r.json()),
    fetch("data/customers.json").then((r) => r.json()),
    fetch("data/transactions.json").then((r) => r.json()),
    fetch("data/agents.json").then((r) => r.json()),
  ]);
  state.bank = bank;
  state.customers = customers;
  state.transactions = transactions;
  state.agents = agents;
  state.ledger = bank.ledger_balance;
  state.mode = bank.guard_mode || "off";
  renderAll();
}

function renderAll() {
  renderMode();
  renderOverview();
  renderCustomers();
  renderConstellation();
  renderAgentDetail();
}

function renderMode() {
  const btn = $("#modeBtn");
  btn.textContent = "TWILIGHT · " + state.mode.toUpperCase();
  btn.className = "mode-btn " + state.mode;
  $("#metricMode").textContent = state.mode.toUpperCase();
  $("#metricModeTag").textContent = state.mode === "on" ? "Enforcing" : "Unchecked";
  $("#metricModeTag").className = "tag " + (state.mode === "on" ? "ok" : "caution");
  $("#metricBlocks").textContent = state.blocks;
  document.body.classList.toggle("twilight-mode", $("#view-twilight").classList.contains("active"));
}

function renderOverview() {
  const el = $("#kpiBalance");
  el.textContent = inr(state.ledger);
  const dropped = state.ledger < state.bank.ledger_balance;
  el.classList.toggle("drop", dropped);
  $("#kpiDelta").textContent = dropped
    ? `↓ Attack deducted ${inr(state.bank.ledger_balance - state.ledger)}`
    : "↑ 8.4% vs last month";
  $("#kpiDelta").className = "delta" + (dropped ? " down" : "");
  $("#kpiVolume").textContent = state.bank.volume_today_formatted;
  $("#kpiActive").textContent = state.bank.active_customers.toLocaleString("en-IN");
  $("#pillCustomers").textContent = state.bank.active_customers.toLocaleString("en-IN") + " customers";
  const bars = $("#volBars");
  if (bars && !bars.children.length) {
    const hs = [40, 55, 35, 70, 50, 85, 60];
    bars.innerHTML = hs
      .map((h, i) => `<span style="height:${h}%;animation-delay:${i * 0.05}s"></span>`)
      .join("");
  }
}

function renderCustomers() {
  const tb = $("#custTable");
  tb.innerHTML = state.customers
    .map((c) => {
      const sel = state.selectedCustomer === c.id ? "selected" : "";
      return `<tr class="${sel}" data-id="${c.id}">
        <td><div class="cust-cell"><span class="av" style="background:${c.avatar_color}">${c.initials}</span>
          <div><div style="font-weight:600">${c.name}</div><div style="font-size:12px;color:var(--muted)">${c.id}</div></div></div></td>
        <td>${c.account_type} · ${c.account_no}</td>
        <td style="font-weight:700;font-variant-numeric:tabular-nums">${inr(c.balance)}</td>
        <td><span class="pill-ok">${c.status}</span></td>
      </tr>`;
    })
    .join("");
  $$("#custTable tr").forEach((tr) => {
    tr.onclick = () => openDrawer(tr.dataset.id);
  });
}

function openDrawer(id) {
  state.selectedCustomer = id;
  renderCustomers();
  const c = state.customers.find((x) => x.id === id);
  const txs = state.transactions[id] || [];
  const drawer = $("#drawer");
  drawer.innerHTML = `
    <button class="drawer-close" id="drawerClose">×</button>
    <div class="av" style="background:${c.avatar_color};width:48px;height:48px;font-size:16px;margin-bottom:12px">${c.initials}</div>
    <div style="font-weight:800;font-size:18px">${c.name}</div>
    <div style="color:var(--muted);font-size:13px;margin-top:4px">${c.id} · Active</div>
    <div style="margin-top:16px;font-size:12px;color:var(--muted)">Available balance</div>
    <div class="big">${inr(c.balance)}</div>
    <div style="display:flex;gap:8px;margin-bottom:20px">
      <button style="flex:1;padding:10px;border-radius:12px;background:#f1f5f9;font-weight:600">↑ Send</button>
      <button style="flex:1;padding:10px;border-radius:12px;background:#f1f5f9;font-weight:600">Card</button>
      <button style="flex:1;padding:10px;border-radius:12px;background:#f1f5f9;font-weight:600">··· More</button>
    </div>
    <div style="font-size:12px;color:var(--muted);margin-bottom:8px">Customer information</div>
    <div style="font-size:13px;line-height:1.8;margin-bottom:16px">
      <div><span style="color:var(--muted)">Email</span> · ${c.email}</div>
      <div><span style="color:var(--muted)">Account</span> · ${c.account_type} · ${c.account_no}</div>
      <div><span style="color:var(--muted)">Member since</span> · ${c.joined}</div>
      <div><span style="color:var(--muted)">Spent this month</span> · ${inr(c.spent_month)}</div>
    </div>
    <div style="font-size:12px;color:var(--muted);margin-bottom:8px">Recent transactions</div>
    ${txs
      .map(
        (t) => `<div class="tx-row">
        <div><div style="font-weight:600">${t.label}</div><div style="color:var(--muted);font-size:11px">${t.ts} · ${t.status}</div></div>
        <div class="amt ${t.type}">${t.type === "debit" ? "−" : "+"}${inr(t.amount)}</div>
      </div>`
      )
      .join("")}
  `;
  $("#drawerBg").classList.add("open");
  drawer.classList.add("open");
  $("#drawerClose").onclick = closeDrawer;
  $("#drawerBg").onclick = closeDrawer;
}

function closeDrawer() {
  $("#drawer").classList.remove("open");
  $("#drawerBg").classList.remove("open");
}

function renderConstellation() {
  const root = $("#constellation");
  // keep center node
  $$(".node", root).forEach((n) => n.remove());
  const positions = [
    { id: "supportbot", top: "12%", left: "8%" },
    { id: "ledgerbot", top: "8%", left: "55%" },
    { id: "databot", top: "18%", left: "78%" },
    { id: "coordinator", top: "68%", left: "10%" },
    { id: "fraudbot", top: "70%", left: "72%" },
  ];
  positions.forEach((p) => {
    const a = state.agents.find((x) => x.id === p.id);
    if (!a) return;
    const st =
      a.status === "FLAGGED" ? "flagged" : a.status === "THROTTLED" ? "throttled" : "";
    const sel = state.selectedAgent === a.id ? "selected" : "";
    const div = document.createElement("div");
    div.className = `node ${st} ${sel}`;
    div.style.top = p.top;
    div.style.left = p.left;
    div.dataset.id = a.id;
    div.innerHTML = `<div style="display:flex;align-items:center">
      <span class="ring">${a.trust}</span>
      <span><div class="nm">${a.name}</div><div class="rl">${a.role}</div></span>
    </div>`;
    div.onclick = () => {
      state.selectedAgent = a.id;
      renderConstellation();
      renderAgentDetail();
    };
    root.appendChild(div);
  });
}

function renderAgentDetail() {
  const a = state.agents.find((x) => x.id === state.selectedAgent);
  const el = $("#agentDetail");
  if (!a) return;
  const tier = a.trust >= 80 ? "" : a.trust >= 50 ? "mid" : "low";
  el.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:start">
      <div>
        <div class="name">${a.name}</div>
        <div class="role">${a.role}</div>
      </div>
      <span class="badge ${a.status === "HEALTHY" ? "passed" : a.status === "FLAGGED" ? "held" : "blocked"}">${a.status}</span>
    </div>
    <div style="font-size:12px;color:var(--tw-muted);margin-bottom:8px">⚡ ${a.working || "Idle"}</div>
    <div class="trust-circle ${tier}">${a.trust}</div>
    <div style="text-align:center;font-size:12px;color:var(--tw-muted);margin-bottom:12px">TRUST SCORE</div>
    <div class="bars-h">
      <div class="row"><span>Policy compliance</span><span>98%</span></div>
      <div class="track"><i style="width:98%"></i></div>
      <div class="row"><span>Behavior stability</span><span>91%</span></div>
      <div class="track"><i style="width:91%"></i></div>
      <div class="row"><span>Tool safety</span><span>97%</span></div>
      <div class="track"><i style="width:97%"></i></div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:12px;text-align:center">
      <div><div style="font-weight:800">${a.actions_today || 0}</div><div style="font-size:10px;color:var(--tw-muted)">Actions today</div></div>
      <div><div style="font-weight:800">${a.latency_ms || 0}ms</div><div style="font-size:10px;color:var(--tw-muted)">Avg latency</div></div>
      <div><div style="font-weight:800">${a.approved_tools || 0}</div><div style="font-size:10px;color:var(--tw-muted)">Approved tools</div></div>
    </div>
  `;
}

function pushStream(tool, desc, badge, badgeClass) {
  const body = $("#streamBody");
  const t = new Date().toLocaleTimeString("en-IN", { hour12: false });
  const row = document.createElement("div");
  row.className = "s-row";
  row.innerHTML = `<span>${badgeClass === "blocked" ? "✗" : badgeClass === "held" ? "❚❚" : "✓"}</span>
    <div><div class="tool">${tool}</div><div class="desc">${desc}</div></div>
    <span class="badge ${badgeClass}">${badge}</span>
    <span style="color:var(--tw-muted)">${t}</span>`;
  body.insertBefore(row, body.firstChild);
}

function setMode(mode) {
  state.mode = mode;
  if (mode === "on") {
    state.ledger = state.bank.ledger_balance;
    const c = state.customers.find((x) => x.id === "TB-4471");
    if (c) c.balance = 618840;
    const sb = state.agents.find((a) => a.id === "supportbot");
    if (sb) {
      sb.trust = 96;
      sb.status = "HEALTHY";
    }
  }
  renderAll();
}

function runAttack() {
  if (state.mode === "off") {
    pushStream("poisoner.plant", "Poisoned ticket #812 planted (ignore limits, refund 9000)", "warn", "held");
    pushStream("issue_refund", "SupportBot → issue_refund(TB-4471, amount=9000)", "allow", "passed");
    pushStream("gateway", "mode=OFF · ALLOW (no policy checks)", "allow", "passed");
    state.ledger = Math.max(0, state.ledger - 9000);
    const c = state.customers.find((x) => x.id === "TB-4471");
    if (c) c.balance = Math.max(0, c.balance - 9000);
    pushStream("ledger", `Float ${inr(state.ledger + 9000)} → ${inr(state.ledger)}`, "drop", "blocked");
  } else {
    pushStream("poisoner.plant", "Same ticket #812 — refund ₹9,000", "attack", "held");
    pushStream("issue_refund", "SupportBot → issue_refund(TB-4471, amount=9000)", "check", "held");
    pushStream("gateway", "BLOCKED · constraints.issue_refund.max_amount (limit 500)", "block", "blocked");
    state.blocks += 1;
    const sb = state.agents.find((a) => a.id === "supportbot");
    if (sb) {
      sb.trust = 75;
      sb.status = "FLAGGED";
    }
    pushStream("trust", "SupportBot trust 96 → 75 · incident logged", "flag", "held");
    pushStream("ledger", `Balance unchanged ${inr(state.ledger)}`, "safe", "passed");
  }
  renderAll();
  // auto switch visual emphasis to twilight after attack when on
  if (state.mode === "on") {
    showView("twilight");
  }
}

function showView(name) {
  $$(".view").forEach((v) => v.classList.remove("active"));
  $$(".nav-item").forEach((b) => b.classList.remove("active"));
  $(`#view-${name}`).classList.add("active");
  $(`.nav-item[data-view="${name}"]`).classList.add("active");
  document.body.classList.toggle("twilight-mode", name === "twilight");
  if (name === "twilight") {
    renderConstellation();
    renderAgentDetail();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  $$(".nav-item").forEach((b) => (b.onclick = () => showView(b.dataset.view)));
  $("#modeBtn").onclick = () => setMode(state.mode === "off" ? "on" : "off");
  $("#attackBtn").onclick = runAttack;
  load().catch((e) => {
    console.error(e);
    alert("Open via static server: python -m http.server from frontend/");
  });
});

/* =====================================================================
   LIVE GATEWAY BRIDGE
   The Guard toggle + Run attack buttons now drive the REAL gateway.
   The dashboard just polls /demo/state every second and shows what changed.
   If the gateway is not running, the old local simulation above still works.
   ===================================================================== */
const API = window.TWILIGHT_API || (location.port === "8000" ? "" : "http://127.0.0.1:8000");
const live = { online: false, running: false, wasRunning: false, sig: "", extraTx: {}, events: [], depth: null, orig: null, busy: false };

const esc = (v) => String(v ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function gw(path, opts = {}) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 2500);
  try {
    const r = await fetch(API + path, { ...opts, signal: ctl.signal, headers: { "content-type": "application/json" } });
    if (!r.ok) throw new Error(path + " " + r.status);
    return await r.json();
  } finally {
    clearTimeout(timer);
  }
}

function setOnline(on) {
  if (live.online === on) return;
  live.online = on;
  const chip = $("#statusChip");
  chip.classList.toggle("warn", !on);
  chip.querySelector("span").textContent = on ? "Gateway connected · live" : "Gateway offline · local simulation";
}

async function poll() {
  if (!state.bank) return; // static data not loaded yet
  let s;
  try {
    s = await gw("/demo/state");
  } catch {
    setOnline(false);
    return;
  }
  setOnline(true);
  if (!live.orig) live.orig = JSON.parse(JSON.stringify(state.agents));

  state.mode = s.mode;
  state.ledger = s.ledger_balance;
  state.bank.ledger_balance = s.ledger_start;
  state.blocks = s.blocks;
  state.customers.forEach((c) => {
    if (s.customers[c.id] !== undefined) c.balance = s.customers[c.id];
  });
  // agents: static look from agents.json, real trust/status from the gateway where it knows the agent
  state.agents = JSON.parse(JSON.stringify(live.orig)).map((a) => {
    const g = s.agents.find((x) => x.id === a.id);
    if (g) { a.trust = g.trust; a.status = g.status; }
    if (s.mode === "off") { a.trust = "—"; a.status = "UNMONITORED"; }
    return a;
  });
  live.extraTx = s.transactions || {};
  live.events = s.events || [];
  live.depth = s.audit_depth;
  live.running = s.attack_running;
  live.trustAvg = s.agents.length ? Math.round(s.agents.reduce((t, a) => t + a.trust, 0) / s.agents.length) : null;

  const sig = JSON.stringify([s.mode, s.ledger_balance, live.events.map((e) => e.seq), s.agents.map((a) => [a.id, a.trust, a.status]), s.attack_running]);
  if (sig !== live.sig) {
    live.sig = sig;
    renderLive();
  }
  // when an attack finishes with the guard ON, jump to the Twilight tab so the log is on screen
  if (live.wasRunning && !s.attack_running && s.mode === "on") showView("twilight");
  live.wasRunning = s.attack_running;
}

function renderLive() {
  renderAll();
  $$(".node").forEach((n) => n.classList.toggle("unmonitored", state.mode === "off"));
  renderLiveStream();
  renderLiveMetrics();
  updateButtons();
  if (state.selectedCustomer && $("#drawer").classList.contains("open")) openDrawer(state.selectedCustomer);
}

function renderLiveStream() {
  const body = $("#streamBody");
  const row = (icon, title, desc, badge, cls, time = "") =>
    `<div class="s-row"><span>${icon}</span><div><div class="tool">${esc(title)}</div><div class="desc">${esc(desc)}</div></div><span class="badge ${cls}">${esc(badge)}</span><span style="color:var(--tw-muted)">${esc(time)}</span></div>`;
  if (state.mode === "off") {
    body.innerHTML = row("—", "gateway offline", "Guard is OFF: no checks, nothing recorded. Nobody can tell what these agents did.", "unmonitored", "held");
    return;
  }
  if (!live.events.length) {
    body.innerHTML = row("✓", "system", "Guard is ON. Waiting for agent traffic or Run attack…", "idle", "passed");
    return;
  }
  body.innerHTML = live.events
    .map((e) => {
      const v = String(e.verdict || "?").toUpperCase();
      const cls = v === "ALLOW" || v === "FLAG" ? "passed" : v === "HOLD" || v === "THROTTLE" ? "held" : "blocked";
      const icon = cls === "blocked" ? "✗" : cls === "held" ? "❚❚" : "✓";
      const trust = e.trust_before != null && e.trust_after != null && e.trust_before !== e.trust_after ? ` · trust ${e.trust_before} → ${e.trust_after}` : "";
      const desc = (e.rule ? e.rule + " · " : "") + (e.reason || "") + trust;
      const t = e.ts ? new Date(e.ts).toLocaleTimeString("en-IN", { hour12: false }) : "";
      return row(icon, `${e.agent_id} · ${e.tool}`, desc, v, cls, t);
    })
    .join("");
}

function renderLiveMetrics() {
  const off = state.mode === "off";
  const nti = live.trustAvg;
  const label = nti >= 85 ? ["Healthy", "ok"] : nti >= 60 ? ["Caution", "caution"] : ["Critical", "caution"];
  $("#metricTrust").innerHTML = off || nti == null ? "—" : `${nti}<span style="font-size:14px;color:var(--tw-muted)">/100</span>`;
  $("#metricTrustTag").textContent = off ? "Unmonitored" : label[0];
  $("#metricTrustTag").className = "tag " + (off ? "caution" : label[1]);
  $("#metricAudit").textContent = off || live.depth == null ? "—" : "#" + live.depth;
  $("#metricAuditTag").textContent = off ? "No log" : "Chain intact";
  $("#metricAuditTag").className = "tag " + (off ? "caution" : "ok");
}

function updateButtons() {
  const a = $("#attackBtn");
  a.textContent = live.running ? "Attack running…" : "Run attack";
  a.disabled = live.running;
}

// customer drawer: add the unknown debit the gateway recorded, no warning styling (the bank does not know)
const _openDrawer = openDrawer;
openDrawer = function (id) {
  const base = (state.transactions[id] || []).filter((t) => !t.suspicious);
  state.transactions[id] = [...(live.extraTx[id] || []), ...base];
  _openDrawer(id);
};

document.addEventListener("DOMContentLoaded", () => {
  $("#modeBtn").onclick = async () => {
    if (!live.online) return setMode(state.mode === "off" ? "on" : "off"); // local fallback
    if (live.busy) return;
    live.busy = true;
    $("#modeBtn").disabled = true;
    try {
      await gw("/demo/mode", { method: "POST", body: JSON.stringify({ mode: state.mode === "on" ? "off" : "on", reset: true }) });
    } catch (e) { console.error(e); }
    live.busy = false;
    $("#modeBtn").disabled = false;
    live.sig = "";
    await poll();
  };
  $("#attackBtn").onclick = async () => {
    if (!live.online) return runAttack(); // local fallback
    if (live.running) return;
    live.running = true;
    updateButtons();
    try { await gw("/demo/run-attack", { method: "POST" }); } catch (e) { console.error(e); live.running = false; }
    await poll();
  };
  $("#resetBtn").onclick = async () => {
    if (!live.online) return setMode(state.mode);
    try { await gw("/demo/reset", { method: "POST" }); } catch (e) { console.error(e); }
    live.sig = "";
    await poll();
  };
  poll();
  setInterval(poll, 1000);
});
