// Global Checkmate · Mission Control
// Every value from the API — log lines above all, since they echo request
// paths — reaches the page through textContent, never innerHTML.
"use strict";

const POLL_MS = 2000;
const SAMPLES = 60;
const RING = 119.38; // 2π·19
const TOKEN_KEY = "gc-chaos-token";

const $ = (id) => document.getElementById(id);

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "text") node.textContent = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else node.setAttribute(key, value);
  }
  for (const child of children) node.append(child);
  return node;
}

function setTone(node, tone) { node.dataset.tone = tone; }
function setRing(id, ratio) { $(id).style.strokeDashoffset = String(RING * (1 - Math.max(0, Math.min(1, ratio)))); }
function fmt(n, digits = 1) { return Number(n).toFixed(digits); }

// ---------- Clock ----------
function tickClock() {
  $("utc-clock").textContent = new Date().toISOString().slice(11, 19) + " UTC";
}

// ---------- Chart ----------
const history = { errors: [], p95: [], rps: [] };
const hidden = new Set();

function drawGrid() {
  const g = $("chart-grid");
  for (let i = 1; i < 4; i++) {
    const y = (220 / 4) * i;
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", "0"); line.setAttribute("x2", "600");
    line.setAttribute("y1", String(y)); line.setAttribute("y2", String(y));
    g.append(line);
  }
}

