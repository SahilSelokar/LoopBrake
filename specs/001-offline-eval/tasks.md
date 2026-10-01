---

description: "Task list for the Offline Evaluation Experiment"
---

# Tasks: Offline Evaluation Experiment

**Input**: design documents in `specs/001-offline-eval/`: plan.md, spec.md, research.md,
data-model.md, contracts/, quickstart.md

**Tests**: included. The constitution requires a runnable check for every non-trivial part
(signals, the stop-line rule, file readers). The plan names four key tests. In each phase, write
the tests first and check that they fail before writing the code.

**Organization**: tasks are grouped by user story (US1, US2, US3 from spec.md), so each story can
be built and checked on its own.

**Words**: "stop line" = τ, "false stop" = stopping a run that would have succeeded. See the
table at the top of plan.md.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can be done in parallel with other [P] tasks: different files, no unfinished
  dependencies.
- **[Story]**: the user story the task belongs to.
- All paths are relative to the repository root `LoopBrake/`.
- Downloaded data lives in `~/.loopbrake/data/`, outside the repository.

---

## Phase 1: Setup

**Purpose**: an empty, runnable Python project.

- [X] T001 Create a git repository in `LoopBrake/` (`git init`). Add `.gitignore` containing `.claude/`, `__pycache__/`, `.venv/`, `.pytest_cache/` and `*.egg-info/`. Git is needed so the chosen method can be committed before the final run (research R9). `.claude/` must be ignored before the repository ever goes public (constitution).
- [X] T002 Create `pyproject.toml`:
  - project `name = "loopbrake"`, `version = "0.0.0"`, `requires-python = ">=3.11"`, `dependencies = []`;
  - a `[dependency-groups]` `dev = ["pytest"]`;
  - build backend `hatchling` with the `src/` layout (package at `src/loopbrake`);
  - `[tool.pytest.ini_options]` with `testpaths = ["tests"]` and `pythonpath = ["."]`, so tests can import `liveness.py` from the root.
- [X] T003 [P] Create the folders: `src/loopbrake/__init__.py` (containing only `__version__ = "0.0.0"`), `eval/results/.gitkeep` and `tests/fixtures/.gitkeep`. Check that `uv run python -c "import loopbrake; print(loopbrake.__version__)"` prints `0.0.0`.

**Checkpoint**: `uv run pytest` runs. Finding no tests is fine at this point.

---

## Phase 2: Foundational (needed by every story)

**Purpose**: the stop-line rule, the step and run records, the shared file format and the
replay engine. No story can start until this phase is done.

### Tests first

- [X] T004 [P] Write `tests/test_conformal.py`. Check:
  - `rank(19, 0.05) == 19`, `rank(20, 0.05) == 20`, `rank(18, 0.05) == 19`, `rank(99, 0.01) == 99`, `rank(20, 0.10) == 19`;
  - `threshold(xs, 0.05)` is `math.inf` for `len(xs) <= 18`, and `max(xs)` for 19 or 20 values;
  - `threshold` returns the k-th smallest value even when the input is unsorted or has ties;
  - **simulation**: in 20,000 trials of 21 random uniform scores (20 used to set the stop line, 1 test score, `random.Random(0)`), the share of trials where the test score is above `threshold(first20, 0.05)` is within ±0.005 of 1/21.
- [X] T005 [P] Write `tests/test_traces.py` for the normalized runs file. Check:
  - `write_runs` then `read_runs` gives back identical `Run` records;
  - `read_runs` skips bad lines, never raises, and counts each skip by reason in the returned `Counter`. Bad lines are: invalid JSON; empty `steps`; a negative or non-integer `tokens`; an empty `action`; an `error` that isn't true/false/null.
