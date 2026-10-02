"""The dashboard: its record index, its server and access rules, and its actions (specs/005-observability)."""
import json
import time
from datetime import datetime, timedelta, timezone

import pytest

from loopbrake import calibration, claude_code, dashboard, records
from loopbrake.brake import start


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOPBRAKE_HOME", str(tmp_path / "lb"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    return records.home()


def ts(days_ago=0, minutes=0):
    t = datetime.now(timezone.utc) - timedelta(days=days_ago, minutes=minutes)
    return t.isoformat(timespec="milliseconds")


def calibrate(home, project, stop_line, n=19, lengths=None):
    (home / "calibration").mkdir(parents=True, exist_ok=True)
    rec = {"v": 1, "project": project, "method": "steps", "alpha": 0.05, "n": n, "k": n, "stop_line": stop_line,
           "watch_only": stop_line is None, "source": {"kind": "claude-code"}, "created": "2026-10-02", "version": "0.3.0"}
    if lengths is not None:
        rec["lengths"] = lengths
    (home / "calibration" / f"{project}.json").write_text(json.dumps(rec))


def write(home, session, events):
    w = records.RunWriter(home / "runs" / f"{session}.jsonl")
    for e in events:
        w.write({"session": session} | e)


def task_events(run, project="demo", stop_line=3, calls=2, end=None, stop_at=None, when=0, call_prefix="c"):
    cal = {"method": "steps", "alpha": 0.05, "n": 19, "k": 19, "stop_line": stop_line, "watch_only": stop_line is None}
    ev = [{"event": "run_start", "run": run, "project": project, "calibration": cal, "ts": ts(when, 10)}]
    for i in range(1, calls + 1):
        ev.append({"event": "step", "run": run, "step": i, "tool": "Bash", "action_excerpt": f"Bash {{\"command\": \"echo {i}\"}}",
                   "tokens": None, "error": i == 2, "call_id": f"{call_prefix}{run}-{i}", "ts": ts(when, 10 - i)})
    if stop_at:
        ev.append({"event": "stop", "run": run, "step": stop_at, "stop_line": stop_line,
                   "reason": f"stopped at step {stop_at}: past the stop line of {stop_line} steps; repeating in 3 of last 3 steps", "ts": ts(when, 2)})
    if end:
        ev.append({"event": "run_end", "run": run, "status": end, "steps": calls, "tokens": None, "ts": ts(when, 1)})
    return ev


# ---- the index (T006) ----

def test_task_summaries_and_status(home):
    write(home, "s1", task_events("fin", end="finished"))
    write(home, "s1", task_events("stp", calls=4, stop_at=4, end="stopped"))
    write(home, "s2", task_events("open-stop", calls=4, stop_at=4))  # stopped, no run_end yet
    write(home, "s3", task_events("run", calls=1))
    write(home, "s4", task_events("old", calls=1, when=2))  # nothing new for two days
    write(home, "s5", task_events("esc", calls=1, end="interrupted"))
    idx = dashboard.Index(home)
    idx.refresh()
    by = {t["run"]: t for t in idx.tasks(limit=50)["tasks"]}
    assert {r: by[r]["status"] for r in by} == {"fin": "Finished", "stp": "Stopped", "open-stop": "Stopped", "run": "Running",
                                                "old": "Running (no activity)", "esc": "Interrupted"}
    assert by["stp"]["calls"] == 4 and by["stp"]["limit"] == 3 and by["stp"]["stop_at"] == 4
    assert by["fin"]["agent"] == "python" and by["fin"]["id"] == "s1/fin"


def test_incremental_reads_and_damaged_lines(home):
    write(home, "s1", task_events("a", calls=1))
    idx = dashboard.Index(home)
    idx.refresh()
    v1, read1 = idx.version, idx.bytes_read
    assert idx.task("s1", "a")["summary"]["calls"] == 1
    with open(home / "runs" / "s1.jsonl", "a") as f:
        f.write("{damaged\n")
    write(home, "s1", [{"event": "step", "run": "a", "step": 2, "tool": "Bash", "action_excerpt": "Bash x", "error": False, "ts": ts()}])
    idx.refresh()
    assert idx.version > v1 and idx.bytes_read - read1 == (home / "runs" / "s1.jsonl").stat().st_size - read1  # only new bytes read
    assert idx.tasks(limit=5)["tasks"][0]["calls"] == 2 and idx.overview()["skipped_lines"] == 1
    v2 = idx.version
    idx.refresh()
    assert idx.version == v2  # nothing new


