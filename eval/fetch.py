"""One-time download of the public agent runs, converted to LoopBrake's common runs format.

This is the only part of the project that uses the network (spec FR-016).
Usage: uv run python eval/fetch.py [--data DIR] [--only GROUP ...]
Sources and expected counts: specs/001-offline-eval/research.md, R1.
"""
import argparse
import hashlib
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from loopbrake.signals import Step
from loopbrake.traces import Run, write_runs

DATA = Path.home() / ".loopbrake" / "data"
S3 = "https://swe-bench-submissions.s3.amazonaws.com/bash-only/{sub}/trajs/{iid}/{iid}.traj.json"
LABELS = "https://raw.githubusercontent.com/SWE-bench/experiments/main/evaluation/verified/{sub}/per_instance_details.json"
TAU = "https://raw.githubusercontent.com/sierra-research/tau-bench/main/historical_trajectories/{name}.json"

# group id -> (source, name, expected successes, expected runs)
GROUPS = {
    "swe-devstral": ("mini-v1", "20251209_mini-v1.17.2_devstral-small-2512", 282, 500),
    "swe-gpt5mini": ("mini-v2", "20260217_mini-v2.0.0_gpt-5-mini", 281, 500),
    "tau-gpt4o-airline": ("tau", "gpt-4o-airline", 84, 200),
    "tau-gpt4o-retail": ("tau", "gpt-4o-retail", 278, 460),
    "tau-sonnet35-airline": ("tau", "sonnet-35-new-airline", 184, 400),
    "tau-sonnet35-retail": ("tau", "sonnet-35-new-retail", 637, 920),
}


# ---------- downloading ----------


def download(url, dest):
    """Save url to dest unless it is already there."""
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
        f.write(r.read())
    tmp.rename(dest)
    return dest


# ---------- shared helpers ----------


def action_text(tool, args):
    """One way of writing every action, so all sources compare the same: '<tool> <json, sorted keys>'."""
    return f"{tool} {json.dumps(args, sort_keys=True, ensure_ascii=False)}"


def parse_args(raw):
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return {"raw": raw}


def clean_output(text):
    """Drop mini-SWE-agent's <returncode>/<output> wrapper so only the real output is left."""
    return re.sub(r"<returncode>-?\d+</returncode>|</?output>", "", text).strip("\n")


def as_text(content):
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False) if content else ""


class StepList:
    """Collects steps. Tokens of a model call that produced no action go to the previous step,
    or to the first step if there is none yet (research R3), so each run's total stays exact."""

    def __init__(self):
        self.steps, self.pending = [], 0

    def add_tokens(self, n):
        if self.steps:
            last = self.steps[-1]
            self.steps[-1] = last._replace(tokens=last.tokens + n)
        else:
            self.pending += n

    def add(self, action, observation, error, tokens):
        self.steps.append(Step(action, observation, error, tokens + self.pending))
        self.pending = 0


# ---------- parsers ----------


def parse_mini_v2(traj, resolved, group):
    """mini-SWE-agent 2.x: model calls are OpenAI Responses objects; results are function_call_output items.

    Returns (run, number of model calls with no usage recorded).
    """
    outputs = {m["call_id"]: m for m in traj["messages"] if m.get("type") == "function_call_output"}
    steps, missing = StepList(), 0
    for m in traj["messages"]:
        if m.get("object") != "response":
            continue
        usage = m.get("usage") or {}
        missing += "input_tokens" not in usage
        tokens = (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0)
        calls = [o for o in m.get("output", []) if o.get("type") == "function_call"]
        if not calls:
            steps.add_tokens(tokens)
        for j, c in enumerate(calls):
            out = outputs.get(c.get("call_id"))
            rc = out["extra"].get("returncode") if out else None
            steps.add(
                action_text(c["name"], parse_args(c["arguments"])),
                clean_output(as_text(out["output"])) if out else "",
                None if rc is None else rc != 0,
                tokens if j == 0 else 0,
            )
    iid = traj["instance_id"]
    return Run(group, "swe-bench-verified", iid, iid, resolved, traj["info"].get("exit_status"), True, tuple(steps.steps)), missing


