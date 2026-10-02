"""Export to OpenTelemetry tools (specs/005-observability/contracts/otlp.md, research R7 and R8)."""
import hashlib
import json
import os
import socket
import statistics
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from loopbrake import claude_code, otlp, records
from loopbrake.brake import start
from mimic_backends import Backend, otlp_problems

PROJECT = "cc-Users-someone-private-folder-1a2b3c"  # made up, and it must never leave without opt-in
BASE = datetime(2026, 10, 2, 5, 0, tzinfo=timezone.utc)
TP = "00-" + "ab" * 16 + "-" + "cd" * 8 + "-01"


def ts(seconds):
    return (BASE + timedelta(seconds=seconds)).isoformat(timespec="milliseconds")


def write(home, session, events):
    w = records.RunWriter(home / "runs" / f"{session}.jsonl")
    for e in events:
        w.write({"session": session} | e)


def start_event(run, t0=0, traceparent=None, project=PROJECT, export=True):
    cal = {"method": "steps", "alpha": 0.05, "n": 19, "k": 19, "stop_line": 3, "watch_only": False}
    return {"event": "run_start", "run": run, "project": project, "calibration": cal, "ts": ts(t0)} | (
        {"traceparent": traceparent} if traceparent else {}) | ({"export": True} if export else {})


def step_event(run, i, t0=0, tokens=None):
    return {"event": "step", "run": run, "step": i, "tool": "Bash", "action_excerpt": f'Bash {{"command": "secret-cmd-{run}-{i}"}}',
            "tokens": tokens, "error": i == 2, "call_id": f"toolu_{run}_{i}", "ts": ts(t0 + i)} | (
        {"duration_ms": 250} if i > 1 else {})


def task(run, calls=2, stop_at=None, end="finished", t0=0, traceparent=None, after_stop=0, tokens=None):
    ev = [start_event(run, t0, traceparent)] + [step_event(run, i, t0, tokens) for i in range(1, calls + 1)]
    if stop_at:
        ev.append({"event": "stop", "run": run, "step": stop_at, "stop_line": 3, "ts": ts(t0 + calls + 0.5),
                   "reason": f"stopped at step {stop_at}: past the stop line of 3 steps; repeating in 3 of last 3 steps"})
        ev += [step_event(run, calls + i, t0) for i in range(1, after_stop + 1)]
    if end:
        ev.append({"event": "run_end", "run": run, "status": end, "steps": calls, "tokens": None, "ts": ts(t0 + calls + 1)})
    return ev


def spans(backend):
    return [sp for b in backend.bodies("/v1/traces") for r in b["resourceSpans"] for ss in r["scopeSpans"] for sp in ss["spans"]]


def attrs(item):
    return {a["key"]: next(iter(a["value"].values())) for a in item.get("attributes", [])}


def metrics(backend):
    return {m["name"]: m for b in backend.bodies("/v1/metrics") for r in b["resourceMetrics"] for s in r["scopeMetrics"]
            for m in s["metrics"]}


def closed_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def lb(tmp_path, monkeypatch):
    for k in list(os.environ):
        if k.startswith(("OTEL_", "LOOPBRAKE_EXPORT")) or k == "TRACEPARENT":
            monkeypatch.delenv(k)
    monkeypatch.setenv("LOOPBRAKE_HOME", str(tmp_path / "lb"))
    monkeypatch.setenv("LOOPBRAKE_EXPORT", "otlp")
    backend = Backend()
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", backend.url)
    yield records.home(), backend
    backend.close()


# ---- settings ----

def test_off_unless_turned_on(lb, monkeypatch):
    home, backend = lb
    monkeypatch.delenv("LOOPBRAKE_EXPORT")  # only OTEL_EXPORTER_OTLP_ENDPOINT is set
    write(home, "s1", task("a"))
    otlp.begin(home)
    assert otlp.export_pending() is None and otlp.test_connection() is None and otlp.spawn_pending() is False
    assert not (home / "export" / "state.json").exists() and backend.requests == []


