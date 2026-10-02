# Research: Observability (dashboard and company-tool export)

**Feature**: [spec.md](spec.md) | **Date**: 2026-10-02

**Sources**:
- local measurements on the builder's M3 Pro, with Claude Code 2.1.285;
- a hook probe (a throwaway plugin that saved the exact input every hook received);
- the OpenTelemetry specification and vendor docs (R7, R8);
- the constitution's visual identity and the roadmap's Phase 4 research (2026-10-01).

Each point gives the decision, why, and what else was considered.

## R1. The dashboard server

**Decision**: `loopbrake dashboard` starts a standard-library threading HTTP server.
- **Where it listens**: `127.0.0.1` only, on a port the OS picks (or `--port N`).
- **What it serves**: the page's files from inside the package, plus a small JSON API over the run
  records.
- **On start**: it prints the address, and opens the browser unless `--no-open` is given.

**Security** (constitution, Dashboard security; spec FR-001):
- **Access key**: a new `secrets.token_urlsafe(32)` each launch. The printed address carries it
  once (`/?k=KEY`). The server answers that first visit by setting the key as a cookie (`HttpOnly`,
  `SameSite=Strict`, path `/`) and redirecting to `/`. The key then isn't left in the address bar,
  so a screen recording for a reel doesn't show it (spec edge case).
- **Every request**: the `Host` header must be `127.0.0.1:<port>` or `localhost:<port>`, which
  blocks DNS rebinding, and the cookie must match. Otherwise 403 or 401.
- **Changes**: only `POST`, and `Origin` must equal the dashboard's own address.
- **Response headers**:
  - `Content-Security-Policy: default-src 'self'; img-src 'self' data:; frame-ancestors 'none'`;
  - `X-Content-Type-Options: nosniff`;
  - `Referrer-Policy: no-referrer`;
  - `Cache-Control: no-store` on the API.

  The policy means the browser itself refuses to load anything from elsewhere (SC-003).

**Alternatives considered**:
- **The key kept in the URL**: it shows in recordings and history.
- **No key at all**: other local programs and malicious pages could act on the records.

## R2. Live updates

**Decision**: the page polls `GET /api/changes?since=<n>` once a second.
- **The server's change counter**: the total of bytes read from the run records. If nothing changed,
  the reply is tiny.
- **When something changed**: the page fetches only the parts it shows.

This meets "within 2 seconds" (SC-001) with one plain mechanism.

**Alternatives considered**: server-sent events. They're slightly faster, but each open tab holds a
connection, and they're harder to test. A one-second poll of a local server costs nothing that
matters.

## R3. Reading the records at scale

**Measured**: a synthetic records file with 220,000 lines (10,000 tasks of 20 tool calls, 79 MB):
- parsing every line takes 0.37 s (1.7 µs per line);
- reading only the task summaries, skipping tool-call lines by a text check, takes 0.07 s.

**Decision**: an in-memory index, updated incrementally.
- **What's tracked**: for each `runs/*.jsonl`, the server keeps the byte offset it has read up to.
  Each poll only checks file sizes and reads the new bytes. Records are append-only, so earlier
  bytes never change.
- **What's kept**: a summary per task (project, session, times, status, tool-call count, limit,
  stop step, reason, marks).
- **Tool-call lists**: read from the session file only when a task is opened.
- **What's skipped**: damaged lines, counted and shown (spec edge case).

A year of heavy use (about 2 million lines) loads in about 1–3 s at start, then costs only new
lines.
`# ponytail: whole history read at start; keep a summary cache on disk if starts get slow.`

## R4. Data the dashboard needs that the records don't hold yet

1. **Better timing.**
   - **The finding**: record times have one-second resolution (`isoformat(timespec="seconds")`),
     which is too coarse for tool-call timing and for export.
   - **Decision**: write times with milliseconds. It's additive, readers compare the strings, and
     old records still parse.
