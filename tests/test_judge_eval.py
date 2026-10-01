import importlib.util
import json
from pathlib import Path

from loopbrake.signals import Step
from loopbrake.traces import Run, write_runs

spec = importlib.util.spec_from_file_location("judge_eval", Path(__file__).parents[1] / "eval" / "judge_eval.py")
je = importlib.util.module_from_spec(spec)
spec.loader.exec_module(je)


def run(name, n, success, task=None):
    return Run("g", "d", task or name, name, success, None, True, tuple(Step(f"a{i}", "", None, 100) for i in range(n)))


def count(n):
    return [(i + 1, "") for i in range(n)]  # score at step t is t


def test_judge_cost_up_to_the_stop_step():
    r = run("r", 5, False)
    p = je.prepare_net(r, count(5), judge_tokens=[10, 10, 10, 10, 10], asked=[True] * 5)
    assert p.judge_cum == [10, 20, 30, 40, 50]
    # stop line 2 -> stopped after step 3: saves 200 agent tokens, the judge spent 30
    split = je.measure_net([p], [], [0], alpha=0.05, tau=2)
    assert split.net_saved == (200 - 30) / 500 and split.judge_share == 30 / 500
    # never stopped: the judge spent tokens on every step, nothing saved
    never = je.measure_net([p], [], [0], alpha=0.05, tau=99)
    assert never.net_saved == -50 / 500 and never.asked_share == 1.0


def test_steps_not_asked_cost_nothing():
    r = run("r", 4, False)
    p = je.prepare_net(r, count(4), judge_tokens=[0, 10, 0, 10], asked=[False, True, False, True])
    assert p.judge_cum == [0, 10, 10, 20] and p.asked_cum == [0, 1, 1, 2]
    split = je.measure_net([p], [], [0], alpha=0.05, tau=99)
    assert split.judge_share == 20 / 400 and split.asked_share == 0.5


def test_missing_judgments_are_no_opinion_and_counted():
    r = run("r", 3, True)
    judgments = {("g", "r", 1): {"progress": 0.9, "kind": "found_new", "kind_p": 0.7, "tokens": 300, "status": "ok"}}
    progress, kinds, tokens, missing = je.judgment_lists("g", r, judgments)
    assert progress == [0.9, None, None] and tokens == [300, 0, 0] and missing == 2
    assert kinds[0] == ("found_new", 0.7) and kinds[1] is None


def test_final_refusals(tmp_path, monkeypatch):
    monkeypatch.setattr(je, "CANDIDATE", tmp_path / "judge_candidate.json")
    assert je.main(["--final", "--data", str(tmp_path)]) == 2  # no committed choice
    (tmp_path / "judge_candidate.json").write_text(json.dumps(
        {"setup": "jev-1.13.0/v1/x", "method": "judge", "lam": 0.9, "ask_level": None, "chosen_on": "swe-devstral", "date": "2026-10-01"}))
    monkeypatch.setattr(je, "candidate_committed", lambda: True)
    monkeypatch.setattr(je, "JUDGMENTS", tmp_path / "judgments")
    (tmp_path / "runs").mkdir()
    write_runs(tmp_path / "runs" / "swe-gpt5mini.jsonl", [run("x", 2, True)._replace(group="swe-gpt5mini")])
    assert je.main(["--final", "--data", str(tmp_path)]) == 1  # a holdout step has no judgment


# ---------- ask only when needed (US3, research R8) ----------

from loopbrake.signals import method


def looping(name, n):
    return Run("g", "d", name, name, False, None, True, tuple(Step('bash {"command": "ls"}', "same", None, 100) for _ in range(n)))


def test_ask_levels_are_percentiles_of_phase1_scores():
    runs = [looping("a", 6), run("b", 6, True)]
    scores = sorted(s for r in runs for s, _ in method("max", lam=0.9)(r.steps))
    levels = je.ask_levels(runs)
    assert len(levels) == 3 and levels == sorted(levels)
    assert levels[0] >= scores[len(scores) // 2 - 1] and levels[2] <= scores[-1]


def test_steps_not_asked_get_no_opinion_and_no_cost():
    r = looping("a", 4)
    flags = je.asked_flags(r, level=1.5)
    assert flags == [s >= 1.5 for s, _ in method("max", lam=0.9)(r.steps)]
    judgments = {("g", "a", i + 1): {"progress": 0.1, "kind": "repeated", "kind_p": 0.9, "tokens": 300, "status": "ok"} for i in range(4)}
    progress, _, tokens, missing = je.judgment_lists("g", r, judgments, asked=flags)
    assert all((p is None) == (not f) for p, f in zip(progress, flags))
    assert all((t == 0) == (not f) for t, f in zip(tokens, flags)) and missing == 0
