# Implementation Plan: Observability (dashboard and company-tool export)

**Branch**: `005-observability` | **Date**: 2026-10-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-observability/spec.md`

## Words used in this plan

As in the spec: **task** (a run or turn), **tool call** (a step), **limit** (the stop line). Code
and records keep their existing names (`run`, `step`, `stop_line`).

## Summary

Two read-mostly surfaces over the records LoopBrake already writes:
1. **`loopbrake dashboard`**:
   - a standard-library web server on `127.0.0.1`, with a per-launch key;
   - one page of plain HTML, CSS and JS (no framework, no build step), in the reel brand's liquid
     glass style;
   - it polls once a second and shows running tasks, stops, each task's tool calls against its
     limit, and each project's limit;
   - it lets the user mark mistakes, leave tasks out and set a limit again, through the same code
     as the Phase 3 commands.
2. **OpenTelemetry export**:
   - a standard-library OTLP/HTTP JSON sender, off unless `LOOPBRAKE_EXPORT=otlp`;
   - it runs in a detached background process when a task ends, so the agent never waits;
   - it sends one trace per task, with a span per tool call, a stop event and four counters, using
     the GenAI conventions where they fit;
   - metadata only, unless content is opted in.

**What research found** (all in [research.md](research.md)):
- **Claude Code's tool-call hook gives `duration_ms`**, and hooks get `TRACEPARENT` when Claude
  Code's tracing is on. Checked with a hook probe; one helper's claim of a `timestamp` field was
  wrong. LoopBrake records both, for exact tool-call spans and for nesting inside Claude Code's
  trace (R4).
- **Datadog's direct intake takes only delta counters, and Grafana Cloud wants cumulative.** Delta
  is the default, as the constitution says; cumulative comes only through the standard preference
  setting (R8).
- **Phoenix only takes the binary format**, so it's reached through a Collector (R8).
- **Reading 220,000 record lines takes 0.37 s** (0.07 s for summaries only), so an incremental
  in-memory index is enough (R3).
- **No vendor accounts** (the builder's decision): export is proven against a real local Collector
  and Jaeger, plus stand-ins that enforce each vendor's published intake rules (R9).

**Release**: v0.3.0.

## Technical Context

| Item | Value |
|---|---|
| **Language/Version** | Python 3.11+ (CI on 3.11–3.13); browser JS (ES2020, no build); CSS |
| **Primary Dependencies** | None at runtime: `http.server`, `urllib.request`, `json`, `secrets`, `webbrowser`, `subprocess`, `importlib.resources`. Development only: `fonttools` and `brotli` (font subsetting, through `uv run --with`), and `npx lighthouse` (the audit). |
| **Storage** | Existing records under `~/.loopbrake`, plus `export/state.json`. Additive record fields: millisecond `ts`, `step.duration_ms`, `run_start.traceparent`, `calibration.lengths`. |
| **Testing** | pytest: the server and its access rules on a real local socket; the index on growing files; the API shapes; OTLP payloads against a tiny in-process receiver; static-file checks (no emoji, no external URLs, icons exist, AA contrast); the hook path's timing with export on. Vendor stand-ins (R9) run inside the tests. Lighthouse, and a real Collector with Jaeger, by hand (quickstart). |
| **Target Platform** | macOS and Linux; current Chrome, Safari and Firefox |
| **Project Type** | Library + CLI + local web app (static files in the package) |
| **Performance Goals** | Dashboard updates within 2 s (SC-001); API replies under 100 ms at p95 on a large history; start reading about 2 million lines in 1–3 s; the hook path still at most 200 ms at p95 with export on (SC-006) |
| **Constraints** | No network unless export is on (Principle VI); the page loads nothing from the internet (CSP); no live tokens saved; plain words on screen; no emoji |
| **Scale/Scope** | One person on one computer; histories up to millions of record lines; static files under 400 KB |

No open questions remain.

## Constitution Check

*GATE: must pass before Phase 0 research. Checked again after the Phase 1 design. Checked against
constitution 2.4.1.*

| Rule | Before | After | Why it passes |
|---|---|---|---|
| I. Guarantee First | PASS | PASS | Nothing about how tasks are stopped changes. "Set the limit again" calls the same `calibration.calibrate`, with Phase 3's rules for earlier stops and mistakes. The dashboard shows mistaken stops against the allowance. |
| II. One Scorer | PASS | PASS | The dashboard decides nothing. Its "repeats an earlier call" flag calls the existing `signals.method("fuzzy")`, as an explanation only. |
| III. Stdlib-Only Core | PASS | PASS | Standard library only at runtime. The hook path gains only extra record fields, plus one detached process start at task end when export is on (measured in tests against the 200 ms budget). Font tools are development only. |
| IV. Evaluation Decides | PASS | PASS | No new stop rule. No live "tokens saved" (spec FR-006). |
| V. Thin Adapters | PASS | PASS | The dashboard and the exporter read records and call existing functions. The core imports no framework. |
| VI. Local by Default | PASS | PASS | The server binds `127.0.0.1` only. The page's CSP allows only its own origin. Export happens only with `LOOPBRAKE_EXPORT=otlp`; the standard `OTEL_*` settings alone do nothing. Metadata only, with content behind its own opt-in. No transcript content in fixtures. |
| Tech constraint: Dashboard | PASS | PASS | Standard-library server, no framework or build step, live from the logs. It shows every run with its status; a step-by-step view with the count line, the limit line and per-call signals (R5); stop reasons; per-project calibration with refresh and exclude actions; stops and tokens over time, and the mistake budget (FR-017). No live tokens saved. Security: localhost, a per-launch key, the `Host` check, POST-only changes. |
| Tech constraint: Visual identity | PASS | PASS | Reel colors and fonts; glass on chrome only; progressive enhancement; the Glass off switch; reduced motion, transparency and contrast, and forced colors; red as a fill only, with an icon and a word; Lucide only; no emoji; vendored assets; phone-first (contracts/ui.md). |
| Tech constraint: Integrations (2.4.1) | PASS | PASS | OTLP/HTTP JSON from the standard library; one trace per task and a span per tool call; the stop as a span event; four counters, delta by default and cumulative only when the standard temporality preference asks (2.4.1, amended after `/speckit-analyze` C1); GenAI conventions plus `loopbrake.*`; explicitly enabled; endpoint and headers from `OTEL_EXPORTER_OTLP_*`; protobuf-only backends through a Collector. Projects are sent as fingerprints unless content is opted in (FR-012). |
| Open core | PASS | PASS | Everything is in the public package. A team or hosted dashboard is out of scope (a private service, if ever built). |
| Releases | PASS | PASS | v0.3.0 through the tag workflow; the wheel contents check still holds (static files are inside `loopbrake/`). |
| Public claims | PASS | PASS | The README's new sections show configuration, not results. The dashboard shows the user's own numbers. |
| Plain language (Phase 3 FR-013, the builder's rule) | PASS | PASS | Every word on screen is plain (contracts/ui.md). |
| Simplicity | PASS | PASS | Two new modules (`dashboard.py`, `otlp.py`), one static folder, and one development script. |

## Project Structure

### Documentation (this feature)

```text
specs/005-observability/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/
│   ├── dashboard-http.md   # access rules, read and change endpoints
│   ├── ui.md               # screens, words, look and its checks
│   ├── otlp.md             # the exact span, event and metric mapping; responses and retries
│   └── cli.md              # dashboard, export, replay --record
├── collector/              # a local Collector + Jaeger config for quickstart scenario 6 (added in tasks)
├── checklists/requirements.md
└── tasks.md                # next: /speckit-tasks
```

### Source code (changes)

```text
src/loopbrake/__init__.py      __version__ = "0.3.0"
src/loopbrake/records.py       millisecond ts
src/loopbrake/brake.py         step(duration_ms=); start(traceparent=) recorded on run_start; end() starts the background export when it's on
src/loopbrake/claude_code.py   passes duration_ms (PostToolUse) and TRACEPARENT (env) through; starts the background export when it closes a task
src/loopbrake/calibration.py   writes lengths into new calibration records
src/loopbrake/otlp.py          new: settings from the environment, export state and lock, payload builder, sender with one Retry-After, background start
src/loopbrake/dashboard.py     new: server and access rules, incremental index, JSON API, actions
src/loopbrake/static/          new: index.html, app.css, app.js, icons.svg, fonts/*.woff2, OFL.txt, LICENSE-lucide.txt
src/loopbrake/cli.py           dashboard, export, replay --record
scripts/vendor_assets.py       new, development only: fetch, check and subset fonts; build the icon sprite
tests/test_dashboard.py        new: access rules, the index, API shapes, actions
tests/test_static.py           new: no emoji, no external URLs, icons exist, AA contrast, size budget
tests/test_otlp.py             new: mapping, content rules, temporality, retries, offsets, background start, hook timing with export on
tests/mimic_backends.py        new: local stand-ins for the Collector, Datadog, Grafana, Honeycomb, Langfuse, Jaeger and Phoenix that enforce their published intake rules (R9)
tests/test_export_backends.py  new: the README's setting for each tool passes its stand-in; wrong settings are rejected and shown
tests/test_records.py, test_brake.py, test_calibrate.py, test_claude_code.py   more: the new optional fields
README.md                      "Dashboard" and "Send to your observability tools" sections
specs/roadmap.md               Phase 4 status
```

**Structure decision**:
- **Placement**: the new code joins the existing package, as two modules. The static files live
  inside the package so the wheel carries them, and the contents check still passes.
- **Excluded**: the Collector config is a test aid, kept under `specs/`, not shipped.

## Complexity Tracking

| Choice | Why it's needed | Simpler option rejected because |
|---|---|---|
| A detached background process for export at task end | Export must never slow or block the agent (FR-013, SC-006), and the hook process ends right away | Sending inside the hook puts the network on the agent's path; a long-running exporter only works while someone keeps it running |
| The whole history read when the dashboard starts | Simple, and measured fast enough (0.37 s per 220,000 lines) | A summary cache on disk is a second format to keep in sync; add it only if starts get slow (`# ponytail:` note in code) |
| Vendored fonts and icons (under 400 KB) inside the package | The constitution forbids loading anything from the network, and the look needs the brand fonts | System fonts would lose the reel brand |
