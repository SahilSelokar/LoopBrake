# Feature Specification: Simple Agent Watch

**Feature Branch**: `007-agent-watch` | **Created**: 2026-10-03 | **Status**: Draft

**Input**: User description: "A simple way to use LoopBrake in your own agents, replacing the
hard-to-remember start()/step() loop and the hand-made runs file. Two pieces on the same engine: a
watcher made once per name, a wrapper put on each tool the agent can call (every tool call counts as
one action automatically: tool name, inputs, result, failure), and a task block around one job given
to the agent (normal and async). Past the limit, the next tool call raises a Stopped error carrying
the plain reason, and every later tool call in that task does too. Setting the limit needs no file: `loopbrake calibrate --project <name>` learns from
the tasks LoopBrake has already watched under that name. The builder's decision (2026-10-03): keep
BOTH multi-agent patterns. Option A, global watch: one watcher for the whole multi-agent system, one
limit for the whole job, works across handoffs. Option B, agent-based watch: one watcher per agent,
each agent's work is its own task with its own limit; a worker's calls count only in the worker's
task, never in its manager's; tasks running at the same time keep separate counts. The limit turns
on only by the user's explicit calibrate command. The existing start()/step() API stays. No change
to how stops are decided. Stop reasons in plain words."

## Background

LoopBrake v0.4.0 stops stuck tasks in Claude Code and Codex through their plugins, and offers a
Python package for people's own agents. The builder's feedback (2026-10-03): the package is "so
complex to remember" for one's own agent. Today it takes three things:

1. **A runs file.** To set a limit, the developer saves past runs in LoopBrake's own file format, by
   hand, and points the set-the-limit command at it. Nothing in the package helps make that file.
2. **Wiring the loop.** The developer calls LoopBrake after every action, turns the action and its
   result into text themselves, and checks LoopBrake's answer each time.
3. **Jargon.** The reason it returns says "step" and "α", unlike the plain words of the plugins.

This feature adds a simpler way on the same engine: name what to watch once, mark the tools, mark
each job. LoopBrake records every task it watches, so the limit can be learned from those records
with one command, with no file. Multi-agent systems are covered in two ways, both kept by the
builder's decision: one limit for the whole job, or one limit per agent.

**Words used here**: as in earlier phases, a **task** is one job given to an agent (one run), an
**action** is one tool call, and the **limit** is the number of actions past which a task is
stopped. New here:
- a **watcher** is a name LoopBrake watches under, with its own limit and history (a "project" in
  the dashboard);
- **wrapping a tool** means marking one of the agent's tool functions, so LoopBrake sees every call
  to it;
- a **task block** is the part of the developer's code that runs one task.

## User Scenarios & Testing *(mandatory)*

The users are developers who build their own AI agents in Python, alone or as teams of agents, and
want runaway tasks stopped with LoopBrake's promise, without learning LoopBrake's internals.

### User Story 1 - Watch and stop your own agent with three small additions (Priority: P1)

A developer makes one watcher for their agent, wraps each of the agent's tools, and puts a task
block around each job. From then on every tool call is counted, with no other code. Without a
limit, LoopBrake only watches and records. With a limit, once a task has used it up, the next tool
call doesn't run: it raises a stop error carrying the plain reason, and so does every later tool
call in that task.

**Why this priority**: it replaces the part that is hard to remember, and it's what every other
story builds on.

**Independent Test**: an agent with one wrapped tool and a limit of 3 calls that tool 10 times in
one task. Three calls run; the fourth raises the stop error with the reason without running, and
so do calls 5 to 10; the task is recorded as stopped.

**Acceptance Scenarios**:

1. **Given** a watcher with no limit, **When** tasks run, **Then** nothing is ever stopped, and each
   task and its tool calls are recorded under the watcher's name.
2. **Given** a limit of N, **When** a task has made N tool calls and the agent calls a wrapped tool
   again, **Then** that call doesn't run: it raises the stop error with the plain reason, and the
   task is recorded as stopped.
3. **Given** a stopped task, **When** the agent calls any wrapped tool again in that task, **Then**
   the tool doesn't run and the same stop error is raised.
4. **Given** a task that stays within N tool calls, **When** its block ends normally, **Then** it is
   recorded as finished and nothing is raised.
5. **Given** a wrapped tool that fails with its own error, **When** it is called, **Then** the error
   reaches the agent unchanged, and the call counts as one failed action.
6. **Given** tools and task blocks written as asynchronous code, **When** they run, **Then**
   scenarios 1 to 5 hold the same way.
