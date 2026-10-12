import json

import pytest

from loopbrake import claude_code, records


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOPBRAKE_HOME", str(tmp_path / "lb"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.delenv("CLAUDE_CODE_ENTRYPOINT", raising=False)  # tests run inside Claude Code too: start from "can't ask"
    return records.home()


# ---- project identity (research R6). Made-up paths only: real folder names never go in the repo ----

def test_history_folder(home, tmp_path):
    assert claude_code.history_folder("/home/me/my app?") == tmp_path / "claude" / "projects" / "-home-me-my-app-"


def test_project_name():
    assert claude_code.project_name("-home-me-my-app-") == "cc-home-me-my-app-c57a41"
    cut_on_a_dash = "-home-q-" + "b" * 39  # its last 40 characters start with "-"
    assert claude_code.project_name(cut_on_a_dash).startswith("cc-" + "b" * 39 + "-")  # no "--" after the cut
    long_a, long_b = "-a" + "-x" * 40 + "-same-tail-of-forty-characters-here", "-b" + "-x" * 40 + "-same-tail-of-forty-characters-here"
    names = {claude_code.project_name(long_a), claude_code.project_name(long_b)}
    assert len(names) == 2
    assert all(records.valid_project(n) and len(n) <= 64 for n in names)


# ---- the hooks (US1, contracts/hooks.md) ----

import os
import socket
import stat
import statistics
import subprocess
import sys
import time
from pathlib import Path

from loopbrake import brake
from loopbrake.traces import claude_code_turns

FOLDER = "-home-me-demo-"
PROJECT = claude_code.project_name(FOLDER)
MIDTURN = Path(__file__).parent / "fixtures" / "claude_code" / "midturn.jsonl"


def calibrate(home, stop_line, project=PROJECT, n=19):
    (home / "calibration").mkdir(parents=True, exist_ok=True)
    rec = {"v": 1, "project": project, "method": "steps", "alpha": 0.05, "n": n, "k": n, "stop_line": stop_line,
           "watch_only": stop_line is None, "source": {"kind": "claude-code"}, "created": "2026-10-01", "version": "0.2.0"}
    (home / "calibration" / f"{project}.json").write_text(json.dumps(rec))


def payload(session="s1", folder=FOLDER, **extra):
    tp = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / folder / f"{session}.jsonl"
    return {"session_id": session, "transcript_path": str(tp), "cwd": "/home/me/demo"} | extra


def tool(n=1, **extra):
    return payload(tool_name="Bash", tool_input={"command": f"echo {n}"}, tool_response={"stdout": "SECRET-OUTPUT"},
                   tool_use_id=f"t{n}") | extra


def hook(home, event, data):
    return claude_code.hook(event, data if isinstance(data, str) else json.dumps(data), home)


def log(home, session="s1"):
    return [json.loads(l) for l in (home / "runs" / f"{session}.jsonl").read_text().splitlines()]


def test_stops_right_after_the_stop_line(home):
    calibrate(home, 3)
    assert hook(home, "prompt", payload()) is None
    assert [hook(home, "tool", tool(i)) for i in (1, 2, 3)] == [None] * 3
    out = json.loads(hook(home, "tool", tool(4)))
    assert out["continue"] is False
    assert out["stopReason"].startswith("LoopBrake stopped this task after 4 tool calls. Based on your 19 past successful "
                                        "tasks in this project, good tasks almost never need more than 3 (fewer than 1 in 20 do).")
    assert out["stopReason"].endswith(" If it wasn't stuck, run /loopbrake:mistake, then tell Claude to continue.")
    assert "α" not in out["stopReason"] and "step " not in out["stopReason"]  # plain words for the user
    again = json.loads(hook(home, "tool", tool(5)))  # a parallel call still in flight
    assert again["continue"] is False and again["stopReason"] == out["stopReason"]
    assert hook(home, "stop", payload()) is None
    ev = log(home)
    assert [e["call_id"] for e in ev if e["event"] == "stop"] == ["t4"]
    assert ev[-1]["event"] == "run_end" and ev[-1]["status"] == "stopped"


