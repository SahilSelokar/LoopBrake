import json
import os
import stat

import pytest

from loopbrake import records


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOPBRAKE_HOME", str(tmp_path / "lb"))
    return records.home()


def test_home_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOPBRAKE_HOME", str(tmp_path / "x"))
    assert records.home() == tmp_path / "x"
    monkeypatch.delenv("LOOPBRAKE_HOME")
    assert records.home() == records.Path.home() / ".loopbrake"


def test_project_names():
    assert records.valid_project("my-agent_1.v2")
    for bad in ("../x", "", "a" * 65, "a/b", "..", None):
        assert not records.valid_project(bad)


def test_one_event_per_line_private_file(home):
    w = records.RunWriter(home / "runs" / "s1.jsonl")
    w.write({"event": "run_start", "session": "s1", "run": "r1"})
    w.write({"event": "run_end", "session": "s1", "run": "r1", "status": "finished"})
    lines = (home / "runs" / "s1.jsonl").read_text().splitlines()
    first = json.loads(lines[0])
    assert len(lines) == 2 and first["v"] == 1 and "ts" in first and first["event"] == "run_start"
    assert stat.S_IMODE(os.stat(home / "runs" / "s1.jsonl").st_mode) == 0o600


def test_failed_write_turns_recording_off(home):
    (home / "runs").mkdir(parents=True)
    os.chmod(home / "runs", 0o500)  # read-only folder
    try:
        w = records.RunWriter(home / "runs" / "s1.jsonl")
        with pytest.warns(RuntimeWarning):
            w.write({"event": "run_start", "session": "s1", "run": "r1"})
        assert w.on is False
        w.write({"event": "step", "session": "s1", "run": "r1"})  # silently ignored, never raises
    finally:
        os.chmod(home / "runs", 0o700)


def start(w, run, watch_only=False, alpha=0.05, project="p"):
    w.write({"event": "run_start", "session": "s", "run": run, "project": project,
             "calibration": {"method": "steps", "alpha": alpha, "n": 20, "k": 20, "stop_line": None if watch_only else 9, "watch_only": watch_only}})


def test_status_counts(home):
    w = records.RunWriter(home / "runs" / "s.jsonl")
    for i in range(20):
        start(w, f"r{i}")
    start(w, "w0", watch_only=True)
    for i in range(3):
        w.write({"event": "stop", "session": "s", "run": f"r{i}", "step": 10, "stop_line": 9, "reason": "x"})
    records.add_feedback(home, "r0", "mistaken_stop")
    st = records.status(home)
    assert (st["runs"], st["watched"], st["stopped"], st["mistaken"]) == (21, 20, 3, 1)
    assert st["allowance"] == pytest.approx(1.0)
    assert records.status(home, project="other")["runs"] == 0


def test_feedback_and_exclude(home):
    w = records.RunWriter(home / "runs" / "s.jsonl")
    start(w, "r1")
    records.add_feedback(home, "r1", "exclude")
    assert "r1" in records.read_exclude(home)
    events = [json.loads(l) for l in (home / "runs" / "s.jsonl").read_text().splitlines()]
    assert events[-1]["event"] == "feedback" and events[-1]["verdict"] == "exclude"
    with pytest.raises(LookupError):
        records.add_feedback(home, "nope", "mistaken_stop")
    with pytest.raises(ValueError):
        records.add_feedback(home, "r1", "maybe")


# ---- session logs as live state (Phase 3, research R4) ----

LOCKED_APPEND = """
import sys, time
from pathlib import Path
from loopbrake import records
h = Path(sys.argv[1])
with records.session_lock(h, "s"):
    p = h / "runs" / "s.jsonl"
    n = len(p.read_text().splitlines())
    time.sleep(0.02)
    with open(p, "a") as f:
        f.write(f"{n}\\n")
"""


def test_session_lock_serializes_processes(home):
    import subprocess
    import sys
    from pathlib import Path
    env = os.environ | {"PYTHONPATH": str(Path(records.__file__).parents[1])}
    procs = [subprocess.Popen([sys.executable, "-c", LOCKED_APPEND, str(home)], env=env) for _ in range(8)]
    assert all(p.wait(timeout=30) == 0 for p in procs)
    path = home / "runs" / "s.jsonl"
    assert sorted(int(x) for x in path.read_text().split()) == list(range(8))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def ev(event, run, **fields):
    return {"v": 1, "ts": "2026-10-01T00:00:00+00:00", "event": event, "session": "s", "run": run} | fields


def test_open_turn():
    a, s1, end_a = ev("run_start", "a"), ev("step", "a", step=1), ev("run_end", "a", status="finished", steps=1)
    b, s2 = ev("run_start", "b"), ev("step", "b", step=1)
    assert records.open_turn([]) is None
    assert records.open_turn([a, s1, end_a]) is None
    assert records.open_turn([a, s1]) == [a, s1]
    assert records.open_turn([a, s1, end_a, b, s2]) == [b, s2]


def test_session_events_reads_from_the_last_start(home):
    path = home / "runs" / "s.jsonl"
    path.parent.mkdir(parents=True)
    lines = [ev("run_start", "a"), ev("run_end", "a", status="finished", steps=0), ev("run_start", "b"), ev("step", "b", step=1)]
    path.write_text("\n".join(json.dumps(e) for e in lines[:3]) + "\n{not json\n" + json.dumps(lines[3]) + "\n")
    assert records.session_events(home, "s") == [lines[2], lines[3]]
    assert records.session_events(home, "missing") == []


def test_last_run(home):
    w = records.RunWriter(home / "runs" / "s1.jsonl")
    w.write(ev("run_start", "a", project="p1"))
    w.write(ev("stop", "a", step=4, stop_line=3, reason="r"))
    w.write(ev("run_end", "a", status="stopped", steps=4))
    w2 = records.RunWriter(home / "runs" / "s2.jsonl")
    w2.write(ev("run_start", "b", project="p2") | {"session": "s2"})
    w2.write(ev("run_end", "b", status="interrupted", steps=0) | {"session": "s2"})
    start, stop = records.last_run(home, "stop")
    assert (start["run"], start["project"], stop["step"]) == ("a", "p1", 4)
    assert records.last_run(home, "run_end")[0]["run"] == "b"
    assert records.last_run(home, "run_end", min_steps=1)[0]["run"] == "a"
    assert records.last_run(records.home(home / "empty"), "stop") is None
