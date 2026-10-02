# Data Model: Observability

**Feature**: [spec.md](spec.md) | **Research**: [research.md](research.md)

The dashboard and the exporter **read** the records LoopBrake already writes (Phase 2 and 3
contracts). This feature adds a few optional fields, one new file, and in-memory summaries.
Everything lives under `$LOOPBRAKE_HOME` (default `~/.loopbrake`).

## Changes to existing records (all additive; `"v"` stays 1)

| Record | Field | Meaning | Source |
|---|---|---|---|
| every run event | `ts` | now with milliseconds, e.g. `2026-10-02T04:38:19.123+00:00` (was seconds) | R4.1 |
| `step` | `duration_ms` (optional) | how long the tool itself ran, when the agent reports it (Claude Code's `PostToolUse` does) | R4.2 |
| `run_start` | `traceparent` (optional) | the W3C trace context the agent passed (Claude Code sets `TRACEPARENT` when its tracing is on) | R4.3 |
| `run_start` | `export` (optional) | `true` when the task started with `LOOPBRAKE_EXPORT=otlp`. Only these tasks are ever sent, so tasks run with export off stay local even if it's turned on later. | R7 |
| calibration record | `lengths` (optional) | the sorted step counts the limit came from; `null` for a mistaken stop counted as unbounded | R4.4 |

**Readers**: they treat every new field as optional. Old records keep working.

## Task summary (in memory, built by the dashboard's index)

| Field | Rule |
|---|---|
| `id` | `<session>/<run>` (both are already file-name safe) |
| `project`, `session`, `run` | from `run_start` |
| `agent` | `claude-code` when the project name starts with `cc-`; otherwise `python` |
| `started`, `ended` | `run_start.ts`, and `run_end.ts` if any |
| `status` | `running` (no `run_end`), `finished`, `stopped` or `interrupted`. A run with a `stop` event and no `run_end` is shown as `stopped`. |
| `calls` | the number of `step` events |
| `limit` | `run_start.calibration.stop_line` (null when watch-only) |
| `stop_at`, `reason` | from the `stop` event (`reason` is technical; the UI shows the plain message, built as in Phase 3 R12) |
| `marks` | `mistaken` and/or `left_out`, from `feedback` events |
| `tokens` | the `run_end.tokens` sum when the agent reported it; for `cc-` tasks, the token total of the matching Claude Code transcript turn (research R5); else null |

**Task states**: `running → finished | stopped | interrupted`. A `stopped` task stays stopped. An
open run whose session hasn't been written to for 24 hours is shown as `running (no activity)`;
nothing is written to the records.

## Tool call (read when a task is opened)

`n` (step number), `tool`, `action` (the record's excerpt, at most 200 characters), `failed`
(`error`), `tokens`, `duration_ms`, `call_id`, `ts`, plus:
- **`repeats`**: true when this call's action matches one of the previous 10 by the existing
  fuzzy-repeat signal (`signals.method("fuzzy", lam=0)`, which is the raw per-call value) scoring 1.0. This is explanation only.

## Project (in memory)

| Field | Source |
|---|---|
| `name` | the calibration file name, or `run_start.project` |
| `limit`, `n`, `alpha`, `created`, `watch_only`, `lengths` | the calibration record |
| `needed` | `calibration.runs_needed(alpha, mistakes_counted)` when watch-only |
| `history` | for `cc-` projects, the Claude Code history folder whose name gives this project name (found by scanning `~/.claude/projects`), so "Set the limit again" can run |
| `seen`, `stopped`, `mistaken`, `allowance` | `records.status(home, project)` |

## Export state (new file: `export/state.json`)

```json
{"v": 1, "started": "2026-10-02T05:00:00.000+00:00", "sent_at": "2026-10-02T05:10:00.000+00:00",
 "offsets": {"<session>.jsonl": {"at": 18234, "open": [17950]}},
 "totals": {"<project>": {"tasks": 3, "stops": 1, "mistaken_stops": 0, "tokens": 0}},
 "last": {"at": "…", "ok": true, "tasks": 3, "spans": 41, "status": 200, "message": "", "rejected": 0, "warning": null}}
```

- **`offsets`**: per session file, `at` is how far it has been read, and `open` holds the `run_start`
  offsets of tasks that were still running there, so they're picked up when they end. When export is
  first turned on, each existing file's current end becomes its starting point, and only tasks whose
  `run_start` lies after it, and is marked `export: true`, are sent (R7).
- **`sent_at`**: the last successful send; the start of the next delta window.
- **`totals`**: counts per project since `started`, for cumulative counters.
- **Finished**: a task is final at its `run_end` or its `stop`, whichever comes first (R7).
- **Writing it**: under an exclusive lock (`export/lock`), and replaced atomically.
- **Content**: no record content, only offsets and counts. `message` holds the backend's error text
  if any, with secrets never echoed; the headers are never written.

## Export settings (read from the environment, never stored)

| Setting | Meaning |
|---|---|
| `LOOPBRAKE_EXPORT=otlp` | turns export on. Anything else, or unset, means off (spec FR-010). |
| `LOOPBRAKE_EXPORT_CONTENT=1` | adds content (action text, reason text). Off by default (spec FR-012). |
| `OTEL_EXPORTER_OTLP_ENDPOINT` / `_TRACES_ENDPOINT` / `_METRICS_ENDPOINT` | where to send (standard). `_METRICS_ENDPOINT=none` skips metrics, for traces-only tools such as Langfuse and Jaeger (a LoopBrake convention). |
| `OTEL_EXPORTER_OTLP_HEADERS` / `_TRACES_HEADERS` / `_METRICS_HEADERS` | auth headers (standard), never logged or shown |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | must be `http/json`; anything else gets a warning that points to a Collector |
| `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE` | see research R8 |
| `OTEL_SERVICE_NAME` | the service name, default `loopbrake` |

## Validation rules

- **Action requests**: the dashboard's POST bodies name a task by `<session>/<run>`, and both parts
  must match `[A-Za-z0-9._-]{1,128}`, as in Phase 3. A project name must pass
  `records.valid_project`.
- **Paging**: the dashboard never sends a whole huge session at once. Tool-call lists come in pages
  of 200.