def test_task_page_lists_calls_with_repeats(home):
    ev = task_events("t", calls=0, stop_line=5)
    for i, cmd in enumerate(["ls", "ls", "pytest -q", "ls"], 1):
        ev.append({"event": "step", "run": "t", "step": i, "tool": "Bash", "action_excerpt": f"Bash {{\"command\": \"{cmd}\"}}",
                   "error": cmd == "pytest -q", "duration_ms": 50 + i, "ts": ts(0, 5 - i)})
    write(home, "s1", ev)
    idx = dashboard.Index(home)
    idx.refresh()
    t = idx.task("s1", "t")
    assert [c["repeats"] for c in t["calls"]] == [False, True, False, True]
    assert [c["failed"] for c in t["calls"]] == [False, False, True, False]
    assert t["calls"][0]["duration_ms"] == 51 and t["calls"][0]["n"] == 1
    assert idx.task("s1", "missing") is None


def test_task_pages_of_200(home):
    write(home, "s1", task_events("big", calls=450, stop_line=None))
    idx = dashboard.Index(home)
    idx.refresh()
    assert len(idx.task("s1", "big", page=0)["calls"]) == 200
    assert len(idx.task("s1", "big", page=2)["calls"]) == 50 and idx.task("s1", "big", page=2)["more"] is False


def test_plain_reason_on_stopped_tasks(home):
    write(home, "s1", task_events("stp", calls=4, stop_at=4, end="stopped"))
    idx = dashboard.Index(home)
    idx.refresh()
    text = idx.task("s1", "stp")["reason_text"]
    assert text.startswith("LoopBrake stopped this task after 4 tool calls.") and "repeat each other" in text
    assert "Mark as mistake" in text and "α" not in text and "step" not in text


def test_overview_counts_and_days(home):
    write(home, "s1", task_events("a", calls=4, stop_at=4, end="stopped", when=1))
    write(home, "s1", task_events("b", end="finished"))
    write(home, "s2", task_events("c", calls=1))
    write(home, "s2", [{"event": "feedback", "run": "a", "verdict": "mistaken_stop"}])
    write(home, "s3", task_events("w", stop_line=None, end="finished"))
    idx = dashboard.Index(home)
    idx.refresh()
    o = idx.overview()
    assert (o["seen"], o["stopped"], o["mistaken"]) == (4, 1, 1)
    assert o["normal_mistakes"] == pytest.approx(0.15)  # alpha x watched tasks (3 with a limit)
    assert [t["run"] for t in o["running"]] == ["c"] and [t["run"] for t in o["recent_stops"]] == ["a"]
    assert len(o["days"]) == 30 and sum(d["stops"] for d in o["days"]) == 1


def test_projects_and_history(home, tmp_path):
    folder = claude_code.history_folder("/home/me/demo")  # made up; under the temporary CLAUDE_CONFIG_DIR
    folder.mkdir(parents=True)
    cc = claude_code.project_name(folder.name)
    calibrate(home, cc, 3, lengths=[1, 2, 2, 3, None])
    calibrate(home, "agent-x", None, n=7)
    write(home, "s1", task_events("a", project=cc, end="finished"))
    idx = dashboard.Index(home)
    idx.refresh()
    ps = {p["name"]: p for p in idx.projects()}
    assert ps[cc]["limit"] == 3 and ps[cc]["can_recalibrate"] is True and ps[cc]["seen"] == 1
    assert ps["agent-x"]["watch_only"] is True and ps["agent-x"]["needed"] == 19 and ps["agent-x"]["can_recalibrate"] is False
    p = idx.project(cc)
    assert p["lengths"] == [1, 2, 2, 3, None] and p["promise"] == "fewer than 1 in 20 good tasks should go past it"
    assert idx.project("nope") is None


def test_claude_code_tokens_from_history(home):
    folder = claude_code.history_folder("/home/me/demo")
    folder.mkdir(parents=True)
    cc = claude_code.project_name(folder.name)
    usage = {"input_tokens": 100, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 20}
    lines = [{"type": "user", "uuid": "u1", "message": {"role": "user", "content": "hi"}},
             {"type": "assistant", "uuid": "a1", "message": {"id": "m1", "role": "assistant", "stop_reason": "tool_use", "usage": usage,
                                                            "content": [{"type": "tool_use", "id": "ccc-1", "name": "Bash", "input": {}}]}},
             {"type": "assistant", "uuid": "a2", "message": {"id": "m2", "role": "assistant", "stop_reason": "end_turn", "usage": usage,
                                                            "content": [{"type": "text", "text": "ok"}]}}]
    (folder / "s.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n")
    write(home, "s1", task_events("cc", project=cc, calls=1, end="finished"))  # first call id "c" + "cc" + "-1" = "ccc-1"
    write(home, "s1", task_events("other", project=cc, calls=1, end="finished", call_prefix="zz"))
    idx = dashboard.Index(home)
    idx.refresh()
    by = {t["run"]: t for t in idx.tasks(limit=10)["tasks"]}
    assert by["cc"]["tokens"] == 240 and by["other"]["tokens"] is None
    assert sum(d["tokens"] for d in idx.overview()["days"]) == 240