def test_turn_boundaries(home):
    calibrate(home, 3)
    hook(home, "prompt", payload()), hook(home, "tool", tool(1)), hook(home, "prompt", payload())
    ends = [e for e in log(home) if e["event"] == "run_end"]
    assert [e["status"] for e in ends] == ["interrupted"]
    hook(home, "tool", tool(2)), hook(home, "stop", payload())
    assert [e["status"] for e in log(home) if e["event"] == "run_end"] == ["interrupted", "finished"]
    assert [e["step"] for e in log(home) if e["event"] == "step"] == [1, 1]  # the second turn counts from 1 again
    hook(home, "tool", tool(3))  # a background task woke Claude after Stop: a new turn opens
    assert sum(e["event"] == "run_start" for e in log(home)) == 3
    for i in (4, 5, 6):
        hook(home, "tool", tool(i))
    hook(home, "prompt", payload())  # braked and no Stop came: the next prompt closes it as stopped
    assert [e["status"] for e in log(home) if e["event"] == "run_end"][-1] == "stopped"


def test_a_second_prompt_event_is_harmless(home):
    hook(home, "prompt", payload()), hook(home, "prompt", payload())
    ev = log(home)
    assert [e["event"] for e in ev] == ["run_start"]


def test_watch_only_never_stops(home):
    hook(home, "prompt", payload())
    assert all(hook(home, "tool", tool(i)) is None for i in range(10))
    assert log(home)[0]["calibration"]["watch_only"] is True


def test_ignored_inputs_write_nothing(home):
    for data in (tool(agent_id="sub-1", agent_type="Explore"), tool(session_id="../x"), {"session_id": "s1", "tool_name": "Bash"}):
        assert hook(home, "tool", data) is None
    assert not (home / "runs").exists()


def test_failed_tool_and_action_format(home):
    hook(home, "prompt", payload())
    hook(home, "tool-failed", tool(1, tool_input={"z": 1, "command": "x" * 300}, error="boom"))
    step = [e for e in log(home) if e["event"] == "step"][0]
    assert step["error"] is True and step["tool"] == "Bash"
    assert step["action_excerpt"] == ("Bash " + json.dumps({"z": 1, "command": "x" * 300}, sort_keys=True, ensure_ascii=False))[:200]


def test_tool_outputs_are_never_written(home):
    hook(home, "prompt", payload())
    for i in range(3):
        hook(home, "tool", tool(i))
    assert not any("SECRET-OUTPUT" in p.read_text() for p in home.rglob("*") if p.is_file())


def test_failures_never_raise_or_stop(home, capsys):
    assert hook(home, "tool", "{not json") is None
    assert capsys.readouterr().err.count("\n") == 1
    calibrate(home, 3)
    (home / "runs").mkdir(parents=True, exist_ok=True)
    (home / "runs" / "s1.jsonl").write_text("{damaged\n")
    assert hook(home, "prompt", payload()) is None and hook(home, "tool", tool(1)) is None
    (home / "calibration" / f"{PROJECT}.json").write_text("{")
    hook(home, "prompt", payload())
    assert all(hook(home, "tool", tool(i)) is None for i in range(10))  # damaged calibration: watch-only
    os.chmod(home / "runs", stat.S_IRUSR | stat.S_IXUSR)
    try:
        assert hook(home, "tool", tool(99, session_id="s2")) is None
    finally:
        os.chmod(home / "runs", stat.S_IRWXU)


def test_parallel_hook_processes_do_not_lose_a_step(home):
    hook(home, "prompt", payload())
    env = os.environ | {"PYTHONPATH": str(Path(claude_code.__file__).parents[1])}
    procs = [subprocess.Popen([sys.executable, "-m", "loopbrake.cli", "hook", "tool"], stdin=subprocess.PIPE, env=env)
             for _ in range(8)]
    for i, p in enumerate(procs):
        p.stdin.write(json.dumps(tool(i)).encode())
        p.stdin.close()
    assert [p.wait(timeout=60) for p in procs] == [0] * 8
    assert sorted(e["step"] for e in log(home) if e["event"] == "step") == list(range(1, 9))


