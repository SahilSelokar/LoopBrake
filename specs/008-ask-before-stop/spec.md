# Feature Specification: Ask Before Stopping (Claude Code)

**Feature Branch**: `008-ask-before-stop` | **Created**: 2026-10-12 | **Status**: Draft

**Input**: User description: "LoopBrake stops Claude unexpectedly many times in the middle of a task."
After looking at why (Background), the owner chose: keep the stop rule, and in Claude Code ask the
person at the stop line instead of ending the turn. Allow lets the task continue where it was; deny
ends it and records it as stuck; where nobody can answer, it stops as today.

## Background

Today, when a Claude Code turn passes its stop line, the plugin ends the turn. In the owner's own
use, this stopped good work again and again. The counts below come from the owner's local run logs
(counts only, no transcript content), checked on 2026-10-12, for one project:

- **All 8 stops came at tool call 39 or 40, on length alone.** None looked stuck: at most 1 or 2 of the
  last 5 tool calls repeated each other.
- **7 of the 8 were long, productive build turns**: 18 to 35 file edits in about 40 tool calls, never
  more than 7 calls without an edit. The 8th was a 22-call reading phase before writing a new spec.
- **The stop line is low because most turns are short.** The line came from 758 past turns. Half of
  them used 5 tool calls or fewer (quick questions), so the longest 5% starts at 39. The turns that
  get stopped are exactly the big tasks the owner cares most about.
- **Marking stops as mistakes barely helps.** Three marked mistakes among 758 turns moved the line
  from 38 to 39.

**Why not a smarter stop rule.** "Tool calls since the last file edit" was checked on the same
history and rejected:
- Claude often edits files through shell commands (scripts, `cat > file`), which a count of edit
  tools can't see.
- Big tasks often start with a long reading phase before the first edit.

The project's signal gate also says no new stop signal ships without a pre-registered experiment
that beats the step count on held-out agents (constitution, Development Workflow). So **the rule
stays the same; what happens at the line changes.**

**Why this keeps the guarantee.** The question goes to the person, not to Claude:
- When the person lets the task continue, the held tool call runs exactly as it would have, and
  nothing is added to what Claude sees. The turn's path is the same as it would have been without
  LoopBrake, so live turns stay exchangeable with the calibration turns. This is why it is not the
  "warn-first" the constitution rules out (Technical Constraints, "No warn-first in v1"). That rule
  is about feeding warnings back to the agent.
- When the person ends the task, it ends like a stop does today.

The bound becomes a bound on questions: in a project calibrated at α 5%, fewer than 1 in 20 good
turns get a question.

**A side benefit for calibration.** Today a mistaken stop's real length is unknown, so it is counted
as "longer than any line". A turn the person lets continue finishes with its real length, and later
calibrations can learn from it like any other good turn.

**Words used here**: as in specs/004. A **turn** is everything Claude does in answer to one prompt.
A **tool call** is one tool call made by the main agent; subagents' calls don't count. The **stop
line** is the project's calibrated limit. An **ask point** is the tool call at which LoopBrake asks.

**Words users see**: "task", "tool calls", "limit". The question appears in Claude Code's own
approval prompt; its text says what allowing (keep going) and denying (stop here) do.

## User Scenarios & Testing *(mandatory)*

The users are Claude Code users who keep LoopBrake on so runaway tasks don't burn time and tokens,
but who also run long, productive tasks they don't want cut off.

### User Story 1 - A long task asks before it is stopped (Priority: P1)

A task reaches the project's limit. Instead of ending it, LoopBrake holds Claude's next tool call
and asks the person, in Claude Code's own approval prompt, whether the task should keep going. The
question explains itself in plain words. For example: "LoopBrake: this task has made 38 tool calls.
In this project, good tasks almost never need more than 38 (fewer than 1 in 20 of your 758 past
tasks did). Allow to keep going: LoopBrake asks again at 78. Deny to stop the task here." The person
allows it, and Claude continues exactly where it was. LoopBrake asks again only if the task gets
much longer.

**Why this priority**: it removes the problem the owner reported: good long tasks cut off in the
middle.

**Independent Test**: in a test project with a stop line of 3, ask Claude to run a harmless command
10 times in one turn. Before the 4th call runs, the approval prompt appears with LoopBrake's reason.
Allow it: all 10 commands run, and the turn finishes normally.

