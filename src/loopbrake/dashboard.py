"""The local dashboard: a record index, a JSON API and a small web server.

Contracts: specs/005-observability/contracts/dashboard-http.md and ui.md. It reads the records
LoopBrake already writes; its actions reuse the Phase 3 code. It listens on 127.0.0.1 only and the
page loads nothing from anywhere else (constitution, Principle VI and Dashboard security).
"""
import json
import re
import threading
import time
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
