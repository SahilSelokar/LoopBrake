# Research: Offline Evaluation Experiment

**Feature**: [spec.md](spec.md) | **Date**: 2026-10-01

Every NEEDS CLARIFICATION item from the Technical Context is resolved below. Sources: dataset
probes run on 2026-10-01, the FailFast paper (arXiv 2608.03222v1), the MAST-Data card and files,
and a structure-only scan of local Claude Code transcripts (no content was printed).

## R1. Public datasets and groups

**Decision**: use six public groups. A group is one agent/model on one dataset.

| Group id | Dataset | Agent / model | Runs | Successes | Tasks × trials | Tokens |
|---|---|---|---|---|---|---|
| `swe-devstral` | SWE-bench Verified | mini-SWE-agent 1.17.2 / Devstral-Small-2512 | 500 | 282 | 500 × 1 | measured |
| `swe-gpt5mini` | SWE-bench Verified | mini-SWE-agent 2.0.0 / GPT-5-mini | 500 | 281 | 500 × 1 | measured |
| `tau-gpt4o-airline` | τ-bench | GPT-4o, airline | 200 | 84 | 50 × 4 | estimated |
| `tau-gpt4o-retail` | τ-bench | GPT-4o, retail | 460 | 278 | 115 × 4 | estimated |
| `tau-sonnet35-airline` | τ-bench | Claude 3.5 Sonnet (new), airline | 400 | 184 | 50 × 8 | estimated |
| `tau-sonnet35-retail` | τ-bench | Claude 3.5 Sonnet (new), retail | 920 | 637 | 115 × 8 | estimated |

**Sources**:
- **SWE-bench**: trajectories are on public S3 at
  `swe-bench-submissions/bash-only/<submission>/trajs/<iid>/<iid>.traj.json`. The submissions
  are `20251209_mini-v1.17.2_devstral-small-2512` and `20260217_mini-v2.0.0_gpt-5-mini`. Labels
  come from `per_instance_details.json` in `SWE-bench/experiments`
  (`evaluation/verified/<submission>/`).
- **τ-bench**: `historical_trajectories/*.json` in `sierra-research/tau-bench` (MIT). Each run
  has a `reward` (0/1) and a `traj` (OpenAI-style messages with `tool_calls`). Runs are capped
  at 30 agent messages.

**Rationale**:
- **Closest to FailFast:** the SWE-bench groups are the only public runs that record token usage
  for every step, and they use the same harness family as FailFast (mini-SWE-agent on SWE-bench
  Verified).
- **Lots to save:** the Devstral group has long failed runs (median 84.5 calls, against 57.5 for
  resolved runs). 45 of them hit the 250-step or $3 limit, all failures.
- **A different domain:** τ-bench adds non-coding tool-use (customer service) under a permissive
  license, so test fixtures can come from it.

**Alternatives considered**:
- `nebius/SWE-agent-trajectories` (CC-BY-4.0, 80k runs) and
  `nebius/SWE-rebench-openhands-trajectories` (CC-BY-4.0, 67k runs): good labels but no token
  counts, and the downloads are 1–2 GB of parquet. Parquet needs a non-stdlib reader. Deferred
  as an optional seventh group if we want a third harness.
- `SWE-smith-trajectories` (MIT): synthetic bugs, no tokens. Rejected.
- `swe_rebench_07_2026` (Claude Code, Codex, Cursor): token totals only per run, not per step,
  and the license is "other". Rejected for now. It's the only public Claude Code data, so it's
  worth revisiting for Phase 3.

**Fetch checks**: `per_instance_details.json` has a known bad entry in another submission (one
model shows 0 resolved), so the fetch step checks that each group's resolved count matches the
numbers above. If it doesn't, the fetch fails.

## R2. MAST-Data dropped

**Decision**: remove MAST-Data from the evaluation (spec FR-001 amended).

**Rationale**: none of the 1,642 traces has a task success label. `mast_annotation` only flags
failure modes, and "no failure mode flagged" is not the same as "solved". Each trace is one raw
text log in a format specific to its framework, with no per-step tokens. Four of its seven
frameworks have 30 traces or fewer. It can't support calibration on successful runs.

**Alternatives considered**: grading Magentic/GAIA final answers ourselves, which is a project
of its own. Who&When was also checked: it contains only failures.

## R3. Token accounting

**Decision**: one definition everywhere: **billed tokens**. A step's tokens are the tokens
processed by the model call that produced that step's action, input plus output. Input includes
re-reading the whole context, which is the "token snowball".