- [X] T006 [P] Write `tests/test_eval.py` for the replay engine, using a hand-made group of about 12 runs over 6 tasks, with some tasks run twice. Check:
  - **Kill step**: a run is stopped at the first step whose running-max score is above the stop line, and saved tokens are the sum of tokens of the later steps (0 if stopped on the last step).
  - **Task-level split**: no held-out run shares a task with any calibration run, in both `plain` and `boot` splits.
  - **Reproducibility**: the same seed gives identical splits; a different seed gives different ones.
  - **"insufficient" status**: when the group has fewer than n successes, when the held-out set has fewer than 20 successes, or when k > n.
  - **"invalid" status**: when the lower end of the false-stop rate's confidence interval is above α.
  - The `fixed` method is never marked invalid.

### Code

- [X] T007 [P] Write `src/loopbrake/conformal.py` following contracts/scoring-api.md:
  - `rank(n, alpha)` computes `ceil((n + 1) * (1 - Fraction(str(alpha))))` with exact `fractions.Fraction` math;
  - `threshold(run_scores, alpha)` returns the k-th smallest score, or `math.inf` when `k > len(run_scores)`.

  Standard library only. Makes T004 pass.
- [X] T008 Write the start of `src/loopbrake/signals.py`:
  - `Step(NamedTuple)` with `action: str`, `observation: str`, `error: bool | None`, `tokens: int`;
  - a module-level `METHODS` tuple (empty for now; filled in by US1 and US2);
  - `method(name, lam=None)`. It returns a scorer `scorer(steps) -> list[tuple[float, str]]`, one `(score, reason)` per step. It raises `ValueError` on an unknown name, on a missing `lam` for signal methods, or on a `lam` given to a baseline.

  Scorers must be pure: no I/O, clock, randomness or globals.
- [X] T009 Write `src/loopbrake/traces.py`:
  - `Run(NamedTuple)` with `group, task, run, success, exit, tokens_measured, steps` (`steps` is a tuple of `Step`);
  - `write_runs(path, runs)`, which writes JSON Lines with keys in the order shown in contracts/normalized-runs.md;
  - `read_runs(path) -> (list[Run], Counter)`, following that contract's rules:
    - "`steps` is non-empty and in order. Every `tokens` value is an int ≥ 0."
    - "`action` is never empty."
    - "A line that fails validation is skipped, and its reason is counted. Loading never raises because of one bad run."

  Makes T005 pass. Depends on T008.
- [X] T010 Write `eval/run.py`, part 1: **loading and preparing runs**.
  - Load every `~/.loopbrake/data/runs/<group>.jsonl` (`--data` changes the folder) into groups with the roles from data-model.md: `swe-devstral` is `dev`; `swe-gpt5mini` and the four `tau-*` groups are `holdout`.
  - For each run and method, compute once: the step scores, `peak` (running maximum of the scores), `tail_tokens[t]` (tokens saved if stopped after step t) and the run's total tokens.

  To make `eval/` import the package, run it with `uv run`.
- [X] T011 Write `eval/run.py`, part 2: **splits**.
  - **`plain` split**: draw n successful runs without replacement (calibration). The held-out set is every run whose `task` isn't used by any calibration run.
  - **`boot` split**: first resample *tasks* with replacement, then make a plain split. Every copy of a calibration task is removed from the held-out set.
  - **Seeding**: each split list comes from `random.Random(f"{seed}|{group}|{alpha}|{n}|{kind}")`. String seeds are stable across processes; never use `hash()`.
  - **Order**: sort task and run ids before sampling, so set order can't change the results.
  - **Sharing**: make the splits once per group and setting, and reuse them for every method, so comparisons are paired.
- [X] T012 Write `eval/run.py`, part 3: **measuring one split**. For a calibrated method:
  - τ = `threshold(calibration run scores, alpha)`;
  - a held-out run is stopped at step `bisect_right(peak, tau)` if that is less than its length. For `fixed`, it is stopped at the first step with score ≥ 1 (`bisect_left(peak, 1.0)`).

  Record for the split:

  | Value | Definition |
  |---|---|
  | false-stop rate | stopped successful held-out runs / successful held-out runs |
  | `saved_all` | tokens after the stop point on all stopped held-out runs / all held-out tokens |
  | `saved_fail` | the same, for failed runs only |
  | `lost` | tokens spent up to the stop on falsely stopped runs / all held-out tokens |
  | kill steps | the stop steps of stopped failed runs |
