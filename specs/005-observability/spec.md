# Feature Specification: Observability (dashboard and company-tool export)

**Feature Branch**: `005-observability` | **Created**: 2026-10-02 | **Status**: Draft

**Input**: User description: "" (empty; started from `/speckit-specify` after Phase 3 shipped). This
is roadmap Phase 4: "a working observability tool, local first, that also plugs into company
tools", with a liquid glass dashboard, proper icons, no emoji, and export to the tools companies
already use.

## Background

LoopBrake 0.2.1 stops runaway agent tasks: in Claude Code through the plugin, and in other agents
through the Python package. Everything it sees is written to local records on the user's computer.
Right now the only ways to look at those records are a one-line status and a few commands.

This feature gives people two ways to see what LoopBrake is doing:
1. **A dashboard on their own computer.** It shows tasks as they run, where each one stands against
   its limit, why a task was stopped, and each project's limit. They can also act on it: mark a
   wrong stop, leave a task out, set the limit again.
2. **Export to their company's tools** (Datadog, Grafana, Honeycomb and others), through the
   OpenTelemetry standard those tools accept. LoopBrake's tasks and stops then show up next to
   everything else the team watches.

**Words used here**: as in Phase 3, and in the plain words users see (Phase 3, FR-013).
- **Task**: everything an agent does for one request. LoopBrake's records call it a run, or a turn
  in Claude Code.
- **Tool call**: one action the agent takes (a step).
- **Limit**: the stop line. A task that goes past it is stopped.
- **Project**: one agent or one Claude Code folder, with its own limit.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See what LoopBrake is doing (Priority: P1)

A developer opens the dashboard with one command. They see:
- the tasks running right now, each with its tool-call count against its project's limit;
- the tasks LoopBrake stopped recently;
- totals: tasks seen, tasks stopped, and stops marked as mistakes.

When they open a stopped task, they see:
- every tool call in order: the tool, a short description of the action, and whether it failed;
- where the limit was, and the call at which LoopBrake stopped it;
- the reason, in plain words.

The same view works for a task still running, which updates as it goes, and for past tasks.

**Why this priority**: today nobody can see what LoopBrake did without reading raw files. This is
the core of the phase, and the launch reel's "dashboard catching a loop" moment.

**Independent Test**: start the dashboard, then run a Claude Code task in a project with a low
limit. The task appears with a rising count, then shows as stopped. Opening it shows each tool call
and the reason.

**Acceptance Scenarios**:

1. **Given** a task is running, **When** it makes a tool call, **Then** the dashboard's count for
   that task goes up within 2 seconds, with no page reload.
2. **Given** a task was stopped, **When** the user opens it, **Then** they see each tool call in
   order, the limit, the call where it stopped, and the reason in plain words.
3. **Given** records from several projects and agents (the Claude Code plugin, the Python package,
   the agent toolkit), **When** the user opens the overview, **Then** all of them appear, and can be
   filtered by project.
4. **Given** no records yet, **When** the dashboard opens, **Then** it explains in one sentence how
   to get started, instead of showing empty charts.

---

### User Story 2 - Act on what you see (Priority: P2)

From the dashboard, the user can:
- **mark a stop as a mistake**, which counts against the allowance, so the next limit can only go
  up;
- **leave a task out** of future limits;
- **set a project's limit again** from its past tasks.

A project page shows:
- the limit and how many past tasks it came from;
- when it was set;
- the promise, in plain words ("fewer than 1 in 20 good tasks should go past it");
- whether the project only watches for now, and how many more tasks it needs.

**Why this priority**: seeing a wrong stop and fixing it in the same place is what makes people
trust the brake. The commands from Phase 3 already do this; the dashboard makes it obvious.

**Independent Test**: on a stopped task, click "Mark as mistake". The project's mistaken-stop count
goes up by one. Click "Set the limit again", and the new limit appears with the same numbers the
`/loopbrake:calibrate` command would give.

**Acceptance Scenarios**:

1. **Given** a stopped task, **When** the user marks it a mistake, **Then** the same thing happens as
   with `/loopbrake:mistake` for that task. Marking it twice is refused.
2. **Given** a finished task, **When** the user leaves it out, **Then** future limits ignore it, as
   with `/loopbrake:exclude`.
3. **Given** a project, **When** the user sets its limit again, **Then** the result equals what the
   command gives for the same history.
4. **Given** any action, **When** it would change records, **Then** the user confirms it first, and
   only the person at this computer can do it.

