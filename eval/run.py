"""Replay recorded agent runs through LoopBrake's stuck scores and measure what would happen.

Commands: specs/001-offline-eval/contracts/eval-cli.md. Outputs: contracts/results.md.
Run with `uv run python eval/run.py ...` from the repository root.
"""
import argparse
import bisect
import csv
import json
import math
import random
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

from loopbrake.conformal import rank, threshold
from loopbrake.signals import BASELINES, SIGNALS, method
from loopbrake.traces import claude_code_turns, read_runs

DATA = Path.home() / ".loopbrake" / "data"
EVAL_DIR = Path.home() / ".loopbrake" / "eval"
RESULTS = Path(__file__).parent / "results"
CANDIDATE = Path(__file__).parent / "candidate.json"
ALPHAS = (0.01, 0.05, 0.10)
SIZES = (20, 50, 100)
HEADLINE = (0.05, 20)
LAMS = (0.8, 0.9, 1.0)
MIN_HELD_SUCCESSES = 20
DEV_GROUP = "swe-devstral"
ROLES = {DEV_GROUP: "dev"}  # every other public group is a holdout group

COLUMNS = [
    "group", "dataset", "role", "method", "lam", "alpha", "n", "splits", "status",
    "runs", "successes", "failures", "skipped", "tokens_measured",
    "fk_mean", "fk_lo", "fk_hi", "fk_p05", "fk_p95",
    "saved_all_mean", "saved_all_lo", "saved_all_hi", "saved_all_p05", "saved_all_p95",
    "saved_fail_mean", "saved_fail_lo", "saved_fail_hi", "lost_mean", "kill_step_median",
]
RATE_COLUMNS = {c for c in COLUMNS if c.startswith(("fk_", "saved_", "lost_"))}


# ---------- loading and preparing runs ----------


class Group(NamedTuple):
    id: str
    dataset: str
    role: str  # dev, holdout or local
    runs: list  # sorted by run id
    skipped: dict  # reason -> count


def load_groups(data_dir=DATA, only=None):
    groups = {}
    for path in sorted((Path(data_dir) / "runs").glob("*.jsonl")):
        if only and path.stem not in only:
            continue
        runs, skipped = read_runs(path)
        runs.sort(key=lambda r: r.run)
        if runs:
            groups[path.stem] = Group(path.stem, runs[0].dataset, ROLES.get(path.stem, "holdout"), runs, dict(skipped))
    return groups


class Prepared(NamedTuple):
    run: str
    task: str
    success: bool
    peak: list  # running maximum of the stuck score; never goes down, so a bisect finds the stop step
    tail: list  # tail[i] = tokens saved if the run is stopped right after step i + 1
    total: int


def prepare(run, scorer):
    peak, top = [], -math.inf
    for score, _ in scorer(run.steps):
        top = max(top, score)
        peak.append(top)
    total = left = sum(s.tokens for s in run.steps)
    tail = []
    for s in run.steps:
        left -= s.tokens
        tail.append(left)
    return Prepared(run.run, run.task, run.success, peak, tail, total)


def kill_index(p, tau, fixed=False):
    """0-based index of the step after which the run is stopped, or None if it never is.

    Calibrated methods stop at the first step whose score goes above the stop line;
    `fixed` (the old liveness.py rule) stops at the first score of 1 or more.
    """
    i = bisect.bisect_left(p.peak, 1.0) if fixed else bisect.bisect_right(p.peak, tau)
    return i if i < len(p.peak) else None


# ---------- splits ----------


def split_rng(seed, group, alpha, n, kind):
    # String seeds give the same numbers in every process; hash() does not.
    return random.Random(f"{seed}|{group}|{alpha}|{n}|{kind}")


def boot_items(rng, preps):
    """Resample tasks with replacement and return the runs of the drawn tasks (repeats allowed)."""
    by_task = defaultdict(list)
    for i, p in enumerate(preps):
        by_task[p.task].append(i)
    tasks = sorted(by_task)
    items = []
    for _ in tasks:
        items.extend(by_task[rng.choice(tasks)])
    return items