- [X] T013 Write `eval/run.py`, part 4: **summing up**. For each value over the `plain` splits:
  - the mean;
  - a 95% confidence interval for the mean: mean ± 1.96 × standard deviation / √(number of splits);
  - the 5th and 95th percentiles: `statistics.quantiles(values, n=20)`, first and last cut points.

  For each value over the `boot` splits, the 2.5th–97.5th percentiles (`statistics.quantiles(values, n=40)`, first and last).

  Status rules, from data-model.md:
  - `insufficient` when "the group has fewer than n successes, or the held-out set has fewer than 20 successes", and also when k > n (observe-only);
  - `invalid` when "the lower bound of the Monte Carlo confidence interval of the mean false-kill rate is above α";
  - "`fixed` rows are never judged against α".

  `kill_step_median` is the median over all stop events on failed runs, pooled across `plain` splits. Makes T006 pass.

**Checkpoint**: `uv run pytest` passes T004–T006.

---

## Phase 3: User Story 1: measure the simple rules on public runs (Priority: P1). MVP.

**Goal**: download the public runs, replay them through the three simple methods (`fixed`,
`exact`, `steps`), and print a results table with false-stop rates and tokens saved.

**Independent test**: `uv run python eval/run.py --dev` prints a table for `swe-devstral`:
- every calibrated row at α = 5% has a false-stop interval that includes 5% or lies below it;
- the `fixed` row's false-stop rate is reported;
- two runs print identical tables.

### Tests first

- [X] T014 [P] [US1] Write `tests/test_signals.py`, part 1:
  - **Liveness match**: turn the demo agents in `liveness.py` into `Step` lists (`action = f"{tool} {json.dumps(args, sort_keys=True)}"`, empty observation, `error=None`, `tokens=1`; take the first 30 steps of the endless agents with `itertools.islice`). The first step where `fixed` scores ≥ 1 is 5 for `looping` (`watch` says "stuck" at 5) and 21 for `wandering` (`watch` refuses step 21 and reports 20). `healthy` never reaches 1.
  - **`exact`**: the score is the running maximum of how many times an identical action has appeared.
  - **`steps`**: the score at step t is t.
  - **Never looks ahead**: for every name in `METHODS`, and every t, `scorer(steps[:t]) == scorer(steps)[:t]`. Use `lam=0.9` for methods that need it.
- [X] T015 [P] [US1] Write `tests/test_fetch.py` with small fixture files:
  - `tests/fixtures/tau_run.json`: one τ-bench run trimmed to 4 messages (MIT license);
  - `tests/fixtures/mini_v2.traj.json` and `tests/fixtures/mini_v1.traj.json`: made-up files that copy only the *field layout* of mini-SWE-agent 2.x and 1.17, from research R1/R3. No real S3 content, because its license isn't stated.

  Check that each parser gives the expected actions, observations, error flags and tokens, and that each run's tokens add up to the source's total.

### Code

- [X] T016 [US1] Add the three simple methods to `src/loopbrake/signals.py` and to `METHODS` (research R5):
  - **`fixed`**: score at step t = max(times this exact action has appeared so far / 3, t / 21). Reasons: "same action seen 3 times (steps a, b, c)" or "step limit of 20 reached".
  - **`exact`**: the running maximum of identical-action counts. Reason: "same action N times: `<first 80 chars>`".
  - **`steps`**: score = t. Reason: "step t".

  Makes T014 pass.