def test_large_history_loads_fast(home):
    lines = []
    for r in range(10000):
        lines += [json.dumps(e | {"v": 1, "session": "big"}) for e in task_events(f"r{r}", calls=20, end="finished")]
    (home / "runs").mkdir(parents=True)
    (home / "runs" / "big.jsonl").write_text("\n".join(lines) + "\n")
    t = time.perf_counter()
    idx = dashboard.Index(home)
    idx.refresh()
    assert time.perf_counter() - t < 3
    t = time.perf_counter()
    idx.overview()
    assert time.perf_counter() - t < 0.1


# ---- the server and its access rules (T008, contracts/dashboard-http.md) ----

import http.client
import threading


@pytest.fixture
def server(home):
    write(home, "s1", task_events("stp", calls=4, stop_at=4, end="stopped"))
    calibrate(home, "demo", 3)
    srv, key = dashboard.make_server(home)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv, key, srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def call(port, path, method="GET", key=None, host=None, origin=None, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Host": host or f"127.0.0.1:{port}"}
    if key:
        headers["Cookie"] = f"lb={key}"
    if origin:
        headers["Origin"] = origin
    if body is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(body)
    conn.request(method, path, body=body, headers=headers)
    r = conn.getresponse()
    data = r.read()
    conn.close()
    return r.status, dict(r.getheaders()), data


def test_key_exchange_and_access(server):
    _, key, port = server
    code, headers, _ = call(port, f"/?k={key}")
    cookie = headers["Set-Cookie"]
    assert code == 303 and headers["Location"] == "/"
    assert f"lb={key}" in cookie and "HttpOnly" in cookie and "SameSite=Strict" in cookie and "Path=/" in cookie
    assert call(port, "/?k=wrong")[0] == 401
    code, _, body = call(port, "/api/overview")
    assert code == 401 and b"Open the address loopbrake dashboard printed." in body
    assert call(port, "/api/overview", key=key, host="evil.example")[0] == 403
    assert call(port, "/api/overview", key=key, host=f"localhost:{port}")[0] == 200
    assert call(port, "/api/mistake", "POST", key=key, origin="http://evil.example", body={"task": "s1/stp"})[0] == 403


def test_headers_and_bind_address(server):
    srv, key, port = server
    assert srv.server_address[0] == "127.0.0.1"
    _, headers, _ = call(port, "/api/overview", key=key)
    assert headers["Content-Security-Policy"] == "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
    assert headers["X-Content-Type-Options"] == "nosniff" and headers["Referrer-Policy"] == "no-referrer"
    assert headers["Cache-Control"] == "no-store" and headers["Content-Type"] == "application/json"


def test_read_endpoints(server):
    _, key, port = server
    get = lambda p: json.loads(call(port, p, key=key)[2])
    assert set(get("/api/changes?since=0")) == {"version"}
    o = get("/api/overview")
    assert {"seen", "stopped", "mistaken", "normal_mistakes", "running", "recent_stops", "days", "skipped_lines"} <= set(o)
    assert get("/api/tasks?limit=5")["tasks"][0]["id"] == "s1/stp"
    t = get("/api/task/s1/stp")
    assert t["summary"]["status"] == "Stopped" and len(t["calls"]) == 4 and t["reason_text"]
    assert get("/api/projects")[0]["name"] == "demo" and get("/api/project/demo")["limit"] == 3
    assert call(port, "/api/task/s1/nope", key=key)[0] == 404 and call(port, "/api/project/nope", key=key)[0] == 404
    assert call(port, "/api/task/..%2F/x", key=key)[0] in (400, 404)


def test_static_files_and_no_traversal(server):
    _, key, port = server
    code, headers, body = call(port, "/", key=key)
    assert code == 200 and headers["Content-Type"].startswith("text/html") and b"<html" in body
    code, headers, _ = call(port, "/static/icons.svg", key=key)
    assert code == 200 and headers["Content-Type"] == "image/svg+xml"
    assert call(port, "/static/fonts/inter-tight.woff2", key=key)[1]["Content-Type"] == "font/woff2"
    for bad in ("/static/../dashboard.py", "/static/%2e%2e/dashboard.py", "/static/fonts/../../dashboard.py", "/nope"):
        assert call(port, bad, key=key)[0] == 404, bad
    assert call(port, "/static/icons.svg")[0] == 401  # files need the key too


def test_live_update_within_two_seconds(server, home):
    _, key, port = server
    v1 = json.loads(call(port, "/api/changes", key=key)[2])["version"]
    write(home, "s1", [{"event": "step", "run": "stp", "step": 5, "tool": "Bash", "action_excerpt": "Bash x", "error": False}])
    t0 = time.time()
    while json.loads(call(port, "/api/changes", key=key)[2])["version"] == v1:
        assert time.time() - t0 < 2
        time.sleep(0.05)
