"use strict";
// LoopBrake dashboard (specs/005-observability/contracts/ui.md): written for people who don't code.
// Every piece of text goes into the page through textContent, never as HTML: action text is whatever
// the agent typed. No libraries, no build step; the CSP allows only this origin.

const TEXT = {
  greeting: (part, name) => `Good ${part}${name ? `, ${name}` : ""}`,
  sub: "Here's what LoopBrake saw while your AI agents worked.",
  stoppedToday: (n) => (n === 1 ? "LoopBrake stopped a task today because it looked stuck." : `LoopBrake stopped ${n} tasks today because they looked stuck.`),
  workingNow: (n) => (n === 1 ? "Your agent is working on a task right now. LoopBrake is watching it." : `Your agents are working on ${n} tasks right now. LoopBrake is watching them.`),
  quietWeek: (n) => `All quiet today. LoopBrake stopped ${n === 1 ? "1 task" : `${n} tasks`} earlier this week.`,
  allQuiet: "All quiet. No task got stuck in the last 7 days.",
  watchingOnly: "LoopBrake is only watching for now. It sets a limit once a project has enough finished tasks.",
  seeWhy: "See why",
  tasksWeek: "Tasks this week",
  last7: "in the last 7 days",
  stopped: "Stopped",
  marked: (n) => (n === 1 ? "1 marked as a mistake" : `${n} marked as mistakes`),
  tokensWeek: "Tokens this week",
  spent: "spent by your agents",
  workingTile: "Working now",
  rightNow: "tasks right now",
  workingIn: (label) => `Working in ${label}`,
  started: (when) => `started ${when}`,
  noLimitYet: "No limit yet, so LoopBrake only watches this one.",
  near: "Getting close to the limit.",
  recentStops: "Recent stops",
  noStops: "LoopBrake hasn't stopped anything yet. That's good news.",
  viewAll: "View all",
  projects: "Projects",
  stopsPerDay: "Stops per day",
  tokensPerDay: "Tokens spent per day",
  last30: "last 30 days",
  limitActions: (n) => `Limit: ${n} actions`,
  watchingNoLimit: "Watching, no limit yet",
  usually: (n) => `usually about ${n}`,
  thisWeek: (n) => `${n} this week`,
  startTitle: "Getting started",
  startSteps: [
    "In Claude Code, install the plugin: /plugin marketplace add SahilSelokar/LoopBrake, then /plugin install loopbrake@loopbrake",
    "Work as usual. LoopBrake counts each task's actions and learns what's normal.",
    "When a project has about 20 finished tasks, run /loopbrake:calibrate there to set its limit.",
  ],
  startNote: "Your tasks show up here as soon as they start.",
  tasksTitle: "Tasks",
  tasksSub: "Everything your agents did, newest first.",
  all: "All",
  allProjects: "All projects",
  search: "Search by project",
  noMatch: "No tasks match.",
  loadMore: "Show more",
  showAll: (n) => `Show all ${n} actions`,
  whyTitle: "Why it stopped",
  whyLead: (median, limit, oneIn, at) => `${median ? `Tasks in this project usually take about ${median} actions. ` : ""}Good ones almost never need more than ${limit}: ${oneIn} go past it. This one reached ${at}.`,
  pictureNote: "Each dot is one of your past finished tasks here. The dashed line is the limit.",
  howItWent: "How it went",
  finishedNote: (n, limit) => `Finished normally after ${n === 1 ? "1 action" : `${n} actions`}${limit != null ? `, under the limit of ${limit}` : ""}.`,
  interruptedNote: "A new message came in before this task finished.",
  liveNote: "Your agent is working on this right now. This page updates by itself.",
  idleNote: "Nothing new has happened in this task for a day.",
  keptDoing: "What it kept doing",
  keptNote: "The same actions, again and again, are what a stuck task looks like.",
  overTime: "Actions over time",
  firstOf: (n, total) => `Showing the first ${n} of ${total} actions.`,
  allActions: (n) => `All actions (${n})`,
  failed: "Failed",
  repeated: "Repeated",
  copy: "Copy",
  copied: "Copied.",
  copyFailed: "Couldn't copy. Select the text instead.",
  took: (t) => `took ${t}`,
  notStuck: "It wasn't stuck",
  markMistakeTitle: "Was this task not stuck?",
  markMistakeText: "LoopBrake will count it as a long good task the next time the limit is set, so the limit can only go up.",
  markedMistake: "Marked as a mistake",
  leaveOut: "Leave out of future limits",
  leaveOutTitle: "Leave this task out?",
  leaveOutText: "The next time the limit is set, LoopBrake won't learn from this task.",
  leftOut: "Left out of future limits",
  projectsSub: "Each project has its own limit, learned from its own past tasks.",
  noProjects: "No projects yet.",
  claudeProject: "Claude Code project",
  agentProject: "Agent project",
  limitTitle: "The limit",
  promise: (oneIn) => `Good tasks almost never need more: ${oneIn} go past it.`,
  usuallyPer: (n) => `Usually about ${n} actions per task.`,
  notSet: "No limit yet. LoopBrake is only watching.",
  needs: (have, need) => `It has ${have === 1 ? "1 finished task" : `${have} finished tasks`} to learn from and needs ${need}.`,
  setFrom: (n, d) => `Learned from ${n === 1 ? "1 past finished task" : `${n} past finished tasks`} on ${d}.`,
  pastTasks: "Past finished tasks",
  soFar: "So far",
  seenN: (n) => (n === 1 ? "1 task seen" : `${n} tasks seen`),
  stoppedN: (n) => `${n} stopped`,
  mistakes: (n, expected) => `${n === 1 ? "1 marked" : `${n} marked`} as a mistake (expected by now: ${expected})`,
  fewerThanOne: "fewer than 1",
  aboutN: (x) => `about ${x}`,
  recentTasks: "Recent tasks",
  setAgain: "Set the limit again",
  setAgainTitle: "Set the limit again?",
  setAgainText: "LoopBrake will look at this project's past tasks and set a new limit.",
  setAgainOk: "Set the limit",
  settingsTitle: "Settings",
  you: "You",
  nameLabel: "What should LoopBrake call you?",
  nameHint: "Saved in this browser only.",
  appearance: "Appearance",
  themeSystem: "System",
  themeLight: "Light",
  themeDark: "Dark",
  themeNote: "Glass effects turn off by themselves if your computer is set to reduce transparency or increase contrast.",
  howTitle: "How LoopBrake works",
  how: [
    ["gauge", "It learns your normal", "From your past finished tasks in a project, it learns how many actions a normal task takes, and sets a limit just above that."],
    ["eye", "It watches each task", "While your agent works, it counts every action. You can see the count here, live."],
    ["octagon-x", "It stops the stuck ones", "When a task goes past the limit, it stops it and says why. If it was wrong, tell it, and the limit adjusts."],
  ],
  wordsTitle: "What the words mean",
  privacy: "Only this computer can open this page. Nothing leaves it unless you turn on sending below.",
  exportTitle: "Send to your observability tools",
  exportOff: "Sending is off.",
  exportOffText: "LoopBrake sends nothing anywhere until you turn it on with the lines below.",
  exportOn: (where) => `Sending is on, to ${where}.`,
  exportWhat: "What's sent: counts and timings only. Commands, project names and stop reasons stay on this computer.",
  exportWhatContent: "What's sent: counts and timings, plus commands, project names and stop reasons (LOOPBRAKE_EXPORT_CONTENT=1).",
  exportNoCounters: "Counters are off (traces only).",
  exportFromShell: "These settings come from the terminal that started this dashboard. Your agent reads its own, so set them there too.",
  lastSend: "Last send",
  neverSent: "Nothing sent yet. Each task is sent when it ends.",
  sentTasks: (n, when) => `${n === 1 ? "1 task" : `${n} tasks`} sent ${when}.`,
  sendFailed: (when) => `Sending failed ${when}.`,
  sendNow: "Send now",
  testConnection: "Test connection",
  setup: "How to turn it on",
  setupHint: "Pick your tool, copy the lines, and run them in the terminal you start your agent from.",
  protobufOnly: "Phoenix and other tools that only take protobuf: send to an OpenTelemetry Collector, which forwards to them.",
  justStopped: "LoopBrake just stopped a task.",
  notFound: "Not found.",
  offline: "Can't reach the dashboard. Is loopbrake dashboard still running?",
  justNow: "just now",
  back: "Back",
};

