# Quickstart: Validating the Core Package

## Prerequisites

- `uv` and Python 3.11 or newer.
- For step 4, the Phase 1 data in `~/.loopbrake/data` (`eval/fetch.py`).

## 1. Tests

```bash
uv run pytest
```

**Expect**: everything passes, including:

| Test | Checks |
|---|---|
| Stop rule | It stops at step `stop_line + 1`, stays stopped, and watch-only never stops |
| Reasons | A stop names the step, the stop line and n, plus the signals' explanation |
| Fail-safe (SC-005) | An unwritable records folder, a damaged calibration file, or an internal error: the host loop always finishes |
| Calibration (SC-006) | 19 successful tasks at α 5% give the max run length as the stop line; 18 give watch-only; one run per task; excluded ids skipped; no source text in the record |
| Status (SC-008) | 20 runs watched, 3 stopped, 1 marked a mistake: shows 1 mistaken against an allowance of 1 |
| No network (SC-007) | With socket creation blocked, start, step, calibrate, status and replay all work |
| Speed (SC-003) | 250-step runs: 95th-percentile time per decision under 10 ms |

## 2. Install from the repository, as a stranger would (SC-004)

```bash
time uvx --from git+https://github.com/SahilSelokar/LoopBrake loopbrake --version
```

**Expect**: `loopbrake 0.1.0`, in under 1 minute, with no other packages pulled in.

## 3. The five-line example (SC-002)

Run the README's "Use it" example exactly as written, against a made-up loop that repeats one
action. **Expect**: watch-only at first. After
`loopbrake calibrate tests/fixtures/calibration_runs.jsonl --project demo`, it stops at
`stop_line + 1` and prints the reason.

## 4. Same decision live and offline (SC-001)

```bash
uv run pytest tests/test_replay_data.py      # skipped when ~/.loopbrake/data is absent
uv run loopbrake replay ~/.loopbrake/data/runs/swe-gpt5mini.jsonl --stop-line 40
```

**Expect**: the data test passes. For every run in the 6 public groups, at stop lines 10, 20, 40, 80
and 160, the brake's stop step equals the Phase 1 evaluation's. The replay prints a summary.

## 5. Claude's agent toolkit (US3)

```bash
uv run --with claude-agent-sdk python -m pytest tests/test_agent_sdk.py
```

**Expect**: the hook's tests pass. Optionally, with Claude Code installed and an API key, run the
example in [contracts/agent-sdk.md](contracts/agent-sdk.md): a toolkit agent with a stop line of 5
is stopped after its 6th tool call.

## 6. Your own history

```bash
uv run loopbrake calibrate ~/.claude/projects/<one-project-folder> --project my-claude-code
uv run loopbrake status --project my-claude-code
```

**Expect**: a stop line, or watch-only for small projects. The record file contains only counts and
a fingerprint.

## 7. Release to PyPI (US4, SC-009)

One-time setup first ([contracts/release.md](contracts/release.md)). Then:

```bash
git tag v0.1.0 && git push origin v0.1.0
# about 5–10 minutes later, in a fresh folder:
uvx --from loopbrake==0.1.0 loopbrake --version
```

**Expect**:
- `loopbrake 0.1.0`;
- the PyPI page shows the README and the MIT license;
- a test tag that doesn't match the version (for example on a fork) fails at the version check.

## 8. CI

Push a commit. **Expect**: the "tests" workflow runs on Python 3.11, 3.12 and 3.13 and passes.
