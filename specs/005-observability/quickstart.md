# Quickstart: validate the dashboard and export

Runnable checks showing the feature works end to end. The formats are in
[contracts/](contracts/) and [data-model.md](data-model.md).

## Prerequisites

- `uv`, Chrome, and Node 18+ (for the accessibility audit, through `npx lighthouse`).
- A checkout of this repo on the feature branch.
- A throwaway home, so your real records stay clean:
  `export LOOPBRAKE_HOME=$(mktemp -d)/lb`.
- For scenario 6: Docker (a local OpenTelemetry Collector and Jaeger). For scenario 7: trial
  accounts for Datadog, Grafana Cloud and Honeycomb.

## 1. Automated tests

```sh
uv run python -m pytest
```

**Expect**: all pass, including:
- the server's access rules (the key exchange, a wrong `Host`, a foreign `Origin`, no cookie);
- the incremental index on growing files;
- the API shapes;
- the OTLP payload mapping and content rules;
- the static-file checks (no emoji, no external URLs, icons exist, colors pass AA).

## 2. Replayed evaluation records (SC-007)

```sh
uv run loopbrake replay ~/.loopbrake/data/runs/swe-gpt5mini.jsonl --stop-line 27 --record
uv run loopbrake dashboard
```

**Expect**: the overview lists the replayed project, with stopped and finished tasks. Each screen
opens without errors, the task chart shows the stop at the limit, and the browser console is clean.

## 3. Live task (SC-001, US1)

With the dashboard open, run a Claude Code task in a project whose limit is low (as in Phase 3's
quickstart, scenario 3).

**Expect**:
- the task appears under "Running now", and its count rises within 2 seconds of each tool call;
- when it's stopped, it moves to "Recent stops";
- opening it shows every call, the limit line, the stop marker and the plain reason.

## 4. Actions (US2)

On that stopped task: "Mark as mistake" → confirm.

**Expect**: the project's mistaken count goes up by 1, and a second click says "That one is already
marked." On a finished task, "Leave out of future limits" works the same way. On a `cc-` project,
"Set the limit again" shows the same text that `/loopbrake:calibrate` prints.

## 5. Security (FR-001)

| Try | Expect |
|---|---|
| `curl http://127.0.0.1:<port>/api/overview` (no cookie) | 401 |
| `curl -H 'Host: evil.example' http://127.0.0.1:<port>/` | 403 |
| A `POST` with a foreign `Origin` | 403 |
| The address bar after opening the printed link | no `?k=` |
| `lsof -iTCP -sTCP:LISTEN \| grep <port>` | `127.0.0.1` only |

## 6. Export to a local Collector (US3, SC-005, SC-006)

1. Run an OpenTelemetry Collector with an OTLP HTTP receiver and a debug exporter (a config file
   is added under `specs/005-observability/collector/`, with Jaeger as a second backend).
2. `export LOOPBRAKE_EXPORT=otlp OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 OTEL_EXPORTER_OTLP_PROTOCOL=http/json`.
3. Run a task that gets stopped, then wait a few seconds.

**Expect**:
- one trace: a task span, with one span per tool call and a `loopbrake.stop` event; the task span
  is marked as an error;
- the counters arrive;
- no action text, and no readable project name or folder name, in the received payloads (SC-005,
  FR-012); only `loopbrake.project_id`;
- with `LOOPBRAKE_EXPORT_CONTENT=1`, the action text and `loopbrake.project` appear.

Then stop the Collector and run 50 tool calls.

**Expect**: the per-call time stays under the 200 ms p95 budget, and the dashboard's Export screen
shows the last send as failed (SC-006).

## 7. Company tools, without accounts (SC-004)

1. `uv run python -m pytest tests/test_export_backends.py -v`.

   **Expect**:
   - every tool's README settings are accepted by its stand-in (research R9);
   - each wrong setting is rejected and recorded as a failed send: cumulative to Datadog, delta to
     Grafana, metrics to Langfuse or Jaeger, JSON to Phoenix.
2. **Real software**: start the Collector and Jaeger from `specs/005-observability/collector/`
   (`docker compose up`, or the release binaries if Docker isn't running). Run a task that gets
   stopped with `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318`.

   **Expect**:
   - the Collector's debug output shows the task span, the tool-call spans and the counters;
   - Jaeger's UI (`http://localhost:16686`) shows the trace, with the tool calls nested under the
     task and the stop marked as an error.

## 8. Accessibility and look (SC-002, SC-009, US4)

```sh
npx lighthouse "http://127.0.0.1:<port>/#/" --only-categories=accessibility --extra-headers='{"Cookie":"lb=<key>"}'
```

Run it for each screen, once with glass on and once with `?glass=off`.

**Expect**: a score of at least 95 everywhere. Then check by hand:
- macOS "Reduce motion", "Reduce transparency" and "Increase contrast" change the look as
  contracts/ui.md says;
- at a 390×844 window, no screen scrolls sideways.

## 9. Nothing leaves the computer (SC-003)

With export off, open the dashboard and click through every screen while watching the browser's
network panel and `lsof -i -P | grep python`.

**Expect**: only `127.0.0.1` connections.

## 10. Plain words and first-time users (SC-008, after release; FR-007)

Ask three people new to LoopBrake to open the dashboard after a stop and say why the task stopped.

**Expect**: each answers within 30 seconds. Note the times.