// One line for each idea, behind the "?" next to it (FR-022).
const HELP = {
  task: ["Task", "Everything your agent does for one message you send it."],
  action: ["Action", "One thing the agent does, like running a command or reading a file. Developers call it a tool call."],
  limit: ["Limit", "How many actions a task may take before LoopBrake stops it. It's learned from your own past finished tasks in that project, so that fewer than 1 in 20 good tasks go past it."],
  mistake: ["It wasn't stuck", "Tell LoopBrake a stop was wrong. The next time the limit is set, that task counts as a long good one, so the limit can only go up."],
  leaveOut: ["Leave out", "Tell LoopBrake not to learn from this task, for example one that went badly."],
  watching: ["Watching only", "LoopBrake counts actions but stops nothing until a project has enough finished tasks to set a limit."],
  repeated: ["Repeated", "An action very much like one of the 10 before it. A few are normal; many in a row usually mean the agent is going in circles."],
};
const WORDS = ["task", "action", "limit", "mistake", "repeated"];

// What each Claude Code tool did, in words: [what it did, icon, the field worth showing, "the same ..."].
const TOOLS = {
  Bash: ["Ran a command", "square-terminal", "command", "Ran the same command"],
  Read: ["Read a file", "file-text", "file_path", "Read the same file"],
  Edit: ["Edited a file", "pencil", "file_path", "Edited the same file"],
  MultiEdit: ["Edited a file", "pencil", "file_path", "Edited the same file"],
  Write: ["Wrote a file", "file-plus", "file_path", "Wrote the same file"],
  NotebookEdit: ["Edited a notebook", "pencil", "notebook_path", "Edited the same notebook"],
  Grep: ["Searched the code", "search", "pattern", "Ran the same search"],
  Glob: ["Looked for files", "folder-search", "pattern", "Looked for the same files"],
  LS: ["Listed a folder", "folder", "path", "Listed the same folder"],
  WebFetch: ["Opened a web page", "globe", "url", "Opened the same page"],
  WebSearch: ["Searched the web", "globe", "query", "Ran the same web search"],
  Task: ["Asked a helper", "users", "description", "Asked a helper the same thing"],
  Agent: ["Asked a helper", "users", "description", "Asked a helper the same thing"],
  TodoWrite: ["Updated its to-do list", "list-checks", null, "Updated its to-do list"],
};
const DETAIL_KEYS = ["command", "file_path", "notebook_path", "path", "pattern", "url", "query", "description", "prompt"];

const STATES = { running: ["Working", "loader-circle"], idle: ["No recent activity", "clock"], finished: ["Finished", "circle-check"],
  stopped: ["Stopped", "octagon-x"], interrupted: ["Interrupted", "circle-alert"] };
const SYMPTOMS = { repeating: "It kept repeating the same actions.", same_error: "It kept hitting the same error.",
  nothing_new: "Its last actions turned up nothing new." };

// Copyable setup lines (contracts/otlp.md, "Settings per tool"). Shown as text only, never loaded.
const SETUP = [
  ["OpenTelemetry Collector", ["OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318"]],
  ["Datadog", ["OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp.datadoghq.com", "OTEL_EXPORTER_OTLP_HEADERS=dd-api-key=YOUR_API_KEY"]],
  ["Grafana Cloud", ["OTEL_EXPORTER_OTLP_ENDPOINT=YOUR_STACK_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic%20BASE64_OF_INSTANCE_ID:TOKEN",
    "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=cumulative"]],
  ["Honeycomb", ["OTEL_EXPORTER_OTLP_ENDPOINT=https://api.honeycomb.io", "OTEL_EXPORTER_OTLP_HEADERS=x-honeycomb-team=YOUR_API_KEY"]],
  ["Langfuse", ["OTEL_EXPORTER_OTLP_ENDPOINT=https://cloud.langfuse.com/api/public/otel",
    "OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic%20BASE64_OF_PUBLIC_KEY:SECRET_KEY", "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=none"]],
  ["Jaeger", ["OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318", "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=none"]],
];

// ---- small helpers ----

