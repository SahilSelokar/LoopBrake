# Research: Core Package (LoopBrake v1)

**Feature**: [spec.md](spec.md) | **Date**: 2026-10-01

## R1. The stop rule, exactly as certified

**Decision**:
- **Scoring**: on each `step()`, the brake appends a `Step` and computes
  `method("steps")(steps)[-1][0]` (= t).
- **Stopping**: it stops when that score is greater than the stop line, which is the evaluation's
  `bisect_right(peak, tau)` rule. A run therefore stops at step `stop_line + 1`.
- **Stop line**: `conformal.threshold(lengths, alpha)`, where `lengths` holds the step counts of the
  successful calibration runs.

**Rationale**: Principle II requires the same function live and offline. Calling the certified
scorer, even though for `steps` it just counts, keeps that literally true, and the replay test
(SC-001) proves it.

**Alternatives considered**: a bare counter `t > stop_line`. Identical in behaviour, but it would be
a second implementation to keep in sync. Rejected; it's noted as the upgrade path in the plan's
Complexity Tracking.

## R2. Reasons

**Decision**: a stop reason is:

`stopped at step {t}: past the stop line of {stop_line} steps set from your {n} past successful runs (α {alpha:.0%})`

followed by `; last 5 steps: {signals reason}` when the Phase 1 `max` (λ 0.9) scorer has a non-empty
reason at that step. That scorer is computed only when stopping.

**Rationale**:
- the spec's FR-003 wording;
- the constitution 2.2.0 rule that signals explain but never decide;
- computing them only at stop time keeps each step cheap.

## R3. Calibration sources

**Decision**:

| Source | How it's read | Task id | Success |
|---|---|---|---|
| Runs file | `traces.read_runs` | `run.task` | `run.success`. At most one run per task: the first successful one by run id. |
| Claude Code folder | `traces.claude_code_turns` on every `*.jsonl` in it | Each turn is its own task (turn id) | As in Phase 1: ended normally, not interrupted, not excluded |

- Ids listed in `exclude.txt` are skipped.
- **Source fingerprint**:
  - a runs file: the sha256 of the file;
  - a Claude Code folder: the sha256 of the sorted list of (file name, size) pairs. It doesn't
    hash the content, so no turn text is read twice.

**Rationale**:
- One run per task is the fix learned in Phase 1 (CORRECTIONS.md).
- Taking the *first* run by id is deterministic, so calibrating again on the same file gives the
  same line.

## R4. Where things live

**Decision**: `$LOOPBRAKE_HOME`, default `~/.loopbrake`, with `calibration/<project>.json`,
`runs/<session>.jsonl` and `exclude.txt`. The project name must match `[A-Za-z0-9._-]{1,64}`, so it
can't escape the folder.

**Rationale**:
- it's the folder the constitution names;
- one environment variable lets tests and CI use a temporary home.

## R5. Never hurting the host (spec FR-005)

**Decision**:
- **Catching errors**: every public `Brake` method catches `Exception` inside LoopBrake. It warns
  once (with `warnings.warn`, category `RuntimeWarning`), switches to watch-only, and returns a
  continue decision.
- **Bad records**: a missing or damaged calibration record means watch-only with one warning.
- **Failed writes**: they turn recording off for that brake only.

**Rationale**: a stop controller that can crash the agent is worse than none. Watch-only is the safe
fallback, because it can never cause a false stop.

## R6. Writing records safely with parallel runs

**Decision**: each event is one line written by one `write()` call on a file opened in append mode
(`"a"`), with lines kept short (action excerpts of at most 200 characters). Each session has its
own file.

**Rationale**: on local POSIX filesystems, appends of short lines from a single `write()` don't
interleave in practice. Separate session files avoid most sharing anyway.

**Alternatives considered**: file locks. That's more code and isn't portable across platforms.
Rejected for v1.

## R7. Packaging and install

**Decision**:
- `version = "0.1.0"`, read by hatch from `src/loopbrake/__init__.py` (one source of truth).
- `[project.scripts] loopbrake = "loopbrake.cli:main"`.
- `[project.optional-dependencies] agent-sdk = ["claude-agent-sdk"]`.
- **Install without PyPI**: `uvx --from git+https://github.com/SahilSelokar/LoopBrake loopbrake`,
  or `pip install git+…`.

**Rationale**: SC-004 (fresh install to first decision in under 1 minute) works without
publishing. Publishing stays the builder's separate decision.

## R8. Claude's agent toolkit adapter (spec FR-014, US3)

**Facts** (Claude Agent SDK docs, hooks page, checked 2026-10-01):
- **Package**: `claude-agent-sdk`, imported as `claude_agent_sdk`. It needs Python 3.10+ and a
  bundled or installed Claude Code.
- **Hook callback**: `async def cb(input_data, tool_use_id, context) -> dict`, registered with
  `ClaudeAgentOptions(hooks={"PostToolUse": [HookMatcher(hooks=[cb])]})`.
- **PostToolUse input**: `hook_event_name`, `session_id`, `cwd`, `tool_name`, `tool_input`,
  `tool_response`, and optionally `agent_id` and `agent_type`.
- **Stopping the whole run**: return `{"continue_": False}`. Python uses `continue_` because
  `continue` is a keyword.
