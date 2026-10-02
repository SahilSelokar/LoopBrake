"""The local dashboard: a record index, a JSON API and a small web server.

Contracts: specs/005-observability/contracts/dashboard-http.md and ui.md. It reads the records
LoopBrake already writes; its actions reuse the Phase 3 code. It listens on 127.0.0.1 only and the
page loads nothing from anywhere else (constitution, Principle VI and Dashboard security).
"""
import http.cookies
import http.server
import json
import os
import re
import secrets
import threading
import time
import warnings
import webbrowser
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from loopbrake import calibration, claude_code, records
from loopbrake.signals import Step, method
from loopbrake.traces import claude_code_turns

PAGE = 200
STALE = timedelta(hours=24)
LABELS = {"running": "Running", "idle": "Running (no activity)", "finished": "Finished", "stopped": "Stopped",
          "interrupted": "Interrupted"}
NEXT_STEP = ' Use "Mark as mistake" if it wasn\'t stuck.'
_RUN = re.compile(r'"run": "([^"]*)"')
_TS = re.compile(r'"ts": "([^"]*)"')
_CALL = re.compile(r'"call_id": "([^"]*)"')


def _when(ts):
    try:
        return datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


class Index:
    """Task summaries built from the run records, read incrementally (research R3).

    Records are append-only, so each refresh reads only the bytes added since the last one. Tool-call
    lines are counted by a text check and parsed only when a task is opened.
    """

    def __init__(self, home=None, days=None):
        self.home, self.days = records.home(home), days
        self.offsets, self.tasks_by_id, self.by_run = {}, {}, {}
        self.bytes_read = self.skipped = self.version = 0
        self._cc = {}  # transcript path -> ((size, mtime), {call_id: turn tokens})
        self._lock = threading.RLock()

    # ---- reading ----

    def refresh(self):
        # ponytail: whole history read at start; keep a summary cache on disk if starts get slow
        with self._lock:
            runs = self.home / "runs"
            cutoff = time.time() - self.days * 86400 if self.days else None
            for path in sorted(runs.glob("*.jsonl")) if runs.exists() else []:
                try:
                    st = path.stat()
                except OSError:
                    continue
                if cutoff and st.st_mtime < cutoff and path not in self.offsets:
                    continue
                start = self.offsets.get(path, 0)
                if st.st_size <= start:
                    continue
                with open(path, "rb") as f:
                    f.seek(start)
                    data = f.read(st.st_size - start)
                end = data.rfind(b"\n")
                if end < 0:
                    continue  # only a half-written line so far
                chunk = data[:end + 1]
                self.offsets[path] = start + len(chunk)
                self.bytes_read += len(chunk)
                for line in chunk.decode("utf-8", "replace").splitlines():
                    if line.strip():
                        self._line(path, line)
            self.version = self.bytes_read
        return self.version

    def _line(self, path, line):
        session = path.stem
        if '"event": "step"' in line:  # the common case: count without parsing
            m = _RUN.search(line)
            t = self.tasks_by_id.get(f"{session}/{m.group(1)}") if m else None
            if t is None:
                self.skipped += m is None
                return
            t["calls"] += 1
            if (ts := _TS.search(line)):
                t["last_ts"] = ts.group(1)
            if t["first_call"] is None and (c := _CALL.search(line)):
                t["first_call"] = c.group(1)
            return
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            self.skipped += 1
            return
        kind, run = e.get("event"), e.get("run")
        if kind == "run_start":
            cal = e.get("calibration") or {}
            watched = not cal.get("watch_only", True)
            tid, project = f"{session}/{run}", e.get("project") or ""
            self.tasks_by_id[tid] = {
                "id": tid, "session": session, "run": run, "project": project,
                "agent": "claude-code" if project.startswith("cc-") else "python", "file": path,
                "started": e.get("ts"), "ended": None, "last_ts": e.get("ts"), "end_status": None, "calls": 0,
                "limit": cal.get("stop_line") if watched else None, "watched": watched, "alpha": cal.get("alpha"),
                "n": cal.get("n"), "stop_at": None, "stop_ts": None, "reason": None, "marks": set(), "tokens": None,
                "first_call": None}
            self.by_run[run] = tid
            return
        t = self.tasks_by_id.get(self.by_run.get(run, ""))
        if t is None:
            return
        if kind == "stop":
            t["stop_at"], t["stop_ts"], t["reason"], t["last_ts"] = e.get("step"), e.get("ts"), e.get("reason"), e.get("ts")
        elif kind == "run_end":
            t["end_status"], t["ended"], t["tokens"], t["last_ts"] = e.get("status"), e.get("ts"), e.get("tokens"), e.get("ts")
        elif kind == "feedback":
            t["marks"].add("mistaken" if e.get("verdict") == "mistaken_stop" else "left_out")

    # ---- Claude Code tokens, read from its own history (research R5) ----

    def _history(self, project):
        root = claude_code.history_folder("/").parent
        if not project.startswith("cc-") or not root.is_dir():
            return None
        return next((d for d in root.iterdir() if d.is_dir() and claude_code.project_name(d.name) == project), None)

    def _cc_tokens(self, project):
        folder, tokens = self._history(project), {}
        if folder is None:
            return tokens
        recent = time.time() - 30 * 86400
        for f in folder.glob("*.jsonl"):
            st = f.stat()
            if st.st_mtime < recent:
                continue
            key = (st.st_size, st.st_mtime)
            if self._cc.get(f, (None,))[0] != key:
                ids, found = {}, {}
                for r in claude_code_turns(f, call_ids=ids)[0]:
                    total = sum(s.tokens for s in r.steps)
                    found.update({c: total for c in ids.get(r.run, ())})
                self._cc[f] = (key, found)
            tokens.update(self._cc[f][1])
        return tokens

    # ---- answers ----

    def _state(self, t, now):
        if t["end_status"]:
            return t["end_status"] if t["end_status"] in LABELS else "finished"
        if t["stop_at"] is not None:
            return "stopped"
        last = _when(t["last_ts"])
        return "idle" if last and now - last > STALE else "running"

    def _public(self, t, now, cc=None):
        state = self._state(t, now)
        tokens = t["tokens"]
        if tokens is None and cc is not None and t["first_call"]:
            tokens = cc.get(t["first_call"])
        return {"id": t["id"], "session": t["session"], "run": t["run"], "project": t["project"], "agent": t["agent"],
                "state": state, "status": LABELS[state], "started": t["started"], "ended": t["ended"],
                "calls": t["calls"], "limit": t["limit"], "stop_at": t["stop_at"], "marks": sorted(t["marks"]),
                "tokens": tokens}

    def _all(self):
        now = datetime.now(timezone.utc)
        cc_by_project = {}
        for p in {t["project"] for t in self.tasks_by_id.values() if t["agent"] == "claude-code"}:
            cc_by_project[p] = self._cc_tokens(p)
        return now, [self._public(t, now, cc_by_project.get(t["project"])) for t in self.tasks_by_id.values()]

    def overview(self, project=None):
        with self._lock:
            now, tasks = self._all()
            raw = {t["id"]: t for t in self.tasks_by_id.values()}
        if project:
            tasks = [t for t in tasks if t["project"] == project]
        newest = lambda t: t["started"] or ""
        days = [(now - timedelta(days=i)).date().isoformat() for i in range(29, -1, -1)]
        per = {d: {"day": d, "stops": 0, "tokens": 0} for d in days}
        for t in tasks:
            stop_day = (_when(raw[t["id"]]["stop_ts"]) or now).date().isoformat() if t["stop_at"] is not None else None
            if stop_day in per:
                per[stop_day]["stops"] += 1
            end_day = (_when(t["ended"] or raw[t["id"]]["last_ts"]) or now).date().isoformat()
            if t["tokens"] and end_day in per:
                per[end_day]["tokens"] += t["tokens"]
        stops = sorted((t for t in tasks if t["state"] == "stopped"), key=lambda t: raw[t["id"]]["stop_ts"] or "", reverse=True)
        return {
            "seen": len(tasks),
            "stopped": sum(t["state"] == "stopped" for t in tasks),
            "mistaken": sum("mistaken" in t["marks"] for t in tasks),
            "normal_mistakes": sum(raw[t["id"]]["alpha"] or 0 for t in tasks if raw[t["id"]]["watched"]),
            "running": sorted((t for t in tasks if t["state"] in ("running", "idle")), key=newest, reverse=True),
            "recent_stops": stops[:20],
            "days": [per[d] for d in days],
            "skipped_lines": self.skipped,
            "projects": sorted({t["project"] for t in tasks}),
        }

    def tasks(self, project=None, state=None, before=None, limit=50):
        with self._lock:
            _, tasks = self._all()
        tasks = [t for t in tasks if (not project or t["project"] == project) and (not state or t["state"] == state)
                 and (not before or (t["started"] or "") < before)]
        tasks.sort(key=lambda t: t["started"] or "", reverse=True)
        page = tasks[:limit]
        return {"tasks": page, "next": page[-1]["started"] if len(tasks) > limit else None}

    def task(self, session, run, page=0):
        with self._lock:
            t = self.tasks_by_id.get(f"{session}/{run}")
            if t is None:
                return None
            now = datetime.now(timezone.utc)
            summary = self._public(t, now, self._cc_tokens(t["project"]) if t["agent"] == "claude-code" else None)
        calls = []
        with open(t["file"], encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"event": "step"' not in line or f'"run": "{run}"' not in line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                calls.append({"n": e.get("step"), "tool": e.get("tool"), "action": e.get("action_excerpt") or "",
                              "failed": e.get("error") is True, "tokens": e.get("tokens"),
                              "duration_ms": e.get("duration_ms"), "call_id": e.get("call_id"), "ts": e.get("ts")})
        fuzzy = method("fuzzy", lam=0)([Step(c["action"], "", None, 0) for c in calls]) if calls else []
        for c, (score, _) in zip(calls, fuzzy):
            c["repeats"] = score == 1.0  # explanation only: same as one of the previous 10 calls
        reason = None
        if t["stop_at"] is not None:
            reason = claude_code.plain_stop(t["stop_at"], t["limit"], t["n"], t["alpha"], t["reason"], NEXT_STEP)
        lo = page * PAGE
        return {"summary": summary, "reason_text": reason, "calls": calls[lo:lo + PAGE], "page": page,
                "more": len(calls) > lo + PAGE, "total": len(calls)}

    def projects(self):
        with self._lock:
            _, tasks = self._all()
            raw = dict(self.tasks_by_id)
        cal_dir = self.home / "calibration"
        names = {p.stem for p in cal_dir.glob("*.json")} if cal_dir.exists() else set()
        names |= {t["project"] for t in tasks}
        out = []
        for name in sorted(n for n in names if n):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                rec = calibration.load(name, self.home) if records.valid_project(name) else None
            mine = [t for t in tasks if t["project"] == name]
            watched = [t for t in mine if raw[t["id"]]["watched"]]
            alpha = (rec or {}).get("alpha") or 0.05
            mistakes = ((rec or {}).get("source") or {}).get("mistakes_counted", 0)
            out.append({
                "name": name, "agent": "claude-code" if name.startswith("cc-") else "python",
                "limit": None if not rec or rec["watch_only"] else rec["stop_line"], "n": (rec or {}).get("n"),
                "alpha": alpha, "created": (rec or {}).get("created"), "calibrated": rec is not None,
                "watch_only": rec is None or rec["watch_only"],
                "needed": calibration.runs_needed(alpha, mistakes) if rec is None or rec["watch_only"] else None,
                "lengths": (rec or {}).get("lengths"),
                "can_recalibrate": self._history(name) is not None,
                "seen": len(mine), "watched": len(watched), "stopped": sum(t["state"] == "stopped" for t in mine),
                "mistaken": sum("mistaken" in t["marks"] for t in mine),
                "normal_mistakes": sum(raw[t["id"]]["alpha"] or 0 for t in watched),
            })
        return out

    def project(self, name):
        p = next((p for p in self.projects() if p["name"] == name), None)
        if p is not None:
            p["promise"] = f"{claude_code.one_in(p['alpha'])} good tasks should go past it"
        return p


