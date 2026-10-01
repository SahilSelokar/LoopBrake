import json
import re
from pathlib import Path

import pytest

from loopbrake import __version__, cli, records

FIX = Path(__file__).parent / "fixtures" / "calibration_runs.jsonl"
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOPBRAKE_HOME", str(tmp_path / "lb"))
    return tmp_path / "lb"


def run_cli(capsys, *args):
    code = cli.main(list(args))
    out = capsys.readouterr()
    assert not EMOJI.search(out.out + out.err)
    return code, out.out, out.err


def test_version(capsys, home):
    assert run_cli(capsys, "--version") == (0, f"loopbrake {__version__}\n", "")


def test_calibrate(capsys, home, tmp_path):
    code, out, _ = run_cli(capsys, "calibrate", str(FIX), "--project", "demo")
    assert code == 0 and "stop line: 27 steps" in out and "25 successful runs" in out
    small = tmp_path / "small.jsonl"
    small.write_text("\n".join(FIX.read_text().splitlines()[:10]) + "\n")
    code, out, _ = run_cli(capsys, "calibrate", str(small), "--project", "small")
    assert code == 0 and "watch-only" in out and "need 9 more" in out
    code, _, err = run_cli(capsys, "calibrate", str(tmp_path / "missing.jsonl"))
    assert code == 2 and "loopbrake:" in err and "Traceback" not in err


def write_events(home):
    w = records.RunWriter(home / "runs" / "s.jsonl")
    for i in range(20):
        w.write({"event": "run_start", "session": "s", "run": f"r{i}", "project": "demo",
                 "calibration": {"method": "steps", "alpha": 0.05, "n": 25, "k": 25, "stop_line": 27, "watch_only": False}})
    for i in range(3):
        w.write({"event": "stop", "session": "s", "run": f"r{i}", "step": 28, "stop_line": 27, "reason": "x"})


def test_status_and_feedback(capsys, home):
    run_cli(capsys, "calibrate", str(FIX), "--project", "demo")
    write_events(home)
    assert run_cli(capsys, "feedback", "r0", "--mistaken")[0] == 0
    code, out, _ = run_cli(capsys, "status", "--project", "demo")
    assert code == 0 and "stop line: 27 steps" in out
    assert "runs watched: 20" in out and "runs stopped: 3" in out and "mistaken stops: 1 of an allowance of 1.0" in out
    assert run_cli(capsys, "feedback", "r1", "--exclude")[0] == 0 and "r1" in records.read_exclude(home)
    assert run_cli(capsys, "feedback", "nope", "--mistaken")[0] == 1


def test_replay_writes_no_records(capsys, home):
    code, out, _ = run_cli(capsys, "replay", str(FIX), "--stop-line", "10")
    assert code == 0
    lines = out.splitlines()
    assert any(l.startswith("run-15\t") and "stop at 11" in l for l in lines)
    assert any(l.startswith("run-02\t") and l.split("\t")[1] == "-" for l in lines)
    assert "runs 30, stopped 22 (17 successful, 5 failed)" in out
    assert not (home / "runs").exists()
