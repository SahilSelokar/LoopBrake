# Feature Specification: Offline Evaluation Experiment

**Feature Branch**: none (no git repository yet). Feature directory: `specs/001-offline-eval`

**Created**: 2026-10-01

**Status**: Implemented. Verdict NO-GO (2026-10-01); see `eval/results/results.md`.

**Input**: User description: "" (empty). Inferred from the agreed LoopBrake plan, Phase 1:
"Offline experiment on recorded agent runs. Calibrate a kill threshold on past successful runs.
Measure how many tokens it saves on failed runs at a guaranteed false-kill rate. Compare against
the exact-repeat baseline and the FailFast bar (20.4% at 5%)."

## User Scenarios & Testing *(mandatory)*

The primary user is the LoopBrake builder, who must decide whether the idea works before any
package code is written (constitution, Experiment gate). The secondary audience is skeptical
viewers and agent developers. They need to check the headline claim from published numbers.

### User Story 1 - Measure the calibrated baseline on public agent runs (Priority: P1)

The builder points the evaluation at a public collection of recorded agent runs, each labelled as
succeeded or failed. The evaluation takes the existing exact-repeat rule and turns it into a score.
It sets the kill threshold from a small random sample of successful runs, then replays the
held-out runs step by step, as if live. It repeats this over many random samples. The output is a
results table:

- how often held-out successful runs were killed (false-kill rate);
- what share of tokens it saved on failed runs.

The same table also shows the fixed, uncalibrated rule, so the cost of skipping calibration is
visible.

**Why this priority**: this is the measuring stick. It checks that the false-kill guarantee holds
on real data, and it sets the baseline number every later idea must beat. Without it, nothing else
in the project can be judged.

**Independent Test**: run the evaluation on one public dataset. A results table appears. Its
measured false-kill rate is at or below the chosen α. Its numbers are identical on a rerun.

**Acceptance Scenarios**:

1. **Given** a labelled public dataset and α = 5% with 20 calibration runs, **When** the builder
   runs the evaluation, **Then** the table shows, per agent:
   - the mean false-kill rate over all random splits, with its 95% interval;
   - the mean tokens saved, with its 95% interval;
   - the number of runs used.
2. **Given** the same inputs, **When** the evaluation is run twice, **Then** both results tables
   are identical.
3. **Given** the fixed, uncalibrated exact-repeat rule, **When** it is evaluated on the same
   held-out runs, **Then** its false-kill rate and tokens saved appear in the same table, next to
   the calibrated version.

---

### User Story 2 - Beat the baseline with better signals and get a go/no-go verdict (Priority: P2)

The builder adds candidate stuck signals and evaluates each one alone and in combination. Every
candidate is calibrated exactly like the baseline. The candidate signals are:

- **fuzzy repeats**: near-identical actions;
- **no new information**: a step whose result adds nothing the run hasn't already seen;
- **repeated errors**: the same error coming back.

The evaluation then compares each candidate to the calibrated baseline on the same random splits
and states a verdict for the Experiment gate:

- **go**: a candidate beats the baseline on every public dataset;
- **no-go**: no candidate beats it.

**Why this priority**: the constitution blocks Phase 2 (core package) until a signal set beats the
calibrated baseline. This story produces that decision.

**Independent Test**: with the baseline from Story 1 in place, run the comparison on one dataset.
It reports a per-candidate difference against the baseline, with a 95% interval, plus an explicit
go or no-go.

**Acceptance Scenarios**:

1. **Given** the baseline results and at least one candidate signal, **When** the comparison
   runs, **Then** each candidate's tokens saved is reported against the baseline as a paired
   difference over the same splits, with a 95% interval.
2. **Given** one candidate, chosen on a development group and frozen before any holdout numbers
   are seen, **When** every public dataset shows that candidate's paired difference with its 95%
   interval entirely above zero on the holdout groups, **Then** the verdict reads "go" and names
   the candidate. Otherwise the verdict reads "no-go" and shows how far short it fell.
3. **Given** any candidate is evaluated, **When** the 95% confidence interval of its mean
   false-kill rate lies entirely above α on any dataset, **Then** the candidate is marked invalid
   and cannot produce a "go".
4. **Given** a failed run that a candidate would kill, **When** the builder asks for its kill
   story, **Then** the evaluation shows the step where the run would have stopped, a readable
   reason naming the signals that fired, and the tokens saved.

---

### User Story 3 - Run the same evaluation on my own Claude Code history (Priority: P3)

The builder runs the same evaluation on their own local Claude Code session history, where one
user turn counts as one run. Success labels come from the agreed automatic proxy. All of this
happens on the builder's machine. Only aggregate numbers may leave it. This shows whether the
approach carries over to the agent that Phase 3 targets.

**Why this priority**: it previews the real product setting and checks whether the automatic
success labels behave sensibly. It isn't needed for the gate, which rests on public data.

