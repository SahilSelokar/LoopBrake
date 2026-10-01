import json

import pytest

from loopbrake import claude_code, records


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOPBRAKE_HOME", str(tmp_path / "lb"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    return records.home()


# ---- project identity (research R6). Made-up paths only: real folder names never go in the repo ----

def test_history_folder(home, tmp_path):
    assert claude_code.history_folder("/home/me/my app?") == tmp_path / "claude" / "projects" / "-home-me-my-app-"


def test_project_name():
    assert claude_code.project_name("-home-me-my-app-") == "cc-home-me-my-app--c57a41"
    long_a, long_b = "-a" + "-x" * 40 + "-same-tail-of-forty-characters-here", "-b" + "-x" * 40 + "-same-tail-of-forty-characters-here"
    names = {claude_code.project_name(long_a), claude_code.project_name(long_b)}
    assert len(names) == 2
    assert all(records.valid_project(n) and len(n) <= 64 for n in names)
