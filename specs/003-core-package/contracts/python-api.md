# Contract: Python API

This is the public surface of `loopbrake` v0.1. It uses the standard library only (constitution
Principle III). Everything not listed here is internal.

## Five-line use (spec FR-013, SC-002)

```python
import loopbrake

with loopbrake.start(project="my-agent") as brake:       # loads ~/.loopbrake/calibration/my-agent.json
    for action, result in my_agent_steps():               # your loop
        decision = brake.step(action, result)
        if decision.stop:
            print(decision.reason); break
```

## `loopbrake.start(project="default", *, session=None, run=None, home=None) -> Brake`

- Starts one run.
- `project`: picks the calibration record `<home>/calibration/<project>.json`. It must match
  `[A-Za-z0-9._-]{1,64}`.
- `session`: groups runs into one record file. The default is a new random id.
- `run`: the default is a new random id.
- `home`: the default is `$LOOPBRAKE_HOME`, or else `~/.loopbrake`.
- It never raises because calibration is missing or damaged. Instead the brake is watch-only and
  warns once (spec FR-004, FR-005).

## `Brake`

| Member | Meaning |
|---|---|
| `step(action, result="", *, tool=None, tokens=None, error=None) -> Decision` | Report one step. `action` and `result` are text. Once it returns stop, every later call returns stop too (FR-002). |
| `end(status="finished")` | Closes the run. `status` is one of `finished`, `stopped`, `interrupted`. Called for you by `with`: `stopped` if the brake stopped, `interrupted` if an exception left the block, `finished` otherwise. |
| `stop_line` | The stop line in force (int), or `None` when watch-only |
| `watch_only` | True when the brake can never stop |
| `run`, `session`, `project` | Ids |

## `Decision` (NamedTuple)

| Field | Meaning |
|---|---|
| `stop` | bool |
| `step` | Step number, counting from 1 |
| `reason` | Empty when continuing. When stopping, for example: `stopped at step 61: past the stop line of 60 steps set from your 40 past successful runs (α 5%); last 5 steps: repeating in 5 of last 5 steps (same command as step 58)` |
| `watch_only` | bool |

## The stop rule (FR-001)

At step t the brake computes `method("steps")(steps)` from `loopbrake.signals`, the scorer the
experiments certified. It stops when the latest score is greater than the stop line, which is the
same comparison as the evaluation's `bisect_right(peak, tau)`. With `steps`, that means it stops at
step `stop_line + 1`.

The explanation comes from `method("max", lam=0.9)(steps)` at that step. That score never decides
anything (constitution 2.2.0).

## `loopbrake.calibrate(source, *, project="default", alpha=0.05, home=None) -> dict`

- `source` is a runs file in the common format (`specs/001-offline-eval/contracts/normalized-runs.md`)
  or a Claude Code project folder (`~/.claude/projects/<slug>/`).
- It writes and returns the calibration record ([records.md](records.md)).
- It counts at most one successful run per task. For a runs file, that is the first by run id; a
  Claude Code turn is its own task.
- It skips run and turn ids listed in `<home>/exclude.txt`.

## `loopbrake.agent_sdk` (optional, needs the `agent-sdk` extra)

See [agent-sdk.md](agent-sdk.md).
