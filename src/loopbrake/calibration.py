"""Calibration: set the stop line from your own past successful runs (constitution Principle I).

Contract: specs/003-core-package/contracts/python-api.md and records.md.
"""
import hashlib
import json
import math
import warnings
from datetime import date
from pathlib import Path

from loopbrake import __version__, records
from loopbrake.conformal import rank, threshold
from loopbrake.traces import claude_code_turns, read_runs


def path(project, home):
    return home / "calibration" / f"{project}.json"


def load(project, home):
    """The calibration record for a project, or None if there is none or it is damaged (watch-only)."""
    p = path(project, home)
    if not p.exists():
        return None
    try:
        rec = json.loads(p.read_text())
        line = rec["stop_line"]
        ok = (rec["method"] == "steps" and isinstance(rec["watch_only"], bool) and isinstance(rec["n"], int)
              and 0 < rec["alpha"] < 1 and (line is None or (isinstance(line, int) and line >= 0)))
        if not ok:
            raise ValueError("unexpected values")
        return rec
    except Exception as e:
        warnings.warn(f"loopbrake: calibration file {p} is damaged ({e}); watching only", RuntimeWarning, stacklevel=3)
        return None


def runs_needed(alpha):
    """The fewest successful runs that give a stop line at this alpha (fewer means watch-only)."""
    n = 1
    while rank(n, alpha) > n:
        n += 1
    return n


def _from_runs_file(src, exclude):
    """One successful run per task (the first by run id), skipping excluded ids."""
    runs, _ = read_runs(src)
    first, seen, excluded = {}, 0, 0
    for r in sorted(runs, key=lambda r: r.run):
        if not r.steps:
            continue
        seen += 1
        if r.run in exclude:
            excluded += 1
            continue
        if r.success and r.task not in first:
            first[r.task] = len(r.steps)
    source = {"kind": "runs-file", "sha256": hashlib.sha256(src.read_bytes()).hexdigest(), "runs_seen": seen, "excluded": excluded}
    return list(first.values()), source


def _from_claude_code(folder, exclude):
    """Every turn is its own task; success follows the experiments' rule (not interrupted, not excluded)."""
    files = sorted(folder.glob("*.jsonl"))
    if not files:
        raise FileNotFoundError(f"no Claude Code session files (*.jsonl) in {folder}")
    lengths, seen, excluded = [], 0, 0
    for f in files:
        for r in claude_code_turns(f, exclude)[0]:
            if not r.steps:
                continue
            seen += 1
            excluded += r.run in exclude
            if r.success:
                lengths.append(len(r.steps))
    listing = "\n".join(f"{f.name}\t{f.stat().st_size}" for f in files)  # names and sizes only, never content
    source = {"kind": "claude-code", "sha256": hashlib.sha256(listing.encode()).hexdigest(), "runs_seen": seen, "excluded": excluded}
    return lengths, source


def calibrate(source, *, project="default", alpha=0.05, home=None):
    """Set a project's stop line from past runs and save it. Returns the calibration record.

    `source`: a runs file (common format) or a Claude Code project folder. The record holds counts and a
    fingerprint only, never text from the source (spec FR-007).
    """
    if not records.valid_project(project):
        raise ValueError(f"project names may use letters, digits, '.', '_' and '-' (got {project!r})")
    h = records.home(home)
    src = Path(source).expanduser()
    if not src.exists():
        raise FileNotFoundError(f"no such file or folder: {src}")
    exclude = records.read_exclude(h)
    lengths, src_info = _from_claude_code(src, exclude) if src.is_dir() else _from_runs_file(src, exclude)
    line = threshold(lengths, alpha)
    rec = {
        "v": 1, "project": project, "method": "steps", "alpha": alpha,
        "n": len(lengths), "k": rank(len(lengths), alpha),
        "stop_line": None if line == math.inf else int(line), "watch_only": line == math.inf,
        "source": src_info, "created": date.today().isoformat(), "version": __version__,
    }
    p = path(project, h)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, indent=1) + "\n")
    return rec
