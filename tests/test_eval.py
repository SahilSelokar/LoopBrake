import importlib.util
import random
from pathlib import Path

from loopbrake.signals import Step
from loopbrake.traces import Run


def count_steps(steps):
    """Stand-in scorer for engine tests: the score at step t is t."""
    return [(i + 1, f"step {i + 1}") for i in range(len(steps))]

spec = importlib.util.spec_from_file_location("evalrun", Path(__file__).parents[1] / "eval" / "run.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


def make_run(task, idx, length, success):
    steps = tuple(Step(f"cmd {i}", "", None, 10 + i) for i in range(length))
    return Run("toy", "toy-set", task, f"{task}-{idx}", success, None, True, steps)


# 6 tasks x 2 runs. Short runs succeed, long runs fail.
RUNS = sorted(
    (make_run(f"t{t}", i, 3 + t if i == 0 else 8 + t, i == 0) for t in range(6) for i in range(2)),
    key=lambda r: r.run,
)


def preps():
    return [ev.prepare(r, count_steps) for r in RUNS]


def test_stop_step_and_saved_tokens():
    run = Run("g", "d", "t", "r", False, None, True, tuple(Step(f"a{i}", "", None, tok) for i, tok in enumerate([5, 7, 11, 13])))
    p = ev.prepare(run, count_steps)  # scores 1, 2, 3, 4
    assert p.peak == [1, 2, 3, 4] and p.total == 36
    assert ev.kill_index(p, 2) == 2 and p.tail[2] == 13  # stopped after step 3, step 4's tokens saved
    assert ev.kill_index(p, 3.5) == 3 and p.tail[3] == 0  # stopped on the last step: nothing saved
    assert ev.kill_index(p, 4) is None
    assert ev.kill_index(p, float("inf")) is None


def test_splits_never_share_a_task():
    ps = preps()
    rng = random.Random(1)
    for kind in ("plain", "boot"):
        for _ in range(200):
            items = list(range(len(ps))) if kind == "plain" else ev.boot_items(rng, ps)
            split = ev.make_split(rng, items, ps, 3)
            if split is None:
                continue
            cal, held = split
            assert {ps[i].task for i in cal}.isdisjoint({ps[i].task for i in held})


def test_same_seed_same_splits():
    ps = preps()

    def draw(seed):
        rng = ev.split_rng(seed, "toy", 0.05, 3, "plain")
        return [ev.make_split(rng, range(len(ps)), ps, 3) for _ in range(20)]

    assert draw(0) == draw(0)
    assert draw(0) != draw(1)


def test_insufficient_when_too_few_successes_or_k_above_n(monkeypatch):
    monkeypatch.setattr(ev, "MIN_HELD_SUCCESSES", 1)
    by_key = {("steps", None): preps()}
    assert ev.evaluate("toy", by_key, 0.05, 7, 50, 50, 0)[("steps", None)].row["status"] == "insufficient"  # 6 successes < 7
    assert ev.evaluate("toy", by_key, 0.05, 6, 50, 50, 0)[("steps", None)].row["status"] == "insufficient"  # k = 7 > n = 6
    ok = ev.evaluate("toy", by_key, 0.5, 2, 50, 50, 0)[("steps", None)].row
    assert ok["status"] in ("ok", "invalid") and ok["splits"] == 50


def test_insufficient_when_held_out_successes_are_few():
    # With the real minimum of 20 held-out successes, a 6-success group can never be measured.
    by_key = {("steps", None): preps()}
    assert ev.evaluate("toy", by_key, 0.5, 2, 50, 50, 0)[("steps", None)].row["status"] == "insufficient"


def test_invalid_only_for_calibrated_methods():
    bad = [ev.Split(fk=0.5, saved_all=0.1, saved_fail=0.2, lost=0.0, kill_steps=[3], held_successes=30, tau=1.0)] * 10
    assert ev.summarize(bad, bad, 0.05, fixed=False)["status"] == "invalid"
    assert ev.summarize(bad, bad, 0.05, fixed=True)["status"] == "ok"
    good = [ev.Split(fk=0.0, saved_all=0.1, saved_fail=0.2, lost=0.0, kill_steps=[], held_successes=30, tau=1.0)] * 10
    assert ev.summarize(good, good, 0.05, fixed=False)["status"] == "ok"


# ---------- go / no-go decision (US2) ----------


def fake(saved_mean, boot):
    return ev.Result({"saved_all_mean": saved_mean, "status": "ok"}, boot, [])


def test_stronger_baseline_and_paired_differences():
    headline = {
        "g1": {("exact", None): fake(0.10, [0.10, 0.12]), ("steps", None): fake(0.20, [0.18, 0.22]), ("loop", 0.9): fake(0.30, [0.31, 0.29])},
        "g2": {("exact", None): fake(0.30, [0.30, 0.30]), ("steps", None): fake(0.25, [0.24, 0.26]), ("loop", 0.9): fake(0.40, [0.40, 0.40, 0.5])},
    }
    assert ev.stronger_baseline(headline, ["g1", "g2"]) == "steps"  # means 0.225 vs 0.20
    diffs = ev.paired_diffs(headline, ["g1", "g2"], ("loop", 0.9), "steps")
    assert [round(d, 6) for d in diffs] == [round(((0.31 - 0.18) + (0.40 - 0.24)) / 2, 6), round(((0.29 - 0.22) + (0.40 - 0.26)) / 2, 6)]


def test_decision_needs_both_datasets_above_zero_and_validity():
    up, mixed = [0.05 + i * 1e-4 for i in range(100)], [-0.05 + i * 1e-3 for i in range(100)]
    assert ev.decide({"a": up, "b": up}, valid_everywhere=True)[0] == "GO"
    assert ev.decide({"a": up, "b": mixed}, valid_everywhere=True)[0] == "NO-GO"
    assert ev.decide({"a": up, "b": up}, valid_everywhere=False)[0] == "NO-GO"
    assert ev.decide({"a": up, "b": []}, valid_everywhere=True)[0] == "NO-GO"


def test_final_refuses_without_a_chosen_method(tmp_path, monkeypatch):
    monkeypatch.setattr(ev, "CANDIDATE", tmp_path / "candidate.json")
    assert ev.main(["--final", "--data", str(tmp_path)]) == 2