def make_split(rng, items, preps, n):
    """Draw n successful runs, at most one per task, to set the stop line; every run of those
    tasks leaves the test set.

    At most one per task, because repeats of a task are not independent: using several of them
    set the stop line too low for new tasks (first final run, tau-bench; see eval/results/CORRECTIONS.md).
    Returns (calibration, held_out) as index lists, or None when fewer than n tasks have a success.
    """
    items = list(items)
    wins = defaultdict(list)
    for i in items:
        if preps[i].success:
            wins[preps[i].task].append(i)
    if len(wins) < n:
        return None
    tasks = rng.sample(sorted(wins), n)
    # Groups with one run per task (SWE-bench) get exactly the plain splits the first run drew. Bootstrap
    # splits do change, because resampled tasks repeat.
    cal = [wins[t][0] if len(wins[t]) == 1 else rng.choice(wins[t]) for t in tasks]
    used = set(tasks)
    return cal, [i for i in items if preps[i].task not in used]


# ---------- measuring ----------


class Split(NamedTuple):
    fk: float | None  # false-stop rate: stopped successful runs / successful runs
    saved_all: float | None  # tokens saved / all held-out tokens
    saved_fail: float | None  # tokens saved on failed runs / tokens of failed runs
    lost: float | None  # tokens spent on falsely stopped runs / all held-out tokens
    kill_steps: list  # stop step of each stopped failed run
    held_successes: int
    tau: float | None


def measure(preps, cal, held, alpha, fixed=False):
    tau = None if fixed else threshold([preps[i].peak[-1] for i in cal], alpha)
    wins = stopped_wins = all_tok = fail_tok = saved = saved_fail = lost = 0
    steps = []
    for i in held:
        p = preps[i]
        all_tok += p.total
        wins += p.success
        if not p.success:
            fail_tok += p.total
        k = kill_index(p, tau, fixed)
        if k is None:
            continue
        saved += p.tail[k]
        if p.success:
            stopped_wins += 1
            lost += p.total - p.tail[k]
        else:
            saved_fail += p.tail[k]
            steps.append(k + 1)

    def share(a, b):
        return a / b if b else None

    return Split(share(stopped_wins, wins), share(saved, all_tok), share(saved_fail, fail_tok), share(lost, all_tok), steps, wins, tau)


class Result(NamedTuple):
    row: dict  # results.csv columns for one method at one setting
    boot_saved: list  # saved_all in each bootstrap split, in split order (paired across methods)
    taus: list  # stop line in each plain split


def evaluate(gid, preps_by_key, alpha, n, splits, boots, seed):
    """Run every method on the same random splits of one group. Returns {key: Result}.

    preps_by_key maps (method, lam) to Prepared runs, all in the same run order.
    """
    base = next(iter(preps_by_key.values()))
    if rank(n, alpha) > n or sum(p.success for p in base) < n:
        return {key: Result({"status": "insufficient", "splits": 0}, [], []) for key in preps_by_key}
    plain, boot = defaultdict(list), defaultdict(list)
    # ponytail: random splits in plain Python (about 1 minute for --dev). If --final ever passes 15 minutes,
    # bootstrap only the main setting, then precompute savings for every possible stop line (research R12).
    for kind, count, out in (("plain", splits, plain), ("boot", boots, boot)):
        rng = split_rng(seed, gid, alpha, n, kind)
        for _ in range(count):
            items = range(len(base)) if kind == "plain" else boot_items(rng, base)
            split = make_split(rng, items, base, n)
            if split is None:
                continue
            cal, held = split
            if sum(base[i].success for i in held) < MIN_HELD_SUCCESSES:
                continue  # not enough successful runs left to test on
            for key, preps in preps_by_key.items():
                out[key].append(measure(preps, cal, held, alpha, fixed=key[0] == "fixed"))
    usable = len(next(iter(plain.values()), []))
    if usable < splits / 2 or not boot:
        return {key: Result({"status": "insufficient", "splits": usable}, [], []) for key in preps_by_key}
    return {
        key: Result(
            summarize(plain[key], boot[key], alpha, fixed=key[0] == "fixed") | {"splits": usable},
            [s.saved_all for s in boot[key]],
            [s.tau for s in plain[key]],
        )
        for key in preps_by_key
    }


