"""Read and write runs. A run is one agent attempt at one task, as a list of steps.

File format: specs/001-offline-eval/contracts/normalized-runs.md (JSON Lines, one run per line).
"""
import json
import re
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
        self.last_stop = None  # why the latest answer stopped; "tool_use" means it's waiting on a tool
        self.hook_stopped = False  # a hook (LoopBrake or another) told Claude to stop: the turn is over

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
        exit = "interrupted" if self.interrupted else "stopped" if self.hook_stopped else None
        ok = exit is None and self.id not in exclude  # killed turns are not successes (constitution 2.4.0)
        return Run(group, "claude-code-local", self.id, self.id, ok, exit, True, steps)


def claude_code_turns(transcript, exclude=(), call_ids=None):
    """Split one Claude Code session transcript into turns.

    A prompt (or a task notification) starts a turn only once the previous turn is over: a record that
    arrives while Claude is still waiting on a tool joins the running turn, as it does live
    (constitution 2.4.0, "Turns"). Compaction summaries never start one.

    Returns (runs, skipped). A turn succeeds when it was not interrupted and is not in `exclude`
    (turn ids: the uuid of the prompt record). When `call_ids` is a dict, it is filled with each
    turn's tool_use ids in step order. The run's group is the project folder name; callers rename it
    before anything leaves the machine (constitution Principle VI).
    """
    group = Path(transcript).parent.name
    runs, skipped, seen_msgs = [], Counter(), set()
    turn = None

    def close(t):
        runs.append(t.run(group, exclude))
        if call_ids is not None:
            call_ids[t.id] = tuple(t.by_call)
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
            if kind == "attachment" and (rec.get("attachment") or {}).get("type") == "hook_stopped_continuation":
                if turn:  # written when a hook replies continue: false; Claude's last answer still says tool_use
                    turn.hook_stopped = True
                continue
            if kind not in ("user", "assistant") or not isinstance(msg, dict):
                skipped["not a message"] += 1
                continue
            content = msg.get("content")
            if kind == "user":
                if rec.get("isMeta") or rec.get("isCompactSummary"):
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
                if turn and not turn.interrupted and not turn.hook_stopped and turn.last_stop == "tool_use":
                    continue  # arrived mid-turn: it joins the running turn
                if turn:
                    close(turn)
                turn = _Turn(rec.get("uuid") or f"turn-{len(runs) + 1}")
                continue
            if turn is None:
                continue  # assistant output before any prompt
            turn.last_stop = msg.get("stop_reason") or turn.last_stop
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
        close(turn)
    return runs, skipped


# ---- Codex session files (specs/006-codex-cli-plugin, research R4 and R10) ----

_EXIT = re.compile(r"exited with code (\d+)")
_CODEX_CALLS = ("function_call", "custom_tool_call", "local_shell_call")


def codex_session_cwd(path):
    """The working folder a Codex session file belongs to (its `session_meta`), or None."""
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("type") == "session_meta":
                return (rec.get("payload") or {}).get("cwd")
    return None


def codex_turns(path, exclude=(), call_ids=None):
    """Split one Codex session file into tasks: the one place that reads Codex's own format
    (constitution Principle V; checked against tests/fixtures/codex_rollout.jsonl).

    A task runs from `task_started` to its `task_complete` (finished) or `turn_aborted` (interrupted),
    both tagged with Codex's turn id, the same id the live hooks see, so tasks match live and here by
    construction. A turn continued under the same root id stays one task. Steps are local tool calls in
    order; hosted tools such as web search never reach a hook live, so they aren't steps here either.

    Returns (runs, skipped). A task succeeds when it finished and its turn id isn't in `exclude`. When
    `call_ids` is a dict, it is filled with each task's call ids in step order (the hooks' tool_use_id).
    """
    group = Path(path).name
    runs, skipped = [], Counter()
    task = None  # [turn id, root id, steps, call ids, by call id]

    def close(exit):
        nonlocal task
        tid, _, steps, ids, _ = task
        if steps:
            ok = exit is None and tid not in exclude
            runs.append(Run(group, "codex-local", tid, tid, ok, exit, False,
                            tuple(Step(s["action"], s["observation"], s["error"], 0) for s in steps)))
            if call_ids is not None:
                call_ids[tid] = tuple(ids)
        task = None

    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                skipped["bad json"] += 1
                continue
            p = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
            kind = p.get("type")
            if rec.get("type") == "event_msg" and kind == "task_started":
                root = p.get("root_turn_id") or p.get("turn_id")
                if task and task[1] == root:
                    continue  # the same task, continued
                if task:
                    close("interrupted")  # a new task began before this one ended
                task = [p.get("turn_id"), root, [], [], {}]
            elif task and rec.get("type") == "event_msg" and kind in ("task_complete", "turn_aborted"):
                close(None if kind == "task_complete" else "interrupted")
            elif task and rec.get("type") == "response_item" and kind in _CODEX_CALLS:
                args = p.get("arguments", p.get("input", p.get("action", "")))
                step = {"action": f"{p.get('name') or kind} {args if isinstance(args, str) else json.dumps(args)}",
                        "observation": "", "error": None}
                task[2].append(step)
                if p.get("call_id"):
                    task[3].append(p["call_id"])
                    task[4][p["call_id"]] = step
            elif task and rec.get("type") == "response_item" and kind in ("function_call_output", "custom_tool_call_output"):
                step = task[4].get(p.get("call_id"))
                if step is not None:
                    out = p.get("output")
                    step["observation"] = out if isinstance(out, str) else json.dumps(out)
                    m = _EXIT.search(step["observation"])
                    step["error"] = None if m is None else m.group(1) != "0"
    return runs, skipped