def test_a_turn_without_network(home, monkeypatch):
    def no_network(*a, **k):
        raise AssertionError("loopbrake tried to use the network")

    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    calibrate(home, 2)
    hook(home, "prompt", payload())
    assert [hook(home, "tool", tool(i)) is not None for i in range(3)] == [False, False, True]
    hook(home, "stop", payload())


def replay_through_hooks(home, run, stop_line, session):
    """Feed one reader turn through the hooks; return the step it stopped at, or None."""
    hook(home, "prompt", payload(session=session))
    for t in range(1, len(run.steps) + 1):
        if hook(home, "tool", tool(t, session_id=session)) is not None:
            hook(home, "stop", payload(session=session))
            return t
    hook(home, "stop", payload(session=session))
    return None


def test_hooks_agree_with_the_reader_and_replay(home):
    """SC-001 in CI: the hooks stop each turn of the synthetic transcript exactly where replay() does."""
    runs, _ = claude_code_turns(MIDTURN)
    for line in (0, 1, 2, 3):
        calibrate(home, line)
        for r in runs:
            assert replay_through_hooks(home, r, line, f"{r.run}-{line}") == brake.replay(r, {"stop_line": line, "watch_only": False})


REAL = Path.home() / ".claude" / "projects"


@pytest.mark.skipif(not REAL.exists(), reason="no local Claude Code history (as in CI)")
def test_hooks_agree_on_real_history(home):
    """SC-001 locally: the same check on the builder's own history. Reads private data, prints only counts."""
    from itertools import islice
    turns = list(islice((r for f in sorted(REAL.glob("*/*.jsonl")) for r in claude_code_turns(f)[0] if r.steps), 300))
    checked = 0
    for line in (10, 20, 38):
        calibrate(home, line)
        for i, r in enumerate(turns):
            got = replay_through_hooks(home, r, line, f"real-{line}-{i}")
            assert got == brake.replay(r, {"stop_line": line, "watch_only": False}), f"turn {i} at stop line {line}"
            checked += 1
    assert checked == 3 * len(turns)


def timed_steps(home, session, n=250):
    hook(home, "prompt", payload(session=session))
    times = []
    for i in range(n):
        t0 = time.perf_counter()
        hook(home, "tool", tool(i, session_id=session))
        times.append((time.perf_counter() - t0) * 1000)
    return sorted(times)[int(0.95 * n) - 1]


def test_hook_work_is_fast(home):
    """SC-002: the hook's own work stays within its 10 ms share, also on the largest local session's log."""
    calibrate(home, 1000)
    assert timed_steps(home, "fast") <= 10
    big = home / "runs" / "big.jsonl"
    w = records.RunWriter(big)
    for t in range(315):  # 6,300 earlier steps, as in the largest local session (research R4)
        w.write({"event": "run_start", "session": "big", "run": f"r{t}", "project": PROJECT, "calibration": {"stop_line": 1000, "watch_only": False}})
        for s in range(1, 21):
            w.write({"event": "step", "session": "big", "run": f"r{t}", "step": s, "tool": "Bash", "action_excerpt": "Bash " + "x" * 195, "tokens": None, "error": False, "call_id": f"c{t}-{s}"})
        w.write({"event": "run_end", "session": "big", "run": f"r{t}", "status": "finished", "steps": 20, "tokens": None})
    assert timed_steps(home, "big") <= 10


