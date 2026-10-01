# Feature Specification: Progress Judge Experiment

**Feature Branch**: `002-progress-judge` | **Created**: 2026-10-01 | **Status**: Draft

**Input**: User description: "You plan in the scope". This is the next step chosen after Phase 1's
NO-GO: test whether a small model that judges "did this step move the run forward?" beats the
calibrated step-count rule, under the same guarantee and the same choose-in-advance rules. The
builder left the scope to Claude.

## Background (why this experiment)

Phase 1 found that hand-made stuck signals (repeats, nothing-new output, repeated errors) don't
clearly beat the simple rule "stop runs that go on too long". The numbers:

- **Extra saving over the step-count rule**: +1.5% on SWE-bench, with a 95% interval of
  −9.7% to +13.2%.
- **Simple rule on its own**: about 11% of tokens saved, the same as FailFast's step-count control.
- **FailFast's trained monitor**: 14.6–20.4%. That suggests the missing piece is *understanding*
  what a step did, not counting how it looks.

The constitution (Principle III) allows a small model as an optional extra only after a plateau
like this one. This experiment is that check.

**Words used here**:

| Word | Meaning |
|---|---|
| **Judge** | A fast decision model that reads one step (with a little context) and says how likely it is that the step made progress, and what kind of step it was |
| **Judgment** | One answer from the judge for one step |
| **Net tokens saved** | Tokens saved by stopping runs, minus the tokens the judge itself read and wrote |
| **Stop line, false stop, α, calibration** | Same meaning as in Phase 1 (see specs/001-offline-eval/plan.md) |

## User Scenarios & Testing *(mandatory)*

The user is the LoopBrake builder. They must decide, with evidence, whether a progress judge earns
a place in the product before Phase 2 starts.

### User Story 1 - Measure a progress judge on the development group (Priority: P1)

The builder runs the judge once over every step of the development group (`swe-devstral`) and
stores every judgment. Several stuck scores are built from those judgments and replayed with the
Phase 1 machinery: same splits, same stop-line rule, same metrics. The result is a development
table that puts the judge methods next to the Phase 1 methods. It also shows what the judge cost:
time per step, and tokens it read and wrote.

**Why this priority**: it is the cheapest way to see whether a judge can plausibly beat the step
count. If it can't even do that on the development group, there is no reason to judge the holdout
groups.

**Independent Test**: judge the development group, run the development evaluation, and get a
table with net tokens saved and false stops for each judge method. Running the evaluation again
from the stored judgments gives identical numbers.

**Acceptance Scenarios**:

1. **Given** the development group, **When** the builder starts judging, **Then** every step gets
   one stored judgment. If judging is interrupted, it resumes where it stopped, and no step is
   judged twice.
2. **Given** the stored judgments, **When** the development evaluation runs, **Then** every judge
   method appears with false stops, tokens saved, net tokens saved and judge cost. The Phase 1
   methods appear beside them on the same splits.
3. **Given** the same stored judgments, **When** the evaluation runs twice, **Then** both result
   tables are identical.

---

### User Story 2 - Pre-registered go/no-go on unseen agents (Priority: P2)

The builder chooses one judge method using the development group only. They commit that choice
before any holdout results exist. Only then are the holdout groups judged and evaluated. The
verdict compares the chosen method's **net** tokens saved against the stronger calibrated simple
method (step count or exact repeats), on both datasets, under the same rule as Phase 1. Kill stories
include the judge's own one-line reason.

**Why this priority**: this answers the question that gates Phase 2. It is honest only if the
choice comes before the holdout numbers.

**Independent Test**: with a committed choice, run the final evaluation. A report appears that
starts with GO or NO-GO, gives each dataset's paired difference in net tokens saved with a 95%
interval, and confirms the false-stop limit on every holdout group.

**Acceptance Scenarios**:

1. **Given** no committed choice, **When** the final evaluation is started, **Then** it refuses to
   run.
2. **Given** a committed choice, **When** the final evaluation runs, **Then** the verdict is GO
   only if:
   - on both datasets, the chosen method's net savings beat the stronger simple method with the
     whole 95% interval above zero; and
   - no holdout group goes over its false-stop limit.
3. **Given** the final results, **When** the builder opens the kill stories, **Then** each one shows
   the stop step, the judge's reason at that step, and the last few actions.

---