---

### User Story 3 - See it in the company's tools (Priority: P2)

A developer whose team uses an observability tool turns on export. From then on:
- each task appears there as a trace, with one entry per tool call;
- a stop shows as an error on that task, with the reason;
- counts of tasks, stops, mistaken stops and tokens spent show as numbers they can chart and alert
  on.

If they also use Claude Code's own telemetry, LoopBrake's entries appear inside the same trace as
the Claude Code session.

By default only metadata is sent: ids, counts, tool names, times, stop events and token counts.
What the agent typed or saw is never sent unless they turn that on separately.

**Why this priority**: teams already watch their agents in these tools, so "it shows up in your
Datadog too" is what gets LoopBrake used at work.

**Independent Test**: point export at a local OpenTelemetry Collector and run a task that gets
stopped. The Collector receives one trace for the task, with one span per tool call and the stop
marked as an error, plus the counters. No action text appears in what was received.

**Acceptance Scenarios**:

1. **Given** export is off (the default), **When** tasks run, **Then** nothing leaves the computer,
   even if the standard telemetry settings are set for other tools.
2. **Given** export is on, **When** a task finishes or is stopped, **Then** its trace reaches the
   configured backend.
3. **Given** export is on and the backend is down or slow, **When** tasks run, **Then** the agent
   isn't slowed beyond its normal limit, every task finishes as it would have, and the export
   failure shows in the dashboard.
4. **Given** content export is off, **When** the received data is inspected, **Then** it holds no
   action text, prompts, tool outputs or quoted reasons.

---

### User Story 4 - Readable, accessible and on-brand (Priority: P3)

The dashboard:
- looks like the LoopBrake reel brand (night background, lime accents, the liquid glass look on its
  controls);
- uses one consistent icon set and no emoji;
- stays readable for everyone. It comes in a light and a dark theme that follow the system, glass
  turns itself off when the system asks for less transparency or more contrast, motion respects the
  user's settings, and color is never the only signal.

It also works at phone width, so it can be recorded for reels.

**Why this priority**: it carries the launch video and the builder's credibility, but every
function above works without it.

**Independent Test**: run an automated accessibility audit in the light and the dark theme. Both
score at least 95 of 100. Turn on the system's "reduce motion" and "increase contrast" settings,
and check that the dashboard follows them.

**Acceptance Scenarios**:

1. **Given** the dashboard, **When** the user picks light, dark or system in Settings, **Then** the
   whole page switches and stays that way the next time they open it.
2. **Given** a stopped task anywhere in the UI, **When** it's shown, **Then** it has a stop icon and
   the word "Stopped", never red text alone.
3. **Given** a phone-width window, **When** any screen is shown, **Then** nothing needs sideways
   scrolling, and every action is reachable.

---

### User Story 5 - Anyone can understand it (Priority: P2)

Someone who doesn't code opens the dashboard and, without help, can say what LoopBrake did and why.
- The home screen says in one sentence how things are going, and shows the work happening now.
- A stopped task explains itself as a picture: the project's normal tasks, the limit, and this task
  past it. What the agent kept repeating is shown as a group ("Ran the same command 6 times").
- Actions are named by what they did ("Ran a command", "Read a file"), and projects by their real
  folder name, not a code.
- Every idea (task, action, limit, mistake) has a one-line explanation one click away.

**Why this priority**: the builder's audience includes people who don't code. If they can't read
it, the dashboard doesn't do its job, however correct it is.

**Independent Test**: open a stopped task and ask someone who doesn't code why it stopped. Measured
after release (SC-008).

**Acceptance Scenarios**:

1. **Given** a task stopped today, **When** the home screen opens, **Then** its first sentence says
   so, with a link to why.
2. **Given** a stopped task that repeated one command, **When** its page opens, **Then** it shows
   that command, how many times it ran, and the picture of normal tasks against the limit.
3. **Given** a chart, **When** the user points at or taps any part of it, **Then** it shows what that
   part means in words.
4. **Given** the dashboard is open, **When** LoopBrake stops a task, **Then** a notice appears with a
   link to why.

---

### Edge Cases

- **Huge sessions**: a session with thousands of tool calls (the largest local one has 6,300)
  opens without freezing. Long lists load in pages.
- **Damaged record lines**: they're skipped, and the dashboard says how many it skipped.
- **Someone else on the network** opens the dashboard's address: refused. So is a web page trying
  to reach it through a trick address (DNS rebinding).
