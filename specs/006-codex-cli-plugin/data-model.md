# Data Model: Codex CLI Plugin

**Feature**: [spec.md](spec.md) | **Research**: [research.md](research.md)

Codex tasks use the records LoopBrake already writes (Phases 2–4). This feature adds two optional
fields and one naming rule. Readers treat every new field as optional; old records keep working.

## Changes to existing records (additive; `"v"` stays 1)

| Record | Field | Meaning | Source |
|---|---|---|---|
| `run_start` | `turn_id` (optional) | Codex's id for the task; later events of another turn are ignored for this one | R2 |
| `run_start` | `transcript` (optional) | the main session's transcript path, to tell helper calls apart; local only, never exported | R3 |
| `run_start` | `folder` (optional) | the last part of Codex's `cwd`, the project's readable name in the dashboard; local only, never exported | R8 |
| `step` | `call_id` | Codex's `tool_use_id`, the same id the history uses | R4 |

## Codex project

| Field | Rule |
|---|---|
| `name` | `codex-<last 40 characters of the cwd, letters, digits and dashes>-<first 6 hex of sha256(cwd)>`, built like the Claude Code `cc-` names, so the same folder gives two projects |
| `limit` | the calibration file `~/.loopbrake/calibration/<name>.json`, learned only from this folder's Codex sessions |
| `agent` | `codex` (the dashboard and export derive it from the `codex-` prefix) |

## Codex task (one run)

| Field | Rule |
|---|---|
| boundaries | opens at `UserPromptSubmit`; closes at `Stop` (finished, or stopped if LoopBrake stopped it), at `Interrupt` (interrupted), or at the next `UserPromptSubmit` (interrupted, or stopped) |
| steps | main-agent `PostToolUse` events of this `turn_id`, each `tool_use_id` counted once |
| stopped | after its `stop` record, every `PreToolUse` of this `turn_id` is refused |

**States**: `running → finished | stopped | interrupted`, as for Claude Code tasks.

## History task (calibration, `codex_turns()`)

| Field | Rule |
|---|---|
| file | one main-session file, `~/.codex/sessions/**/rollout-*.jsonl`, whose `session_meta.cwd` is the project folder |
| boundaries | a user message to its `task_complete` (finished) or `turn_aborted` (interrupted, left out); messages sent while Codex works stay in the running task (R4) |
| steps | local tool calls (`function_call`, `custom_tool_call`, `local_shell_call`) in order; hosted tools (`web_search_call`) skipped, as live |
| left out | tasks LoopBrake stopped (matched by call id), tasks marked "leave out", interrupted tasks |
| mistakes | a stop marked "it wasn't stuck" counts as a good task longer than any limit (constitution) |

## Validation rules

- A hook event whose `session_id` isn't `[A-Za-z0-9._-]{1,128}` is ignored, as in Phase 3.
- A `PostToolUse` whose `transcript_path` differs from the task's `transcript` is a helper's and is
  not counted (R3).
- A `tool_use_id` already counted in this task isn't counted again (a call reported twice).
- The `folder` and `transcript` fields never leave the computer: export reads neither.