### User Story 3 - Ask the judge only when it's needed (Priority: P3)

Asking the judge about every step costs time and tokens, and it would slow a live agent. The builder
measures a cheaper variant: the judge is consulted only on steps where the cheap Phase 1 signals
suggest the run might be stuck. The report shows how many judgments this saves, how much of the
full judge's net saving it keeps, and the expected extra delay per agent step if used live.

**Why this priority**: it decides whether a judge is practical inside a live tool (Phase 3 has a
200 ms per-step target). It isn't needed for the go/no-go decision.

**Independent Test**: from stored judgments, evaluate the "only when needed" variant on the
development group. The report shows the share of steps judged, net tokens saved, and the expected
delay per step.

**Acceptance Scenarios**:

1. **Given** stored judgments for every step, **When** the "only when needed" variant is evaluated,
   **Then** it uses only judgments for the steps it would have asked about, and it reports that
   share.
2. **Given** the measured judge time per step, **When** the report is written, **Then** it states
   the expected extra delay per agent step: typical and worst 5%.

---

### Edge Cases

- **Unreadable answer**: the judge's output can't be read (empty, malformed, off-topic). The
  judgment counts as "no opinion", which neither adds to nor reduces stuckness. Such answers are
  counted and reported per group.
- **Judge service errors**: the service is busy, limits the request rate, or fails. Requests are
  retried with growing waits; steps that still fail are counted as "no opinion" and reported.
- **Steps too long for the judge**: a step plus its context is longer than the judge can read. It is
  shortened by one fixed rule (keep the start and the end) that is the same for every method. The
  number of shortened steps is reported.
- **The judge is not fully repeatable**: asking again may give a different answer. Stored judgments
  make the evaluation repeatable anyway. A re-check on a fixed sample of steps reports how often
  the judge agrees with itself.
- **Judge cost larger than savings**: net savings can come out negative. That is reported as is,
  never hidden.
- **Too few successful runs or tasks**: reported as "not enough data", exactly as in Phase 1.
- **Coding and customer-service steps**: one judge setup has to work for both datasets. No separate
  tuning per dataset.

## Requirements *(mandatory)*

### Functional Requirements

**Reuse**

- **FR-001**: The experiment MUST use the Phase 1 data (the same six public groups), the Phase 1
  split rule (at most one calibration run per task), the same stop-line rule, metrics and
  intervals. Phase 1 results and code paths MUST stay unchanged.

**The judge**

- **FR-002**: For each step, the judge MUST read:
  - the step's action and result;
  - the run's task, as given to the agent;
  - at most a fixed number of earlier steps.

  It MUST return a progress value from 0 to 1, and a short reason. The reason is the most likely
  *kind* of step from a fixed list, such as "found something new", "changed code", "repeated an
  earlier action" or "same error again", with its probability.
- **FR-003**: The judge MAY be a hosted service (the builder approved API use on 2026-10-01). Only
  steps from the **public** datasets may be sent to it. The builder's own Claude Code history MUST
  NOT be sent. The service's access key MUST NOT be written into the repository, results or logs.
- **FR-004**: Every judgment MUST be stored together with:
  - the judge's identity and setup;
  - a fingerprint of the exact input;
  - the time it took;
  - the tokens the judge read and wrote.

  Judging MUST be resumable and MUST never judge the same input twice. Evaluations MUST read the
  stored judgments and never call the judge themselves.

**Methods and measurement**

- **FR-005**: Judge methods MUST turn judgments into a stuck score per step, using only steps seen
  so far (no look-ahead). Each judge method MUST be set on the stop line by the Phase 1 rule.
  Methods to test:
  - the judge alone;
  - the judge combined with the step count;
  - the judge combined with the Phase 1 signals.
- **FR-006**: The experiment MUST report **net tokens saved**: tokens saved minus every token the
  judge read and wrote on held-out runs, counted one for one. This is deliberately strict, even
  though judge tokens cost less. Plain tokens saved and the judge's cost MUST also be reported
  separately.
- **FR-007**: The experiment MUST measure judge time per step on the builder's laptop (typical and
  worst 5%). It MUST also re-judge a fixed random sample of 200 steps and report how often the
  answers match the stored ones.

**Protocol**

- **FR-008**: All choices of judge setup and method MUST be made on the development group only. The
  chosen setup and method MUST be recorded and committed before any holdout group is evaluated.
  Holdout groups MUST be judged only with the chosen setup.
