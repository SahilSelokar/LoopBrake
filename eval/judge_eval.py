"""Evaluate judge-based stop rules on stored Jev judgments (feature 002-progress-judge).

Reuses Phase 1's splits, stop-line rule and intervals (eval/run.py, unchanged) and counts savings
NET of the judge's own tokens. Never calls Jev: it only reads stored judgments.
Commands: specs/002-progress-judge/contracts/judge-cli.md. Outputs: contracts/judge-results.md.
"""
import argparse
import csv
import hashlib
import importlib.util
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import NamedTuple

from loopbrake.conformal import rank, threshold
from loopbrake.signals import JUDGED, judged, method


def _load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ev = _load("run")
jd = _load("judge")

DATA = ev.DATA
RESULTS = Path(__file__).parent / "results" / "judge"
CANDIDATE = Path(__file__).with_name("judge_candidate.json")
JUDGMENTS = jd.JUDGMENTS
LAMS = (0.8, 0.9, 1.0)
PHASE1 = ("max", 0.9)
BASE_KEYS = [("fixed", None, None), ("exact", None, None), ("steps", None, None), ("max", 0.9, None)]
NET_COLUMNS = ev.COLUMNS[:7] + ["ask_level", "setup"] + ev.COLUMNS[7:] + [
    "net_saved_mean", "net_saved_lo", "net_saved_hi", "judge_share", "asked_share"]
RATES = ev.RATE_COLUMNS | {"net_saved_mean", "net_saved_lo", "net_saved_hi", "judge_share", "asked_share"}


def candidate_committed():
    return CANDIDATE.exists() and ev.is_committed(CANDIDATE)


# ---------- turning judgments into per-step lists ----------


def load_judgments(setup, groups):
    """{(group, run, step): judgment} for the given groups."""
    out = {}
    for g in groups:
        path = JUDGMENTS / setup.replace("/", "-") / f"{g}.jsonl"
        if path.exists():
            for d in map(json.loads, path.read_text().splitlines()):
                out[(d["group"], d["run"], d["step"])] = d
    return out


def judgment_lists(group, run, judgments, asked=None):
    """progress, kinds and judge-token lists for one run. Steps not asked, or with no stored answer,
    are "no opinion" (None) and cost nothing. Returns (progress, kinds, tokens, missing)."""
    progress, kinds, tokens, missing = [], [], [], 0
    for i in range(len(run.steps)):
        j = None if asked is not None and not asked[i] else judgments.get((group, run.run, i + 1))
        if j is None:
            missing += asked is None or bool(asked[i])
            progress.append(None)
            kinds.append(None)
            tokens.append(0)
            continue
        progress.append(j["progress"])
        kinds.append((j["kind"], j["kind_p"]) if j.get("kind") and j.get("kind_p") is not None else None)
        tokens.append(j["tokens"])
    return progress, kinds, tokens, missing


def phase1_scores(run):
    return [s for s, _ in method(*PHASE1)(run.steps)]


def asked_flags(run, level):
    """Ask the judge only where the Phase 1 stuck score already reaches `level` (research R8)."""
    return [s >= level for s in phase1_scores(run)]


def ask_levels(runs):
    """The 50th, 75th and 90th percentiles of the Phase 1 step scores on the development group."""
    cuts = statistics.quantiles([s for r in runs for s in phase1_scores(r)], n=20)
    return [cuts[9], cuts[14], cuts[17]]


class NetPrep(NamedTuple):
    run: str
    task: str
    success: bool
    peak: list
    tail: list
    total: int
    judge_cum: list  # judge tokens spent on steps 1..i+1
    asked_cum: list  # steps the judge was asked about, 1..i+1


def prepare_net(run, scores, judge_tokens, asked):
    peak, top = [], -math.inf
    for score, _ in scores:
        top = max(top, score)
        peak.append(top)
    total = left = sum(s.tokens for s in run.steps)
    tail, judge_cum, asked_cum, j, a = [], [], [], 0, 0
    for s, t, q in zip(run.steps, judge_tokens, asked):
        left -= s.tokens
        tail.append(left)
        j += t if q else 0
        a += bool(q)
        judge_cum.append(j)
        asked_cum.append(a)
    return NetPrep(run.run, run.task, run.success, peak, tail, total, judge_cum, asked_cum)


