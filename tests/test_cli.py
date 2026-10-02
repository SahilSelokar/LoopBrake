import json
import os
import re
from pathlib import Path

import pytest

from loopbrake import __version__, cli, dashboard, otlp, records
from mimic_backends import Backend
from test_otlp import closed_port, task, write

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


def test_hook_prints_the_stop_and_always_exits_0(capsys, home, tmp_path, monkeypatch):
    import io
    from loopbrake import claude_code
    folder = "-home-me-demo-"
    project = claude_code.project_name(folder)
    (home / "calibration").mkdir(parents=True)
    (home / "calibration" / f"{project}.json").write_text(json.dumps(
        {"v": 1, "project": project, "method": "steps", "alpha": 0.05, "n": 19, "k": 19, "stop_line": 0,
         "watch_only": False, "source": {}, "created": "2026-10-01", "version": "0.2.0"}))
    data = {"session_id": "s1", "transcript_path": f"/x/projects/{folder}/s1.jsonl", "tool_name": "Bash",
            "tool_input": {"command": "ls"}, "tool_use_id": "t1"}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(data)))
    code, out, _ = run_cli(capsys, "hook", "tool")
    assert code == 0 and json.loads(out)["continue"] is False
    for args, stdin in ((["hook", "tool"], "{bad"), (["hook", "no-such-event"], "{}"), (["hook"], "")):
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        assert run_cli(capsys, *args)[:2] == (0, "")


# ---- Claude Code commands (Phase 3, contracts/cli.md) ----

def claude_project(tmp_path, monkeypatch, turns=19):
    """Work in a made-up folder whose Claude Code history has `turns` finished 2-step turns."""
    from loopbrake import claude_code
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    folder = claude_code.history_folder(work)
    folder.mkdir(parents=True)
    lines = []
    for i in range(turns):
        lines.append({"type": "user", "uuid": f"u{i}", "message": {"role": "user", "content": "hi"}})
        lines.append({"type": "assistant", "uuid": f"a{i}", "message": {"id": f"m{i}", "role": "assistant", "stop_reason": "tool_use",
                      "content": [{"type": "tool_use", "id": f"t{i}-{j}", "name": "Bash", "input": {}} for j in range(2)]}})
        lines.append({"type": "assistant", "uuid": f"e{i}", "message": {"id": f"me{i}", "role": "assistant", "stop_reason": "end_turn",
                      "content": [{"type": "text", "text": "done"}]}})
    (folder / "s.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n")
    return claude_code.project_name(folder.name)


def test_calibrate_and_status_for_claude_code(capsys, home, tmp_path, monkeypatch):
    project = claude_project(tmp_path, monkeypatch)
    code, out, _ = run_cli(capsys, "calibrate", "--claude-code")
    assert code == 0 and out.splitlines() == [
        "LoopBrake is set up for this project.",
        "It will stop a task that goes past 2 tool calls. That limit comes from your 19 past successful tasks here: "
        "fewer than 1 in 20 good tasks should go past it."]  # no line about earlier stops: there were none
    assert (home / "calibration" / f"{project}.json").exists()
    code, out, _ = run_cli(capsys, "status", "--claude-code")
    assert code == 0 and out.startswith("LoopBrake in this project:\n  Stop line: 2 tool calls per task (set ")
    assert "No tasks recorded here yet" in out and "α" not in out
    records.RunWriter(home / "runs" / "x.jsonl").write({"event": "run_start", "session": "x", "run": "r", "project": project, "calibration": {}})
    out = run_cli(capsys, "status", "--claude-code")[1]
    assert "No tasks recorded here yet" not in out and "  Tasks seen: 1 (the stop line was on for 0)" in out


def test_calibrate_argument_errors(capsys, home, tmp_path, monkeypatch):
    claude_project(tmp_path, monkeypatch)
    for args in (["calibrate"], ["calibrate", str(FIX), "--claude-code"], ["calibrate", "--claude-code", "--project", "x"],
                 ["status", "--claude-code", "--project", "x"]):
        code, _, err = run_cli(capsys, *args)
        assert code == 2 and err.startswith("loopbrake:"), args