def test_settings(monkeypatch):
    for k in list(os.environ):
        if k.startswith("OTEL_"):
            monkeypatch.delenv(k)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318/")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "a=1, b = x%20y,broken")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_HEADERS", "a=2")
    s = otlp.settings()
    assert (s["traces"], s["metrics"]) == ("http://otel-collector:4318/v1/traces", "http://otel-collector:4318/v1/metrics")
    assert s["traces_headers"] == {"a": "2", "b": "x y"} and s["metrics_headers"] == {"a": "1", "b": "x y"}
    assert s["warning"] is None and not s["cumulative"] and not s["content"] and otlp.host(s["traces"]) == "otel-collector:4318"
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "https://cloud.example/api/public/otel/v1/traces")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "none")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
    s = otlp.settings()
    assert s["traces"] == "https://cloud.example/api/public/otel/v1/traces" and s["metrics"] is None
    assert s["warning"] == otlp.WARNING


# ---- mapping ----

def test_spans(lb):
    home, backend = lb
    otlp.begin(home)
    write(home, "s1", task("stp", calls=4, stop_at=4, traceparent=TP, after_stop=1))
    write(home, "s1", task("fin", t0=100))
    r = otlp.export_pending()
    assert r["ok"] and r["tasks"] == 2 and r["spans"] == (1 + 4) + (1 + 2)
    assert all(status == 200 for *_, status in backend.requests)
    got = spans(backend)
    by_run = lambda run: [s for s in got if s["traceId"] == (("ab" * 16) if run == "stp" else hashlib.sha256(f"s1/{run}".encode()).hexdigest()[:32])]
    stp, fin = by_run("stp"), by_run("fin")
    task_span = stp[0]
    assert task_span["name"] == "invoke_agent claude-code" and task_span["kind"] == 1 and task_span["parentSpanId"] == "cd" * 8
    assert task_span["status"] == {"code": 2, "message": "stopped by LoopBrake"}
    a = attrs(task_span)
    assert a["gen_ai.operation.name"] == "invoke_agent" and a["gen_ai.agent.name"] == "claude-code"
    assert a["gen_ai.conversation.id"] == "s1" and a["error.type"] == "loopbrake.stopped"
    assert a["loopbrake.project_id"] == hashlib.sha256(PROJECT.encode()).hexdigest()[:12]
    assert (a["loopbrake.limit"], a["loopbrake.calibration.n"], a["loopbrake.tool_calls"], a["loopbrake.status"]) == ("3", "19", "4", "stopped")
    assert a["loopbrake.alpha"] == 0.05
    stop = task_span["events"][0]
    assert stop["name"] == "loopbrake.stop" and attrs(stop) == {"loopbrake.step": "4", "loopbrake.limit": "3",
                                                                 "loopbrake.reason_code": "past_limit,repeating"}
    calls = stp[1:]
    assert len(calls) == 4  # the call that landed after the stop isn't sent
    assert {c["parentSpanId"] for c in calls} == {task_span["spanId"]} and {c["name"] for c in calls} == {"execute_tool Bash"}
    one, two = calls[0], calls[1]
    assert attrs(two)["gen_ai.tool.name"] == "Bash" and attrs(two)["gen_ai.tool.call.id"] == "toolu_stp_2"
    assert attrs(two)["loopbrake.failed"] is True and attrs(one)["loopbrake.failed"] is False
    assert int(two["endTimeUnixNano"]) - int(two["startTimeUnixNano"]) == 250 * 10**6  # duration_ms before its time
    assert one["startTimeUnixNano"] == task_span["startTimeUnixNano"]  # no duration: from the previous event
    assert task_span["endTimeUnixNano"] == stop["timeUnixNano"]  # final at the stop
    assert "parentSpanId" not in fin[0] and fin[0]["status"] == {"code": 0} and attrs(fin[0])["loopbrake.status"] == "finished"
    every = json.dumps(backend.bodies("/v1/traces"))
    assert "gen_ai.system" not in every and "gen_ai.provider.name" not in every
    assert not any(otlp_problems(b) for b in backend.bodies("/v1/traces") + backend.bodies("/v1/metrics"))
    tasks = otlp.finished_tasks(home, {"offsets": {}})[0]
    assert otlp.build_traces(tasks, otlp.settings()) == otlp.build_traces(tasks, otlp.settings())  # same task, same ids


