# Contract: OpenTelemetry export (OTLP/HTTP JSON)

The facts and decisions are in [research.md](../research.md), R7 and R8. This contract fixes the
exact mapping.

## When

- **On**: only when `LOOPBRAKE_EXPORT=otlp`.
- **Trigger**: at the end of each task, through a detached `loopbrake export --pending --quiet`.
  Also by hand, or from the dashboard.
- **Each run sends**: every *finished* task (final at its `run_end` or its `stop`, whichever comes
  first) whose `run_start` lies beyond the saved offsets and is marked `export: true` (the task started
  with export on), in batches of up to 50 tasks per request.
  Tool calls recorded after a stop aren't sent (research R7).

## Traces: `POST <traces endpoint>`, `Content-Type: application/json`

```json
{"resourceSpans": [{
  "resource": {"attributes": [
    {"key": "service.name", "value": {"stringValue": "loopbrake"}},
    {"key": "service.version", "value": {"stringValue": "0.3.0"}}]},
  "scopeSpans": [{
    "scope": {"name": "loopbrake", "version": "0.3.0"},
    "spans": [
      {"traceId": "<32 hex>", "spanId": "<16 hex>", "parentSpanId": "<16 hex, only with traceparent>",
       "name": "invoke_agent claude-code", "kind": 1,
       "startTimeUnixNano": "<string>", "endTimeUnixNano": "<string>",
       "attributes": [
         {"key": "gen_ai.operation.name", "value": {"stringValue": "invoke_agent"}},
         {"key": "gen_ai.agent.name", "value": {"stringValue": "claude-code"}},
         {"key": "gen_ai.conversation.id", "value": {"stringValue": "<session id>"}},
         {"key": "loopbrake.project_id", "value": {"stringValue": "<sha256(project)[:12]>"}},
         {"key": "loopbrake.limit", "value": {"intValue": "58"}},
         {"key": "loopbrake.alpha", "value": {"doubleValue": 0.05}},
         {"key": "loopbrake.calibration.n", "value": {"intValue": "61"}},
         {"key": "loopbrake.status", "value": {"stringValue": "stopped"}},
         {"key": "loopbrake.tool_calls", "value": {"intValue": "59"}}],
       "events": [{"name": "loopbrake.stop", "timeUnixNano": "<string>", "attributes": [
         {"key": "loopbrake.step", "value": {"intValue": "59"}},
         {"key": "loopbrake.limit", "value": {"intValue": "58"}},
         {"key": "loopbrake.reason_code", "value": {"stringValue": "past_limit,repeating"}}]}],
       "status": {"code": 2, "message": "stopped by LoopBrake"}},
      {"traceId": "<same>", "spanId": "<16 hex>", "parentSpanId": "<task span id>",
       "name": "execute_tool Bash", "kind": 1,
       "startTimeUnixNano": "<end - duration_ms>", "endTimeUnixNano": "<step ts>",
       "attributes": [
         {"key": "gen_ai.operation.name", "value": {"stringValue": "execute_tool"}},
         {"key": "gen_ai.tool.name", "value": {"stringValue": "Bash"}},
         {"key": "gen_ai.tool.call.id", "value": {"stringValue": "toolu_…"}},
         {"key": "loopbrake.step", "value": {"intValue": "1"}},
         {"key": "loopbrake.failed", "value": {"boolValue": false}}]}]}]}]}
```

**Rules**:
- **Ids**:
  - trace id: `sha256(session + "/" + run)[:32]`, unless `run_start.traceparent` is valid; then its
    trace id is used, and its parent id becomes the task span's `parentSpanId`;
  - task span id: `sha256(session + "/" + run + "/task")[:16]`;
  - step span id: `sha256(session + "/" + run + "/" + step)[:16]`;
  - all lowercase hex, never all zeros.