def parse_mini_v1(traj, resolved, group):
    """mini-SWE-agent 1.x: the command is a ```bash block in the reply; the next user message is the result."""
    pattern = re.compile(traj["info"]["config"]["agent"]["action_regex"], re.DOTALL)
    msgs = traj["messages"]
    steps, missing = StepList(), 0
    for i, m in enumerate(msgs):
        if m.get("role") != "assistant":
            continue
        usage = ((m.get("extra") or {}).get("response") or {}).get("usage") or {}
        missing += "prompt_tokens" not in usage
        tokens = (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0)
        found = pattern.findall(as_text(m.get("content")))
        if len(found) != 1:  # mini-SWE-agent only runs a reply with exactly one command
            steps.add_tokens(tokens)
            continue
        nxt = msgs[i + 1] if i + 1 < len(msgs) and msgs[i + 1].get("role") == "user" else None
        obs = as_text(nxt["content"]) if nxt else ""
        rc = re.search(r"<returncode>(-?\d+)</returncode>", obs)
        steps.add(action_text("bash", {"command": found[0].strip()}), clean_output(obs), None if rc is None else rc.group(1) != "0", tokens)
    iid = traj["instance_id"]
    return Run(group, "swe-bench-verified", iid, iid, resolved, traj["info"].get("exit_status"), True, tuple(steps.steps)), missing


def char_count(m):
    """Characters a message adds to the model's context: its text plus any tool calls."""
    return len(as_text(m.get("content"))) + (len(json.dumps(m["tool_calls"])) if m.get("tool_calls") else 0)


def parse_tau(entry, group):
    """τ-bench: OpenAI-style messages. Tokens are estimated as characters / 4, because none are recorded."""
    msgs = entry["traj"]
    tool_out = {m.get("tool_call_id"): m for m in msgs if m.get("role") == "tool"}
    steps, seen = StepList(), 0
    for i, m in enumerate(msgs):
        size = char_count(m)
        if m.get("role") == "assistant":
            tokens = (seen + size) // 4  # the call re-reads everything before it, then writes this message
            calls = m.get("tool_calls") or []
            for j, c in enumerate(calls):
                out = tool_out.get(c.get("id"))
                obs = as_text(out.get("content")) if out else ""
                steps.add(action_text(c["function"]["name"], parse_args(c["function"]["arguments"])), obs,
                          obs.startswith("Error") if out else None, tokens if j == 0 else 0)
            if not calls:
                nxt = msgs[i + 1] if i + 1 < len(msgs) and msgs[i + 1].get("role") == "user" else None
                steps.add(action_text("respond", {"content": as_text(m.get("content"))}), as_text(nxt["content"]) if nxt else "", None, tokens)
        seen += size
    task = str(entry["task_id"])
    return Run(group, "tau-bench", task, f"{task}-{entry['trial']}", entry["reward"] == 1, None, False, tuple(steps.steps))


# ---------- building one group ----------


def build(group, data_dir):
    source, name, _, _ = GROUPS[group]
    raw = data_dir / "raw" / name
    if source == "tau":
        entries = json.loads(download(TAU.format(name=name), raw / f"{name}.json").read_text())
        return [parse_tau(e, group) for e in entries], 0, 0
    labels = json.loads(download(LABELS.format(sub=name), raw / "per_instance_details.json").read_text())
    iids = sorted(labels)
    with ThreadPoolExecutor(16) as pool:
        paths = list(pool.map(lambda iid: download(S3.format(sub=name, iid=iid), raw / f"{iid}.traj.json"), iids))
    parse = parse_mini_v1 if source == "mini-v1" else parse_mini_v2
    runs, missing, calls = [], 0, 0
    for iid, path in zip(iids, paths):
        traj = json.loads(path.read_text())
        run, miss = parse(traj, bool(labels[iid]["resolved"]), group)
        runs.append(run)
        missing += miss
        calls += sum(1 for m in traj["messages"] if m.get("object") == "response" or m.get("role") == "assistant")
    return runs, missing, calls


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=DATA)
    ap.add_argument("--only", nargs="+", choices=sorted(GROUPS))
    args = ap.parse_args(argv)
    out_dir = args.data / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    ok = True
    for group in args.only or GROUPS:
        try:
            runs, missing, calls = build(group, args.data)
        except OSError as e:
            print(f"{group}: download failed: {e}", file=sys.stderr)
            ok = False
            continue
        empty = sum(1 for r in runs if not r.steps)
        wins = sum(r.success for r in runs)
        _, _, want_wins, want_runs = GROUPS[group]
        write_runs(out_dir / f"{group}.jsonl", runs)  # runs with no steps stay in, so the reader counts them as skipped
        print(f"{group:22} runs {len(runs):4}  successes {wins:4}  failures {len(runs) - wins:4}  skipped (no steps) {empty}")
        if (wins, len(runs)) != (want_wins, want_runs):
            print(f"{group}: expected {want_wins}/{want_runs} successes/runs, got {wins}/{len(runs)}", file=sys.stderr)
            ok = False
        if calls and missing / calls > 0.01:
            print(f"{group}: token usage missing on {missing} of {calls} model calls", file=sys.stderr)
            ok = False
    sums = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}" for p in sorted(out_dir.glob("*.jsonl"))]
    (out_dir / "SHA256SUMS").write_text("\n".join(sums) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
