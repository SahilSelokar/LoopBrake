import itertools
import json

import pytest

import liveness
from loopbrake.signals import BASELINES, METHODS, Step, method


def demo_steps(agent, limit=30):
    return [Step(f"{tool} {json.dumps(args, sort_keys=True)}", "", None, 1) for tool, args in itertools.islice(agent(), limit)]


def first_at_least_one(scores):
    return next((t for t, (score, _) in enumerate(scores, 1) if score >= 1), None)


def test_fixed_matches_liveness_watch():
    fixed = method("fixed")
    assert liveness.watch(liveness.looping()) == ("stuck", 5)
    assert first_at_least_one(fixed(demo_steps(liveness.looping))) == 5
    assert liveness.watch(liveness.wandering()) == ("over_budget", 20)
    assert first_at_least_one(fixed(demo_steps(liveness.wandering))) == 21  # watch refuses step 21
    assert first_at_least_one(fixed(demo_steps(liveness.healthy))) is None
    assert "3 times" in fixed(demo_steps(liveness.looping))[4][1]
    assert "step limit" in fixed(demo_steps(liveness.wandering))[20][1]


def test_exact_is_running_max_of_repeats():
    steps = [Step(a, "", None, 1) for a in ["a", "b", "a", "c", "a", "b"]]
    assert [s for s, _ in method("exact")(steps)] == [1, 1, 2, 2, 3, 3]


def test_steps_counts_steps():
    steps = [Step("a", "", None, 1)] * 4
    assert [s for s, _ in method("steps")(steps)] == [1, 2, 3, 4]


def test_method_rejects_bad_names_and_lam():
    with pytest.raises(ValueError):
        method("nope")
    with pytest.raises(ValueError):
        method("steps", lam=0.9)


MIXED = [
    Step('bash {"command": "python reproduce.py"}', "Traceback\nValueError: bad 12", True, 5),
    Step('bash {"command": "sed -n 100,200p f.py"}', "line a\nline b", False, 5),
    Step('bash {"command": "python reproduce.py"}', "Traceback\nValueError: bad 13", True, 5),
    Step('bash {"command": "sed -n 200,300p f.py"}', "line c", False, 5),
    Step('bash {"command": "python reproduce.py"}', "Traceback\nValueError: bad 14", True, 5),
    Step('respond {"content": "done"}', "", None, 5),
]


@pytest.mark.parametrize("name", METHODS)
def test_never_looks_ahead(name):
    scorer = method(name) if name in BASELINES else method(name, lam=0.9)
    full = scorer(MIXED)
    assert len(full) == len(MIXED)
    for t in range(len(MIXED) + 1):
        assert scorer(MIXED[:t]) == full[:t]


# ---------- stuck signals (research R6). With lam = 0 the score is just this step's signal value. ----------


def values(name, steps, lam=0.0):
    return [round(s, 6) for s, _ in method(name, lam=lam)(steps)]


def act(cmd, obs="", error=None):
    return Step(json.dumps({"command": cmd}), obs, error, 1)


def test_fuzzy_repeat():
    assert values("fuzzy", [act("ls"), act("ls")]) == [0, 1]
    paging = values("fuzzy", [act("sed -n 100,200p f.py"), act("sed -n 200,300p f.py")])
    assert 0 < paging[1] < 1  # digits are kept, so paging through a file is not a repeat
    # only the previous 10 actions count: step 12 repeats step 1, which is out of reach
    steps = [act("alpha")] + [act(f"w{i}") for i in range(10)] + [act("alpha")]
    assert values("fuzzy", steps)[-1] < 1


def test_stale_nothing_new():
    assert values("stale", [act("a", "x\ny"), act("a", "x\ny")]) == [0, 1]
    assert values("stale", [act("a", "x\ny"), act("a", "x\nz")]) == [0, 0.5]
    assert values("stale", [act("a", "took 12 ms"), act("a", "took 13 ms")]) == [0, 1]  # digits masked
    assert values("stale", [act("a", "x"), act("b", "")]) == [0, 0]  # empty output is not evidence


def test_errors_repeat():
    assert values("errors", [act("a", "ValueError: bad 12", True), act("a", "ValueError: bad 13", True)]) == [0, 1]
    assert values("errors", [act("a", "Traceback\nKeyError: 'k'"), act("b", "Traceback\nKeyError: 'k'")]) == [0, 1]  # found by text
    assert values("errors", [act("a", "KeyError: 'k'", True), act("b", "KeyError: 'k'", False)]) == [0, 0]  # flag says fine
    assert values("errors", [act("a", "KeyError: 'k'", True), act("b", "IndexError", True)]) == [0, 0]


def test_combinations():
    steps = [act("ls", "x"), act("ls", "x", True), act("ls", "x", True)]
    f, s, e = values("fuzzy", steps), values("stale", steps), values("errors", steps)
    assert values("loop", steps) == [round(a * b, 6) for a, b in zip(f, s)]
    assert values("max", steps) == [max(t) for t in zip(f, s, e)]
    assert values("mean", steps) == [round(sum(t) / 3, 6) for t in zip(f, s, e)]


def test_running_score():
    steps = [act("a", "x"), act("b", "x"), act("c", "x")]  # stale: 0, 1, 1
    assert values("stale", steps, lam=0.5) == [0, 1, 1.5]
    assert values("stale", steps, lam=1.0) == [0, 1, 2]


def test_reasons_name_the_signals():
    steps = [act("python run.py", "boom")] + [act("python run.py", "boom")] * 4
    reason = method("loop", lam=0.9)(steps)[-1][1]
    assert "repeating in 4 of last 5 steps (same command as step 4)" in reason
    assert "nothing new in 4 of last 5 steps (0 of 1 output lines new)" in reason
    assert method("loop", lam=0.9)(steps[:1])[0][1] == ""


def test_signal_methods_need_lam():
    for name in ("fuzzy", "stale", "errors", "mean", "max", "loop"):
        with pytest.raises(ValueError):
            method(name)
