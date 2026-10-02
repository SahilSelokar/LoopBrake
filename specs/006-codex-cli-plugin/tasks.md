---

description: "Task list for the Codex CLI plugin (LoopBrake v0.4.0, roadmap Phase 4b)"
---

# Tasks: Codex CLI Plugin

**Input**: `specs/006-codex-cli-plugin/`: plan.md, spec.md, research.md (R1–R9), data-model.md,
contracts/ (hooks.md, plugin.md, cli.md), quickstart.md

**Tests**: included. The constitution asks for a runnable check on every non-trivial path. Each
story's tests come first and must fail before its code is written.

**The gate**: Phase 2 (the probe) must pass before any later phase starts. If it fails, stop and
report to the builder (spec FR-001).

**Rules for every commit**:
- no Claude attribution lines;
- the repo-local identity (SahilSelokar <sahilselokar03@gmail.com>);
- no emoji;
- no Codex or Claude Code history content, and no local folder or user names, in fixtures, docs or
  commits (Principle VI). The probe's logs stay in the scratch folder.

**Words**: messages inside Codex say "tool calls", like the Claude Code plugin; the dashboard says
"actions". Never "step", "τ", "α", "score", "kill" or ids on screen.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel: different files, and no unfinished dependencies.
- **[Story]**: US1–US3 from spec.md. Paths are relative to `LoopBrake/`.

---

## Phase 1: Setup

- [X] T001 Set up the version and roadmap:
  - set `__version__ = "0.4.0"` in `src/loopbrake/__init__.py`, and the Claude Code plugin's version
    in `plugin/.claude-plugin/plugin.json` and `V=0.4.0` in `plugin/bin/loopbrake`, so
    `tests/test_plugin_files.py` keeps agreeing;
  - mark Phase 4b "in progress" in `specs/roadmap.md` and the README roadmap table;
  - commit.
- [X] T002 Builder, by hand: install Codex CLI (`npm install -g @openai/codex` or `brew install
  codex`) and sign in (a ChatGPT login or an OpenAI API key). Record `codex --version` in research.md
  under a new "R10. Probe results" heading.

---

## Phase 2: Foundational: the probe (the gate; research R9, quickstart scenario 0)

**Purpose**: settle research R9 on a real Codex before anything is built. Nothing in Phases 3–6
starts until T004 passes.

- [X] T003 Build a throwaway probe plugin in the scratch folder (never committed):
  - a local marketplace (`.agents/plugins/marketplace.json`) and a plugin with
    `.codex-plugin/plugin.json` and `hooks/hooks.json` hooking `UserPromptSubmit`, `PreToolUse`,
    `PostToolUse`, `Stop`, `Interrupt`, `SubagentStart` and `SubagentStop`;
  - each hook appends `{event, env PLUGIN_ROOT, stdin}` as one JSON line to a log file;
  - `PreToolUse` refuses (`permissionDecision: "deny"`) every call after the third in a `turn_id`;
    `PostToolUse` on the fourth replies `continue: false` with a `stopReason` and `systemMessage`;
  - one skill that runs `uvx --offline --from loopbrake==0.3.0 loopbrake --version` and writes a file
    under `~/.loopbrake/probe/`.
- [X] T004 Run quickstart scenario 0 and write the findings in research.md "R10. Probe results":
  - **the gate**: 10 runs of `codex exec "Run 'echo hi' ten times, one command at a time."`; at most
    4 ran and the task ended within 3 refused attempts, 10 of 10;
  - items 2–8 of R9: what the user sees; helpers' `transcript_path`; the exact `tool_name` values;
    `tool_use_id` equal to the history's `call_id`; the history's task boundaries, including a
    message sent while Codex works; installing from the local marketplace and `$PLUGIN_ROOT` in a
    hook command; the skill under the default sandbox (`uvx`, writing `~/.loopbrake`); hook times;
  - update research R1–R8, data-model.md and the contracts wherever a finding differs;
  - **if the gate fails, stop here** and report to the builder.
- [X] T005 [P] Write the pinned synthetic sample `tests/fixtures/codex_rollout.jsonl` in the exact
  shape of the probe's real session files (only made-up commands and paths): a finished task, a
  task with a hosted web search, an interrupted (`turn_aborted`) task, a task with a message sent
  while Codex worked, and a task LoopBrake stopped. Add a helper's own session file
  `tests/fixtures/codex_rollout_helper.jsonl` if T004 found helpers write separate files.

**Checkpoint**: the gate passed, and the design matches what Codex really does.

---

## Phase 3: User Story 1: stuck Codex tasks get stopped, live (Priority: P1)