# ---- the server (research R1, contracts/dashboard-http.md) ----

CSP = "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
HINT = b"Open the address loopbrake dashboard printed.\n"
_PART = re.compile(r"[A-Za-z0-9._-]{1,128}")
_TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
          ".svg": "image/svg+xml", ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8"}


class _Handler(http.server.BaseHTTPRequestHandler):
    index = key = port = None
    server_version = "loopbrake"
    sys_version = ""

    def log_message(self, *args):  # quiet: nothing about the user's tasks goes to the terminal
        pass

    def _send(self, code, body=b"", ctype=None, extra=None):
        self.send_response(code)
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if ctype:
            self.send_header("Content-Type", ctype)
        if ctype == "application/json":
            self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json")

    def _allowed(self):
        """The Host check (DNS rebinding) and the per-launch key, as a cookie."""
        if self.headers.get("Host") not in (f"127.0.0.1:{self.port}", f"localhost:{self.port}"):
            self._send(403)
            return False
        jar = http.cookies.SimpleCookie()
        try:
            jar.load(self.headers.get("Cookie") or "")
        except http.cookies.CookieError:
            pass
        if "lb" not in jar or not secrets.compare_digest(jar["lb"].value, self.key):
            self._send(401, HINT, "text/plain; charset=utf-8")
            return False
        return True

    def do_GET(self):
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        if url.path == "/" and "k" in query and self.headers.get("Host") in (f"127.0.0.1:{self.port}", f"localhost:{self.port}"):
            if secrets.compare_digest(query["k"][0], self.key):  # the printed address: swap the key for a cookie
                return self._send(303, extra={"Location": "/", "Set-Cookie": f"lb={self.key}; HttpOnly; SameSite=Strict; Path=/"})
            return self._send(401, HINT, "text/plain; charset=utf-8")
        if not self._allowed():
            return
        if url.path == "/":
            return self._static("index.html")
        if url.path.startswith("/static/"):
            return self._static(url.path[len("/static/"):])
        if url.path.startswith("/api/"):
            return self._api_get(url.path, query)
        self._send(404)

    def _static(self, rel):
        parts = unquote(rel).split("/")
        if not parts or any(not _PART.fullmatch(p) or p in (".", "..") for p in parts):
            return self._send(404)
        f = resources.files("loopbrake").joinpath("static", *parts)
        if not f.is_file():
            return self._send(404)
        self._send(200, f.read_bytes(), _TYPES.get(Path(parts[-1]).suffix, "application/octet-stream"))

    def _api_get(self, path, query):
        q = lambda name, default=None: (query.get(name) or [default])[0]
        idx = self.index
        idx.refresh()
        parts = [unquote(p) for p in path.split("/")[2:]]
        if parts == ["changes"]:
            return self._json(200, {"version": idx.version})
        if parts == ["overview"]:
            return self._json(200, idx.overview(q("project")))
        if parts == ["tasks"]:
            limit = int(q("limit", "50")) if (q("limit") or "50").isdigit() else 50
            return self._json(200, idx.tasks(q("project"), q("status"), q("before"), min(limit, 200)))
        if parts and parts[0] == "task" and len(parts) == 3:
            if not all(_PART.fullmatch(p) and p.strip(".") for p in parts[1:]):
                return self._json(400, {"error": "Not a task."})
            page = int(q("page", "0")) if (q("page") or "0").isdigit() else 0
            t = idx.task(parts[1], parts[2], page)
            return self._json(200, t) if t else self._json(404, {"error": "No such task."})
        if parts == ["projects"]:
            return self._json(200, idx.projects())
        if parts and parts[0] == "project" and len(parts) == 2:
            p = idx.project(parts[1]) if records.valid_project(parts[1]) else None
            return self._json(200, p) if p else self._json(404, {"error": "No such project."})
        if parts == ["export"]:
            return self._json(200, export_status())
        self._send(404)

    def do_POST(self):
        if not self._allowed():
            return
        if self.headers.get("Origin") not in (f"http://127.0.0.1:{self.port}", f"http://localhost:{self.port}"):
            return self._send(403)
        try:
            body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 10_000)) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"error": "Not valid JSON."})
        action = urlsplit(self.path).path
        handler = ACTIONS.get(action)
        if handler is None:
            return self._send(404)
        code, obj = handler(self.index, body if isinstance(body, dict) else {})
        self._json(code, obj)


