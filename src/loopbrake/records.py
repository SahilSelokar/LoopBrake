"""Local records: where LoopBrake keeps run records and the exclude list, and how status is read back.

Format: specs/003-core-package/contracts/records.md. Nothing here touches the network (Principle VI).
"""
import json
import os
import re
import warnings
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # ponytail: no lock on Windows; untested platform in v1
    fcntl = None

_PROJECT = re.compile(r"[A-Za-z0-9._-]{1,64}")
VERDICTS = ("mistaken_stop", "exclude")


def home(path=None):
    """The LoopBrake folder: `path`, else $LOOPBRAKE_HOME, else ~/.loopbrake."""
    return Path(path or os.environ.get("LOOPBRAKE_HOME") or Path.home() / ".loopbrake")


def valid_project(name):
    """Project names become file names, so only plain characters are allowed."""
    return isinstance(name, str) and bool(_PROJECT.fullmatch(name)) and name not in (".", "..")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RunWriter:
    """Appends one event per line, readable only by the owner. If a write fails, recording turns off
    for this writer; it never raises, so it can't hurt the agent being watched (spec FR-005)."""

    def __init__(self, path):
        self.path, self.on = Path(path), True

    def write(self, event):
        if not self.on:
            return
        line = (json.dumps({"v": 1, "ts": _now()} | event, ensure_ascii=False) + "\n").encode()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                os.write(fd, line)  # one write per line, so parallel runs don't interleave
            finally:
                os.close(fd)
        except OSError as e:
            self.on = False
            warnings.warn(f"loopbrake: can't write run records ({e}); recording is off for this run", RuntimeWarning, stacklevel=3)


def _files(h):
    return sorted((h / "runs").glob("*.jsonl")) if (h / "runs").exists() else []


def read_events(h):
    for path in _files(h):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                yield json.loads(line) | {"_file": path}
            except json.JSONDecodeError:
                continue


def status(h, project=None):
    """Runs, runs watched with a stop line, stops, stops marked mistaken, and the allowance (α × watched)."""
    events = list(read_events(h))
    starts = {e["run"]: e for e in events if e.get("event") == "run_start" and (project is None or e.get("project") == project)}
    watched = {r: e for r, e in starts.items() if not (e.get("calibration") or {}).get("watch_only", True)}
    stopped = {e["run"] for e in events if e.get("event") == "stop" and e.get("run") in starts}
    mistaken = {e["run"] for e in events if e.get("event") == "feedback" and e.get("verdict") == "mistaken_stop" and e.get("run") in starts}
    return {
        "runs": len(starts),
        "watched": len(watched),
        "stopped": len(stopped),
        "mistaken": len(mistaken),
        "allowance": sum(e["calibration"].get("alpha", 0) for e in watched.values()),
    }


# ---- a session's log as the live state of its open run (Phase 3, research R4) ----

@contextmanager
def session_lock(h, session):
    """Hold an exclusive lock on runs/<session>.jsonl, so parallel hook processes take turns."""
    path = h / "runs" / f"{session}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        if fcntl:
            fcntl.flock(fd, fcntl.LOCK_EX)
        yield path
    finally:
        os.close(fd)  # closing releases the lock


def session_events(h, session):
    """The events of one session from its last run_start on (all of them if it has none). Bad lines
    are skipped. Only the open run is parsed, so the cost stays small as the session grows."""
    try:
        lines = (h / "runs" / f"{session}.jsonl").read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    start = next((i for i in range(len(lines) - 1, -1, -1) if '"event": "run_start"' in lines[i]), 0)
    out = []
    for line in lines[start:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def open_turn(events):
    """The open run's events (its run_start first), or None when the last run has ended."""
    starts = [i for i, e in enumerate(events) if e.get("event") == "run_start"]
    if not starts:
        return None
    run = events[starts[-1]].get("run")
    rest = [e for e in events[starts[-1]:] if e.get("run") == run]
    return None if any(e.get("event") == "run_end" for e in rest) else rest


def last_run(h, event, min_steps=0):
    """(run_start, event) for the most recent `event` across every session, or None.

    With min_steps, run_end events of shorter runs are skipped."""
    best, starts = None, {}
    for path in _files(h):
        mtime = path.stat().st_mtime_ns
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("event") == "run_start":
                starts[e.get("run")] = e
            if e.get("event") != event or (min_steps and (e.get("steps") or 0) < min_steps):
                continue
            key = (e.get("ts", ""), mtime, i)
            if e.get("run") in starts and (best is None or key > best[0]):
                best = (key, starts[e["run"]], e)
    return best and best[1:]


def add_feedback(h, run, verdict):
    """Record that a stop was a mistake, or that a run should be left out of future calibration."""
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}")
    start = next((e for e in read_events(h) if e.get("event") == "run_start" and e.get("run") == run), None)
    if start is None:
        raise LookupError(f"no run {run!r} in {h / 'runs'}")
    RunWriter(start["_file"]).write({"event": "feedback", "session": start.get("session"), "run": run, "verdict": verdict})
    if verdict == "exclude":
        add_exclude(h, run)


def read_exclude(h):
    path = h / "exclude.txt"
    return set(path.read_text().split()) if path.exists() else set()


def add_exclude(h, run_id):
    if run_id not in read_exclude(h):
        h.mkdir(parents=True, exist_ok=True)
        with open(h / "exclude.txt", "a", encoding="utf-8") as f:
            f.write(run_id + "\n")
