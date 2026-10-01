---

description: "Task list for the Core Package (LoopBrake v1)"
---

# Tasks: Core Package (LoopBrake v1)

**Input**: `specs/003-core-package/`: plan.md, spec.md, research.md, data-model.md, contracts/,
quickstart.md

**Tests**: included. Each phase's tests come first and must fail before the code is written.

**Rules for every commit**: no Claude attribution lines. The identity is the repo-local one
(SahilSelokar <sahilselokar03@gmail.com>).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel: different files, no unfinished dependencies.
- **[Story]**: US1–US4 from spec.md. Paths are relative to `LoopBrake/`.

---

## Phase 1: Setup

- [X] T001 Update `pyproject.toml` and `src/loopbrake/__init__.py`:
  - set `__version__ = "0.1.0"` and read the version from it (`dynamic = ["version"]`, `[tool.hatch.version] path = "src/loopbrake/__init__.py"`);
  - add `readme = "README.md"`, `license = "MIT"`, `license-files = ["LICENSE"]`, `authors`, `keywords` and `classifiers`, plus `[project.urls]` pointing at the repo;
  - add `[project.scripts] loopbrake = "loopbrake.cli:main"` and `[project.optional-dependencies] agent-sdk = ["claude-agent-sdk"]`;
  - set `[tool.hatch.build.targets.sdist] include = ["src/", "README.md", "LICENSE", "pyproject.toml"]`.

  Check with `uv build`, then list the wheel's files: only `loopbrake/` and `*.dist-info/` (research R11).
- [X] T002 [P] Write `.github/workflows/tests.yml` (research R9). It runs on `push` and `pull_request` on `ubuntu-latest`, with a matrix over Python 3.11, 3.12 and 3.13. Steps: `actions/checkout@v7`, `astral-sh/setup-uv@v10`, then `uv run --python ${{ matrix.python }} pytest -q`. Add a `build` job that runs `uv build` and checks the wheel holds only `loopbrake/` and `*.dist-info/`.

---

## Phase 2: Foundational (records and home folder; needed by every story)

- [X] T003 [P] Write `tests/test_records.py`, using a temporary `LOOPBRAKE_HOME` throughout. Check:
  - **Home folder**: `home()` uses `LOOPBRAKE_HOME`, or else `~/.loopbrake`.
  - **Project names**: `valid_project()` accepts `[A-Za-z0-9._-]{1,64}` and rejects `../x`, the empty name and names of 65 characters.
  - **Writing**: one event is one line with `v=1`, `ts`, `event`, `session` and `run`. A failed write (records folder made read-only) turns recording off without raising.
  - **Status (SC-008)**: 20 watched runs, 3 stops and 1 `mistaken_stop` give runs watched 20, stopped 3, mistaken 1 and allowance 1.0. Watch-only runs don't count toward the allowance.
  - **Feedback**: `add_feedback(run, "mistaken_stop")` appends to that run's session file. `"exclude"` also appends the id to `exclude.txt`. An unknown run raises `LookupError`.
- [X] T004 Write `src/loopbrake/records.py` (contracts/records.md):
  - `home()` and `valid_project(name)`;
  - `RunWriter(path)`, whose `write(event: dict)` makes one `write()` call per line on a file opened in append mode. On `OSError` it turns itself off and warns once with `RuntimeWarning`.
  - `read_events(home)`, `status(home, project=None)`, `add_feedback(home, run, verdict)`, `read_exclude(home)` and `add_exclude(home, id)`.

  Standard library only. Makes T003 pass.

---

## Phase 3: User Story 1: brakes in a few lines (Priority: P1). MVP.

**Goal**: `loopbrake.start()` and `brake.step()` stop a run at `stop_line + 1` with a reason. Without
a calibration it is watch-only, and it never hurts the host.

**Independent test**: with a calibration record whose stop line is 5, a loop that keeps stepping
gets `stop` at step 6 with a full reason. With no record, it never stops.

