import importlib.util
import json
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"
spec = importlib.util.spec_from_file_location("fetch", Path(__file__).parents[1] / "eval" / "fetch.py")
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)


def load(name):
    return json.loads((FIX / name).read_text())


def test_mini_v2():
    run, missing = fetch.parse_mini_v2(load("mini_v2.traj.json"), True, "swe-x")
    assert missing == 0
    assert [s.action for s in run.steps] == [
        'bash {"command": "ls"}',
        'bash {"command": "cat x"}',
        'bash {"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"}',
    ]
    assert [s.observation for s in run.steps] == ["a\nb", "cat: x: No such file or directory", ""]
    assert [s.error for s in run.steps] == [False, True, None]
    assert [s.tokens for s in run.steps] == [110, 170, 205]
    assert (run.task, run.run, run.success, run.exit, run.tokens_measured) == ("demo__demo-1", "demo__demo-1", True, "Submitted", True)


def test_mini_v1_charges_calls_without_an_action_to_a_step():
    run, missing = fetch.parse_mini_v1(load("mini_v1.traj.json"), False, "swe-y")
    assert missing == 0
    assert [s.action for s in run.steps] == [
        'bash {"command": "ls"}',
        'bash {"command": "cat x"}',
        'bash {"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"}',
    ]
    assert [s.observation for s in run.steps] == ["a", "cat: x: No such file or directory", ""]
    assert [s.error for s in run.steps] == [False, True, None]
    # first format error (55) goes to step 1, second (135) also to step 1: 55 + 110 + 135
    assert [s.tokens for s in run.steps] == [300, 152, 165]
    assert sum(s.tokens for s in run.steps) == 55 + 110 + 135 + 152 + 165


def test_tau_estimates_tokens_from_text_length():
    entry = load("tau_run.json")[0]
    run = fetch.parse_tau(entry, "tau-x")
    msgs = entry["traj"]
    assert [s.action.split(" ")[0] for s in run.steps] == ["respond", "find_user_id_by_name_zip"]
    assert run.steps[0].observation == msgs[3]["content"]  # the user's reply
    assert run.steps[1].observation == msgs[5]["content"]  # the tool's output
    assert [s.error for s in run.steps] == [None, False]
    chars = [fetch.char_count(m) for m in msgs]
    assert run.steps[0].tokens == sum(chars[:3]) // 4
    assert run.steps[1].tokens == sum(chars[:5]) // 4
    assert (run.task, run.run, run.success, run.tokens_measured) == (str(entry["task_id"]), f"{entry['task_id']}-0", True, False)
