# Contract: CLI additions (v0.3.0)

All earlier commands keep their behavior. New:

## `loopbrake dashboard [--port N] [--no-open] [--days D]`

It starts the dashboard (research R1) and prints:

```text
LoopBrake dashboard: http://127.0.0.1:53817/?k=...
Only this computer can open it. Press Ctrl+C to stop.
```

**Options**:
- `--port N`: a fixed port. The default is 0, so the OS picks one.
- `--no-open`: don't open a browser.
- `--days D`: read the last D days of session files. The default is all.

**Exit codes**: 0 on Ctrl+C, and 2 if the port is taken, with a one-line message.

## `loopbrake dashboard --background | --stop` and `/loopbrake:dashboard [stop]`

- **`--background`**: starts the dashboard detached and returns at once, printing its address, that
  it keeps running, and how to stop it. If one is already serving this LoopBrake folder, it reopens
  that one instead of starting a second. Exit code 1 if it didn't start.
- **`--stop`**: stops it: "Stopped the LoopBrake dashboard." or "No LoopBrake dashboard is running.";
  exit code 0 either way.
- **The running dashboard** records its process and address in `~/.loopbrake/dashboard.json`
  (owner-only, since the address holds the access key) and removes it when it stops.
- **The plugin**: `/loopbrake:dashboard` runs `loopbrake dashboard --background`, and
  `/loopbrake:dashboard stop` runs `loopbrake dashboard --stop`. Claude repeats the output as printed.

## `loopbrake export --pending | --test`

- **`--pending`**: sends every finished task not yet sent (research R7). It prints one line, such as
  `sent 3 tasks (41 spans) to otel-collector:4318` or `export is off; set LOOPBRAKE_EXPORT=otlp to
  turn it on`. The exit code is 0 when sent or off, and 1 when the backend refused or couldn't be
  reached; the reason goes to stderr, without headers.
- **`--test`**: sends one test span and prints the result.

The background process started at task end is `loopbrake export --pending --quiet`.

## `loopbrake replay FILE (--project P | --stop-line N) [--record]`

- **`--record`** (new): writes run records for every replayed run into `LOOPBRAKE_HOME`, with
  project `replay-<file stem>`. The dashboard can then show records replayed from the published
  evaluation (spec SC-007).
- **Without it**: replay still writes nothing (Phase 2 contract).