# ---------- summing up ----------


def _spread(vals):
    """Mean, 95% confidence interval of the mean, and 5th / 95th percentiles across splits."""
    if not vals:
        return (None,) * 5
    mean = statistics.fmean(vals)
    if len(vals) == 1:
        return (mean,) * 5
    half = 1.96 * statistics.stdev(vals) / math.sqrt(len(vals))
    cuts = statistics.quantiles(vals, n=20)
    return mean, mean - half, mean + half, cuts[0], cuts[-1]


def _boot_interval(vals):
    """2.5th to 97.5th percentile of bootstrap values: the 95% interval that includes data noise."""
    if len(vals) < 2:
        return None, None
    cuts = statistics.quantiles(vals, n=40)
    return cuts[0], cuts[-1]


def summarize(plain, boot, alpha, fixed=False):
    row = {}
    for name in ("fk", "saved_all", "saved_fail", "lost"):
        mean, lo, hi, p05, p95 = _spread([getattr(s, name) for s in plain if getattr(s, name) is not None])
        row[f"{name}_mean"] = mean
        if name == "fk":
            row.update(fk_lo=lo, fk_hi=hi, fk_p05=p05, fk_p95=p95)
        elif name == "saved_all":
            row.update(saved_all_p05=p05, saved_all_p95=p95)
    for name in ("saved_all", "saved_fail"):
        row[f"{name}_lo"], row[f"{name}_hi"] = _boot_interval([getattr(s, name) for s in boot if getattr(s, name) is not None])
    steps = [k for s in plain for k in s.kill_steps]
    row["kill_step_median"] = statistics.median(steps) if steps else None
    # Invalid: even the low end of the false-stop rate's interval is above alpha. The old fixed rule
    # has no stop line to keep, so it is reported but never judged.
    row["status"] = "invalid" if not fixed and row["fk_lo"] is not None and row["fk_lo"] > alpha else "ok"
    return row


# ---------- running groups and writing tables ----------


def method_keys(lam=None):
    """(method, lam) pairs: each simple method once, each signal method at every lam (or just the one given)."""
    lams = LAMS if lam is None else (lam,)
    return [(m, None) for m in BASELINES] + [(m, x) for m in SIGNALS for x in lams]


def group_info(group):
    wins = sum(r.success for r in group.runs)
    return {
        "group": group.id, "dataset": group.dataset, "role": group.role, "runs": len(group.runs),
        "successes": wins, "failures": len(group.runs) - wins, "skipped": sum(group.skipped.values()),
        "tokens_measured": all(r.tokens_measured for r in group.runs),
    }


def run_group(group, keys, splits, boots, seed, settings=None):
    """Evaluate one group for every method and (alpha, n). Returns {(key, alpha, n): Result}."""
    preps = {key: [prepare(r, method(*key)) for r in group.runs] for key in keys}
    out = {}
    for alpha, n in settings or [(a, n) for a in ALPHAS for n in SIZES]:
        for key, res in evaluate(group.id, preps, alpha, n, splits, boots, seed).items():
            res.row.update(group_info(group) | {"method": key[0], "lam": key[1], "alpha": alpha, "n": n})
            out[(key, alpha, n)] = res
    return out


def fmt(col, v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v).lower()
    if col in RATE_COLUMNS:
        return f"{v:.4f}"
    return f"{v:g}" if isinstance(v, float) else str(v)


def sort_rows(rows):
    return sorted(rows, key=lambda r: (r["group"], r["method"], r["lam"] or 0, r["alpha"], r["n"]))


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(COLUMNS)
        for r in sort_rows(rows):
            w.writerow([fmt(c, r.get(c)) for c in COLUMNS])


def pct(v):
    return "   -  " if v is None else f"{v:6.1%}"