def test_pre_tool_work_is_fast(home, monkeypatch):
    """specs/008 FR-013: the hook before each call keeps the same 10 ms share as the one after it."""
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "cli")
    calibrate(home, 1000)
    hook(home, "prompt", payload(session="pre", **ASKS))
    times = []
    for i in range(250):
        t0 = time.perf_counter()
        hook(home, "pre-tool", tool(i, session_id="pre", **ASKS))
        times.append((time.perf_counter() - t0) * 1000)
        hook(home, "tool", tool(i, session_id="pre", **ASKS))
    assert sorted(times)[int(0.95 * 250) - 1] <= 10


# ---- the status line (US3, contracts/cli.md) ----

def line(home, session="s1"):
    return claude_code.statusline(json.dumps({"session_id": session, "transcript_path": "/x/y.jsonl", "model": {}}), home)


def snapshot(home):
    return {p: p.stat().st_mtime_ns for p in home.rglob("*")} if home.exists() else {}


def test_statusline_states(home):
    assert line(home) == "LoopBrake: ready"
    calibrate(home, 3)
    hook(home, "prompt", payload())
    assert line(home) == "LoopBrake: 0 of 3 tool calls"
    for i in range(1, 4):
        hook(home, "tool", tool(i))
        assert line(home) == f"LoopBrake: {i} of 3 tool calls"  # SC-007: the count follows every tool call
    hook(home, "tool", tool(4))
    assert line(home) == "LoopBrake: stopped this task at 4 tool calls"
    hook(home, "stop", payload())
    assert line(home) == "LoopBrake: ready"
    hook(home, "prompt", payload(session="w", folder="-home-me-other-"))
    hook(home, "tool", tool(1, session_id="w", transcript_path=payload(session="w", folder="-home-me-other-")["transcript_path"]))
    assert line(home, "w") == "LoopBrake: 1 tool call (watching only)"


def test_statusline_never_fails_or_writes(home):
    hook(home, "prompt", payload())
    before = snapshot(home)
    for bad in ("", "{bad", "[]", json.dumps({"session_id": "../x"}), json.dumps({"session_id": "nobody"})):
        assert claude_code.statusline(bad, home) == "LoopBrake: ready"
    line(home)
    assert snapshot(home) == before


# ---- live vs calibration agreement (SC-008, contracts/cli.md) ----

def agreement_setup(home, tmp_path, live):
    cwd = tmp_path / "work"
    cwd.mkdir()
    folder = claude_code.history_folder(cwd)
    folder.mkdir(parents=True)
    (folder / "s.jsonl").write_text(MIDTURN.read_text())
    project = claude_code.project_name(folder.name)
    for run, calls in live.items():
        w = records.RunWriter(home / "runs" / f"live-{run}.jsonl")
        w.write({"event": "run_start", "session": f"live-{run}", "run": run, "project": project, "calibration": {}})
        for i, c in enumerate(calls, 1):
            w.write({"event": "step", "session": f"live-{run}", "run": run, "step": i, "call_id": c})
    return cwd


def test_agreement_flags_a_higher_live_count(home, tmp_path, monkeypatch, capsys):
    from loopbrake import cli
    live = {"A": ["t1", "t2", "t3"], "B": ["t4"], "C": ["t6"], "D": ["t5", "extra"], "E": ["nope"], "F": []}
    cwd = agreement_setup(home, tmp_path, live)
    lines, higher = claude_code.agreement(cwd, home)
    assert higher == 1
    assert lines == ["higher  run D  live 2  transcript 1",
                     "turns matched 4, equal 2, live lower 1, live higher 1, unmatched 1"]
    monkeypatch.chdir(cwd)
    assert cli.main(["agreement", "--claude-code"]) == 1
    assert capsys.readouterr().out.splitlines() == lines


def test_agreement_passes_when_live_is_never_higher(home, tmp_path, monkeypatch):
    from loopbrake import cli
    cwd = agreement_setup(home, tmp_path, {"A": ["t1", "t2", "t3"], "C": ["t6"]})
    lines, higher = claude_code.agreement(cwd, home)
    assert higher == 0 and lines == ["turns matched 2, equal 1, live lower 1, live higher 0"]
    monkeypatch.chdir(cwd)
    assert cli.main(["agreement", "--claude-code"]) == 0