**Independent Test**: point the evaluation at the local Claude Code history for one project. It
produces the same kind of table as Story 1. No transcript content appears in any output meant
for committing.

**Acceptance Scenarios**:

1. **Given** a local project history with at least 20 turns labelled successful, **When** the
   evaluation runs, **Then** the table reports false-kill rate and tokens saved for that project.
2. **Given** a turn the builder excluded, **When** calibration samples successful runs, **Then**
   that turn is never used.
3. **Given** the results are written out, **When** the committed output is inspected, **Then** it
   contains only aggregate numbers. Per-run details and any transcript text stay outside the
   project.
4. **Given** history records the evaluation does not recognise, **When** the evaluation runs,
   **Then** it reports how many records it skipped and why, rather than failing silently.

---

### Edge Cases

- **Too few successful runs** for the chosen calibration size and α (for example fewer than 19
  at α = 5%): that configuration is reported as "insufficient data / observe-only" and never as a
  result. This matches the product, which never kills in that state.
- **Tied scores** (common with counting signals): the threshold rule stays conservative. Ties
  never make the false-kill rate exceed α.
- **Kill on the last step**: the run counts as killed, and its tokens saved are zero.
- **Very short runs** (one or two steps) are scored like any other run. They are never dropped
  silently.
- **Runs with no token counts**: tokens are estimated from the size of each step's text. The
  same estimate is used for every method, so comparisons stay fair. The table says when an
  estimate was used.
- **Malformed or unlabelled runs** are skipped. They are counted per dataset and shown in the
  table.
- **Failures that never look stuck** (the agent confidently finishes with a wrong answer) can't
  be saved by any stop rule. They stay in the denominator, so savings aren't inflated.
- **A successful run that gets killed**: the work it loses is reported separately from savings.
- **Several runs of the same task** (τ-bench repeats each task 4–8 times): if any run of a task
  is used for calibration, none of that task's runs may appear in the held-out set.
- **One agent, many task types**: calibration and testing always use runs from the same agent
  on the same dataset. Agents are never mixed in one calibration set.

## Requirements *(mandatory)*

### Functional Requirements

**Data**

- **FR-001**: The evaluation MUST read recorded agent runs from public datasets with
  success/failure labels: SWE-bench agent trajectories for at least two different agents, and
  τ-bench tool-use trajectories as a non-coding dataset. It MUST treat each recorded trajectory as
  one run and each action with its result as one step. (MAST-Data was dropped during research:
  its traces carry no success label. See research.md.)
- **FR-002**: The evaluation MUST read the builder's local Claude Code session history. One user
  turn counts as one run. A turn counts as successful when it ended normally, was not
  interrupted by the user, and was not killed, unless the builder has excluded it.
- **FR-003**: The evaluation MUST group runs by dataset and agent. It MUST calibrate and test
  only within a group.

**Scoring and calibration**

- **FR-004**: Every method MUST score a run step by step, using only the steps seen so far
  (no look-ahead). The kill decision at step t MUST depend only on steps 1..t.
- **FR-005**: Every method MUST set its kill threshold from a random sample of n successful runs
  in the group, by the constitution's rule (Principle I). The run score is the highest step
  score, and the threshold is the ⌈(n+1)(1−α)⌉-th smallest calibration score. When that rank
  exceeds n, the method MUST NOT kill.
- **FR-006**: The evaluation MUST include the existing exact-repeat rule in two forms: as fixed
  (uncalibrated) and as a calibrated score. Both form the baseline.
- **FR-007**: The evaluation MUST support candidate signals for fuzzy repeats, no new
  information and repeated errors, each alone and combined. Every candidate is calibrated by the
  same rule as the baseline.

**Splits and metrics**

- **FR-008**: For each group, method, α and calibration size, the evaluation MUST repeat the
  random split (calibration sample vs held-out runs) at least 500 times with a fixed seed. The
  same splits MUST be used for every method.
- **FR-009**: For each configuration, the evaluation MUST report:
  - the false-kill rate: the share of held-out successful runs killed;
  - tokens saved on failed runs: tokens after the kill point divided by all tokens of held-out
    failed runs;
  - tokens saved overall: tokens after the kill point on any killed run, divided by all held-out
    tokens;
  - the work lost on falsely killed runs;
  - the median step at which failed runs are killed;
  - run counts.

  Each value MUST come with three numbers: its mean across splits, a 95% confidence interval for
  that mean, and the 5th–95th percentile spread across splits (how much a single calibration can
  vary).
- **FR-010**: The evaluation MUST run at α ∈ {1%, 5%, 10%} and calibration size n ∈ {20, 50, 100}
  wherever the group has enough successful runs. α = 5%, n = 20 is the headline setting.
- **FR-011**: The evaluation MUST compare each candidate to the calibrated baseline as a paired
  difference over identical splits. It MUST output a go or no-go verdict as defined in User
  Story 2. The gate candidate MUST be fixed on a development group and recorded before holdout
  groups are evaluated. A method MUST be marked invalid when the 95% confidence interval of its mean
  false-kill rate lies entirely above α.