def print_table(rows):
    print(f"{'method':7} {'lam':>4} {'alpha':>5} {'n':>4}  {'status':12} {'false stops [95%]':>26}  {'saved, all runs [95%]':>28}  {'saved, failed':>13}")
    for r in sort_rows(rows):
        lam = "" if r["lam"] is None else f"{r['lam']:g}"
        print(
            f"{r['method']:7} {lam:>4} {r['alpha']:5g} {r['n']:4}  {r['status']:12} "
            f"{pct(r.get('fk_mean'))} [{pct(r.get('fk_lo'))},{pct(r.get('fk_hi'))}]  "
            f"{pct(r.get('saved_all_mean'))} [{pct(r.get('saved_all_lo'))},{pct(r.get('saved_all_hi'))}]  "
            f"{pct(r.get('saved_fail_mean')):>13}"
        )


def best_signal(rows):
    """Best valid signal method at the headline setting, by mean tokens saved. A suggestion only."""
    alpha, n = HEADLINE
    pool = [r for r in rows if r["method"] in SIGNALS and r["alpha"] == alpha and r["n"] == n and r["status"] == "ok"]
    return max(pool, key=lambda r: (r["saved_all_mean"], -SIGNALS.index(r["method"]), -(r["lam"] or 0)), default=None)


# ---------- the go / no-go decision (research R8, R9) ----------


def stronger_baseline(headline, gids):
    """Of the two calibrated simple methods, the one that saves more on these groups: the bar to beat."""
    return max(("exact", "steps"), key=lambda name: statistics.fmean(headline[g][(name, None)].row["saved_all_mean"] for g in gids))


def paired_diffs(headline, gids, cand, base):
    """Per bootstrap split: candidate minus baseline tokens saved, averaged over the groups.

    Within a group both methods saw the same splits, so the difference is paired.
    Groups are resampled independently, so split r of each group can be averaged together.
    """
    per_group = [[c - b for c, b in zip(headline[g][cand].boot_saved, headline[g][(base, None)].boot_saved)] for g in gids]
    count = min((len(x) for x in per_group), default=0)
    return [statistics.fmean(x[r] for x in per_group) for r in range(count)]


def decide(diffs_by_dataset, valid_everywhere):
    """GO only if, on every dataset, the 95% interval of the difference is above zero, and the candidate is valid."""
    details = {}
    for name, diffs in diffs_by_dataset.items():
        lo, hi = _boot_interval(diffs)
        details[name] = (statistics.fmean(diffs) if diffs else None, lo, hi, lo is not None and lo > 0)
    go = valid_everywhere and bool(details) and all(d[3] for d in details.values())
    return ("GO" if go else "NO-GO"), details


# ---------- kill stories ----------


def display(action):
    """The readable part of an action: the shell command, or the message to the user."""
    tool, _, raw = action.partition(" ")
    try:
        args = json.loads(raw)
    except json.JSONDecodeError:
        return action
    if isinstance(args, dict) and len(args) == 1 and isinstance(next(iter(args.values())), str):
        return next(iter(args.values()))
    return action


def trim(text, n=80):
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def story(group_id, run, key, tau):
    """A short, readable account of where and why a run would have been stopped (None if it never is)."""
    scores = method(*key)(run.steps)
    p = prepare(run, lambda steps: scores)
    k = kill_index(p, tau, fixed=key[0] == "fixed")
    if k is None:
        return None
    share = f" ({p.tail[k] / p.total:.0%})" if p.total else ""
    lines = [
        f"### {group_id} · {run.run} · stopped at step {k + 1} of {len(run.steps)} · saved {p.tail[k]:,} tokens{share}",
        f"Reason: {scores[k][1] or 'score above the stop line'}",
        "```text",
    ]
    lines += [f"{t + 1:>4}  {trim(display(run.steps[t].action))}" for t in range(max(0, k - 4), k + 1)]
    return "\n".join(lines + ["```"]), p.tail[k]


def headline_tau(res):
    finite = [t for t in res.taus if t is not None and t != math.inf]
    return statistics.median(finite) if finite else math.inf


# ---------- writing the report (contracts/results.md) ----------


def p1(v):
    return "–" if v is None else f"{v:.1%}"


def ci(row, name):
    return f"{p1(row.get(name + '_mean'))} [{p1(row.get(name + '_lo'))}, {p1(row.get(name + '_hi'))}]"


def label(key):
    return key[0] if key[1] is None else f"{key[0]} (λ {key[1]:g})"