**Goal**: a Codex task that goes past its limit runs no more tool calls, ends, and shows the plain
reason; failures inside LoopBrake never affect Codex.

**Independent test**: quickstart scenario 3 (limit 3, ten commands, at most 4 run, 10 of 10).

### Tests for User Story 1

- [X] T006 [P] [US1] Write `tests/test_codex.py`, per contracts/hooks.md and data-model.md:
  - `codex-prompt` opens a task whose `run_start` has `turn_id`, `transcript` and `folder` (the last
    part of `cwd`), and closes an open task as interrupted (or stopped);
  - project names: `codex-<last 40 characters of the cwd, letters, digits and dashes>-<first 6 hex of
    sha256(cwd)>`, different from the `cc-` name of the same folder;
  - `codex-tool` counts a main-agent call once: a repeated `tool_use_id` isn't counted again; a call
    whose `transcript_path` differs from the task's `transcript` is a helper's and isn't counted;
  - with limit 3, the 4th call replies exactly `{"continue": false, "stopReason": <msg>,
    "systemMessage": <msg>}` with the plain message ending "use the loopbrake-mistake skill, then
    tell Codex to continue";
  - after the stop, `codex-pre-tool` for the same `turn_id` replies the `deny` object; for another
    `turn_id`, or before any stop, it replies nothing;
  - `codex-stop` and `codex-interrupt` close the task (finished, stopped or interrupted) and never
    reply `decision: "block"`;
  - watch-only projects never reply; a `session_id` not matching `[A-Za-z0-9._-]{1,128}` is ignored;
  - failing safely: a damaged log, an unwritable home or an exception gives exit 0, no stdout, one
    stderr line, and never exit 2;
  - speed: 50 in-process `codex-tool` plus 50 `codex-pre-tool` calls stay within 10 ms each at p95.

### Implementation for User Story 1

- [X] T007 [US1] Let a task's start carry the Codex fields: `start()` and `Brake.__init__` in
  `src/loopbrake/brake.py` accept optional `extra` fields written on `run_start` (`turn_id`,
  `transcript`, `folder`); readers ignore unknown fields. Add a test in `tests/test_brake.py`.
- [X] T008 [US1] Write the adapter `src/loopbrake/codex.py` (constitution Principle V: no scoring of
  its own):
  - `project_name(cwd)`; `hook(event, stdin_text, home=None)` for the five events, under the
    session lock, reusing `records.session_events`, `records.open_turn` and `Brake.from_events`;
  - the two-part stop of contracts/hooks.md, with the message from `claude_code.plain_stop` and the
    Codex next step;
  - the `codex-pre-tool` fast path: read only whether the open task of this `turn_id` is stopped;
  - the same never-raise wrapper as `claude_code.hook`. Makes T006 pass.
- [X] T009 [US1] In `src/loopbrake/cli.py`, route `loopbrake hook codex-<event>` to `codex.hook`
  before argument parsing, always exiting 0; add a test to `tests/test_cli.py`.
- [X] T010 [US1] Write the plugin, per contracts/plugin.md (no skills; hook definitions that never
  change between versions, research R10):
  - `codex-plugin/.codex-plugin/plugin.json` (name `loopbrake`, version 0.4.0, description), using
    the field names T004 confirmed;
  - `codex-plugin/hooks/hooks.json`: the seven events of contracts/hooks.md, each running
    `"$PLUGIN_ROOT/bin/loopbrake" hook codex-<event>` with a 30 s timeout (`Interrupt` keeps 1 s);
  - `codex-plugin/bin/loopbrake`: a copy of `plugin/bin/loopbrake`, mode 755;
  - `.agents/plugins/marketplace.json`: one plugin, `loopbrake`, `git-subdir` source
    `./codex-plugin` on `main`;
  - `tests/test_plugin_files.py`: the manifest and marketplace parse; the hooks run the launcher;
    `hooks/hooks.json` holds no version (so updates need no new trust);
    the two launchers are byte for byte identical; every version agrees with `__version__`; the
    plugin isn't packaged in the wheel.
- [ ] T011 [US1] Manual, on a real Codex with `LOOPBRAKE_CMD` pointing at this checkout and a scratch
  `LOOPBRAKE_HOME`: quickstart scenarios 1 (install from the local marketplace), 3 (the live stop,
  10 of 10), 4 (failing safely, 10 of 10), 5 (helpers don't count) and 6 (speed: p95 added at most
  200 ms for the hook pair). Note the results in "Outcome".

**Checkpoint**: Codex tasks are stopped live (the MVP).

---

## Phase 4: User Story 2: set up and manage it from inside Codex (Priority: P2)