def test_the_same_call_reported_twice_counts_once(home):
    """If the plugin is ever loaded twice, each event arrives twice. Counting both would stop turns at
    half the stop line: the dangerous direction."""
    calibrate(home, 2)
    hook(home, "prompt", payload())
    got = [hook(home, "tool", tool(i)) for i in (1, 1, 2, 2)]
    assert got == [None] * 4
    assert [e["step"] for e in log(home) if e["event"] == "step"] == [1, 2]
    stop = [hook(home, "tool", tool(3)), hook(home, "tool", tool(3))]
    assert all(json.loads(x)["continue"] is False for x in stop)
    assert [e["step"] for e in log(home) if e["event"] == "step"] == [1, 2, 3]


# ---- Phase 4: tool durations and Claude Code's trace context ----

def test_hooks_record_duration_and_traceparent(home, monkeypatch):
    tp = "00-7c34dde18d794cfe024a074bf0190d06-6b75b47cab499875-01"
    monkeypatch.setenv("TRACEPARENT", tp)
    hook(home, "prompt", payload())
    hook(home, "tool", tool(1, duration_ms=64))
    hook(home, "tool", tool(2))
    ev = log(home)
    assert ev[0]["traceparent"] == tp
    assert [e.get("duration_ms") for e in ev if e["event"] == "step"] == [64, None]
    monkeypatch.delenv("TRACEPARENT")
    hook(home, "prompt", payload(session="s2"))
    assert "traceparent" not in log(home, "s2")[0]


def test_plain_stop_and_reason_codes():
    reason = "stopped at step 7: past the stop line of 6 steps set from your 40 past successful turns (α 5%); repeating in 5 of last 5 steps"
    text = claude_code.plain_stop(7, 6, 40, 0.05, reason, " Use the button if it wasn't stuck.")
    assert text == ("LoopBrake stopped this task after 7 tool calls. Based on your 40 past successful tasks in this project, "
                    "good tasks almost never need more than 6 (fewer than 1 in 20 do). This one also looks stuck: its last few "
                    "tool calls repeat each other. Use the button if it wasn't stuck.")
    assert claude_code.reason_codes(reason) == ["past_limit", "repeating"]
    assert claude_code.reason_codes("stopped at step 3: past the stop line of 2 steps") == ["past_limit"]
    assert claude_code.reason_codes("…; same error again in 2 of last 5 steps; nothing new in 3 of last 5 steps") == ["past_limit", "same_error", "nothing_new"]


# ---- asking before stopping (specs/008, contracts/hooks.md) ----

ASKS = {"permission_mode": "default"}


@pytest.fixture
def can_ask(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "cli")


def pre(home, n, **extra):
    return hook(home, "pre-tool", tool(n, **ASKS) | extra)


def post(home, n, **extra):
    return hook(home, "tool", tool(n, **ASKS) | extra)


def asked(out):
    o = json.loads(out)["hookSpecificOutput"]
    assert (o["hookEventName"], o["permissionDecision"]) == ("PreToolUse", "ask")
    return o["permissionDecisionReason"]


def of(home, kind, session="s1"):
    return [e for e in log(home, session) if e["event"] == kind]


def up_to_the_line(home, line=3):
    calibrate(home, line)
    hook(home, "prompt", payload(**ASKS))
    for i in range(1, line + 1):
        assert pre(home, i) is None
        assert post(home, i) is None


def test_asks_before_the_call_that_would_pass_the_line(home, can_ask):
    up_to_the_line(home)
    question = asked(pre(home, 4))
    assert question.startswith("LoopBrake: this task has made 3 tool calls. In this project, good tasks almost never need "
                               "more than 3 (fewer than 1 in 20 of your 19 past tasks did).")
    assert question.endswith(" Allow to keep going: LoopBrake asks again at 8. Deny to stop the task here.")
    assert "α" not in question and "step " not in question
    assert len(of(home, "step")) == 3  # pre-tool never counts
    [ask] = of(home, "ask")
    assert (ask["step"], ask["ask_point"], ask["stop_line"], ask["call_id"]) == (4, 4, 3, "t4")
    assert not of(home, "stop")