FAILFAST = [
    ("FailFast (trained monitor)", "14.6–20.4%"),
    ("AgentStop", "10.2–12.5%"),
    ("Duration (step count only)", "10.0–12.0%"),
]


def token_check(groups):
    """How far the chars/4 estimate (used for τ-bench) lands from measured usage on the SWE-bench groups."""
    out = []
    for g in groups.values():
        if g.role == "local" or not all(r.tokens_measured for r in g.runs):
            continue
        ratios = []
        for r in g.runs:
            seen = est = 0
            for s in r.steps:
                est += (seen + len(s.action)) // 4
                seen += len(s.action) + len(s.observation)
            total = sum(s.tokens for s in r.steps)
            if total:
                ratios.append(est / total)
        if len(ratios) > 1:
            q = statistics.quantiles(ratios, n=4)
            out.append(f"| {g.id} | {statistics.median(ratios):.2f} | {q[0]:.2f}–{q[2]:.2f} |")
    return out


def write_report(path, args, cand, groups, results, verdict, details, baselines, cand_key, used_groups, sums):
    alpha, n = HEADLINE
    out = ["# LoopBrake offline evaluation: results", ""]
    cmd = f"uv run python eval/run.py --final --seed {args.seed} --splits {args.splits} --boot {args.boot}" + (" --local" if args.local else "")
    out += ["## 1. Reproduce", "", "```bash", "uv run python eval/fetch.py", cmd, "```", "", "Data fingerprints (sha256 of each runs file):", "", "```text"]
    out += [line for line in sums if line.split()[-1].removesuffix(".jsonl") in groups] + ["```", ""]
    out += ["Corrections to earlier runs are listed in [CORRECTIONS.md](CORRECTIONS.md).", ""]

    out += [f"## 2. Verdict: {verdict}", ""]
    out += [f"Method chosen in advance on `{cand['chosen_on']}` ({cand['date']}): **{label(cand_key)}**.", ""]
    out += ["| Dataset | Groups tested | Bar to beat | Extra tokens saved [95% interval] | Above zero |", "|---|---|---|---|---|"]
    for name, (mean, lo, hi, ok) in details.items():
        out.append(f"| {name} | {', '.join(used_groups[name]) or 'none'} | {baselines.get(name, '–')} | {p1(mean)} [{p1(lo)}, {p1(hi)}] | {'yes' if ok else 'no'} |")
    invalid = [g for g in used_groups_all(used_groups) if results[g][(cand_key, alpha, n)].row["status"] == "invalid"]
    out += ["", f"Candidate within its false-stop limit on every holdout group: {'yes' if not invalid else 'no (' + ', '.join(invalid) + ')'}.", ""]
    out += ["GO means: on every dataset the candidate saves more than the stronger simple method, with the whole",
            "95% interval above zero, and it never breaks its false-stop limit. The interval resamples tasks, so it",
            "includes the noise of having a limited number of tasks.", ""]

    out += [f"## 3. Main table (α = {alpha:.0%}, calibrated on n = {n} successful runs)", ""]
    out += ["| Group | Method | False stops [95%] | Tokens saved, all runs [95%] | Saved on failed runs | Status |", "|---|---|---|---|---|---|"]
    for g in sorted(groups):
        for key in [("fixed", None), ("exact", None), ("steps", None), cand_key]:
            res = results[g].get((key, alpha, n))
            if res:
                r = res.row
                out.append(f"| {g}{' (dev)' if groups[g].role == 'dev' else ''} | {label(key)} | {ci(r, 'fk')} | {ci(r, 'saved_all')} | {p1(r.get('saved_fail_mean'))} | {r['status']} |")
    out.append("")

    out += ["## 4. Against FailFast", ""]
    sg = "swe-gpt5mini"
    if sg in results:
        out += ["| Method | Data | Tokens saved at 5% false stops |", "|---|---|---|"]
        for key in [("steps", None), cand_key]:
            for size in (20, 100):
                r = results[sg][(key, 0.05, size)].row
                out.append(f"| LoopBrake {label(key)}, n = {size} | {sg} | {p1(r.get('saved_all_mean'))} |")
        out += [f"| {name} | FailFast paper (other models) | {v} |" for name, v in FAILFAST]
        out += ["", "Read this comparison with care:",
                "1. FailFast set its 5% line on the same data it reports on, so its 5% is a target, not a guarantee. Ours is set on separate runs.",
                "2. Different models: FailFast used Qwen3.5/3.6, Gemma4 and Gemini 3 Flash; these numbers use GPT-5-mini.",
                "3. FailFast does not say exactly which tokens it counts. We count every token each model call reads and writes.", ""]

    out += ["## 5. Price of the guarantee (α = 5%)", "", "Tokens saved, all runs. More past runs give a tighter stop line.", ""]
    out += ["| Group | Method | n = 20 | n = 50 | n = 100 |", "|---|---|---|---|---|"]
    for g in sorted(groups):
        for key in [("steps", None), cand_key]:
            cells = [p1(results[g][(key, 0.05, size)].row.get("saved_all_mean")) if results[g][(key, 0.05, size)].row["status"] != "insufficient" else "not enough data" for size in SIZES]
            out.append(f"| {g} | {label(key)} | " + " | ".join(cells) + " |")
    out.append("")

    out += [f"## 6. All methods (α = {alpha:.0%}, n = {n})", "", "Exploratory. Rows on the development group are in-sample: the candidate was chosen there.", ""]
    out += ["| Group | Method | False stops | Tokens saved, all runs | Status |", "|---|---|---|---|---|"]
    for g in sorted(groups):
        for (key, a, size), res in sorted(results[g].items(), key=lambda kv: (METHOD_ORDER[kv[0][0][0]], kv[0][0][1] or 0)):
            if (a, size) == HEADLINE:
                out.append(f"| {g}{' (dev)' if groups[g].role == 'dev' else ''} | {label(key)} | {p1(res.row.get('fk_mean'))} | {p1(res.row.get('saved_all_mean'))} | {res.row['status']} |")
    out.append("")

    out += ["## 7. Token estimate check", "",
            "τ-bench records no token counts, so they are estimated as characters / 4 of everything each call reads and writes.",
            "On the SWE-bench groups we can compare that estimate with measured usage (estimate / measured, per run).",
            "The estimate ignores the system prompt, the task text and hidden reasoning, so it should come out low.", "",
            "| Group | Median ratio | Middle half |", "|---|---|---|"] + token_check(groups) + [""]

    out += ["## 8. Skipped runs", ""]
    for g in sorted(groups):
        sk = groups[g].skipped
        out.append(f"- {g}: " + (", ".join(f"{v} ({k})" for k, v in sorted(sk.items())) if sk else "none"))
    out.append("")
    path.write_text("\n".join(out))


