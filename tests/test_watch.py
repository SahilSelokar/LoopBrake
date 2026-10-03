"""Watching your own agent (spec 007): wrapped tools, task blocks, a limit without a file, teams of agents."""
import asyncio
import json
import threading
import warnings

import pytest

import loopbrake
from loopbrake import calibration, cli, records
from loopbrake.watcher import Stopped


def events(h, project=None):
    starts = {e["run"] for e in records.read_events(h) if e.get("event") == "run_start" and project in (None, e.get("project"))}
    return [e for e in records.read_events(h) if e.get("run") in starts]


def counts(h, project):
    """Steps per task, in the order the tasks started."""
    order, n = [], {}
    for e in events(h, project):
        if e["event"] == "run_start":
            order.append(e["run"])
        n[e["run"]] = n.get(e["run"], 0) + (e["event"] == "step")
    return [n[r] for r in order]


def ends(h, project):
    return [e["status"] for e in events(h, project) if e["event"] == "run_end"]


def set_limit(h, name, line):
    calibration._save([line] * 19, {"kind": "test"}, name, 0.05, h)


def test_without_a_limit_it_only_watches(tmp_path):
    w = loopbrake.watch("solo", home=tmp_path)

    @w.tool
    def double(x):
        return 2 * x

    with w.task():
        assert [double(i) for i in range(30)] == [2 * i for i in range(30)]
    assert counts(tmp_path, "solo") == [30] and ends(tmp_path, "solo") == ["finished"]
    step = next(e for e in events(tmp_path) if e["event"] == "step")
    assert step["tool"] == "double" and step["action_excerpt"] == 'double {"x": 0}'


def test_the_call_past_the_limit_never_runs(tmp_path):
    set_limit(tmp_path, "solo", 3)
    w = loopbrake.watch("solo", home=tmp_path)
    ran, raised = [], []

    @w.tool
    def search(page):
        ran.append(page)
        return f"page {page}"

    with w.task() as task:
        for page in range(10):
            try:
                search(page)
            except Stopped as e:
                raised.append(str(e))
    assert ran == [0, 1, 2] and len(raised) == 7 and len(set(raised)) == 1
    assert task.stopped and task.reason == raised[0]
    reason = raised[0]
    assert "tool calls" in reason and "fewer than 1 in 20" in reason and "loopbrake feedback last --mistaken" in reason
    assert not any(word in reason for word in ("step", "α", "score"))
    assert ends(tmp_path, "solo") == ["stopped"]
    stop = next(e for e in events(tmp_path) if e["event"] == "stop")
    assert stop["step"] == 4


def test_the_stop_leaves_the_task_block_unless_caught(tmp_path):
    set_limit(tmp_path, "solo", 1)
    w = loopbrake.watch("solo", home=tmp_path)
    tool = w.tool(lambda: "ok")
    with pytest.raises(Stopped):
        with w.task():
            tool(), tool()
    assert ends(tmp_path, "solo") == ["stopped"]


def test_a_tool_error_passes_through_and_counts_as_failed(tmp_path):
    w = loopbrake.watch("solo", home=tmp_path)

    @w.tool
    def broken():
        raise KeyError("nope")

    with pytest.raises(KeyError):
        with w.task():
            broken()
    step = next(e for e in events(tmp_path) if e["event"] == "step")
    assert step["error"] is True and ends(tmp_path, "solo") == ["interrupted"]


def test_async_tools_and_tasks(tmp_path):
    set_limit(tmp_path, "solo", 3)
    w = loopbrake.watch("solo", home=tmp_path)
    ran = []

    @w.tool
    async def fetch(i):
        await asyncio.sleep(0)
        ran.append(i)
        return i

    async def job():
        async with w.task():
            for i in range(10):
                try:
                    await fetch(i)
                except Stopped:
                    pass

    asyncio.run(job())
    assert ran == [0, 1, 2] and ends(tmp_path, "solo") == ["stopped"]


def test_outside_a_task_a_tool_runs_uncounted_and_says_so_once(tmp_path):
    w = loopbrake.watch("solo", home=tmp_path)
    tool = w.tool(lambda: "ok")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert tool() == "ok" and tool() == "ok"
    assert len([c for c in caught if "outside a task" in str(c.message)]) == 1
    assert events(tmp_path) == []


