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


# ---- Claude Code projects and recalibration after the brake was on (Phase 3, research R6, R10) ----

from loopbrake import claude_code, records

CWD = "/home/me/demo app"  # made up: real folder names never go in the repo


def history(tmp_path, monkeypatch, lengths):
    """A Claude Code history folder for CWD: one session, turn i has lengths[i] tool calls t{i}-{j}."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    folder = claude_code.history_folder(CWD)
    folder.mkdir(parents=True)
    lines = []
    for i, n in enumerate(lengths):
        lines.append({"type": "user", "uuid": f"u{i}", "message": {"role": "user", "content": f"secret prompt {i}"}})
        for j in range(n):
            lines.append({"type": "assistant", "uuid": f"a{i}-{j}", "message": {"id": f"m{i}-{j}", "role": "assistant", "stop_reason": "tool_use",
                          "content": [{"type": "tool_use", "id": f"t{i}-{j}", "name": "Bash", "input": {"command": f"secret {j}"}}]}})
            lines.append({"type": "user", "uuid": f"r{i}-{j}", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{i}-{j}", "content": "x"}]}})
        lines.append({"type": "assistant", "uuid": f"e{i}", "message": {"id": f"me{i}", "role": "assistant", "stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}]}})
    (folder / "s1.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n")
    return folder


def live_turn(home, turn, length, stopped=False, verdicts=()):
    """The run log of a live turn that covered transcript turn `turn`, as the hooks write it."""
    project = claude_code.project_name(claude_code.history_folder(CWD).name)
    w = records.RunWriter(home / "runs" / f"live-{turn}.jsonl")
    w.write({"event": "run_start", "session": f"live-{turn}", "run": f"L{turn}", "project": project, "calibration": {}})
    for j in range(length):
        w.write({"event": "step", "session": f"live-{turn}", "run": f"L{turn}", "step": j + 1, "call_id": f"t{turn}-{j}"})
    if stopped:
        w.write({"event": "stop", "session": f"live-{turn}", "run": f"L{turn}", "step": length, "call_id": f"t{turn}-{length - 1}"})
    for v in verdicts:
        w.write({"event": "feedback", "session": f"live-{turn}", "run": f"L{turn}", "verdict": v})


def test_claude_code_project_needs_19_turns(tmp_path, home, monkeypatch):
    history(tmp_path, monkeypatch, [3] * 18)
    rec = claude_code.calibrate_claude_code(CWD)
    assert rec["watch_only"] and rec["project"] == claude_code.project_name("-home-me-demo-app")
    (claude_code.history_folder(CWD) / "s2.jsonl").write_text(json.dumps({"type": "user", "uuid": "z", "message": {"role": "user", "content": "hi"}}) + "\n"
        + json.dumps({"type": "assistant", "uuid": "za", "message": {"id": "zm", "role": "assistant", "stop_reason": "tool_use", "content": [{"type": "tool_use", "id": "zt", "name": "Bash", "input": {}}]}}) + "\n")
    rec = claude_code.calibrate_claude_code(CWD)
    assert rec["n"] == 19 and rec["stop_line"] == 3
    assert "secret" not in json.dumps(rec)


def test_missing_history_names_the_path(tmp_path, home, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    with pytest.raises(FileNotFoundError, match="-home-me-nowhere"):
        claude_code.calibrate_claude_code("/home/me/nowhere")


@pytest.mark.parametrize("case, expected_line, counts", [
    ("none", 39, (0, 0)),                     # lengths 1..40, n 40, k 39
    ("stopped", 38, (1, 0)),                  # the 40-step turn was stopped: left out as stuck
    ("excluded", 38, (1, 0)),                 # the user excluded it: left out
    ("mistaken", 40, (0, 1)),                 # the 1-step turn was a mistaken stop: counts as longer than any line
    ("mistaken+excluded", 40, (0, 1)),        # both: the cautious side, mistaken
])
def test_recalibration_after_the_brake_was_on(tmp_path, home, monkeypatch, case, expected_line, counts):
    history(tmp_path, monkeypatch, list(range(1, 41)))
    if case in ("stopped", "excluded"):
        live_turn(home, 39, 40, stopped=case == "stopped", verdicts=["exclude"] if case == "excluded" else [])
    if case.startswith("mistaken"):
        live_turn(home, 0, 1, stopped=True, verdicts=["mistaken_stop"] + (["exclude"] if "excluded" in case else []))
    rec = claude_code.calibrate_claude_code(CWD)
    assert rec["stop_line"] == expected_line
    assert (rec["source"]["stops_left_out"], rec["source"]["mistakes_counted"]) == counts


def test_runs_needed_counts_mistaken_stops_as_taking_the_top_places():
    assert calibration.runs_needed(0.05) == 19
    assert calibration.runs_needed(0.05, unbounded=1) == 39  # ceil(0.95 * 40) = 38 = 39 - 1