def used_groups_all(used):
    return sorted(g for gs in used.values() for g in gs)


METHOD_ORDER = {m: i for i, m in enumerate(BASELINES + SIGNALS)}


# ---------- modes ----------


def load_candidate():
    if not CANDIDATE.exists():
        return None
    cand = json.loads(CANDIDATE.read_text())
    for field in ("method", "chosen_on", "date"):
        if field not in cand:
            raise SystemExit(f"{CANDIDATE} is missing '{field}'")
    method(cand["method"], cand.get("lam") if cand["method"] in SIGNALS else None)  # fails loudly on a bad choice
    return cand


def is_committed(path):
    """True if the file is tracked by git and has no uncommitted changes."""
    try:
        cwd = path.parent
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", path.name], cwd=cwd, capture_output=True).returncode == 0
        clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", path.name], cwd=cwd, capture_output=True).returncode == 0
        return tracked and clean
    except OSError:
        return False


def run_dev(args):
    groups = load_groups(args.data, only={DEV_GROUP})
    if DEV_GROUP not in groups:
        print(f"no data for {DEV_GROUP} in {args.data}; run eval/fetch.py first", file=sys.stderr)
        return 1
    results = run_group(groups[DEV_GROUP], method_keys(), args.splits, args.boot, args.seed)
    rows = [res.row for res in results.values()]
    write_csv(EVAL_DIR / "dev-results.csv", rows)
    print(f"{DEV_GROUP} (development group; these numbers are in-sample)\n")
    print_table(rows)
    best = best_signal(rows)
    if best:
        print(f"\nsuggestion only: method={best['method']} lam={best['lam']:g} "
              f"(saved {best['saved_all_mean']:.1%} at alpha={HEADLINE[0]}, n={HEADLINE[1]})")
    return 0


