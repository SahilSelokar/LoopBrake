# Feature Specification: Core Package (LoopBrake v1)

**Feature Branch**: `003-core-package` | **Created**: 2026-10-01 | **Status**: Implemented (v0.1.0, CI green, 2026-10-01). The PyPI release waits on the builder's one-time PyPI setup (tasks T019–T020).

**Input**: User description: "" (empty). Taken from the decision of 2026-10-01 (constitution 2.2.0):
"v1 ships the calibrated step budget: stop a run that goes on longer than a stop line set from
your own past successful runs, with the false-stop guarantee. The stuck signals only explain
stops." This is roadmap Phase 2.

## Background

Two pre-registered experiments showed that, on agents a method was not tuned on, nothing tested
beat "stop runs that go on too long", provided the length limit is set the right way. That way is
LoopBrake's: from the user's own past successful runs, with a guaranteed limit on how often a good
run gets stopped. v1 turns that measured result into something people can install.

**Words used here** (same as the experiments):

| Word | Meaning |
|---|---|
| **Run** | One attempt by an agent at one task (for Claude Code, one user turn) |
| **Step** | One action the agent takes plus the result it gets back |
| **Stop line** | How many steps a run may take before LoopBrake stops it, set from past successful runs |
| **False stop** | Stopping a run that would have succeeded |
| **α** | The highest false-stop rate the user accepts (default 5 in 100) |
| **Calibration** | Setting the stop line from past successful runs, by the constitution's rule (Principle I) |
| **Watch-only** | LoopBrake records and explains, but never stops: too few past runs to set a stop line |

## User Scenarios & Testing *(mandatory)*

The users are developers who run AI agents, either in their own code or with Claude's agent
toolkit. Later phases (the Claude Code plugin, the dashboard) build on this package.

### User Story 1 - Put brakes on my own agent in a few lines (Priority: P1)

A developer has an agent loop. They add LoopBrake: once per run they start a brake, and after every
step they report what happened. LoopBrake answers "continue" or "stop", and when it says stop it
gives a short reason the developer can show or log. For example: "stopped at step 61: past the
stop line of 58 set from your 40 past successful runs; last 5 steps: same command repeated, nothing
new in the output." If the developer has no stop line yet, LoopBrake only watches: it never stops,
but it still records each run.

**Why this priority**: this is the product. Everything else (calibration tools, plugin, dashboard)
serves it.

**Independent Test**: with a stop line in place, feed a recorded failing run through the brake step
by step. It says stop at exactly the step the experiment reported, with a readable reason. A
successful short run is never stopped.

**Acceptance Scenarios**:

1. **Given** a stop line of N steps, **When** a run reaches step N + 1, **Then** the brake says
   stop. The reason names the step, the stop line and how many past runs set it, and adds what the
   stuck signals saw in the last few steps.
2. **Given** a run that finishes within N steps, **When** it ends, **Then** it was never stopped,
   and it is recorded as finished.
3. **Given** no stop line, or too few past successful runs for the chosen α, **When** a run goes on
   for any length, **Then** the brake never says stop and reports that it is watch-only.
4. **Given** a brake that already said stop, **When** more steps are reported, **Then** it keeps
   saying stop. It never flips back to continue.
5. **Given** anything goes wrong inside LoopBrake (it can't write its record, the calibration file
   is damaged), **When** the agent reports a step, **Then** the agent is never crashed or stopped
   because of it. LoopBrake reports the problem once and acts as watch-only.

---

### User Story 2 - Set my stop line from my own past runs, and see how it's doing (Priority: P2)

From a terminal, the developer builds their stop line from past runs. These can be recorded agent
runs in LoopBrake's common runs format, or their own Claude Code history for one project. Each
past task counts once. LoopBrake shows the result: the stop line, how many successful runs it used,
α, and whether that's enough. Later they can check status:
- how many runs were watched;
- how many were stopped;
- how many stops the developer marked as mistakes, against how many α allows.

They can mark a stop as a mistake, and that feeds the status.

**Why this priority**: without a stop line, the brake only watches. Status and mistake-marking are
how the guarantee is checked in real use: tokens saved can't be measured live, but false stops can
be counted.

**Independent Test**: point calibration at a runs file with at least 19 successful tasks and get a
stop line that matches the experiment's rule. With 18, get "watch-only". Marking a stop as a
mistake changes the status count.

**Acceptance Scenarios**:

1. **Given** a runs file with M successful tasks (one run counted per task), **When** the developer
   calibrates at α = 5%, **Then** the stop line equals the k-th smallest run length among them
   (constitution Principle I). The record keeps α, M, k, the stop line, the source, the date and
   the LoopBrake version.
