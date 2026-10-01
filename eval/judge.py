"""Ask Jev (Typesafe's hosted decision model) whether each step of a public run made progress.

Every answer is stored once, so evaluations never call Jev and always repeat exactly.
Only the six public groups can be judged; the access key never leaves ~/.loopbrake/typesafe_key.
Contracts: specs/002-progress-judge/contracts/judge-request.md and judge-cli.md.
Usage: uv run python eval/judge.py --group swe-devstral [--runs 100 --seed 0] [--recheck 200]
"""
import argparse
import hashlib
import importlib.util
import json
import os
import random
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from loopbrake.traces import read_runs


def _load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fetch = _load("fetch")
run_mod = _load("run")

URL = "https://api.typesafe.ai/v1/systemone"
KEY_FILE = Path.home() / ".loopbrake" / "typesafe_key"
JUDGMENTS = Path.home() / ".loopbrake" / "judgments"
CANDIDATE = Path(__file__).with_name("judge_candidate.json")
PUBLIC_GROUPS = tuple(fetch.GROUPS)
DEV_GROUP = run_mod.DEV_GROUP
PRICE_PER_MILLION = 0.042  # dollars per million input tokens; output tokens are free

# ---------- setup v1 (research R2) ----------
# ponytail: one judge setup, fixed in advance with no prompt search. A logged v2 may be tried on the
# development group only (research R9); a real prompt search would need its own dev/holdout split.

SETUPS = {
    "v1": {
        "model": "jev-1.13.0",
        "questions": {
            "progress": {
                "type": "noul",
                "instructions": "The latest action moved the agent closer to finishing its task.",
                "criteria": {
                    "true": "It found information it did not have, changed something the task needs, or confirmed the work is done.",
                    "false": "It repeated earlier work, hit an earlier error again, or got nothing useful.",
                },
            },
            "kind": {
                "type": "choice",
                "instructions": "What kind of step was the latest action?",
                "criteria": {
                    "found_new": "Found information it did not have before",
                    "changed": "Changed files or settings the task needs",
                    "verified": "Ran a check that confirms progress, such as a passing test",
                    "talked": "Asked or answered the user a question",
                    "finished": "Finished or submitted the task",
                    "repeated": "Repeated or nearly repeated an earlier action",
                    "same_error": "Hit an error it had already hit",
                    "dead_end": "Got an empty, irrelevant or failed result",
                },
            },
        },
        "limits": {"task": 1500, "earlier": 3, "earlier_chars": 200, "action": 600, "head": 1200, "tail": 800},
    }
}


def setup_id(name="v1"):
    template = json.dumps(SETUPS[name], sort_keys=True)
    return f"{SETUPS[name]['model']}/{name}/{hashlib.sha256(template.encode()).hexdigest()[:8]}"


def setup_dir(name="v1"):
    return JUDGMENTS / setup_id(name).replace("/", "-")


def _cut(text, n):
    return (text, False) if len(text) <= n else (text[: n - 1] + "…", True)


def build_state(task_text, steps, i, setup="v1"):
    """What the judge sees for step i: the task, the last few actions, this action and its result."""
    lim = SETUPS[setup]["limits"]
    task, c1 = _cut(task_text, lim["task"])
    earlier = [_cut(s.action, lim["earlier_chars"]) for s in steps[max(0, i - lim["earlier"]) : i]]
    action, c2 = _cut(steps[i].action, lim["action"])
    result = steps[i].observation
    c3 = len(result) > lim["head"] + lim["tail"]
    if c3:
        result = result[: lim["head"]] + "…" + result[-lim["tail"] :]
    state = {"task": task, "earlier_actions": [a for a, _ in earlier], "action": action, "result": result}
    return state, c1 or c2 or c3 or any(c for _, c in earlier)


def request_body(state, setup="v1"):
    return {"model": SETUPS[setup]["model"], "state": state, "questions": SETUPS[setup]["questions"]}


def judgment_key(body):
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def load_key():
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key and KEY_FILE.exists():
        key = KEY_FILE.read_text().strip()
    return key or None


# ---------- calling Jev (research R3) ----------


