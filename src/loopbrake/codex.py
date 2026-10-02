"""The Codex CLI adapter: Codex's hook events in, Brake calls through, Codex replies out.

Contracts: specs/006-codex-cli-plugin/contracts/hooks.md and plugin.md; Codex's behavior as the probe
found it (research R10). Like the Claude Code adapter it holds no stop logic of its own (constitution
Principle V): every decision is Brake.step().
"""
import hashlib
import json
import os
import re
import sys
import warnings
from pathlib import Path

from loopbrake import calibration, claude_code, records
from loopbrake.brake import Brake, start

EVENTS = ("prompt", "pre-tool", "tool", "stop", "interrupt", "subagent-start", "subagent-stop")
_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")
NEXT_STEP = ' If it wasn\'t stuck, send "loopbrake: mistake", then tell Codex to continue.'


def project_name(cwd):
    """A LoopBrake project for a Codex working folder: readable, at most 53 characters, and unique.
    Built like the Claude Code `cc-` names, so the same folder gives two separate projects."""
    safe = re.sub(r"[^A-Za-z0-9-]", "-", str(cwd)).strip("-")
    return f"codex-{safe[-40:].strip('-')}-{hashlib.sha256(str(cwd).encode()).hexdigest()[:6]}"


# ---- learning the limit from Codex history (contracts/cli.md) ----

def sessions_root():
    """Where Codex keeps its session files: $CODEX_HOME/sessions, or ~/.codex/sessions."""
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "sessions"


def history_files(cwd):
    """This folder's Codex session files, oldest first (each file names its folder in session_meta)."""
    from loopbrake.traces import codex_session_cwd
    root = sessions_root()
    files = sorted(root.rglob("rollout-*.jsonl")) if root.is_dir() else []
    return [f for f in files if codex_session_cwd(f) == str(cwd)]


def calibrate_codex(cwd=None, *, alpha=0.05, home=None):
    """Set the limit for the Codex project of a working folder, from its own Codex history."""
    cwd = str(cwd or Path.cwd())
    files = history_files(cwd)
    if not files:
        raise FileNotFoundError(f"no Codex history for this folder in {sessions_root()}; use Codex here for a while first")
    return calibration.calibrate_codex(files, project=project_name(cwd), alpha=alpha, home=home)


# ---- what Codex users read: Claude Code's wording, with Codex's commands ----

CAL = '"loopbrake: calibrate"'
AGAIN = f"Send {CAL} again after more work here."
HOW = f"Send {CAL} to set it."
NOTHING = ("No tasks recorded here yet. If you've used Codex in this folder since installing LoopBrake, open /hooks "
           "in Codex and trust LoopBrake's hooks: Codex skips hooks it hasn't been told to trust, without a word.")


def calibrate_text(cwd=None, *, alpha=0.05, home=None):
    return claude_code.calibrate_message(calibrate_codex(cwd, alpha=alpha, home=home), again=AGAIN)


def status_text(cwd=None, *, home=None):
    h = records.home(home)
    project = project_name(str(cwd or Path.cwd()))
    return claude_code.status_message(calibration.load(project, h), records.status(h, project), how=HOW, nothing=NOTHING)


def agreement(cwd=None, home=None):
    """Live Codex tasks against the history task holding their first call id (constitution: live
    higher must be 0 before a release)."""
    from loopbrake.traces import codex_turns
    cwd = str(cwd or Path.cwd())
    files = history_files(cwd)
    if not files:
        raise FileNotFoundError(f"no Codex history for this folder in {sessions_root()}")
    length = {}
    for f in files:
        ids = {}
        for r in codex_turns(f, call_ids=ids)[0]:
            length.update({c: len(r.steps) for c in ids.get(r.run, ())})
    return claude_code.compare_live(project_name(cwd), length, records.home(home))


# ---- the commands, typed as a message (contracts/plugin.md, research R10) ----