def test_bad_names_are_refused_up_front(tmp_path):
    with pytest.raises(ValueError):
        loopbrake.watch("my agent", home=tmp_path)


def test_option_b_a_workers_calls_never_count_for_its_manager(tmp_path):
    manager, worker = loopbrake.watch("desk", home=tmp_path), loopbrake.watch("researcher", home=tmp_path)

    @worker.tool
    def search(q):
        return q

    @manager.tool
    def ask_researcher(q):
        with worker.task():
            return [search(q) for _ in range(3)]

    with manager.task():
        ask_researcher("a"), ask_researcher("b")
    assert counts(tmp_path, "desk") == [2] and counts(tmp_path, "researcher") == [3, 3]


def test_option_a_one_watcher_counts_every_agent(tmp_path):
    team = loopbrake.watch("support-bot", home=tmp_path)
    search, write = team.tool(lambda q: q, name="search"), team.tool(lambda t: t, name="write")

    def researcher():
        return [search(i) for i in range(3)]

    def writer():
        return [write(i) for i in range(3)]

    with team.task():
        researcher(), writer()  # the job passes from one agent to the other
    assert counts(tmp_path, "support-bot") == [6]


def test_the_same_tool_wrapped_for_two_agents_counts_for_the_caller(tmp_path):
    a, b = loopbrake.watch("a", home=tmp_path), loopbrake.watch("b", home=tmp_path)

    def search(q):
        return q

    search_a, search_b = a.tool(search), b.tool(search)
    with a.task(), b.task():
        search_a(1), search_a(2), search_b(3)
    assert counts(tmp_path, "a") == [2] and counts(tmp_path, "b") == [1]