def run_final(args):
    cand = load_candidate()
    if cand is None:
        print(f"{CANDIDATE} is missing. Choose a method with --dev, write it down and commit it first (research R9).", file=sys.stderr)
        return 2
    if not is_committed(CANDIDATE):
        print(f"warning: {CANDIDATE.name} is not committed; the choice is not on record yet", file=sys.stderr)
    groups = load_groups(args.data)
    if not groups:
        print(f"no data in {args.data}; run eval/fetch.py first", file=sys.stderr)
        return 1
    if args.local:
        groups.update(load_local_groups())
    cand_key = (cand["method"], cand.get("lam") if cand["method"] in SIGNALS else None)
    keys = method_keys(lam=cand_key[1]) if cand_key[1] is not None else method_keys(lam=LAMS[1])
    if cand_key not in keys:
        keys.append(cand_key)
    results = {g.id: run_group(g, keys, args.splits, args.boot, args.seed) for g in groups.values()}

    alpha, n = HEADLINE
    headline = {g: {key: results[g][(key, alpha, n)] for key in keys} for g in results}
    datasets = defaultdict(list)
    for g in sorted(groups):
        if groups[g].role == "holdout":
            datasets[groups[g].dataset].append(g)
    used, baselines, diffs = {}, {}, {}
    for name, gids in sorted(datasets.items()):
        ok = [g for g in gids if all(headline[g][k].row["status"] != "insufficient" for k in (cand_key, ("exact", None), ("steps", None)))]
        used[name] = ok
        if ok:
            baselines[name] = stronger_baseline(headline, ok)
            diffs[name] = paired_diffs(headline, ok, cand_key, baselines[name])
        else:
            diffs[name] = []
    # Validity is judged at the main setting. Elsewhere the true rate can sit right at alpha
    # (e.g. 4.95% at n = 100), so with dozens of rows some would cross by chance alone.
    valid = all(headline[g][cand_key].row["status"] != "invalid" for g in used_groups_all(used))
    verdict, details = decide(diffs, valid)

    RESULTS.mkdir(parents=True, exist_ok=True)
    write_csv(RESULTS / "results.csv", [res.row for g in results for res in results[g].values()])
    sums_file = Path(args.data) / "runs" / "SHA256SUMS"
    sums = sums_file.read_text().splitlines() if sums_file.exists() else []
    public = {g: grp for g, grp in groups.items() if grp.role != "local"}
    write_report(RESULTS / "results.md", args, cand, public, results, verdict, details, baselines, cand_key, used, sums)

    stories = ["# Kill stories", "", f"Failed runs that {label(cand_key)} stops, at the median stop line over the plain splits (α = {alpha:.0%}, n = {n}).",
               "Each shows where the run would have been stopped, why, and the last few actions.", ""]
    for g in sorted(public):
        tau = headline_tau(headline[g][cand_key])
        found = [s for s in (story(g, r, cand_key, tau) for r in public[g].runs if not r.success) if s]
        found.sort(key=lambda s: (-s[1], s[0]))
        stories += [f"## {g}", ""] + ([s[0] + "\n" for s in found[:10]] or ["No failed run is stopped at this stop line.", ""])
        if 0 < len(found) < 10:
            stories += [f"(Only {len(found)} failed runs are stopped at this stop line.)", ""]
    (RESULTS / "kill-stories.md").write_text("\n".join(stories))
    if args.local:
        write_local_details(groups, headline, cand_key)
    print(f"verdict: {verdict}")
    for name, (mean, lo, hi, ok) in details.items():
        print(f"  {name}: candidate minus {baselines.get(name, '-')}: {p1(mean)} [{p1(lo)}, {p1(hi)}] {'above zero' if ok else 'not above zero'}")
    print(f"wrote {RESULTS}/results.csv, results.md, kill-stories.md")
    return 0