- [X] T005 [P] [US1] Write `tests/test_brake.py`. Calibration records are written by hand into a temporary home. Check:
  - **Stop rule**: stop line 5 means steps 1–5 continue, step 6 stops, and step 7 is still stop.
  - **Reason**: `stopped at step 6: past the stop line of 5 steps set from your N past successful runs (α 5%)`, plus `; last 5 steps: repeating…` when actions repeat.
  - **Watch-only**: with no file, or `watch_only: true`, a 300-step loop never stops, and `decision.watch_only` is set.
  - **`with` block**: it ends the run `stopped`, `interrupted` (on an exception, which is then re-raised) or `finished`, and writes `run_end`.
  - **Recalibration**: changing the record mid-run doesn't change the open brake's stop line.
  - **Events**: `run_start` carries the calibration, each `step` carries `action_excerpt` of at most 200 characters, and `stop` and `run_end` appear.
  - **SC-005**, the loop finishes in each of these cases:
    - a damaged calibration file (watch-only, one warning);
    - a read-only records folder;
    - `loopbrake.brake._decide` monkeypatched to raise, which gives continue, watch-only and one warning.
  - **SC-003**: 50 brakes × 250 steps, with the 95th-percentile `step()` time under 10 ms.
- [X] T006 [US1] Write `src/loopbrake/brake.py` (contracts/python-api.md, research R1, R2, R5):
  - `Decision` (NamedTuple), `Brake` and `start(project="default", *, session=None, run=None, home=None)`;
  - the stop rule: `method("steps")(steps)[-1][0] > stop_line`;
  - reasons from `method("max", lam=0.9)` only when stopping;
  - every public method wrapped so internal errors give watch-only plus one warning;
  - `__enter__` and `__exit__`.

  Makes T005 pass.
- [X] T007 [US1] Export `start`, `Brake`, `Decision`, `calibrate` and `__version__` from `src/loopbrake/__init__.py`. Write `tests/fixtures/calibration_runs.jsonl`: 25 made-up successful runs, one per task, with lengths 3–27, and 5 failed runs of 40 steps, for the README example and the CLI tests.

---

## Phase 4: User Story 2: calibrate, status, feedback, replay (Priority: P2)

**Goal**: the `loopbrake` command sets stop lines from runs files or Claude Code history, shows
status, records feedback, and replays runs.

**Independent test**: `loopbrake calibrate tests/fixtures/calibration_runs.jsonl --project demo`
writes a record whose `stop_line` matches `conformal.threshold`. `loopbrake status --project demo`
shows it.

- [X] T008 [P] [US2] Write `tests/test_calibrate.py`. Check:
  - **Runs file**: at most one successful run per task (the first by run id); `n`, `k` and `stop_line` match `rank`/`threshold`.
  - **SC-006**: 19 successful tasks at α 5% give the max length; 18 give `watch_only: true` and `stop_line: null`.
  - **Exclude list**: ids in `exclude.txt` are skipped.
  - **Claude Code folder**: copy `tests/fixtures/claude_code_session.jsonl` into a temporary folder. Successful turns are counted by Phase 1's rule.
  - **No source text**: the record holds no string longer than 64 characters except `sha256`, and no action or observation text from the source.
  - **Fingerprints**: the source sha256 is right.
- [X] T009 [US2] Write `src/loopbrake/calibration.py`: `calibrate(source, *, project="default", alpha=0.05, home=None) -> dict` (contracts/python-api.md, research R3), which writes `calibration/<project>.json`, and `load(project, home) -> dict | None`, which returns None on a missing or damaged file. Makes T008 pass.
- [X] T010 [P] [US2] Write `tests/test_cli.py`, calling `loopbrake.cli.main([...])` and capturing output. Check:
  - `--version` prints `loopbrake 0.1.0`;
  - `calibrate` prints the stop line, n, k and α, or a watch-only message saying how many more runs are needed; an unreadable source exits 2;
  - `status` shows the SC-008 numbers on hand-written events;
  - `feedback RUN --mistaken`, `--exclude`, and an unknown run (exit 1);
  - `replay FILE --stop-line 10` prints per-run stop steps and a summary, and writes no records;
  - no emoji anywhere in the output.
- [X] T011 [US2] Write `src/loopbrake/cli.py` (contracts/cli.md) with `argparse` subcommands `calibrate`, `status`, `feedback`, `replay` and `--version`. Errors go to stderr, without tracebacks unless `LOOPBRAKE_DEBUG=1`. Makes T010 pass.
- [X] T012 [P] [US2] Write `tests/test_replay_data.py` (SC-001):
  - skip when `~/.loopbrake/data/runs` is missing;
  - otherwise, for every run of the 6 public groups at stop lines {10, 20, 40, 80, 160}, the brake's first stop step (fed step by step, with records off through a temporary home) equals Phase 1's `kill_index(prepare(run, method("steps")), tau) + 1`, or neither stops.
