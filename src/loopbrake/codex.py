"""The Codex CLI adapter: Codex's hook events in, Brake calls through, Codex replies out.

Contracts: specs/006-codex-cli-plugin/contracts/hooks.md and plugin.md; Codex's behavior as the probe
found it (research R10). Like the Claude Code adapter it holds no stop logic of its own (constitution
Principle V): every decision is Brake.step().
"""
import hashlib
import json
import re
import sys
import warnings
from pathlib import Path

from loopbrake import claude_code, records
from loopbrake.brake import Brake, start

EVENTS = ("prompt", "pre-tool", "tool", "stop", "interrupt", "subagent-start", "subagent-stop")
_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")
NEXT_STEP = ' If it wasn\'t stuck, send "loopbrake: mistake", then tell Codex to continue.'


def project_name(cwd):
    """A LoopBrake project for a Codex working folder: readable, at most 53 characters, and unique.
    Built like the Claude Code `cc-` names, so the same folder gives two separate projects."""
    safe = re.sub(r"[^A-Za-z0-9-]", "-", str(cwd)).strip("-")
    return f"codex-{safe[-40:].strip('-')}-{hashlib.sha256(str(cwd).encode()).hexdigest()[:6]}"


# ---- hooks (contracts/hooks.md) ----

def hook(event, stdin_text, home=None):
    """One Codex hook call. Returns the JSON to print, or None. Never raises and never blocks: any
    failure becomes one stderr line, and an empty reply means "nothing to say" to Codex."""
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            out = _hook(event, stdin_text, records.home(home))
        for w in caught:
            claude_code._say(str(w.message))
        return json.dumps(out) if out else None
    except Exception as e:
        claude_code._say(f"loopbrake: codex hook {event}: {type(e).__name__}: {e}")
        return None


def _valid(value):
    return isinstance(value, str) and bool(_ID.fullmatch(value)) and value not in (".", "..")


def _helper(data, turn):
    """A helper agent's call: it comes from another transcript, or while a helper of this task runs.
    Either test can only lower the count, which can only stop later (the safe side)."""
    own = turn[0].get("transcript")
    if own and data.get("transcript_path") and data["transcript_path"] != own:
        return True
    running = set()
    for e in turn:
        if e.get("event") == "helper":
            (running.add if e.get("state") == "start" else running.discard)(e.get("agent_id"))
    return bool(running)


def _stop_text(b):
    cal = b.calibration or {}
    return claude_code.plain_stop(b.stop_step, b.stop_line, cal.get("n"), cal.get("alpha"), b.reason, NEXT_STEP)


def _hook(event, text, h):
    event = event.removeprefix("codex-")  # the hook commands say `loopbrake hook codex-<event>`
    if event not in EVENTS:
        return None
    data = json.loads(text)
    if not isinstance(data, dict) or not _valid(data.get("session_id")) or not isinstance(data.get("turn_id"), str):
        return None
    session, turn_id, cwd = data["session_id"], data["turn_id"], data.get("cwd") or ""
    project = project_name(cwd)
    with records.session_lock(h, session):
        turn = records.open_turn(records.session_events(h, session))
        b = Brake.from_events(project, session, h, turn, unit="turns") if turn else None
        same = b is not None and turn[0].get("turn_id") == turn_id
        if event == "prompt":
            if same:
                return None  # the same message reported twice
            if b is not None:
                b.end("stopped" if b.stopped else "interrupted")  # no Stop came for it
            start(project, session=session, home=h, unit="turns", extra=_fields(data))
            return None
        if not same:
            return None  # no open task for this turn (for example, hooks trusted in the middle of one)
        if event == "pre-tool":
            return _deny(_stop_text(b)) if b.stopped else None
        if event == "tool":
            call_id = data.get("tool_use_id")
            if _helper(data, turn) or (call_id and any(e.get("event") == "step" and e.get("call_id") == call_id for e in turn)):
                return None
            was_stopped = b.stopped
            d = b.step(claude_code.action(data.get("tool_name"), data.get("tool_input")), tool=data.get("tool_name"), call_id=call_id)
            return _stop(_stop_text(b)) if d.stop and not was_stopped else None
        if event in ("stop", "interrupt"):
            b.end("stopped" if b.stopped else "finished" if event == "stop" else "interrupted")
            return None
        records.RunWriter(h / "runs" / f"{session}.jsonl").write(  # a helper starts or ends
            {"event": "helper", "session": session, "run": b.run, "agent_id": data.get("agent_id"),
             "state": "start" if event == "subagent-start" else "stop"})
        return None


def _fields(data):
    """What a Codex task's start records besides the usual (data-model.md). Local only: export reads
    neither `transcript` nor `folder`."""
    out = {"turn_id": data["turn_id"], "folder": Path(data.get("cwd") or "").name}
    if isinstance(data.get("transcript_path"), str):
        out["transcript"] = data["transcript_path"]
    return out


def _stop(text):
    return {"continue": False, "stopReason": text, "systemMessage": text}


def _deny(text):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": text}}


if __name__ == "__main__":  # pragma: no cover - for trying a hook by hand
    print(hook(sys.argv[1], sys.stdin.read()) or "")
