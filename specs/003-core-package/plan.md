# Implementation Plan: Core Package (LoopBrake v1)

**Branch**: `003-core-package` | **Date**: 2026-10-01 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-core-package/spec.md`

## Words used in this plan

The same as the spec's table. In short:
- **stop line**: the most steps a run may take;
- **false stop**: stopping a run that would have succeeded;
- **watch-only**: records, never stops.

## Summary

v1 turns the measured result into an installable package. A `Brake` per run counts steps with the
exact scorer the experiments certified, and stops once the run passes a stop line set from the
user's own past successful runs (constitution Principle I's rule). Each stop is explained with the
Phase 1 signals, which never decide anything.

Around the brake:
- **Calibration** from a runs file or Claude Code history;
- **Local run records** in the roadmap's event format;
- **Status and feedback commands**, so false stops can be counted in real use;
- **A replay command** that shows live and offline decisions agree;
- **A thin adapter** for Claude's agent toolkit;
- **CI** on every push.
- **Release**: tagged versions go to PyPI through trusted publishing, so no token is stored
  (constitution 2.3.0, open core).

## Technical Context

| Item | Value |
|---|---|
| **Language/Version** | Python 3.11+, with CI on 3.11, 3.12 and 3.13 |
| **Primary Dependencies** | None at runtime. The optional extra `agent-sdk` adds Claude's agent toolkit for the adapter only. pytest for tests. |
| **Storage** | Local files under `$LOOPBRAKE_HOME` (default `~/.loopbrake`): `calibration/`, `runs/`, `exclude.txt` |
| **Testing** | pytest, using a temporary `LOOPBRAKE_HOME`, fixture runs, a socket-blocking no-network test, a timing test, and a data replay test that's skipped when no data is present |
| **Target Platform** | macOS and Linux, wherever the agent runs |
| **Project Type** | Library + command line tool |
| **Performance Goals** | Under 10 ms per decision (95th percentile) for runs up to 250 steps (SC-003) |
| **Constraints** | It never crashes or stops the host because of its own failures (FR-005). No network (Principle VI). It reuses the Phase 1 scorer and stop-line code unchanged (Principle II). The stop rule is the step budget only (constitution 2.2.0). |
| **Scale/Scope** | One brake per run. Typical runs are under 250 steps. Records grow by one short line per step. |

All open points are resolved in [research.md](research.md).

## Constitution Check

*GATE: must pass before Phase 0 research. Checked again after the Phase 1 design.*

| Principle | Before | After | Why it passes |
|---|---|---|---|
| I. Guarantee First | PASS | PASS | The stop line comes from `conformal.threshold` with one run per task. Watch-only applies when k > n. Every stop has a reason. Status counts mistaken stops against the α allowance. |
| II. One Scorer | PASS | PASS | The brake calls `method("steps")` and the evaluation's comparison (score > stop line). A replay test on all public runs checks the stop steps agree 100% (SC-001). |
| III. Stdlib-Only Core | PASS | PASS | No runtime dependencies. The toolkit adapter is an optional extra, imported only when used. A decision costs well under 10 ms. |
| IV. Evaluation Decides | PASS | PASS | The only stop rule is the one with committed results (`eval/results/`). The signals only explain. |
| V. Thin Adapters | PASS | PASS | `agent_sdk.py` turns toolkit events into `brake.step()` calls and decisions into the toolkit's stop reply. It has no stop logic of its own. |
| VI. Local by Default | PASS | PASS | Everything stays under `~/.loopbrake`, checked by a no-network test (SC-007). Records keep action excerpts of at most 200 characters, and calibration records keep no text. |
| Workflow: signal gate (2.2.0) | PASS | PASS | The step budget is the only stop rule. Other methods can't decide a stop. |
| Open core and releases (2.3.0) | PASS | PASS | Only the public library ships, which CI checks. Publishing uses trusted publishing on version tags, with no stored token. |
| Workflow: simplicity | PASS | PASS | Five small modules. No classes beyond `Brake` and `Decision`. No config files beyond the calibration record. |

## Project Structure

### Documentation (this feature)

```text
specs/003-core-package/
├── plan.md, research.md, data-model.md, quickstart.md
├── contracts/
│   ├── python-api.md      # start(), Brake, Decision, calibrate()
│   ├── records.md         # calibration record, run record events, exclude list, status
│   ├── cli.md             # loopbrake calibrate | status | feedback | replay | --version
│   ├── agent-sdk.md       # the adapter for Claude's agent toolkit
│   └── release.md         # publishing to PyPI
├── checklists/requirements.md
└── tasks.md               # created next by /speckit-tasks
```

### Source code (changes)

```text
pyproject.toml                    version 0.1.0 read from src/loopbrake/__init__.py; [project.scripts] loopbrake; optional extra agent-sdk
src/loopbrake/__init__.py         __version__, start, Brake, Decision, calibrate
src/loopbrake/brake.py            new: Brake, Decision, start(): stop rule, reasons, fail-safe, run records
src/loopbrake/calibration.py        new: calibrate() from a runs file or a Claude Code folder; read and write records
src/loopbrake/records.py          new: home folder, reading run records, status, feedback, exclude list
src/loopbrake/cli.py              new: the loopbrake command
src/loopbrake/agent_sdk.py        new: the toolkit hook adapter (optional extra)
.github/workflows/tests.yml       new: pytest on 3.11, 3.12 and 3.13 via astral-sh/setup-uv@v10, plus a build check of the wheel's contents
.github/workflows/publish.yml     new: on a v* tag, build (version check, smoke test, contents check), then publish with uv publish (research R11)
tests/test_brake.py, test_calibrate.py, test_records.py, test_cli.py, test_agent_sdk.py, test_no_network.py, test_replay_data.py
tests/fixtures/calibration_runs.jsonl   made-up runs for the README example and tests
README.md                         new "Use it" section with the five-line example
specs/roadmap.md                  event `kill` renamed `stop` (contracts/records.md)
```

Untouched: `signals.py`, `conformal.py`, `traces.py` (used as is), and everything under `eval/`.

**Structure decision**: these modules join the existing `src/loopbrake/` package. The experiment
code stays in `eval/`.

## Complexity Tracking

No constitution rule is broken. One deliberate shortcut:

| Shortcut | Limit | Fix if it becomes a problem |
|---|---|---|
| The brake rescores all steps so far on each `step()` (O(t)), so it uses the certified scorer literally | About 0.1 ms per step at 250 steps; fine | Keep a running count, with the replay test guarding that the two agree |