- [X] T013 [P] [US2] Write `tests/test_no_network.py` (SC-007): monkeypatch `socket.socket` and `socket.create_connection` to raise, then run start, step, calibrate, status and replay on fixtures, with no errors.

---

## Phase 5: User Story 3: Claude's agent toolkit (Priority: P3)

- [X] T014 [US3] Check the SDK's hook output type for a `stopReason` field (research R8): read `types.py` from the `claude-agent-sdk` source on GitHub (no install needed), and record the finding in `specs/003-core-package/research.md` R8.
- [X] T015 [P] [US3] Write `tests/test_agent_sdk.py`, calling the callbacks directly with fake `input_data` dicts and a temporary home. Check:
  - with a stop line of 5, the 6th `PostToolUse` returns `{"continue_": False, ...}`;
  - `UserPromptSubmit` starts a new run;
  - `Stop` ends the run;
  - the action text is `"<tool_name> <json(tool_input, sorted keys)>"`;
  - an exception inside a callback returns `{}` and warns.

  `hooks()` itself is tested only if `claude_agent_sdk` imports (`pytest.importorskip`).
- [X] T016 [US3] Write `src/loopbrake/agent_sdk.py` (contracts/agent-sdk.md): the callbacks plus `hooks(project="default", *, home=None)`, which imports `HookMatcher` lazily and raises an `ImportError` naming the `agent-sdk` extra. Makes T015 pass.

---

## Phase 6: User Story 4: install from PyPI (Priority: P2)

- [X] T017 [US4] Write `.github/workflows/publish.yml` (research R11, contracts/release.md). It triggers on a pushed `v[0-9]+.[0-9]+.[0-9]+` tag.
  - **Job `build`**: the tag-vs-`__version__` check; `uv build`; the smoke test `uv run --isolated --with dist/*.whl loopbrake --version`; the wheel-contents check; upload `dist/`.
  - **Job `publish`**: `needs: build`, `environment: pypi`, `permissions: id-token: write`; download `dist/`; `uv publish`.
- [X] T018 [US4] Update `README.md`:
  - a "Use it" section with the install line (`pip install loopbrake`, available from v0.1.0), the five-line example, `loopbrake calibrate` and `loopbrake status`;
  - the status line;
  - the roadmap row for Phase 2.

  Rename the event `kill` to `stop` in `specs/roadmap.md`.
- [ ] T019 [US4] **Manual step, done by the builder**, once, on their accounts:
  - **On pypi.org**: add a pending trusted publisher: project `loopbrake`, owner `SahilSelokar`, repository `LoopBrake`, workflow `publish.yml`, environment `pypi`.
  - **On GitHub**: create the environment `pypi` in the repository settings.
- [ ] T020 [US4] After T019, and only with the builder's go-ahead: `git tag v0.1.0 && git push origin v0.1.0`. Watch the workflow, then check SC-009 with `uvx --from loopbrake==0.1.0 loopbrake --version` in a fresh folder.

---

## Phase 7: Polish

- [ ] T021 Run `specs/003-core-package/quickstart.md` steps 1–6 and 8, and fix any mismatch. Then update the status lines of `specs/roadmap.md` and `specs/003-core-package/spec.md`. Commit and push, without attribution lines.

## Dependencies and order

- **Setup**: T001–T002.
- **Foundational**: T003–T004.
- **US1**: T005–T007, the MVP.
- **US2**: T008–T013.
- **US3**: T014–T016.
- **US4**: T017–T020.
- **Polish**: T021.
- **Release gate**: T019 (manual) blocks T020. T020 also needs the builder's go-ahead, because a release is public.
- **Same-file order**: `src/loopbrake/__init__.py`: T001 → T007.
- **Parallel**: test files can be written in parallel with each other, and T002, T017 and T018 don't touch library code.

## Implementation strategy

1. **MVP**: T001–T007. A working brake.
2. **Then**: US2 (the command line), US3, US4's files (T017–T018), and polish.
3. **Last**: the release (T019–T020), when the builder is ready.

Total: 21 tasks. T019 is manual, and T020 waits for the builder's go-ahead.
