"""The toolkit adapter, tested by calling its callbacks with plain dicts: no SDK or API key needed."""
import asyncio
import json

import pytest

from loopbrake.agent_sdk import Hooks


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    home = tmp_path / "lb"
    (home / "calibration").mkdir(parents=True)
    (home / "calibration" / "demo.json").write_text(json.dumps(
        {"v": 1, "project": "demo", "method": "steps", "alpha": 0.05, "n": 30, "k": 29, "stop_line": 5,
         "watch_only": False, "source": {}, "created": "2026-10-01", "version": "0.1.0"}))
    return Hooks(project="demo", home=home), home


def call(cb, **data):
    return asyncio.run(cb(data, None, None))


def tool_event(i):
    return {"hook_event_name": "PostToolUse", "session_id": "s1", "tool_name": "Bash",
            "tool_input": {"command": f"ls {i}"}, "tool_response": {"stdout": "a", "exit_code": 0}}


def test_stops_after_the_stop_line(adapter):
    hooks, home = adapter
    call(hooks.user_prompt_submit, session_id="s1", prompt="go")
    replies = [call(hooks.post_tool_use, **tool_event(i)) for i in range(6)]
    assert replies[:5] == [{}] * 5
    assert replies[5]["continue_"] is False and replies[5]["stopReason"].startswith("stopped at step 6")
    call(hooks.stop, session_id="s1")
    events = [json.loads(l) for l in (home / "runs" / "s1.jsonl").read_text().splitlines()]
    assert events[1]["action_excerpt"] == 'Bash {"command": "ls 0"}'
    assert events[-1]["event"] == "run_end" and events[-1]["status"] == "stopped"


def test_each_prompt_is_a_new_run(adapter):
    hooks, home = adapter
    call(hooks.user_prompt_submit, session_id="s1", prompt="one")
    for i in range(3):
        call(hooks.post_tool_use, **tool_event(i))
    call(hooks.user_prompt_submit, session_id="s1", prompt="two")
    assert all(call(hooks.post_tool_use, **tool_event(i)) == {} for i in range(5))  # counting restarted
    starts = [l for l in (home / "runs" / "s1.jsonl").read_text().splitlines() if '"run_start"' in l]
    assert len(starts) == 2


def test_errors_never_reach_the_agent(adapter, monkeypatch):
    hooks, _ = adapter
    monkeypatch.setattr("loopbrake.agent_sdk.start", lambda *a, **k: 1 / 0)
    with pytest.warns(RuntimeWarning):
        assert call(hooks.post_tool_use, **tool_event(0)) == {}


def test_hooks_needs_the_sdk():
    sdk = pytest.importorskip("claude_agent_sdk")
    from loopbrake.agent_sdk import hooks
    got = hooks(project="demo")
    assert set(got) == {"UserPromptSubmit", "PostToolUse", "Stop"}
    assert all(isinstance(m[0], sdk.HookMatcher) for m in got.values())
