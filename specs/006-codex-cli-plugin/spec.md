# Feature Specification: Codex CLI Plugin

**Feature Branch**: `006-codex-cli-plugin` | **Created**: 2026-10-02 | **Status**: Draft

**Input**: User description: "Phase 4b: a LoopBrake plugin for OpenAI's Codex CLI, the same live
stops the Claude Code plugin gives. Codex users install it once; it counts each task's tool calls
through Codex's hooks, stops a task that goes past the project's limit and says why in plain words,
learns the limit from the user's own past Codex sessions, offers the same commands (set the limit,
status, it wasn't stuck, leave out, open the dashboard), and shows Codex tasks in the existing
dashboard and export. ChatGPT itself and the OpenAI Agents SDK are out of scope."

## Background

LoopBrake v0.3.0 stops stuck Claude Code tasks live, learns each project's limit from its own past
tasks, and shows everything in a local dashboard and, optionally, in observability tools. This
feature brings the same to **Codex CLI**, OpenAI's coding agent for the terminal. It is the
builder's choice for OpenAI support (2026-10-02), over ChatGPT (which offers no way to watch or stop
its own work) and the OpenAI Agents SDK (later, if asked for).

**What Codex offers** (its documentation, checked 2026-10-02): programs that run on its events
("hooks"), on by default, which plugins can ship. One event comes after each tool call, others when
a task starts and ends, and one before each tool call. **One difference from Claude Code matters**:
when the after-tool-call hook asks Codex to stop, Codex replaces that tool's result with the message
and carries on. So whether, and how, LoopBrake can really end a Codex task must be proven first
(User Story 1's gate).

**Words used here**: as in Phases 3 and 4. A **task** is everything Codex does for one message the
user sends. An **action** is one tool call made by the main agent; actions made by Codex's helper
agents don't count, as in Claude Code. Messages shown inside Codex say "tool calls", like the
Claude Code plugin; the dashboard says "actions" (constitution 2.5.0).

## User Scenarios & Testing *(mandatory)*

The users are Codex CLI users who want runaway tasks stopped before they burn time and tokens, and
people who use both Claude Code and Codex.

### User Story 1 - Stuck Codex tasks get stopped, live (Priority: P1)

A user installs the plugin and sets a limit for their project. From then on, when a Codex task goes
past the limit, no further tool call of that task runs, the task ends, and the user sees LoopBrake's
reason in plain words, the same message the Claude Code plugin gives. Without a limit, the plugin
only watches and records.

**The gate**: before anything else is built, a probe on a real Codex shows a way to end a task
after a given tool call so that no later tool call of that task runs. If no such way exists, the
feature stops here and goes back to the builder: shipping something that only warns would break the
constitution ("no warn-first in v1").

**Why this priority**: this is the whole point of the plugin. Everything else supports it.

**Independent Test**: with a limit of 3 for a test project, ask Codex to run a harmless command 10
times in one task. No more than 4 run, and the reason is shown.

**Acceptance Scenarios**:

1. **Given** a limit of N for this project, **When** a task makes its (N + 1)th main-agent tool
   call, **Then** no later tool call of that task runs, the task ends, and the reason is shown.
2. **Given** a task that finishes within N tool calls, **When** it ends, **Then** nothing is
   stopped and the task is recorded as finished.
3. **Given** no limit yet, **When** tasks run, **Then** nothing is ever stopped and each task is
   recorded.
4. **Given** a new message after a stop, **When** the user continues, **Then** counting starts again
   from zero for the new task.
5. **Given** anything goes wrong in the plugin (its program can't be found or is slow, a file is
   damaged, its folder can't be written), **When** Codex uses tools, **Then** Codex carries on
   normally. The plugin never blocks or stops a task because of its own problem.

---

### User Story 2 - Set up and manage it from inside Codex (Priority: P2)

From inside Codex, the user sets this project's limit from its own past Codex tasks with one
command and sees the result in plain words. They can ask for status, mark the last stop as a
mistake ("it wasn't stuck"), leave the last finished task out of future limits, and open the
dashboard: the same five commands the Claude Code plugin has, with the same messages.

**Why this priority**: setup should take seconds, without leaving Codex or knowing where its
history lives.

**Independent Test**: in a project with at least 19 finished past Codex tasks, the set-the-limit
command gives a limit; with fewer, it says how many more are needed. Status shows the counts;
marking a stop as a mistake raises the mistaken count by one.

**Acceptance Scenarios**:

1. **Given** a project with enough Codex history, **When** the user sets the limit, **Then** it is
   learned from that project's own Codex tasks and reported in plain words.
2. **Given** a stopped task, **When** the user says it wasn't stuck, **Then** status counts it, and
   the next limit counts that task as a good one longer than any limit, so the limit can only go up.
3. **Given** two projects, **When** each sets its limit, **Then** each has its own, and they never
   mix.
4. **Given** the same folder used with both Claude Code and Codex, **When** each sets its limit,
   **Then** each agent has its own limit, learned only from its own tasks.

---

### User Story 3 - Codex tasks in the dashboard and your tools (Priority: P3)

Codex tasks appear in the same dashboard as Claude Code tasks, live, marked as Codex, with each
action named by what it did ("Ran a command", "Edited files"). The dashboard command opens it from
inside Codex. With export on, Codex tasks go to the user's observability tools like any other.

**Why this priority**: seeing and explaining a stop matters, but the stop itself comes first.

**Independent Test**: run a Codex task and open the dashboard: the task is there within 2 seconds
of each action, labeled Codex, with plain action names; with export on, it reaches a test
observability tool.

**Acceptance Scenarios**:

1. **Given** a Codex task running, **When** the dashboard is open, **Then** its count rises within 2
   seconds of each action, and the task is labeled Codex.
2. **Given** a stopped Codex task, **When** its page opens, **Then** it explains the stop as for
   Claude Code: the picture of past tasks, what it kept doing, and every action in plain words.
3. **Given** export on, **When** a Codex task ends or is stopped, **Then** it is sent like other
   tasks, named as Codex, with nothing more than for Claude Code tasks.

---

### Edge Cases

- **Helper agents**: Codex's helper agents fire the same events; their tool calls never count, and
  a task that uses a helper is counted on the main agent's actions alone.
- **Parallel tool calls**: several tool calls at once are each counted once.
- **Interrupting a task** (the user presses Esc, or Codex's interrupt event): the task is recorded
  as interrupted, and the next message starts a new count.
- **Resumed sessions and compaction**: a resumed session or a compacted history doesn't double-count
  or reset a task's count.
- **Non-interactive runs** (`codex exec`): counted and stopped the same way.
- **Codex's sandbox**: if the sandbox stops the plugin from writing its records or reaching its
  program, Codex still carries on (User Story 1, scenario 5), and status says LoopBrake couldn't
  record.
- **Hooks turned off** by the user: LoopBrake does nothing, and status says hooks are off.
- **A Codex update changes its events or history format**: the plugin fails safe (watches nothing,
  blocks nothing), and a pinned sample catches the change in tests.
- **The same folder in Claude Code and Codex at once**: two separate projects, two limits, one
  dashboard.

## Requirements *(mandatory)*

### Functional Requirements

**Stopping (User Story 1)**
- **FR-001**: Before any release, a probe on a real Codex MUST show a way to end a task after a
  given tool call so that no later tool call of that task runs. Without it, the feature stops and
  goes back to the builder.
- **FR-002**: Each task MUST count only the main agent's tool calls; helper agents' calls MUST NOT
  count.
- **FR-003**: When a task's count passes the project's limit, no later tool call of that task MUST
  run, the task MUST end, and the user MUST see the reason in the same plain words as the Claude
  Code plugin.
- **FR-004**: Without a limit, the plugin MUST only watch and record; it MUST never stop anything.
- **FR-005**: A failure inside the plugin MUST never block, slow beyond the per-action budget, or
  end a Codex task (constitution, "Failing safely").
- **FR-006**: The decision MUST be the existing LoopBrake rule, unchanged (constitution, Principle
  V: the plugin is a thin adapter).

**Limits (User Story 2)**
- **FR-007**: The limit MUST be learned from the user's own past Codex tasks in that project, cut
  at the same task boundaries the live count uses, so the live count is never higher than the
  learned one for the same task (constitution, "Same turns live and in calibration").
- **FR-008**: A project MUST be one Codex working folder, and Codex and Claude Code limits MUST be
  kept apart, even for the same folder.
- **FR-009**: From inside Codex, the user MUST be able to set the limit, see status, mark the last
  stop as a mistake, leave the last finished task out, and open the dashboard, with the same effect
  and messages as the Claude Code commands.
- **FR-010**: Reading Codex's history MUST happen in one place, checked against a pinned sample,
  because that format is Codex's own and can change (constitution, Principle V).

**Seeing it (User Story 3)**
- **FR-011**: Codex tasks MUST appear in the existing dashboard, labeled Codex, with each action
  named by what it did.
- **FR-012**: With export on, Codex tasks MUST be sent like other tasks, named as Codex, under the
  same content rules (metadata only unless content is opted in).

**Install and privacy**
- **FR-013**: Codex users MUST be able to install the plugin from this repository, in the way Codex
  installs plugins, with the README showing how.
- **FR-014**: Nothing MUST leave the computer unless export is on (constitution, Principle VI);
  Codex history MUST never appear in commits, test samples or public content.

### Key Entities

- **Codex task**: one message's work by Codex: its project, its session, start and end, status
  (running, finished, stopped, interrupted), its counted actions, and the limit in force.
- **Action**: one main-agent tool call: the tool, a short text of what it did, failed or not, and
  its id.
- **Codex project**: one Codex working folder, with its own limit, kept apart from the same
  folder's Claude Code project.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With a limit of 3, a Codex task asked to run a harmless command 10 times runs no more
  than 4 of them, and the reason is shown, in 10 of 10 tries.
- **SC-002**: LoopBrake adds no more than a fifth of a second to 95% of Codex's tool calls.
- **SC-003**: With LoopBrake broken on purpose (program missing, records damaged, folder read-only),
  10 of 10 Codex tasks still finish normally.
- **SC-004**: On the builder's real Codex use, the live count is never higher than the learned count
  for any matched task.
- **SC-005**: A user with enough Codex history goes from install to a working limit in under 2
  minutes.
- **SC-006**: In a task that uses a helper agent, the count equals the main agent's actions alone.
- **SC-007**: A running Codex task's new action shows on the dashboard within 2 seconds, every time.

## Assumptions

- **Codex version**: a Codex CLI with hooks and plugins (hooks have been on by default since early
  2026). The plan pins the lowest version that works.
- **The builder's setup**: the builder has no Codex account (2026-10-02). The builder's decision:
  check on a real Codex running a local model instead, which exercises Codex's own hooks, history and
  sandbox; what a GPT model does after a refused call is then checked by the first users (research
  R10). The README says how it was checked.
- **The same core**: the plugin uses the same LoopBrake package and the same records, dashboard and
  export as v0.3.0; only the part that talks to Codex is new.
- **Separate limits per agent**: Claude Code and Codex tasks differ in size, so mixing them would
  break the promise ("fewer than 1 in 20"), which only holds for tasks like the ones it learned
  from.
- **Messages**: inside Codex, "tool calls" (Codex's users know the term); in the dashboard,
  "actions".
- **Out of scope**: ChatGPT (it offers no way to watch or stop its own work) and the OpenAI Agents
  SDK (a later adapter, if asked for). Codex's IDE extensions and cloud tasks only if they run the
  same hooks; the plan checks.
