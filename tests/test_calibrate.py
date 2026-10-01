import json
import shutil
from pathlib import Path

import pytest

import loopbrake
from loopbrake import calibration
from loopbrake.conformal import rank, threshold
from loopbrake.signals import Step
from loopbrake.traces import Run, write_runs

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOPBRAKE_HOME", str(tmp_path / "lb"))
    return tmp_path / "lb"


def run(rid, task, length, success=True):
    return Run("g", "d", task, rid, success, None, True, tuple(Step(f"secret action {i}", "secret output", None, 1) for i in range(length)))


def runs_file(tmp_path, runs):
    p = tmp_path / "runs.jsonl"
    write_runs(p, runs)
    return p


def test_one_run_per_task_and_the_rule(tmp_path, home):
    runs = [run(f"r{i:02d}", f"t{i}", 10 + i) for i in range(30)]
    runs += [run("r00b", "t0", 99), run("x1", "tz", 500, success=False)]  # a repeat of t0 is ignored
    rec = loopbrake.calibrate(runs_file(tmp_path, runs), project="demo")
    lengths = [10 + i for i in range(30)]
    assert (rec["n"], rec["k"], rec["stop_line"]) == (30, rank(30, 0.05), threshold(lengths, 0.05))
    assert rec["method"] == "steps" and rec["source"]["kind"] == "runs-file" and rec["watch_only"] is False
    assert calibration.load("demo", home) == rec


def test_19_tasks_give_the_max_18_give_watch_only(tmp_path, home):
    rec = loopbrake.calibrate(runs_file(tmp_path, [run(f"r{i:02d}", f"t{i}", i + 1) for i in range(19)]))
    assert rec["stop_line"] == 19
    rec = loopbrake.calibrate(runs_file(tmp_path, [run(f"r{i:02d}", f"t{i}", i + 1) for i in range(18)]))
    assert rec["watch_only"] is True and rec["stop_line"] is None
    assert calibration.runs_needed(0.05) == 19


def test_excluded_runs_are_skipped(tmp_path, home):
    home.mkdir(parents=True)
    (home / "exclude.txt").write_text("r05\n")
    rec = loopbrake.calibrate(runs_file(tmp_path, [run(f"r{i:02d}", f"t{i}", 1 + i) for i in range(25)]))
    assert rec["n"] == 24 and rec["source"]["excluded"] == 1


def test_claude_code_folder(tmp_path, home):
    folder = tmp_path / "project"
    folder.mkdir()
    shutil.copy(FIX / "claude_code_session.jsonl", folder / "s1.jsonl")
    rec = loopbrake.calibrate(folder, project="cc")
    assert rec["source"]["kind"] == "claude-code" and rec["source"]["runs_seen"] == 2
    assert rec["n"] == 1 and rec["watch_only"] is True  # one successful turn: far too few


def test_record_holds_no_source_text(tmp_path, home):
    src = runs_file(tmp_path, [run(f"r{i:02d}", f"t{i}", 5) for i in range(20)])
    rec = loopbrake.calibrate(src)
    text = json.dumps(rec)
    assert "secret" not in text
    assert all(len(v) <= 64 for v in rec["source"].values() if isinstance(v, str))
    import hashlib
    assert rec["source"]["sha256"] == hashlib.sha256(src.read_bytes()).hexdigest()


def test_bad_inputs(tmp_path, home):
    with pytest.raises(FileNotFoundError):
        loopbrake.calibrate(tmp_path / "missing.jsonl")
    with pytest.raises(ValueError):
        loopbrake.calibrate(runs_file(tmp_path, [run("a", "t", 1)]), project="../escape")