2. **How long each tool call took.**
   - **The hook probe shows**: Claude Code's `PostToolUse` input includes `duration_ms`, the
     tool's own run time (68 and 64 in the probe). There's no `timestamp` field.
   - **Decision**: record `duration_ms` on `step` events when the agent provides it, through a new
     optional `Brake.step(..., duration_ms=)`.
   - **Effect on export**: a tool-call span ends at the step's time and starts `duration_ms`
     earlier. Without it, the span runs from the previous event.
3. **Claude Code's trace.**
   - **The hook probe shows**: with Claude Code's tracing on (`CLAUDE_CODE_ENABLE_TELEMETRY=1`,
     `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`, `OTEL_TRACES_EXPORTER=otlp`), every hook process gets
     a `TRACEPARENT` environment variable. It had the same value for prompt, pre-tool and post-tool
     hooks in one task. With tracing off, it's absent. Neither probe had it in the stdin JSON.
   - **Decision**: the prompt hook records `traceparent` on `run_start` (metadata only), and export
     uses it as the task span's parent (spec FR-014).
4. **Past task lengths, for the project page's chart.**
   - **Decision**: calibration records gain `lengths`, the sorted step counts it used, with mistaken
     stops as `null`. That's numbers only, no text (Phase 2 FR-007 still holds).
   - **Older records**: they lack it, and their page shows the numbers without the chart.

## R5. Screens and charts

**Decision**: one page with four views, switched by the address hash (`#/`, `#/task/…`,
`#/project/…`, `#/export`):
- **Overview**: running now, recent stops, totals, and two per-day charts: stops, and tokens spent
  when known.
- **Task**: tool calls against the limit.
- **Project**: past task lengths with the limit line.
- **Export**: status and the test action.

**Charts**: inline SVG drawn by about 200 lines of plain JS. There's no chart library and no build
step (constitution: "no framework and no build step").

**The task view's chart is the constitution's "score line and τ line"**, in v1 terms:
- the line is the tool-call count rising one per call;
- the horizontal line is the limit;
- the stop marker sits at the call where it stopped.

**Per-call explanation signals** (the constitution's "signal values"):
- the records keep the action text (up to 200 characters) and whether the call failed, so each row
  can show "repeats an earlier call" (the fuzzy-repeat signal on action text) and "failed";
- the "nothing new" signal needs tool outputs, which the plugin never stores (Phase 3 FR-010), so
  it isn't shown for Claude Code tasks.

**Also on the overview** (constitution: "kills and tokens spent over time, and the false-kill
budget"):
- stops per day;
- tokens spent per day: Claude Code's hooks report no tokens, so for `cc-` projects the dashboard
  reads them from Claude Code's own history files with the existing reader (`claude_code_turns`,
  the single loader under Principle V). Each live task takes the token total of the transcript turn
  that holds its first tool call id. Only numbers are used. It's read lazily for the last 30 days,
  and cached per file by size and modification time (`/speckit-analyze` E1). Other agents report
  their own tokens;
- mistaken stops against how many would be normal.

The spec gains FR-017 for this.

## R6. Look and feel: the liquid glass system

The constitution and the roadmap's 2026-10-01 research set the rules (glass on chrome only, layers,
progressive enhancement, Lucide, OFL fonts, red as a fill only, the "Glass off" switch). This plan
adds how it's built:
- **Styling**: one CSS file with custom properties for the six brand colors and the glass
  parameters.
  - **Glass**: `@supports (backdrop-filter: blur(1px))` adds blur on top of an opaque base.
  - **Refraction**: an SVG `feDisplacementMap` filter, Chromium only (detected with `CSS.supports`
    plus the user agent).
  - **The sheen**: only under `prefers-reduced-motion: no-preference`.
- **"Glass off"**: sets `data-glass="off"` on `<html>`, saved in `localStorage`. That's a
  per-viewer preference; it falls back to "on" if storage is blocked.
- **Overrides**:
  - `prefers-reduced-transparency: reduce` and `prefers-contrast: more` force glass off;
  - `forced-colors: active` uses system colors.
- **Fonts**: fetched once by a development script (`scripts/vendor_assets.py`) from the official
  sources, at pinned versions with sha256 checks.
  - Inter Tight (variable), JetBrains Mono (variable), and Instrument Serif italic.
  - Subset to Latin and saved as woff2 with `fonttools`, a development-only dependency through
    `uv run --with`.
  - Committed with `OFL.txt` under `src/loopbrake/static/fonts/`.
