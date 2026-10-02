"""The Claude Code plugin's static files and its launcher (contracts/plugin.md)."""
import json
import os
import re
import stat
import subprocess
import tomllib
from pathlib import Path

import pytest

import loopbrake

ROOT = Path(__file__).parents[1]
PLUGIN = ROOT / "plugin"
LAUNCHER = PLUGIN / "bin" / "loopbrake"


def test_manifests_agree():
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    assert market["name"] == "loopbrake" and market["owner"]["name"]
    [entry] = market["plugins"]
    assert entry["name"] == manifest["name"] == "loopbrake" and entry["source"] == "./plugin"
    assert manifest["author"]["name"] and manifest["description"]
    pin = re.search(r"^V=(\S+)$", LAUNCHER.read_text(), re.M).group(1)
    assert manifest["version"] == pin == loopbrake.__version__
    assert set(re.findall(r"loopbrake==(\S+?)`", (ROOT / "README.md").read_text())) == {pin}  # the README's pip fallback


def test_hooks():
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())["hooks"]
    assert set(hooks) >= {"UserPromptSubmit", "PostToolUse", "PostToolUseFailure", "Stop"}
    for event, groups in hooks.items():
        for group in groups:
            assert group.get("matcher", "*") == "*"
            for h in group["hooks"]:
                assert h["type"] == "command" and h["timeout"] == 30
                assert h["command"].startswith('"${CLAUDE_PLUGIN_ROOT}/bin/loopbrake" hook ')


def test_launcher_is_executable_and_not_packaged():
    assert LAUNCHER.stat().st_mode & stat.S_IXUSR
    include = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    assert not any(p.startswith(("plugin", ".claude-plugin")) for p in include)


# ---- launcher behavior, with a fake uvx that logs each call ----

FAKE_UVX = """#!/bin/sh
echo "$*" >> "$FAKE_LOG"
case "$*" in
  *--version*) exit ${FAKE_VERSION:-0} ;;
  *--offline*) exit ${FAKE_OFFLINE:-0} ;;
  *) exit ${FAKE_ONLINE:-0} ;;
esac
"""


@pytest.fixture
def launch(tmp_path):
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "uvx").write_text(FAKE_UVX)
    (fake / "uvx").chmod(0o755)
    logfile = tmp_path / "calls.log"

    def run(*args, **env):
        logfile.unlink(missing_ok=True)
        base = {k: v for k, v in os.environ.items() if k not in ("LOOPBRAKE_CMD", "LOOPBRAKE_LAUNCHER")}
        p = subprocess.run([str(LAUNCHER), *args], input="{}", capture_output=True, text=True, timeout=30,
                           env=base | {"PATH": f"{fake}:/usr/bin:/bin", "FAKE_LOG": str(logfile)} | env)
        calls = logfile.read_text().splitlines() if logfile.exists() else []
        return p.returncode, p.stdout, p.stderr, calls

    return run


def test_a_hook_always_exits_0_and_never_waits_on_the_network(launch, tmp_path):
    import time
    for code in ("1", "2"):
        rc, out, _, calls = launch("hook", "prompt", FAKE_OFFLINE=code, FAKE_ONLINE=code)
        assert (rc, out) == (0, "")
        assert "--offline" in calls[0]  # the background download may already have logged too
        log = tmp_path / "calls.log"
        for _ in range(50):  # the download runs in the background, after the hook has returned
            lines = log.read_text().splitlines()
            if len(lines) >= 2:
                break
            time.sleep(0.05)
        assert len(lines) == 2 and "--offline" not in lines[1] and lines[1].endswith("loopbrake --version")
        assert "--refresh-package loopbrake" in lines[1]  # a just-released version is found (v0.3.0's release)


def test_a_hook_uses_the_cache_without_retrying(launch):
    rc, _, _, calls = launch("hook", "tool")
    assert rc == 0 and len(calls) == 1 and "--offline" in calls[0]


def test_a_command_runs_once_and_keeps_its_exit_code(launch):
    rc, _, _, calls = launch("status", FAKE_VERSION="0", FAKE_OFFLINE="2")
    assert rc == 2 and len(calls) == 2 and calls[0].endswith("--version") and calls[1].endswith("loopbrake status")
    rc, _, _, calls = launch("status", FAKE_VERSION="1", FAKE_ONLINE="1")
    assert rc == 1 and len(calls) == 2 and "--offline" not in calls[1]


def test_loopbrake_cmd_pointing_at_the_launcher_does_not_loop(launch):
    quoted = f"'{LAUNCHER}'"  # the repo path may hold spaces, so it is quoted inside the variable
    rc, out, _, _ = launch("hook", "stop", LOOPBRAKE_CMD=quoted)
    assert (rc, out) == (0, "")
    rc, _, err, _ = launch("status", LOOPBRAKE_CMD=quoted)
    assert rc == 2 and "points back at the plugin launcher" in err


def test_a_broken_loopbrake_cmd_never_fails_a_hook(launch):
    rc, out, _, _ = launch("hook", "prompt", LOOPBRAKE_CMD="/no/such/command")
    assert (rc, out) == (0, "")


def test_loopbrake_cmd_with_arguments_and_a_quoted_path(launch, tmp_path):
    target = tmp_path / "dir with space" / "lb"
    target.parent.mkdir()
    target.write_text('#!/bin/sh\necho "got: $*"\n')
    target.chmod(0o755)
    rc, out, _, _ = launch("status", "--project", "x", LOOPBRAKE_CMD=f"'{target}' --extra")
    assert (rc, out) == (0, "got: --extra status --project x\n")


# ---- the Codex plugin (specs/006-codex-cli-plugin/contracts/plugin.md) ----

CODEX = ROOT / "codex-plugin"


def test_codex_plugin_files():
    market = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text())
    [entry] = market["plugins"]
    assert market["name"] == entry["name"] == "loopbrake"
    assert entry["source"] == {"source": "local", "path": "./codex-plugin"}
    manifest = json.loads((CODEX / ".codex-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "loopbrake" and manifest["description"] and manifest["author"]["name"]
    pin = re.search(r"^V=(\S+)$", (CODEX / "bin" / "loopbrake").read_text(), re.M).group(1)
    assert manifest["version"] == pin == loopbrake.__version__


def test_codex_hooks_run_the_launcher_and_never_change_between_versions():
    text = (CODEX / "hooks" / "hooks.json").read_text()
    hooks = json.loads(text)["hooks"]
    assert set(hooks) == {"UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "Interrupt", "SubagentStart", "SubagentStop"}
    for event, groups in hooks.items():
        [group] = groups
        assert group.get("matcher", ".*") == ".*"
        [h] = group["hooks"]
        assert h["type"] == "command" and h["timeout"] == (1 if event == "Interrupt" else 30)
        assert re.fullmatch(r'"\$PLUGIN_ROOT/bin/loopbrake" hook codex-[a-z-]+', h["command"])
    # Codex runs a hook only after the user trusts its exact definition, so no version may appear here
    assert loopbrake.__version__ not in text and not re.search(r"\d+\.\d+\.\d+", text)


def test_codex_launcher_is_the_same_and_not_packaged():
    assert (CODEX / "bin" / "loopbrake").read_bytes() == LAUNCHER.read_bytes()
    assert (CODEX / "bin" / "loopbrake").stat().st_mode & stat.S_IXUSR
    include = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    assert not any(p.startswith(("codex-plugin", ".agents")) for p in include)
