"""SC-001: the live brake stops every public run at exactly the step the Phase 1 evaluation reports.

Needs the Phase 1 data (uv run python eval/fetch.py); skipped when it is absent, as in CI.
"""
import importlib.util
from pathlib import Path

import pytest

from loopbrake.brake import replay
from loopbrake.signals import method
from loopbrake.traces import read_runs

DATA = Path.home() / ".loopbrake" / "data" / "runs"
FILES = sorted(DATA.glob("*.jsonl")) if DATA.exists() else []
pytestmark = pytest.mark.skipif(len(FILES) < 6, reason="Phase 1 data not downloaded")

spec = importlib.util.spec_from_file_location("evalrun", Path(__file__).parents[1] / "eval" / "run.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


@pytest.mark.parametrize("path", FILES, ids=[p.stem for p in FILES])
def test_live_brake_matches_the_evaluation(path, tmp_path, monkeypatch):
    monkeypatch.setenv("LOOPBRAKE_HOME", str(tmp_path))
    runs, _ = read_runs(path)
    checked = 0
    for tau in (10, 20, 40, 80, 160):
        cal = {"stop_line": tau, "watch_only": False}
        for r in runs:
            k = ev.kill_index(ev.prepare(r, method("steps")), tau)
            assert replay(r, cal) == (None if k is None else k + 1), (r.run, tau)
            checked += 1
    assert checked == 5 * len(runs)