def test_content_only_with_opt_in(lb, monkeypatch):
    home, backend = lb
    otlp.begin(home)
    write(home, "s1", task("a", calls=4, stop_at=4))
    assert otlp.export_pending()["ok"]
    sent = json.dumps([b for _, _, b, _ in backend.requests])
    for private in ("secret-cmd", "private-folder", PROJECT, "LoopBrake stopped this task"):
        assert private not in sent, private
    assert hashlib.sha256(PROJECT.encode()).hexdigest()[:12] in sent
    monkeypatch.setenv("LOOPBRAKE_EXPORT_CONTENT", "1")
    write(home, "s2", task("b", calls=4, stop_at=4))
    assert otlp.export_pending()["ok"]
    got = [s for s in spans(backend) if s["traceId"] == hashlib.sha256(b"s2/b").hexdigest()[:32]]
    assert attrs(got[0])["loopbrake.project"] == PROJECT
    assert attrs(got[0]["events"][0])["loopbrake.reason"].startswith("LoopBrake stopped this task after 4 tool calls.")
    assert attrs(got[1])["loopbrake.action"] == 'Bash {"command": "secret-cmd-b-1"}'
    points = metrics(backend)["loopbrake.tasks"]["sum"]["dataPoints"]
    assert attrs(points[-1])["loopbrake.project"] == PROJECT


# ---- which tasks, and when (research R7) ----

def test_only_finished_tasks_started_after_the_starting_point(lb):
    home, backend = lb
    write(home, "s1", [start_event("old"), step_event("old", 1)])  # running when export is turned on
    otlp.begin(home)
    write(home, "s1", [step_event("old", 2), {"event": "run_end", "run": "old", "status": "finished", "ts": ts(5)}])
    write(home, "s1", task("new", t0=10))
    write(home, "s2", task("stopped", calls=4, stop_at=4, end=None))  # no run_end yet
    write(home, "s3", [start_event("open"), step_event("open", 1)])
    assert otlp.export_pending()["tasks"] == 2
    sent = {attrs(s)["gen_ai.conversation.id"] for s in spans(backend) if s["name"].startswith("invoke_agent")}
    assert sent == {"s1", "s2"} and len([s for s in spans(backend) if s["name"].startswith("invoke_agent")]) == 2
    write(home, "s2", [step_event("stopped", 5), {"event": "run_end", "run": "stopped", "status": "stopped", "ts": ts(9)}])
    write(home, "s3", [{"event": "run_end", "run": "open", "status": "finished", "ts": ts(9)}])
    r = otlp.export_pending()
    assert r["tasks"] == 1  # the open one, once it ended; the stopped one isn't sent again
    assert len([s for s in spans(backend) if s["name"].startswith("invoke_agent")]) == 3
    assert otlp.export_pending()["tasks"] == 0


def test_tasks_run_with_export_off_are_never_sent(lb, monkeypatch):
    home, backend = lb
    otlp.begin(home)
    monkeypatch.delenv("LOOPBRAKE_EXPORT")  # the agent runs a task with export off...
    with start(PROJECT, session="s1", home=home) as b:
        b.step("Bash echo hi")
    monkeypatch.setenv("LOOPBRAKE_EXPORT", "otlp")  # ...then export is on again
    monkeypatch.setattr(otlp, "spawn_pending", lambda home=None: False)
    with start(PROJECT, session="s1", home=home) as b:
        b.step("Bash echo hi")
    starts = [e for e in records.read_events(home) if e["event"] == "run_start"]
    assert [e.get("export") for e in starts] == [None, True]
    assert otlp.export_pending()["tasks"] == 1
    assert [attrs(s)["loopbrake.tool_calls"] for s in spans(backend) if s["name"].startswith("invoke_agent")] == ["1"]


# ---- counters ----

