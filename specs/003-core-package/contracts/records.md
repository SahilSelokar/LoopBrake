# Contract: Local records

All files live under `$LOOPBRAKE_HOME` (default `~/.loopbrake`). Nothing is sent anywhere
(constitution Principle VI).

## Calibration record: `calibration/<project>.json`

```json
{"v": 1, "project": "my-agent", "method": "steps", "alpha": 0.05,
 "n": 40, "k": 39, "stop_line": 60, "watch_only": false,
 "source": {"kind": "runs-file", "sha256": "…", "runs_seen": 52, "excluded": 1},
 "created": "2026-10-01", "version": "0.1.0"}
```

- `kind` is `runs-file` or `claude-code`.
- `n` is the number of successful runs used, one per task.
- When `k > n`: `stop_line` is `null` and `watch_only` is `true`.
- The record holds **no text from the source**, only counts and a fingerprint (FR-007).

## Run records: `runs/<session>.jsonl`

These are append-only, one JSON event per line, with `"v": 1`. This replaces the event list in
`specs/roadmap.md` (`kill` is renamed `stop`).

| Event | Fields besides `v`, `ts` (UTC ISO time), `event`, `session`, `run` |
|---|---|
| `run_start` | `project`, `calibration`: `{method, alpha, n, k, stop_line, watch_only}` |
| `step` | `step`, `tool` (or null), `action_excerpt` (at most 200 characters), `tokens` (or null), `error` (or null) |
| `stop` | `step`, `stop_line`, `reason` |
| `run_end` | `status`: `finished`, `stopped` or `interrupted`; `steps`; `tokens` (sum of the known values, or null) |
| `feedback` | `verdict`: `mistaken_stop` or `exclude` |

**Writing**:
- **One line per event**, from one `write()` call on a file opened in append mode. Lines stay short,
  so parallel runs in one session don't interleave.
- **If the write fails**: recording turns off for that brake, with one warning, and the decision
  logic carries on (FR-005).

## Exclude list: `exclude.txt`

One run or turn id per line. Calibration skips the listed ids. `loopbrake feedback RUN --exclude`
appends to it. Phase 1's evaluation reads the same file.

## Status (computed, not stored)

| Field | Rule |
|---|---|
| runs watched | `run_start` events whose `calibration.watch_only` is false |
| runs stopped | `stop` events |
| mistaken stops | `feedback` events with `mistaken_stop` |
| allowance | α × runs watched, using each run's own α |
