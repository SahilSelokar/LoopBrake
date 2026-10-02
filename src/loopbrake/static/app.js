"use strict";
// LoopBrake dashboard (specs/005-observability/contracts/ui.md). Plain words only (spec FR-007).
// Every piece of text goes into the page through textContent, never as HTML: tool-call text is
// whatever the agent typed. No libraries, no build step; the CSP allows only this origin.

const TEXT = {
  overview: "Overview",
  projects: "Projects",
  runningNow: "Running now",
  recentStops: "Recent stops",
  noRunning: "Nothing is running right now.",
  noStops: "LoopBrake hasn't stopped any task yet.",
  seen: "Tasks seen",
  stopped: "Stopped",
  mistakes: "Marked as mistakes",
  normal: (x) => `up to about ${x} would be normal by now`,
  stopsPerDay: "Stops per day",
  tokensPerDay: "Tokens spent per day",
  last30: "last 30 days",
  allProjects: "All projects",
  empty: "No tasks yet. Run an agent with LoopBrake, or replay past runs:",
  emptyCmd: "loopbrake replay runs.jsonl --stop-line 20 --record",
  of: (n, l) => (l == null ? `${n} tool calls` : `${n} of ${l} tool calls`),
  stoppedAfter: (n, l) => `stopped after ${n} tool calls (limit ${l})`,
  calls: (n) => (n === 1 ? "1 tool call" : `${n} tool calls`),
  tasks: (n) => (n === 1 ? "1 task" : `${n} tasks`),
  watching: "watching only",
  why: "Why it stopped",
  toolCalls: "Tool calls",
  failed: "failed",
  repeats: "repeats an earlier call",
  loadMore: "Load more",
  limitLine: "limit",
  stopMark: "Stopped",
  back: "Back",
  noProjects: "No projects yet.",
  limit: "Limit",
  perTask: "tool calls per task",
  notSet: "Not set yet: LoopBrake only watches.",
  needs: (have, need) => `${have} successful past tasks found, ${need} needed.`,
  setFrom: (n, d) => `Set ${d} from ${n} past successful tasks.`,
  pastLengths: "Past successful tasks, by tool calls",
  counts: (p) => `${p.seen} tasks seen, ${p.stopped} stopped, ${p.mistaken} marked as mistakes (up to about ${p.normal_mistakes.toFixed(1)} would be normal)`,
  exportTitle: "Send to your observability tools",
  exportSoon: "Export status appears here.",
  glassOn: "Glass on",
  glassOff: "Glass off",
  notFound: "Not found.",
  offline: "Can't reach the dashboard. Is loopbrake dashboard still running?",
  justNow: "just now",
};

// ---- small helpers ----

const SVG = "http://www.w3.org/2000/svg";
function h(tag, attrs = {}, ...kids) {
  const svg = ["svg", "use", "rect", "line", "polyline", "circle", "g", "title", "text"].includes(tag);
  const el = svg ? document.createElementNS(SVG, tag) : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.setAttribute("class", v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
const icon = (name) => h("svg", { class: "icon", "aria-hidden": "true" }, h("use", { href: `/static/icons.svg#${name}` }));
// Claude Code project names are a folder path's tail plus a hash; show the end, which names the folder.
const shortName = (name) => {
  const s = (name || "").replace(/^cc-/, "").replace(/-[0-9a-f]{6}$/, "");
  return s.length > 30 ? `…${s.slice(-29)}` : s;
};
const countText = (t) => (t.state === "stopped" && t.stop_at ? TEXT.stoppedAfter(t.stop_at, t.limit) :
  t.limit == null ? `${TEXT.calls(t.calls)} (${TEXT.watching})` : TEXT.of(t.calls, t.limit));
const actionText = (c) => (c.tool && c.action.startsWith(`${c.tool} `) ? c.action.slice(c.tool.length + 1) : c.action);
const chip = (task) => h("span", { class: `chip ${task.state}` },
  task.state === "stopped" ? icon("octagon-x") : task.state === "finished" ? icon("check") :
  task.state === "interrupted" ? icon("circle-alert") : icon("loader-circle"), task.status);

function ago(ts) {
  if (!ts) return "";
  const s = (Date.now() - Date.parse(ts)) / 1000;
  if (s < 45) return TEXT.justNow;
  const fmt = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  for (const [unit, size] of [["day", 86400], ["hour", 3600], ["minute", 60]]) {
    if (s >= size) return fmt.format(-Math.round(s / size), unit);
  }
  return TEXT.justNow;
}

async function api(path, options) {
  const r = await fetch(path, { credentials: "same-origin", ...options });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(body.error || TEXT.notFound), { status: r.status, body });
  return body;
}

function toast(message) {
  const t = document.getElementById("toast");
  t.textContent = message;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { t.hidden = true; }, 5000);
}

