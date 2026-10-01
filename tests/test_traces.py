import json
from collections import Counter
from pathlib import Path

from loopbrake.signals import Step
from loopbrake.traces import Run, claude_code_turns, read_runs, write_runs

RUN = Run(
    group="g", dataset="d", task="t1", run="t1-0", success=True, exit="Submitted", tokens_measured=True,
    steps=(Step('bash {"command": "ls"}', "a\nb", False, 10), Step('respond {"content": "done"}', "", None, 0)),
)


def as_dict(run):
    return {
        "group": run.group, "dataset": run.dataset, "task": run.task, "run": run.run,
        "success": run.success, "exit": run.exit, "tokens_measured": run.tokens_measured,
        "steps": [s._asdict() for s in run.steps],
    }


def test_round_trip(tmp_path):
    path = tmp_path / "g.jsonl"
    runs = [RUN, RUN._replace(run="t1-1", success=False, exit=None)]
    write_runs(path, runs)
    got, skipped = read_runs(path)
    assert got == runs
    assert not skipped


def test_bad_lines_are_skipped_and_counted(tmp_path):
    def with_step(**change):
        d = as_dict(RUN)
        d["steps"][0].update(change)
        return json.dumps(d)

    no_steps = as_dict(RUN) | {"steps": []}
    lines = [
        json.dumps(as_dict(RUN)),
        "{not json",
        json.dumps(no_steps),
        with_step(tokens=-1),
        with_step(tokens=1.5),
        with_step(action=""),
        with_step(error="yes"),
    ]
    path = tmp_path / "g.jsonl"
    path.write_text("\n".join(lines) + "\n")
    got, skipped = read_runs(path)
    assert got == [RUN]
    assert skipped == Counter({"bad json": 1, "no steps": 1, "bad tokens": 2, "empty action": 1, "bad error flag": 1})


# ---------- Claude Code transcripts (research R10) ----------

FIXTURE = Path(__file__).parent / "fixtures" / "claude_code_session.jsonl"


def test_claude_code_turns():
    runs, skipped = claude_code_turns(FIXTURE)
    assert [r.run for r in runs] == ["u1", "u2"]
    first, second = runs
    assert (first.success, first.exit) == (True, None)
    assert (second.success, second.exit) == (False, "interrupted")
    assert [s.action for s in first.steps] == [
        'Bash {"command": "pytest -q"}', 'Read {"file_path": "a.py"}', 'Read {"file_path": "b.py"}']
    assert [s.observation for s in first.steps] == ["1 failed", "print(1)", "x = 2"]
    assert [s.error for s in first.steps] == [True, False, False]
    # msg_1 counted once (1115); msg_2 goes to its first call (1127); text-only msg_3 goes to the step before it (1208)
    assert [s.tokens for s in first.steps] == [1115, 1127, 1208]
    assert [s.tokens for s in second.steps] == [1334]
    assert skipped == Counter({"sidechain": 1, "not a message": 2})
    assert all(r.dataset == "claude-code-local" and r.tokens_measured for r in runs)


def test_excluded_turn_is_not_a_success():
    runs, _ = claude_code_turns(FIXTURE, exclude={"u1"})
    assert runs[0].success is False


MIDTURN = Path(__file__).parent / "fixtures" / "claude_code" / "midturn.jsonl"


def test_mid_turn_records_stay_in_the_running_turn():
    """Research R1: compaction, typed prompts and notifications that arrive while Claude waits on a
    tool join the running turn; a notification after the turn ended starts its own turn."""
    runs, _ = claude_code_turns(MIDTURN)
    assert [r.run for r in runs] == ["p1", "n1", "p2", "p3", "p4", "p5"]
    assert [len(r.steps) for r in runs] == [3, 1, 1, 2, 1, 1]
    assert [r.success for r in runs] == [True, True, False, True, False, True]
    assert runs[4].exit == "stopped"  # a hook stopped it: the next prompt starts a new turn, and it isn't a success


def test_call_ids_per_turn():
    ids = {}
    claude_code_turns(MIDTURN, call_ids=ids)
    assert ids == {"p1": ("t1", "t2", "t3"), "n1": ("t4",), "p2": ("t5",), "p3": ("t6", "t7"), "p4": ("t8",), "p5": ("t9",)}