**Acceptance Scenarios**:

1. **Given** a stop line of N and a person who can be asked, **When** a turn is about to make its
   (N + 1)th main-agent tool call, **Then** that call waits, and the person is asked with
   LoopBrake's reason.
2. **Given** the person allows it, **When** the task continues, **Then** the held call runs
   unchanged, and nothing about LoopBrake is added to what Claude sees.
3. **Given** an allowed task, **When** it keeps going, **Then** it is not asked again until its next
   ask point (twice the tool calls at which it was last asked).
4. **Given** an allowed task, **When** it ends normally, **Then** it is recorded as finished, with
   its full length, and later calibrations count it as a good task.
5. **Given** a task that finishes within N tool calls, or a project with no stop line yet, **When**
   it runs, **Then** no question is ever asked.
6. **Given** anything goes wrong in the plugin, **When** Claude uses tools, **Then** Claude carries
   on normally. The plugin never holds or blocks a call because of its own problem.

---

### User Story 2 - The person stops a stuck task from the question (Priority: P1)

The question appears, and the person can see the task is going in circles. They choose to stop it.
The held tool call doesn't run, and Claude Code ends the task there and hands back to the person,
as it does whenever a person rejects a tool call. When the task ends, LoopBrake records it as stopped
by the person: a confirmed stuck task. Claude Code tells hooks nothing at the moment of a rejection
(research R4), so LoopBrake learns of it when the task ends.

**Why this priority**: a "no" must really stop the task, and the stuck tasks the person catches must
be kept out of the next calibration.

**Independent Test**: same setup as Story 1, but deny at the first question. The 4th command doesn't
run, the task ends, and the log records it as stopped by the person.

**Acceptance Scenarios**:

1. **Given** an open question, **When** the person denies it, **Then** the held call doesn't run and
   the task ends.
2. **Given** Claude carries on after a rejection instead of ending, **When** it makes another call
   past the line, **Then** that call shows the same question again, so nothing past the line runs
   without the person.
3. **Given** a denied task, **When** it ends, **Then** it is recorded as stopped by the person and
   left out of future calibration, like any stuck task.
4. **Given** a denied task, **When** the person sends a new prompt, **Then** a new turn starts from
   zero, as today.

---

### User Story 3 - When nobody can answer, it still stops (Priority: P1)

Some sessions have no one to ask: Claude Code running headless (`claude -p`, scripts, CI), or a
session where permission prompts are turned off. There, a task past the limit is stopped exactly as
today, with the same reason, and `/loopbrake:mistake` still works for those stops.

**Why this priority**: unattended sessions are where a runaway task costs the most. Asking must
never quietly turn into "never stop".

**Independent Test**: run the Story 1 test headless (`claude -p`). The turn stops at the 4th call
with LoopBrake's reason, and no further tool calls run.

**Acceptance Scenarios**:

1. **Given** a headless session, **When** a turn reaches the stop line, **Then** it is stopped as
   today, and no further tool calls run in that turn.
2. **Given** a session where permission prompts are turned off, **When** a turn reaches the stop
   line, **Then** it is stopped as today, with no question.
3. **Given** a stop in such a session, **When** the person runs `/loopbrake:mistake` later, **Then**
   it is marked as a mistake, as today.

---

### User Story 4 - See the questions and answers (Priority: P2)

`/loopbrake:status` and the dashboard show how many tasks LoopBrake asked about, how many the person
let continue, and how many they stopped, next to the stops and the expected rate. A task view shows
where the question came and what the person answered.

**Why this priority**: the person can see whether the limit fits their work. Many "keep going"
answers mean it is too low, and the next calibration will raise it.

**Independent Test**: after one allowed and one denied question in a test project, status shows
"asked 2: you let 1 keep going, you stopped 1", and the dashboard shows both tasks with their
answers.

**Acceptance Scenarios**:

1. **Given** questions were asked, **When** the person runs status, **Then** it shows questions
   asked, allowed and denied, with stops shown separately.
2. **Given** a task that was asked about, **When** the person opens it in the dashboard, **Then** the
   question's place and the answer appear in plain words ("asked", "you let it keep going", "you
   stopped it").

---

### User Story 5 - Honest words everywhere (Priority: P2)