def export_status():
    """Placeholder until export exists (US3)."""
    return {"on": os.environ.get("LOOPBRAKE_EXPORT") == "otlp"}


_TASK_ID = re.compile(r"[A-Za-z0-9._-]{1,128}/[A-Za-z0-9._-]{1,128}")


def _task_for(index, body):
    tid = body.get("task")
    if not isinstance(tid, str) or not _TASK_ID.fullmatch(tid) or any(p.strip(".") == "" for p in tid.split("/")):
        return None, (400, {"error": "Not a task."})
    index.refresh()
    t = index.tasks_by_id.get(tid)
    return (t, None) if t else (None, (404, {"error": "No such task."}))


def _mark(index, body, verdict):
    """The same effect as /loopbrake:mistake or /loopbrake:exclude for one task (spec FR-005)."""
    t, err = _task_for(index, body)
    if err:
        return err
    state = index._state(t, datetime.now(timezone.utc))
    if verdict == "mistaken_stop" and t["stop_at"] is None:
        return 400, {"error": "Only a stopped task can be marked as a mistake."}
    if verdict == "exclude" and state in ("running", "idle"):
        return 400, {"error": "Wait until this task ends."}
    try:
        records.add_feedback(index.home, t["run"], verdict)
    except ValueError:
        return 409, {"error": "That one is already marked."}
    except LookupError:
        return 404, {"error": "No such task."}
    index.refresh()
    if verdict == "mistaken_stop":
        return 200, {"message": "Marked as a mistake. LoopBrake will count this task as a long good one next time you set the limit."}
    return 200, {"message": "Left out. The next time you set the limit, this task won't count."}


