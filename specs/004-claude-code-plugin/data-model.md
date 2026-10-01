# Data Model: Claude Code Plugin

**Feature**: [spec.md](spec.md) | **Research**: [research.md](research.md)

Phase 2's records stay as they are ([records contract](../003-core-package/contracts/records.md)).
This feature adds:
- two optional fields on run events;
- two counts on calibration records;
- a way of reading the open turn back from the log.

There's no new file. Everything lives under `$LOOPBRAKE_HOME` (default `~/.loopbrake`).

## Turn (a run)

A turn is one answer from Claude: from a prompt, or a background-task wake-up, until Claude stops.
It's a Phase 2 run, recorded in `runs/<session>.jsonl`.

| Field | Value |
|---|---|
| `session` | Claude Code's `session_id` |
| `run` | 12 hex characters, new for each turn |
| `project` | from the history folder (see Project) |

**Life of a turn** (research R1):

```text
            UserPromptSubmit, or a step with no open turn
  (none) ----------------------------------------------> open      (run_start)
  open   -- step, count <= stop line ------------------> open      (step)
  open   -- step, count  > stop line ------------------> braked    (step, stop; Claude is told to stop)
  braked -- more steps (parallel calls in flight) -----> braked    (step; still says stop)
  open   -- Stop ---------------------------------------> closed    (run_end: finished)
  braked -- Stop, or the next UserPromptSubmit --------> closed    (run_end: stopped)
  open   -- the next UserPromptSubmit (Esc, no Stop) ---> closed    (run_end: interrupted)
  open with 0 steps -- UserPromptSubmit ----------------> unchanged (a second prompt event is harmless)
```

**Steps**: one per `PostToolUse` or `PostToolUseFailure` from the main agent. Events with
`agent_id` are ignored.

## Open turn (read from the log, never stored)

Hooks and the status line rebuild the open turn from the session's log. Nothing else holds it
(constitution: the log is "the single source for live state"). The rule:

1. Find the last `run_start` in `runs/<session>.jsonl`.
2. If a `run_end` with the same `run` comes after it, no turn is open.
3. Otherwise the open turn is:
   - `run`, `project` and `calibration`, from that `run_start`;
   - the steps, from the `step` events after it;
   - `braked`, if a `stop` event follows, with its `reason`.

**Writers** take an exclusive `flock` on the log file while they read it and append. Readers (the
status line) don't lock: a half-written last line is skipped, as Phase 2's reader already does.

**Calibration** is copied into `run_start` when the turn opens. Calibrating mid-turn affects the
next turn, not this one.

## Project (Claude Code)

| Field | Rule |
|---|---|
| History folder | `$CLAUDE_CONFIG_DIR/projects/<slug>` (default `~/.claude/projects/<slug>`); slug = the working folder with every non-letter, non-digit character replaced by `-` |
| In hooks | `Path(transcript_path).parent` |
| Name | `cc-` + last 40 characters of the folder name (leading `-` removed) + `-` + first 6 hex characters of sha256(folder name) |

Valid under Phase 2's rule `[A-Za-z0-9._-]{1,64}`. Two folders with the same name in different
places get different names.

## Run record events (changed: optional fields)

| Event | New optional field | Meaning |
|---|---|---|
| `step` | `call_id` | Claude Code's `tool_use_id` for this step |
| `stop` | `call_id` | the tool call at which the turn was stopped |
| `feedback` | none | `verdict` `exclude` now also applies to live Claude Code turns (research R10) |

These are additive, so `"v"` stays 1, and Phase 2 readers ignore unknown fields. The Agent SDK
adapter may fill `call_id` too, but doesn't have to.

## Calibration record (changed: two counts)

`source` gains two counts for `kind: "claude-code"` (research R10):

| Field | Meaning |
|---|---|
| `stops_left_out` | turns LoopBrake stopped, or the user excluded, that were left out |
| `mistakes_counted` | stops marked mistaken, counted as good turns longer than any line |

Neither holds text. Both are 0 for history from before the brake was on.

## Transcript turn (calibration reader, changed)

`traces.claude_code_turns` keeps its output (`Run`s) and changes two things:
- **Where turns start**: a prompt, notification or compaction summary starts a new turn only when
  the previous turn is over. That is, its last main-thread answer stopped for a reason other than
  `tool_use`, or it was interrupted (research R1).
- **Tool call ids**: each turn also carries the `tool_use` ids of its steps, so calibration can match
  it to live turns.

## Hook input (read-only, from Claude Code)

Only these fields are used. Anything else is ignored.

| Field | Used for |
|---|---|
| `session_id` | the run log's name |
| `transcript_path` | the project (its parent folder) |
| `agent_id` | when present, the event is ignored (subagent) |
| `tool_name`, `tool_input` | the step's action: `<tool_name> <tool_input as sorted JSON>`, the same format as the calibration reader |
| `tool_use_id` | `call_id` |

`tool_response` and `error` are never read. The step's error flag comes from which event fired.

## Validation rules

- **Session ids** become file names, so they must match `[A-Za-z0-9._-]{1,128}`. Any other input
  is ignored, with no records written.
- **Actions** use exactly the calibration reader's format. Records keep at most **200** characters
  of them (unchanged).
- **Tool outputs and prompt text** are never written anywhere (Principle VI).