- [X] T017 [US1] Write `eval/fetch.py`, part 1. Network use is allowed only in this script (FR-016).
  - A table of the six groups (research R1): id, dataset, source URLs, expected successes/runs:
    - `swe-devstral` 282/500 and `swe-gpt5mini` 281/500, from S3 submissions `20251209_mini-v1.17.2_devstral-small-2512` and `20260217_mini-v2.0.0_gpt-5-mini`;
    - `tau-gpt4o-airline` 84/200, `tau-gpt4o-retail` 278/460, `tau-sonnet35-airline` 184/400 and `tau-sonnet35-retail` 637/920.
  - A download helper using `urllib.request`. It saves into `~/.loopbrake/data/raw/` and skips files already there.
  - **URLs**:
    - SWE-bench trajectories: `https://swe-bench-submissions.s3.amazonaws.com/bash-only/<submission>/trajs/<iid>/<iid>.traj.json`;
    - SWE-bench labels: `https://raw.githubusercontent.com/SWE-bench/experiments/main/evaluation/verified/<submission>/per_instance_details.json`;
    - τ-bench: `https://raw.githubusercontent.com/sierra-research/tau-bench/main/historical_trajectories/<gpt-4o-airline|gpt-4o-retail|sonnet-35-new-airline|sonnet-35-new-retail>.json`.
- [X] T018 [US1] Write `eval/fetch.py`, part 2: the **mini-SWE-agent 2.x parser** for `swe-gpt5mini`.
  - Each `tool_calls[]` entry is one step, with action `bash {"command": "<cmd>"}`, matching how the 1.17 parser writes actions.
  - The observation is the matching `role: "tool"` message. `error = extra.returncode != 0`.
  - Tokens: `usage.input_tokens + usage.output_tokens` of the assistant message (Responses-API format).
  - A call with several tool calls is charged to its first step. A call with no action is charged to the previous step (research R3).
  - Stop with an error if usage is missing on more than 1% of calls.
  - `success` comes from `per_instance_details[iid].resolved`. `task` and `run` are the instance id. `exit` is `info.exit_status`.
- [X] T019 [US1] Write `eval/fetch.py`, part 3: the **mini-SWE-agent 1.17 parser** for `swe-devstral`.
  - Take the command out of the assistant text with `info.config.agent.action_regex`, and write the action as `bash {"command": "<cmd>"}`.
  - The observation is the next user message. `error` comes from `<returncode>N</returncode>` in the observation.
  - Tokens: `extra.response.usage.prompt_tokens + completion_tokens`, charged with the same rules as T018.
- [X] T020 [US1] Write `eval/fetch.py`, part 4: the **τ-bench parser**.
  - Each assistant tool call is one step: action `<name> <json args, sorted keys>`. The observation is the `role: "tool"` message with the same `tool_call_id`. `error` = the output starts with `Error`.
  - An assistant text reply to the user is one step: action `respond {"content": "<text>"}`. The observation is the next user message. `error = null`.
  - **Estimated tokens** for each assistant message: (characters of all earlier messages + characters of this message) // 4, charged to its first step. Set `tokens_measured = false`.
  - `success = reward == 1`, `task = str(task_id)`, `run = f"{task_id}-{trial}"`.

  Makes T015 pass.
- [X] T021 [US1] Write `eval/fetch.py`, part 5: **output**.
  - Write `~/.loopbrake/data/runs/<group>.jsonl` with `write_runs`, and `~/.loopbrake/data/runs/SHA256SUMS`.
  - Print one line per group: runs, successes, failures, skipped.
  - Exit 1 if a download fails, or if a group's success/run counts differ from the table in T017 (this guards against a known bad labels file, research R1).
  - Command-line options `--data DIR` and `--only GROUP ...` (contracts/eval-cli.md).
- [X] T022 [US1] Write `eval/run.py`, part 5: **command line** and `--dev` mode with the simple methods.
  - Options (contracts/eval-cli.md): `--dev` (default), `--final`, `--local`, `--story GROUP RUN`, `--method`, `--lam`, `--seed` (default 0), `--splits` (default 1000; refuse below 500, FR-008), `--boot` (default 1000), `--data`.
  - `--dev` evaluates `swe-devstral` for every method in `METHODS` at α ∈ {0.01, 0.05, 0.10} × n ∈ {20, 50, 100}.
  - It prints a table and writes `~/.loopbrake/eval/dev-results.csv` with the columns from contracts/results.md: rates as fractions with 4 decimals, rows sorted by `group, method, lam, alpha, n`, no timestamps.
  - Exit 1 if data is missing.
