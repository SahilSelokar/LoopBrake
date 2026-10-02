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


def history_folder(cwd=None):
    """Where Claude Code keeps a working folder's history: every non-letter, non-digit becomes '-'."""
    root = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects"
    return root / re.sub(r"[^A-Za-z0-9]", "-", str(cwd or Path.cwd()))


def project_name(folder_name):
    """A LoopBrake project name for a history folder: readable, at most 50 characters, and unique."""
    safe = re.sub(r"[^A-Za-z0-9-]", "-", folder_name).lstrip("-")
    return f"cc-{safe[-40:].strip('-')}-{hashlib.sha256(folder_name.encode()).hexdigest()[:6]}"


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
                start(project, session=session, home=h, unit="turns", traceparent=os.environ.get("TRACEPARENT"))
            return None
        if event == "stop":
            if b:
                b.end()
            return None
        call_id = data.get("tool_use_id")
        if b is not None and call_id and any(e.get("event") == "step" and e.get("call_id") == call_id for e in turn):
            return _stop_reply(b) if b.stopped else None  # the same call reported twice: count it once
        if b is None:  # a step after Stop: work woken by a background task is its own turn
            b = start(project, session=session, home=h, unit="turns", traceparent=os.environ.get("TRACEPARENT"))
        d = b.step(action(data.get("tool_name"), data.get("tool_input")), tool=data.get("tool_name"),
                   error=event == "tool-failed", call_id=call_id, duration_ms=data.get("duration_ms"))
        return _stop_reply(b) if d.stop else None


def _stop_reply(b):
    return json.dumps({"continue": False, "stopReason": stop_message(b)})


def one_in(alpha):
    """alpha in everyday words: 0.05 -> 'fewer than 1 in 20'."""
    k = 1 / alpha
    return f"fewer than 1 in {round(k)}" if abs(k - round(k)) < 1e-9 else f"under {alpha:.0%}"


_SYMPTOMS = (("same error", "same_error", "it keeps hitting the same error"),
             ("repeating", "repeating", "its last few tool calls repeat each other"),
             ("nothing new", "nothing_new", "its last few tool calls turned up nothing new"))


def plain_stop(step, limit, n, alpha, reason, next_step):
    """A stop in plain words (Phase 3 FR-013), from plain values, so the hook, the dashboard and export
    share it. `next_step` is the closing sentence, which differs per surface."""
    based = f"Based on your {n} past successful tasks in this project, good" if n else "Good"
    text = (f"LoopBrake stopped this task after {step} tool calls. {based} tasks almost never need more "
            f"than {limit} ({one_in(alpha or 0.05)} do).")
    symptom = next((plain for key, _, plain in _SYMPTOMS if key in (reason or "")), None)
    if symptom:
        text += f" This one also looks stuck: {symptom}."
    return text + next_step


def reason_codes(reason):
    """Short codes for a stop, for export: past_limit, then any explanation signals that fired."""
    return ["past_limit"] + [code for key, code, _ in _SYMPTOMS if key in (reason or "")]


def stop_message(b):
    """What the user reads in Claude Code when a task is stopped (contracts/hooks.md)."""
    cal = b.calibration or {}
    return plain_stop(b.stop_step, b.stop_line, cal.get("n"), cal.get("alpha"), b.reason,
                      " If it wasn't stuck, run /loopbrake:mistake, then tell Claude to continue.")


# ---- status line (contracts/cli.md) ----

IDLE = "LoopBrake: ready"

def statusline(stdin_text, home=None):
    """One short line for Claude Code's status line. Reads the session's log without a lock and never
    writes or raises."""
    try:
        session = json.loads(stdin_text).get("session_id")
        if not isinstance(session, str) or not _SESSION.fullmatch(session) or session in (".", ".."):
            return IDLE
        turn = records.open_turn(records.session_events(records.home(home), session))
        if not turn:
            return IDLE
        cal = turn[0].get("calibration") or {}
        stop = next((e for e in turn if e.get("event") == "stop"), None)
        if stop:
            return f"LoopBrake: stopped this task at {stop.get('step')} tool calls"
        count = sum(e.get("event") == "step" for e in turn)
        line = cal.get("stop_line")
        if cal.get("watch_only", True) or line is None:
            return f"LoopBrake: {_n(count, 'tool call')} (watching only)"
        return f"LoopBrake: {count} of {line} tool calls"
    except Exception:
        return IDLE