**Goal**: the limit is learned from the user's own Codex history; the five commands work as skills.

**Independent test**: quickstart scenario 2 (set the limit), and status, mistake and exclude from
the skills.

### Tests for User Story 2

- [ ] T012 [P] [US2] Add tests, against `tests/fixtures/codex_rollout.jsonl`:
  - `tests/test_traces.py`: `codex_turns()` cuts tasks at a user message and its `task_complete` or
    `turn_aborted`; steps are `function_call`, `custom_tool_call` and `local_shell_call` only; a
    hosted `web_search_call` is skipped; a message sent while Codex worked stays in the running task;
    aborted tasks are interrupted; call ids come back for matching;
  - `tests/test_calibrate.py`: Codex calibration picks only session files whose
    `session_meta.cwd` is the folder, leaves out stopped and excluded tasks, counts a mistaken stop as
    a task longer than any limit, honors `CODEX_HOME`, and never stores text from the history.

### Implementation for User Story 2

- [ ] T013 [US2] Write `codex_turns(path, exclude=(), call_ids=None)` in `src/loopbrake/traces.py`,
  the one reader of Codex session files (constitution Principle V), shaped like
  `claude_code_turns()`. Makes the traces tests pass.
- [ ] T014 [US2] Add `_from_codex(files, exclude, home, project)` in `src/loopbrake/calibration.py`
  beside `_from_claude_code` (source kind `codex`, names and sizes only in the fingerprint), and
  `codex.calibrate_codex(cwd=None, alpha=0.05, home=None)` and `codex.history_files(cwd)`
  (`$CODEX_HOME/sessions` or `~/.codex/sessions`, filtered by `session_meta.cwd`) in
  `src/loopbrake/codex.py`. Makes the calibration tests pass.
- [ ] T015 [US2] In `src/loopbrake/cli.py`, add `--codex` to `calibrate`, `status` and `agreement`
  (contracts/cli.md), with the Claude Code wording; `agreement --codex` in `src/loopbrake/codex.py`
  matches each live task to the history task holding its first call id and exits 1 if any live
  count is higher. Add tests to `tests/test_cli.py`.