- [X] T023 [US1] Run `uv run python eval/fetch.py`. Check the six count lines match T017 and that it exits 0. Then run `uv run python eval/run.py --dev` twice and check:
  - both outputs are identical;
  - every calibrated row at α = 0.05 has `fk_lo <= 0.05`.

  Write down the `fixed` row's false-stop rate; it's the first reel number (SC-008).

**Checkpoint**: Story 1 works on its own. The simple methods are measured on real data, and the
false-stop guarantee is checked.

---

## Phase 4: User Story 2: better signals and the go/no-go decision (Priority: P2)

**Goal**: add the stuck signals, choose one method on the development group, write that choice
down, test it on the other groups, and publish the decision with kill stories.

**Independent test**: `uv run python eval/run.py --final` writes `eval/results/results.md`.
It starts with GO or NO-GO, and gives each dataset's paired difference and its interval.
`kill-stories.md` has at least 10 stories per public group.

### Tests first

- [X] T024 [P] [US2] Write `tests/test_signals.py`, part 2 (research R6). Check:
  - **`fuzzy`**: the highest Jaccard similarity of word sets against the previous 10 actions. Digits are kept, so `sed -n 100,200p f` vs `sed -n 200,300p f` scores below 1, and identical commands score 1. The first step scores 0.
  - **`stale`**: 1 − (new lines / all lines), where lines are whitespace-collapsed and digit runs are masked to `0`. An empty observation scores 0. Repeating an identical output scores 1.
  - **`errors`**: 1 only when the step is an error and its signature (the last non-empty line, digits masked) appeared earlier in the run. Error detection order: the `error` flag if not None, otherwise the last line matches `error|exception|traceback|not found|no such file` (case-insensitive).
  - **Combinations**: `mean`, `max`, and `loop = fuzzy × stale`.
  - **Running score**: S_t = λ·S_{t−1} + u_t.
  - **Reasons**: they name each signal with a value ≥ 0.5 in the last 5 steps, with a count and one pointer, such as "same command as step 12" or "0 of 40 output lines new".
  - `method()` raises `ValueError` when `lam` is missing for these six methods.
- [X] T025 [P] [US2] Add to `tests/test_eval.py` checks for the decision, using made-up per-split numbers:
  - **Stronger simple method**: of `exact` and `steps`, the one with the higher mean `saved_all` at α = 0.05, n = 20 over a dataset's holdout groups.
  - **Dataset-level difference**: computed per `boot` split as the mean, over that dataset's holdout groups, of (chosen method − stronger simple method).
  - **GO** only when both datasets' 2.5th percentile of that difference is above 0 and the chosen method isn't `invalid` in any holdout group. Otherwise NO-GO.
  - `--final` exits with code 2 when `eval/candidate.json` is missing.

### Code

- [X] T026 [US2] Add `fuzzy`, `stale` and `errors` to `src/loopbrake/signals.py`, exactly as described in T024, each with its reason text. Use Jaccard on word sets, not `difflib` (research R6).
- [X] T027 [US2] Add the combinations `mean`, `max` and `loop`, plus the running score S_t = λ·S_{t−1} + u_t, to `src/loopbrake/signals.py`. Register all six signal methods in `METHODS`, in the order `("fixed", "exact", "steps", "fuzzy", "stale", "errors", "mean", "max", "loop")`. Makes T024 pass, and the "never looks ahead" test from T014 must still pass for all nine.
- [X] T028 [US2] Extend `--dev` in `eval/run.py`:
  - run the six signal methods at λ ∈ {0.8, 0.9, 1.0};
  - print the best valid row by mean `saved_all` at α = 0.05, n = 20, marked "suggestion only".
