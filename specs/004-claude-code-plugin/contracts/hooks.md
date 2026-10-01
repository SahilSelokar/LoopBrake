# Contract: `loopbrake hook <event>`

Claude Code runs this through the plugin's launcher ([plugin.md](plugin.md)) on four events. It
reads one JSON object from stdin, and may print one JSON object to stdout.

## Events

| Command | Claude Code event | Matcher | What it does |
|---|---|---|---|
| `loopbrake hook prompt` | `UserPromptSubmit` | none | Closes the open turn, if any (`stopped` if braked, else `interrupted`), and opens a new one. An open turn with no steps that isn't braked is kept as it is, so firing twice is harmless. |
| `loopbrake hook tool` | `PostToolUse` | `*` | Adds one step (error = false). If it has no open turn, opens one first. |
| `loopbrake hook tool-failed` | `PostToolUseFailure` | `*` | Adds one step (error = true). If it has no open turn, opens one first. |
| `loopbrake hook stop` | `Stop` | none | Closes the open turn (`stopped` if braked, else `finished`) |

Each call takes an exclusive lock on `runs/<session>.jsonl`, reads the open turn from it
([data-model.md](../data-model.md)), appends its events through `Brake`, and releases the lock.

**Ignored inputs**: any input that has `agent_id` (a subagent), or a `session_id` that isn't a
valid file name, gets no output, writes nothing, and exits 0.

## Output

| Case | stdout | Exit code |
|---|---|---|
| The step passes the stop line, or the turn is already braked | `{"continue": false, "stopReason": "<reason>"}` | 0 |
| Anything else | nothing | 0 |
| Any internal error (bad input, a damaged log or calibration, a disk that can't be written) | nothing; one line `loopbrake: …` on stderr | 0 |

It never exits non-zero, and never prints anything that blocks or changes a tool call (FR-004).
Setting `LOOPBRAKE_DEBUG=1` re-raises errors, for development only.

## Reason text

`Brake`'s reason, with "turns" in place of "runs" for Claude Code:

```text
LoopBrake stopped at step 39: past the stop line of 38 steps set from your 898 past successful
turns (α 5%); repeating in 5 of last 5 steps. If this stop was wrong, run /loopbrake:mistake.
```

The hook adds "LoopBrake " at the start and the last sentence at the end. The middle is
`Brake._explain`'s reason.

## Decision

The decision is exactly `Brake.step()`, which uses `_decide(steps, stop_line)` with the `steps`
rule. It stops at step `stop_line + 1`. With no calibration, or a damaged one, the hook only
watches. The calibration is read when the turn opens.

## Timing

The work after stdin is read should be at most 10 ms (lock, read the log, decide, append). The whole command, including the launcher and Python starting, should be at most 200 ms
at the 95th percentile (SC-002).

## Debug capture (for SC-008)

No extra capture is needed. The run log already holds each step's `call_id`. `loopbrake agreement`
([cli.md](cli.md)) matches those ids against the transcripts.
