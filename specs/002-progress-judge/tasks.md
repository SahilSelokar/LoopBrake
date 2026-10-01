---

description: "Task list for the Progress Judge Experiment"
---

# Tasks: Progress Judge Experiment

**Input**: design documents in `specs/002-progress-judge/`: plan.md, spec.md, research.md,
data-model.md, contracts/, quickstart.md

**Tests**: included. The constitution requires a runnable check for every non-trivial part. Write
each phase's tests first and check that they fail before writing the code.

**Organization**: tasks are grouped by user story (US1, US2, US3 from spec.md).

**Words**:
- "judge" = Jev, the hosted model that answers "did this step make progress?";
- "judgment" = one stored answer;
- "net saved" = tokens saved minus the judge's own tokens.

The full table is at the top of plan.md.

**Secrets**: the Typesafe key lives only in `~/.loopbrake/typesafe_key` (permission 600; saved and
tested on 2026-10-01). It must never appear in any file in this repository, any result, any log or
any commit message.

**Commits**: no `Co-Authored-By` or other Claude attribution lines (the builder's standing rule).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can be done in parallel with other [P] tasks: different files, no unfinished dependencies.
- **[Story]**: the user story the task belongs to.
- All paths are relative to the repository root `LoopBrake/`.

---

## Phase 1: Setup

- [X] T001 Check `~/.loopbrake/typesafe_key` exists with permission `-rw-------`, and that `git grep -c "apikey_"` finds nothing in `LoopBrake/`. Create `eval/results/judge/.gitkeep`.

---

## Phase 2: Foundational (needed by every story)

**Purpose**: the pure judged scorer, task texts, the Jev client, and net-savings measurement. No
story can start until this phase is done.

### Tests first

- [X] T002 [P] Add to `tests/test_signals.py` tests for `judged(name, lam)` from `loopbrake.signals` (research R6, contracts/judge-request.md):
  - **Per-step values**:
    - `judge`: u = 1 − p;
    - `judge_steps`: u = (1 + (1 − p)) / 2;
    - `judge_max`: u = max(1 − p, the Phase 1 `max` signal value at that step).

    Check each with λ = 0 (score = u).
  - **Running score**: S_t = λ·S_(t−1) + u_t, checked at λ = 1.
  - **No opinion**: a `None` in `progress` keeps the score exactly at its previous value.
  - **Never looks ahead**: for every method and every t, `scorer(steps[:t], progress[:t]) == scorer(steps, progress)[:t]`.
  - **Kinds only affect reasons**: passing `kinds` leaves every score unchanged.
  - **Reason text**: the reason includes `judge: no progress in K of last N steps`, plus the latest `(kind, p)` when kinds are given.
- [X] T003 [P] Write `tests/test_judge.py` for `eval/judge.py`. Load it with `importlib`, as `tests/test_eval.py` does, and use a fake opener, so the tests make no network calls. Check:
  - **State**:
    - `task` is cut to its first 1,500 characters;
    - `earlier_actions` holds at most 3 items, each ≤ 200 characters, oldest first, and is empty on step 1;
    - `action` is ≤ 600 characters;
    - `result` is the first 1,200 characters + `…` + the last 800 when longer than 2,000;
    - the `…` mark appears only when something was cut.
  - **Key**: `sha256(json.dumps(body, sort_keys=True, ensure_ascii=False))` is stable, and the body never contains the access key.
  - **Parsing**: `answers.progress.noul` becomes `progress`; `answers.kind.choice` and `probabilities[choice]` become `kind` and `kind_p`; the usage tokens are summed. A missing field, or a `noul` outside 0–1, becomes `status = "unreadable"` with `progress = null`.
  - **Retries**:
    - a fake 429 and then 200 is retried and succeeds, and `Retry-After` is honoured (sleep is patched);
    - repeated 529/5xx/timeouts end as `service_error` after 6 tries;
    - 422 becomes `unreadable` with no retry;
    - 401 raises a stop error whose message doesn't contain the key.
  - **Refusals**:
    - a `local-1` or unknown group exits 2;
    - a holdout group while `eval/judge_candidate.json` is not committed exits 3 (the candidate path and the git check are patched);
    - with no key in the environment or the key file, it exits 4.
- [X] T004 [P] Write `tests/test_judge_eval.py` for `eval/judge_eval.py`, using hand-made runs and judgments. Check:
  - **Judge cost**:
    - a run stopped at step k pays judge tokens for steps 1..k;
    - a run that's never stopped pays for every judged step;
    - steps not asked (ask-level variant) cost nothing.
  - **Net saved** equals (agent tokens saved − judge tokens) / held-out agent tokens.
  - **Missing judgments** count as no opinion and are counted.
  - **Refusals**: `--final` exits 2 without a committed candidate, and exits 1 when any holdout step has no stored judgment.

### Code

- [X] T005 [P] Add `judged(name, lam)` to `src/loopbrake/signals.py` (research R6):
  - it returns a pure `scorer(steps, progress, kinds=None) -> [(score, reason), …]`;
  - `JUDGED = ("judge", "judge_steps", "judge_max")`;
  - `judge_max` uses the existing Phase 1 signal functions for the `max` value;
  - a `ValueError` for an unknown name or a missing `lam`;
  - standard library only (Principle III).

  Makes T002 pass.
- [X] T006 [P] Write `eval/tasks.py` (contracts/judge-cli.md, research R5). It reads the raw files under `~/.loopbrake/data/raw/` (`--data` changes the folder):
  - **SWE-bench groups**: `messages[1].content` of each `<iid>.traj.json`;
  - **τ-bench groups**: the first `role: "user"` message of each entry; the task id is `str(task_id)`, with one record per task.

  It writes `~/.loopbrake/data/tasks/<group>.jsonl` as `{"task", "text"}` lines, sorted by task, and prints a task count per group. Exit 1 if a raw file is missing, or if any run in `~/.loopbrake/data/runs/<group>.jsonl` has a task with no text. No network.
- [X] T007 Write `eval/judge.py`, part 1: **setup and requests** (contracts/judge-request.md, research R2):
  - **Setup `v1`**: the exact questions and criteria from the contract, `model = "jev-1.13.0"`, and the limits. `SETUP_ID = "jev-1.13.0/v1/" + sha256(template json)[:8]`.
  - **Requests**: `build_state(task_text, steps, i)` and `request_body(state)`; `judgment_key(body)`.
  - **Key loading**: from `TYPESAFE_API_KEY`, or else `~/.loopbrake/typesafe_key`.
  - **Public groups**: `PUBLIC_GROUPS` = the six group ids from `eval/fetch.py`'s `GROUPS`.
- [X] T008 Write `eval/judge.py`, part 2: **calling Jev** (contracts/judge-request.md "Errors", research R3):
  - **Call**: `POST https://api.typesafe.ai/v1/systemone` with `urllib.request`, a 60 s timeout, and headers `Authorization: Bearer <key>` and `Content-Type: application/json`.
  - **Retries**: on 429, 529, other 5xx or a timeout, wait 1, 2, 4, 8, 16, 32 s, or the `Retry-After` value if given, for at most 6 tries; then `status = "service_error"`.
  - **Other errors**: 422 becomes `unreadable` with no retry; 401 stops the run with "invalid TYPESAFE_API_KEY".
  - **Never** print, log or store the `Authorization` header. Remove it from any error message.
  - **Result**: a judgment dict in the data-model.md layout:
    - `ms` = wall time including retries;
    - `tokens` = `usage.input_tokens + usage.output_tokens`;
    - `status`: one of `ok`, `unreadable`, `service_error` or `truncated_ok` ("the state had to be shortened, and the answer is fine").
- [X] T009 Write `eval/judge.py`, part 3: **the runner** (contracts/judge-cli.md):
  - **Options**: `--group G …`, `--setup v1`, `--runs N --seed S`, `--recheck N`, `--rate 30`, `--workers 32`, `--data`.
  - **Inputs**: loads runs and task texts. Skips every key already in `~/.loopbrake/judgments/<setup id, "/" replaced by "-">/<group>.jsonl`, so a resumed run never judges twice.
  - **Speed**: runs requests in a `ThreadPoolExecutor`, paced to at most `--rate` requests a second, and appends each judgment under a lock.
  - **Progress**: prints a line every 1,000 steps with steps done, no-opinion count, tokens, and estimated cost at $0.042 per million input tokens.
  - **Refusals**, with exit codes 2, 3 and 4 as in the contract. Holdout groups need `eval/judge_candidate.json` tracked by git and unchanged against HEAD.
  - **`--recheck N`**: re-judges a seeded sample of N stored steps. Agreement means |Δp| ≤ 0.05 and the same `kind`. It prints the rate and writes `{"sample": N, "agree": rate}` to `recheck.json` in the same folder. It never changes stored judgments.

  Makes T003 pass.
- [X] T010 Write `eval/judge_eval.py`, part 1: **loading and preparing**:
  - reuse `eval/run.py` (`load_groups`, `make_split`, `split_rng`, `boot_items`, `_spread`, `_boot_interval`, `decide`, `stronger_baseline`, `write_csv`, `COLUMNS`) by loading it with `importlib`;
  - load the stored judgments of a setup into `{(group, run, step): judgment}`;
  - for each run, build the `progress`, `kinds` and `judge_tokens` lists (missing becomes `None` and 0, and is counted);
  - `prepare_net(run, scorer_output, judge_tokens, asked)` returns the running-max scores, the tail tokens, the total, and `judge_cum[i]` = judge tokens of asked steps 1..i+1.
- [X] T011 Write `eval/judge_eval.py`, part 2: **measuring net savings**:
  - `measure_net` adds `net_saved`, `judge_share` and `asked_share` to Phase 1's split metrics. The judge cost of a held-out run is `judge_cum[stop]` if stopped, otherwise `judge_cum[-1]`.
  - `evaluate_net` and `summarize_net` reuse Phase 1's splits (one run per task) and intervals, adding `net_saved_mean`, `net_saved_lo` and `net_saved_hi`.
  - Baselines have zero judge cost.

  Makes the first parts of T004 pass.

**Checkpoint**: `uv run pytest` passes, Phase 1's 42 tests included.

---

## Phase 3: User Story 1: measure a progress judge on the development group (Priority: P1). MVP.

**Goal**: judge every development step once, then compare the judge methods with Phase 1's methods.

**Independent test**: `uv run python eval/judge_eval.py --dev` prints a table with net saved and
false stops for each judge method, next to `steps`, `exact` and Phase 1's `max`. Two runs give
identical output.

- [X] T012 [US1] Write `--dev` in `eval/judge_eval.py`:
  - **Methods**: on `swe-devstral`, evaluate `fixed`, `exact` and `steps`, Phase 1's `max` (λ 0.9), and `judge`, `judge_steps` and `judge_max` at λ ∈ {0.8, 0.9, 1.0}, across α ∈ {0.01, 0.05, 0.10} × n ∈ {20, 50, 100}.
  - **Outputs**: write `~/.loopbrake/eval/judge-dev-results.csv` (Phase 1 columns plus `setup, ask_level, net_saved_mean, net_saved_lo, net_saved_hi, judge_share, asked_share`) and print a table at the headline setting.
  - **Health check** (research R9): print "setup looks broken" when more than 90% of p values sit within 0.1 of each other, or more than 10% of steps are no opinion.
  - **Suggestion**: print the best valid judge method by `net_saved_mean` at α 0.05, n 20, as "suggestion only".
- [X] T013 [US1] Run `uv run python eval/tasks.py` (expect 500, 500, 50, 115, 50 and 115 tasks). Then run `uv run python eval/judge.py --group swe-devstral --runs 100 --seed 0`:
  - check the cost so far (about $0.25 expected);
  - check the no-opinion share is under 10%;
  - check the median `ms`, and tune `--workers` so requests stay at or under 30/s.
- [X] T014 [US1] Run `uv run python eval/judge.py --group swe-devstral` (the rest of the group), then `--recheck 200`. Write down the cost, time and agreement rate (SC-004 target ≥ 95%).
- [X] T015 [US1] Run `uv run python eval/judge_eval.py --dev` twice and confirm identical output (SC-004). If the health check says "setup looks broken", define setup `v2` in `eval/judge.py`, judge `swe-devstral` only, and log why in `specs/002-progress-judge/research.md` R9.

**Checkpoint**: Story 1 works on its own. The judge is measured on the development group, at known
cost.

---

## Phase 4: User Story 2: pre-registered go/no-go on unseen agents (Priority: P2)

**Goal**: commit a choice, judge the holdout groups, and publish the verdict on net savings.

**Independent test**: `uv run python eval/judge_eval.py --final` writes
`eval/results/judge/results.md`, starting with GO or NO-GO on net tokens saved.

- [X] T016 [US2] Write `--final` in `eval/judge_eval.py` (contracts/judge-results.md):
  - **Candidate**: load and validate `eval/judge_candidate.json` (`setup`, `method`, `lam`, `ask_level`, `chosen_on`, `date`). Exit 2 if it's missing, and warn if it isn't committed. Exit 1 if any holdout step has no judgment.
  - **Methods**: on every public group, evaluate the Phase 1 methods, the judge methods at the chosen λ, and the chosen ask-level variant if set.
  - **Verdict**:
    - the bar per dataset = `stronger_baseline` on `saved_all`, since baselines have no judge cost;
    - the paired difference per bootstrap split = candidate `net_saved` − bar `saved_all`, averaged over the dataset's holdout groups;
    - `decide()` turns that into GO or NO-GO.
  - **Outputs**: write `eval/results/judge/results.csv` and `results.md`, with all 8 sections in contract order. Section 6 reads `recheck.json` and computes calls, tokens, the cost in dollars, the no-opinion share by status, the share of shortened inputs, and the median and 95th-percentile `ms`.
- [X] T017 [US2] Write the kill stories and `--story GROUP RUN` in `eval/judge_eval.py`, writing `eval/results/judge/kill-stories.md`:
  - it uses Phase 1's format (it can reuse `story` and `display` from `eval/run.py`);
  - the Reason line starts with the judged scorer's reason (`judge: no progress in K of last N steps (kind, p)`), followed by the Phase 1 signals' reason;
  - at least 10 stories per public group, or all if fewer.
- [X] T018 [US2] **Manual step, done by the builder**: choose the method from the `--dev` output and record it in `eval/judge_candidate.json`, in data-model.md's layout. Commit it with `git commit -m "eval: pre-register judge candidate"`, without attribution lines. This must happen **before** T019.
- [X] T019 [US2] Run `uv run python eval/judge.py --group swe-gpt5mini tau-gpt4o-airline tau-gpt4o-retail tau-sonnet35-airline tau-sonnet35-retail`. Before T018, the same command must exit 3; check that once. Write down the cost and time.
- [X] T020 [US2] Run `time uv run python eval/judge_eval.py --final` and check:
  - SC-001: no holdout row of the chosen method is invalid;
  - SC-002: the verdict is present;
  - SC-007: section 5 states the delay.

  Copy `eval/results/judge/` aside, run `--final` again, and confirm `diff -r` finds no differences. Commit `eval/results/judge/` without attribution lines.

**Checkpoint**: the go/no-go for Phase 2 is published.

---

## Phase 5: User Story 3: ask the judge only when it's needed (Priority: P3)

**Goal**: measure a cheaper variant that consults the judge only on suspicious steps, plus the delay
it would add live.

**Independent test**: `--dev` shows rows for 3 ask levels, with the share asked, net saved and the
expected delay per step.

**Order note**: to make the variant eligible as the chosen method, finish T021–T023 before T018.

- [X] T021 [P] [US3] Add tests to `tests/test_judge_eval.py`:
  - the ask levels are the 50th, 75th and 90th percentiles of the Phase 1 `max` (λ 0.9) step scores on `swe-devstral`;
  - a step is asked when its score is ≥ L;
  - steps not asked get `None` progress and zero judge tokens;
  - `asked_share` is right on a hand-made group.
- [X] T022 [US3] Add the ask-level variant to `eval/judge_eval.py` (research R8):
  - compute the levels on `swe-devstral` (`--dev`), and use the numeric `ask_level` from the candidate in `--final`;
  - evaluate each judge method at each level;
  - report the expected delay per agent step: typical = `asked_share` × median `ms`; worst 5% = the 95th-percentile `ms` on asked steps.

  Show them in the `--dev` table and in results.md section 5. Makes T021 pass.
- [X] T023 [US3] Run `uv run python eval/judge_eval.py --dev` and check the SC-006 target: at most 50% of steps asked while keeping at least 80% of the full judge's net savings. Write down the result either way.

**Checkpoint**: all three stories work.

---

## Phase 6: Polish

- [X] T024 [P] Add `ponytail:` comments in `eval/judge.py` for the known limits:
  - one setup decided in advance (the `v1` definition in `eval/judge.py`);
  - thread-and-pacing concurrency instead of async (the runner in `eval/judge.py`).

  Each comment names its limit and the fix.
- [X] T025 Follow `specs/002-progress-judge/quickstart.md` from top to bottom. Include the privacy checks:
  - `git grep -n "$(cat ~/.loopbrake/typesafe_key)"` finds nothing (SC-008);
  - every judgments file name is one of the six public groups.
- [X] T026 Update `specs/roadmap.md` (the progress-judge status line) and the status line of `specs/002-progress-judge/spec.md` with the verdict and the date. If the verdict is GO, note that Phase 2 is unblocked. Commit and push without attribution lines.

---

## Outcome (2026-10-01)

- **Verdict: NO-GO.** The pre-registered `judge_max` (λ 0.9, ask ≥ 7.79) did worse than the step-count rule:
  - SWE-bench: −6.3% [−18.9%, +1.9%];
  - τ-bench: −4.2% [−8.2%, −1.5%].
- **Cause**: the ask level is a raw score tuned on Devstral's long runs. On other agents it was almost never
  reached (0–0.3% of steps asked), so the method rarely stopped.
- **Exploratory**: judging every step gave negative net savings on all holdout groups. Before judge cost,
  `judge` alone still saved less than `steps` on most groups.
- **Checks**: SC-001 passed (no invalid holdout rows); SC-002, SC-003 (judging under 2 hours) and SC-004
  passed, with re-check agreement 94.0% reported; SC-006 met on dev; SC-007 reported; SC-008 passed.
  SC-005 (≥ 20.4%) not reached.
- **Spend**: about $3.91 in total (development $2.16, holdout $1.75).

## Dependencies and order

- **Setup (T001)** comes first.
- **Foundational (T002–T011)** blocks every story. Tests first: T002–T004, then T005–T011.
- **US1 (T012–T015)**: needs Foundational. This is the MVP.
- **US3 (T021–T023)**: needs US1's development judgments. Do it **before T018**, so the variant can be chosen.
- **US2 (T016–T020)**: T016–T017 (code) can be built any time after Foundational. **T018 (the manual commit) must come before T019 (holdout judging).** The tooling enforces this.
- **Polish (T024–T026)** comes last.

**Same-file order**:
- `eval/judge.py`: T007 → T008 → T009
- `eval/judge_eval.py`: T010 → T011 → T012 → T016 → T017 → T022

**Parallel opportunities**:
- T002, T003 and T004 (three test files);
- T005 and T006 (`signals.py` and `tasks.py`), alongside the start of `judge.py`;
- T021 alongside T016/T017 (test file vs code).

## Parallel example: Foundational

```bash
Task: "Add judged-scorer tests to tests/test_signals.py"
Task: "Write tests/test_judge.py with a fake opener"
Task: "Write tests/test_judge_eval.py with hand-made runs"
# then
Task: "Add judged() to src/loopbrake/signals.py"
Task: "Write eval/tasks.py"
```

## Implementation strategy

1. **MVP**: Setup, Foundational and US1 (T001–T015). For about $1.50 and roughly an hour of
   judging, you learn whether the judge looks promising on the development group at all.
2. **If promising**: US3 (T021–T023), then the commit (T018), then US2 (T019–T020).
3. **If clearly not promising on dev**: still run US2 as pre-registered, for an honest published
   NO-GO, or stop and rethink, logging the decision.

## Notes

- Total: 26 tasks. T018 is the builder's manual step.
- Estimated spend: about $3.50 over all judging (73,812 steps, about 280 tokens of fixed cost per request plus step text). It's measured live in T013.
- Phase 1 files (`eval/run.py`, `eval/fetch.py`, `eval/results/*.md|csv`) must not change.
