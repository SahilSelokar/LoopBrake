"""OpenTelemetry export: each finished task as one trace, plus four counters, as OTLP/HTTP JSON.

Contract: specs/005-observability/contracts/otlp.md (research R7, R8). Off unless LOOPBRAKE_EXPORT=otlp
(constitution Principle VI). The agent's path only calls begin() and spawn_pending(), which never touch
the network: sending happens in a detached `loopbrake export --pending --quiet`.
"""
import hashlib
import json
import os
import sys
import time
import warnings
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote, urlsplit

from loopbrake import __version__, records

try:
    import fcntl
except ImportError:  # ponytail: no lock on Windows, as in records
    fcntl = None

# Names from the OpenTelemetry GenAI conventions, all still "Development": kept in one place so a rename
# is a one-line change (roadmap risk). LoopBrake's own names start with "loopbrake.".
OP, AGENT, CONVERSATION = "gen_ai.operation.name", "gen_ai.agent.name", "gen_ai.conversation.id"
TOOL, CALL_ID, ERROR_TYPE = "gen_ai.tool.name", "gen_ai.tool.call.id", "error.type"
INVOKE, EXECUTE = "invoke_agent", "execute_tool"
METRICS = (("loopbrake.tasks", "{task}", "tasks"), ("loopbrake.stops", "{stop}", "stops"),
           ("loopbrake.mistaken_stops", "{stop}", "mistaken_stops"), ("loopbrake.tokens.spent", "{token}", "tokens"))

BATCH = 50  # tasks per request
RETRY = (429, 502, 503, 504)
WARNING = "LoopBrake sends OTLP JSON; for protobuf-only backends, put an OpenTelemetry Collector in between."
_SIGNALS = ("", "_TRACES", "_METRICS")


# ---- settings (data-model.md, "Export settings": read from the environment, never stored) ----

def _headers(text):
    out = {}
    for pair in (text or "").split(","):
        k, sep, v = pair.partition("=")
        if sep and k.strip():
            out[unquote(k.strip())] = unquote(v.strip())
    return out


def settings():
    env = os.environ
    base = (env.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "http://localhost:4318").rstrip("/")
    metrics = env.get("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT") or f"{base}/v1/metrics"
    common = _headers(env.get("OTEL_EXPORTER_OTLP_HEADERS"))
    protocols = {env.get(f"OTEL_EXPORTER_OTLP{s}_PROTOCOL") for s in _SIGNALS} - {None, "", "http/json"}
    return {
        "on": env.get("LOOPBRAKE_EXPORT") == "otlp",
        "content": env.get("LOOPBRAKE_EXPORT_CONTENT") == "1",
        "traces": env.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or f"{base}/v1/traces",
        "metrics": None if metrics.strip().lower() == "none" else metrics,
        "traces_headers": common | _headers(env.get("OTEL_EXPORTER_OTLP_TRACES_HEADERS")),
        "metrics_headers": common | _headers(env.get("OTEL_EXPORTER_OTLP_METRICS_HEADERS")),
        "cumulative": (env.get("OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE") or "").lower() == "cumulative",
        "service": env.get("OTEL_SERVICE_NAME") or "loopbrake",
        "warning": WARNING if protocols else None,
    }


def host(url):
    """Where it sends, for people to read: host and port only, never a path or credentials."""
    u = urlsplit(url)
    return f"{u.hostname}:{u.port}" if u.port else (u.hostname or url)


# ---- state: export/state.json (data-model.md) ----

def _dir(h):
    return h / "export"