- [X] T029 [US2] **Manual step, done by you (the builder)**: choose the method and record it in `eval/candidate.json`.
  - run `uv run python eval/run.py --dev`;
  - choose the method and λ;
  - write `eval/candidate.json` as `{"method": "<name>", "lam": <float>, "chosen_on": "swe-devstral", "date": "YYYY-MM-DD"}`;
  - commit it (`git add eval/candidate.json && git commit -m "eval: pre-register gate candidate"`).

  This must happen **before** any `--final` run (research R9).
- [X] T030 [US2] Write `--final` in `eval/run.py`.
  - If `eval/candidate.json` is missing, exit 2. If it isn't committed (`git ls-files --error-unmatch` fails, or `git diff --quiet` shows changes), print a warning.
  - Evaluate every group, with the three simple methods plus the six signal methods at the chosen λ, across the full α × n grid, using both `plain` and `boot` splits.
  - Then compute the stronger simple method per dataset, the paired differences and the verdict, as tested in T025. Makes T025 pass.
- [X] T031 [US2] Write `eval/results/results.csv` and `eval/results/results.md` in `eval/run.py`, following contracts/results.md. results.md has, in order:
  1. **Reproduce**: the command, seed, split counts and each group's sha256 from `SHA256SUMS`.
  2. **Verdict**.
  3. **Main table** (α = 5%, n = 20).
  4. **Against FailFast**: our `steps` and chosen method on `swe-gpt5mini`, next to FailFast's published numbers at 5% (FailFast 14.6–20.4%, AgentStop 10.2–12.5%, Duration 10.0–12.0%), with the three caveats from research R4.
  5. **Price of the guarantee**: the chosen method and `steps` at n = 20, 50, 100, α = 5%.
  6. **Ablation**: all methods, with dev rows marked "chosen on this data".
  7. **Token estimate check**: on both SWE-bench groups, the chars/4 estimate rebuilt from the steps vs the measured tokens, as a median ratio, with a note that it ignores the system prompt.
  8. **Skipped runs**.

  No timestamps; the date comes from candidate.json.
- [X] T032 [US2] Write **kill stories** in `eval/run.py`:
  - for each public group, take the median stop line of the chosen method over the `plain` splits at α = 0.05, n = 20;
  - pick the failed runs it stops at that line, sorted by tokens saved (at least 10, or all if fewer, with a note);
  - write `eval/results/kill-stories.md` in the format in contracts/results.md: a header with the run, stop step, tokens saved and %, the reason, then up to 5 earlier actions of at most 80 characters each, and under 60 words of prose.

  Also write `--story GROUP RUN`, which prints one story to the screen.
- [X] T033 [US2] Run `time uv run python eval/run.py --final`. Check:
  - it finishes in under 15 minutes (SC-002). If not, apply the fallback in research R12: error bars at the main setting only first.
  - no holdout row is `invalid` (SC-001);
  - results.md starts with GO or NO-GO (SC-004).

  Then copy `eval/results/` to a temporary folder, run `--final` again, and confirm `diff -r` finds no differences (SC-003). Commit `eval/results/`.

**Checkpoint**: Stories 1 and 2 work. The go/no-go decision for Phase 2 is published.

---

## Phase 5: User Story 3: the same evaluation on your own Claude Code history (Priority: P3)

**Goal**: replay your own Claude Code turns locally. Only renamed, summed-up numbers ever reach
the repository.

**Independent test**: `uv run python eval/run.py --final --local` adds `local-1`, `local-2`
rows to `eval/results/results.csv`. Per-run details exist only in `~/.loopbrake/eval/local/`,
and `eval/results/` contains none of your project folder names (read from `~/.loopbrake/eval/local-map.json`) and no home-folder path.

### Tests first

