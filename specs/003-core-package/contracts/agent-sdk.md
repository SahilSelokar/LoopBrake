# Contract: Adapter for Claude's agent toolkit (`loopbrake.agent_sdk`)

Install with `pip install "loopbrake[agent-sdk]"`, or `uv add "loopbrake[agent-sdk]"`. The core
package never imports this module.

## Use

```python
from claude_agent_sdk import ClaudeAgentOptions, query
from loopbrake.agent_sdk import hooks

options = ClaudeAgentOptions(hooks=hooks(project="my-agent"))
async for message in query(prompt="Fix the failing test", options=options):
    print(message)
```

## `hooks(project="default", *, home=None) -> dict`

It returns `{"UserPromptSubmit": [...], "PostToolUse": [...], "Stop": [...]}`, with each value a
list holding one `HookMatcher`. Each matcher wraps one of the callbacks below. The function needs
`claude_agent_sdk`, and raises a clear `ImportError` naming the extra if it's missing.

## Callbacks (plain dict in, plain dict out; testable without the SDK)

| Event | Behavior | Returns |
|---|---|---|
| `UserPromptSubmit` | Ends any open run for `input_data["session_id"]` as `finished`, then starts a new brake (`loopbrake.start(project, session=session_id)`) | `{}` |
| `PostToolUse` | Starts a brake for the session if none is open. Then calls `brake.step(action, result, tool=tool_name)`, where `action = f"{tool_name} {json.dumps(tool_input, sort_keys=True, ensure_ascii=False)}"` and `result` is `tool_response` as text (strings as they are, content blocks joined, anything else as JSON). | `{}` to continue. `{"continue_": False, "stopReason": reason}` to stop (see research R8 for the `stopReason` check). |
| `Stop` | Ends the session's open run as `finished`, or `stopped` if the brake stopped | `{}` |

**Rules**:
- **No stop logic here**: every decision comes from `Brake` (Principle V).
- **Never crashes the agent**: any exception inside a callback is caught. The callback returns `{}`
  and warns once (FR-005).
