"""The Codex CLI adapter (specs/006-codex-cli-plugin): hook events in, Brake calls through, replies out.

Event shapes follow what Codex 0.160.0 sent in the probe (research R10). Made-up paths and ids only.
"""
import hashlib
import json
import statistics
import time

import pytest

from loopbrake import codex, records

CWD = "/home/someone/demo"
PROJECT = codex.project_name(CWD)
TRANSCRIPT = "/home/someone/.codex/sessions/2026/10/02/rollout-s1.jsonl"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOPBRAKE_HOME", str(tmp_path / "lb"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    return records.home()


def calibrate(home, stop_line, project=PROJECT, n=19):
    (home / "calibration").mkdir(parents=True, exist_ok=True)
    rec = {"v": 1, "project": project, "method": "steps", "alpha": 0.05, "n": n, "k": n, "stop_line": stop_line,
           "watch_only": stop_line is None, "source": {"kind": "codex"}, "created": "2026-10-02", "version": "0.4.0"}
    (home / "calibration" / f"{project}.json").write_text(json.dumps(rec))


def event(name, turn="turn-1", session="s1", **extra):
    return {"session_id": session, "turn_id": turn, "transcript_path": TRANSCRIPT, "cwd": CWD, "hook_event_name": name,
            "model": "test", "permission_mode": "default"} | extra


def prompt(turn="turn-1", text="Run the tests.", **extra):
    return event("UserPromptSubmit", turn, prompt=text, **extra)


def call(n, turn="turn-1", **extra):
    return event("PostToolUse", turn, tool_name="Bash", tool_input={"command": f"echo {n}"}, tool_response="SECRET-OUTPUT",
                 tool_use_id=f"call_{turn}_{n}") | extra


def pre(n, turn="turn-1"):
    return event("PreToolUse", turn, tool_name="Bash", tool_input={"command": f"echo {n}"}, tool_use_id=f"call_{turn}_{n}")


def hook(home, name, data):
    out = codex.hook(name, data if isinstance(data, str) else json.dumps(data), home)
    return json.loads(out) if out else None


def log(home, session="s1"):
    return [json.loads(l) for l in (home / "runs" / f"{session}.jsonl").read_text().splitlines()]


# ---- project identity (data-model.md) ----

def test_project_name():
    digest = hashlib.sha256(CWD.encode()).hexdigest()[:6]
    assert PROJECT == f"codex-home-someone-demo-{digest}"
    assert records.valid_project(PROJECT) and not PROJECT.startswith("cc-")
    long = "/x" * 40 + "/same-tail-of-forty-characters-here"
    assert len(codex.project_name(long)) <= 64 and records.valid_project(codex.project_name(long))


# ---- a task's life (contracts/hooks.md) ----

def test_prompt_opens_a_task_with_the_codex_fields(home):
    assert hook(home, "codex-prompt", prompt()) is None
    start = log(home)[0]
    assert start["event"] == "run_start" and start["project"] == PROJECT
    assert (start["turn_id"], start["transcript"], start["folder"]) == ("turn-1", TRANSCRIPT, "demo")


def test_stop_in_two_parts(home):
    calibrate(home, 3)
    hook(home, "codex-prompt", prompt())
    for n in (1, 2, 3):
        assert hook(home, "codex-pre-tool", pre(n)) is None
        assert hook(home, "codex-tool", call(n)) is None
    reply = hook(home, "codex-tool", call(4))
    assert reply["continue"] is False and reply["stopReason"] == reply["systemMessage"]
    msg = reply["stopReason"]
    assert msg.startswith("LoopBrake stopped this task after 4 tool calls.")
    assert msg.endswith('If it wasn\'t stuck, send "loopbrake: mistake", then tell Codex to continue.')
    deny = hook(home, "codex-pre-tool", pre(5))
    assert deny == {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                           "permissionDecisionReason": msg}}
    assert hook(home, "codex-pre-tool", pre(1, turn="turn-other")) is None  # another task isn't refused
    assert hook(home, "codex-stop", event("Stop")) is None  # never "block": that would make Codex keep going
    kinds = [e["event"] for e in log(home)]
    assert kinds.count("step") == 4 and kinds.count("stop") == 1 and kinds[-1] == "run_end"
    assert log(home)[-1]["status"] == "stopped"
    assert "SECRET-OUTPUT" not in (home / "runs" / "s1.jsonl").read_text()  # tool output is never recorded