**How each source is counted**:
- **Measured (SWE-bench)**:
  - GPT-5-mini: `usage.input_tokens + usage.output_tokens`, from the Responses-API format.
  - Devstral: `extra.response.usage.prompt_tokens + completion_tokens`.
- **Measured (Claude Code)**: `input_tokens + cache_creation_input_tokens +
  cache_read_input_tokens + output_tokens`, counted once per `message.id`. One API response is
  split across several transcript records that repeat the same `usage`: the local scan found
  22,840 assistant records but 10,782 unique message ids.
- **Estimated (τ-bench)**: for each agent message, (characters of all prior messages +
  characters of this message) / 4.

**Attribution**:
- A call that emits several actions (parallel tool calls) is charged to its first step. Its
  other steps are charged 0.
- A call with no action (a text-only reply) is charged to the previous step, or to the first
  step if there is none.

This keeps each run's total exact.

**Tokens saved when killed after step t** = the sum of tokens for steps after t. The kill happens
after step t's result is seen, which matches a PostToolUse hook.

**Rationale**:
- Billed tokens are what users pay for, and FailFast cites the snowball effect.
- Under the context-re-read model, a run killed halfway saves about 75% of its tokens, not 50%.
  Mixing the two models would make the numbers meaningless, so one model is used throughout.
- The estimated groups only compare methods with each other on the same estimate.

**Diagnostic**: on the measured SWE-bench groups we also compute the chars/4 estimate and report
how far it lands from measured usage. This shows how far to trust the τ-bench absolute numbers.

**Alternatives considered**: counting only new or output tokens. Rejected: it understates spend
by an order of magnitude on long runs, and it isn't what a bill shows.

## R4. Headline metric and the FailFast comparison

**Decision**: the headline is **tokens saved overall**: tokens after the kill point on all
killed held-out runs, divided by all tokens of the held-out runs, at α = 5% and n = 20. Savings
on failed runs only are always reported next to it.

**Rationale**: this is FailFast's definition, quoted: "fraction of total agent compute (in
tokens) reclaimed by early abortion, relative to running all trajectories (aborted and
completed) to completion". Their FPR is "the fraction of successful runs wrongly aborted", the
same as our false-kill rate.

**Comparability caveats** (printed next to the comparison row):
1. FailFast fitted its threshold on evaluation-fold predictions, so its 5% is a target, not a
   held-out guarantee. Ours is held out by construction.
2. Different models: they used Qwen3.5/3.6, Gemma4 and Gemini 3 Flash; we use GPT-5-mini and
   Devstral.
3. Which tokens they count is not stated.

**Reference numbers at 5% FPR**:

| | FailFast | AgentStop | Duration (step count) |
|---|---|---|---|
| Tokens saved | 14.6–20.4% | 10.2–12.5% | 10.0–12.0% |

**Sanity anchor**: our calibrated step-count baseline is their "Duration" control. If ours lands
far from 10–12% on `swe-gpt5mini` at n = 100, check the token accounting before trusting
anything else.

## R5. Baselines

**Decision**: three baseline methods, all scored by the same machinery as the candidates.

| Method | Step score | Calibrated? |
|---|---|---|
| `fixed` | the liveness.py rule as-is: kill when an identical action is seen a 3rd time, or at step 21 | no (shows the cost of skipping calibration) |
| `exact` | running max of identical-action counts | yes |
| `steps` | step index t, so the run score is the run length | yes (= FailFast "Duration") |

The gate compares the candidate against the stronger of `exact` and `steps` on each dataset,
judged by mean savings.