- **FR-009**: The verdict MUST follow Phase 1's rule, using net tokens saved:
  - **GO** when, on both datasets, the chosen method beats the stronger calibrated simple method
    with the whole 95% interval above zero, and no holdout group goes over its false-stop limit;
  - **NO-GO** otherwise.
- **FR-010**: The final report MUST also compare the chosen judge method with Phase 1's chosen
  method and with FailFast's published numbers, using Phase 1's caveats.

**Cost-saving variant**

- **FR-011**: The experiment MUST evaluate an "ask only when needed" variant. It consults the judge
  only on steps where the Phase 1 stuck score is at or above a fixed level. That level is chosen on
  the development group, and on other steps the judge's place is filled by "no opinion". It MUST
  report:
  - the share of steps judged;
  - net tokens saved;
  - the expected extra delay per agent step.

**Outputs and privacy**

- **FR-012**: Kill stories MUST include the judge's reason at the stop step. Each public group MUST
  have at least 10 kill stories, or all available if there are fewer.
- **FR-013**: The builder's own Claude Code history is out of scope for this feature. Judging it
  with a hosted judge would send private content to a third party (constitution Principle VI).
- **FR-014**: Results MUST be committed with the command that reproduces them from the stored
  judgments. Any later change to how results are computed MUST be logged with before-and-after
  numbers, as in Phase 1's CORRECTIONS.md.

### Key Entities

- **Judge setup**: which model, the instruction it is given, how many earlier steps it sees, and
  how long inputs are shortened. A setup has a version, so stored judgments always say which setup
  made them.
- **Judgment**: one answer for one step. It has:
  - the setup version and an input fingerprint;
  - the progress value (0–1) or "no opinion";
  - the reason;
  - the time taken and the judge tokens used.
- **Judge method**: a way of turning judgments, and optionally the Phase 1 signals and step count,
  into a stuck score per step.
- **Net result row**: a Phase 1 result row plus net tokens saved, judge tokens as a share of agent
  tokens, and the share of steps judged.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On every holdout group, the chosen judge method's false-stop rate at α = 5% is within
  the limit: its 95% interval includes 5% or lies below it.
- **SC-002**: The experiment ends with an explicit GO or NO-GO, based on net tokens saved against
  the stronger calibrated simple method on both datasets.
- **SC-003**: Judging every step of the six public groups once finishes within 12 hours of
  unattended running on the builder's laptop. Judgments are never repeated.
- **SC-004**: Re-running the evaluation from stored judgments gives identical results. On a sample
  of 200 re-judged steps, the judge agrees with its stored answer at least 95% of the time, or the
  real rate is reported.
- **SC-005** (target, not a pass condition): the chosen method's net tokens saved on `swe-gpt5mini`
  at 5% false stops reach at least 20.4%, the FailFast bar.
- **SC-006** (target): the "ask only when needed" variant judges at most half of all steps and keeps
  at least 80% of the full judge's net savings.
- **SC-007**: The report states the expected extra delay per agent step (typical and worst 5%), so
  Phase 3 can tell whether its 200 ms target is reachable.
- **SC-008**: Only public-dataset steps are ever sent to the judge, and the access key appears in no
  committed file. This is checked by inspecting the judging inputs and searching the repository for
  the key.

## Assumptions

- **Judge**: Jev, Typesafe's hosted decision model, pinned to version `jev-1.13.0`. It returns a
  yes/no probability, and choice probabilities, for typed questions about a piece of text. Laya was
  considered and rejected; see research.md.
- **No training**: the judge is used as is, with an instruction (zero-shot). Training or tuning a
  dedicated monitor, as FailFast did, is a later option if this fails.
- **Same data as Phase 1**: there are no new datasets. If judging every step doesn't fit in the time
  budget, a fixed random subset of runs per group is used. It's the same subset for every method,
  and it's documented.
- **Strict cost accounting**: judge tokens count one for one against savings. If the judge still
  wins under that rule, it wins under any fairer rule.
- **The bar stays the same**: the calibrated step count, or exact repeats if stronger, is the method
  to beat, as in Phase 1.
- **Out of scope**:
  - the Python package (Phase 2);
  - any live use inside a running agent (Phase 3);
  - dashboards (Phase 4);
  - training a monitor;
  - judging the builder's own Claude Code history.
