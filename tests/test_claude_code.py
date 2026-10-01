import json

import pytest

from loopbrake import claude_code, records


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOPBRAKE_HOME", str(tmp_path / "lb"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    return records.home()


# ---- project identity (research R6). Made-up paths only: real folder names never go in the repo ----

def test_history_folder(home, tmp_path):
    assert claude_code.history_folder("/home/me/my app?") == tmp_path / "claude" / "projects" / "-home-me-my-app-"


def test_project_name():
    assert claude_code.project_name("-home-me-my-app-") == "cc-home-me-my-app--c57a41"
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
    assert out["stopReason"].startswith("LoopBrake stopped at step 4: past the stop line of 3 steps set from your 19 past successful turns")
    assert out["stopReason"].endswith(". If this stop was wrong, run /loopbrake:mistake.")
    assert json.loads(hook(home, "tool", tool(5)))["continue"] is False  # a parallel call still in flight
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


# ---- the status line (US3, contracts/cli.md) ----

def line(home, session="s1"):
    return claude_code.statusline(json.dumps({"session_id": session, "transcript_path": "/x/y.jsonl", "model": {}}), home)


def snapshot(home):
    return {p: p.stat().st_mtime_ns for p in home.rglob("*")} if home.exists() else {}


def test_statusline_states(home):
    assert line(home) == "brake idle"
    calibrate(home, 3)
    hook(home, "prompt", payload())
    assert line(home) == "brake 0/3"
    for i in range(1, 4):
        hook(home, "tool", tool(i))
        assert line(home) == f"brake {i}/3"  # SC-007: the count follows every tool call
    hook(home, "tool", tool(4))
    assert line(home) == "brake stopped at 4"
    hook(home, "stop", payload())
    assert line(home) == "brake idle"
    hook(home, "prompt", payload(session="w", folder="-home-me-other-"))
    hook(home, "tool", tool(1, session_id="w", transcript_path=payload(session="w", folder="-home-me-other-")["transcript_path"]))
    assert line(home, "w") == "brake 1 (watching)"


def test_statusline_never_fails_or_writes(home):
    hook(home, "prompt", payload())
    before = snapshot(home)
    for bad in ("", "{bad", "[]", json.dumps({"session_id": "../x"}), json.dumps({"session_id": "nobody"})):
        assert claude_code.statusline(bad, home) == "brake idle"
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
