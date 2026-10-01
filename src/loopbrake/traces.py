"""Read and write runs. A run is one agent attempt at one task, as a list of steps.

File format: specs/001-offline-eval/contracts/normalized-runs.md (JSON Lines, one run per line).
"""
import json
from collections import Counter
from pathlib import Path
from typing import NamedTuple

from loopbrake.signals import Step


class Run(NamedTuple):
    group: str
    dataset: str
    task: str
    run: str
    success: bool
    exit: str | None
    tokens_measured: bool
    steps: tuple  # of Step, in order, never empty


def write_runs(path, runs):
    with open(path, "w", encoding="utf-8") as f:
        for r in runs:
            d = r._asdict()
            d["steps"] = [s._asdict() for s in r.steps]
            f.write(json.dumps(d, ensure_ascii=False) + "\n")


def read_runs(path):
    """Returns (runs, skipped). A bad line is skipped and counted by reason; it never raises."""
    runs, skipped = [], Counter()
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                skipped["bad json"] += 1
                continue
            problem = _problem(d)
            if problem:
                skipped[problem] += 1
                continue
            steps = tuple(Step(s["action"], s["observation"], s["error"], s["tokens"]) for s in d["steps"])
            runs.append(Run(d["group"], d["dataset"], d["task"], d["run"], d["success"], d["exit"], d["tokens_measured"], steps))
    return runs, skipped


def _problem(d):
    if not isinstance(d, dict) or not all(isinstance(d.get(k), str) for k in ("group", "dataset", "task", "run")):
        return "bad field"
    if not isinstance(d.get("success"), bool) or not isinstance(d.get("tokens_measured"), bool):
        return "bad field"
    if d.get("exit") is not None and not isinstance(d["exit"], str):
        return "bad field"
    steps = d.get("steps")
    if not isinstance(steps, list) or not steps:
        return "no steps"
    for s in steps:
        if not isinstance(s, dict) or not isinstance(s.get("observation"), str):
            return "bad field"
        if not isinstance(s.get("action"), str) or not s["action"]:
            return "empty action"
        tokens = s.get("tokens")
        if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens < 0:
            return "bad tokens"
        if "error" not in s or (s["error"] is not None and not isinstance(s["error"], bool)):
            return "bad error flag"  # isinstance, because 1 == True would sneak past an `in` check
    return None


# ---------- Claude Code session transcripts (research R10) ----------
# The format is internal to Claude Code and can change between releases, so this is the only
# function that reads it, and tests/fixtures/claude_code_session.jsonl pins what it expects.

INTERRUPTED = "[Request interrupted by user"


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _usage_tokens(usage):
    """Every token the call read or wrote, cached or not: what the turn really consumed."""
    keys = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
    return sum(usage.get(k) or 0 for k in keys) if isinstance(usage, dict) else 0


class _Turn:
    def __init__(self, turn_id):
        self.id, self.steps, self.by_call = turn_id, [], {}
        self.interrupted, self.pending = False, 0
        self.msg, self.msg_tokens, self.msg_charged = None, 0, True

    def add_tokens(self, n):  # to the previous step, or held for the first one
        if self.steps:
            self.steps[-1]["tokens"] += n
        else:
            self.pending += n

    def close_message(self):  # a response that called no tool: its tokens go to the step before it
        if self.msg is not None and not self.msg_charged:
            self.add_tokens(self.msg_tokens)
        self.msg_charged = True

    def run(self, group, exclude):
        self.close_message()
        steps = tuple(Step(s["action"], s["observation"], s["error"], s["tokens"]) for s in self.steps)
        exit = "interrupted" if self.interrupted else None
        return Run(group, "claude-code-local", self.id, self.id, not self.interrupted and self.id not in exclude, exit, True, steps)


def claude_code_turns(transcript, exclude=()):
    """Split one Claude Code session transcript into turns, one Run per user prompt.

    Returns (runs, skipped). A turn succeeds when it was not interrupted and is not in `exclude`
    (turn ids: the uuid of the prompt record). The run's group is the project folder name; callers
    rename it before anything leaves the machine (constitution Principle VI).
    """
    group = Path(transcript).parent.name
    runs, skipped, seen_msgs = [], Counter(), set()
    turn = None
    with open(transcript, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                skipped["bad json"] += 1
                continue
            if rec.get("isSidechain"):
                skipped["sidechain"] += 1
                continue
            kind, msg = rec.get("type"), rec.get("message")
            if kind not in ("user", "assistant") or not isinstance(msg, dict):
                skipped["not a message"] += 1
                continue
            content = msg.get("content")
            if kind == "user":
                if rec.get("isMeta"):
                    continue
                results = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"] if isinstance(content, list) else []
                if results:
                    for b in results:
                        step = turn.by_call.get(b.get("tool_use_id")) if turn else None
                        if step is not None:
                            step["observation"] = _text(b.get("content"))
                            step["error"] = bool(b.get("is_error", False))
                    continue
                text = _text(content)
                if text.startswith(INTERRUPTED):
                    if turn:
                        turn.interrupted = True
                    continue
                if text.startswith("<local-command"):
                    continue
                if turn:
                    runs.append(turn.run(group, exclude))
                turn = _Turn(rec.get("uuid") or f"turn-{len(runs) + 1}")
                continue
            if turn is None:
                continue  # assistant output before any prompt
            mid = msg.get("id")
            if mid != turn.msg:
                turn.close_message()
                turn.msg, turn.msg_charged = mid, False
                turn.msg_tokens = 0 if mid in seen_msgs else _usage_tokens(msg.get("usage"))
                seen_msgs.add(mid)  # one response is split across records that repeat its usage
            for b in content if isinstance(content, list) else []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    tokens = 0 if turn.msg_charged else turn.msg_tokens + turn.pending
                    turn.msg_charged, turn.pending = True, 0
                    step = {"action": f"{b.get('name')} {json.dumps(b.get('input') or {}, sort_keys=True, ensure_ascii=False)}",
                            "observation": "", "error": None, "tokens": tokens}
                    turn.steps.append(step)
                    turn.by_call[b.get("id")] = step
    if turn:
        runs.append(turn.run(group, exclude))
    return runs, skipped