Everything LoopBrake says about Claude Code matches the new behavior: the README, the plugin's
description and its messages say that LoopBrake asks before it stops, and that fewer than 1 in 20
good tasks get a question (at α 5%). Where it can't ask, they say it stops.

**Why this priority**: the project's public claims must stay true (constitution, Public claims).

**Independent Test**: read the README's Claude Code section, the plugin description and each message.
None says that good tasks get stopped at that rate in sessions where the person can be asked.

**Acceptance Scenarios**:

1. **Given** the release, **When** someone reads the Claude Code section of the README, **Then** it
   describes the question, both answers, and the headless fallback, with the condition on the
   promise kept ("as long as your future tasks are like your past ones").

### Edge Cases

- **Several tool calls at once**: Claude sometimes sends a batch of calls together, and Claude Code
  may check a later call before an earlier one finishes (research R5). The ask point is one question.
  Calls already on their way at that point may each show the same question, and the task continues if
  the person allows any of them.
- **The person walks away**: the question waits, and nothing more is spent until someone answers.
  If the person types a new prompt instead, the turn counts as stopped by the person and is left out
  of calibration. In Claude Code a rejection itself ends the turn, so the two can't be told apart.
- **Auto-approve settings**: the question appears even when the person has set Claude Code to accept
  edits or commands without asking. Only "permission prompts turned off" counts as "can't ask"
  (Story 3).
- **The call would have needed approval anyway**: the person sees one prompt, and it carries
  LoopBrake's reason.
- **Subagents**: their tool calls are never held and never counted, as today.
- **A turn woken by a background task** (no new prompt): it counts and asks like any other turn.
- **The held call fails after being allowed**: it counts as a tool call, as today.
- **Calibration while a question is open**: the open turn is not used. Only finished turns count.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When a turn reaches its stop line in a session where the person can be asked, the
  plugin MUST hold the next main-agent tool call and ask the person, through Claude Code's own
  approval prompt, whether the task should keep going. It MUST NOT end the turn.
- **FR-002**: The decision to ask MUST be the brake's existing stop decision (same score, same stop
  line, same calibration). The plugin changes only how that decision is acted on (constitution
  Principles II and V).
- **FR-003**: The question MUST say, in plain words:
  - the task's tool calls so far;
  - the project's limit, and how many past tasks it comes from;
  - the promise ("fewer than 1 in 20 good tasks", for α 5%);
  - the stuck signals that fired, if any (repeats, nothing new, the same error);
  - what each answer does.
- **FR-004**: When the person allows it, the held call MUST run unchanged, and the plugin MUST NOT
  add any message to Claude's context.
- **FR-005**: After an allow, the plugin MUST NOT ask again in that turn until the turn reaches twice
  the tool calls at which it last asked (for example 39, then 78, then 156).
- **FR-006**: When the person denies it:
  - the held call MUST NOT run;
  - if Claude carries on instead of ending, every later main-agent call past the line MUST show the
    same question again, so none runs without the person;
  - when the turn ends with no held call run, it MUST be recorded as stopped by the person.
- **FR-007**: When nobody can be asked (headless sessions, or permission prompts turned off for the
  session), the plugin MUST stop the turn at the stop line exactly as today: same reason, and the
  same mistake path.
- **FR-008**: Each ask point MUST be one question. Calls already on their way at that point may each
  show that same question (research R5). A call past the line MUST never run without the person
  allowing it, and MUST never be refused without the person's answer.
- **FR-009**: Subagent tool calls MUST NOT be held or counted (unchanged).
- **FR-010**: Each question and its outcome MUST be recorded in the session's run log: the turn, the
  tool call at which it was asked, and the outcome: allowed (a held call ran), or denied (the turn
  ended with none run). Records hold no more content than today's records do (Principle VI).
- **FR-011**: Calibration MUST treat outcomes as follows:
  - an allowed turn that ends normally is a successful turn with its real length;
  - a denied turn is left out as stuck, like other stops;
  - a turn interrupted while a question was open counts as denied, because the person didn't let it
    continue.

  The calibration math does not change.
- **FR-012**: Fail-safe, unchanged: any failure in the plugin's own path MUST let the tool call run.
  It never holds or blocks it.
- **FR-013**: The plugin's work before and after each tool call MUST stay within the existing time
  budget (200 ms at the 95th percentile, constitution Principle III).