- **Not documented in the SDK docs**: whether `stopReason` is passed through, and what the caller
  sees. The Claude Code CLI hooks docs do define `stopReason`.
- **Python events** include `PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop` and
  `SubagentStop`. `SessionStart` and `SessionEnd` are TypeScript-only.

**Decision**: `loopbrake.agent_sdk.hooks(project="default")` returns the `hooks` dict:
- **UserPromptSubmit** starts a new run for that `session_id`. One prompt is one run, matching how
  Claude Code turns are calibrated.
- **PostToolUse** calls `brake.step(action, result, tool=...)`:
  - `action` is `"<tool_name> <json(tool_input, sorted keys)>"`, the same text Phase 1 builds from
    Claude Code transcripts;
  - `result` is `tool_response` as text;
  - on a stop it returns `{"continue_": False, "stopReason": reason}`.
- **Stop** ends the run as `finished`, unless it was already stopped.

**Checked 2026-10-01** (claude-agent-sdk 0.2.163, `src/claude_agent_sdk/types.py`): `SyncHookJSONOutput` has
`continue_: NotRequired[bool]` and `stopReason: NotRequired[str]`, documented as "Message shown when continue is
False". So a stop returns `{"continue_": False, "stopReason": reason}`. Callbacks are
`async (input, tool_use_id, context)`, and `HookMatcher(matcher=None, hooks=[...], timeout=None)` registers them.

Originally planned: at implementation, check the installed package's hook-output type. If `stopReason` isn't a known
field, also return the reason through `systemMessage`, or drop it, whichever the type allows, and
record the finding in this file.

**Testing**: the callbacks take and return plain dicts, so the tests call them directly with fake
inputs and need neither the SDK nor an API key. A real-agent run is optional and manual
(quickstart step 5).

## R9. CI

**Decision**: `.github/workflows/tests.yml` runs on `push` and `pull_request`, on `ubuntu-latest`,
with a Python matrix of 3.11, 3.12 and 3.13. It uses `astral-sh/setup-uv@v10` (latest release
v10.2.0, 2026-09-21) and runs `uv run --python ${{ matrix.python }} pytest -q`.

The data-dependent replay test skips itself when `~/.loopbrake/data` is missing, as it is in CI.

## R10. Tests for the success criteria

| Criterion | Test |
|---|---|
| SC-001 | `tests/test_replay_data.py`: for every run in the 6 public groups, at stop lines {10, 20, 40, 80, 160}, the brake's stop step equals the evaluation's. It skips without data. |
| SC-003 | `tests/test_brake.py`: 50 brakes × 250 steps; 95th-percentile decision time under 10 ms |
| SC-005 | Point `LOOPBRAKE_HOME` at a read-only folder, write garbage into the calibration file, and monkeypatch an internal function to raise. The host loop finishes each time. |
| SC-006 | Hand-made runs with 19 and 18 successful tasks, plus repeated tasks and excluded ids |
| SC-007 | Monkeypatch `socket.socket` to raise, then run start, step, calibrate, status and replay |
| SC-008 | Write 20 `run_start` events, 3 `stop` events and 1 `mistaken_stop` feedback event, then check the status numbers |

## R11. Publishing to PyPI (spec US4, FR-016, FR-017)

**Decision**: `.github/workflows/publish.yml`, following uv's GitHub guide (checked 2026-10-01).

- **Trigger**: a pushed tag matching `v[0-9]+.[0-9]+.[0-9]+`.
- **Job `build`** (no special permissions):
  1. `astral-sh/setup-uv@v10`;
  2. check that the tag without its `v` equals `loopbrake.__version__`, and fail with a message if
     not (FR-016);
  3. `uv build`, which writes the sdist and the wheel to `dist/`;
  4. a smoke test: in a fresh environment, install the wheel and run `loopbrake --version`;
  5. list the wheel's files and fail if anything outside `loopbrake/` and `*.dist-info/` is
     inside (FR-017);
  6. upload `dist/` as an artifact.
- **Job `publish`**: `needs: build`, `environment: pypi`, `permissions: id-token: write`. It
  downloads the artifact, then runs `uv publish`. Trusted publishing needs no credentials.
- **Why two jobs**: only the publish job can mint the publishing credential, which reduces
  supply-chain risk (uv docs).
- **Keeping the sdist small**: `[tool.hatch.build.targets.sdist]` includes only `src/`,
  `README.md`, `LICENSE` and `pyproject.toml`. Experiment code, data, specs and tests stay out.

**One-time manual setup by the builder** (needs their accounts):
1. On pypi.org: Account → Publishing → *Add a pending publisher*:
   - project `loopbrake`;
   - owner `SahilSelokar`, repository `LoopBrake`;
   - workflow `publish.yml`;
   - environment `pypi`.
2. On GitHub: repository Settings → Environments → create `pypi`.

**Alternatives considered**: a manual upload with a PyPI token. Rejected by the builder; tokens
leak and need rotating.

## R12. Open core boundary (constitution 2.3.0)

**Decision**: this feature ships only public code. The wheel and sdist contents are checked in CI
(R11). Any future private feature is a separate service in a private repository. The package keeps
working fully without it, and sending run content to it would need explicit opt-in (Principle VI).
