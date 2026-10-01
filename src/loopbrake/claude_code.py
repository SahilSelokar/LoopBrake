"""The Claude Code adapter: hook events in, Brake calls through, Claude Code replies out.

Contracts: specs/004-claude-code-plugin/contracts/hooks.md and cli.md. It holds no stop logic of its
own (constitution Principle V): every decision is Brake.step().
"""
import hashlib
import json
import os
import re
import sys
import warnings
from pathlib import Path

from loopbrake import calibration, records
from loopbrake.brake import Brake, start

EVENTS = ("prompt", "tool", "tool-failed", "stop")
_SESSION = re.compile(r"[A-Za-z0-9._-]{1,128}")
MISTAKE_HINT = ". If this stop was wrong, run /loopbrake:mistake."


def history_folder(cwd=None):
    """Where Claude Code keeps a working folder's history: every non-letter, non-digit becomes '-'."""
    root = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects"
    return root / re.sub(r"[^A-Za-z0-9]", "-", str(cwd or Path.cwd()))


def project_name(folder_name):
    """A LoopBrake project name for a history folder: readable, at most 50 characters, and unique."""
    safe = re.sub(r"[^A-Za-z0-9-]", "-", folder_name).lstrip("-")
    return f"cc-{safe[-40:]}-{hashlib.sha256(folder_name.encode()).hexdigest()[:6]}"


def calibrate_claude_code(cwd=None, *, alpha=0.05, home=None):
    """Set the stop line for the Claude Code project of a working folder, from its own history."""
    folder = history_folder(cwd)
    if not folder.is_dir():
        raise FileNotFoundError(f"no Claude Code history for this folder at {folder}; "
                                "run loopbrake calibrate <folder> --project <name>")
    return calibration.calibrate(folder, project=project_name(folder.name), alpha=alpha, home=home)


def action(tool_name, tool_input):
    """The step's action, in exactly the calibration reader's format."""
    return f"{tool_name} {json.dumps(tool_input or {}, sort_keys=True, ensure_ascii=False)}"


# ---- hooks (contracts/hooks.md) ----

def hook(event, stdin_text, home=None):
    """One Claude Code hook call. Returns the JSON to print, or None. Never raises and never blocks:
    any failure becomes one stderr line (constitution 2.4.0, "Failing safely")."""
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            out = _hook(event, stdin_text, records.home(home))
        for w in caught:
            _say(str(w.message))
        return out
    except Exception as e:
        if os.environ.get("LOOPBRAKE_DEBUG") == "1":
            raise
        _say(f"loopbrake: hook {event}: {type(e).__name__}: {e}")
        return None


def _say(line):
    print(" ".join(str(line).split()), file=sys.stderr)


def _session(data):
    """(session, project) for a main-agent event, or None for one to ignore."""
    if not isinstance(data, dict) or data.get("agent_id"):
        return None  # a subagent's call: calibration ignores subagents too
    session, transcript = data.get("session_id"), data.get("transcript_path")
    if not isinstance(session, str) or not _SESSION.fullmatch(session) or session in (".", "..") or not transcript:
        return None
    return session, project_name(Path(transcript).parent.name)


def _hook(event, text, h):
    if event not in EVENTS:
        return None
    data = json.loads(text)
    found = _session(data)
    if found is None:
        return None
    session, project = found
    with records.session_lock(h, session):
        turn = records.open_turn(records.session_events(h, session))
        b = Brake.from_events(project, session, h, turn, unit="turns") if turn else None
        if event == "prompt":
            if b and (b.steps or b.stopped):
                b.end("stopped" if b.stopped else "interrupted")
                b = None
            if b is None:  # an open turn with no steps is kept, so a second prompt event is harmless
                start(project, session=session, home=h, unit="turns")
            return None
        if event == "stop":
            if b:
                b.end()
            return None
        if b is None:  # a step after Stop: work woken by a background task is its own turn
            b = start(project, session=session, home=h, unit="turns")
        d = b.step(action(data.get("tool_name"), data.get("tool_input")), tool=data.get("tool_name"),
                   error=event == "tool-failed", call_id=data.get("tool_use_id"))
        if d.stop:
            return json.dumps({"continue": False, "stopReason": f"LoopBrake {d.reason}{MISTAKE_HINT}"})
        return None


# ---- status line (contracts/cli.md) ----

def statusline(stdin_text, home=None):
    """One short line for Claude Code's status line. Reads the session's log without a lock and never
    writes or raises."""
    try:
        session = json.loads(stdin_text).get("session_id")
        if not isinstance(session, str) or not _SESSION.fullmatch(session) or session in (".", ".."):
            return "brake idle"
        turn = records.open_turn(records.session_events(records.home(home), session))
        if not turn:
            return "brake idle"
        cal = turn[0].get("calibration") or {}
        stop = next((e for e in turn if e.get("event") == "stop"), None)
        if stop:
            return f"brake stopped at {stop.get('step')}"
        count = sum(e.get("event") == "step" for e in turn)
        line = cal.get("stop_line")
        return f"brake {count} (watching)" if cal.get("watch_only", True) or line is None else f"brake {count}/{line}"
    except Exception:
        return "brake idle"