2. **Given** fewer successful tasks than α needs (for example 18 at 5%), **When** they calibrate,
   **Then** the result says watch-only and explains how many more successful runs are needed.
3. **Given** one Claude Code project's history, **When** they calibrate from it, **Then** successful
   turns are counted by the experiments' rule (ended normally, not interrupted, not excluded), and
   no text from the history is copied into the calibration record.
4. **Given** stopped runs, **When** the developer marks one as a mistake and asks for status, **Then**
   the status shows the mistaken stops against the allowed number (α × runs watched).

---

### User Story 3 - Use it with Claude's agent toolkit (Priority: P3)

A developer builds agents with Claude's agent toolkit. They add LoopBrake as a hook in a few lines.
The toolkit's agent is stopped, with LoopBrake's reason, when the run passes the stop line.

**Why this priority**: it shows the package's "thin adapter" design on a real framework. It also
rehearses the Claude Code plugin (Phase 3), which uses the same kind of hook.

**Independent Test**: run a small scripted toolkit agent that keeps calling a tool. With a stop
line of 5, it is stopped after step 6, and the stop reason reaches the agent's output.

**Acceptance Scenarios**:

1. **Given** a toolkit agent with the LoopBrake hook and a stop line, **When** the agent passes the
   stop line, **Then** the toolkit stops the agent, and the reason is visible.
2. **Given** the same agent in watch-only mode, **When** it runs, **Then** it is never stopped, and
   its run is recorded.

---

### User Story 4 - Install it with one command from PyPI (Priority: P2)

A developer who has never seen the repository runs `pip install loopbrake` (or `uv add loopbrake`)
and gets the same package, command line included. Each new version reaches PyPI when the builder
creates a version tag on GitHub. No upload password or token is involved.

**Why this priority**: "a few lines to add to any agent" only works if installing is one command.
PyPI is where Python developers look first.

**Independent Test**: after the first release, `pip install loopbrake==0.1.0` in a fresh
environment works, and `loopbrake --version` prints `loopbrake 0.1.0`.

**Acceptance Scenarios**:

1. **Given** the builder pushes the tag `v0.1.0` and the package version is 0.1.0, **When** the
   release workflow runs, **Then** version 0.1.0 appears on PyPI, with the README as its description
   and the MIT license.
2. **Given** a tag that doesn't match the package version, **When** the workflow runs, **Then** it
   refuses to publish and says why.
3. **Given** the published package, **When** someone inspects it, **Then** it contains only the
   public package: no experiment code, data, results or anything private.

---

### Edge Cases

- **No calibration file, or a damaged one**: watch-only, with one clear notice. The agent is never
  crashed.
- **Several runs at once** (parallel agents or sessions): each run has its own brake and its own
  record. They never mix.
- **Token counts unknown**: the stop rule doesn't need them, so they are recorded when given and
  left blank otherwise.
- **Very large step results**: only a short excerpt of each action goes into the local record, never
  the full result.
- **Calibration source mixes projects or agents**: allowed, but calibration warns. The guarantee
  only holds when new runs look like the past ones.
- **The stop line changes** (recalibration): runs already started keep the stop line they began with.
  New runs use the new one. The record says which stop line each run used.
- **Steps reported after a run ended**: ignored and counted, never an error.

## Requirements *(mandatory)*

### Functional Requirements

**The brake**

- **FR-001**: The stop rule MUST be the calibrated step budget: stop when the run's step count goes
  past the stop line. The decision MUST use the very scoring and stop-line code the experiments
  certified, unchanged (constitution Principle II).
- **FR-002**: For every reported step, the brake MUST answer continue or stop. Once it says stop, it
  MUST keep saying stop for that run.
- **FR-003**: Every stop MUST come with a readable reason. The reason names the stop step, the stop
  line and the number of past runs behind it. It adds what the stuck signals saw in the last 5 steps
  (repeats, nothing new, same error again). The signals MUST NOT influence whether to stop
  (constitution 2.2.0).
- **FR-004**: With no stop line, or with fewer successful past runs than α needs, the brake MUST be
  watch-only. It never stops, and it says so.
- **FR-005**: No failure inside LoopBrake may crash or stop the host agent. Errors are reported once,
  and the brake falls back to watch-only.

**Calibration**

- **FR-006**: Calibration MUST accept two sources:
  - recorded runs in LoopBrake's common runs format;
  - one project's Claude Code history, using the experiments' success rule and exclude list.

  It MUST count at most one successful run per task. It MUST compute the stop line by the
  constitution's rule, at a chosen α (default 5%).
- **FR-007**: A calibration record MUST hold:
  - α, the number of successful runs used, k, and the stop line (or "watch-only");
  - a fingerprint of the source, the date and the LoopBrake version.

  It MUST NOT hold any text from the source.

