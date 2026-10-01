# Feature Specification: Claude Code Plugin

**Feature Branch**: `004-claude-code-plugin` | **Created**: 2026-10-01 | **Status**: Draft

**Input**: User description: "" (empty; started from `/speckit-plan` after Phase 2 shipped). This is
roadmap Phase 3: "Zero-friction install for Claude Code users: stop stuck sessions live,
calibrated on your own history."

## Background

LoopBrake v0.1.0 (Phase 2) is on PyPI. It stops a run once it passes a stop line set from your own
past successful runs, and it can already read Claude Code history to set that line. This feature
puts it inside Claude Code itself:
- each user prompt starts a run;
- each tool call is a step;
- when a turn passes the stop line, Claude stops and shows why.

**Words used here**: as in Phase 2. A **turn** is everything Claude does in answer to one prompt;
it is one run. A **step** is one tool call made by the main agent. Tool calls made inside subagents
don't count, which matches how calibration counts.

## User Scenarios & Testing *(mandatory)*

The users are Claude Code users who want runaway turns stopped before they burn time and tokens.

### User Story 1 - Stuck turns get stopped, live (Priority: P1)

A user installs the plugin and sets a stop line for their project. From then on, when a Claude Code
turn goes past the stop line, Claude stops working on that turn, and the user sees LoopBrake's
reason. For example: "stopped at step 39: past the stop line of 38 steps set from your 898 past
successful turns; repeating in 5 of last 5 steps." The user can then redirect Claude. Without a stop
line, the plugin only watches and records.

**Why this priority**: this is the whole point of the plugin. Everything else supports it.

**Independent Test**: with a stop line of 3 for a test project, ask Claude to run a harmless
command 10 times in one turn. The turn stops after the 4th tool call, with the reason visible.

**Acceptance Scenarios**:

1. **Given** a stop line of N for this project, **When** a turn makes its (N + 1)th main-agent tool
   call, **Then** Claude stops the turn and the reason is shown to the user.
2. **Given** a turn that finishes within N tool calls, **When** it ends, **Then** nothing is
   stopped, and the turn is recorded as finished.
3. **Given** no stop line yet, **When** turns run, **Then** nothing is ever stopped, and each turn
   is recorded.
4. **Given** a new prompt after a stop, **When** the user continues, **Then** counting starts again
   from zero for the new turn.
5. **Given** anything goes wrong in the plugin (its command can't be found or is slow, a file is
   damaged), **When** Claude uses tools, **Then** Claude carries on normally. The plugin never
   blocks or stops a turn because of its own problem.

---

### User Story 2 - Set up and manage it from inside Claude Code (Priority: P2)

From inside Claude Code, the user runs one command to set this project's stop line from its own
past turns, and sees the result. They can ask for status, which shows the stop line, turns watched,
turns stopped, and stops they marked as mistakes against the allowance. They can mark the last stop
as a mistake.

**Why this priority**: setup should take seconds, without leaving Claude Code or knowing where
history files live.

**Independent Test**: in a project with at least 19 successful past turns, run the calibrate
command and get a stop line. In a project with fewer, get "watch-only, need X more". Status shows
the counts. Marking the last stop as a mistake raises the mistaken count by one.

**Acceptance Scenarios**:

1. **Given** a project with enough history, **When** the user runs the calibrate command,
   **Then** the project's stop line is set from that project's own turns, and the result is
   reported in one line.
2. **Given** a stopped turn, **When** the user marks it a mistake, **Then** status counts it, and
   future calibration counts that turn as a good turn longer than any stop line.
3. **Given** two different projects, **When** each is calibrated, **Then** each has its own stop
   line, and they never mix.

---

### User Story 3 - See the brake at a glance (Priority: P3)

The user adds one documented line to their Claude Code settings. The status line then shows the
current turn's step count against the stop line, for example `brake 12/38`, or `brake 12 (watching)`
when there is none.

**Why this priority**: it makes the brake visible, and it films well, but it's optional.

**Independent Test**: with the status line set up, a turn's count rises with each tool call and
resets on a new prompt.

**Acceptance Scenarios**:

1. **Given** the status line is set up, **When** a turn makes tool calls, **Then** the shown count
   matches the number of steps so far, with the project's stop line next to it.

---

### Edge Cases

- **Subagents**: their tool calls are not counted, matching calibration, which ignores subagent
  transcripts.
- **Parallel tool calls**: each counts as one step, matching calibration.
- **Interrupted turns**: when the user presses Esc, the turn ends as interrupted, and the next
  prompt starts fresh.
- **Several Claude Code sessions at once**: each session counts its own turns.
- **Resumed sessions**: the first prompt after a resume starts a new turn.
- **The `loopbrake` command can't run** (uv missing, no internet on the first install): the hook
  fails silently from Claude's point of view. Status then shows that no turns were recorded for this
  project, with a hint that the hooks may not be running.