- [ ] T016 [US2] The typed commands (contracts/plugin.md, research R10; they replace the skills,
  which Codex's sandbox blocks): in `src/loopbrake/codex.py`, `codex-prompt` recognizes `loopbrake:
  calibrate|status|mistake|exclude|dashboard|dashboard stop|help` (the whole message, trimmed,
  case-insensitive, colon optional), runs it in-process, opens no task, and replies with the output as
  `additionalContext` to repeat exactly. Add tests to `tests/test_codex.py`: each command's reply, a
  near-miss message ("loopbrake: status please") treated as ordinary, and no task opened.
- [ ] T017 [US2] Manual: quickstart scenario 2 on a folder with real Codex history, each skill once,
  and scenario 7 (`loopbrake agreement --codex`: live higher 0). Note the results.

**Checkpoint**: Codex users set and manage the limit without leaving Codex.

---

## Phase 5: User Story 3: Codex tasks in the dashboard and your tools (Priority: P3)

**Goal**: Codex tasks show in the dashboard, marked Codex, with plain action names, and go to the
user's tools when export is on.

**Independent test**: quickstart scenario 8.

### Tests for User Story 3

- [ ] T018 [P] [US3] Add tests:
  - `tests/test_dashboard.py`: a `codex-` task has agent `codex` and the label from its `folder`;
  - `tests/test_otlp.py`: a `codex-` task is sent with `gen_ai.agent.name` `codex` and never sends
    its `folder` or `transcript`;
  - `tests/test_static.py`: the icons of the Codex tool names exist in the sprite.

### Implementation for User Story 3

- [ ] T019 [US3] In `src/loopbrake/dashboard.py`, give `codex-` tasks the agent `codex` and the label
  from `run_start.folder`; in `src/loopbrake/otlp.py`, the agent name `codex`; in
  `src/loopbrake/static/app.js`, plain names and icons for the `tool_name` values T004 found (at
  least: commands "Ran a command", `apply_patch` "Edited files", `update_plan` "Updated its plan",
  `view_image` "Looked at an image", MCP tools "Used <server>") and a "Codex" mark on Codex tasks and
  projects. Makes T018 pass.
- [ ] T020 [US3] Manual: quickstart scenarios 8 (the dashboard live during a Codex task; export to a
  local Collector) and 9 (nothing leaves the computer with export off). Lighthouse accessibility
  stays at least 95 on a Codex task's page in both themes. Note the results.

**Checkpoint**: all three stories work.

---

## Phase 6: Polish, docs and release

- [ ] T021 Amend the constitution (PATCH, through `/speckit-constitution`): word "Failing safely" and
  "Same turns live and in calibration" for every agent plugin, not only Claude Code (plan,
  Constitution Check follow-up).
- [ ] T022 [P] The launcher fix found at v0.3.0's release, in `plugin/bin/loopbrake` and
  `codex-plugin/bin/loopbrake`: the background download on a cache miss refreshes uv's copy of
  the package list (`--refresh-package loopbrake`), so a just-released version is found; the hook
  path stays offline. Add a test to `tests/test_plugin_files.py`.
- [ ] T023 [P] README: a "Use it with Codex" section (install, the five skills, the sandbox approval
  if any, and what differs from Claude Code: no action durations, no nesting in a Codex trace); the
  roadmap table. Absolute links only; check with `readme_renderer[md]`.
- [ ] T024 Run the full suite and the release checks: pytest on 3.11–3.13; the launcher speed against
  a local 0.4.0 wheel; `claude plugin validate` for the Claude Code plugin; Codex's own plugin check
  if it has one; `loopbrake agreement --claude-code` and `--codex` on real use (live higher 0). Push
  the branch and confirm GitHub's tests pass.
- [ ] T025 Release v0.4.0, with the builder's go-ahead (a release is public): tag and push the tag;
  confirm PyPI serves 0.4.0; merge into `main` and push; confirm `main`'s tests; update the builder's
  Claude Code plugin; the builder installs the Codex plugin from the marketplace.
- [ ] T026 Wrap up: roadmap Phase 4b done, README status; note the outcomes below.

---

## Dependencies and order

- **Phase 1 → Phase 2 (the gate) → everything else.** T002 needs the builder.
- **US1** (T006–T011) needs T004 and T005. **US2** (T012–T017) needs T004 and T005, and T008 for the
  live records it calibrates against; it can run alongside US1's manual checks. **US3** (T018–T020)
  needs T007 (the `folder` field).
- **Polish**: T021–T023 any time after the gate; T024 after all stories; T025 after T024; T026 last.
- **Files touched by several tasks, in order**: `src/loopbrake/codex.py`: T008 → T014 → T015;
  `src/loopbrake/cli.py`: T009 → T015; `tests/test_plugin_files.py`: T010 → T016 → T022;
  `tests/test_cli.py`: T009 → T015.

## Parallel examples

- **After the gate**: T005 (the sample), T006 (US1 tests), T012 (US2 tests) and T018 (US3 tests)
  touch different files.
- **Inside US1**: T007 (`brake.py`) and T010 (the plugin files) are independent.
- **Polish**: T022 (launchers) and T023 (README).

## Implementation strategy

1. **MVP**: Phases 1–3. Codex tasks are stopped live, with the limit set by hand
   (`loopbrake calibrate <runs file> --project …`) if needed.
2. **Then** US2 (learned limits and the skills), then US3 (dashboard and export).
3. **Release** only after T024's checks and the builder's go-ahead.

**Total**: 26 tasks. T002, T004, T011, T017, T020 and T025 involve the builder or a real Codex.

---

## Outcome

**2026-10-02, implementation run 1**

- **T001**: package, Claude Code plugin and launcher at 0.4.0; Phase 4b marked in progress. Found
  while running the suite: `test_dashboard_command_prints_its_address_and_stops_cleanly` failed about
  1 run in 3. The dashboard printed its address before it wrote its address file and started catching
  Ctrl+C, so a Ctrl+C in that window crashed it (exit -2) instead of stopping it cleanly. The window
  came with v0.3.0's `--background` work. Now everything after the server starts sits inside the
  Ctrl+C handling, and the address is printed last, once the dashboard is ready: 15 of 15 runs pass.
- **T002**: Codex CLI 0.160.0 installed in the builder's user folder (npm). The builder has no Codex
  account, so the probe ran Codex on a local model (research R10).
- **T003–T004**: the probe plugin installed from a local marketplace. **The gate passed, 10 of 10**
  (research R10). Findings that changed the design: Codex runs hooks only after the user trusts them
  with `/hooks` (and `codex exec` skips untrusted hooks silently); commands can't run as skills under
  Codex's sandbox, so they're typed messages run by the prompt hook; task boundaries come from
  `turn_id` on both sides. Not settled: helpers (the small model never started one), and how a GPT
  model behaves after a refusal.
- **T005–T010**: the synthetic session samples (five tasks in one folder, one in another), the adapter
  `src/loopbrake/codex.py`, `loopbrake hook codex-<event>`, the plugin (`codex-plugin/`, hooks for
  seven events with no version in them) and `.agents/plugins/marketplace.json`. 230 tests pass.