# ---------- measuring (Phase 1 rules, plus the judge's cost) ----------


class NetSplit(NamedTuple):
    fk: float | None
    saved_all: float | None
    saved_fail: float | None
    lost: float | None
    kill_steps: list
    held_successes: int
    tau: float | None
    net_saved: float | None
    judge_share: float | None
    asked_share: float | None


def measure_net(preps, cal, held, alpha, fixed=False, tau=None):
    if tau is None and not fixed:
        tau = threshold([preps[i].peak[-1] for i in cal], alpha)
    wins = stopped_wins = all_tok = fail_tok = saved = saved_fail = lost = judge = asked = ran = 0
    steps = []
    for i in held:
        p = preps[i]
        all_tok += p.total
        wins += p.success
        if not p.success:
            fail_tok += p.total
        k = ev.kill_index(p, tau, fixed)
        last = len(p.peak) - 1 if k is None else k  # the judge works on every step until the stop
        judge += p.judge_cum[last]
        asked += p.asked_cum[last]
        ran += last + 1
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

    return NetSplit(share(stopped_wins, wins), share(saved, all_tok), share(saved_fail, fail_tok), share(lost, all_tok),
                    steps, wins, tau, share(saved - judge, all_tok), share(judge, all_tok), share(asked, ran))


def summarize_net(plain, boot, alpha, fixed=False):
    row = ev.summarize(plain, boot, alpha, fixed)
    net = [s.net_saved for s in plain if s.net_saved is not None]
    row["net_saved_mean"] = statistics.fmean(net) if net else None
    row["net_saved_lo"], row["net_saved_hi"] = ev._boot_interval([s.net_saved for s in boot if s.net_saved is not None])
    for name in ("judge_share", "asked_share"):
        vals = [getattr(s, name) for s in plain if getattr(s, name) is not None]
        row[name] = statistics.fmean(vals) if vals else None
    return row


def evaluate_net(gid, preps_by_key, alpha, n, splits, boots, seed):
    """Phase 1's evaluate(), with net savings. Every method sees the same splits."""
    base = next(iter(preps_by_key.values()))
    if rank(n, alpha) > n or sum(p.success for p in base) < n:
        return {key: ev.Result({"status": "insufficient", "splits": 0}, [], []) for key in preps_by_key}
    plain, boot = defaultdict(list), defaultdict(list)
    for kind, count, out in (("plain", splits, plain), ("boot", boots, boot)):
        rng = ev.split_rng(seed, gid, alpha, n, kind)
        for _ in range(count):
            items = range(len(base)) if kind == "plain" else ev.boot_items(rng, base)
            split = ev.make_split(rng, items, base, n)
            if split is None:
                continue
            cal, held = split
            if sum(base[i].success for i in held) < ev.MIN_HELD_SUCCESSES:
                continue
            for key, preps in preps_by_key.items():
                out[key].append(measure_net(preps, cal, held, alpha, fixed=key[0] == "fixed"))
    usable = len(next(iter(plain.values()), []))
    if usable < splits / 2 or not boot:
        return {key: ev.Result({"status": "insufficient", "splits": usable}, [], []) for key in preps_by_key}
    return {key: ev.Result(summarize_net(plain[key], boot[key], alpha, fixed=key[0] == "fixed") | {"splits": usable},
                           [s.net_saved for s in boot[key]], [s.tau for s in plain[key]]) for key in preps_by_key}


# ---------- running groups ----------


def prepare_group(group, keys, judgments):
    """Prepared runs for every method key (name, lam, ask_level). Returns (preps_by_key, missing judgments)."""
    preps, missing = {key: [] for key in keys}, 0
    base_scores = {r.run: phase1_scores(r) for r in group.runs}
    for r in group.runs:
        n = len(r.steps)
        full = judgment_lists(group.id, r, judgments)
        missing += full[3]
        for key in keys:
            name, lam, ask = key
            if name in JUDGED:
                flags = [s >= ask for s in base_scores[r.run]] if ask is not None else [True] * n
                progress, kinds, tokens, _ = full if ask is None else judgment_lists(group.id, r, judgments, flags)
                scores = judged(name, lam)(r.steps, progress, kinds)
                preps[key].append(prepare_net(r, scores, tokens, flags))
            else:
                preps[key].append(prepare_net(r, method(name, lam)(r.steps), [0] * n, [False] * n))
    return preps, missing


