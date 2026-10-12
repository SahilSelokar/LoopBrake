# Contract: `loopbrake hook <event>` for Claude Code (changes in 0.6.0)

Extends [specs/004 contracts/hooks.md](../../004-claude-code-plugin/contracts/hooks.md). Anything not
named here is unchanged. Ignored inputs, locking and fail-safety are as before: the hook exits 0 every
time, prints nothing on an internal error, and `LOOPBRAKE_DEBUG=1` re-raises errors.

## Can this session be asked? (research R3)

A hook call **can ask** when both are true:
- the environment's `CLAUDE_CODE_ENTRYPOINT` is set and doesn't start with `sdk`;
- the input's `permission_mode` is `default`, `acceptEdits`, `plan` or `auto`.

Anything else, including missing values, means **can't ask**: LoopBrake stops exactly as in 0.5.0.

## Events

| Command | Claude Code event | Matcher | What changes |
|---|---|---|---|
| `loopbrake hook pre-tool` | `PreToolUse` | `*` | **New.** See "pre-tool" below. |
| `loopbrake hook tool` | `PostToolUse` | `*` | If the call was held by an open question: `answer allowed` first, then the line becomes 2t − 1 (t = the ask point), then the step is counted. In a session that can ask, it never replies `continue: false`. |
| `loopbrake hook tool-failed` | `PostToolUseFailure` | `*` | Same as `tool`, with error = true. |
| `loopbrake hook stop` | `Stop` | none | With an open question and no held call run: `answer denied`, `stop by person`, then the turn ends `stopped`. |
| `loopbrake hook prompt` | `UserPromptSubmit` | none | The same closing rule as `stop` for an open question, then a new turn as before. |

## `pre-tool`

Done under the session lock, on the open turn:

| Case | stdout |
|---|---|
| Ignored input, no open turn, watching only, or can't ask | nothing |
| `would_stop(1)` is true (this call would pass the line), or a question is open: this covers calls on their way and Claude carrying on after a rejection (research R4, R5) | write `ask` (a new `ask_point`, or the open one); reply `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": "<question>"}}` |
| Anything else | nothing (the call goes ahead as usual) |

`pre-tool` never counts a step. Only `tool` and `tool-failed` do, as before, so live counts and history
counts still agree.

## Question text (`<question>`)

Built from the same parts as `plain_stop`, so the dashboard and export can share the words. Example,
with line 38 from 758 tasks:

```text
LoopBrake: this task has made 38 tool calls. In this project, good tasks almost never need more
than 38 (fewer than 1 in 20 of your 758 past tasks did). Its last few tool calls repeat each other.
Allow to keep going: LoopBrake asks again at 78. Deny to stop the task here.
```

- When no stuck signal fired, the stuck-signal sentence is left out.
- When a call already on its way repeats the question, the text is the same, so the person sees one
  question repeated, not a new one.

## Sessions that can't ask

Unchanged from 0.5.0: the call that passes the line runs, `tool` replies
`{"continue": false, "stopReason": "<reason>"}`, and the reason ends with the `/loopbrake:mistake`
sentence.