**Records, status and feedback**

- **FR-008**: Each run MUST be recorded locally as events: run start (with the stop line in force),
  each step (step number, tool name, a short action excerpt, token count if given), stop (with
  reason), run end (finished, stopped or interrupted), and feedback. The format follows the roadmap's
  shared event contract, with a version number. LoopBrake MUST NOT send anything over the network
  (constitution Principle VI).
- **FR-009**: A status view MUST show:
  - the stop line in force and its source;
  - runs watched, runs stopped, and runs stopped then marked mistaken;
  - the false-stop allowance (α × runs watched).
- **FR-010**: The developer MUST be able to mark a stopped run as a mistake, or exclude a past run
  from future calibration.
- **FR-011**: A replay command MUST run recorded runs through the brake and report where each would
  stop. That makes the "same decision live and offline" check (Principle II) something anyone can
  run.

**Package**

- **FR-012**: The package MUST install with no other packages (constitution Principle III). After
  installing, a version check and the commands MUST work.
- **FR-013**: Adding brakes to a custom agent loop MUST take at most 5 lines, shown in a runnable
  example in the README.
- **FR-014**: An adapter for Claude's agent toolkit MUST let a toolkit agent be stopped by LoopBrake.
  It is a thin adapter with no stop logic of its own (constitution Principle V).
- **FR-015**: Every change pushed to the repository MUST have the test suite run automatically.

**Releases and open core**

- **FR-016**: Pushing a version tag MUST publish that version to PyPI, using trusted publishing
  between the GitHub repository and PyPI. No upload token is stored. A tag that doesn't match the
  package version MUST NOT publish.
- **FR-017**: The published package MUST contain only the `loopbrake` library, its command line,
  the README and the license. It contains no evaluation code, data, results or private code
  (constitution "Open core").

### Key Entities

- **Brake**: one per run. It holds the stop line in force, the steps seen so far, and whether it has
  already said stop.
- **Decision**: continue or stop, the step number, and the reason (for stops).
- **Calibration record**:
  - α, the number of successful runs used, k, and the stop line (or watch-only);
  - the method (`steps`), a source fingerprint, the date and the version.

  It holds no source text.
- **Run record**: the event lines for one run (start, steps, stop, end, feedback), kept locally.
- **Status**: counts from the run records plus the calibration in force, including mistaken stops
  against the allowance.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Fed step by step through the brake at the same stop line, every run in the six public
  groups is stopped at exactly the step the Phase 1 evaluation reports, or not stopped exactly when
  it reports none. That's 100% agreement.
- **SC-002**: A developer adds brakes to an agent loop with at most 5 new lines, by following the
  README example. The example runs as written.
- **SC-003**: Deciding one step adds less than 10 milliseconds for runs of up to 250 steps, at the
  95th percentile on a laptop.
- **SC-004**: From a fresh install to the first brake decision takes under 1 minute, with no other
  packages installed.
- **SC-005**: In tests that break LoopBrake on purpose (record folder not writable, calibration file
  damaged, an internal error), the host agent completes its run every time.
- **SC-006**: Calibrating from 19 or more successful tasks at α = 5% gives a stop line identical to
  the experiments' rule. With 18 or fewer, it gives watch-only.
- **SC-007**: Nothing in the package opens a network connection. A test that blocks all network
  access runs the full brake, calibration and status flow successfully.
- **SC-008**: In a scripted scenario (20 runs watched, 3 stopped, 1 marked a mistake, α = 5%), the
  status shows 1 mistaken stop against an allowance of 1.
- **SC-009**: Within 10 minutes of pushing the `v0.1.0` tag, `pip install loopbrake==0.1.0` works in a
  fresh environment. The installed files contain only the library, its command line and its
  metadata.

## Assumptions

- **Who it's for first**: Python agents. Other languages can come later through the same event
  format.
- **Claude Code**: the package's calibration can read Claude Code history now, but stopping live
  Claude Code sessions (the hook and plugin) is Phase 3.
- **Default α**: 5%. The user can choose another.
- **Calibration size**: by default, all successful runs (one per task) in the chosen source. More
  runs give a tighter stop line (the experiments' "price of the guarantee" table).
- **Publishing**: in scope since 2026-10-01 (US4). The builder makes a one-time "trusted publisher"
  setup on pypi.org, which needs their account. Everything after that is automatic.
- **Open core**: everything in this feature is public (MIT). Any private, paid features come later,
  as separate hosted services (constitution 2.3.0).
- **Out of scope**:
  - the Claude Code plugin and live hook (Phase 3);
  - the dashboard and telemetry export (Phase 4);
  - the progress judge;
  - any stop signal other than the step budget (constitution 2.2.0 signal gate).