- **FR-014**: `/loopbrake:status` MUST show questions asked, allowed and denied, next to stops and the
  expected rate. The dashboard MUST show them in a task's view and in the project summary, in its
  plain words (constitution, Dashboard).
- **FR-015**: The README, the plugin description and the plugin's messages MUST describe the new
  behavior and the promise as "fewer than 1 in 20 good tasks get a question" (α 5%), keeping its
  condition. They MUST say that the plugin stops instead where nobody can be asked.
- **FR-016**: The Codex CLI plugin, the Python package's brake for your own agents, and the
  OpenTelemetry export format MUST keep working unchanged.

### Key Entities

- **Question**: one ask point in one turn. It holds:
  - the turn and the tool call it held;
  - the stop line in force, and the reason shown;
  - the outcome: allowed (a held call ran) or denied (the turn ended with none run).

  A turn can have several questions, at doubling ask points.
- **Turn outcome**: finished, interrupted, stopped by LoopBrake (no one could be asked), and the new
  outcome, stopped by the person. What calibration does with each is set in FR-011.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In sessions where the person can be asked, no task is ended at the stop line without
  the person choosing it: 0 such endings in testing and in the owner's first two weeks of use.
- **SC-002**: Questions stay within the promise. Over the owner's next 200 good tasks in a project
  calibrated at 1 in 20, at most about 1 in 20 good tasks get a question, the same rate today's stops
  have.
- **SC-003**: Answering takes one choice in the prompt. After "keep going", the task picks up where
  it was, with no repeated or lost work, in 100% of tests.
- **SC-004**: After "stop here", no further call past the line runs in that task without the person
  allowing it, in 100% of tests.
- **SC-005**: Where nobody can be asked, 100% of tasks that reach the stop line are stopped, as today.
- **SC-006**: Long allowed tasks are asked rarely: a task twice its project's limit is asked at most
  once, a task four times the limit at most twice (asked at the limit, then at double it).
- **SC-007**: The owner no longer needs `/loopbrake:mistake` for tasks that got a question: 0 uses
  needed for them in two weeks.
- **SC-008**: No noticeable delay before or after tool calls: the plugin stays within its existing
  time budget.

## Assumptions

- **Claude Code's approval prompt**: a hook can make Claude Code ask the person before a tool call,
  with a reason the person sees. This is documented, and it shows even under auto-accept settings
  (Claude Code hooks docs, checked 2026-10-12).
- **Headless sessions**: Claude Code refuses such a call when nobody can answer, and the refusal
  reaches Claude. FR-006 and FR-007 make sure the turn still ends.
- **Undocumented behavior** (to settle in research before planning commits to a design):
  - how the approval prompt behaves when permission prompts are turned off. The safe default is to
    treat that session as "can't ask" and stop as today;
  - what Claude does right after a refusal;
  - whether the tool-call count kept after each call can decide before the next call, including
    calls sent in one batch.
- **The second ask point** is twice the first, then doubling. This is a simple, fixed default: the
  constitution allows no configuration for values that never change. The plan may pick a different
  fixed rule if research shows a better one.
- **The `--alpha` option stays**, so users can still set how rare questions are.
- **Exchangeability**: allowing a call adds nothing to Claude's context, so live turns follow the
  same paths as calibration turns. Calibration stays valid without being rerun under questions.

## Dependencies

- **Constitution amendment** (through `/speckit-constitution`, before the plan's Constitution
  Check). Three places describe today's behavior:
  - Principle I's wording ("kills stuck agent runs");
  - Technical Constraints, Claude Code hooks ("A stop is `continue: false`");
  - "Success labels".

  They need the Claude Code question, its two answers, and the headless fallback. The amendment
  should also say why this is not warn-first.
- **Public claims elsewhere**: the Visual Vortex website's LoopBrake page says "fewer than 1 in 20
  good tasks stopped". It must change with the release, under that site's own Honest Claims rule.
- **Earlier specs**: specs/004 (Claude Code plugin) and specs/005 (observability) are the base this
  changes.

## Out of Scope

- Changing the stuck score or adding stop signals. The signal gate still applies.
- The Codex CLI plugin, unless its hooks offer an equivalent "ask the person" decision. A later spec
  can add it then.
- The Python package's brake for your own agents (specs/007).
- Asking Claude itself to judge whether it is stuck. That would change what Claude sees, which is the
  ruled-out warn-first.
