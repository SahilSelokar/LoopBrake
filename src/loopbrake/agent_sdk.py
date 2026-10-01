"""Adapter for Claude's agent toolkit (`claude-agent-sdk`). Contract: specs/003-core-package/contracts/agent-sdk.md.

Thin by design (constitution Principle V): it turns toolkit hook events into brake.step() calls and the
brake's decision into the toolkit's stop reply. All stop logic lives in loopbrake.brake.
"""
import json
import warnings

from loopbrake.brake import start


def _text(value):
    """A tool's output as text: strings as they are, content blocks joined, anything else as JSON."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(b, dict) and "text" in b for b in value):
        return "\n".join(b["text"] for b in value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


class Hooks:
    """One brake per session; a new user prompt starts a new run (as Claude Code turns are calibrated)."""

    def __init__(self, project="default", home=None):
        self.project, self.home, self.brakes, self._warned = project, home, {}, False

    def _brake(self, session):
        b = self.brakes.get(session)
        if b is None or b.ended:
            b = self.brakes[session] = start(self.project, session=session, home=self.home)
        return b

    async def user_prompt_submit(self, input_data, tool_use_id=None, context=None):
        try:
            session = input_data.get("session_id") or "default"
            old = self.brakes.pop(session, None)
            if old:
                old.end()
            self.brakes[session] = start(self.project, session=session, home=self.home)
        except Exception as e:
            self._fail(e)
        return {}

    async def post_tool_use(self, input_data, tool_use_id=None, context=None):
        try:
            tool = input_data.get("tool_name") or "tool"
            action = f"{tool} {json.dumps(input_data.get('tool_input') or {}, sort_keys=True, ensure_ascii=False)}"
            decision = self._brake(input_data.get("session_id") or "default").step(
                action, _text(input_data.get("tool_response")), tool=tool)
            if decision.stop:
                return {"continue_": False, "stopReason": decision.reason}
        except Exception as e:
            self._fail(e)
        return {}

    async def stop(self, input_data, tool_use_id=None, context=None):
        try:
            b = self.brakes.pop(input_data.get("session_id") or "default", None)
            if b:
                b.end()
        except Exception as e:
            self._fail(e)
        return {}

    def _fail(self, e):
        if not self._warned:
            self._warned = True
            warnings.warn(f"loopbrake: agent hook error ({e!r}); the agent continues unbraked", RuntimeWarning, stacklevel=2)


def hooks(project="default", *, home=None):
    """The `hooks=` value for ClaudeAgentOptions: UserPromptSubmit, PostToolUse and Stop."""
    try:
        from claude_agent_sdk import HookMatcher
    except ImportError as e:
        raise ImportError('loopbrake.agent_sdk needs the agent toolkit: pip install "loopbrake[agent-sdk]"') from e
    h = Hooks(project, home)
    return {
        "UserPromptSubmit": [HookMatcher(hooks=[h.user_prompt_submit])],
        "PostToolUse": [HookMatcher(hooks=[h.post_tool_use])],
        "Stop": [HookMatcher(hooks=[h.stop])],
    }