7. **Given** a problem inside LoopBrake (its folder can't be written, its records are damaged),
   **When** wrapped tools are called, **Then** every call runs and returns normally, and no stop
   error is raised because of LoopBrake's own problem.

---

### User Story 2 - Set the limit with one command, no file (Priority: P2)

After the agent has run some tasks under a watcher, the developer sets the limit with one command
naming the watcher. It learns from the tasks LoopBrake already watched under that name. With too few
good tasks, it says how many more are needed.

**Why this priority**: the hand-made runs file is the hardest step today; without this story the
developer still needs it.

**Independent Test**: record 25 finished tasks under a watcher, run the command, and get the same
limit as from the same task lengths given as a runs file.

**Acceptance Scenarios**:

1. **Given** at least 19 good watched tasks, **When** the developer runs the command, **Then** a
   limit is set and reported in plain words, and new tasks under that watcher use it.
2. **Given** fewer than 19, **When** the command runs, **Then** LoopBrake keeps watching only and
   says how many more good tasks it needs.
3. **Given** a stop the developer marked as a mistake, **When** the limit is set again, **Then** that
   task counts as a good task longer than any limit, so the limit can only go up.
4. **Given** tasks that were stopped, ended by an error, or left out by the developer, **When** the
   limit is set, **Then** they are not used.
5. **Given** a developer who still uses a runs file, or the old step-by-step way, **When** they use
   it, **Then** it works exactly as before.

---

### User Story 3 - Teams of agents: one limit for the whole job, or one per agent (Priority: P3)

The builder's decision: both patterns are supported.

- **Option A, global watch**: one watcher shared by every agent in the system, and one task block
  per job. Every agent's tool calls count toward that job, including when the job passes from one
  agent to another. One limit covers the whole job.
- **Option B, agent-based watch**: one watcher per agent, and each agent's work in its own task
  block. A tool used by several agents is wrapped once for each. When a manager agent hands work to
  a worker agent, the worker's calls count only in the worker's task, never in the manager's. Each
  agent learns its own limit and shows in
  the dashboard as its own project.

**Why this priority**: teams of agents are common, and a single loop can't express them; but each
agent in a team relies on Stories 1 and 2.

**Independent Test**: (A) two agents whose tools share one watcher make 3 calls each in one task:
the task counts 6. (B) a manager's task makes 2 calls and opens a worker's task that makes 5: the
manager's task counts 2 and the worker's 5. Ten tasks running at the same time, each with a known
number of calls: every recorded count matches.

**Acceptance Scenarios**:

1. **Given** one watcher for all agents (A), **When** a job passes from one agent to another,
   **Then** every call counts in the job's task, and the job's limit applies.
2. **Given** a worker's task opened inside a manager's task (B), **When** the worker calls tools,
   **Then** those calls never count in the manager's task.
3. **Given** the same tool wrapped for two agents (B), **When** each agent calls it, **Then** each
   call counts only for the agent that called it.
4. **Given** several tasks running at the same time, **When** they call tools, **Then** each task's
   count equals its own calls.
5. **Given** two watchers, **When** each sets its limit, **Then** each limit is learned only from
   that watcher's own tasks.
6. **Given** a worker's task that gets stopped, **When** the stop error reaches the manager's code,
   **Then** the manager's task carries on unless the manager's own code decides otherwise; LoopBrake
   never stops one task because another was stopped.

---

### Edge Cases

- **A tool called outside any task block**: it runs normally, isn't counted, and nothing is stopped.
  LoopBrake says so once per watcher, so the developer notices a missing task block.
- **Nested task blocks of the same watcher**: the inner block is its own task; calls count in the
  innermost open task.
- **A framework that catches tool errors and hands them to the model**: the model sees the reason;
  any later call in that task raises again without running; the task stays stopped and is recorded
  as stopped when its block ends.
- **A task block ended by any other error**: the task is recorded as interrupted and isn't used for
  the limit; the error passes through unchanged.
- **A tool run where LoopBrake can't tell which task called it** (for example on a separate thread
  that doesn't carry the task along): the call isn't counted. Counting fewer can only stop later,
  the safe side.
- **Inputs or results that can't be turned into text**: the call still counts; a short description
  is recorded instead.
- **Very long inputs or results**: only a short excerpt is kept, as today.
- **A tool that returns a stream**: it counts once, when called.
- **Watcher names**: the same rules as project names. An invalid name is refused when the watcher is
  made, before any task runs.
- **The same watcher name in two programs**: they share one limit and one history, by design.
- **Setting the limit for a name with no watched tasks**: a plain message says so.

## Requirements *(mandatory)*

### Functional Requirements

**Watching and stopping (User Story 1)**
- **FR-001**: A developer MUST be able to make a watcher by name once and use it throughout their
  program.
- **FR-002**: A developer MUST be able to wrap any tool function, normal or asynchronous, so that
  each call counts as one action, recording the tool's name, a short text of its inputs, a short
  text of its result, and whether it failed, with no other code.
- **FR-003**: A developer MUST be able to mark one task with a task block, in normal or asynchronous
  code; a call counts in the innermost open task of the watcher whose wrapper was called.
- **FR-004**: Without a limit, LoopBrake MUST only watch and record; it MUST never stop anything.
- **FR-005**: With a limit of N, a task's (N + 1)th wrapped call MUST NOT run: it MUST raise a stop
  error with the plain reason, and every later wrapped call in that task MUST raise the same error
  without running.
- **FR-006**: The decision MUST be the existing LoopBrake rule, unchanged (constitution Principles I,
  II and V): this feature adds no scoring of its own.
- **FR-007**: The stop reason MUST be in plain words: "tool calls", how long tasks usually take, "fewer than 1 in 20", and what the task kept doing; never step, α, score or ids.
- **FR-008**: A failure inside LoopBrake MUST never stop a tool call, change its result, or slow it
  beyond the budget in SC-005 (constitution, "Failing safely").
- **FR-009**: A task block MUST record its task as finished, stopped, or interrupted (ended by any
  other error), and MUST pass the stop error and any other error out unchanged.

**Setting the limit (User Story 2)**
- **FR-010**: The set-the-limit command, given only a watcher's name, MUST learn the limit from the
  tasks watched under that name: finished tasks as good ones; stopped, interrupted and left-out
  tasks not used; stops marked as mistakes counted as good tasks longer than any limit.
- **FR-011**: The runs-file route and the existing step-by-step way MUST keep working unchanged.
- **FR-012**: The live count and the count the limit is learned from MUST come from the same records,
  so the live count is never higher than the learned one for the same task (constitution, "Same
  turns live and in calibration").

**Teams of agents (User Story 3)**
- **FR-013**: One watcher shared by several agents MUST count all their calls in the open task of
  that watcher (Option A).
- **FR-014**: Separate watchers MUST keep separate tasks, counts and limits; a call counts only for
  the watcher whose wrapper was called (Option B).
- **FR-015**: Tasks running at the same time MUST keep separate counts; a call whose task can't be
  determined MUST NOT be counted in any task.
- **FR-016**: A stop in one task MUST NOT stop any other task, including the task around it.

**Seeing it and privacy**
- **FR-017**: Tasks from watchers MUST appear in the dashboard and the export like other tasks,
  under the watcher's name, with each action named by its tool's name.
- **FR-018**: Nothing MUST leave the computer unless export is on, and inputs and results are kept
  only as short excerpts, locally (constitution Principle VI).

**Documentation**
- **FR-019**: The README MUST show the three additions, both team patterns, and the one-command limit,
  each as an example that runs as written.

### Key Entities

- **Watcher**: a name LoopBrake watches under, with its own limit and history; made once per agent
  (Option B) or once for a whole team of agents (Option A).
- **Task**: one job, from its task block's start to its end; its status (running, finished, stopped,
  interrupted), its counted actions, and the limit in force.
- **Action**: one call to a wrapped tool: the tool's name, a short text of its inputs and result, and
  whether it failed.
- **Stop error**: what a wrapped tool raises once its task is stopped; it carries the plain reason.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Adding LoopBrake to an existing agent takes three kinds of additions: one line for the
  watcher, one per tool, and one block per task. A developer new to LoopBrake gets a watched agent
  working from the README in under 5 minutes.
- **SC-002**: With a limit of 3 and 10 calls in a task, exactly 3 tool calls run; the 4th raises the
  stop with the reason without running, and so do calls 5 to 10, in 100 of 100 automated runs, for both normal
  and asynchronous tools.
- **SC-003**: After 19 or more good watched tasks, one command sets the limit with no file, and the
  limit equals the one learned from the same task lengths given as a runs file.
- **SC-004**: In team tests, every task's recorded count equals the tool calls made for it: across a
  handoff (Option A), for a manager and its worker (Option B), and for 10 tasks running at the same
  time, in 100% of runs.
- **SC-005**: LoopBrake adds no more than 10 milliseconds to 95% of tool calls.
- **SC-006**: With LoopBrake broken on purpose (its folder read-only, its records damaged), 100% of
  tool calls run and return normally, and no stop error is raised.
- **SC-007**: Every code example in the README runs as written.

## Assumptions

- **Python agents**: tools are Python functions that the agent, or its framework, calls. Tools run
  by the model's provider (a hosted web search, for example) aren't seen. Other languages are out of
  scope.
- **No framework-specific adapters**: the wrapper works wherever tools are Python functions, so one
  feature serves many frameworks. A dedicated adapter for a given framework (for example the OpenAI
  Agents SDK) stays a possible later feature.
- **The limit turns on only by the developer's command**, so the developer decides when stops begin,
  for example after testing their agent; status says when enough good tasks are recorded.
- **Good tasks**: a task counts as good when its block ended normally and it wasn't stopped
  (constitution, "Success labels"). A task that ended normally but didn't do its job still counts as
  good; that can only make the limit higher, so stops only get rarer.
- **No call past the limit runs**: the call that would go past it is refused before it runs,
  because an agent's tools can have real effects (sending a message, spending money). Which tasks get
  stopped is the same as when the call runs first, so the promise is unchanged.
- **No token counts** from wrapped tools: a tool call doesn't know what the model spent. Developers
  who want token totals keep using the step-by-step way.
- **No new evaluation**: stops are decided exactly as before (constitution Principle IV).
- **Release**: a minor version (v0.5.0); nothing existing changes.
- **Messages**: the stop error says "tool calls"; the dashboard says "actions".
