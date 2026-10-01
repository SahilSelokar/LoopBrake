# Data Model: Core Package (LoopBrake v1)

**Feature**: [spec.md](spec.md) | **Contracts**: [python-api.md](contracts/python-api.md), [records.md](contracts/records.md)

The scoring records from Phase 1 (`Step`, `Run`) are reused unchanged. This feature adds the
records below.

## Brake (one per run)

| Field | Rules |
|---|---|
| `project`, `session`, `run` | `project` matches `[A-Za-z0-9._-]{1,64}`. The ids are random by default. |
| `calibration` | The calibration record in force, or `None`. Fixed when the run starts (spec edge case: recalibration affects only new runs). |
| `stop_line` | `calibration.stop_line`, or `None` when watch-only |
| `steps` | The `Step`s reported so far, in order |
| `stopped` | False until the first stop. It never goes back to False. |
| `recording` | True until a record write fails; then False for the rest of the run |

**States**:

```text
watching ──step()──▶ watching ──step() past the stop line──▶ stopped ──step()──▶ stopped
    │                                                            │
    └──────────────── end() / leaving `with` ───────────────────┴──▶ ended
watch-only brakes never enter "stopped"
```

## Decision

| Field | Rules |
|---|---|
| `stop` | True only when the `steps` score is above `stop_line`, or when already stopped |
| `step` | Equals `len(steps)` |
| `reason` | Empty unless `stop`. Otherwise it gives the step, the stop line, n, α, and the Phase 1 signals' explanation at that step (which never decides). |
| `watch_only` | Mirrors the brake |

## Calibration record

The format is in [records.md](contracts/records.md). Rules:
- `k = rank(n, alpha)` and `stop_line = threshold(lengths, alpha)`, using `loopbrake.conformal`
  unchanged.
- `stop_line` is an int, being the k-th smallest run length. It is `None` when `k > n`.
- `n` counts successful runs, at most one per task, after removing excluded ids.

## Run record events

The format is in [records.md](contracts/records.md). One `run_start`, any number of `step` events,
at most one `stop`, and one `run_end` (unless the process dies). `feedback` events may come later.

## Status

Computed from all run records ([records.md](contracts/records.md)). The allowance is α × runs
watched, using each run's own α.
