import json
import os
import statistics
import time

import pytest

import loopbrake
from loopbrake import brake as brake_mod


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "lb"
    monkeypatch.setenv("LOOPBRAKE_HOME", str(h))
    return h


def calibrate_by_hand(home, stop_line=5, n=20, alpha=0.05, project="demo", **extra):
    (home / "calibration").mkdir(parents=True, exist_ok=True)
    record = {"v": 1, "project": project, "method": "steps", "alpha": alpha, "n": n, "k": n,
              "stop_line": stop_line, "watch_only": stop_line is None, "source": {}, "created": "2026-10-01", "version": "0.1.0"} | extra
    (home / "calibration" / f"{project}.json").write_text(json.dumps(record))


def events(home):
    return [json.loads(l) for p in sorted((home / "runs").glob("*.jsonl")) for l in p.read_text().splitlines()]


def test_stops_after_the_stop_line_and_stays_stopped(home):
    calibrate_by_hand(home, stop_line=5, n=40)
    b = loopbrake.start(project="demo")
    got = [b.step(f"bash ls {i}", "out") for i in range(7)]
    assert [d.stop for d in got] == [False] * 5 + [True, True]
    assert got[5].step == 6 and not got[5].watch_only
    assert got[5].reason.startswith("stopped at step 6: past the stop line of 5 steps set from your 40 past successful runs (α 5%)")
    assert got[6].reason == got[5].reason


def test_reason_adds_the_signals_view(home):
    calibrate_by_hand(home, stop_line=5)
    b = loopbrake.start(project="demo")
    d = None
    for _ in range(6):
        d = b.step('bash {"command": "python run.py"}', "boom")
    assert d.stop and "; repeating in 5 of last 5 steps" in d.reason


def test_watch_only_never_stops(home):
    for setup in (lambda: None, lambda: calibrate_by_hand(home, stop_line=None)):
        setup()
        b = loopbrake.start(project="demo")
        assert b.watch_only and b.stop_line is None
        assert not any(b.step("bash ls", "x").stop for _ in range(300))
        assert b.step("bash ls").watch_only


def test_with_block_records_how_the_run_ended(home):
    calibrate_by_hand(home, stop_line=2)
    with loopbrake.start(project="demo", run="a") as b:
        for _ in range(3):
            if b.step("x").stop:
                break
    with loopbrake.start(project="demo", run="b") as b:
        b.step("x")
    with pytest.raises(KeyError):
        with loopbrake.start(project="demo", run="c") as b:
            b.step("x")
            raise KeyError("boom")
    ends = {e["run"]: e["status"] for e in events(home) if e["event"] == "run_end"}
    assert ends == {"a": "stopped", "b": "finished", "c": "interrupted"}


def test_recalibration_does_not_change_an_open_run(home):
    calibrate_by_hand(home, stop_line=5)
    b = loopbrake.start(project="demo")
    calibrate_by_hand(home, stop_line=1)
    assert b.stop_line == 5 and not b.step("x").stop and not b.step("x").stop


def test_events_written(home):
    calibrate_by_hand(home, stop_line=1)
    with loopbrake.start(project="demo", session="s", run="r") as b:
        b.step("a" * 500, "result text", tool="bash", tokens=12)
        b.step("b")
    ev = events(home)
    assert [e["event"] for e in ev] == ["run_start", "step", "step", "stop", "run_end"]
    assert ev[0]["calibration"]["stop_line"] == 1 and ev[0]["project"] == "demo"
    assert len(ev[1]["action_excerpt"]) == 200 and ev[1]["tool"] == "bash" and ev[1]["tokens"] == 12
    assert "result text" not in json.dumps(ev)  # results are never recorded
    assert ev[-1]["status"] == "stopped" and ev[-1]["steps"] == 2 and ev[-1]["tokens"] == 12


# ---------- never hurting the host (SC-005) ----------


def run_loop(project="demo", n=20):
    with loopbrake.start(project=project) as b:
        for i in range(n):
            if b.step(f"x {i}").stop:
                break
    return True


def test_damaged_calibration_means_watch_only(home):
    (home / "calibration").mkdir(parents=True)
    (home / "calibration" / "demo.json").write_text("{not json")
    with pytest.warns(RuntimeWarning):
        b = loopbrake.start(project="demo")
    assert b.watch_only
    with pytest.warns(RuntimeWarning):
        assert run_loop()


