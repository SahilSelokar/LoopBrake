# Contract: Codex hooks

The facts and decisions are in [research.md](../research.md), R1–R3. Every hook runs
`"$PLUGIN_ROOT/bin/loopbrake" hook codex-<event>` with Codex's JSON on stdin.

## Failing safely (constitution 2.4.0, applied to Codex)

Every hook exits 0. Any failure inside LoopBrake prints one plain line to stderr and **no** reply on
stdout, so Codex treats it as "nothing to say" and carries on. A hook never exits 2, which Codex
reads as "refuse" (`PreToolUse`) or "keep going" (`Stop`). The launcher keeps this promise when the
package is missing or uv can't reach the network, as for Claude Code.

## Events

| Hook | Event name | Reads | Does | Replies (stdout) |
|---|---|---|---|---|
| `UserPromptSubmit` | `codex-prompt` | `session_id`, `turn_id`, `cwd`, `transcript_path` | closes an open task (stopped or interrupted), opens a new one with `turn_id`, `transcript` and `folder` | nothing |
| `PreToolUse` | `codex-pre-tool` | `session_id`, `turn_id` | if this task is stopped, refuses | the refusal below, or nothing |
| `PostToolUse` | `codex-tool` | `session_id`, `turn_id`, `transcript_path`, `tool_name`, `tool_use_id`, `tool_input` | counts a main-agent call once (helpers' and repeats skipped); decides | the stop below, or nothing |
| `Stop` | `codex-stop` | `session_id`, `turn_id` | closes the task (finished, or stopped) | nothing (never `decision: "block"`) |
| `Interrupt` | `codex-interrupt` | `session_id`, `turn_id` | closes the task as interrupted | nothing |

Matchers: `PreToolUse` and `PostToolUse` use `.*` (every local tool). Timeouts: 30 s, as for Claude
Code; `Interrupt` keeps Codex's 1 s default.

## The stop (R1)

**At the decision**, the `PostToolUse` that passes the limit replies:

```json
{"continue": false,
 "stopReason": "<the plain stop message>",
 "systemMessage": "<the plain stop message>"}
```

**After it**, every `PreToolUse` of the same `turn_id` replies:

```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
 "permissionDecisionReason": "<the plain stop message>"}}
```

**The plain stop message** is the Claude Code plugin's, with Codex's commands:
"LoopBrake stopped this task after N tool calls. Based on your M past successful tasks in this
project, good tasks almost never need more than L (fewer than 1 in 20 do). [This one also looks
stuck: ….] If it wasn't stuck, use the loopbrake-mistake skill, then tell Codex to continue."

**Watch-only projects** (no limit yet) never reply anything.

## Speed (spec SC-002)

`codex-pre-tool` reads only whether the open task is stopped and returns; `codex-tool` does what the
Claude Code `tool` hook does. Together: at most 200 ms per tool call at p95, through the launcher.