def test_calibrate_claude_code_without_history(capsys, home, tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.chdir(tmp_path)
    code, _, err = run_cli(capsys, "calibrate", "--claude-code")
    assert code == 2 and "no Claude Code history for this folder at" in err


def test_feedback_last(capsys, home):
    assert run_cli(capsys, "feedback", "last", "--mistaken") == (1, "", "loopbrake: there's no stop to mark yet: LoopBrake hasn't stopped anything.\n")
    assert run_cli(capsys, "feedback", "last", "--exclude") == (1, "", "loopbrake: there's no finished task to leave out yet.\n")
    w = records.RunWriter(home / "runs" / "s.jsonl")
    w.write({"event": "run_start", "session": "s", "run": "a", "project": "cc-x", "calibration": {}})
    w.write({"event": "stop", "session": "s", "run": "a", "step": 39, "stop_line": 38, "reason": "r"})
    w.write({"event": "run_end", "session": "s", "run": "a", "status": "stopped", "steps": 39})
    w.write({"event": "run_start", "session": "s", "run": "b", "project": "cc-x", "calibration": {}})
    w.write({"event": "run_end", "session": "s", "run": "b", "status": "interrupted", "steps": 0})
    code, out, _ = run_cli(capsys, "feedback", "last", "--mistaken")
    assert code == 0 and out.startswith("Done: the stop after 39 tool calls is marked as a mistake.")
    assert run_cli(capsys, "feedback", "last", "--mistaken") == (1, "", "loopbrake: that one is already marked.\n")
    code, out, _ = run_cli(capsys, "feedback", "last", "--exclude")
    assert code == 0 and out.startswith("Done: your last finished task (39 tool calls) will be left out")


def test_watch_only_because_of_a_mistaken_stop(capsys, home, tmp_path, monkeypatch):
    project = claude_project(tmp_path, monkeypatch)  # 19 finished 2-step turns: just enough for a line
    w = records.RunWriter(home / "runs" / "live.jsonl")
    w.write({"event": "run_start", "session": "live", "run": "L", "project": project, "calibration": {}})
    w.write({"event": "step", "session": "live", "run": "L", "step": 1, "call_id": "t0-0"})
    w.write({"event": "stop", "session": "live", "run": "L", "step": 1, "call_id": "t0-0"})
    w.write({"event": "feedback", "session": "live", "run": "L", "verdict": "mistaken_stop"})
    code, out, _ = run_cli(capsys, "calibrate", "--claude-code")
    assert code == 0 and "LoopBrake found 19 successful past tasks in this project and needs 39." in out
    assert "Counted as long good tasks: 1 stop you marked as a mistake." in out
    assert "more than the usual 19 because each stop you marked as a mistake counts as a very long good task" in out
    assert "Left out:" not in out  # nothing to say about zero
    out = run_cli(capsys, "status", "--claude-code")[1]
    assert "only watching (19 successful past tasks found, 39 needed)" in out and "Tasks seen: 1 (the stop line was on for 0)" in out


# ---- Phase 4: dashboard and replay --record ----

def test_dashboard_command_prints_its_address_and_stops_cleanly(home, tmp_path):
    import os
    import signal
    import subprocess
    import sys
    env = os.environ | {"LOOPBRAKE_HOME": str(home), "PYTHONPATH": str(Path(cli.__file__).parents[1])}
    p = subprocess.Popen([sys.executable, "-m", "loopbrake.cli", "dashboard", "--no-open"], stdout=subprocess.PIPE, text=True, env=env)
    first = p.stdout.readline()
    second = p.stdout.readline()
    assert re.fullmatch(r"LoopBrake dashboard: http://127\.0\.0\.1:\d+/\?k=[A-Za-z0-9_-]{43}\n", first)
    assert second == "Only this computer can open it. Press Ctrl+C to stop.\n"
    p.send_signal(signal.SIGINT)
    assert p.wait(timeout=10) == 0


def test_dashboard_port_taken(capsys, home):
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    code, _, err = run_cli(capsys, "dashboard", "--no-open", "--port", str(s.getsockname()[1]))
    s.close()
    assert code == 2 and err.startswith("loopbrake: port") and "--port" in err


def test_replay_record_writes_tasks_for_the_dashboard(capsys, home):
    code, out, _ = run_cli(capsys, "replay", str(FIX), "--stop-line", "10", "--record")
    assert code == 0 and "runs 30, stopped 22" in out
    ev = [json.loads(l) for l in (home / "runs" / "replay-calibration_runs.jsonl").read_text().splitlines()]
    starts = [e for e in ev if e["event"] == "run_start"]
    assert len(starts) == 30 and {e["project"] for e in starts} == {"replay-calibration_runs"}
    assert sum(e["event"] == "stop" for e in ev) == 22 and sum(e["event"] == "run_end" for e in ev) == 30


def test_dashboard_in_the_background(capsys, home):
    """/loopbrake:dashboard runs this: it returns at once, reuses a running dashboard, and stops cleanly."""
    code, out, _ = run_cli(capsys, "dashboard", "--background", "--no-open")
    try:
        first = dashboard.running(home)
        assert code == 0 and first and f"LoopBrake dashboard: {first['url']}\n" in out and "/loopbrake:dashboard stop" in out
        assert oct((home / "dashboard.json").stat().st_mode & 0o777) == "0o600"  # the address holds the key
        assert run_cli(capsys, "dashboard", "--background", "--no-open")[0] == 0
        assert dashboard.running(home)["pid"] == first["pid"]  # the same one, not a second
    finally:
        code, out, _ = run_cli(capsys, "dashboard", "--stop")
    assert code == 0 and out == "Stopped the LoopBrake dashboard.\n"
    assert dashboard.running(home) is None and not (home / "dashboard.json").exists()
    assert run_cli(capsys, "dashboard", "--stop") == (0, "No LoopBrake dashboard is running.\n", "")


def test_export_command(capsys, home, monkeypatch):
    for k in list(os.environ):
        if k.startswith(("OTEL_", "LOOPBRAKE_EXPORT")):
            monkeypatch.delenv(k)
    assert run_cli(capsys, "export", "--pending") == (0, "export is off; set LOOPBRAKE_EXPORT=otlp to turn it on\n", "")
    backend = Backend()
    try:
        monkeypatch.setenv("LOOPBRAKE_EXPORT", "otlp")
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", backend.url)
        otlp.begin(home)
        write(home, "s1", task("a"))
        where = backend.url.removeprefix("http://")
        assert run_cli(capsys, "export", "--pending") == (0, f"sent 1 task (3 spans) to {where}\n", "")
        assert run_cli(capsys, "export", "--pending") == (0, "nothing new to send\n", "")
        assert run_cli(capsys, "export", "--test") == (0, f"test span accepted by {where}\n", "")
        write(home, "s1", task("b"))
        backend.replies.append((400, "bad request", {}))
        assert run_cli(capsys, "export", "--pending") == (1, "", f"loopbrake: {where} refused the data (HTTP 400): bad request\n")
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"http://127.0.0.1:{closed_port()}")
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
        code, out, err = run_cli(capsys, "export", "--pending")
        assert code == 1 and err.startswith(f"loopbrake: {otlp.WARNING}\nloopbrake: couldn't reach 127.0.0.1:")
        assert run_cli(capsys, "export", "--pending", "--quiet") == (1, "", "")
    finally:
        backend.close()


def test_codex_hook_entry_point(capsys, home, monkeypatch):
    import io
    from loopbrake import codex
    data = {"session_id": "s1", "turn_id": "t1", "transcript_path": "/x/r.jsonl", "cwd": "/home/someone/demo", "prompt": "hi"}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(data)))
    assert cli.main(["hook", "codex-prompt"]) == 0
    assert (home / "runs" / "s1.jsonl").exists()
    monkeypatch.setattr("sys.stdin", io.StringIO("{broken"))
    assert cli.main(["hook", "codex-tool"]) == 0 and capsys.readouterr().out == ""  # always exit 0, nothing printed
    assert codex.project_name("/home/someone/demo") in (home / "runs" / "s1.jsonl").read_text()