def run_group(group, keys, judgments, splits, boots, seed, setup, settings=None):
    preps, missing = prepare_group(group, keys, judgments)
    out = {}
    for alpha, n in settings or [(a, s) for a in ev.ALPHAS for s in ev.SIZES]:
        for key, res in evaluate_net(group.id, preps, alpha, n, splits, boots, seed).items():
            res.row.update(ev.group_info(group) | {"method": key[0], "lam": key[1], "ask_level": key[2], "alpha": alpha,
                                                   "n": n, "setup": setup if key[0] in JUDGED else None})
            out[(key, alpha, n)] = res
    return out, missing


def fmt(col, v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v).lower()
    if col in RATES:
        return f"{v:.4f}"
    return f"{v:.4g}" if isinstance(v, float) else str(v)


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(rows, key=lambda r: (r["group"], r["method"], r["lam"] or 0, r["ask_level"] or 0, r["alpha"], r["n"]))
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(NET_COLUMNS)
        for r in rows:
            w.writerow([fmt(c, r.get(c)) for c in NET_COLUMNS])


def pct(v):
    return "   -  " if v is None else f"{v:6.1%}"


def label(key):
    name, lam, ask = key
    out = name if lam is None else f"{name} (λ {lam:g})"
    return out + (f", ask ≥ {ask:.3g}" if ask is not None else "")


# ---------- judge facts (latency, cost, health) ----------


def judge_facts(judgments, setup):
    js = list(judgments.values())
    ms = [j["ms"] for j in js if j["status"] in ("ok", "truncated_ok")]
    ps = [j["progress"] for j in js if j["progress"] is not None]
    rc_path = JUDGMENTS / setup.replace("/", "-") / "recheck.json"
    tokens = sum(j["tokens"] for j in js)
    return {
        "calls": len(js), "tokens": tokens, "dollars": tokens * jd.PRICE_PER_MILLION / 1e6,
        "status": Counter(j["status"] for j in js),
        "ms_median": statistics.median(ms) if ms else None,
        "ms_p95": statistics.quantiles(ms, n=20)[-1] if len(ms) > 1 else None,
        "p_spread": (statistics.quantiles(ps, n=20)[-1] - statistics.quantiles(ps, n=20)[0]) if len(ps) > 1 else 0.0,
        "no_opinion": 1 - len(ps) / len(js) if js else 1.0,
        "kinds": Counter(j["kind"] for j in js if j.get("kind")),
        "recheck": json.loads(rc_path.read_text()) if rc_path.exists() else None,
    }


def delay(row, facts):
    """Expected extra wait per agent step: typical and worst 5% (research R8)."""
    if facts["ms_median"] is None or row.get("asked_share") is None:
        return None, None
    return row["asked_share"] * facts["ms_median"], facts["ms_p95"]


# ---------- modes ----------


def default_setup():
    if CANDIDATE.exists():
        return json.loads(CANDIDATE.read_text())["setup"]
    return jd.setup_id("v1")


