"""SC-007: nothing in the package opens a network connection."""
import socket
from pathlib import Path

import pytest

import loopbrake
from loopbrake import cli

FIX = Path(__file__).parent / "fixtures" / "calibration_runs.jsonl"


def test_whole_flow_without_network(tmp_path, monkeypatch, capsys):
    def no_network(*a, **k):
        raise AssertionError("loopbrake tried to use the network")

    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setenv("LOOPBRAKE_HOME", str(tmp_path / "lb"))
    loopbrake.calibrate(FIX, project="demo")
    with loopbrake.start(project="demo") as b:
        assert any(b.step(f"x {i}").stop for i in range(40))
    for args in (["status"], ["replay", str(FIX), "--project", "demo"], ["--version"]):
        assert cli.main(args) == 0