- **Projects with the same folder name in different places**: kept apart.
- **Mid-turn events**: in calibration, automatic compaction, prompts typed while Claude works, and
  background task notifications that arrive mid-turn stay part of the running turn. Live,
  compaction and notifications do too. A typed prompt may start a new live turn, if Claude Code
  reports it as a prompt. That can only make the live count lower, so the stop comes later.
- **A background task wakes Claude after a turn ended**: that work is its own turn, both live and
  in calibration.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Each main-agent tool call in a turn MUST count as one step.
  - **Turn boundaries**: they MUST follow the constitution's rule (2.4.0, "Turns"). A turn starts at
    a prompt, or at the first tool call after Claude stopped. It ends when Claude stops, or when a
    new prompt arrives.
  - **Calibration**: it MUST cut past turns at the same boundaries.
  - **Counts**: for the same turn, the live count MUST never be higher than calibration's. A lower
    count can only stop later.
- **FR-002**: When a turn's step count passes the project's stop line, the plugin MUST stop the turn
  and show LoopBrake's reason. The decision MUST come from the Phase 2 brake (the step-budget
  rule), unchanged.
- **FR-003**: Without a stop line, the plugin MUST only watch and record. It never stops.
- **FR-004**: No failure in the plugin may block, delay beyond its time limit, or stop Claude's work.
- **FR-005**: The plugin's work after each tool call MUST add at most 200 ms (95th percentile) on the
  builder's laptop, an M3 Pro (constitution Principle III).
- **FR-006**: One command inside Claude Code MUST set the current project's stop line from that
  project's own history, and report the result.
- **FR-007**: Commands inside Claude Code MUST show status, mark the last stop as a mistake, and
  leave the last finished turn out of future calibration (the constitution's `/loopbrake:exclude`). In
  future calibration, a mistaken stop counts as a good turn longer than any stop line, so marking
  mistakes can only raise the line. Other stops are left out as stuck turns. (Leaving mistaken stops
  out would lower the next line; see research R10.)
- **FR-008**: A status-line command MUST show the current turn's count and the stop line. Its
  one-line setup MUST be documented, because plugins can't install a status line themselves.
- **FR-009**: Installing MUST take two Claude Code commands (add the marketplace, install the
  plugin). The repository serves as its own plugin marketplace.
- **FR-010**: Everything MUST stay on the user's machine. The only network use is installing the
  package itself. Records keep action excerpts of at most 200 characters, and calibration records
  hold no transcript text (Principle VI).
- **FR-011**: Each Claude Code project MUST get its own stop line, identified by its working
  folder, with no setup per project beyond calibrating.
- **FR-012**: Uninstalling the plugin MUST leave nothing behind outside LoopBrake's own folder.

### Key Entities

- **Turn**: one prompt, or one background-task wake-up, and everything Claude does for it. It is a Phase 2 run, with the session id
  and a turn id.
- **Project**: one Claude Code working folder. It has its own calibration record, named from the
  folder.
- **Hook event**: what Claude Code hands the plugin after a prompt, after each tool call, and when a
  turn ends.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Replaying each turn's tool calls through the plugin's hook gives exactly the step
  counts and stop steps that calibration's reader computes from the same transcripts: 100%
  agreement. This holds on a synthetic test transcript in CI, and on the builder's own recorded
  sessions locally.
- **SC-002**: The plugin's work after each tool call takes at most 200 ms at the 95th percentile,
  measured on the builder's laptop.
- **SC-003**: From the first install command to the first watched turn takes under 2 minutes.
- **SC-004**: With the command missing, the records folder unwritable, or the calibration damaged,
  Claude Code turns still finish normally every time.
- **SC-005**: A deliberately stuck test turn is stopped live, right after the stop line, with the
  reason visible to the user. That's the launch demo moment.
- **SC-006**: With network access blocked, the hook still works (after the package is installed).
- **SC-007**: The status line's count matches the turn's step count after every tool call.
- **SC-008**: On at least 200 turns of the builder's real use with the plugin on, each turn's live
  step count equals calibration's count for the same turn, or is lower (a lower count can only stop
  later). Every higher count is a bug to fix before release.

## Assumptions

- **Running the hook**: users have `uv`, which runs `loopbrake` without a separate install. Anyone
  who installed `loopbrake` another way sets `LOOPBRAKE_CMD` to its full path. The README covers
  both.
- **Defaults**: α is 5%, with one stop line per project.
- **Platforms**: macOS and Linux are tested. Windows is untested in v1.
- **No warnings first**: the plugin never feeds warnings back to Claude before stopping, because that
  would change the runs the stop line was measured on (constitution, "No warn-first in v1").
- **Out of scope**:
  - the dashboard and telemetry export (Phase 4);
  - the demo agent and launch (Phase 5);
  - any stop signal other than the step budget.