def test_allowing_lets_the_task_go_on_and_asks_again_at_twice_the_call(home, can_ask):
    up_to_the_line(home)
    asked(pre(home, 4))
    assert post(home, 4) is None  # the person said yes: counted, never `continue: false`
    assert [(e["verdict"], e["call_id"]) for e in of(home, "answer")] == [("allowed", "t4")]
    for i in (5, 6, 7):
        assert pre(home, i) is None and post(home, i) is None
    question = asked(pre(home, 8))
    assert question.startswith("LoopBrake: this task has made 7 tool calls. In this project, good tasks almost never need more than 3 ")
    assert "asks again at 16" in question
    assert post(home, 8) is None and not of(home, "stop")
    hook(home, "stop", payload(**ASKS))
    assert of(home, "run_end")[-1]["status"] == "finished" and of(home, "run_end")[-1]["steps"] == 8


def test_the_question_names_a_stuck_signal(home, can_ask):
    calibrate(home, 3)
    hook(home, "prompt", payload(**ASKS))
    same = {"tool_input": {"command": "python run.py"}}
    for i in (1, 2, 3):
        pre(home, i, **same), post(home, i, **same)
    assert "Its last few tool calls repeat each other." in asked(pre(home, 4, **same))


def test_the_question_leaves_out_the_stuck_sentence_when_nothing_fired(home, can_ask):
    calibrate(home, 3)
    hook(home, "prompt", payload(**ASKS))
    calls = [("Read", {"file_path": "/src/app.py"}), ("Grep", {"pattern": "def main", "path": "/src"}),
             ("Bash", {"command": "pytest -q tests/test_app.py"}), ("Edit", {"file_path": "/docs/index.md", "old_string": "a", "new_string": "b"})]
    for i, (name, args) in enumerate(calls[:3], 1):
        pre(home, i, tool_name=name, tool_input=args), post(home, i, tool_name=name, tool_input=args)
    question = asked(pre(home, 4, tool_name=calls[3][0], tool_input=calls[3][1]))
    assert "Its last few" not in question and question.endswith("asks again at 8. Deny to stop the task here.")


def test_no_question_under_the_line_or_while_watching(home, can_ask):
    up_to_the_line(home)
    hook(home, "stop", payload(**ASKS))
    assert not of(home, "ask") and of(home, "run_end")[-1]["status"] == "finished"
    other = "-home-me-other-"  # no calibration: watching only
    hook(home, "prompt", payload(session="s2", folder=other, **ASKS))
    for i in range(1, 60):
        assert hook(home, "pre-tool", tool(i, session_id="s2", transcript_path=payload(folder=other)["transcript_path"], **ASKS)) is None
    assert not of(home, "ask", "s2")


def test_pre_tool_ignores_subagents_and_bad_input(home, can_ask):
    up_to_the_line(home)
    assert hook(home, "pre-tool", tool(4, agent_id="sub-1", **ASKS)) is None
    assert hook(home, "pre-tool", "{not json") is None
    assert not of(home, "ask")


def test_pre_tool_fails_safe(home, can_ask, capsys):
    calibrate(home, 1)
    (home / "runs").mkdir(parents=True, exist_ok=True)
    (home / "runs" / "s1.jsonl").write_text("{damaged\n")
    assert pre(home, 1) is None
    (home / "calibration" / f"{PROJECT}.json").write_text("{")
    hook(home, "prompt", payload(**ASKS))
    assert all(pre(home, i) is None for i in range(1, 10))  # damaged calibration: watch-only, never a question
    assert '"event": "ask"' not in (home / "runs" / "s1.jsonl").read_text()


