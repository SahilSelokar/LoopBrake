"""Stuck scores. A method turns a run's steps into one (score, reason) pair per step.

Rules (constitution Principle II): a scorer looks only at the steps it is given, always gives
the same output for the same input, and keeps nothing between calls.
"""
import re
from collections import defaultdict
from functools import partial
from typing import NamedTuple


class Step(NamedTuple):
    action: str  # what the agent did, e.g. 'bash {"command": "ls"}'
    observation: str  # what came back; may be empty
    error: bool | None  # True/False when the source says so, None when unknown
    tokens: int  # tokens billed for the model call that produced this step


def _short(text, n=80):
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


# ---------- simple methods (research R5) ----------


def _fixed(steps):
    """The original liveness.py rule: stop on the 3rd identical action, or at step 21."""
    seen = defaultdict(list)
    out = []
    for t, s in enumerate(steps, 1):
        seen[s.action].append(t)
        count = len(seen[s.action])
        if t > 20:
            reason = "step limit of 20 reached"
        elif count >= 3:
            reason = f"same action seen {count} times (steps {', '.join(map(str, seen[s.action][-3:]))})"
        else:
            reason = ""
        out.append((max(count / 3, t / 21), reason))
    return out


def _exact(steps):
    """Most times any single action has been repeated so far."""
    seen = defaultdict(int)
    top, top_action, out = 0, "", []
    for s in steps:
        seen[s.action] += 1
        if seen[s.action] > top:
            top, top_action = seen[s.action], s.action
        out.append((top, f"same action {top} times: {_short(top_action)}"))
    return out


def _steps(steps):
    """How long the run has gone on (FailFast's "Duration" control)."""
    return [(t, f"step {t}") for t in range(1, len(steps) + 1)]


_BASELINE_SCORERS = {"fixed": _fixed, "exact": _exact, "steps": _steps}


# ---------- stuck signals (research R6): each gives a value from 0 to 1 per step ----------

WINDOW = 10  # a repeat is checked against this many previous actions
RECENT = 5  # reasons describe this many latest steps
_WORD = re.compile(r"[a-z0-9_]+")
_DIGITS = re.compile(r"\d+")
_ERROR_WORDS = re.compile(r"error|exception|traceback|not found|no such file", re.IGNORECASE)


def _norm(line):
    """Collapse spaces and turn every number into 0, so timestamps and counters don't look new."""
    return _DIGITS.sub("0", " ".join(line.split()))


def _fuzzy(steps):
    """How closely this action repeats one of the previous 10: overlap of their word sets (Jaccard).

    Digits are kept, so paging through a file (lines 100-200, then 200-300) is not a repeat.
    """
    words = [set(_WORD.findall(s.action.lower())) for s in steps]
    out = []
    for i, w in enumerate(words):
        best, where = 0.0, None
        for j in range(max(0, i - WINDOW), i):
            union = w | words[j]
            sim = len(w & words[j]) / len(union) if union else 0.0
            if sim > 0 and sim >= best:  # on a tie, point at the latest step
                best, where = sim, j
        detail = "" if where is None else f"{'same command as' if best == 1 else 'similar to'} step {where + 1}"
        out.append((best, detail))
    return out


def _stale(steps):
    """Share of this step's output lines the run has already seen. Empty output scores 0:
    many useful actions (like editing a file) print nothing."""
    seen, out = set(), []
    for s in steps:
        lines = [x for x in map(_norm, s.observation.splitlines()) if x]
        if not lines:
            out.append((0.0, ""))
            continue
        new = sum(1 for x in lines if x not in seen)
        seen.update(lines)
        out.append((1 - new / len(lines), f"{new} of {len(lines)} output lines new"))
    return out


def _errors(steps):
    """1 when this step fails with an error the run has already hit (same last line, numbers masked)."""
    first, out = {}, []
    for t, s in enumerate(steps, 1):
        last = next((x for x in reversed(s.observation.splitlines()) if x.strip()), "")
        failed = s.error if s.error is not None else bool(_ERROR_WORDS.search(last))
        if not failed:
            out.append((0.0, ""))
            continue
        sig = _norm(last)[:200]
        if sig in first:
            out.append((1.0, f"as step {first[sig]}: {_short(sig, 60)}"))
        else:
            first[sig] = t
            out.append((0.0, ""))
    return out


_SIGNAL_FNS = {"fuzzy": _fuzzy, "stale": _stale, "errors": _errors}
_LABELS = {"fuzzy": "repeating", "stale": "nothing new", "errors": "same error again"}
_ALL = ("fuzzy", "stale", "errors")
_PARTS = {"fuzzy": ("fuzzy",), "stale": ("stale",), "errors": ("errors",), "mean": _ALL, "max": _ALL, "loop": ("fuzzy", "stale")}


def _combine(name, vals):
    if name == "mean":
        return sum(vals.values()) / len(vals)
    if name == "max":
        return max(vals.values())
    if name == "loop":  # repeating AND learning nothing
        return vals["fuzzy"] * vals["stale"]
    return vals[name]


def _reason(per, parts, i):
    lo = max(0, i - RECENT + 1)
    bits = []
    for p in parts:
        hits = [j for j in range(lo, i + 1) if per[p][j][0] >= 0.5]
        if hits:
            bits.append(f"{_LABELS[p]} in {len(hits)} of last {i - lo + 1} steps ({per[p][hits[-1]][1]})")
    return "; ".join(bits)


def _signal_scorer(name, lam, steps):
    """Running score S_t = lam * S_(t-1) + u_t: one odd step fades, steady stuckness adds up."""
    # ponytail: recomputes every signal from all steps on each call, so a live run costs O(t^2) overall.
    # Fine for the 250-step runs seen here; Phase 2's Brake can keep running state instead, with the
    # "never looks ahead" test checking both give the same scores.
    parts = _PARTS[name]
    per = {p: _SIGNAL_FNS[p](steps) for p in parts}
    out, score = [], 0.0
    for i in range(len(steps)):
        score = lam * score + _combine(name, {p: per[p][i][0] for p in parts})
        out.append((score, _reason(per, parts, i)))
    return out


BASELINES = tuple(_BASELINE_SCORERS)
SIGNALS = tuple(_PARTS)
METHODS = BASELINES + SIGNALS


def method(name, lam=None):
    """The scorer for a method: scorer(steps) -> [(score, reason), ...], one per step."""
    if name in BASELINES:
        if lam is not None:
            raise ValueError(f"{name} takes no lam")
        return _BASELINE_SCORERS[name]
    if name in SIGNALS:
        if lam is None:
            raise ValueError(f"{name} needs lam")
        return partial(_signal_scorer, name, float(lam))
    raise ValueError(f"unknown method {name!r}")