const SVG = "http://www.w3.org/2000/svg";
const SVG_TAGS = ["svg", "use", "rect", "line", "polyline", "polygon", "path", "circle", "g", "title", "text"];
function h(tag, attrs = {}, ...kids) {
  const el = SVG_TAGS.includes(tag) ? document.createElementNS(SVG, tag) : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(3)) {
    if (kid == null || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
const icon = (name) => h("svg", { class: "icon", "aria-hidden": "true" }, h("use", { href: `/static/icons.svg#${name}` }));
const actions = (n) => (n === 1 ? "1 action" : `${n} actions`);
const oneIn = (alpha) => `fewer than 1 in ${Math.round(1 / (alpha || 0.05))}`;
const about = (x) => (x < 0.95 ? TEXT.fewerThanOne : TEXT.aboutN(Math.round(x)));
const link = (t) => `#/task/${t.session}/${t.run}`;
const ms = (ts) => Date.parse(ts);
const short = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e4 ? `${Math.round(n / 1e3)}k` : String(n));

function ago(ts) {
  const s = (Date.now() - ms(ts)) / 1000;
  if (!ts || !isFinite(s) || s < 45) return TEXT.justNow;
  const fmt = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  for (const [unit, size] of [["day", 86400], ["hour", 3600], ["minute", 60]]) if (s >= size) return fmt.format(-Math.round(s / size), unit);
  return TEXT.justNow;
}
const clock = (ts, sec) => (ts ? new Date(ts).toLocaleTimeString("en", { hour: "numeric", minute: "2-digit", ...(sec ? { second: "2-digit" } : {}) }) : "");
function dayTime(ts) {
  if (!ts) return "";
  const d = new Date(ts), now = new Date(), y = new Date(now);
  y.setDate(now.getDate() - 1);
  const day = d.toDateString() === now.toDateString() ? "Today" : d.toDateString() === y.toDateString() ? "Yesterday"
    : d.toLocaleDateString("en", { month: "short", day: "numeric" });
  return `${day}, ${clock(ts)}`;
}
function span(a, b) {
  const s = (ms(b) - ms(a)) / 1000;
  if (!isFinite(s) || s < 0) return "";
  if (s < 60) return s < 2 ? "a second" : `${Math.round(s)} seconds`;
  const m = Math.round(s / 60);
  return m < 60 ? (m === 1 ? "1 minute" : `${m} minutes`) : `${Math.floor(m / 60)} h ${m % 60} min`;
}
const dur = (msec) => (msec < 1000 ? `${msec} ms` : `${(msec / 1000).toFixed(1)} s`);
function axisTime(sec) {
  if (sec < 10) return `${Number(sec.toFixed(1))}s`;
  if (sec < 90) return `${Math.round(sec)}s`;
  const m = sec / 60;
  return m < 90 ? `${Math.round(m)} min` : `${(m / 60).toFixed(1)} h`;
}

function detailOf(raw, key) {
  const keys = [key, ...DETAIL_KEYS].filter(Boolean);
  let found = null;
  try {
    const o = JSON.parse(raw);
    if (o && typeof o === "object") found = keys.map((k) => o[k]).find((v) => typeof v === "string" && v);
  } catch (e) {  // cut off at 200 characters: no longer valid JSON, so pick the field out by hand
    for (const k of keys) {
      const m = raw.match(new RegExp(`"${k}":\\s*"((?:[^"\\\\]|\\\\.)*)`));
      if (m) { found = m[1].replace(/\\n/g, " ").replace(/\\"/g, '"').replace(/\\\\/g, "\\"); break; }
    }
  }
  if (!found) return raw;
  const parts = found.split("/");  // long file paths: the last two parts say enough
  return /path$/.test(key || "") && parts.length > 3 ? `.../${parts.slice(-2).join("/")}` : found;
}

function describe(c) {
  const tool = c.tool || "";
  const server = tool.startsWith("mcp__") ? tool.split("__")[1] : null;
  const [verb, ic, key, same] = TOOLS[tool] || [server ? `Used ${server}` : tool ? `Used ${tool}` : "Took an action",
    server ? "plug" : "wrench", null, "Did the same thing"];
  const raw = tool && c.action.startsWith(`${tool} `) ? c.action.slice(tool.length + 1) : c.action;
  return { verb, icon: ic, same, raw, detail: detailOf(raw, key) };
}

async function api(path, options) {
  const r = await fetch(path, { credentials: "same-origin", ...options });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(body.error || TEXT.notFound), { status: r.status, body });
  return body;
}
const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });

function toast(message, href) {
  const t = document.getElementById("toast");
  t.replaceChildren(...[h("span", {}, message), href ? h("a", { href }, TEXT.seeWhy) : null].filter(Boolean));
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { t.hidden = true; }, 8000);
}

function confirmDialog(title, text, ok) {
  const d = document.getElementById("confirm");
  document.getElementById("confirm-title").textContent = title;
  document.getElementById("confirm-text").textContent = text;
  document.getElementById("confirm-ok").textContent = ok;
  d.returnValue = "";  // Esc keeps the old value, so a past "ok" would count as yes
  return new Promise((resolve) => {
    d.addEventListener("close", () => resolve(d.returnValue === "ok"), { once: true });
    d.showModal();
  });
}

let helpSeq = 0;
function help(key) {  // a "?" with its one-line explanation (native popover: Esc and outside clicks close it)
  const [title, text] = HELP[key];
  const id = `help-${helpSeq++}`;
  return [h("button", { class: "help", type: "button", popovertarget: id, "aria-label": `What does "${title}" mean?` }, icon("circle-help")),
    h("div", { class: "pop", id, popover: "auto" }, h("strong", {}, title), text)];
}

// ---- actions (FR-005): every change asks first ----

async function act(path, body, title, text, ok) {
  if (!(await confirmDialog(title, text, ok))) return;
  try {
    toast((await post(path, body)).message);
  } catch (e) {
    toast(e.message);
  }
  state.version = -1;
  render();
}
const mistakeButton = (t, cls = "") => h("button", { class: `button ${cls}`, type: "button",
  onclick: () => act("/api/mistake", { task: t.id }, TEXT.markMistakeTitle, TEXT.markMistakeText, TEXT.notStuck) }, icon("shield-check"), TEXT.notStuck);
const leaveOutButton = (t) => h("button", { class: "button quiet", type: "button",
  onclick: () => act("/api/exclude", { task: t.id }, TEXT.leaveOutTitle, TEXT.leaveOutText, TEXT.leaveOut) }, icon("funnel"), TEXT.leaveOut);
const doneTag = (text) => h("span", { class: "tag ok" }, icon("check"), text);

// ---- shared pieces ----

function titleFor(t) {
  const n = t.state === "stopped" && t.stop_at ? t.stop_at : t.calls;
  if (t.state === "stopped") return `Stopped after ${actions(n)}`;
  if (t.state === "finished") return `Finished after ${actions(n)}`;
  if (t.state === "interrupted") return `Interrupted after ${actions(n)}`;
  if (t.state === "idle") return `${actions(n)}, then no activity`;
  return t.limit == null ? `${actions(n)} so far` : `${n} of ${t.limit} actions`;
}
const chip = (t) => h("span", { class: `chip ${t.state}` }, icon(STATES[t.state][1]), STATES[t.state][0]);
function track(t) {
  const near = t.state === "running" && t.calls >= 0.8 * t.limit;
  const el = h("span", { class: `track${t.state === "stopped" ? " stopped" : near ? " near" : ""}`, "aria-hidden": "true" }, h("span", { class: "fill" }));
  el.firstChild.style.width = `${Math.min(100, ((t.stop_at || t.calls) / t.limit) * 100)}%`;
  return el;
}
const symptom = (t) => (t.symptoms && t.symptoms.length ? SYMPTOMS[t.symptoms[0]] : "It went far past how long tasks here usually take.");

function taskRow(t) {
  const limit = t.limit != null && t.state !== "running" ? ` (limit ${t.limit})` : "";
  return h("a", { class: "row", href: link(t) },
    h("div", { class: "fit" }, h("div", { class: "name" }, t.label), h("div", { class: "meta" }, `${titleFor(t)}${limit} · ${dayTime(t.started)}`)),
    h("div", { class: "side-r" }, chip(t), icon("chevron-right")),
    t.limit != null ? track(t) : null);
}

function projectRow(p) {
  const meta = [p.limit != null ? TEXT.limitActions(p.limit) : TEXT.watchingNoLimit, p.median ? TEXT.usually(Math.round(p.median)) : null].filter(Boolean).join(", ");
  return h("a", { class: "row", href: `#/project/${encodeURIComponent(p.name)}` },
    h("div", { class: "fit" }, h("div", { class: "name" }, p.label), h("div", { class: "meta" }, meta)),
    h("div", { class: "side-r" }, h("span", { class: "meta" }, TEXT.thisWeek(p.week)), icon("chevron-right")));
}

// ---- charts: inline SVG, no library; every mark explains itself on hover or tap ----

const chartWidth = (share = 1) => Math.max(300, Math.round((document.getElementById("main").clientWidth - 110) * share));