def run_dev(args):
    setup = args.setup or default_setup()
    groups = ev.load_groups(args.data, only={ev.DEV_GROUP})
    if ev.DEV_GROUP not in groups:
        print(f"no data for {ev.DEV_GROUP} in {args.data}; run eval/fetch.py first", file=sys.stderr)
        return 1
    g = groups[ev.DEV_GROUP]
    judgments = load_judgments(setup, [g.id])
    if not judgments:
        print(f"no stored judgments for {g.id} under setup {setup}; run eval/judge.py first", file=sys.stderr)
        return 1
    levels = ask_levels(g.runs)
    keys = BASE_KEYS + [(m, lam, None) for m in JUDGED for lam in LAMS] + [(m, lam, L) for m in JUDGED for lam in LAMS for L in levels]
    results, missing = run_group(g, keys, judgments, args.splits, args.boot, args.seed, setup)
    rows = [res.row for res in results.values()]
    write_csv(ev.EVAL_DIR / "judge-dev-results.csv", rows)
    facts = judge_facts(judgments, setup)
    print(f"{g.id}, setup {setup} (development group; these numbers are in-sample)")
    print(f"judge: {facts['calls']:,} judgments, missing {missing:,}, no opinion {facts['no_opinion']:.1%}, "
          f"P(progress) spread (5th-95th pct) {facts['p_spread']:.2f}, median {facts['ms_median']} ms, about ${facts['dollars']:.2f}")
    if facts["p_spread"] < 0.1 or facts["no_opinion"] > 0.10:
        print("WARNING: setup looks broken (research R9): answers barely vary or too many have no opinion")
    print(f"ask levels (50th/75th/90th pct of Phase 1 scores): {', '.join(f'{x:.3g}' for x in levels)}\n")
    a, n = ev.HEADLINE
    print(f"{'method':34} {'false stops [95%]':>25}  {'saved':>6}  {'net saved [95%]':>26}  {'judge':>6}  {'asked':>6}  {'delay ms':>8}")
    for key in keys:
        r = results[(key, a, n)].row
        d, _ = delay(r, facts) if key[0] in JUDGED else (None, None)
        print(f"{label(key):34} {pct(r.get('fk_mean'))} [{pct(r.get('fk_lo'))},{pct(r.get('fk_hi'))}]  {pct(r.get('saved_all_mean'))}  "
              f"{pct(r.get('net_saved_mean'))} [{pct(r.get('net_saved_lo'))},{pct(r.get('net_saved_hi'))}]  "
              f"{pct(r.get('judge_share'))}  {pct(r.get('asked_share'))}  {'' if d is None else f'{d:8.0f}'}  {r['status']}")
    pool = [(results[(k, a, n)].row, k) for k in keys if k[0] in JUDGED and results[(k, a, n)].row["status"] == "ok"]
    if pool:
        row, k = max(pool, key=lambda x: (x[0]["net_saved_mean"], -JUDGED.index(x[1][0])))
        print(f"\nsuggestion only: {label(k)}: net saved {row['net_saved_mean']:.1%} at alpha={a}, n={n}")
        print(f'  candidate line: {{"setup": "{setup}", "method": "{k[0]}", "lam": {k[1]}, "ask_level": {"null" if k[2] is None else repr(k[2])}, '
              f'"chosen_on": "{ev.DEV_GROUP}", "date": "YYYY-MM-DD"}}')
    return 0


def load_candidate():
    if not CANDIDATE.exists():
        return None
    cand = json.loads(CANDIDATE.read_text())
    for field in ("setup", "method", "lam", "ask_level", "chosen_on", "date"):
        if field not in cand:
            raise SystemExit(f"{CANDIDATE} is missing '{field}'")
    judged(cand["method"], cand["lam"])  # fails loudly on a bad choice
    return cand


def stronger_bar(headline, gids):
    return max(("exact", "steps"), key=lambda m: statistics.fmean(headline[g][(m, None, None)].row["saved_all_mean"] for g in gids))


def paired(headline, gids, cand_key, bar):
    per = [[c - b for c, b in zip(headline[g][cand_key].boot_saved, headline[g][(bar, None, None)].boot_saved)] for g in gids]
    count = min((len(x) for x in per), default=0)
    return [statistics.fmean(x[r] for x in per) for r in range(count)]


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stories_for(group, cand_key, tau, judgments, limit=10):
    found = []
    for r in group.runs:
        if r.success:
            continue
        s = one_story(group.id, r, cand_key, tau, judgments)
        if s:
            found.append(s)
    found.sort(key=lambda s: (-s[1], s[0]))
    return found[:limit], len(found)