function confirmDialog(title, text, ok) {
  const d = document.getElementById("confirm");
  document.getElementById("confirm-title").textContent = title;
  document.getElementById("confirm-text").textContent = text;
  document.getElementById("confirm-ok").textContent = ok;
  return new Promise((resolve) => {
    d.addEventListener("close", () => resolve(d.returnValue === "ok"), { once: true });
    d.showModal();
  });
}

// ---- charts: inline SVG, no library ----

function barChart(days, key, label) {
  const max = Math.max(1, ...days.map((d) => d[key]));
  const total = days.reduce((a, d) => a + d[key], 0);
  const w = 300, hgt = 80, bw = w / days.length;
  return h("svg", { class: "chart bars", viewBox: `0 0 ${w} ${hgt}`, preserveAspectRatio: "none", role: "img", "aria-label": `${label}, ${TEXT.last30}: ${total}` },
    days.map((d, i) => {
      const bh = d[key] ? Math.max(2, (d[key] / max) * (hgt - 4)) : 0;
      return h("rect", { x: i * bw + 1, y: hgt - bh, width: bw - 2, height: bh, rx: 1, class: key === "stops" ? "bar stop" : "bar" },
        h("title", {}, `${d.day}: ${d[key]}`));
    }));
}

function taskChart(summary, calls, total) {
  const limit = summary.limit;
  const top = Math.max(total, limit ?? 0, 4) + 1;
  const w = 300, hgt = 130, pad = 8;
  const x = (n) => pad + (n / top) * (w - 2 * pad);
  const y = (n) => hgt - pad - (n / top) * (hgt - 2 * pad);
  const label = `${TEXT.calls(total)}` + (limit != null ? `, ${TEXT.limitLine} ${limit}` : "") +
    (summary.stop_at ? `, ${TEXT.stopMark.toLowerCase()} at ${summary.stop_at}` : "");
  const kids = [h("polyline", { class: "count", points: `${x(0)},${y(0)} ${x(total)},${y(total)}` })];
  if (limit != null) {
    kids.push(h("line", { class: "limit", x1: x(0), x2: x(top), y1: y(limit), y2: y(limit) }));
    kids.push(h("text", { class: "label lime", x: x(0), y: y(limit) - 4 }, `${TEXT.limitLine} ${limit}`));
  }
  kids.push(h("text", { class: "label", x: x(total), y: Math.min(hgt - 2, y(total) - 6), "text-anchor": "end" }, String(total)));
  for (const c of calls) {
    if (c.failed || c.repeats) kids.push(h("circle", { class: c.failed ? "dot failed" : "dot repeat", cx: x(c.n), cy: y(c.n), r: 2.6 }));
  }
  if (summary.stop_at) {
    kids.push(h("circle", { class: "stopmark", cx: x(summary.stop_at), cy: y(summary.stop_at), r: 5 }));
  }
  return h("svg", { class: "chart tall", viewBox: `0 0 ${w} ${hgt}`, role: "img", "aria-label": label }, kids);
}

function lengthsStrip(lengths, limit) {
  const finite = lengths.filter((v) => v != null);
  const top = Math.max(...finite, limit ?? 0, 1) + 2;
  const w = 300, hgt = 46;
  const x = (v) => 6 + (v / top) * (w - 12);
  const seen = {};
  const dots = finite.map((v) => {
    seen[v] = (seen[v] || 0) + 1;
    return h("circle", { class: "dot past", cx: x(v), cy: hgt - 8 - (seen[v] - 1) * 5, r: 2.2 });
  });
  const kids = [...dots];
  if (limit != null) kids.push(h("line", { class: "limit", x1: x(limit), x2: x(limit), y1: 2, y2: hgt - 2 }));
  return h("svg", { class: "chart", viewBox: `0 0 ${w} ${hgt}`, role: "img", "aria-label": `${TEXT.pastLengths}: ${finite.length}` }, kids);
}

// ---- views ----

const state = { version: -1, project: "", pages: {} };