**Rationale**: liveness.py has two knobs, a repeat limit and a step cap. Calibrating each one
separately is faithful to the rule, and it makes the bar honest: a cheap step budget is the
baseline that actually matters (FailFast's Duration reaches 10–12%).

**Alternatives considered**: one combined score from both knobs. Rejected: it needs an arbitrary
weighting between the two.

## R6. Candidate signals

**Decision**: each signal gives a per-step value u ∈ [0, 1]. A leaky accumulator turns these
into the step score: S_t = λ·S_{t−1} + u_t. The run score is max_t S_t. All of this is pure and
stdlib-only.

**Signals**:

| Signal | Definition |
|---|---|
| `fuzzy` | The highest Jaccard similarity between the word set of this step's action and each of the previous 10 actions. Digits are kept, so paging through a file (`sed -n 100,200p` then `200,300p`) is not a repeat. |
| `stale` | 1 − (new observation lines / all observation lines). Lines are normalized: whitespace collapsed, digit runs masked to `0`. An empty observation scores 0, because edits print nothing and that isn't evidence of being stuck. |
| `errors` | 1 if the step is an error and its signature was already seen in this run, else 0. |

- **What counts as an error**: a non-zero return code where the data has one; a τ-bench tool
  output that starts with `Error`; otherwise a last line matching
  `error|exception|traceback|not found|no such file`.
- **The signature** is the last non-empty line, with digits masked.

**Combinations**:

| Combo | Formula | Meaning |
|---|---|---|
| `mean` | mean of the three signals | |
| `max` | max of the three signals | |
| `loop` | `fuzzy × stale` | "repeating and learning nothing" |

**λ values tried** (on the dev group only): {0.8, 0.9, 1.0}. λ = 1 is a cumulative count of
stuck evidence.

**Kill reason**: name each signal with u ≥ 0.5 in the last 5 steps, how often it fired, and one
concrete pointer. Examples: "same command as step 12", "0 of 40 output lines new", "same error as
step 9: ModuleNotFoundError…".

**Rationale**:
- Loops look like repeated actions whose results teach the agent nothing. The product `loop`
  encodes exactly that and avoids flagging legitimate polling or paging.
- The accumulator means one repeated poll doesn't kill, but sustained repetition does.
- Any score function keeps the guarantee (constitution Principle I), so trying variants is safe.
  Only the selection protocol (R9) protects the headline from cherry-picking.

**Alternatives considered**:
- `difflib.SequenceMatcher` for fuzzy matching: quadratic on long commands; Jaccard is linear.
- Learned weights: they need a training split and invite overfitting. Deferred: Principle III
  says to add learned or model signals only after a plateau.

## R7. Splits and the threshold

**Decision**:
- **Calibration sample**: n successful runs drawn at random, **at most one per task** (corrected
  after the first final run; see the alternatives below).
- **Held-out set**: every run whose task is not touched by the calibration sample. For the
  single-run SWE-bench groups, this is just "all runs not in calibration".
- **Threshold**: τ is the k-th smallest calibration run score, with
  k = ⌈(n+1)(1−α)⌉ computed with `fractions.Fraction(str(α))`. If k > n, then τ = ∞ and the
  method never kills.
- **Kill rule**: a run is killed at the first step t where S_t > τ.
- **Insufficient data**: a configuration is reported as "insufficient data" when the group has
  fewer than n successes, or when a split leaves fewer than 20 held-out successes.

**Rationale**:
- **Splitting by task:** τ-bench runs each task 4–8 times. Splitting by run would leak a task's
  behaviour from calibration into the test set, and splitting by task matches deployment, where
  new tasks arrive.
- **Using Fraction:** a sweep of n ≤ 20,000 at the usual α values found no case where float and
  exact arithmetic disagree. Fraction is the same length and can't round wrong.
- **Expected false-kill rate** with continuous scores: (n + 1 − k)/(n + 1). At n = 20 and α = 5%
  that is 1/21 ≈ 4.76%. This is the test oracle.

**Alternatives considered**: drawing calibration runs without regard to task. This was used in
the first final run (commit e655b96), and it broke the guarantee on τ-bench: false stops reached
6.4% at a 5% limit. Repeats of one task are not independent, so a sample with several of them
sets the stop line too low for new tasks. One run per task fixes it (2.9–4.8% in a diagnostic).
The cost: n can't exceed the number of tasks with a success, so `tau-gpt4o-airline` gets no
n = 50 result. An earlier draft of this plan had rejected one-run-per-task for exactly that
reason, and that was the wrong trade.

## R8. Intervals and the gate statistic

**Decision**: two Monte Carlo procedures, both with a fixed seed and identical across methods,
so comparisons are paired.

1. **Plain splits** (S = 1,000 per configuration) on the original data. These give the point
   estimates, the 5th–95th percentile spread (how much one calibration varies), and the
   Monte Carlo confidence interval of the mean false-kill rate. That interval is used for SC-001
   and for marking a method invalid.
2. **Task-cluster bootstrap** (B = 1,000 replicates per configuration). Each replicate resamples
   tasks with replacement and then draws one split. Every copy of a calibration task is dropped
   from the held-out set. These replicates give the 95% percentile intervals for the savings
   metrics and for the paired differences.

**Dataset-level gate statistic**: the mean of the candidate-minus-baseline differences over that
dataset's holdout groups, computed replicate by replicate. Calibration never mixes agents; only
the final differences are averaged.

**Rationale**: the spec requires the interval to reflect that the same runs are reused across
splits. Split-only intervals measure Monte Carlo noise, not data noise, and would make the gate
far too easy to pass. The task bootstrap is the standard fix and costs about the same as the
plain splits.

**Finding to state publicly**: on a fixed dataset, random splits make calibration and test runs
exchangeable by construction. So SC-001 mostly confirms the *implementation*. What a real user
faces is a *shift* when their task mix changes, and Phase 1 doesn't test that.

**Recommendation** (not in scope): a later spec amendment adding a cross-repository split on
SWE-bench, calibrating on some repos and testing on others. It would take about 10 lines and
would answer "does it survive new kinds of tasks?".

## R9. Selection protocol (protecting the headline)

**Decision**:
- `swe-devstral` is the **development group**: all methods and λ values are explored on it, and
  its numbers are marked in-sample.
- The builder records the chosen candidate (method + λ) in `eval/candidate.json` and commits it
  *before* running the final evaluation. The git history then works as a pre-registration.
- The final run evaluates every method on every group (an exploratory ablation table). The
  **gate** uses only the pre-registered candidate on the holdout groups: SWE-bench means
  `swe-gpt5mini`; τ-bench means all four τ groups.

**Rationale**: picking the best of about 20 variants on the same numbers you report inflates
the result. A pre-registered choice tested on agents it never saw also makes a clean story to
tell on camera.

**Alternatives considered**: a random 30% dev split inside every group. Rejected: it shrinks
already small groups (airline has 84 successes), and holding out a whole group is easier to
explain.

## R10. Claude Code transcripts (Story 3)

**Decision**: one loader function. Its rules come from the local structure scan: 13 files,
77,703 records.

- **Files**: `~/.claude/projects/<slug>/<session>.jsonl`. One project slug is one group.
  Sidechain records (`isSidechain: true`) are skipped.
- **Turn start**: a `type: "user"` record that is not `isMeta`, carries a human prompt (string
  content or `text` blocks, no `tool_result`), and is not a local-command output or an interrupt
  marker.
- **Step**: one `tool_use` block, from an assistant record, plus the `tool_result` with the
  matching `tool_use_id` (`is_error` gives the error flag).
- **Interrupted turn**: the turn contains a text block starting with
  `[Request interrupted by user` (51 found locally). An interrupted turn is never a success.
- **Success**: the turn ended (the next prompt or end of file), wasn't interrupted, isn't listed
  in `~/.loopbrake/exclude.txt` (one turn id per line, where the turn id is the uuid of the
  turn's first user record), and wasn't killed (trivially true for past history).
- **Tokens**: as in R3, de-duplicated by `message.id`.
- **Unrecognized records** are counted per type and reported, never raised as errors.
- **Format stability**: the docs call this format internal and unstable, so it's covered by a
  synthetic fixture test (Principle V).

**Local feasibility**: one project has 643 turns with tool use, and one has 63. Every other
project has fewer than 20, so it's reported as observe-only.

## R11. Privacy and licensing

**Decision**:
- All raw and normalized data lives in `~/.loopbrake/data/`, outside the repository.
  Per-run local results go to `~/.loopbrake/eval/`.
- Committed outputs label local groups `local-1`, `local-2`, and so on. The slug-to-label
  mapping stays in `~/.loopbrake/eval/`. Project slugs can reveal employer or client names.
- Test fixtures are synthetic, or trimmed τ-bench runs (MIT).
- SWE-bench S3 trajectories have no stated license. Kill stories from them quote at most an
  80-character command excerpt per step.

**Rationale**: these follow Principle VI. Anonymizing labels closes a leak that "aggregates
only" alone would miss.

## R12. Dependencies and performance

**Decision**:
- **Stdlib only**, for the package and for the eval scripts: `urllib` for the fetch; `json`,
  `random`, `bisect`, `statistics` and `fractions` for the rest.
- **pytest** is the only dev dependency. The project runs through `uv run`.

**Cost model**:
- Score every run once per method, keeping a running-max score list and cumulative tokens.
- Each split then costs about one `bisect` per held-out run.
- Rough total for the final run: 9 methods × 6 groups × 9 (α, n) settings × 2,000 splits
  × ~0.4 ms ≈ 6–7 minutes, within SC-002's 15-minute budget.

**Fallback if over budget**:
1. Run the bootstrap only at the headline setting.
2. Then precompute total savings for each possible τ, since τ is always one of the
   success scores.

**Alternatives considered**: numpy, which is allowed as a dev-only dependency but not needed at
this scale; and parquet groups, which need pyarrow and are deferred (R1).