def test_tasks_at_the_same_time_keep_separate_counts(tmp_path):
    w = loopbrake.watch("crowd", home=tmp_path)

    @w.tool
    async def step(i):
        await asyncio.sleep(0.001 * (i % 3))
        return i

    async def job(k):
        async with w.task():
            for i in range(k):
                await step(i)

    async def main():
        await asyncio.gather(*(job(k) for k in range(1, 11)))

    asyncio.run(main())
    assert sorted(counts(tmp_path, "crowd")) == list(range(1, 11))

    def thread_job(k):
        with w.task():
            for i in range(k):
                asyncio.run(step(i))

    threads = [threading.Thread(target=thread_job, args=(k,)) for k in range(1, 6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(counts(tmp_path, "crowd")) == sorted(list(range(1, 11)) + list(range(1, 6)))


def test_parallel_calls_in_one_task_never_go_past_the_limit(tmp_path):
    set_limit(tmp_path, "solo", 3)
    w = loopbrake.watch("solo", home=tmp_path)
    ran = []

    @w.tool
    async def fetch(i):
        await asyncio.sleep(0.01)
        ran.append(i)

    async def job():
        async with w.task() as task:
            results = await asyncio.gather(*(fetch(i) for i in range(10)), return_exceptions=True)
        return task, results

    task, results = asyncio.run(job())
    assert len(ran) == 3 and sum(isinstance(r, Stopped) for r in results) == 7
    assert task.stopped and ends(tmp_path, "solo") == ["stopped"]
    assert next(e for e in events(tmp_path) if e["event"] == "stop")["step"] == 4


def test_a_stop_in_one_task_never_stops_another(tmp_path):
    set_limit(tmp_path, "researcher", 1)
    manager, worker = loopbrake.watch("desk", home=tmp_path), loopbrake.watch("researcher", home=tmp_path)
    search = worker.tool(lambda q: q, name="search")

    @manager.tool
    def ask_researcher(q):
        with worker.task():
            return [search(q), search(q)]

    reply = manager.tool(lambda text: text, name="reply")
    with manager.task():
        try:
            ask_researcher("a")
        except Stopped:
            pass  # the manager's own code decides what to do
        assert reply("sorry") == "sorry"
    assert ends(tmp_path, "researcher") == ["stopped"] and ends(tmp_path, "desk") == ["finished"]


def test_fails_safe(tmp_path, monkeypatch):
    calibration.path("solo", tmp_path).parent.mkdir(parents=True)
    calibration.path("solo", tmp_path).write_text('{"stop_line": 1, broken')  # a damaged limit: watching only
    w = loopbrake.watch("solo", home=tmp_path)
    tool = w.tool(lambda: "ok")
    with w.task():
        assert [tool() for _ in range(5)] == ["ok"] * 5

    from loopbrake import watcher as watch_mod
    monkeypatch.setattr(watch_mod, "start", lambda *a, **k: 1 / 0)  # LoopBrake itself failing
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        with w.task():
            assert [tool() for _ in range(5)] == ["ok"] * 5


def test_set_the_limit_from_watched_tasks_without_a_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LOOPBRAKE_HOME", str(tmp_path))
    w = loopbrake.watch("solo", home=tmp_path)
    tool = w.tool(lambda: "ok")
    lengths = [3, 5, 4, 6, 2, 7, 5, 4, 3, 8, 5, 6, 4, 3, 5, 9, 4, 6, 5, 4, 3, 5, 6, 4, 5]
    for n in lengths:
        with w.task():
            for _ in range(n):
                tool()
    with pytest.raises(RuntimeError):  # ended by an error: interrupted, not used
        with w.task():
            tool()
            raise RuntimeError
    assert cli.main(["calibrate", "--project", "solo"]) == 0
    assert "will stop a task that goes past" in capsys.readouterr().out
    rec = calibration.load("solo", tmp_path)
    runs = tmp_path / "runs.jsonl"
    step = {"action": "x", "observation": "", "error": False, "tokens": 0}
    runs.write_text("".join(json.dumps({"group": "g", "dataset": "d", "task": f"t{i}", "run": f"r{i}", "success": True,
                                        "exit": "finished", "tokens_measured": False, "steps": [step] * n}) + "\n"
                            for i, n in enumerate(lengths)))
    other = calibration.calibrate(runs, project="file-route", home=tmp_path)
    assert rec["n"] == len(lengths) and rec["stop_line"] == other["stop_line"]


def test_set_the_limit_honors_mistakes_and_leave_outs(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LOOPBRAKE_HOME", str(tmp_path))
    set_limit(tmp_path, "solo", 2)
    w = loopbrake.watch("solo", home=tmp_path)
    tool = w.tool(lambda: "ok")
    for _ in range(20):
        with w.task():
            tool()
    with pytest.raises(Stopped):
        with w.task():
            tool(), tool(), tool()
    assert cli.main(["feedback", "last", "--mistaken"]) == 0
    rec = calibration.calibrate(None, project="solo", home=tmp_path)
    assert rec["n"] == 21 and None in rec["lengths"]  # 20 good tasks, and the mistaken stop as longer than any
    assert cli.main(["calibrate"]) == 2  # no file and no name: says what to give
    assert "--project" in capsys.readouterr().err


def test_a_wrapped_call_adds_little_time(tmp_path):
    import time
    set_limit(tmp_path, "solo", 500)
    w = loopbrake.watch("solo", home=tmp_path)
    tool = w.tool(lambda i: i, name="tool")
    took = []
    with w.task():
        for i in range(200):
            t0 = time.perf_counter()
            tool(i)
            took.append(time.perf_counter() - t0)
    assert sorted(took)[int(0.95 * len(took))] < 0.010  # spec SC-005


def test_the_readme_examples_run_as_written(tmp_path, monkeypatch):
    import re
    from pathlib import Path
    monkeypatch.setenv("LOOPBRAKE_HOME", str(tmp_path))
    text = (Path(__file__).parents[1] / "README.md").read_text()
    section = text[text.index("## Use it\n"):text.index("## Use it with Claude Code")]
    blocks = re.findall(r"```python\n(.*?)```", section, re.S)
    assert len(blocks) == 3  # spec SC-007
    for code in blocks:
        exec(compile(code, "README.md", "exec"), {})
    assert {"my-agent", "support-bot", "desk", "researcher"} <= {e.get("project") for e in records.read_events(tmp_path)}
