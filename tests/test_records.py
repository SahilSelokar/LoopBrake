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