def run_story(args):
    gid, run_id = args.story
    groups = load_groups(args.data, only={gid})
    if gid not in groups:
        print(f"no group {gid}", file=sys.stderr)
        return 1
    cand = load_candidate() or {}
    name = args.method or cand.get("method")
    if not name:
        print("give --method (and --lam), or write eval/candidate.json", file=sys.stderr)
        return 1
    key = (name, (args.lam if args.lam is not None else cand.get("lam")) if name in SIGNALS else None)
    run = next((r for r in groups[gid].runs if r.run == run_id), None)
    if run is None:
        print(f"no run {run_id} in {gid}", file=sys.stderr)
        return 1
    res = run_group(groups[gid], [key], args.splits, args.boot, args.seed, settings=[HEADLINE])[(key, *HEADLINE)]
    s = story(gid, run, key, headline_tau(res))
    print(s[0] if s else f"{run_id} is not stopped at the median stop line ({headline_tau(res):g}).")
    return 0


PROJECTS = Path.home() / ".claude" / "projects"
EXCLUDE = Path.home() / ".loopbrake" / "exclude.txt"


def load_local_groups(projects=None):
    """Your own Claude Code history, one group per project folder, renamed local-1, local-2, ...

    The folder names (which can reveal employer or client names) only go to
    ~/.loopbrake/eval/local-map.json, never into the repository (constitution Principle VI).
    """
    projects = Path(projects or PROJECTS)
    exclude = set(EXCLUDE.read_text().split()) if EXCLUDE.exists() else set()
    groups, mapping = {}, {}
    folders = sorted(p for p in projects.iterdir() if p.is_dir()) if projects.exists() else []
    for folder in folders:
        runs, skipped = [], defaultdict(int)
        for f in sorted(folder.glob("*.jsonl")):
            found, sk = claude_code_turns(f, exclude)
            runs += [r for r in found if r.steps]
            skipped["no steps"] += sum(1 for r in found if not r.steps)
            for k, v in sk.items():
                skipped[k] += v
        if not runs:
            continue
        label = f"local-{len(groups) + 1}"
        mapping[label] = folder.name
        runs = sorted((r._replace(group=label) for r in runs), key=lambda r: r.run)
        groups[label] = Group(label, "claude-code-local", "local", runs, dict(skipped))
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    (EVAL_DIR / "local-map.json").write_text(json.dumps(mapping, indent=1))
    return groups


def write_local_details(groups, headline, cand_key):
    """Per-run results for your own history. Written outside the repository only."""
    out_dir = EVAL_DIR / "local"
    out_dir.mkdir(parents=True, exist_ok=True)
    for g, grp in groups.items():
        if grp.role != "local":
            continue
        tau = headline_tau(headline[g][cand_key]) if headline[g][cand_key].taus else math.inf
        scorer = method(*cand_key)
        with open(out_dir / f"{g}.csv", "w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["run", "success", "exit", "steps", "tokens", "stopped_at_step", "tokens_saved"])
            for r in grp.runs:
                p = prepare(r, scorer)
                k = kill_index(p, tau, fixed=cand_key[0] == "fixed")
                w.writerow([r.run, r.success, r.exit or "", len(r.steps), p.total, "" if k is None else k + 1, "" if k is None else p.tail[k]])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Replay recorded agent runs through LoopBrake.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dev", action="store_true", help="explore methods on the development group (default)")
    mode.add_argument("--final", action="store_true", help="evaluate every group and write eval/results/")
    mode.add_argument("--story", nargs=2, metavar=("GROUP", "RUN"), help="print one kill story")
    ap.add_argument("--local", action="store_true", help="add your own Claude Code history (kept local)")
    ap.add_argument("--method")
    ap.add_argument("--lam", type=float)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--splits", type=int, default=1000)
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--data", type=Path, default=DATA)
    args = ap.parse_args(argv)
    if args.splits < 500:
        ap.error("--splits must be at least 500 (spec FR-008)")
    if args.final:
        return run_final(args)
    if args.story:
        return run_story(args)
    return run_dev(args)


if __name__ == "__main__":
    sys.exit(main())