def test_denying_ends_the_task_as_stopped_by_the_person(home, can_ask):
    up_to_the_line(home)
    asked(pre(home, 4))
    assert hook(home, "stop", payload(**ASKS)) is None  # the held call never ran: the person said no
    [answer], [stop] = of(home, "answer"), of(home, "stop")
    assert (answer["verdict"], answer["ask_point"]) == ("denied", 4)
    assert (stop["by"], stop["step"], stop["stop_line"]) == ("person", 3, 3)
    assert of(home, "run_end")[-1]["status"] == "stopped" and len(of(home, "step")) == 3
    hook(home, "prompt", payload(**ASKS))  # the next prompt is a new turn, counting from zero
    assert pre(home, 5) is None and len(of(home, "run_start")) == 2


def test_an_interrupt_while_asking_counts_as_denied(home, can_ask):
    up_to_the_line(home)
    asked(pre(home, 4))
    hook(home, "prompt", payload(**ASKS))  # Esc at the prompt (or a rejection), then a new message
    assert [e["verdict"] for e in of(home, "answer")] == ["denied"]
    assert [e["status"] for e in of(home, "run_end")] == ["stopped"] and of(home, "stop")[0]["by"] == "person"


def test_claude_carrying_on_after_a_rejection_is_asked_again(home, can_ask):
    up_to_the_line(home)
    first = asked(pre(home, 4))
    again = asked(pre(home, 5))  # no step for t4 yet: the question is still open, so it is repeated
    assert again == first
    assert [(e["ask_point"], e["call_id"]) for e in of(home, "ask")] == [(4, "t4"), (4, "t5")]
    assert not of(home, "answer") and not of(home, "stop")


def test_calls_on_their_way_follow_the_same_question(home, can_ask):
    up_to_the_line(home)
    asked(pre(home, 4)), asked(pre(home, 5))  # a batch: both past the line
    assert post(home, 5) is None  # either held call running means yes
    assert [(e["verdict"], e["call_id"]) for e in of(home, "answer")] == [("allowed", "t5")]
    assert post(home, 4) is None and len(of(home, "answer")) == 1  # answered once
    assert not of(home, "stop")


def test_a_batch_cannot_pass_the_line_unasked(home, can_ask):
    calibrate(home, 3)
    hook(home, "prompt", payload(**ASKS))
    assert pre(home, 1) is None and post(home, 1) is None
    assert pre(home, 2) is None and pre(home, 3) is None  # let through, both still running
    assert asked(pre(home, 4))  # 1 done + 2 on their way + this one = 4 > 3
    assert [e["call_id"] for e in of(home, "approve")] == ["t1", "t2", "t3"]


@pytest.mark.parametrize("entry, mode", [
    ("sdk-cli", "default"),            # claude -p
    ("sdk-py", "default"),             # the Agent SDK
    ("cli", "bypassPermissions"),      # permission prompts turned off
    ("cli", "dontAsk"),                # a mode we don't know: can't ask
    (None, "default"),                 # no entrypoint
    ("cli", None),                     # no permission mode
])
def test_where_nobody_can_answer_it_stops_as_before(home, monkeypatch, entry, mode):
    if entry:
        monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", entry)
    extra = {"permission_mode": mode} if mode else {}
    calibrate(home, 3)
    hook(home, "prompt", payload(**extra))
    for i in (1, 2, 3):
        assert hook(home, "pre-tool", tool(i, **extra)) is None
        assert hook(home, "tool", tool(i, **extra)) is None
    assert hook(home, "pre-tool", tool(4, **extra)) is None  # no question
    out = json.loads(hook(home, "tool", tool(4, **extra)))
    assert out["continue"] is False and out["stopReason"].startswith("LoopBrake stopped this task after 4 tool calls.")
    assert out["stopReason"].endswith(" If it wasn't stuck, run /loopbrake:mistake, then tell Claude to continue.")
    assert not of(home, "ask") and not of(home, "approve") and "by" not in of(home, "stop")[0]