def test_metrics_delta_by_default_then_cumulative(lb, monkeypatch):
    home, backend = lb
    otlp.begin(home)
    started = otlp.load_state(home)["started"]
    write(home, "s1", task("a", tokens=100))
    write(home, "s1", task("b", calls=4, stop_at=4, t0=10))
    assert otlp.export_pending()["ok"]
    m = metrics(backend)
    assert set(m) == {"loopbrake.tasks", "loopbrake.stops", "loopbrake.tokens.spent"}  # no mistakes yet, so no points
    for name, value in (("loopbrake.tasks", "2"), ("loopbrake.stops", "1"), ("loopbrake.tokens.spent", "200")):
        s = m[name]["sum"]
        assert s["aggregationTemporality"] == 1 and s["isMonotonic"] is True and s["dataPoints"][0]["asInt"] == value
        assert s["dataPoints"][0]["startTimeUnixNano"] == str(otlp._ns(started))
    assert m["loopbrake.tasks"]["unit"] == "{task}"
    first_send = otlp.load_state(home)["sent_at"]
    write(home, "s1", [{"event": "feedback", "run": "b", "verdict": "mistaken_stop", "ts": ts(30)}])
    assert otlp.export_pending()["ok"]
    point = metrics(backend)["loopbrake.mistaken_stops"]["sum"]["dataPoints"][0]
    assert point["asInt"] == "1" and point["startTimeUnixNano"] == str(otlp._ns(first_send))
    assert attrs(point) == {"loopbrake.project_id": otlp.project_id(PROJECT)}
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE", "cumulative")
    write(home, "s1", task("c", t0=40))
    assert otlp.export_pending()["ok"]
    s = metrics(backend)["loopbrake.tasks"]["sum"]
    assert s["aggregationTemporality"] == 2 and s["dataPoints"][0]["asInt"] == "3"
    assert s["dataPoints"][0]["startTimeUnixNano"] == str(otlp._ns(started))
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE", "lowmemory")
    assert otlp.settings()["cumulative"] is False


# ---- state ----

def test_first_run_starts_from_here(lb):
    home, backend = lb
    write(home, "s1", task("before"))
    assert otlp.export_pending() == {"ok": True, "tasks": 0, "spans": 0}
    state = otlp.load_state(home)
    assert state["offsets"]["s1.jsonl"] == {"at": (home / "runs" / "s1.jsonl").stat().st_size, "open": []}
    assert backend.requests == [] and otlp.export_pending()["tasks"] == 0


def test_offsets_move_only_after_success(lb):
    home, backend = lb
    otlp.begin(home)
    write(home, "s1", task("a"))
    before = otlp.load_state(home)["offsets"]
    backend.replies.append((500, "down for maintenance", {}))
    r = otlp.export_pending()
    assert not r["ok"] and r["status"] == 500 and r["message"] == "down for maintenance"
    state = otlp.load_state(home)
    assert state["offsets"] == before and state["last"]["ok"] is False
    assert otlp.export_pending()["ok"] and otlp.load_state(home)["offsets"] != before
    assert otlp.export_pending()["tasks"] == 0


def test_two_exporters_at_once_send_each_task_once(lb):
    home, backend = lb
    otlp.begin(home)
    for i in range(6):
        write(home, f"s{i}", task(f"t{i}"))
    threads = [threading.Thread(target=otlp.export_pending) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ids = [s["traceId"] for s in spans(backend) if s["name"].startswith("invoke_agent")]
    assert len(ids) == 6 and len(set(ids)) == 6


# ---- replies (contracts/otlp.md, "Responses") ----

def test_partial_success_moves_on_and_is_recorded(lb):
    home, backend = lb
    otlp.begin(home)
    write(home, "s1", task("a"))
    backend.replies.append((200, {"partialSuccess": {"rejectedSpans": "2", "errorMessage": "span too old"}}, {}))
    r = otlp.export_pending()
    assert not r["ok"] and r["rejected"] == 2 and r["message"] == "span too old"
    assert otlp.export_pending()["tasks"] == 0  # never retried


def test_retry_once_after_retry_after_then_give_up(lb):
    home, backend = lb
    otlp.begin(home)
    write(home, "s1", task("a"))
    backend.replies += [(429, "slow down", {"Retry-After": "1"}), (429, "slow down", {"Retry-After": "1"})]
    began = time.monotonic()
    r = otlp.export_pending()
    assert not r["ok"] and r["status"] == 429 and len(backend.requests) == 2 and time.monotonic() - began >= 1
    backend.requests.clear()
    backend.replies.append((400, "bad request", {}))
    assert otlp.export_pending()["status"] == 400 and len(backend.requests) == 1  # never retried


def test_unreachable_is_recorded_without_secrets(lb, monkeypatch):
    home, backend = lb
    otlp.begin(home)
    write(home, "s1", task("a"))
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"http://127.0.0.1:{closed_port()}")
    r = otlp.export_pending()
    assert not r["ok"] and r["status"] is None and r["message"]
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", backend.url)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "x-api-key=supersecret123,Authorization=Basic%20dXNlcjpwYXNzd29yZA==")
    backend.replies.append((401, "bad key supersecret123 (Basic dXNlcjpwYXNzd29yZA==)", {}))
    r = otlp.export_pending()
    assert r["status"] == 401 and "supersecret123" not in r["message"] and "dXNlcjpwYXNzd29yZA" not in r["message"]
    saved = (home / "export" / "state.json").read_text()
    assert "supersecret123" not in saved and "dXNlcjpwYXNzd29yZA" not in saved