- [X] T034 [P] [US3] Write the made-up fixture `tests/fixtures/claude_code_session.jsonl` (no real transcript content). It contains:
  - two user prompts, so two turns;
  - one assistant response split across two records with the same `message.id` and the same `usage`, so tokens must be counted once;
  - one assistant message with two `tool_use` blocks, so its tokens are charged to the first step;
  - a `tool_result` with `is_error: true`;
  - a text block `[Request interrupted by user for tool use]` in the second turn;
  - an `isMeta: true` user record and a `<local-command-stdout>` user record, neither of which starts a turn;
  - one `isSidechain: true` record, which is skipped;
  - one record with an unknown `type`, which is counted.
- [X] T035 [US3] Add Claude Code tests to `tests/test_traces.py`, using the fixture. Check:
  - the fixture gives 2 runs;
  - turn 1 is `success=True` and turn 2 is `False` (interrupted);
  - steps pair each `tool_use` with the `tool_result` that has the same `tool_use_id`;
  - tokens use `input_tokens + cache_creation_input_tokens + cache_read_input_tokens + output_tokens`, counted once per `message.id`;
  - the returned `Counter` lists the skipped sidechain and unknown records;
  - passing a turn's id in `exclude` turns its `success` to `False`.

### Code

- [X] T036 [US3] Write `claude_code_turns(transcript, exclude=())` in `src/loopbrake/traces.py`, following research R10.
  - **Turn start**: a `type: "user"` record that isn't `isMeta`, has string or `text`-block content with no `tool_result`, and isn't a local-command output or an interrupt marker.
  - **Turn id**: that record's `uuid`.
  - **Steps**: each `tool_use` is a step; the action is `<tool name> <json input, sorted keys>`.
  - **Interrupted**: a text block starting with `[Request interrupted by user` marks the turn interrupted (`exit = "interrupted"`, `success=False`).
  - **Skipped and counted**: sidechain records and unknown record types.

  This is the **only** function that reads this format (constitution Principle V). Makes T035 pass.
- [X] T037 [US3] Add `--local` to `eval/run.py`.
  - Each folder in `~/.claude/projects/` is one group: read every `*.jsonl` in it with `claude_code_turns`, using the exclude list from `~/.loopbrake/exclude.txt` (one turn id per line; a missing file means an empty list).
  - Name the groups `local-1`, `local-2`, … in sorted folder order. Save the name map to `~/.loopbrake/eval/local-map.json`.
  - Per-run details go to `~/.loopbrake/eval/local/<label>.csv`.
  - Only with `--final`, add summed-up rows (`dataset = claude-code-local`, `role = local`) to `eval/results/results.csv`.
  - Local groups never count toward the go/no-go decision. No folder names, paths, actions or kill stories from local data may be written inside the repository (FR-014, constitution Principle VI).
- [X] T038 [US3] Run `uv run python eval/run.py --final --local`. Check:
  - `local-*` rows appear, and small projects show `insufficient`;
  - the leak check in quickstart.md step 6 prints `clean` (SC-007). It reads your real folder names from `~/.loopbrake/eval/local-map.json`, so no private name is ever written into the repository.

**Checkpoint**: all three stories work.

---

## Phase 6: Polish

- [X] T039 [P] Add `ponytail:` comments for the two deliberate shortcuts from plan.md's Complexity Tracking, each naming its limit and fix:
  - recomputing scores from all steps so far, in `src/loopbrake/signals.py`;
  - plain-Python random splits, in `eval/run.py`.
- [X] T040 Follow `specs/001-offline-eval/quickstart.md` from top to bottom on a clean checkout, and fix anything that doesn't match. Include the sanity check: `steps` on `swe-gpt5mini` at n = 100 should be roughly 10–12% `saved_all`. If it's far off, check the token counting before trusting other numbers (research R4).
- [X] T041 Update the status line in `specs/roadmap.md` and the spec status to the outcome (GO or NO-GO) and its date. Commit.

---

## Dependencies and order

### Phases