@contextmanager
def _lock(h, blocking=True):
    """Hold export/lock; yields False instead when it's busy and blocking is off."""
    _dir(h).mkdir(parents=True, exist_ok=True)
    fd = os.open(_dir(h) / "lock", os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        if fcntl:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            except BlockingIOError:
                yield False
                return
        yield True
    finally:
        os.close(fd)


def load_state(h):
    try:
        return json.loads((_dir(h) / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save(h, state):
    path = _dir(h) / "state.json"
    tmp = path.with_name("state.json.tmp")
    with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, path)


def _start_here(h):
    """The starting point: each file's current end. Only tasks starting after it are ever sent (R7)."""
    return {"v": 1, "started": records._now(), "sent_at": None, "totals": {}, "last": None,
            "offsets": {p.name: {"at": p.stat().st_size, "open": []} for p in records._files(h)}}


def begin(h):
    """Called before a task's run_start is written. Returns True when export is on, so the run_start is
    marked and the task may be sent; tasks run with export off never are, even if it's turned on later.
    The first marked task also fixes the starting point. Never raises and never waits: agent path."""
    try:
        if not settings()["on"]:
            return False
        if not (_dir(h) / "state.json").exists():
            with _lock(h, blocking=False) as got:
                if got and load_state(h) is None:
                    _save(h, _start_here(h))
        return True
    except Exception:
        return False


# ---- reading finished tasks (research R7) ----

def _lines(path, start):
    """(offset, event) for each complete line from `start`, and the offset after the last complete one."""
    with open(path, "rb") as f:
        f.seek(start)
        data = f.read()
    end = data.rfind(b"\n") + 1
    out, pos = [], start
    for raw in data[:end].split(b"\n")[:-1]:
        try:
            e = json.loads(raw)
        except ValueError:
            e = None
        if isinstance(e, dict):
            out.append((pos, e))
        pos += len(raw) + 1
    return out, start + end


def finished_tasks(h, state):
    """Tasks started with export on and finished since the last send, mistaken-stop marks made since then (as (file, run)), and the
    offsets to save once they're sent. A task is final at its stop or its run_end, whichever comes first,
    so calls landing after a stop aren't sent. Per file, `at` is how far it was read and `open` holds the
    run_start offsets of tasks still running there."""
    # ponytail: a task that never ends keeps its file re-read from its start; fine at session-file sizes.
    tasks, marks, offsets = [], [], {}
    for path in records._files(h):
        old = state["offsets"].get(path.name, {"at": 0, "open": []})  # a new file started after the starting point
        at, waiting = old["at"], set(old["open"])
        lines, end = _lines(path, min([at, *waiting]))
        found = {}
        for pos, e in lines:
            kind, run = e.get("event"), e.get("run")
            if kind == "feedback":
                if pos >= at and e.get("verdict") == "mistaken_stop":
                    marks.append((path, run))
            elif kind == "run_start":
                if e.get("export") is True and (pos >= at or pos in waiting):
                    found[run] = {"pos": pos, "start": e, "steps": [], "final": None}
            elif run in found and found[run]["final"] is None:
                if kind == "step":
                    found[run]["steps"].append(e)
                elif kind in ("stop", "run_end"):
                    found[run]["final"] = e
        tasks += [t for t in found.values() if t["final"]]
        offsets[path.name] = {"at": end, "open": sorted(t["pos"] for t in found.values() if not t["final"])}
    return tasks, marks, offsets


# ---- building OTLP JSON (contracts/otlp.md) ----

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _ns(ts):
    """A record time as integer nanoseconds, exactly (a float would round)."""
    t = datetime.fromisoformat(ts)
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (t - _EPOCH) // timedelta(microseconds=1) * 1000


def _hex(text, n):
    return hashlib.sha256(text.encode()).hexdigest()[:n]


def project_id(name):
    """What identifies a project without content opt-in: Claude Code project names hold folder paths."""
    return _hex(name or "", 12)


def _attr(key, value):
    if isinstance(value, bool):
        v = {"boolValue": value}
    elif isinstance(value, int):
        v = {"intValue": str(value)}
    elif isinstance(value, float):
        v = {"doubleValue": value}
    else:
        v = {"stringValue": str(value)}
    return {"key": key, "value": v}


def _attrs(*pairs):
    return [_attr(k, v) for k, v in pairs if v is not None]


def _resource(s):
    return {"attributes": _attrs(("service.name", s["service"]), ("service.version", __version__))}


_SCOPE = {"name": "loopbrake", "version": __version__}


def _task_spans(t, content):
    from loopbrake.claude_code import plain_stop, reason_codes  # here: claude_code imports brake, which imports this

    start, final, steps = t["start"], t["final"], t["steps"]
    session, project = start.get("session") or "", start.get("project") or ""
    cal = start.get("calibration") or {}
    key = f"{session}/{start.get('run')}"
    trace, parent = _hex(key, 32), None
    if start.get("traceparent"):  # checked when written: 00-<trace>-<span>-<flags>
        _, trace, parent, _ = start["traceparent"].split("-")
    task_id = _hex(key + "/task", 16)
    stopped = final.get("event") == "stop"
    agent = "claude-code" if project.startswith("cc-") else project
    out, prev = [], _ns(start["ts"])
    for s in steps:
        end, took = _ns(s["ts"]), s.get("duration_ms")
        begin_at = end - took * 1_000_000 if isinstance(took, int) and not isinstance(took, bool) else prev
        tool = s.get("tool") or "tool"
        out.append({"traceId": trace, "spanId": _hex(f"{key}/{s.get('step')}", 16), "parentSpanId": task_id,
                    "name": f"{EXECUTE} {tool}", "kind": 1, "startTimeUnixNano": str(begin_at), "endTimeUnixNano": str(end),
                    "attributes": _attrs((OP, EXECUTE), (TOOL, tool), (CALL_ID, s.get("call_id")), ("loopbrake.step", s.get("step")),
                                         ("loopbrake.failed", s.get("error") is True),
                                         ("loopbrake.action", (s.get("action_excerpt") or "")[:200] if content else None))})
        prev = end
    task = {"traceId": trace, "spanId": task_id, "name": f"{INVOKE} {agent}", "kind": 1,
            "startTimeUnixNano": str(_ns(start["ts"])), "endTimeUnixNano": str(_ns(final["ts"])),
            "attributes": _attrs((OP, INVOKE), (AGENT, agent), (CONVERSATION, session or None),
                                 ("loopbrake.project_id", project_id(project)), ("loopbrake.project", project if content else None),
                                 ("loopbrake.limit", cal.get("stop_line")), ("loopbrake.alpha", cal.get("alpha")),
                                 ("loopbrake.calibration.n", cal.get("n")),
                                 ("loopbrake.status", "stopped" if stopped else final.get("status") or "finished"),
                                 ("loopbrake.tool_calls", len(steps)), (ERROR_TYPE, "loopbrake.stopped" if stopped else None)),
            "status": {"code": 2, "message": "stopped by LoopBrake"} if stopped else {"code": 0}}
    if parent:
        task["parentSpanId"] = parent
    if stopped:
        reason = plain_stop(final.get("step"), final.get("stop_line"), cal.get("n"), cal.get("alpha"), final.get("reason"), "")
        task["events"] = [{"name": "loopbrake.stop", "timeUnixNano": str(_ns(final["ts"])), "attributes": _attrs(
            ("loopbrake.step", final.get("step")), ("loopbrake.limit", final.get("stop_line")),
            ("loopbrake.reason_code", ",".join(reason_codes(final.get("reason")))),
            ("loopbrake.reason", reason if content else None))}]
    return [task, *out]


def build_traces(tasks, s):
    """One request body per BATCH tasks."""
    return [{"resourceSpans": [{"resource": _resource(s), "scopeSpans": [{"scope": _SCOPE, "spans": [
        span for t in tasks[i:i + BATCH] for span in _task_spans(t, s["content"])]}]}]}
        for i in range(0, len(tasks), BATCH)]


def counts(tasks, mark_projects):
    """Per project name: tasks, stops, mistaken stops and reported tokens."""
    out = {}

    def row(p):
        return out.setdefault(p or "", {"tasks": 0, "stops": 0, "mistaken_stops": 0, "tokens": 0})
    for t in tasks:
        r = row(t["start"].get("project"))
        r["tasks"] += 1
        r["stops"] += t["final"].get("event") == "stop"
        r["tokens"] += sum(s.get("tokens") or 0 for s in t["steps"])
    for p in mark_projects:
        row(p)["mistaken_stops"] += 1
    return out


def build_metrics(by_project, s, start_ns, now_ns):
    """Four monotonic Sums. Delta (1) by default; cumulative (2) when the standard preference asks for it."""
    metrics = []
    for name, unit, key in METRICS:
        points = [{"attributes": _attrs(("loopbrake.project_id", project_id(p)), ("loopbrake.project", p if s["content"] else None)),
                   "startTimeUnixNano": str(start_ns), "timeUnixNano": str(now_ns), "asInt": str(c[key])}
                  for p, c in sorted(by_project.items()) if c[key]]
        if points:
            metrics.append({"name": name, "unit": unit, "sum": {
                "aggregationTemporality": 2 if s["cumulative"] else 1, "isMonotonic": True, "dataPoints": points}})
    return {"resourceMetrics": [{"resource": _resource(s), "scopeMetrics": [{"scope": _SCOPE, "metrics": metrics}]}]}


# ---- sending (contracts/otlp.md, "Responses") ----

def _clean(raw, headers):
    """A backend's message, safe to keep: header values hidden (some backends echo them), 200 characters."""
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
    for v in headers.values():
        for secret in {v, *v.split()}:
            if len(secret) >= 4:
                text = text.replace(secret, "[hidden]")
    return " ".join(text.split())[:200]


def _retry_after(value):
    try:
        return min(max(float(value), 0.0), 10.0)
    except (TypeError, ValueError):  # missing, or an HTTP date: wait 1 s
        return 1.0


def send(url, body, headers):
    """POST one body. Returns {"reached", "ok", "status", "message", "rejected"} and never raises.
    `reached` means the backend took it (2xx), so the offsets may move even if it rejected part."""
    import socket  # here, not at the top: urllib.request costs the agent's path about 20 ms to import
    import urllib.error
    import urllib.request
    data = json.dumps(body, separators=(",", ":")).encode()
    for attempt in (1, 2):
        req = urllib.request.Request(url, data=data, method="POST", headers={**headers, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                status, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code in RETRY and attempt == 1:
                time.sleep(_retry_after(e.headers.get("Retry-After")))
                continue
            return {"reached": False, "ok": False, "status": e.code, "message": _clean(e.read(), headers), "rejected": 0}
        except (OSError, ValueError) as e:  # refused, timed out, bad address
            reason = getattr(e, "reason", e)
            text = ("that address couldn't be found" if isinstance(reason, socket.gaierror)
                    else getattr(reason, "strerror", None) or str(reason))  # "Connection refused", not "[Errno 61] ..."
            return {"reached": False, "ok": False, "status": None, "message": _clean(text, headers), "rejected": 0}
        try:
            partial = (json.loads(raw or b"{}") or {}).get("partialSuccess") or {}
        except (ValueError, AttributeError):
            partial = {}
        rejected = int(partial.get("rejectedSpans") or partial.get("rejectedDataPoints") or 0)
        message = _clean(partial.get("errorMessage") or "", headers)
        return {"reached": True, "ok": not rejected and not message, "status": status, "message": message, "rejected": rejected}


def problem(r, where):
    """A failed send in plain words."""
    if r["status"] is None:
        return f"couldn't reach {where}: {r['message']}"
    if r["status"] < 300:
        return f"{where} took the data but refused part of it ({r['rejected']} items): {r['message']}"
    return f"{where} refused the data (HTTP {r['status']}): {r['message']}"


def _mark_projects(marks):
    names, by_file = [], {}
    for path, run in marks:
        if path not in by_file:
            by_file[path] = {e.get("run"): e.get("project") for _, e in _lines(path, 0)[0] if e.get("event") == "run_start"}
        names.append(by_file[path].get(run))
    return names


def _send_once(h, s):
    state = load_state(h)
    if state is None:  # export was just turned on: start from here
        _save(h, _start_here(h))
        return {"ok": True, "tasks": 0, "spans": 0}
    tasks, marks, offsets = finished_tasks(h, state)
    batch = counts(tasks, _mark_projects(marks))
    if not tasks and not marks:
        state["offsets"] = offsets
        _save(h, state)
        return {"ok": True, "tasks": 0, "spans": 0}
    now = records._now()
    result = {"at": now, "ok": True, "tasks": len(tasks), "spans": sum(1 + len(t["steps"]) for t in tasks),
              "status": None, "message": "", "rejected": 0, "warning": s["warning"]}
    totals = {p: {k: state["totals"].get(p, {}).get(k, 0) + v for k, v in c.items()} for p, c in batch.items()}
    totals = state["totals"] | totals
    sends = [(s["traces"], body, s["traces_headers"]) for body in build_traces(tasks, s)]
    if s["metrics"] and batch:
        window = _ns(state["started"] if s["cumulative"] else state["sent_at"] or state["started"])
        sends.append((s["metrics"], build_metrics(totals if s["cumulative"] else batch, s, window, _ns(now)), s["metrics_headers"]))
    # ponytail: all or nothing; if a later request fails, the earlier ones are sent again next time
    # (the same ids, so a trace isn't duplicated). Per-batch offsets are the upgrade.
    for url, body, headers in sends:
        r = send(url, body, headers)
        result |= {"status": r["status"], "rejected": result["rejected"] + r["rejected"],
                   "message": r["message"] or result["message"], "ok": result["ok"] and r["ok"]}
        if not r["reached"]:
            state["last"] = result
            _save(h, state)
            return result
    state |= {"offsets": offsets, "sent_at": now, "totals": totals, "last": result}
    _save(h, state)
    return result


def export_pending(home=None):
    """Send every finished task not sent yet. Returns the result, or None when export is off."""
    h, s = records.home(home), settings()
    if not s["on"]:
        return None
    while True:
        with _lock(h):
            (_dir(h) / "again").unlink(missing_ok=True)
            result = _send_once(h, s)
        if not (_dir(h) / "again").exists():  # a task ended while this one was sending: go round again
            return result


def test_connection():
    """Send one test span. Returns send()'s result, or None when export is off."""
    s = settings()
    if not s["on"]:
        return None
    now = str(time.time_ns())
    span = {"traceId": os.urandom(16).hex(), "spanId": os.urandom(8).hex(), "name": "loopbrake test", "kind": 1,
            "startTimeUnixNano": now, "endTimeUnixNano": now, "attributes": _attrs(("loopbrake.test", True))}
    body = {"resourceSpans": [{"resource": _resource(s), "scopeSpans": [{"scope": _SCOPE, "spans": [span]}]}]}
    return send(s["traces"], body, s["traces_headers"])


test_connection.__test__ = False  # not a pytest test, despite the name


def spawn_pending(home=None):
    """Start `loopbrake export --pending --quiet` in the background and don't wait (research R7). Returns
    True if one was started. Never raises: it runs on the agent's path."""
    try:
        h = records.home(home)
        if not settings()["on"]:
            return False
        _dir(h).mkdir(parents=True, exist_ok=True)
        (_dir(h) / "again").touch()  # an exporter already running sees this and goes round once more
        with _lock(h, blocking=False) as free:
            if not free:
                return False
        marker = _dir(h) / "spawned"
        if marker.exists() and time.time() - marker.stat().st_mtime < 2:
            return False  # one is starting up; it reads the records after clearing "again"
        marker.touch()
        import subprocess  # here: the agent's path pays for it only at a task's end
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)  # never waited for, on purpose
            subprocess.Popen([sys.executable, "-m", "loopbrake.cli", "export", "--pending", "--quiet"],
                             env=os.environ | {"LOOPBRAKE_HOME": str(h)}, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except Exception:
        return False