function taskRow(t) {
  const pct = t.limit ? Math.min(100, (t.calls / t.limit) * 100) : 0;
  const bar = h("span", { class: t.state === "stopped" ? "progress stopped" : "progress" }, h("span", { class: "fill" }));
  bar.firstChild.style.width = `${pct}%`;
  return h("a", { class: "row", href: `#/task/${t.session}/${t.run}` },
    h("span", { class: "name" }, shortName(t.project)),
    h("span", { class: "num" }, countText(t)),
    t.limit == null ? null : bar, chip(t), h("span", { class: "when" }, ago(t.ended || t.started)));
}

async function overview() {
  const q = state.project ? `?project=${encodeURIComponent(state.project)}` : "";
  const o = await api(`/api/overview${q}`);
  const filter = h("select", { "aria-label": TEXT.allProjects, onchange: (e) => { state.project = e.target.value; render(); } },
    h("option", { value: "" }, TEXT.allProjects),
    o.projects.map((p) => h("option", { value: p, selected: p === state.project }, shortName(p))));
  if (!o.seen && !state.project) {
    return [h("h1", {}, TEXT.overview), h("section", { class: "panel empty" }, h("p", {}, TEXT.empty), h("code", {}, TEXT.emptyCmd))];
  }
  const tile = (label, value, note, name) => h("div", { class: "tile" }, icon(name), h("span", { class: "label" }, label),
    h("span", { class: "value" }, value), note ? h("span", { class: "note" }, note) : null);
  const anyTokens = o.days.some((d) => d.tokens);
  return [
    h("div", { class: "head" }, h("h1", {}, TEXT.overview), filter),
    h("section", { class: "tiles" },
      tile(TEXT.seen, o.seen, null, "layers"),
      tile(TEXT.stopped, o.stopped, null, "octagon-x"),
      tile(TEXT.mistakes, o.mistaken, TEXT.normal(o.normal_mistakes.toFixed(1)), "shield-check")),
    h("section", { class: "panel" }, h("h2", {}, icon("activity"), TEXT.runningNow),
      o.running.length ? h("div", { class: "rows" }, o.running.map(taskRow)) : h("p", { class: "muted" }, TEXT.noRunning)),
    h("section", { class: "panel" }, h("h2", {}, icon("octagon-x"), TEXT.recentStops),
      o.recent_stops.length ? h("div", { class: "rows" }, o.recent_stops.map(taskRow)) : h("p", { class: "muted" }, TEXT.noStops)),
    h("section", { class: "panel" }, h("h2", {}, icon("chart-column"), TEXT.stopsPerDay, h("span", { class: "muted small" }, ` (${TEXT.last30})`)),
      barChart(o.days, "stops", TEXT.stopsPerDay)),
    anyTokens ? h("section", { class: "panel" }, h("h2", {}, icon("coins"), TEXT.tokensPerDay, h("span", { class: "muted small" }, ` (${TEXT.last30})`)),
      barChart(o.days, "tokens", TEXT.tokensPerDay)) : null,
  ];
}

async function task(session, run) {
  const key = `${session}/${run}`;
  const pages = state.pages[key] || 1;
  const first = await api(`/api/task/${session}/${run}?page=0`);
  let calls = first.calls;
  for (let p = 1; p < pages; p += 1) calls = calls.concat((await api(`/api/task/${session}/${run}?page=${p}`)).calls);
  const s = first.summary;
  const more = calls.length < first.total;
  return [
    h("a", { class: "back", href: "#/" }, icon("chevron-left"), TEXT.back),
    h("div", { class: "head" }, h("h1", {}, shortName(s.project)), chip(s), h("span", { class: "muted" }, ago(s.started))),
    h("section", { class: "panel" }, h("p", { class: "big num" }, countText(s)), taskChart(s, calls, first.total)),
    first.reason_text ? h("section", { class: "panel reason" }, h("h2", {}, icon("triangle-alert"), TEXT.why), h("p", {}, first.reason_text),
      h("div", { class: "actions", id: "task-actions" })) : h("div", { class: "actions", id: "task-actions" }),
    h("section", { class: "panel" }, h("h2", {}, icon("wrench"), TEXT.toolCalls),
      h("ol", { class: "calls" }, calls.map((c) => h("li", { class: c.n === s.stop_at ? "call at-stop" : "call" },
        h("span", { class: "n num" }, c.n), h("span", { class: "tool" }, c.tool || ""),
        h("code", { class: "action" }, actionText(c)),
        h("span", { class: "flags" },
          c.failed ? h("span", { class: "flag failed" }, icon("circle-alert"), TEXT.failed) : null,
          c.repeats ? h("span", { class: "flag repeat" }, icon("repeat"), TEXT.repeats) : null),
        h("span", { class: "dur num" }, c.duration_ms != null ? `${c.duration_ms} ms` : "")))),
      more ? h("button", { class: "button quiet", type: "button", onclick: () => { state.pages[key] = pages + 1; render(); } }, TEXT.loadMore) : null),
  ];
}