def _recalibrate(index, body):
    name = body.get("project")
    if not isinstance(name, str) or not records.valid_project(name):
        return 400, {"error": "Not a project."}
    folder = index._history(name)
    if folder is None:
        return 400, {"error": f"LoopBrake can't find this project's history from here. Run: loopbrake calibrate <runs file> --project {name}"}
    rec = calibration.calibrate(folder, project=name, home=index.home)
    return 200, {"message": claude_code.calibrate_message(rec)}


ACTIONS = {  # POST path -> handler(index, body) -> (status, json)
    "/api/mistake": lambda index, body: _mark(index, body, "mistaken_stop"),
    "/api/exclude": lambda index, body: _mark(index, body, "exclude"),
    "/api/recalibrate": _recalibrate,
}


def make_server(home=None, port=0, days=None):
    """A ready server bound to 127.0.0.1, and its per-launch key."""
    index = Index(home, days)
    index.refresh()
    handler = type("Handler", (_Handler,), {"index": index, "key": secrets.token_urlsafe(32)})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    server.daemon_threads = True
    handler.port = server.server_address[1]
    return server, handler.key


def serve(port=0, open_browser=True, days=None, home=None):
    server, key = make_server(home, port, days)
    url = f"http://127.0.0.1:{server.server_address[1]}/?k={key}"
    print(f"LoopBrake dashboard: {url}")
    print("Only this computer can open it. Press Ctrl+C to stop.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