def test_unwritable_records_folder(home):
    calibrate_by_hand(home, stop_line=3)
    (home / "runs").mkdir(parents=True)
    os.chmod(home / "runs", 0o500)
    try:
        with pytest.warns(RuntimeWarning):
            assert run_loop()
    finally:
        os.chmod(home / "runs", 0o700)


def test_internal_error_falls_back_to_watch_only(home, monkeypatch):
    calibrate_by_hand(home, stop_line=3)

    def broken(*a, **k):
        raise RuntimeError("bug")

    monkeypatch.setattr(brake_mod, "_decide", broken)
    b = loopbrake.start(project="demo")
    with pytest.warns(RuntimeWarning):
        d = b.step("x")
    assert not d.stop and d.watch_only
    assert not any(b.step("x").stop for _ in range(10))


# ---------- speed (SC-003) ----------


def test_decisions_are_fast(home):
    calibrate_by_hand(home, stop_line=1000)
    times = []
    for _ in range(50):
        b = loopbrake.start(project="demo")
        for i in range(250):
            t0 = time.perf_counter()
            b.step(f'bash {{"command": "cmd {i % 7}"}}', "out\n" * 5)
            times.append(time.perf_counter() - t0)
    assert statistics.quantiles(times, n=20)[-1] < 0.010


# ---- picking up an open turn in a new process (Phase 3, research R5) ----

def turn_events(home, session="s"):
    return [json.loads(l) for l in (home / "runs" / f"{session}.jsonl").read_text().splitlines()]


def test_from_events_makes_the_same_decisions(home):
    calibrate_by_hand(home, stop_line=6)
    single = loopbrake.start(project="demo", session="one", run="one")
    expected = [single.step(f"bash {i}").stop for i in range(7)]

    first = loopbrake.start(project="demo", session="s", run="r1")
    for i in range(5):
        first.step(f"bash {i}")
    got = [False] * 5
    for i in (5, 6):  # each step in a new brake, as each hook call is a new process
        b = brake_mod.Brake.from_events("demo", "s", home, turn_events(home))
        got.append(b.step(f"bash {i}").stop)
    assert got == expected == [False] * 6 + [True]
    assert sum(e["event"] == "run_start" for e in turn_events(home)) == 1
    assert [e["step"] for e in turn_events(home) if e["event"] == "step"] == [1, 2, 3, 4, 5, 6, 7]


def test_call_id_is_recorded_on_step_and_stop(home):
    calibrate_by_hand(home, stop_line=1)
    b = loopbrake.start(project="demo", session="s", run="r1")
    b.step("bash a", call_id="t1")
    b.step("bash b", call_id="t2")
    b.step("bash c")
    ev = turn_events(home)
    assert [e.get("call_id") for e in ev if e["event"] == "step"] == ["t1", "t2", None]
    assert "call_id" not in [e for e in ev if e["event"] == "step"][2]
    assert [e["call_id"] for e in ev if e["event"] == "stop"] == ["t2"]


def test_an_already_braked_turn_keeps_saying_stop(home):
    calibrate_by_hand(home, stop_line=1)
    b = loopbrake.start(project="demo", session="s", run="r1")
    b.step("bash a")
    reason = b.step("bash b").reason
    again = brake_mod.Brake.from_events("demo", "s", home, turn_events(home)).step("bash c")
    assert again.stop and again.reason == reason and again.step == 3


def test_turns_wording(home):
    calibrate_by_hand(home, stop_line=1, n=40)
    b = loopbrake.start(project="demo", unit="turns")
    b.step("bash a")
    assert "past successful turns" in b.step("bash b").reason


# ---- Phase 4 record fields (specs/005-observability data-model) ----

TP = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def test_duration_and_traceparent_are_recorded(home):
    calibrate_by_hand(home, stop_line=None)
    b = loopbrake.start(project="demo", session="s", run="r1", traceparent=TP)
    b.step("bash a", duration_ms=68)
    b.step("bash b")
    ev = turn_events(home)
    assert ev[0]["traceparent"] == TP
    steps = [e for e in ev if e["event"] == "step"]
    assert steps[0]["duration_ms"] == 68 and "duration_ms" not in steps[1]
    assert brake_mod.Brake.from_events("demo", "s", home, ev).step("bash c").step == 3


def test_bad_traceparent_is_dropped(home):
    for bad in ("garbage", "00-" + "0" * 32 + "-00f067aa0ba902b7-01", "00-4bf92f3577b34da6a3ce929d0e0e4736-" + "0" * 16 + "-01", "ff-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"):
        loopbrake.start(project="demo", session=f"s{len(bad)}", run="r", traceparent=bad)
    assert not any("traceparent" in e for e in events(home))