async function projectsView() {
  const ps = await api("/api/projects");
  if (!ps.length) return [h("h1", {}, TEXT.projects), h("p", { class: "muted" }, TEXT.noProjects)];
  return [h("h1", {}, TEXT.projects), h("div", { class: "rows panel" }, ps.map((p) => h("a", { class: "row", href: `#/project/${p.name}` },
    h("span", { class: "name" }, shortName(p.name)),
    h("span", { class: "num" }, p.limit == null ? TEXT.watching : `${TEXT.limit} ${p.limit}`),
    h("span", { class: "muted" }, TEXT.tasks(p.seen)))))];
}

async function project(name) {
  const p = await api(`/api/project/${encodeURIComponent(name)}`);
  return [
    h("a", { class: "back", href: "#/projects" }, icon("chevron-left"), TEXT.back),
    h("div", { class: "head" }, h("h1", {}, shortName(p.name))),
    h("section", { class: "panel" },
      p.limit == null
        ? [h("p", { class: "big" }, TEXT.notSet), p.needed ? h("p", { class: "muted" }, TEXT.needs(p.n || 0, p.needed)) : null]
        : [h("p", { class: "big num" }, `${p.limit} `, h("span", { class: "unit" }, TEXT.perTask)),
          h("p", { class: "promise" }, p.promise), p.n ? h("p", { class: "muted" }, TEXT.setFrom(p.n, p.created)) : null],
      p.lengths ? [h("h2", {}, icon("gauge"), TEXT.pastLengths), lengthsStrip(p.lengths, p.limit)] : null,
      h("p", { class: "muted" }, TEXT.counts(p)),
      h("div", { class: "actions", id: "project-actions" })),
  ];
}

async function exportView() {
  return [h("h1", {}, TEXT.exportTitle), h("section", { class: "panel", id: "export" }, h("p", { class: "muted" }, TEXT.exportSoon))];
}

// ---- routing and live updates ----

function route() {
  const parts = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  if (parts[0] === "task" && parts.length === 3) return ["task", () => task(parts[1], parts[2])];
  if (parts[0] === "project" && parts.length === 2) return ["projects", () => project(parts[1])];
  if (parts[0] === "projects") return ["projects", projectsView];
  if (parts[0] === "export") return ["export", exportView];
  return ["overview", overview];
}

async function render() {
  const [nav, view] = route();
  for (const a of document.querySelectorAll("[data-nav]")) {
    if (a.dataset.nav === nav) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  }
  const main = document.getElementById("main");
  try {
    const content = await view();
    main.replaceChildren(...[content].flat().filter(Boolean));
    document.dispatchEvent(new CustomEvent("lb:rendered", { detail: { nav } }));
  } catch (e) {
    main.replaceChildren(h("p", { class: "muted" }, e.status === 404 ? TEXT.notFound : TEXT.offline));
  }
}

async function poll() {
  try {
    const { version } = await api("/api/changes");
    if (version !== state.version) { state.version = version; await render(); }
  } catch (e) { /* the next poll tries again */ }
}

// ---- glass on/off (a per-viewer choice; the system's accessibility settings force it off in CSS) ----

function setGlass(on, save) {
  document.documentElement.dataset.glass = on ? "on" : "off";
  const b = document.getElementById("glass");
  b.setAttribute("aria-pressed", String(on));
  b.querySelector("span").textContent = on ? TEXT.glassOn : TEXT.glassOff;
  if (save) { try { localStorage.setItem("lb-glass", on ? "on" : "off"); } catch (e) { /* storage blocked: still works */ } }
}

function initGlass() {
  let saved = null;
  try { saved = localStorage.getItem("lb-glass"); } catch (e) { /* blocked */ }
  const param = new URLSearchParams(location.search).get("glass");
  setGlass((param || saved || "on") !== "off", false);
  document.getElementById("glass").addEventListener("click", () => setGlass(document.documentElement.dataset.glass !== "on", true));
}

window.LB = { TEXT, h, icon, api, toast, confirmDialog, render, shortName, state };
initGlass();
window.addEventListener("hashchange", () => { state.version = -1; render(); });
render();
setInterval(poll, 1000);