def one_story(gid, r, cand_key, tau, judgments):
    name, lam, ask = cand_key
    flags = asked_flags(r, ask) if ask is not None else None
    progress, kinds, tokens, _ = judgment_lists(gid, r, judgments, flags)
    scores = judged(name, lam)(r.steps, progress, kinds)
    p = prepare_net(r, scores, tokens, flags or [True] * len(r.steps))
    k = ev.kill_index(p, tau)
    if k is None:
        return None
    phase1_reason = method(*PHASE1)(r.steps)[k][1]
    reason = "; ".join(x for x in (scores[k][1], phase1_reason) if x) or "score above the stop line"
    share = f" ({p.tail[k] / p.total:.0%})" if p.total else ""
    lines = [f"### {gid} · {r.run} · stopped at step {k + 1} of {len(r.steps)} · saved {p.tail[k]:,} tokens{share}, "
             f"judge spent {p.judge_cum[k]:,}", f"Reason: {reason}", "```text"]
    lines += [f"{t + 1:>4}  {ev.trim(ev.display(r.steps[t].action))}" for t in range(max(0, k - 4), k + 1)]
    return "\n".join(lines + ["```"]), p.tail[k]


def run_final(args):
    cand = load_candidate()
    if cand is None:
        print(f"{CANDIDATE} is missing. Choose with --dev, write it down and commit it first (research R9).", file=sys.stderr)
        return 2
    if not candidate_committed():
        print(f"warning: {CANDIDATE.name} is not committed; the choice is not on record yet", file=sys.stderr)
    setup = cand["setup"]
    groups = ev.load_groups(args.data)
    public = {g: grp for g, grp in groups.items() if g in jd.PUBLIC_GROUPS}
    judgments = load_judgments(setup, public)
    for g, grp in public.items():
        if grp.role == "holdout":
            gap = sum(judgment_lists(g, r, judgments)[3] for r in grp.runs)
            if gap:
                print(f"{g}: {gap} steps have no stored judgment; run eval/judge.py --group {g} first", file=sys.stderr)
                return 1
    cand_key = (cand["method"], cand["lam"], cand["ask_level"])
    keys = BASE_KEYS + [(m, cand["lam"], None) for m in JUDGED]
    if cand_key not in keys:
        keys.append(cand_key)
    results, missing = {}, {}
    for g, grp in public.items():
        results[g], missing[g] = run_group(grp, keys, judgments, args.splits, args.boot, args.seed, setup)

    a, n = ev.HEADLINE
    headline = {g: {k: results[g][(k, a, n)] for k in keys} for g in results}
    datasets = defaultdict(list)
    for g in sorted(public):
        if public[g].role == "holdout":
            datasets[public[g].dataset].append(g)
    used, bars, diffs = {}, {}, {}
    for name, gids in sorted(datasets.items()):
        ok = [g for g in gids if all(headline[g][k].row["status"] != "insufficient" for k in (cand_key, ("exact", None, None), ("steps", None, None)))]
        used[name] = ok
        if ok:
            bars[name] = stronger_bar(headline, ok)
            diffs[name] = paired(headline, ok, cand_key, bars[name])
        else:
            diffs[name] = []
    invalid = [g for gs in used.values() for g in gs if headline[g][cand_key].row["status"] == "invalid"]
    verdict, details = ev.decide(diffs, not invalid)

    RESULTS.mkdir(parents=True, exist_ok=True)
    write_csv(RESULTS / "results.csv", [res.row for g in results for res in results[g].values()])
    facts = judge_facts(judgments, setup)
    write_report(RESULTS / "results.md", args, cand, cand_key, public, results, headline, verdict, details, bars, used, invalid, facts, missing)
    out = ["# Kill stories (progress judge)", "",
           f"Failed runs that {label(cand_key)} stops, at the median stop line over the plain splits (α = {a:.0%}, n = {n}).",
           "Each Reason line gives the judge's view first, then the Phase 1 signals.", ""]
    for g in sorted(public):
        tau = ev.headline_tau(headline[g][cand_key])
        found, total = stories_for(public[g], cand_key, tau, judgments)
        out += [f"## {g}", ""] + ([s[0] + "\n" for s in found] or ["No failed run is stopped at this stop line.", ""])
        if 0 < total < 10:
            out += [f"(Only {total} failed runs are stopped at this stop line.)", ""]
    (RESULTS / "kill-stories.md").write_text("\n".join(out))
    print(f"verdict: {verdict}")
    for name, (mean, lo, hi, ok) in details.items():
        print(f"  {name}: net saved minus {bars.get(name, '-')}: {ev.p1(mean)} [{ev.p1(lo)}, {ev.p1(hi)}] {'above zero' if ok else 'not above zero'}")
    print(f"wrote {RESULTS}/results.csv, results.md, kill-stories.md")
    return 0