class StopJudging(Exception):
    """A problem no retry can fix, such as a rejected key."""


def parse_answer(data):
    answers = data.get("answers") or {}
    usage = data.get("usage") or {}
    tokens = (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0)
    p = (answers.get("progress") or {}).get("noul")
    kind = answers.get("kind") or {}
    choice = kind.get("choice")
    if not isinstance(p, (int, float)) or isinstance(p, bool) or not 0 <= p <= 1:
        return {"progress": None, "kind": None, "kind_p": None, "tokens": tokens, "status": "unreadable"}
    kind_p = (kind.get("probabilities") or {}).get(choice) if choice else None
    return {"progress": float(p), "kind": choice, "kind_p": kind_p, "tokens": tokens, "status": "ok"}


RETRY_STATUSES = {429, 500, 502, 503, 504, 529}
TRIES = 6


def call_jev(body, key, opener=urllib.request.urlopen, sleep=time.sleep):
    """One judgment. Retries busy or failing calls with growing waits; never reveals the key."""
    data = json.dumps(body, ensure_ascii=False).encode()
    start = time.monotonic()
    for attempt in range(TRIES):
        req = urllib.request.Request(URL, data, {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        wait = 2 ** attempt
        try:
            with opener(req, timeout=60) as resp:
                got = parse_answer(json.loads(resp.read()))
            return got | {"ms": round((time.monotonic() - start) * 1000)}
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise StopJudging("Typesafe rejected the key: invalid TYPESAFE_API_KEY") from None
            if e.code not in RETRY_STATUSES:
                return {"progress": None, "kind": None, "kind_p": None, "tokens": 0, "status": "unreadable", "ms": 0}
            after = e.headers.get("Retry-After") if e.headers else None
            if after:
                try:
                    wait = float(after)
                except ValueError:
                    pass
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            pass
        if attempt < TRIES - 1:
            sleep(wait)
    return {"progress": None, "kind": None, "kind_p": None, "tokens": 0, "status": "service_error",
            "ms": round((time.monotonic() - start) * 1000)}


# ---------- the runner ----------


def candidate_committed():
    return CANDIDATE.exists() and run_mod.is_committed(CANDIDATE)


def load_tasks(group, data):
    path = data / "tasks" / f"{group}.jsonl"
    return {d["task"]: d["text"] for d in map(json.loads, path.read_text().splitlines())}


def stored(path):
    if not path.exists():
        return {}
    return {d["key"]: d for d in map(json.loads, path.read_text().splitlines()) if d.get("key")}


def work_items(group, data, setup, runs_n=None, seed=0):
    """Every (run, step index, body, key) to judge for a group, in a fixed order."""
    runs, _ = read_runs(data / "runs" / f"{group}.jsonl")
    runs.sort(key=lambda r: r.run)
    if runs_n:
        keep = set(random.Random(seed).sample([r.run for r in runs], min(runs_n, len(runs))))
        runs = [r for r in runs if r.run in keep]
    tasks = load_tasks(group, data)
    items = []
    for r in runs:
        for i in range(len(r.steps)):
            state, cut = build_state(tasks[r.task], r.steps, i, setup)
            body = request_body(state, setup)
            items.append((r.run, i + 1, body, judgment_key(body), cut))
    return items


class Pacer:
    """At most `rate` request starts per second across all threads."""

    def __init__(self, rate):
        self.gap, self.next, self.lock = 1.0 / rate, time.monotonic(), threading.Lock()

    def wait(self):
        with self.lock:
            now = time.monotonic()
            start = max(now, self.next)
            self.next = start + self.gap
        time.sleep(max(0.0, start - now))


def judge_group(group, setup, key, data, runs_n=None, seed=0, rate=30, workers=32):
    out = setup_dir(setup) / f"{group}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    have = stored(out)
    # A busy or failing service is worth asking again on resume; the newest line for a key wins.
    pending = [it for it in work_items(group, data, setup, runs_n, seed) if it[3] not in have or have[it[3]]["status"] == "service_error"]
    # Identical requests (a step that exactly repeats an earlier one) are sent once; every such step gets the answer.
    same = defaultdict(list)
    for it in pending:
        same[it[3]].append(it)
    todo = [items[0] for items in same.values()]
    print(f"{group}: {len(have)} stored, {len(pending)} steps to judge in {len(todo)} distinct requests", flush=True)
    pacer, lock = Pacer(rate), threading.Lock()
    done, tokens, no_opinion, t0 = 0, 0, 0, time.monotonic()

    # ponytail: threads plus a pacer, not async. Enough for ~30 requests/s; switch to async only if
    # Jev's limits rise far above that.
    def one(item):
        nonlocal done, tokens, no_opinion
        _, _, body, k, cut = item
        pacer.wait()
        got = call_jev(body, key)
        if got["status"] == "ok" and cut:
            got["status"] = "truncated_ok"
        with lock, open(out, "a", encoding="utf-8") as f:
            for twin in same[k]:
                f.write(json.dumps({"key": k, "group": group, "run": twin[0], "step": twin[1]} | got, ensure_ascii=False) + "\n")
            done += 1
            tokens += got["tokens"]
            no_opinion += got["progress"] is None
            if done % 1000 == 0 or done == len(todo):
                rate_now = done / max(1e-9, time.monotonic() - t0)
                print(f"  {group}: {done}/{len(todo)} judged, no opinion {no_opinion}, tokens {tokens:,}, "
                      f"about ${tokens * PRICE_PER_MILLION / 1e6:.2f}, {rate_now:.1f}/s", flush=True)

    with ThreadPoolExecutor(workers) as pool:
        for fut in [pool.submit(one, it) for it in todo]:
            fut.result()  # re-raises StopJudging


def recheck(groups, setup, key, data, n, seed=0):
    """Re-ask a fixed sample of stored steps; report how often Jev gives the same answer. Stores nothing new."""
    by_key = {}
    for g in groups:
        for it in work_items(g, data, setup):
            by_key[it[3]] = it
    have = {}
    for g in groups:
        have |= stored(setup_dir(setup) / f"{g}.jsonl")
    pool_keys = sorted(k for k, d in have.items() if d["progress"] is not None and k in by_key)
    sample = random.Random(seed).sample(pool_keys, min(n, len(pool_keys)))
    agree = 0
    for k in sample:
        again = call_jev(by_key[k][2], key)
        old = have[k]
        agree += again["progress"] is not None and abs(again["progress"] - old["progress"]) <= 0.05 and again["kind"] == old["kind"]
    result = {"sample": len(sample), "agree": agree / len(sample) if sample else None}
    (setup_dir(setup) / "recheck.json").write_text(json.dumps(result) + "\n")
    print(f"recheck: {agree}/{len(sample)} agree ({result['agree']:.1%})" if sample else "recheck: nothing stored yet")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--group", nargs="+", required=True)
    ap.add_argument("--setup", default="v1", choices=sorted(SETUPS))
    ap.add_argument("--runs", type=int)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--recheck", type=int)
    ap.add_argument("--rate", type=float, default=30)
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--data", type=Path, default=fetch.DATA)
    args = ap.parse_args(argv)
    bad = [g for g in args.group if g not in PUBLIC_GROUPS]
    if bad:
        print(f"refusing {bad}: only the public groups {list(PUBLIC_GROUPS)} may be sent to Jev", file=sys.stderr)
        return 2
    holdout = [g for g in args.group if g != DEV_GROUP]
    if holdout and not candidate_committed():
        print(f"refusing {holdout}: commit eval/judge_candidate.json before judging holdout groups (research R9)", file=sys.stderr)
        return 3
    key = load_key()
    if not key:
        print(f"no key: set TYPESAFE_API_KEY or write it to {KEY_FILE} (chmod 600)", file=sys.stderr)
        return 4
    try:
        if args.recheck:
            recheck(args.group, args.setup, key, args.data, args.recheck, args.seed)
            return 0
        for g in args.group:
            judge_group(g, args.setup, key, args.data, args.runs, args.seed, args.rate, args.workers)
    except StopJudging as e:
        print(str(e), file=sys.stderr)
        return 5
    return 0


if __name__ == "__main__":
    sys.exit(main())