# ---- starting it in the background ----

def test_spawn_pending_detaches(lb, monkeypatch):
    home, _ = lb
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: calls.append((a, k)))
    assert otlp.spawn_pending() is True
    (args,), kw = calls[0]
    assert args[-4:] == ["loopbrake.cli", "export", "--pending", "--quiet"] and kw["start_new_session"] is True
    assert kw["stdin"] == kw["stdout"] == kw["stderr"] == subprocess.DEVNULL and kw["env"]["LOOPBRAKE_HOME"] == str(home)
    assert otlp.spawn_pending() is False and len(calls) == 1  # one is already starting
    monkeypatch.delenv("LOOPBRAKE_EXPORT")
    (home / "export" / "spawned").unlink()
    assert otlp.spawn_pending() is False and len(calls) == 1


def test_hooks_stay_fast_with_export_on_and_the_backend_down(lb, monkeypatch, tmp_path):
    """SC-006: export never slows the agent. Also runs the real background export, which records the failure."""
    home, _ = lb
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"http://127.0.0.1:{closed_port()}")
    tp = str(tmp_path / "claude" / "projects" / "-Users-someone-demo" / "s9.jsonl")
    base = {"session_id": "s9", "transcript_path": tp, "cwd": "/Users/someone/demo"}
    claude_code.hook("prompt", json.dumps(base | {"prompt": "go"}), home)
    times = []
    for i in range(50):
        call = base | {"tool_name": "Bash", "tool_input": {"command": f"echo {i}"}, "tool_use_id": f"toolu_{i}", "duration_ms": 5}
        began = time.perf_counter()
        claude_code.hook("tool", json.dumps(call), home)
        times.append(time.perf_counter() - began)
    began = time.perf_counter()
    claude_code.hook("stop", json.dumps(base), home)  # ends the task, which starts the background export
    times.append(time.perf_counter() - began)
    assert statistics.quantiles(times, n=20)[18] < 0.010, sorted(times)[-5:]
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and not (otlp.load_state(home) or {}).get("last"):
        time.sleep(0.1)
    last = otlp.load_state(home)["last"]
    assert last["ok"] is False and last["status"] is None and last["tasks"] == 1 and last["spans"] == 51


def test_codex_tasks_are_sent_as_codex_without_local_paths(lb):
    home, backend = lb
    otlp.begin(home)
    first, *rest = task("cx")
    first = first | {"project": "codex-home-someone-demo-abc123", "folder": "secret-folder-name",
                     "transcript": "/home/someone/.codex/sessions/rollout-secret.jsonl", "turn_id": "t1"}
    write(home, "s9", [first, *rest])
    assert otlp.export_pending()["ok"]
    task_span = next(s for s in spans(backend) if s["name"].startswith("invoke_agent"))
    assert task_span["name"] == "invoke_agent codex" and attrs(task_span)["gen_ai.agent.name"] == "codex"
    sent = json.dumps([b for _, _, b, _ in backend.requests])
    assert "secret-folder-name" not in sent and "rollout-secret" not in sent