def write_report(path, args, cand, cand_key, public, results, headline, verdict, details, bars, used, invalid, facts, missing):
    a, n = ev.HEADLINE
    p1 = ev.p1
    sdir = JUDGMENTS / cand["setup"].replace("/", "-")
    sums_file = Path(args.data) / "runs" / "SHA256SUMS"
    sums = [l for l in (sums_file.read_text().splitlines() if sums_file.exists() else []) if l.split()[-1].removesuffix(".jsonl") in public]
    jsums = [f"{file_sha(p)}  judgments/{p.name}" for p in sorted(sdir.glob("*.jsonl")) if p.stem in public]
    o = ["# LoopBrake progress judge: results", ""]
    o += ["## 1. Reproduce", "", "```bash", "uv run python eval/fetch.py", "uv run python eval/tasks.py",
          f"uv run python eval/judge.py --group {' '.join(sorted(public))}",
          f"uv run python eval/judge_eval.py --final --seed {args.seed} --splits {args.splits} --boot {args.boot}", "```", "",
          f"Judge setup: `{cand['setup']}`. Fingerprints (sha256) of the runs and the stored judgments:", "", "```text"] + sums + jsums + ["```", ""]
    o += [f"## 2. Verdict: {verdict}", "",
          f"Method chosen in advance on `{cand['chosen_on']}` ({cand['date']}): **{label(cand_key)}**.", "",
          "| Dataset | Groups tested | Bar to beat | Extra NET tokens saved [95% interval] | Above zero |", "|---|---|---|---|---|"]
    for name, (mean, lo, hi, ok) in details.items():
        o.append(f"| {name} | {', '.join(used[name]) or 'none'} | {bars.get(name, '–')} | {p1(mean)} [{p1(lo)}, {p1(hi)}] | {'yes' if ok else 'no'} |")
    o += ["", f"Chosen method within its false-stop limit on every holdout group: {'yes' if not invalid else 'no (' + ', '.join(invalid) + ')'}.", "",
          "Net means the judge's own tokens are subtracted, counted one for one with the agent's tokens, although they cost less.", ""]
    o += [f"## 3. Main table (α = {a:.0%}, n = {n})", "",
          "| Group | Method | False stops [95%] | Tokens saved | Net saved [95%] | Judge share | Status |", "|---|---|---|---|---|---|---|"]
    for g in sorted(public):
        for k in [("exact", None, None), ("steps", None, None), ("max", 0.9, None), cand_key]:
            r = headline[g][k].row
            o.append(f"| {g}{' (dev)' if public[g].role == 'dev' else ''} | {label(k)} | {p1(r.get('fk_mean'))} [{p1(r.get('fk_lo'))}, {p1(r.get('fk_hi'))}] | "
                     f"{p1(r.get('saved_all_mean'))} | {p1(r.get('net_saved_mean'))} [{p1(r.get('net_saved_lo'))}, {p1(r.get('net_saved_hi'))}] | "
                     f"{p1(r.get('judge_share'))} | {r['status']} |")
    o += ["", "## 4. Against Phase 1 and FailFast", ""]
    if "swe-gpt5mini" in results:
        o += ["| Method | Net tokens saved at 5% false stops (swe-gpt5mini) |", "|---|---|"]
        for k in [("steps", None, None), ("max", 0.9, None), cand_key]:
            for size in (20, 100):
                o.append(f"| {label(k)}, n = {size} | {p1(results['swe-gpt5mini'][(k, 0.05, size)].row.get('net_saved_mean'))} |")
        o += [f"| {name} (paper, other models) | {v} |" for name, v in ev.FAILFAST]
        o += ["", "Caveats, as in Phase 1: FailFast set its 5% line on the data it reports on; it used other models; it does not say which tokens it counts.", ""]
    o += ["## 5. Ask only when needed", ""]
    for g in sorted(public):
        r = headline[g][cand_key].row
        d, worst = delay(r, facts)
        o.append(f"- {g}: judge asked on {p1(r.get('asked_share'))} of steps; expected extra delay per agent step "
                 f"{'–' if d is None else f'{d:.0f} ms'} typical, {'–' if worst is None else f'{worst:.0f} ms'} worst 5%.")
    o += ["", "Phase 3's live target is 200 ms per step.", ""]
    st = facts["status"]
    o += ["## 6. The judge itself", "",
          f"- Calls: {facts['calls']:,}; tokens: {facts['tokens']:,}; cost: about ${facts['dollars']:.2f}",
          f"- No opinion: {facts['no_opinion']:.1%} ({st.get('unreadable', 0):,} unreadable, {st.get('service_error', 0):,} service errors)",
          f"- Inputs shortened to fit: {st.get('truncated_ok', 0) / max(1, facts['calls']):.1%}",
          f"- Time per call: median {facts['ms_median']} ms, 95th percentile {facts['ms_p95']:.0f} ms" if facts["ms_p95"] else "- Time per call: –",
          f"- Re-check (same answer when asked again): {facts['recheck']['agree']:.1%} of {facts['recheck']['sample']} steps" if facts["recheck"] else "- Re-check: not run",
          f"- Most common kinds of step: {', '.join(f'{k} {v:,}' for k, v in facts['kinds'].most_common(5))}", ""]
    o += [f"## 7. All methods (α = {a:.0%}, n = {n})", "", "Exploratory. Development rows are in-sample.", "",
          "| Group | Method | False stops | Net saved | Status |", "|---|---|---|---|---|"]
    for g in sorted(public):
        for k in headline[g]:
            r = headline[g][k].row
            o.append(f"| {g}{' (dev)' if public[g].role == 'dev' else ''} | {label(k)} | {p1(r.get('fk_mean'))} | {p1(r.get('net_saved_mean'))} | {r['status']} |")
    o += ["", "## 8. Skipped and missing", ""]
    for g in sorted(public):
        sk = public[g].skipped
        o.append(f"- {g}: skipped runs {', '.join(f'{v} ({k})' for k, v in sorted(sk.items())) or 'none'}; steps without a judgment: {missing[g]:,}")
    o.append("")
    path.write_text("\n".join(o))