**Outputs**

- **FR-012**: For any killed run, the evaluation MUST be able to produce a kill story: the step
  where it stopped, a readable reason naming the signals that fired, and the tokens saved.
  Kill stories are produced for public datasets only. For local history, they are shown to the
  builder and never written to committed outputs.
- **FR-013**: All results MUST be reproducible from the raw datasets with one documented step,
  and give identical numbers on rerun. The results table and the step that produces it MUST be
  committed together (Principle IV).
- **FR-014**: Outputs meant for committing MUST contain only aggregate numbers and public-dataset
  content. Nothing derived from local history beyond aggregates may be written inside the
  project (Principle VI).
- **FR-015**: The evaluation MUST report how many runs or records it skipped per dataset, and
  why.
- **FR-016**: The evaluation MUST make no network calls while running. Datasets are fetched once,
  beforehand, as a separate documented step.

### Key Entities

- **Run**: one recorded agent attempt at one task. It has an agent, a dataset, a success label
  and an ordered list of steps. For Claude Code history, a run is one user turn.
- **Step**: one action the agent took plus the result it got back. It has a token count, which
  is measured or estimated.
- **Method**: a way of scoring steps. Examples are the fixed baseline, the calibrated baseline,
  or a candidate signal set. Each method can explain which signals drove its score.
- **Group**: all runs from one agent on one dataset. This is the unit within which calibration
  and testing happen.
- **Split**: one random division of a group into a calibration sample of successful runs and
  the held-out runs.
- **Threshold**: the kill level computed from one calibration sample for one method and one α.
- **Kill event**: the step where a run would have been stopped, with its reason and the tokens
  saved.
- **Result row**: the aggregate metrics for one group, method, α and calibration size.
- **Verdict**: go or no-go for the Experiment gate, with the candidate it rests on.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every calibrated method on every public group, the 95% confidence interval of
  the mean false-kill rate at α = 5% includes 5% or lies below it. This shows the guarantee holds
  on real data.
- **SC-002**: The builder gets the complete results table for all public datasets in under
  15 minutes on a laptop, from already-downloaded data.
- **SC-003**: Rerunning the evaluation produces identical numbers.
- **SC-004**: The experiment ends with an explicit go or no-go verdict for Phase 2, backed by the
  paired comparison against the calibrated baseline on every public dataset.
- **SC-005** (target, not a pass condition): the best valid candidate saves at least 20.4% of
  tokens at a 5% false-kill rate on SWE-bench runs, matching the FailFast bar.
- **SC-006**: For each public dataset, at least 10 kill stories can be produced. Each is short
  enough to read aloud in under 15 seconds, so it's ready to use as reel material.
- **SC-007**: An inspection of all committed outputs finds no transcript content from local
  history.
- **SC-008**: The table shows how the fixed, uncalibrated rule's false-kill rate compares with α.
  This makes the case for calibration with real numbers.

## Assumptions

- **Datasets** (confirmed in research):
  - **SWE-bench Verified**: mini-SWE-agent runs for two models, about 280 resolved out of 500
    each, with per-step token usage recorded.
  - **τ-bench**: four model/domain groups, each with a 0/1 reward per run.

  Datasets are downloaded once and kept outside the repository. Only small excerpts from
  permissively licensed public data may be committed, as test fixtures.
- **Baseline**: the existing exact-repeat rule is the one in `liveness.py`: identical action
  repeated 3 times, or a 20-step cap. The 20-step cap is expected to kill most long, successful
  coding runs. That is a finding to report, not a defect to fix.
- **Token counts**: when a dataset doesn't record tokens per step, they are estimated from text
  size. Absolute savings may then be approximate. Comparisons between methods stay fair, because
  every method uses the same estimate.
- **FailFast comparison** (resolved in research): FailFast measures savings over all runs, so
  "tokens saved overall" is the headline. Both definitions are always reported. The comparison
  is labelled indicative, because FailFast used different models and fitted its 5% threshold on
  its evaluation fold rather than on held-out data.
- **Intervals**: the plan phase chooses how confidence intervals are computed. The method must
  account for the same runs being reused across splits; otherwise the intervals come out too
  narrow and the gate becomes too easy to pass.
- **Claude Code labels**: success uses the automatic proxy agreed in the constitution. The
  guarantee on local history is approximate wherever a turn finished but was actually wrong.
- **Out of scope**:
  - a System 1 or LLM-based judge (conditional on an evaluation plateau, per the constitution);
  - any live killing of a running agent;
  - the reusable package interface (Phase 2), the Claude Code plugin (Phase 3), observability
    (dashboard and OpenTelemetry export, Phase 4) and the launch demo agent (Phase 5);
  - warn-first feedback to the agent.
- **Setting**: the evaluation runs on one laptop, offline once data is downloaded. The builder is
  the only operator.