# ---- live vs calibration agreement (spec SC-008) ----

def agreement(cwd=None, home=None):
    """Compare each live turn's step count with the transcript turn holding its first tool call.

    Returns (lines to print, how many live counts were higher). A higher live count would mean the
    brake counts more than calibration saw: a bug to fix before release (constitution 2.4.0)."""
    from loopbrake.traces import claude_code_turns
    h = records.home(home)
    folder = history_folder(cwd)
    if not folder.is_dir():
        raise FileNotFoundError(f"no Claude Code history for this folder at {folder}")
    project = project_name(folder.name)
    length = {}  # tool call id -> its transcript turn's step count
    for f in sorted(folder.glob("*.jsonl")):
        ids = {}
        for r in claude_code_turns(f, call_ids=ids)[0]:
            length.update({c: len(r.steps) for c in ids.get(r.run, ())})
    runs, calls = [], {}
    for e in records.read_events(h):
        if e.get("event") == "run_start" and e.get("project") == project:
            runs.append(e.get("run"))
        elif e.get("event") == "step" and e.get("call_id"):
            calls.setdefault(e.get("run"), []).append(e["call_id"])
    lines, counts = [], {"equal": 0, "lower": 0, "higher": 0, "unmatched": 0}
    for run in runs:
        live = calls.get(run)
        if not live:
            continue
        seen = length.get(live[0])
        kind = "unmatched" if seen is None else "equal" if len(live) == seen else "lower" if len(live) < seen else "higher"
        counts[kind] += 1
        if kind == "higher":
            lines.append(f"higher  run {run}  live {len(live)}  transcript {seen}")
    matched = counts["equal"] + counts["lower"] + counts["higher"]
    summary = f"turns matched {matched}, equal {counts['equal']}, live lower {counts['lower']}, live higher {counts['higher']}"
    lines.append(summary + (f", unmatched {counts['unmatched']}" if counts["unmatched"] else ""))
    return lines, counts["higher"]


# ---- what the slash commands print, in plain words (contracts/cli.md) ----

def _n(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def calibrate_message(rec):
    src, alpha = rec["source"], rec["alpha"]
    left, mistakes = src.get("stops_left_out", 0), src.get("mistakes_counted", 0)
    if rec["watch_only"]:
        needed = calibration.runs_needed(alpha, mistakes)
        lines = [f"Not enough history yet: LoopBrake found {_n(rec['n'], 'successful past task')} in this project and needs {needed}.",
                 "Until then it only watches and never stops anything. Run /loopbrake:calibrate again after more work here."]
        if mistakes:
            lines.append(f"(It needs more than the usual {calibration.runs_needed(alpha)} because each stop you marked as a "
                         "mistake counts as a very long good task.)")
    else:
        lines = ["LoopBrake is set up for this project.",
                 f"It will stop a task that goes past {rec['stop_line']} tool calls. That limit comes from your "
                 f"{_n(rec['n'], 'past successful task')} here: {one_in(alpha)} good tasks should go past it."]
    if left:
        lines.append(f"Left out: {_n(left, 'task')} that LoopBrake stopped as stuck or that you excluded.")
    if mistakes:
        lines.append(f"Counted as long good tasks: {_n(mistakes, 'stop')} you marked as a mistake.")
    return "\n".join(lines)


def status_message(rec, st):
    lines = ["LoopBrake in this project:"]
    if rec is None:
        lines.append("  Stop line: not set yet, so LoopBrake only watches. Run /loopbrake:calibrate to set it.")
    elif rec["watch_only"]:
        needed = calibration.runs_needed(rec["alpha"], rec["source"].get("mistakes_counted", 0))
        lines.append(f"  Stop line: not set yet, only watching ({_n(rec['n'], 'successful past task')} found, {needed} needed).")
    else:
        lines.append(f"  Stop line: {rec['stop_line']} tool calls per task (set {rec['created']} from {_n(rec['n'], 'past successful task')}).")
    lines += [f"  Tasks seen: {st['runs']} (the stop line was on for {st['watched']})",
              f"  Tasks stopped: {st['stopped']}",
              f"  Stops you marked as mistakes: {st['mistaken']} (up to about {st['allowance']:.1f} would be normal by now)"]
    if rec is not None and st["runs"] == 0:
        lines.append("  No tasks recorded here yet. If you've used Claude Code in this folder since installing LoopBrake, "
                     "its hooks may not be running (see Troubleshooting in the README).")
    return "\n".join(lines)