function spark(values, bars) {
  const w = 84, hh = 34, max = Math.max(1, ...values);
  if (bars) {
    const bw = w / values.length;
    return h("svg", { class: "spark", viewBox: `0 0 ${w} ${hh}`, "aria-hidden": "true" }, values.map((v, i) =>
      h("rect", { class: v ? "bar stop" : "bar zero", x: i * bw + 1, width: Math.max(1, bw - 2), y: hh - Math.max(v ? 3 : 1, (v / max) * (hh - 2)), height: Math.max(v ? 3 : 1, (v / max) * (hh - 2)) })));
  }
  const pts = values.map((v, i) => [(i * w) / Math.max(1, values.length - 1), hh - 3 - (v / max) * (hh - 8)]);
  const line = pts.map((p) => p.join(",")).join(" ");
  return h("svg", { class: "spark", viewBox: `0 0 ${w} ${hh}`, "aria-hidden": "true" },
    h("polygon", { class: "area", points: `0,${hh} ${line} ${w},${hh}` }), h("polyline", { class: "line", points: line }));
}

function barChart(days, key, label, unit) {
  const W = chartWidth(0.55), H = 130, B = 22, max = Math.max(1, ...days.map((d) => d[key]));
  const bw = W / days.length;
  const fmt = (d) => new Date(`${d}T12:00:00`).toLocaleDateString("en", { month: "short", day: "numeric" });
  const total = days.reduce((a, d) => a + d[key], 0);
  return h("svg", { class: "chart bars", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `${label}, ${TEXT.last30}: ${short(total)} in all` },
    h("line", { class: "axis", x1: 0, x2: W, y1: H - B, y2: H - B }),
    days.map((d, i) => {
      const bh = d[key] ? Math.max(3, (d[key] / max) * (H - B - 14)) : 0;
      return h("rect", { class: key === "stops" ? "bar stop" : "bar", x: i * bw + 2, width: Math.max(2, bw - 4), y: H - B - bh, height: bh, rx: 2 },
        h("title", {}, `${fmt(d.day)}: ${short(d[key])} ${unit}`));
    }),
    h("text", { x: 0, y: H - 6 }, fmt(days[0].day)), h("text", { x: W, y: H - 6, "text-anchor": "end" }, "Today"),
    h("text", { x: 0, y: 10 }, `${short(max)}`));
}

// Past finished tasks as dots on a line, the limit, and this task (the picture behind every stop).
function pastStrip(lengths, limit, mark, share = 1) {
  const W = chartWidth(share), H = 128, L = 10, R = 16, base = 96;
  const finite = (lengths || []).filter((v) => v != null);
  const top = Math.max(1, ...finite, limit ?? 0, mark ?? 0) * 1.08;
  const x = (v) => L + (v / top) * (W - L - R);
  const buckets = new Map();
  for (const v of finite) { const b = Math.round(x(v) / 8); buckets.set(b, (buckets.get(b) || 0) + 1); }
  const step = Math.min(8, (base - 22) / Math.max(1, ...buckets.values()));
  const seen = new Map();
  const dots = finite.map((v) => {
    const b = Math.round(x(v) / 8), k = seen.get(b) || 0;
    seen.set(b, k + 1);
    return h("circle", { class: "past", cx: x(v), cy: base - 6 - k * step, r: 3.6 }, h("title", {}, `A past task: ${actions(v)}`));
  });
  const label = `${finite.length} past finished tasks${limit != null ? `, limit ${limit}` : ""}${mark ? `, this task ${mark}` : ""}`;
  return h("svg", { class: "chart strip", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": label },
    h("line", { class: "axis", x1: L, x2: W - R, y1: base, y2: base }),
    mark && x(mark) < L + 90 ? null : h("text", { x: L, y: base + 18 }, mark ? "0" : "0 actions"),
    mark ? null : h("text", { x: W - R, y: base + 18, "text-anchor": "end" }, `${Math.round(top)}`),
    dots,
    limit != null ? [h("line", { class: "limit", x1: x(limit), x2: x(limit), y1: 10, y2: base }),
      h("text", { class: "limitlabel", x: x(limit) > 90 ? x(limit) - 6 : x(limit) + 6, y: 12, "text-anchor": x(limit) > 90 ? "end" : "start" }, `Limit ${limit}`)] : null,
    mark ? [h("circle", { class: "this", cx: x(mark), cy: base - 6, r: 7 }, h("title", {}, `This task: ${actions(mark)}`)),
      h("text", { x: x(mark), y: base + 18, "text-anchor": x(mark) > W / 2 ? "end" : "start", class: "limitlabel" }, `This task: ${mark}`)] : null);
}

// Actions over time: the count climbing toward the limit; point at it to read each action.
function timeChart(calls, s) {
  const W = chartWidth(1), H = 250, L = 34, R = 18, T = 20, B = 30;
  const t0 = ms(s.started);
  const tx = calls.map((c, i) => { const v = (ms(c.ts) - t0) / 1000; return isFinite(v) ? Math.max(0, v) : i; });
  const tMax = Math.max(1, ...tx);
  const nMax = Math.max(s.limit ?? 0, calls.length ? calls[calls.length - 1].n : 0, 4) * 1.1;
  const x = (v) => L + (v / tMax) * (W - L - R), y = (n) => H - B - (n / nMax) * (H - T - B);
  const pts = calls.map((c, i) => [x(tx[i]), y(c.n)]);
  const line = [[x(0), y(0)], ...pts].map((p) => p.join(",")).join(" ");
  const last = pts.length ? pts[pts.length - 1][0] : x(0);
  const guide = h("line", { class: "guide", y1: T, y2: H - B, visibility: "hidden" });
  const hl = h("circle", { class: "hl", r: 5, visibility: "hidden" });
  const tip = h("div", { class: "tip", hidden: true });
  const svg = h("svg", { class: "chart time", viewBox: `0 0 ${W} ${H}`, role: "img",
      "aria-label": `${actions(calls.length)} over ${axisTime(tMax)}${s.limit != null ? `, limit ${s.limit}` : ""}` },
    h("line", { class: "axis", x1: L, x2: W - R, y1: H - B, y2: H - B }),
    [0.5, 1].map((f) => h("line", { class: "grid", x1: L, x2: W - R, y1: y(nMax * f / 1.1), y2: y(nMax * f / 1.1) })),
    h("text", { x: L - 8, y: H - B + 4, "text-anchor": "end" }, "0"),
    h("text", { x: L - 8, y: y(nMax / 1.1) + 4, "text-anchor": "end" }, String(Math.round(nMax / 1.1))),
    [0, 0.5, 1].map((f) => h("text", { x: x(tMax * f), y: H - 8, "text-anchor": f === 0 ? "start" : f === 1 ? "end" : "middle" }, axisTime(tMax * f))),
    h("polygon", { class: "areafill", points: `${x(0)},${y(0)} ${line.split(" ").slice(1).join(" ")} ${last},${y(0)}` }),
    h("polyline", { class: "count", points: line }),
    s.limit != null ? [h("line", { class: "limit", x1: L, x2: W - R, y1: y(s.limit), y2: y(s.limit) }),
      h("text", { class: "limitlabel", x: L + 8, y: y(s.limit) - 7 }, `Limit ${s.limit}`)] : null,
    calls.map((c, i) => (c.failed || c.repeats ? h("circle", { class: c.failed ? "dot failed" : "dot repeat", cx: pts[i][0], cy: pts[i][1], r: 3.4 }) : null)),
    calls.map((c, i) => (c.n === s.stop_at ? h("circle", { class: "stopmark", cx: pts[i][0], cy: pts[i][1], r: 6.5 }) : null)),
    guide, hl,
    h("rect", { class: "hit", x: L, y: T, width: W - L - R, height: H - T - B }));
  const show = (e) => {
    if (!calls.length) return;
    const ctm = svg.getScreenCTM();
    if (!ctm) return;
    const px = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse()).x;
    let i = 0;
    for (let j = 1; j < pts.length; j += 1) if (Math.abs(pts[j][0] - px) < Math.abs(pts[i][0] - px)) i = j;
    const [cx, cy] = pts[i], c = calls[i];
    for (const [el, a] of [[guide, { x1: cx, x2: cx }], [hl, { cx, cy }]]) {
      for (const [k, v] of Object.entries(a)) el.setAttribute(k, v);
      el.setAttribute("visibility", "visible");
    }
    tip.replaceChildren(h("strong", {}, `${c.n}. ${c.d.verb}`), h("span", { class: "muted" }, c.d.detail.slice(0, 90)), h("br"),
      `${clock(c.ts, true)}${c.failed ? ` · ${TEXT.failed}` : ""}${c.repeats ? ` · ${TEXT.repeated}` : ""}${c.n === s.stop_at ? ` · ${TEXT.stopped}` : ""}`);
    tip.hidden = false;
    const p = new DOMPoint(cx, cy).matrixTransform(ctm), box = wrap.getBoundingClientRect();
    const left = p.x - box.left, wide = box.width;
    tip.style.left = `${Math.min(Math.max(0, left - 150), wide - 300 > 0 ? wide - 300 : 0)}px`;
    tip.style.top = `${Math.max(0, p.y - box.top - 90)}px`;
  };
  const hide = () => { state.pointerInChart = false; tip.hidden = true; guide.setAttribute("visibility", "hidden"); hl.setAttribute("visibility", "hidden"); };
  svg.addEventListener("pointermove", (e) => { state.pointerInChart = true; show(e); });
  svg.addEventListener("pointerdown", show);
  svg.addEventListener("pointerleave", hide);
  const wrap = h("div", { class: "chart-wrap" }, svg, tip);
  return wrap;
}

