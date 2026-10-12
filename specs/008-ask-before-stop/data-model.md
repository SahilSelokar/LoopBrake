# Data Model: Ask Before Stopping (Claude Code)

**Feature**: [spec.md](spec.md) | **Research**: [research.md](research.md)

Everything lives in the existing per-session run log, `~/.loopbrake/runs/<session_id>.jsonl`
(constitution, "State"). Two events are new and one gains a field. Readers ignore fields and events
they don't know, so older dashboards and exports keep working.

## New event: `ask`

LoopBrake held a main-agent tool call and asked the person. One record per held call.

| Field | Type | Meaning |
|---|---|---|
| `event` | `"ask"` | |
| `session`, `run` | string | as on every event |
| `step` | int | the held call's number in the turn (count so far + 1) |
| `ask_point` | int | the call number at which this question started. It equals `step` for the first held call; a call already on its way repeats the question and keeps the same `ask_point` (research R5). |
| `stop_line` | int | the line the turn was compared with: the calibrated line, or 2t − 1 after an allow at t |
| `reason` | string | the brake's reason (same format as a `stop` event's reason, never tool content) |
| `call_id` | string | the held call's `tool_use_id` |

## New event: `answer`

What came of a question. One record per ask point.

| Field | Type | Meaning |
|---|---|---|
| `event` | `"answer"` | |
| `session`, `run` | string | |
| `ask_point` | int | which question |
| `verdict` | `"allowed"` or `"denied"` | allowed: a held call ran (its `PostToolUse` came). Denied: the turn ended (`Stop` or a new prompt) with no held call run. |
| `call_id` | string or null | for allowed, the held call that ran first |

## Adapter event: `approve` (Claude Code, as in Codex)

A call let through without a question while the turn has a line: `{event, session, run, call_id}`.
The adapter counts approved calls that have no `step` yet as calls on their way (`pending`), so a
batch can't pass the line unasked (spec FR-008). The Codex adapter already writes the same event.

## Changed event: `stop`

When a question was denied, the plugin writes the usual `stop` event:
- `step` is the count when the turn ended;
- `stop_line` and `reason` come from the question;
- one new field, `by: "person"`.

A stop with no `by` field is LoopBrake's own (sessions where nobody could be asked). Every existing
reader (status, dashboard, export, calibration) sees a stop either way.

## The brake's state for one turn

Rebuilt from the log on every hook call (`Brake.from_events`), as today:

- **steps**: the counted calls (unchanged).
- **line**: the calibrated `stop_line`, or 2t − 1 after the last allowed ask point t (research R6).
  `None` while only watching.
- **open question**: the last `ask_point` with no `answer` yet, and its held `call_id`s.
- **stopped / by**: set by a `stop` event.

## State transitions (one turn, in a session that can ask)

```text
counting --(PreToolUse: next call would pass `line`)--> asking
asking   --(PreToolUse: another call past `line`)-----> asking      (same question, another `ask` record)
asking   --(PostToolUse for a held call)--------------> counting    (`answer allowed`; line = 2t − 1; the call is counted)
asking   --(Stop, or a new prompt, nothing held ran)--> stopped     (`answer denied`, `stop by person`, run_end stopped)
```

In a session that can't ask (research R3), there is no `asking` state. A call that passes `line` is
counted in `PostToolUse`, and the turn stops, exactly as today.

## Calibration mapping (spec FR-011)

| Turn | In calibration |
|---|---|
| finished, never asked | successful, its length (unchanged) |
| asked, allowed, finished | successful, its real length: every call ran and the transcript shows them all |
| asked, denied | left out as stuck: it has a `stop` event (`_live_verdicts`, unchanged code) |
| interrupted while asking | the same as denied (`answer denied`); the transcript also shows the interrupt |
| stopped where nobody could be asked | unchanged: left out, or counted as a long good turn if marked a mistake |

## Validation rules

- `ask_point` ≥ `stop_line` + 1 at the time of asking. Each new ask point of a turn is at least twice
  the previous one.
- An `answer` follows an `ask_point` exactly once.
- A `stop` with `by: "person"` follows an `answer denied` in the same turn.
- No field holds tool input or output beyond the existing 200-character `action_excerpt` on steps
  (Principle VI).