- **Times**: from the records' `ts` (milliseconds), as decimal-string nanoseconds.
  - A step span ends at the step's `ts`, and starts `duration_ms` earlier when present, else at the
    previous event's `ts`.
  - The task span runs from `run_start.ts` to `run_end.ts`, or to the last step's `ts` if it was
    stopped and never closed.
- **Status**: a stopped task is `{"code": 2}` with `error.type=loopbrake.stopped`; the others are
  `{"code": 0}` (unset). Interrupted tasks carry `loopbrake.status=interrupted`, but no error.
- **Content**: only with `LOOPBRAKE_EXPORT_CONTENT=1`. Adds `loopbrake.project` (the readable name)
  on the task span and the metrics, `loopbrake.action` (the stored action text, up to 200
  characters) on tool-call spans, and `loopbrake.reason` (the plain stop message) on the stop
  event.
- **Never sent**: prompts, tool outputs, file paths beyond what's in the action text, the headers,
  `gen_ai.system`, or `gen_ai.provider.name`.

## Metrics: `POST <metrics endpoint>`

There are four monotonic Sum metrics, each with data points per `loopbrake.project_id` (plus
`loopbrake.project` with content opt-in):

| Name | Unit | Counts |
|---|---|---|
| `loopbrake.tasks` | `{task}` | tasks that finished in this batch |
| `loopbrake.stops` | `{stop}` | tasks stopped by LoopBrake |
| `loopbrake.mistaken_stops` | `{stop}` | stops the user marked as mistakes (counted when marked) |
| `loopbrake.tokens.spent` | `{token}` | tokens of finished tasks, when the agent reported them. Claude Code tasks report none here; the dashboard reads theirs from history. |

**Temporality**:
- **Default**: `aggregationTemporality: 1` (delta), with the window from the last successful send to
  now.
- **When `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=cumulative`**: `2` (cumulative), with
  `startTimeUnixNano` = `export/state.json` `started`, and totals since then.
- **`lowmemory`**: treated as delta for these counters (the spec maps counters to delta).

`isMonotonic: true`. Values are `asInt` (decimal strings).

## Settings per tool (the README shows these; the stand-ins enforce them, research R9)

| Tool | `OTEL_EXPORTER_OTLP_ENDPOINT` | `OTEL_EXPORTER_OTLP_HEADERS` | Temporality |
|---|---|---|---|
| OpenTelemetry Collector | `http://localhost:4318` | none | either |
| Datadog (direct) | `https://otlp.datadoghq.com` (or your site's) | `dd-api-key=<key>` | delta (the default) |
| Grafana Cloud | your stack's OTLP endpoint | `Authorization=Basic%20<base64 instance:token>` | set `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=cumulative` |
| Honeycomb | `https://api.honeycomb.io` | `x-honeycomb-team=<key>` | delta (the default) |
| Langfuse | `https://cloud.langfuse.com/api/public/otel` | `Authorization=Basic%20<base64 pk:sk>` | traces only: set `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=none` to skip metrics |
| Jaeger | `http://localhost:4318` | none | traces only (same setting) |
| Phoenix and other protobuf-only tools | send to a Collector, which forwards as protobuf | | |

**Skipping metrics**: `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=none` is a LoopBrake convention. A
traces-only tool would otherwise answer every metrics send with 404.

## Responses

| Reply | What LoopBrake does |
|---|---|
| 200, and `partialSuccess` absent or empty (`{}`), or with zero rejected and no message | moves the offsets forward and records ok. A real Collector answers a full success with `{"partialSuccess":{}}` (checked 2026-10-02). |
| 200 with `rejectedSpans` or `rejectedDataPoints` above 0, or an `errorMessage` | moves the offsets forward (never retried), and records the rejected count and message |
| 429, 502, 503, 504 | waits `Retry-After` (at most 10 s; 1 s if missing) once, then retries once. If that fails, the offsets stay put and the failure is recorded. |
| other 4xx and 5xx, or a network error | the offsets stay put, and the status and the first 200 characters of the message are recorded |

A request never takes longer than 10 s (connect and read timeout). Being in the background, it
never affects the agent.