- **Icons**: the same script builds an SVG sprite of the roughly 20 Lucide icons the roadmap lists,
  at a pinned Lucide version, with its ISC license. The page uses them through `<use href>`.
- **Emoji**: none. A test scans every static file and the API's strings.

**Measured target**: the static files total under 400 KB, so the wheel stays small.

## R7. Export trigger

**The constraint**: export must never slow or block an agent (spec FR-013, SC-006). The hook path
has a 200 ms budget and must not touch the network.

**Decision**: when a task ends, and only if `LOOPBRAKE_EXPORT=otlp`, LoopBrake starts a detached
background process, `loopbrake export --pending`, and doesn't wait for it:
- `subprocess.Popen` with `start_new_session=True` and all stdio sent to `/dev/null`;
- this is the same pattern as the launcher's background download in Phase 3.

"Ends" means `Brake.end` in the package, and the closing paths of the Claude Code hooks.

**The background process**:
- takes an export lock;
- sends every finished task not sent yet, keeping its position in `~/.loopbrake/export/state.json`
  (per session file: the offset sent up to);
- records the last result for the dashboard.

**Export turned on mid-session**: the first run with no saved position records the current end of
each file as its starting point, and only tasks whose `run_start` lies after that point are ever
sent. A task already running when export was turned on is skipped whole; its start isn't half-sent
(spec edge case: "only tasks that start afterwards are sent").

**A stopped task is final at its stop**: Claude Code sends no `Stop` event after LoopBrake stops a
task (Phase 3 finding), so a task counts as finished at its `run_end` *or* its `stop`, whichever
comes first. The background export started right after the stop decision sends it at once. Tool
calls that land after the stop (calls Claude had running alongside) aren't sent: the trace shows the
task up to the stop. (`/speckit-analyze` U1, F1.)

**By hand**: `loopbrake export --pending` sends now, and `loopbrake export --test` sends one test
span. The dashboard's "Send now" and "Test connection" run the same code.

**Alternatives considered**:
- **Sending inside the hook**: network on the agent's path, so no.
- **A long-running exporter**: it only works while running, and people forget to start it.

## R8. The export format (OTLP over HTTP, JSON)

**Facts** (OTLP spec 1.11.0 and the exporter configuration spec; vendor docs; checked 2026-10-02):
- **Encoding rules**:
  - trace and span ids are **hex strings**, not base64;
  - 64-bit integers (`timeUnixNano`, `asInt`) are **decimal strings**;
  - enums (span kind, status code, temporality) are **integers**;
  - keys are lowerCamelCase;
  - `Content-Type: application/json`.
- **Paths**: `OTEL_EXPORTER_OTLP_ENDPOINT` is a base URL, and signals go to `v1/traces` and
  `v1/metrics` under it. Per-signal `…_TRACES_ENDPOINT` / `…_METRICS_ENDPOINT` are used as given.
  The default is `http://localhost:4318`.
- **Headers**: `key1=value1,key2=value2` (W3C baggage style). Values are percent-decoded.
- **Protocol**: `OTEL_EXPORTER_OTLP_PROTOCOL` is one of `grpc`, `http/protobuf` (the default) or
  `http/json`. LoopBrake speaks `http/json` only, and warns otherwise.
- **Errors**: 429, 502, 503 and 504 may be retried, honoring `Retry-After`. Never retry a 400 or a
  `partial_success` reply.
- **Temporality**: `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE` is `cumulative` (the spec's
  default), `delta` or `lowmemory`.