function seriesPath(values, max) {
  if (values.length < 2) return "";
  const step = 600 / (SAMPLES - 1);
  const offset = (SAMPLES - values.length) * step;
  return values.map((v, i) => {
    const x = offset + i * step;
    const y = 214 - (Math.min(v, max) / max) * 204;
    return `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ");
}

function drawChart() {
  // A red line sitting on zero reads as an alarm; draw errors only once they exist.
  const pErr = history.errors.some((v) => v > 0) ? seriesPath(history.errors, 100) : "";
  $("series-errors").setAttribute("d", pErr);
  $("series-errors-area").setAttribute("d", pErr ? `${pErr} L600 214 L${(600 - (history.errors.length - 1) * (600 / (SAMPLES - 1))).toFixed(1)} 214 Z` : "");
  // p95 scale follows the data but never hides the 300 ms SLO line region.
  $("series-p95").setAttribute("d", seriesPath(history.p95, Math.max(400, ...history.p95) * 1.1));
  $("series-rps").setAttribute("d", seriesPath(history.rps, Math.max(10, ...history.rps) * 1.2));
  for (const key of ["errors", "p95", "rps"]) {
    for (const id of key === "errors" ? ["series-errors", "series-errors-area"] : [`series-${key}`]) {
      if (hidden.has(key)) $(id).setAttribute("data-hidden", ""); else $(id).removeAttribute("data-hidden");
    }
  }
}

function pushSample(key, value) {
  history[key].push(value);
  if (history[key].length > SAMPLES) history[key].shift();
}

// ---------- Rendering ----------
let lastTotal = null;
let lastTime = null;

function renderStatus(data) {
  const pill = $("status-pill");
  const text = $("status-text");
  if (data.status === "NOMINAL") {
    setTone(pill, "ok");
    text.textContent = "All systems nominal";
  } else if (data.burn_rate > 14.4 || data.availability_pct < 99.5) {
    setTone(pill, "alert");
    text.textContent = `SLO breach · ${fmt(data.burn_rate)}× burn`;
  } else {
    setTone(pill, "warn");
    text.textContent = "Degraded performance";
  }
}

function renderMetrics(data) {
  const availTone = data.availability_pct < 99.5 ? "alert" : data.availability_pct < 100 ? "warn" : "ok";
  setTone($("card-avail"), availTone);
  $("metric-avail").textContent = `${fmt(data.availability_pct, 3)}%`;
  $("metric-budget").textContent = `${fmt(data.error_budget_remaining_pct)}%`;
  setRing("ring-avail", data.error_budget_remaining_pct / 100);

  const burnTone = data.burn_rate > 14.4 ? "alert" : data.burn_rate > 1 ? "warn" : "ok";
  setTone($("card-burn"), burnTone);
  $("metric-burn").textContent = fmt(data.burn_rate);
  setRing("ring-burn", data.burn_rate / 20);

  const latTone = data.p95_ms > 300 ? "alert" : data.p95_ms > 150 ? "warn" : "ok";
  setTone($("card-latency"), latTone);
  $("metric-p95").textContent = fmt(data.p95_ms);
  $("metric-p50").textContent = fmt(data.p50_ms);
  $("metric-p99").textContent = fmt(data.p99_ms);
  setRing("ring-latency", data.p95_ms / 300);

  // Real throughput from the request counter, not a random number.
  const now = data.timestamp;
  let rps = 0;
  if (lastTotal !== null && now > lastTime) rps = Math.max(0, (data.total_requests - lastTotal) / (now - lastTime));
  lastTotal = data.total_requests; lastTime = now;
  $("metric-rps").textContent = fmt(rps);
  $("metric-total").textContent = data.total_requests.toLocaleString("en-US");
  $("metric-errors").textContent = data.total_errors.toLocaleString("en-US");
  $("metric-cpu").textContent = `${data.cpu_pct}%`;
  $("metric-mem").textContent = `${data.memory_pct}%`;
  setTone($("card-traffic"), data.cpu_pct > 85 ? "warn" : "ok");
  setRing("ring-cpu", data.cpu_pct / 100);

  pushSample("errors", Math.max(0, 100 - data.availability_pct));
  pushSample("p95", data.p95_ms);
  pushSample("rps", rps);
  drawChart();
}

function toneFor(status) {
  const s = String(status).toLowerCase();
  if (["error", "breach", "failing"].includes(s)) return "alert";
  if (["degraded"].includes(s)) return "warn";
  return "ok";
}

function renderRegions(nodes) {
  const list = $("regions");
  const maxPing = Math.max(200, ...nodes.map((n) => n.ping_ms));
  list.replaceChildren(...nodes.map((n) => {
    const bar = el("span");
    bar.style.width = `${Math.min(100, (n.ping_ms / maxPing) * 100)}%`;
    return el("li", { class: "region", dataset: { tone: toneFor(n.status) } }, [
      el("div", {}, [el("p", { class: "region-name", text: n.name }), el("p", { class: "region-id mono", text: `${n.id} · load ${n.load}%` })]),
      el("p", { class: "region-ping mono", text: `${fmt(n.ping_ms)} ms` }),
      el("div", { class: "region-bar", "aria-hidden": "true" }, [bar]),
    ]);
  }));
  const avg = nodes.reduce((s, n) => s + n.ping_ms, 0) / (nodes.length || 1);
  $("avg-ping").textContent = `${fmt(avg)} ms avg`;
}

function stateCell(status) {
  return el("td", {}, [el("span", { class: "state", dataset: { tone: toneFor(status) }, text: status })]);
}

function renderEndpoints(endpoints) {
  $("endpoints-body").replaceChildren(...endpoints.map((e) => el("tr", {}, [
    el("td", { text: `${e.method} ${e.route}` }),
    el("td", { text: `${fmt(e.p50_ms)} ms` }),
    el("td", { text: `${fmt(e.p95_ms)} ms` }),
    el("td", { text: `${fmt(e.error_pct)}%` }),
    el("td", { text: e.sla }),
    stateCell(e.status),
  ])));
}

function renderPods(pods) {
  $("pods-body").replaceChildren(...pods.map((p) => el("tr", {}, [
    el("td", { text: p.name }),
    el("td", { text: p.zone }),
    stateCell(p.status),
    el("td", { text: `${p.cpu_m}m` }),
    el("td", { text: `${p.mem_mi} Mi` }),
    el("td", { text: String(p.restarts) }),
    el("td", { text: `${fmt(p.p95_ms)} ms` }),
  ])));
}

let logsPaused = false;
let logsClearedAt = "";

function renderLogs(logs) {
  if (logsPaused) return;
  const visible = logsClearedAt ? logs.slice(logs.findIndex((l) => `${l.time}${l.message}` === logsClearedAt) + 1) : logs;
  const box = $("logs");
  const stick = box.scrollTop + box.clientHeight >= box.scrollHeight - 8;
  if (!visible.length) {
    box.replaceChildren(el("li", { class: "console-empty", text: "Waiting for new log lines…" }));
    return;
  }
  box.replaceChildren(...visible.map((l) => el("li", { dataset: { level: l.level } }, [
    el("span", { class: "log-time", text: l.time }),
    el("span", { class: "log-level", text: l.level }),
    el("span", { class: "log-trace", text: l.trace_id }),
    el("span", { class: "log-msg", text: l.message }),
  ])));
  if (stick) box.scrollTop = box.scrollHeight;
}

// ---------- Chaos controls ----------
let chaosEnabled = false;
let chaosToken = "";
try { chaosToken = sessionStorage.getItem(TOKEN_KEY) || ""; } catch { /* storage blocked */ }

function setControlsLocked(locked, message) {
  for (const b of document.querySelectorAll(".chaos, #btn-burst, #btn-autopilot")) b.disabled = locked || !chaosEnabled;
  $("unlock-form").hidden = !locked || !chaosEnabled;
  const badge = $("chaos-badge");
  badge.textContent = !chaosEnabled ? "Disabled" : locked ? "Locked" : "Armed";
  if (message) $("chaos-msg").textContent = message;
}

function renderChaos(state, enabled) {
  if (enabled !== chaosEnabled) {
    chaosEnabled = enabled;
    setControlsLocked(!chaosToken, enabled ? undefined : "Fault injection is disabled in this environment.");
  }
  for (const b of document.querySelectorAll(".chaos")) {
    const kind = b.dataset.chaos;
    const v = Number(b.dataset.value);
    const active = (kind === "latency" && state.injected_latency_ms === v)
      || (kind === "error" && state.injected_error_rate === v)
      || (kind === "circuit" && state.circuit_broken);
    b.setAttribute("aria-pressed", String(active));
  }
}

async function chaosCall(url) {
  const res = await fetch(url, { method: "POST", headers: { "X-Chaos-Token": chaosToken } });
  if (res.status === 401) {
    chaosToken = "";
    try { sessionStorage.removeItem(TOKEN_KEY); } catch { /* storage blocked */ }
    stopAutopilot();
    setControlsLocked(true, "Token rejected. Paste the CHAOS_TOKEN value from .env.");
    throw new Error("unauthorized");
  }
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

const CHAOS_URLS = {
  latency: (v) => `/chaos/inject-latency?ms=${encodeURIComponent(v)}`,
  error: (v) => `/chaos/inject-error?rate=${encodeURIComponent(v)}`,
  circuit: () => "/chaos/trip-circuit",
  reset: () => "/chaos/reset",
};

async function onChaos(event) {
  const b = event.currentTarget;
  try {
    const json = await chaosCall(CHAOS_URLS[b.dataset.chaos](b.dataset.value));
    $("chaos-msg").textContent = json.message;
    fetchTelemetry();
  } catch (e) {
    if (e.message !== "unauthorized") $("chaos-msg").textContent = `Request failed: ${e.message}`;
  }
}

async function sendBurst(count) {
  try {
    const json = await chaosCall(`/api/suite/simulate-traffic?count=${count}`);
    $("chaos-msg").textContent = `${json.requests_sent} requests · ${json.successes} ok · ${json.failures} failed · ${json.avg_latency_ms} ms avg`;
  } catch (e) {
    if (e.message !== "unauthorized") $("chaos-msg").textContent = `Request failed: ${e.message}`;
  }
}

let autopilot = null;
function stopAutopilot() {
  clearInterval(autopilot); autopilot = null;
  $("btn-autopilot").setAttribute("aria-pressed", "false");
  $("btn-autopilot").textContent = "Auto traffic: off";
}
function toggleAutopilot() {
  if (autopilot) return stopAutopilot();
  autopilot = setInterval(() => sendBurst(15), POLL_MS);
  $("btn-autopilot").setAttribute("aria-pressed", "true");
  $("btn-autopilot").textContent = "Auto traffic: on";
}

// ---------- Triage ----------
async function runTriage() {
  const btn = $("btn-triage");
  btn.disabled = true; btn.textContent = "Analyzing…";
  try {
    const res = await fetch("/api/suite/ai-triage", { method: "POST" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const rca = await res.json();
    const tone = rca.status === "NOMINAL" ? "ok" : rca.status === "ACTIVE_CRITICAL" ? "alert" : "warn";
    setTone($("incident"), tone);
    const sev = $("incident-severity");
    sev.textContent = rca.severity; sev.dataset.tone = tone;
    $("incident-id").textContent = rca.incident_id;
    $("incident-title").textContent = rca.title;
    $("incident-cause").textContent = rca.root_cause;
    $("rca-slo").textContent = rca.impacted_slo;
    $("rca-burn").textContent = rca.burn_rate;
    $("rca-runbook").textContent = rca.recommended_runbook;
    $("rca-command").textContent = rca.mitigation_command;
    $("rca-traces").replaceChildren(...rca.correlated_trace_ids.map((id) => el("span", { text: id })));
  } catch (e) {
    $("incident-cause").textContent = `Analysis failed: ${e.message}`;
  } finally {
    btn.disabled = false; btn.textContent = "Run analysis";
  }
}

async function copyCommand() {
  const btn = $("btn-copy");
  try {
    await navigator.clipboard.writeText($("rca-command").textContent);
    btn.textContent = "Copied";
  } catch {
    btn.textContent = "Copy failed";
  }
  setTimeout(() => { btn.textContent = "Copy"; }, 1500);
}

// ---------- Tabs ----------
function selectTab(tab) {
  for (const t of document.querySelectorAll('[role="tab"]')) {
    const on = t === tab;
    t.setAttribute("aria-selected", String(on));
    t.tabIndex = on ? 0 : -1;
    $(t.getAttribute("aria-controls")).hidden = !on;
  }
}

// ---------- Polling ----------
let failures = 0;
async function fetchTelemetry() {
  try {
    const res = await fetch("/api/suite/telemetry", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    failures = 0;
    renderStatus(data);
    renderMetrics(data);
    renderRegions(data.nodes);
    renderEndpoints(data.endpoints);
    renderPods(data.pods);
    renderLogs(data.recent_logs);
    renderChaos(data.chaos_state, Boolean(data.chaos_enabled));
  } catch {
    if (++failures >= 2) {
      setTone($("status-pill"), "alert");
      $("status-text").textContent = "API unreachable";
    }
  }
}

let pollTimer = null;
function startPolling() {
  if (pollTimer) return;
  fetchTelemetry();
  pollTimer = setInterval(fetchTelemetry, POLL_MS);
}
function stopPolling() { clearInterval(pollTimer); pollTimer = null; }

document.addEventListener("DOMContentLoaded", () => {
  drawGrid();
  tickClock();
  setInterval(tickClock, 1000);

  for (const b of document.querySelectorAll(".legend-item")) {
    b.addEventListener("click", () => {
      const key = b.dataset.series;
      if (hidden.has(key)) hidden.delete(key); else hidden.add(key);
      b.setAttribute("aria-pressed", String(!hidden.has(key)));
      drawChart();
    });
  }

  $("unlock-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const value = $("chaos-token").value.trim();
    if (!value) return;
    chaosToken = value;
    try { sessionStorage.setItem(TOKEN_KEY, value); } catch { /* storage blocked */ }
    $("chaos-token").value = "";
    setControlsLocked(false, "Controls armed. Faults affect the live API.");
  });
  for (const b of document.querySelectorAll(".chaos")) b.addEventListener("click", onChaos);
  $("btn-burst").addEventListener("click", () => sendBurst(30));
  $("btn-autopilot").addEventListener("click", toggleAutopilot);
  $("btn-triage").addEventListener("click", runTriage);
  $("btn-copy").addEventListener("click", copyCommand);

  $("btn-pause").addEventListener("click", (e) => {
    logsPaused = !logsPaused;
    e.currentTarget.setAttribute("aria-pressed", String(logsPaused));
    e.currentTarget.textContent = logsPaused ? "Resume" : "Pause";
  });
  $("btn-clear").addEventListener("click", () => {
    const items = $("logs").querySelectorAll("li[data-level]");
    const last = items[items.length - 1];
    if (last) logsClearedAt = `${last.children[0].textContent}${last.children[3].textContent}`;
    $("logs").replaceChildren(el("li", { class: "console-empty", text: "Console cleared. Waiting for new log lines…" }));
  });

  const tabs = [...document.querySelectorAll('[role="tab"]')];
  for (const t of tabs) {
    t.addEventListener("click", () => selectTab(t));
    t.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      const next = tabs[(tabs.indexOf(t) + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
      selectTab(next); next.focus();
    });
  }

  setControlsLocked(!chaosToken);
  startPolling();
  document.addEventListener("visibilitychange", () => (document.hidden ? stopPolling() : startPolling()));
});