- **Setup (T001–T003)**: start immediately.
- **Foundational (T004–T013)**: needs Setup. Blocks every story.
- **US1 (T014–T023)**: needs Foundational. This is the MVP.
- **US2 (T024–T033)**: needs US1. It reuses the downloaded data, the simple methods and `--dev`. The manual step T029 must come before T030–T033.
- **US3 (T034–T038)**: needs only Foundational for its code (T034–T037). Its check, T038, needs `--final` from US2.
- **Polish (T039–T041)**: after the stories you want are done.

### Within each phase

- Tests come first and should fail before the code exists.
- Same-file tasks run in order:
  - `signals.py`: T008 → T016 → T026 → T027
  - `traces.py`: T009 → T036
  - `eval/run.py`: T010 → T011 → T012 → T013 → T022 → T028 → T030 → T031 → T032 → T037
  - `eval/fetch.py`: T017 → T021

### Parallel opportunities

- T003 alongside T002 (after T001).
- T004, T005, T006 and T007: four different files.
- In US1, T014 and T015 (tests) together. Then `signals.py` (T016) and `fetch.py` (T017–T021) in parallel, because they are different files.
- In US2, T024 and T025 together.
- US3's code (T034–T037) can be built alongside US2, since it only touches `traces.py` and the fixtures until T037.

## Parallel example: User Story 1

```bash
# tests together
Task: "Write tests/test_signals.py part 1 (liveness match, exact, steps, never looks ahead)"
Task: "Write tests/test_fetch.py with trimmed τ-bench and made-up mini-SWE-agent fixtures"

# then two different files at once
Task: "Add fixed/exact/steps to src/loopbrake/signals.py"
Task: "Write eval/fetch.py parts 1–5 (download, three parsers, output)"
```

## Implementation strategy

### MVP first (User Story 1 only)

1. Setup and Foundational: T001–T013.
2. US1: T014–T023.
3. **Stop and check**: the simple methods are measured on real data, the false-stop guarantee
   holds, and the numbers repeat exactly. That's enough for the first build-in-public reel
   ("the naive 20-step rule stops most good runs").

### Then

4. US2: signals, the written-down choice, `--final`, the go/no-go decision and kill stories.
   This decides whether Phase 2 (the package) starts.
5. US3: your own history, locally.
6. Polish.

## Outcome (2026-10-01)

- **Verdict: NO-GO.** The pre-registered method (`max`, λ 0.9) beat the step-count rule by +1.5%
  on SWE-bench [−10.6%, +15.1%] and +2.2% on τ-bench [−2.1%, +7.4%]. Both intervals include zero.
- **SC-001 failed on τ-bench** for the signal methods: false stops reached 6.4% against a 5% limit
  (`tau-gpt4o-airline`). Cause: the stop line was set from runs that could include several attempts
  at the same task. A diagnostic that uses at most one run per task brings every group back under
  5% (2.9–4.8%). The builder approved the fix, applied in a separate commit after the first record.
  After the fix, no holdout row is invalid, so SC-001 passes. The verdict is still NO-GO: SWE-bench
  +1.5% [−9.7%, +13.2%], τ-bench +0.9% [−3.1%, +5.0%]. See `eval/results/CORRECTIONS.md`.
- **Passed**:
  - SC-002 (60 s);
  - SC-003 (identical rerun);
  - SC-004 (verdict);
  - SC-006 (10 stories per group);
  - SC-007 (leak check clean);
  - SC-008 (the fixed rule stops 99.3% of good Devstral runs and 29.1% of GPT-5-mini runs).
- **Sanity check**: `steps` at n = 100 on GPT-5-mini saves 11.2%, inside FailFast's Duration range
  (10.0–12.0%).

## Notes

- Total: 41 tasks. T029 is a manual step you do yourself.
- Standard library only in `src/` and `eval/`. pytest is the only extra, for tests (constitution Principle III).
- Nothing from `~/.claude/` or `~/.loopbrake/` is ever committed (constitution Principle VI).
- Commit after each task or small group of tasks.