- **GenAI conventions**: they moved to their own repository (semantic-conventions-genai, building
  on core v1.44.0), and every `gen_ai.*` attribute is still **Development**.
  - **`invoke_agent {gen_ai.agent.name}`**: kind INTERNAL for an in-process agent;
    `gen_ai.operation.name` is required; `gen_ai.provider.name` is required only on CLIENT spans;
    `gen_ai.conversation.id` is conditionally required, and must not be a made-up fallback.
  - **`execute_tool {gen_ai.tool.name}`**: kind INTERNAL; `gen_ai.tool.name` is required;
    `gen_ai.tool.call.id` is recommended; arguments and results are opt-in ("may contain sensitive
    information").
  - **`gen_ai.system`** is deprecated.

| Backend | JSON over HTTP | Metrics temporality | Path for LoopBrake |
|---|---|---|---|
| OpenTelemetry Collector | yes | either | direct |
| Datadog, direct intake | yes (traces and metrics) | **delta only**: cumulative is rejected | direct, with `dd-api-key` |
| Datadog Agent receiver | not documented | delta advised | through the Collector, or direct intake |
| Grafana Cloud | yes, "ideally only for low-traffic testing" | **cumulative** (Prometheus) | direct for low volume, else through the Collector |
| Honeycomb | yes | not documented | direct, with `x-honeycomb-team` |
| Langfuse | yes, traces only | none | direct (traces) |
| Jaeger v2 | yes, traces only | none | direct (traces) |
| Arize Phoenix | **no**: protobuf only (its source rejects other types with 415) | none | through the Collector |

**Decisions**:
1. **Spans**:
   - one trace per task, and one span `invoke_agent {agent}` (INTERNAL) with:
     - `gen_ai.operation.name=invoke_agent`;
     - `gen_ai.agent.name`: `claude-code`, or the project name for Python agents;
     - `gen_ai.conversation.id`: the session id, which is the real conversation id;
     - `loopbrake.project_id`, `loopbrake.limit`, `loopbrake.alpha`, `loopbrake.calibration.n`,
       `loopbrake.status` and `loopbrake.tool_calls`;
     - `loopbrake.project_id` is the first 12 hex characters of `sha256(project name)`. The readable
       `loopbrake.project` is sent only with content opt-in, because Claude Code project names hold
       parts of the local folder path and the username (spec FR-012; `/speckit-analyze` P1);
   - one child span per tool call, `execute_tool {tool}` (INTERNAL), with `gen_ai.tool.name`,
     `gen_ai.tool.call.id` (when known), `loopbrake.step` and `loopbrake.failed`;
   - **a stop**: an event `loopbrake.stop` on the task span, carrying `loopbrake.step`,
     `loopbrake.limit` and `loopbrake.reason_code` (`past_limit`, plus the symptom code `repeating`,
     `same_error` or `nothing_new` when present). The task span's status is ERROR, with
     `error.type=loopbrake.stopped`.
   - **Not sent**: no `gen_ai.provider.name` (LoopBrake doesn't know it; not required on INTERNAL
     spans), no `gen_ai.system`, and no usage tokens unless the agent reported them.
2. **Content**:
   - `loopbrake.action` (the stored action text) on tool-call spans, and the full reason text on
     the stop event, are added **only** with `LOOPBRAKE_EXPORT_CONTENT=1`.
   - LoopBrake doesn't use `gen_ai.tool.call.arguments`, because what it stores is an excerpt, not
     the exact arguments.
3. **Ids and parents**:
   - the trace id is the first 32 hex characters of `sha256(session + "/" + run)`, so sending the
     same task twice gives the same trace (idempotent);
   - span ids are derived the same way per step;
   - when `run_start` has a `traceparent`, its trace id and span id become the task span's trace and
     parent, which places it inside Claude Code's trace (spec FR-014).
4. **Metrics**:
   - four Sum counters, monotonic: `loopbrake.tasks`, `loopbrake.stops`,
     `loopbrake.mistaken_stops` and `loopbrake.tokens.spent`, each with a `loopbrake.project_id`
     attribute (plus `loopbrake.project` with content opt-in);
   - **temporality**: **delta by default** (constitution 2.4.1; it's also what Datadog's direct
     intake requires). **Cumulative** only when the standard
     `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=cumulative` is set, which Grafana and
     Prometheus need. Cumulative totals count from `export/state.json`'s `started` time.
5. **Retries**: one retry after `Retry-After` (capped at 10 s) for 429, 502, 503 and 504, then give
   up for this batch, keep the offsets unsent, and record the failure. A 400 or a partial success is
   never retried, and the backend's message is recorded (roadmap: "retries beyond honouring one
   `Retry-After`" are out of scope).
6. **Protocol check**: if `OTEL_EXPORTER_OTLP_PROTOCOL` is set to anything but `http/json`, export
   still sends JSON and records a one-line warning: "LoopBrake sends OTLP JSON; for protobuf-only
   backends, put an OpenTelemetry Collector in between."

## R9. Proving export works without vendor accounts

**The builder's decision (2026-10-02)**: no trial accounts. "Creating an account for each is
hectic."

**Decision**: two levels of proof, both on the builder's computer:
1. **Real software, no account**: an OpenTelemetry Collector (`otelcol-contrib`, with an OTLP HTTP
   receiver and a debug exporter) and Jaeger v2.
   - They run through Docker when Docker Desktop is running, or else as the official release
     binaries, downloaded once to the scratch folder and never committed.
   - They show the payload is valid OTLP JSON that real OpenTelemetry software parses, and that
     traces nest correctly in Jaeger's UI.
2. **Stand-ins for the vendors** (`tests/mimic_backends.py`): one small standard-library HTTP
   receiver per tool, running inside the tests. Each one checks the generic OTLP JSON rules (R8:
   hex ids, string 64-bit integers, integer enums, lowerCamelCase keys, `Content-Type`), plus that
   tool's published intake rules:

| Stand-in | Accepts | Rejects (as the vendor documents) |
|---|---|---|
| Datadog (direct intake) | `/v1/traces` and `/v1/metrics` with a `dd-api-key` header; JSON; **delta** counters | a missing key (403); **cumulative** counters (an error, as Datadog's docs state) |
| Grafana Cloud | `/v1/traces` and `/v1/metrics` with `Authorization: Basic …`; JSON; **cumulative** counters | missing auth (401); delta counters |
| Honeycomb | `/v1/traces` and `/v1/metrics` with `x-honeycomb-team` | a missing team header (401) |
| Langfuse | `/api/public/otel/v1/traces` with Basic auth; traces only | metrics (404); missing auth (401) |
| Jaeger (also run for real) | `/v1/traces`; traces only | metrics (404) |
| Phoenix | protobuf only | `application/json` with **415**, as Phoenix's source does |

- **What the tests check**:
  - **Right settings**: export with each tool's settings, exactly as the README will show them, is
    accepted.
  - **Wrong settings**: cumulative to Datadog, delta to Grafana, metrics to Langfuse, or JSON to
    Phoenix are rejected, recorded as a failed send, shown on the dashboard's Export screen, and
    never retried. That's the same handling as a real 4xx.
- **The honest limit**: the stand-ins encode the vendors' *documented* rules as of 2026-10-02. They
  can't catch undocumented behavior or later changes. The README's export section says each tool's
  settings were checked against its published rules and a real Collector, and invites a report if a
  live service disagrees.

**Alternatives considered**: trial accounts with Datadog, Grafana Cloud and Honeycomb. That's real
end-to-end proof, but it needs account setup and keys the builder doesn't want to manage now. It
can be added later without changing code.

**Checked early, before any feature code (2026-10-02)**: with Docker running,
`specs/005-observability/collector/` started a real Collector (`otel/opentelemetry-collector-contrib`
0.161.0) and Jaeger 2.21.0. A hand-built stopped task in exactly the format of
contracts/otlp.md was sent to `http://localhost:4318`.

| Check | Result |
|---|---|
| `POST /v1/traces` (JSON) | 200, `{"partialSuccess":{}}` |
| `POST /v1/metrics` (JSON, four delta Sums) | 200, `{"partialSuccess":{}}`; the Collector logged `AggregationTemporality: Delta` |
| Jaeger's API for the trace | `invoke_agent claude-code` with `otel.status_code=ERROR`, `error=true` and the `loopbrake.stop` event; both `execute_tool Bash` spans nested under it |

**One correction found**: a full success still carries an empty `partialSuccess` object. The
exporter treats `{}`, or a zero rejected count with no message, as success (contracts/otlp.md,
Responses).