- **The access key in the address bar**: it isn't left visible after the page opens, so a screen
  recording for a reel doesn't show it.
- **Records written while the dashboard is open**: new tasks appear. A task that ends shows its
  final state.
- **Watch-only projects**: shown as "watching only, needs N more tasks", never as a broken limit.
- **Export turned on mid-session**: only tasks that start afterwards are sent. Tasks that already
  finished aren't sent again.
- **The export backend asks LoopBrake to wait** (rate limit): it waits once, as asked. If it still
  fails, it gives up for that batch, keeps the records local, and shows the failure.
- **Two dashboards opened at once**: both work. Actions are written once, and a double click
  doesn't count twice.

## Requirements *(mandatory)*

### Functional Requirements

**Dashboard**
- **FR-001**: The dashboard MUST start with one command and print the address to open. It MUST be
  reachable only from the same computer, MUST require a per-launch access key, and MUST refuse
  requests that don't come from its own address.
- **FR-002**: It MUST show tasks from every project and every kind of agent that LoopBrake records,
  and a running task's tool-call count MUST update within 2 seconds of each call.
- **FR-003**: A task's page MUST show its tool calls in order (tool, short action text of at most
  200 characters, failed or not, tokens when known), the limit, where it stopped, and the reason in
  plain words.
- **FR-004**: A project's page MUST show the limit, how many past tasks it came from, when it was
  set, the promise in plain words, the watch-only state with how many more tasks are needed, and
  the mistaken stops against how many would be normal by now.
- **FR-005**: The dashboard MUST let the user mark a stop as a mistake, leave a task out, and set a
  project's limit again, with exactly the same effect as the Phase 3 commands. Each change needs a
  confirmation and the access key.
- **FR-006**: The dashboard MUST NOT show any live "tokens saved" figure. A stopped task's
  would-have-been cost is unknown, so savings are only claimed from the published evaluation
  (constitution, Principle IV).
- **FR-007**: Every word the user reads MUST be plain language (tasks, actions, limit, "fewer than 1
  in 20"), with no α symbols, scores, steps, kills or run ids on screen (Phase 3, FR-013;
  constitution 2.5.0, "Plain words"). An "action" is one tool call, and a "?" says so.

**Look and accessibility**
- **FR-008**: The dashboard MUST follow the constitution's visual identity:
  - the reel brand's colors and fonts;
  - glass only on navigation, toolbars, dialogs and floating controls, while tables, charts and
    lists sit on solid panels;
  - one icon set (Lucide), and no emoji anywhere;
  - red only as a fill, always paired with an icon and a word;
  - a light and a dark theme from the brand colors, following the system, with a remembered choice
    in Settings;
  - respect for the system's reduce-motion, reduce-transparency, high-contrast and forced-colors
    settings; under reduced transparency or more contrast, glass turns itself off. There is no
    manual glass switch.
- **FR-009**: The dashboard page MUST load nothing from the internet. Fonts, icons and code ship
  with LoopBrake (Principle VI).

**Export**
- **FR-010**: Export MUST be off by default. It turns on only through LoopBrake's own export
  setting; the standard telemetry settings used by other tools never turn it on by themselves
  (Principle VI).
- **FR-011**: When on, LoopBrake MUST send in the OpenTelemetry standard: one trace per task, one
  span per tool call, a stop as an event with the task marked as an error, and counters for tasks,
  stops, mistaken stops and tokens spent. It goes to the endpoint and headers given in the standard
  OpenTelemetry settings.
- **FR-012**: By default only metadata MUST be sent: ids, a short fingerprint for each project,
  times, tool names, counts, stop events, reason codes and token counts. Readable project names
  (which can contain local folder names and the username), action text, prompts, tool outputs and
  quoted reasons MUST be sent only with a separate content opt-in, which is off by default.
- **FR-013**: Export MUST NOT slow an agent beyond its existing per-step budget, block it, or change
  its outcome. If the backend is unreachable, records stay local and the failure is shown.
- **FR-014**: When Claude Code's own tracing passes a trace context, LoopBrake's task MUST appear
  inside that trace.
- **FR-015**: The dashboard MUST show export status: on or off, where it sends, whether content is
  included, and the last send's result. It MUST also offer a "Test connection" action.
- **FR-016**: Sending MUST follow the published intake rules of Datadog, Grafana, Honeycomb, Langfuse
  and Jaeger (checked with local stand-ins), and MUST work with a real OpenTelemetry Collector and
  Jaeger. The README says which settings and path to use for each.