def run_story(args):
    gid, run_id = args.story
    cand = load_candidate() or {}
    name = args.method or cand.get("method")
    if not name:
        print("give --method and --lam, or write eval/judge_candidate.json", file=sys.stderr)
        return 1
    key = (name, args.lam if args.lam is not None else cand.get("lam"), cand.get("ask_level") if not args.method else None)
    groups = ev.load_groups(args.data, only={gid})
    if gid not in groups:
        print(f"no group {gid}", file=sys.stderr)
        return 1
    setup = args.setup or default_setup()
    judgments = load_judgments(setup, [gid])
    r = next((x for x in groups[gid].runs if x.run == run_id), None)
    if r is None:
        print(f"no run {run_id} in {gid}", file=sys.stderr)
        return 1
    res, _ = run_group(groups[gid], [key], judgments, args.splits, args.boot, args.seed, setup, settings=[ev.HEADLINE])
    tau = ev.headline_tau(res[(key, *ev.HEADLINE)])
    s = one_story(gid, r, key, tau, judgments)
    print(s[0] if s else f"{run_id} is not stopped at the median stop line ({tau:g}).")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Evaluate judge-based stop rules on stored Jev judgments.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dev", action="store_true")
    mode.add_argument("--final", action="store_true")
    mode.add_argument("--story", nargs=2, metavar=("GROUP", "RUN"))
    ap.add_argument("--setup")
    ap.add_argument("--method")
    ap.add_argument("--lam", type=float)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--splits", type=int, default=1000)
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--data", type=Path, default=DATA)
    args = ap.parse_args(argv)
    if args.splits < 500:
        ap.error("--splits must be at least 500 (spec FR-008 of Phase 1)")
    if args.final:
        return run_final(args)
    if args.story:
        return run_story(args)
    return run_dev(args)


if __name__ == "__main__":
    sys.exit(main())