COMMANDS = ("calibrate", "status", "mistake", "exclude", "dashboard", "dashboard stop", "help")
_COMMAND = re.compile(r"\s*loopbrake:?\s+(.+?)\s*", re.I | re.S)
PREAMBLE = ("LoopBrake ran the user's command and printed the text below. Repeat it to the user exactly as printed, "
            "adding nothing, and call no tools.\n\n")


def command(prompt):
    """The LoopBrake command a message is, or None: the whole message, any case, colon optional."""
    m = _COMMAND.fullmatch(prompt) if isinstance(prompt, str) else None
    name = " ".join(m.group(1).lower().split()) if m else None
    return name if name in COMMANDS else None


def run_command(name, cwd, h):
    """Run a typed command outside Codex's sandbox (this is the prompt hook) and return what it printed."""
    import contextlib
    import io

    from loopbrake import cli, dashboard
    if name == "help":
        return ("LoopBrake commands for Codex. Send one as your whole message:\n"
                "  loopbrake: calibrate        set this project's limit from its past Codex tasks\n"
                "  loopbrake: status           the limit, tasks seen and stopped, and mistakes\n"
                "  loopbrake: mistake          the last stop was wrong: the limit can only go up\n"
                "  loopbrake: exclude          leave the last finished task out of future limits\n"
                "  loopbrake: dashboard        open the dashboard in your browser\n"
                "  loopbrake: dashboard stop   stop the dashboard")
    if name == "calibrate":
        try:
            return calibrate_text(cwd, home=h)
        except FileNotFoundError as e:
            return f"LoopBrake: {e}"
    if name == "status":
        return status_text(cwd, home=h)
    if name == "dashboard stop":
        return "Stopped the LoopBrake dashboard." if dashboard.stop(h) else "No LoopBrake dashboard is running."
    if name == "dashboard":
        info = dashboard.start_background(home=h)
        if info is None:
            return "The LoopBrake dashboard didn't start. Run loopbrake dashboard in a terminal to see why."
        return (f"LoopBrake dashboard: {info['url']}\nIt's open in your browser and keeps running in the background; "
                'only this computer can open it. To stop it, send "loopbrake: dashboard stop".')
    out = io.StringIO()  # mistake and exclude: the Claude Code command's words, with Codex's command
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        verdict = "mistaken_stop" if name == "mistake" else "exclude"
        cli._feedback_last(h, name == "mistake", verdict, cal=CAL, verb="send")
    return out.getvalue().strip().removeprefix("loopbrake: ").capitalize()


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


def _ahead_text(b):
    """For a call refused because the calls already on their way reach the limit."""
    cal = b.calibration or {}
    return claude_code.plain_stop(b.stop_line + 1, b.stop_line, cal.get("n"), cal.get("alpha"), "", NEXT_STEP)


def _hook(event, text, h):
    event = event.removeprefix("codex-")  # the hook commands say `loopbrake hook codex-<event>`
    if event not in EVENTS:
        return None
    data = json.loads(text)
    if not isinstance(data, dict) or not _valid(data.get("session_id")) or not isinstance(data.get("turn_id"), str):
        return None
    session, turn_id, cwd = data["session_id"], data["turn_id"], data.get("cwd") or ""
    if event == "prompt" and (name := command(data.get("prompt"))):  # a command opens no task
        return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                       "additionalContext": PREAMBLE + run_command(name, cwd, h)}}
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
            if b.stopped:
                return _deny(_stop_text(b))
            if b.stop_line is None:
                return None  # watching only: nothing to refuse, nothing to record
            # Codex approves a batch of parallel calls before any of them runs: count the ones approved
            # since the last finished call, and refuse those that would only run after the stop.
            last = max((i for i, e in enumerate(turn) if e.get("event") == "step"), default=0)
            pending = sum(e.get("event") == "approve" for e in turn[last:])
            if b.would_stop(pending):
                return _deny(_ahead_text(b))
            records.RunWriter(h / "runs" / f"{session}.jsonl").write(
                {"event": "approve", "session": session, "run": b.run, "call_id": data.get("tool_use_id")})
            return None
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