def test_next_prompt_starts_counting_again(home):
    calibrate(home, 3)
    hook(home, "codex-prompt", prompt())
    for n in range(1, 5):
        hook(home, "codex-tool", call(n))
    hook(home, "codex-prompt", prompt("turn-2"))  # no Stop came: the stopped task closes as stopped
    assert hook(home, "codex-pre-tool", pre(1, "turn-2")) is None
    assert hook(home, "codex-tool", call(1, "turn-2")) is None
    ends = [e for e in log(home) if e["event"] == "run_end"]
    assert ends[0]["status"] == "stopped"


def test_interrupt_and_finish(home):
    hook(home, "codex-prompt", prompt())
    hook(home, "codex-tool", call(1))
    hook(home, "codex-interrupt", event("Interrupt"))
    hook(home, "codex-prompt", prompt("turn-2"))
    hook(home, "codex-tool", call(1, "turn-2"))
    hook(home, "codex-stop", event("Stop", "turn-2"))
    assert [e["status"] for e in log(home) if e["event"] == "run_end"] == ["interrupted", "finished"]


def test_each_call_counted_once_and_helpers_not_at_all(home):
    calibrate(home, 3)
    hook(home, "codex-prompt", prompt())
    hook(home, "codex-tool", call(1))
    hook(home, "codex-tool", call(1))  # the same call reported twice
    hook(home, "codex-tool", call(2, transcript_path="/home/someone/.codex/sessions/helper.jsonl"))  # a helper's own file
    hook(home, "codex-subagent-start", event("SubagentStart", agent_id="a1", agent_type="worker"))
    hook(home, "codex-tool", call(3))  # while a helper runs: not counted (the safe side)
    hook(home, "codex-subagent-stop", event("SubagentStop", agent_id="a1", agent_type="worker"))
    hook(home, "codex-tool", call(4))
    assert [e["call_id"] for e in log(home) if e["event"] == "step"] == ["call_turn-1_1", "call_turn-1_4"]


def test_watch_only_never_replies(home):
    hook(home, "codex-prompt", prompt())
    assert all(hook(home, "codex-tool", call(n)) is None for n in range(1, 40))
    assert hook(home, "codex-pre-tool", pre(40)) is None


def test_bad_input_is_ignored(home):
    assert hook(home, "codex-prompt", prompt() | {"session_id": "../etc"}) is None
    assert hook(home, "codex-tool", "{not json") is None
    assert hook(home, "codex-nope", prompt()) is None
    assert not (home / "runs").exists() or not list((home / "runs").glob("*.jsonl"))


def test_fails_safe(home, capsys):
    calibrate(home, 3)
    hook(home, "codex-prompt", prompt())
    (home / "runs" / "s1.jsonl").write_text("{damaged\n" * 3)
    assert hook(home, "codex-tool", call(1)) is None
    (home / "calibration" / f"{PROJECT}.json").write_text("{damaged")
    assert hook(home, "codex-prompt", prompt("turn-2")) is None  # damaged calibration: watch only
    assert all(hook(home, "codex-tool", call(n, "turn-2")) is None for n in range(1, 10))
    err = capsys.readouterr().err
    assert "Traceback" not in err


def test_hooks_are_fast(home):
    calibrate(home, 1000)
    hook(home, "codex-prompt", prompt())
    times = []
    for n in range(1, 51):
        for name, data in (("codex-pre-tool", pre(n)), ("codex-tool", call(n))):
            began = time.perf_counter()
            hook(home, name, data)
            times.append(time.perf_counter() - began)
    assert statistics.quantiles(times, n=20)[18] < 0.010, sorted(times)[-5:]