- **FR-017**: The overview MUST show stops per day and tokens spent per day over the last 30 days.
  For Claude Code tasks, the tokens come from Claude Code's own history files, matched by tool call;
  other agents report their own. It MUST also show the stops marked as mistakes against how many
  would be normal (constitution, Dashboard: "kills and tokens spent over time, and the false-kill
  budget").

**Understandable by anyone (User Story 5)**
- **FR-018**: The home screen MUST open with one plain sentence on how things are going (a stop
  today, all quiet, or only watching), and MUST show each task working now with its progress
  toward the limit.
- **FR-019**: A task's page MUST show: the stop as a picture of the project's past tasks against the
  limit with this task marked; the actions it repeated, grouped, with how many times; its actions
  over time, with each point explained on hover or tap; and every action named by what it did.
- **FR-020**: Claude Code projects MUST be shown by their real folder name, read from Claude Code's
  own history on this computer. It is never exported (FR-012).
- **FR-021**: A Tasks screen MUST list every task, filterable by status and project, and searchable.
- **FR-022**: Every idea MUST have a one-line explanation one click away, and Settings MUST explain
  how LoopBrake works in three steps. When LoopBrake stops a task while the dashboard is open, a
  notice MUST appear with a link to why.

### Key Entities

- **Task**: one request's work by an agent. It has a project, a session, a start and end time, a
  status (running, finished, stopped, interrupted), its tool calls, the limit in force, and any
  marks (mistake, left out).
- **Tool call**: a tool name, a short action text, failed or not, tokens when known, and its id when
  the agent provides one.
- **Project**: a limit, the number of past tasks it came from, when it was set, the promise level,
  and its watch-only state.
- **Export setting**: on or off, the endpoint, content opt-in, and the last send's result.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A running task's new tool call shows on the dashboard within 2 seconds, every time,
  during a 50-call test task.
- **SC-002**: An automated accessibility audit scores at least 95 of 100 on every screen, in the
  light and the dark theme.
- **SC-003**: With export off, a network monitor sees zero connections leave the computer during a
  full dashboard session.
- **SC-004**: With export on, a stopped task's trace and the counters arrive end to end:
  - in a real OpenTelemetry Collector and a real Jaeger, both run on the builder's computer;
  - in local stand-ins for Datadog, Grafana, Honeycomb, Langfuse and Phoenix. Each stand-in accepts
    or rejects requests exactly as that tool's published intake rules say: address, auth header,
    JSON or not, and the metric counting style it accepts.

  The README's settings for each tool pass its stand-in. A wrong setting, such as running totals sent
  to Datadog, is rejected and shown as a failed send.
- **SC-005**: With content export off, 100% of the inspected export payloads contain no action text,
  prompt text or tool output.
- **SC-006**: With export on and the backend unreachable, the agent's added time per tool call stays
  within the existing 200 ms budget (95th percentile), and every task finishes as it would without
  export.
- **SC-007**: Every screen works both on live records and on records replayed from the published
  evaluation runs.
- **SC-008** (measured after release; not a release gate, because it needs other people): in a test
  with at least 3 people new to LoopBrake, each finds why the last task was stopped within 30
  seconds of opening the dashboard.
- **SC-009**: At phone width (9:16), no screen needs sideways scrolling, and every action can be
  reached.

## Assumptions

- **Who it's for**: one person on their own computer. A shared team dashboard is a hosted service
  for the private repository (constitution, open core), and is out of scope.
- **Data**: it reads the records that LoopBrake 0.1–0.2 already writes. No change to how agents are
  stopped.
- **Browsers**: current Chrome, Safari and Firefox. The glass refraction effect appears in Chromium
  browsers only, and the others get plain blur or solid panels.
- **No vendor accounts** (the builder's decision, 2026-10-02): export is proven against a real
  local Collector and Jaeger, plus stand-ins that follow each vendor's published intake rules. That
  shows LoopBrake sends what each tool documents. It doesn't prove the live services accept it.
  Anyone with an account can check that later; the README says so.
- **Standards**: OpenTelemetry's conventions for AI agents are still marked as in development, so
  their names may change. LoopBrake keeps them in one place.
- **Out of scope**:
  - a hosted or team dashboard;
  - the log signal, and other OpenTelemetry transports beyond the JSON one the roadmap names
    (backends that need another format are reached through a Collector);
  - live "tokens saved";
  - new ways of deciding when to stop;
  - the demo agent and the launch (Phase 5).