// The actions a task repeated, grouped by what they did (same tool, same command or file): a loop, said plainly.
function loops(calls) {
  const groups = new Map();
  for (const c of calls) {
    const k = `${c.tool}\u0000${c.d.detail}`;  // what a person sees: the command or file, not the agent's notes
    const g = groups.get(k) || { c, count: 0, first: c.ts, last: c.ts };
    g.count += 1;
    g.last = c.ts;
    groups.set(k, g);
  }
  return [...groups.values()].filter((g) => g.count >= 2).sort((a, b) => b.count - a.count).slice(0, 3);
}

// ---- views ----

const state = { version: -1, pages: {}, tasksPages: 1, openTool: null, openRows: new Set(),
  callFilter: "all", showAll: new Set(), tf: { status: "", project: "", q: "" }, lastStop: undefined, pointerInChart: false };
const savedName = () => { try { return (localStorage.getItem("lb-name") || "").trim(); } catch (e) { return ""; } };

async function home() {
  const [o, projects] = await Promise.all([api("/api/overview"), api("/api/projects")]);
  const hour = new Date().getHours();
  const head = h("div", { class: "head" }, h("div", { class: "grow" },
    h("h1", {}, TEXT.greeting(hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening", savedName() || o.name)), h("p", { class: "sub" }, TEXT.sub)));
  if (!o.seen) {
    return [head, h("section", { class: "card empty" }, h("h2", {}, icon("sparkles"), TEXT.startTitle),
      h("ol", {}, TEXT.startSteps.map((s) => h("li", {}, s))), h("p", { class: "muted" }, TEXT.startNote))];
  }
  const today = o.days[o.days.length - 1], week = o.days.slice(-7);
  const stopsWeek = week.reduce((a, d) => a + d.stops, 0), tokensWeek = week.reduce((a, d) => a + d.tokens, 0);
  const latest = o.recent_stops[0];
  const banner = today.stops
    ? h("div", { class: "banner stop" }, h("span", { class: "dot" }, icon("octagon-x")), h("p", {}, TEXT.stoppedToday(today.stops)),
      latest ? h("a", { class: "button small", href: link(latest) }, TEXT.seeWhy, icon("arrow-right")) : null)
    : o.watching_only
      ? h("div", { class: "banner watch" }, h("span", { class: "dot" }, icon("eye")), h("p", {}, TEXT.watchingOnly), help("watching"))
      : h("div", { class: "banner ok" }, h("span", { class: "dot" }, icon("shield-check")),
        h("p", {}, o.running.length ? TEXT.workingNow(o.running.length) : stopsWeek ? TEXT.quietWeek(stopsWeek) : TEXT.allQuiet));
  const tile = (label, ic, value, note, chart, helpKey) => h("div", { class: "tile" },
    h("span", { class: "label" }, icon(ic), label, helpKey ? help(helpKey) : null), h("span", { class: "value" }, value), chart, note ? h("span", { class: "note" }, note) : null);
  const tiles = h("section", { class: "tiles", "aria-label": "Totals" },
    tile(TEXT.tasksWeek, "layers", o.week, TEXT.last7, spark(week.map((d) => d.tasks)), "task"),
    tile(TEXT.stopped, "octagon-x", o.stopped, TEXT.marked(o.mistaken), spark(o.days.slice(-14).map((d) => d.stops), true)),
    tokensWeek ? tile(TEXT.tokensWeek, "coins", short(tokensWeek), TEXT.spent, spark(week.map((d) => d.tokens)))
      : tile(TEXT.workingTile, "activity", o.running.length, TEXT.rightNow, null));
  const live = o.running.map((t) => h("a", { class: "card link live", href: link(t) },
    h("div", { class: "top" }, h("span", { class: "pulse", "aria-hidden": "true" }), h("strong", {}, TEXT.workingIn(t.label)),
      h("span", { class: "muted small" }, TEXT.started(ago(t.started)))),
    h("div", { class: "count" }, t.limit == null ? actions(t.calls) : `${t.calls} of ${t.limit} actions`),
    t.limit != null ? track(t) : h("p", { class: "muted small" }, TEXT.noLimitYet),
    t.limit != null && t.calls >= 0.8 * t.limit ? h("p", { class: "small" }, TEXT.near) : null));
  const stops = h("section", { class: "card" },
    h("div", { class: "titlerow" }, h("h2", {}, icon("octagon-x"), TEXT.recentStops),
      o.recent_stops.length ? h("a", { class: "more", href: "#/tasks", onclick: () => { state.tf.status = "stopped"; } }, TEXT.viewAll, icon("arrow-right")) : null),
    o.recent_stops.length ? h("div", { class: "rows" }, o.recent_stops.slice(0, 3).map((t) => h("div", { class: "stopcard" },
      h("div", { class: "meta muted small" }, `${t.label} · ${dayTime(t.ended || t.started)}`),
      h("div", { class: "what" }, `Stopped after ${actions(t.stop_at)} (limit ${t.limit})`),
      h("p", { class: "muted" }, symptom(t)),
      h("div", { class: "actions" }, h("a", { class: "button small", href: link(t) }, TEXT.seeWhy, icon("arrow-right")),
        t.marks.includes("mistaken") ? doneTag(TEXT.markedMistake) : mistakeButton(t, "small quiet"))))) : h("p", { class: "muted" }, TEXT.noStops));
  const charts = h("section", { class: "card" }, h("div", { class: "titlerow" }, h("h2", {}, icon("chart-column"), TEXT.stopsPerDay),
    h("span", { class: "muted small" }, TEXT.last30)), barChart(o.days, "stops", TEXT.stopsPerDay, "stops"),
    o.days.some((d) => d.tokens) ? [h("h2", { class: "sect" }, icon("coins"), TEXT.tokensPerDay), barChart(o.days, "tokens", TEXT.tokensPerDay, "tokens")] : null);
  const proj = h("section", { class: "card" },
    h("div", { class: "titlerow" }, h("h2", {}, icon("folder"), TEXT.projects), h("a", { class: "more", href: "#/projects" }, TEXT.viewAll, icon("arrow-right"))),
    h("div", { class: "rows" }, [...projects].sort((a, b) => b.week - a.week).slice(0, 5).map(projectRow)));
  return [head, banner, tiles, live, h("div", { class: "grid2" }, h("div", { class: "stack" }, stops, charts), h("div", { class: "stack" }, proj))];
}

async function tasksView() {
  const f = state.tf;
  const qs = new URLSearchParams({ limit: "50" });
  if (f.status) qs.set("status", f.status);
  if (f.project) qs.set("project", f.project);
  let page = await api(`/api/tasks?${qs}`);
  let list = page.tasks;
  for (let i = 1; i < state.tasksPages && page.next; i += 1) {
    qs.set("before", page.next);
    page = await api(`/api/tasks?${qs}`);
    list = list.concat(page.tasks);
  }
  const projects = await api("/api/projects");
  const chips = [["", TEXT.all], ["running", STATES.running[0]], ["stopped", STATES.stopped[0]], ["finished", STATES.finished[0]],
    ["interrupted", STATES.interrupted[0]]].map(([v, label]) => h("button", { class: "chip-filter", type: "button", "aria-pressed": String(f.status === v),
    onclick: () => { f.status = v; state.tasksPages = 1; render(); } }, label));
  const select = h("select", { "aria-label": TEXT.allProjects, onchange: (e) => { f.project = e.target.value; state.tasksPages = 1; render(); } },
    h("option", { value: "" }, TEXT.allProjects), projects.map((p) => h("option", { value: p.name, selected: p.name === f.project }, p.label)));
  const rows = list.map(taskRow);
  const filter = (q) => {
    let shown = 0;
    for (const r of rows) { r.hidden = Boolean(q) && !r.textContent.toLowerCase().includes(q.toLowerCase()); shown += !r.hidden; }
    none.hidden = shown > 0;
  };
  const none = h("p", { class: "muted", hidden: true }, TEXT.noMatch);
  const search = h("input", { type: "search", placeholder: TEXT.search, "aria-label": TEXT.search, value: f.q,
    oninput: (e) => { f.q = e.target.value; filter(f.q); } });
  const out = [h("div", { class: "head" }, h("div", { class: "grow" }, h("h1", {}, TEXT.tasksTitle), h("p", { class: "sub" }, TEXT.tasksSub))),
    h("div", { class: "filters", role: "group", "aria-label": "Show" }, chips, select, search),
    h("section", { class: "card" }, h("div", { class: "rows" }, rows), none,
      page.next ? h("button", { class: "button quiet mt", type: "button", onclick: () => { state.tasksPages += 1; render(); } }, TEXT.loadMore) : null)];
  filter(f.q);
  if (!rows.length) none.hidden = false;
  return out;
}

async function task(session, run) {
  const key = `${session}/${run}`;
  const pages = state.pages[key] || 1;
  const first = await api(`/api/task/${session}/${run}?page=0`);
  let raw = first.calls;
  for (let p = 1; p < pages; p += 1) raw = raw.concat((await api(`/api/task/${session}/${run}?page=${p}`)).calls);
  const s = first.summary;
  const p = await api(`/api/project/${encodeURIComponent(s.project)}`).catch(() => null);
  const calls = raw.map((c) => ({ ...c, d: describe(c) }));
  const end = s.ended || (calls.length ? calls[calls.length - 1].ts : s.started);
  const took = span(s.started, end);
  const head = [h("a", { class: "back", href: "#/tasks" }, icon("chevron-left"), TEXT.back),
    h("div", { class: "head" }, h("div", { class: "grow story" },
      h("a", { class: "more", href: `#/project/${encodeURIComponent(s.project)}` }, icon("folder"), s.label),
      h("div", { class: "titleline" }, h("h1", {}, titleFor(s)), help("action")),
      h("p", { class: "sub" }, [dayTime(s.started), took ? TEXT.took(took) : null].filter(Boolean).join(" · "))), chip(s))];

  let verdict;
  if (s.state === "stopped") {
    const median = p && p.median ? Math.round(p.median) : null;
    verdict = h("section", { class: "card why" }, h("h2", {}, icon("triangle-alert"), TEXT.whyTitle),
      h("p", { class: "lead" }, TEXT.whyLead(median, s.limit, oneIn(p ? p.alpha : 0.05), s.stop_at), " ", symptom(s)),
      p && p.lengths ? [pastStrip(p.lengths, s.limit, s.stop_at), h("p", { class: "muted small" }, TEXT.pictureNote, help("limit"))] : null,
      h("div", { class: "actions" }, s.marks.includes("mistaken") ? doneTag(TEXT.markedMistake) : mistakeButton(s), help("mistake")));
  } else if (s.state === "finished") {
    verdict = h("section", { class: "card" }, h("h2", {}, icon("circle-check"), TEXT.howItWent), h("p", {}, TEXT.finishedNote(s.calls, s.limit)),
      p && p.lengths ? pastStrip(p.lengths, s.limit, s.calls) : null,
      h("div", { class: "actions mt" }, s.marks.includes("left_out") ? doneTag(TEXT.leftOut) : leaveOutButton(s), help("leaveOut")));
  } else {
    verdict = h("section", { class: "card" }, h("h2", {}, icon(STATES[s.state][1]), STATES[s.state][0]),
      h("p", {}, s.state === "interrupted" ? TEXT.interruptedNote : s.state === "idle" ? TEXT.idleNote : TEXT.liveNote),
      s.limit != null && s.state === "running" ? [h("p", { class: "big num mt" }, `${s.calls} of ${s.limit} actions`), track(s)] : null);
  }

  const groups = loops(calls);
  const kept = groups.length ? h("section", { class: "card" }, h("h2", {}, icon("repeat"), TEXT.keptDoing), h("p", { class: "muted mb" }, TEXT.keptNote),
    h("div", { class: "loops" }, groups.map((g) => h("div", { class: "loop" }, h("span", { class: "badge" }, icon(g.c.d.icon)),
      h("div", { class: "fit" }, h("strong", {}, `${g.c.d.same} ${g.count} times`), h("code", {}, g.c.d.detail)),
      h("span", { class: "muted small" }, clock(g.first) === clock(g.last) ? clock(g.first) : `${clock(g.first)} to ${clock(g.last)}`))))) : null;

  const failedN = calls.filter((c) => c.failed).length, repeatN = calls.filter((c) => c.repeats).length;
  const fchips = [["all", `${TEXT.all} (${calls.length})`], ["failed", `${TEXT.failed} (${failedN})`], ["repeat", `${TEXT.repeated} (${repeatN})`]].map(([v, label]) =>
    h("button", { class: "chip-filter", type: "button", "aria-pressed": String(state.callFilter === v), onclick: () => { state.callFilter = v; render(); } }, label));
  const matching = calls.filter((c) => state.callFilter === "all" || (state.callFilter === "failed" ? c.failed : c.repeats));
  const FEW = 15;  // a long list buries the page: show a few, the rest on request
  const shown = state.showAll.has(key) ? matching : matching.slice(0, FEW);
  const rowKey = (c) => `${key}:${c.n}`;
  const list = shown.map((c) => h("details", { class: c.n === s.stop_at ? "call at-stop" : "call", open: state.openRows.has(rowKey(c)),
      ontoggle: (e) => { if (e.target.open) state.openRows.add(rowKey(c)); else state.openRows.delete(rowKey(c)); } },
    h("summary", {}, h("span", { class: "n num" }, c.n), h("span", { class: "badge" }, icon(c.d.icon)),
      h("span", { class: "what" }, h("span", { class: "verb" }, c.d.verb), h("span", { class: "detail" }, c.d.detail)),
      h("span", { class: "tags" }, c.failed ? h("span", { class: "tag failed" }, icon("x"), TEXT.failed) : null,
        c.repeats ? h("span", { class: "tag repeat" }, icon("repeat"), TEXT.repeated) : null,
        c.n === s.stop_at ? h("span", { class: "chip stopped" }, icon("octagon-x"), TEXT.stopped) : null),
      h("span", { class: "when" }, clock(c.ts, true), c.duration_ms != null ? ` · ${dur(c.duration_ms)}` : "")),
    h("div", { class: "full" }, h("code", {}, c.d.raw),
      h("div", { class: "actions" }, h("button", { class: "button small quiet", type: "button", onclick: async () => {
        try { await navigator.clipboard.writeText(c.d.raw); toast(TEXT.copied); } catch (e) { toast(TEXT.copyFailed); }
      } }, icon("copy"), TEXT.copy)))));
  const more = calls.length < first.total;
  const timeline = calls.length ? h("section", { class: "card" },
    h("div", { class: "titlerow" }, h("h2", {}, icon("activity"), TEXT.overTime),
      h("div", { class: "legend" }, s.limit != null ? h("span", {}, h("i", { class: "key limit" }), "Limit") : null,
        h("span", {}, h("i", { class: "key failed" }), TEXT.failed), h("span", {}, h("i", { class: "key repeat" }), TEXT.repeated, help("repeated")))),
    timeChart(calls, s), more ? h("p", { class: "muted small" }, TEXT.firstOf(calls.length, first.total)) : null) : null;
  const all = h("section", { class: "card" }, h("div", { class: "titlerow" }, h("h2", {}, icon("list"), TEXT.allActions(first.total))),
    h("div", { class: "filters mb", role: "group", "aria-label": "Show" }, fchips),
    h("div", { class: "calls" }, list),
    matching.length > shown.length ? h("button", { class: "button quiet mt", type: "button", onclick: () => { state.showAll.add(key); render(); } },
      TEXT.showAll(matching.length)) : null,
    more && shown.length === matching.length ? h("button", { class: "button quiet mt", type: "button", onclick: () => { state.pages[key] = pages + 1; render(); } }, TEXT.loadMore) : null);
  return [head, verdict, kept, timeline, all];
}

async function projectsView() {
  const ps = await api("/api/projects");
  const head = h("div", { class: "head" }, h("div", { class: "grow" }, h("h1", {}, TEXT.projects), h("p", { class: "sub" }, TEXT.projectsSub)));
  if (!ps.length) return [head, h("p", { class: "muted" }, TEXT.noProjects)];
  return [head, h("section", { class: "card" }, h("div", { class: "rows" }, ps.map(projectRow)))];
}

async function project(name) {
  const p = await api(`/api/project/${encodeURIComponent(name)}`);
  const recent = await api(`/api/tasks?${new URLSearchParams({ project: name, limit: "8" })}`);
  const limit = h("section", { class: "card" }, h("div", { class: "titleline" }, h("h2", {}, icon("gauge"), TEXT.limitTitle), help("limit")),
    p.limit != null
      ? [h("p", { class: "big num" }, `${p.limit} actions`), h("p", { class: "serif" }, TEXT.promise(oneIn(p.alpha))),
        p.median ? h("p", { class: "muted" }, TEXT.usuallyPer(Math.round(p.median))) : null]
      : [h("p", { class: "big" }, TEXT.notSet), p.needed ? h("p", { class: "muted" }, TEXT.needs(p.n || 0, p.needed)) : null],
    p.lengths ? [h("h2", { class: "sect" }, icon("layers"), TEXT.pastTasks), pastStrip(p.lengths, p.limit, null, 0.55)] : null,
    p.n && p.created ? h("p", { class: "muted small mt" }, TEXT.setFrom(p.n, p.created)) : null,
    p.can_recalibrate ? h("div", { class: "actions mt" }, h("button", { class: "button", type: "button",
      onclick: () => act("/api/recalibrate", { project: p.name }, TEXT.setAgainTitle, TEXT.setAgainText, TEXT.setAgainOk) }, icon("refresh-cw"), TEXT.setAgain)) : null);
  const so = h("section", { class: "card" }, h("h2", {}, icon("activity"), TEXT.soFar),
    h("p", {}, [TEXT.seenN(p.seen), TEXT.stoppedN(p.stopped)].join(", ")),
    h("p", { class: "muted" }, TEXT.mistakes(p.mistaken, about(p.normal_mistakes)), help("mistake")));
  return [h("a", { class: "back", href: "#/projects" }, icon("chevron-left"), TEXT.back),
    h("div", { class: "head" }, h("div", { class: "grow" }, h("h1", {}, p.label),
      h("p", { class: "sub" }, p.agent === "claude-code" ? TEXT.claudeProject : TEXT.agentProject))),
    h("div", { class: "grid2" }, limit, h("div", { class: "stack" }, so,
      recent.tasks.length ? h("section", { class: "card" }, h("h2", {}, icon("list"), TEXT.recentTasks), h("div", { class: "rows" }, recent.tasks.map(taskRow))) : null))];
}

async function exportAction(path) {
  try { toast((await post(path)).message); } catch (e) { toast(e.message); }
  render();
  if (path.endsWith("/send")) setTimeout(render, 4000);  // the background send records its result
}

function setupBlock([tool, lines]) {
  const text = ["export LOOPBRAKE_EXPORT=otlp", ...lines.map((l) => `export ${l}`)].join("\n");
  const copy = async () => { try { await navigator.clipboard.writeText(text); toast(TEXT.copied); } catch (e) { toast(TEXT.copyFailed); } };
  return h("details", { class: "setup", open: state.openTool === tool, ontoggle: (e) => {
    if (e.target.open) state.openTool = tool; else if (state.openTool === tool) state.openTool = null;
  } }, h("summary", {}, tool), h("pre", {}, h("code", {}, text)), h("button", { class: "button small quiet", type: "button", onclick: copy }, icon("copy"), TEXT.copy));
}

function themeChoice() { try { return localStorage.getItem("lb-theme") || "system"; } catch (e) { return "system"; } }
function applyTheme(choice) {
  if (choice === "light" || choice === "dark") document.documentElement.dataset.theme = choice;
  else delete document.documentElement.dataset.theme;
}

async function settings() {
  const x = await api("/api/export");
  const choice = themeChoice();
  const seg = h("div", { class: "seg", role: "group", "aria-label": TEXT.appearance },
    [["system", TEXT.themeSystem, "monitor"], ["light", TEXT.themeLight, "sun"], ["dark", TEXT.themeDark, "moon"]].map(([v, label, ic]) =>
      h("button", { type: "button", "aria-pressed": String(choice === v), onclick: () => {
        try { localStorage.setItem("lb-theme", v); } catch (e) { /* blocked: still applies now */ }
        applyTheme(v);
        render();
      } }, icon(ic), label)));
  const name = h("input", { type: "text", id: "lb-name", maxlength: "30", value: savedName(), autocomplete: "given-name",
    oninput: (e) => { try { localStorage.setItem("lb-name", e.target.value.trim()); } catch (err) { /* blocked */ } } });
  const last = x.last;
  const exportCard = h("section", { class: "card" }, h("h2", {}, icon("send"), TEXT.exportTitle),
    x.on ? [h("p", { class: "big" }, TEXT.exportOn(x.endpoint)), h("p", { class: "muted" }, x.content ? TEXT.exportWhatContent : TEXT.exportWhat),
      x.metrics ? null : h("p", { class: "muted" }, TEXT.exportNoCounters), x.warning ? h("p", { class: "muted" }, icon("triangle-alert"), " ", x.warning) : null]
      : [h("p", { class: "big" }, TEXT.exportOff), h("p", { class: "muted" }, TEXT.exportOffText)],
    h("p", { class: "muted small mt" }, TEXT.exportFromShell),
    x.on ? [h("h2", { class: "sect" }, TEXT.lastSend),
      !last ? h("p", { class: "muted" }, TEXT.neverSent)
        : last.ok ? h("p", {}, icon("check"), " ", TEXT.sentTasks(last.tasks, ago(last.at)))
          : [h("p", {}, h("span", { class: "tag failed" }, icon("x"), TEXT.failed), " ", TEXT.sendFailed(ago(last.at))), h("p", { class: "muted problem" }, x.problem)],
      h("div", { class: "actions mt" },
        h("button", { class: "button", type: "button", onclick: () => exportAction("/api/export/send") }, icon("send"), TEXT.sendNow),
        h("button", { class: "button quiet", type: "button", onclick: () => exportAction("/api/export/test") }, icon("activity"), TEXT.testConnection))] : null,
    h("h2", { class: "sect" }, icon("square-terminal"), TEXT.setup), h("p", { class: "muted" }, TEXT.setupHint),
    SETUP.map(setupBlock), h("p", { class: "muted small" }, TEXT.protobufOnly));
  return [h("div", { class: "head" }, h("div", { class: "grow" }, h("h1", {}, TEXT.settingsTitle), h("p", { class: "sub" }, TEXT.privacy))),
    h("section", { class: "card" }, h("h2", {}, icon("book-open"), TEXT.howTitle),
      h("div", { class: "steps3" }, TEXT.how.map(([ic, title, text], i) => h("div", {}, h("span", { class: "badge" }, icon(ic)),
        h("strong", {}, `${i + 1}. ${title}`), h("p", { class: "muted" }, text))))),
    h("div", { class: "grid2" },
      h("div", { class: "stack" },
        h("section", { class: "card" }, h("h2", {}, icon("user"), TEXT.you),
          h("div", { class: "field" }, h("label", { for: "lb-name" }, TEXT.nameLabel), name, h("p", { class: "muted small" }, TEXT.nameHint))),
        h("section", { class: "card" }, h("h2", {}, icon("sun"), TEXT.appearance), seg, h("p", { class: "muted small mt" }, TEXT.themeNote)),
        h("section", { class: "card" }, h("h2", {}, icon("circle-help"), TEXT.wordsTitle),
          h("dl", { class: "words" }, WORDS.map((k) => [h("dt", {}, HELP[k][0]), h("dd", {}, HELP[k][1])])))),
      exportCard)];
}

// ---- routing and live updates ----

function route() {
  const parts = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  if (parts[0] === "task" && parts.length === 3) return ["tasks", () => task(parts[1], parts[2])];
  if (parts[0] === "tasks") return ["tasks", tasksView];
  if (parts[0] === "project" && parts.length === 2) return ["projects", () => project(parts[1])];
  if (parts[0] === "projects") return ["projects", projectsView];
  if (parts[0] === "settings" || parts[0] === "export") return ["settings", settings];
  return ["home", home];
}

async function render() {
  const [nav, view] = route();
  for (const a of document.querySelectorAll("[data-nav]")) {
    if (a.dataset.nav === nav) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  }
  const main = document.getElementById("main");
  try {
    const content = await view();
    main.replaceChildren(...[content].flat(3).filter(Boolean));
    document.dispatchEvent(new CustomEvent("lb:rendered", { detail: { nav } }));
  } catch (e) {
    main.replaceChildren(h("p", { class: "muted" }, e.status === 404 ? TEXT.notFound : TEXT.offline));
  }
}

// Don't redraw under the user's hand: an open explanation or dialog, typing, or pointing at a chart.
function busy() {
  const a = document.activeElement;
  let open = false;
  try { open = Boolean(document.querySelector(".pop:popover-open, dialog[open]")); } catch (e) { open = Boolean(document.querySelector("dialog[open]")); }
  return open || state.pointerInChart || (a && document.getElementById("main").contains(a) && /^(INPUT|SELECT|TEXTAREA)$/.test(a.tagName));
}

async function poll() {
  try {
    const c = await api("/api/changes");
    if (state.lastStop !== undefined && c.last_stop && c.last_stop !== state.lastStop && location.hash !== `#/task/${c.last_stop}`) {
      toast(TEXT.justStopped, `#/task/${c.last_stop}`);
    }
    state.lastStop = c.last_stop;
    if (c.version !== state.version && !busy()) { state.version = c.version; await render(); }
  } catch (e) { /* the next poll tries again */ }
}

// ---- glass: on, unless the system asks for less transparency or more contrast ----

const FORCED_OFF = matchMedia("(prefers-reduced-transparency: reduce), (prefers-contrast: more)");
function applyGlass() { document.documentElement.dataset.glass = FORCED_OFF.matches ? "off" : "on"; }

function initLook() {
  applyTheme(themeChoice());
  applyGlass();
  FORCED_OFF.addEventListener("change", applyGlass);
  // Refraction only where it renders right: Chromium, with SVG filters in backdrop-filter.
  const chromium = navigator.userAgentData?.brands?.some((b) => b.brand === "Chromium");
  if (chromium && CSS.supports("backdrop-filter", "url(#refract) blur(1px)")) document.documentElement.dataset.refract = "on";
  if (matchMedia("(prefers-reduced-motion: no-preference)").matches) {
    document.addEventListener("pointermove", (e) => {
      const g = e.target.closest && e.target.closest(".glass");
      if (!g) return;
      const r = g.getBoundingClientRect();
      g.style.setProperty("--sx", `${e.clientX - r.left}px`);
      g.style.setProperty("--sy", `${e.clientY - r.top}px`);
    }, { passive: true });
  }
}

window.LB = { TEXT, h, icon, api, toast, confirmDialog, render, describe, state };
initLook();
window.addEventListener("hashchange", () => { state.version = -1; state.callFilter = "all"; window.scrollTo(0, 0); render(); });
let resizeTimer;
window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(render, 300); });
render();
setInterval(poll, 1000);
