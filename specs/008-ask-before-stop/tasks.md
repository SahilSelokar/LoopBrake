---

description: "Task list for asking before stopping in Claude Code (LoopBrake v0.6.0)"
---

# Tasks: Ask Before Stopping (Claude Code)

**Input**: `specs/008-ask-before-stop/`. That folder holds:
- plan.md, spec.md and research.md (R1 to R10, with the 2026-10-12 probe);
- data-model.md;
- contracts/hooks.md and contracts/plugin-and-cli.md;
- quickstart.md.

**Tests**: included. The constitution asks for a runnable check on every non-trivial path. In each
phase, the tests come first, and they must fail before the code is written.

**Rules for every commit**:
- no Claude attribution lines, and no emoji;
- the repo-local identity (SahilSelokar <sahilselokar03@gmail.com>);
- no Claude Code history content, local folder names or user names in fixtures, docs or commits
  (Principle VI). Fixtures are synthetic. The probe's logs stay in the scratch folder.

**Words**: messages inside Claude Code say "task", "tool calls" and "limit". The dashboard says
"action", and adds only the word "asked". Never "step", "τ", "α", "score", "kill" or ids on screen.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel, because it touches different files and has no unfinished dependencies.
- **[Story]**: US1 to US5, from spec.md. Paths are relative to `LoopBrake/`.

---

## Phase 1: Setup

- [ ] T001 Set version 0.6.0 and the roadmap entry:
  - set `__version__ = "0.6.0"` in `src/loopbrake/__init__.py`;
  - set `"version": "0.6.0"` in `plugin/.claude-plugin/plugin.json` and
    `codex-plugin/.codex-plugin/plugin.json`;
  - set `V=0.6.0` in `plugin/bin/loopbrake` and `codex-plugin/bin/loopbrake`. Only the launcher's
    pinned version changes for Codex, never its hook definitions (constitution, Codex "Trust");
  - add "Phase 4d: Ask before stopping (`008-ask-before-stop`), in progress" to `specs/roadmap.md` and
    to the README's Roadmap table;
  - run `uv run pytest -q tests/test_plugin_files.py` (the manifests must agree), then commit.

---

## Phase 2: Foundational: the brake's ask and answer state (blocks US1 to US3)

**Purpose**: the brake, not the adapter, holds the question and the line after an allow (Principle
V). Calls from Codex and the agent SDK, which never ask, must behave exactly as in 0.5.0.

- [ ] T002 Write failing tests in `tests/test_brake.py` for:
  - **`Brake.ask(call_id)`**: it writes an `ask` event with `step` = steps so far + 1, `ask_point`,
    `stop_line` (the line in force), `reason` and `call_id` (data-model.md). A second `ask` while the
    question is open keeps the same `ask_point`.
  - **`Brake.answer("allowed", call_id)`**: it writes one `answer` event, and from then on the run is
    compared with 2t − 1, where t is the ask point. With line 3, the next `would_stop(1)` is true
    first at 7 counted steps (the call that would be the 8th).
  - **`Brake.answer("denied", None)`**: it writes `answer` (verdict `denied`), then
    `stop` with `by: "person"`. After that, `stopped` is True and `would_stop(0)` is True.
  - **`Brake.from_events`**: it rebuilds the open question, the line after the last allowed ask point,
    and stopped with `by`.
  - **No ask events**: a brake with none behaves exactly as before. Assert the 0.5.0 stop step on the
    same inputs.
  - **The data-model.md validation rules**, quoted:
    - "`ask_point` ≥ `stop_line` + 1 at the time of asking";
    - "Each new ask point of a turn is at least twice the previous one";
    - "An `answer` follows an `ask_point` exactly once";
    - "A `stop` with `by: "person"` follows an `answer denied` in the same turn".
- [ ] T003 Implement `ask()`, `answer()`, the open question and the line after an allow in
  `src/loopbrake/brake.py`:
  - `_decide` keeps calling `method("steps")` unchanged; only the line it is given changes;
  - `stop_line` stays the calibrated value; a new `line` (or `_line()`) gives 2t − 1 after the last
    allowed ask point;
  - `would_stop()` and `_step()` use it;
  - `from_events` rebuilds it from `ask`, `answer` and `stop` events;
  - errors go through `_fail()` (watching only), as before. T002 must pass.
- [ ] T004 [P] Add a replay test (Principle II) to `tests/test_brake.py`:
  - **Setup**: a synthetic turn of 12 steps with line 3, asked at call 4 and allowed, asked at call 8
    and allowed.
  - **Check**: replayed through `Brake.from_events` after every event, it gives the same decisions as
    one live brake fed the same events.

**Checkpoint**: the brake can ask, be answered, and be rebuilt from its log. `tests/test_codex.py`
and `tests/test_agent_sdk.py` still pass unchanged.

---

## Phase 3: User Story 1: a long task asks before it is stopped (Priority: P1)

**Goal**: at the limit, in a session that can ask, the next call waits for the person. "Keep going"
lets it run, nothing is added to Claude's context, and the next question comes at twice the call.

**Independent test**: synthetic hook inputs with line 3 and `CLAUDE_CODE_ENTRYPOINT=cli`, mode
`default`:
- the 4th `pre-tool` replies `ask`;
- `tool` for that call counts it and doesn't stop;
- the next `ask` comes before call 8.

- [ ] T005 [US1] Write failing tests in `tests/test_claude_code.py` (monkeypatch
  `CLAUDE_CODE_ENTRYPOINT=cli` and pass `permission_mode: "default"`):
  - `pre-tool` for calls 1 to 3 prints nothing and counts no step;
  - the 4th `pre-tool` prints exactly
    `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": <question>}}`,
    with the question text from contracts/hooks.md, and writes `ask`;
  - `tool` for the held `tool_use_id` writes `answer allowed`, counts the step and prints nothing,
    never `continue: false`;
  - the next question comes at the 8th `pre-tool`, and its text says "asks again at 16";
  - a turn that ends within 3 calls, and a watching-only project, never ask;
  - a subagent's `pre-tool` (input with `agent_id`) is ignored;
  - a damaged log or calibration on `pre-tool` prints nothing, exits cleanly, writes no `ask`
    record, and leaves the log readable (fail-safe, FR-012).
- [ ] T006 [US1] Implement the asking path in `src/loopbrake/claude_code.py`:
  - add `"pre-tool"` to `EVENTS`;
  - `can_ask(data)`, research R3: `os.environ.get("CLAUDE_CODE_ENTRYPOINT")` is set and doesn't
    start with `sdk`, and `data.get("permission_mode")` is in
    `{"default", "acceptEdits", "plan", "auto"}`;
  - a `pre-tool` branch under the session lock, following the contracts/hooks.md table. It never
    counts a step;
  - in `tool` and `tool-failed`, when the call was held, `b.answer("allowed", call_id)` before
    `b.step(...)`. In a can-ask session, never return `_stop_reply`;
  - `question_text(b)`, the contracts/hooks.md wording, built from the same parts as `plain_stop`:
    calls so far, the limit, `one_in(alpha)`, the past-task count, the stuck sentence when a signal
    fired, "LoopBrake asks again at {2t}", and "Deny to stop the task here".

  T005 must pass. `cli.py` takes its `hook` choices from `EVENTS`; check `loopbrake hook pre-tool`
  is accepted.
- [ ] T007 [US1] Add the `PreToolUse` entry to `plugin/hooks/hooks.json`: matcher `"*"`, command
  `"${CLAUDE_PLUGIN_ROOT}/bin/loopbrake" hook pre-tool`, timeout 30 (contracts/plugin-and-cli.md).
  Extend `tests/test_plugin_files.py::test_hooks` to expect it. The Codex plugin's `hooks.json` must
  not change; assert it.
- [ ] T008 [US1] Extend `tests/test_claude_code.py::test_hook_work_is_fast` to time `pre-tool` too,
  under the same bound (constitution 2.7.0: 200 ms per hook call; research R8 measured about 65 ms
  through the launcher).

**Checkpoint**: asking and allowing work end to end on synthetic inputs.

---

## Phase 4: User Story 2: the person stops a stuck task from the question (Priority: P1)

**Goal**: "stop here" ends the task. The held call never runs, no later call past the line runs
without the person, and the turn is recorded as stopped by the person and left out of calibration.

**Independent test**: open a question, then send `stop` with no `tool` for the held call. The log
then has `answer denied`, `stop` with `by: "person"`, and `run_end stopped`.

- [ ] T009 [US2] Write failing tests in `tests/test_claude_code.py`:
  - **Closing an open question**: with the held call unrun, `stop` writes `answer denied`, then
    `stop` with `by: "person"`, then `run_end` `stopped`. A new `prompt` does the same, then opens a
    new turn counting from zero.
  - **Claude carries on after a rejection** (research R4 fallback): a later `pre-tool` with the
    question still open repeats the question. It never prints `deny`.
  - **Calls on their way** (research R5): a second `pre-tool` while the question is open prints the
    same `ask` reason and writes an `ask` with the same `ask_point`. A `tool` for either held call
    writes `answer allowed` once.
- [ ] T010 [US2] Implement the deny path in `src/loopbrake/claude_code.py`:
  - `stop` and `prompt` close an open question with `b.answer("denied", None)` before `b.end(...)`;
  - a call on its way repeats the open question.

  T009 must pass.
- [ ] T011 [P] [US2] Write calibration tests in `tests/test_calibrate.py`, with a synthetic Claude Code
  history in `tests/fixtures/` plus live records:
  - a turn asked at call 4, allowed, and finished at 50 calls counts as a good turn of length 50;
  - a turn with `answer denied` and `stop by person` is left out (`stops_left_out` +1);
  - `mistakes_counted` doesn't change.

  These run against the unchanged `calibration.py` (research R7). If one fails, fix the records
  written in T010, not the calibration code.

**Checkpoint**: both answers work. The MVP needs Phase 5 too before it can ship.

---

## Phase 5: User Story 3: when nobody can answer, it still stops (Priority: P1)

**Goal**: headless and SDK sessions, `bypassPermissions`, and unknown or missing values behave exactly
as in 0.5.0.

**Independent test**: entrypoint `sdk-cli` and line 3. `pre-tool` is always silent, and the 4th
`tool` replies `continue: false` with the 0.5.0 message, ending in the `/loopbrake:mistake` sentence.

- [ ] T012 [US3] Write failing tests in `tests/test_claude_code.py`, for each of:
  - entrypoint `sdk-cli`;
  - entrypoint `sdk-py`;
  - mode `bypassPermissions`;
  - mode `dontAsk` (unknown);
  - the environment variable unset;
  - `permission_mode` missing.

  For each, assert: no `ask` record, no `pre-tool` output, and `continue: false` at the 4th `tool`
  with the unchanged `stop_message`.
- [ ] T013 [US3] Make T012 pass in `src/loopbrake/claude_code.py`. The `can_ask()` rule from T006
  gates the `pre-tool` branch and the `tool` branch's stop reply. `stop_message()` stays word for
  word as in 0.5.0.
- [ ] T014 [US3] Run the headless check from quickstart.md §2 with a real `claude -p` against the dev
  checkout:
  - set `LOOPBRAKE_CMD="uv run --project <repo> loopbrake"`;
  - use a scratch test project calibrated to line 3.

  Record the result under a new "Hand checks" heading in research.md: 4 commands run, then the 0.5.0
  stop; a `stop` with no `by` field; no `ask`.

**Checkpoint (MVP)**: US1, US2 and US3 together are the shippable change. Asking without the deny
path or the fallback would be unsafe to release.

---

## Phase 6: User Story 4: see the questions and answers (Priority: P2)

**Goal**: status and the dashboard show questions asked, allowed and denied, in plain words.

**Independent test**: after one allowed and one denied question, status prints
"Questions asked: 2 (you let 1 keep going, you stopped 1)", and the dashboard shows both tasks with
their answers.

- [ ] T015 [P] [US4] Write failing status tests:
  - in `tests/test_records.py`: `records.status()` returns `asked` (ask points), `allowed` and
    `denied` per project;
  - in `tests/test_claude_code.py`: `status_message()` adds "Questions asked: N (you let M keep
    going, you stopped K)" right after "Tasks stopped", only when N > 0. The mistakes line counts
    only stops without `by: "person"`.
- [ ] T016 [US4] Implement T015:
  - in `src/loopbrake/records.py` `status()`;
  - in `src/loopbrake/claude_code.py` `status_message()`;
  - in `cli.py`, only if its status path needs the new fields.
- [ ] T017 [P] [US4] Write failing dashboard tests in `tests/test_dashboard.py`:
  - the task data from `dashboard.py` carries each ask point (the action number) and its answer;
  - the project summary carries `asked` and `allowed`;
  - a task stopped by the person reports it was stopped by the person;
  - the page words stay within the plain-words list, plus "asked";
  - the existing forbidden-words test still passes.
- [ ] T018 [US4] Implement T017:
  - in `src/loopbrake/dashboard.py`: task data and summary counts;
  - in `src/loopbrake/static/app.js`:
    - a marker "asked here", then "you let it keep going" or "you stopped it", at that action in the
      task view;
    - "you stopped it" in place of the stop reason's first sentence for a task stopped by the person;
    - "asked N, you let M keep going" in the project summary;
    - add "asked" to `WORDS`, with a one-line explanation next to the others;
  - styles in `src/loopbrake/static/app.css` only if needed: brand colors, red only for stopped, no
    emoji.

---

## Phase 7: User Story 5: honest words everywhere (Priority: P2)

**Goal**: everything said about Claude Code matches the new behavior, with the promise's condition
kept.

**Independent test**: the grep in T021 finds no claim, for Claude Code where a person can answer,
that good tasks get "stopped" at the old rate.

- [ ] T019 [US5] Update `README.md`, "Use it with Claude Code", per contracts/plugin-and-cli.md:
  - the question and what Allow and Deny do;
  - the second question at twice the count;
  - the fallback: "headless runs and sessions with permission prompts turned off are stopped as
    before".

  The promise must read "fewer than 1 in 20 good tasks get a question, as long as your future tasks
  are like your past ones". Also update "What a stop looks like" to show the question, and the Status
  section.
- [ ] T020 [P] [US5] Update the Claude Code wording of `calibrate_message()` in
  `src/loopbrake/claude_code.py`:
  - set up: "It will ask you before a task goes past N tool calls (and stop it where nobody can
    answer)";
  - leave the watching-only lines as they are.

  Update its test in `tests/test_claude_code.py` or `tests/test_cli.py`. Check
  `plugin/commands/calibrate.md`, `status.md` and `mistake.md` and `plugin/.claude-plugin/plugin.json`'s
  description for "stops" claims, and fix only what the new behavior makes untrue. `mistake.md` stays
  for stops where nobody could be asked.
- [ ] T021 [US5] Check the wording:
  - run `grep -rn -i "1 in 20\|stops a task\|will stop" README.md plugin/ src/loopbrake/claude_code.py`;
  - for each hit about Claude Code, confirm it describes asking, or says "where nobody can answer";
  - record the clean result in the commit message.

---

## Phase 8: Polish and release

- [ ] T022 Run `uv run pytest -q`. Everything must pass, including `tests/test_codex.py`,
  `tests/test_agent_sdk.py`, `tests/test_otlp.py` (export unchanged, FR-016) and
  `tests/test_no_network.py`.
- [ ] T023 Builder, by hand, in interactive Claude Code: run quickstart.md §3 checks M1 to M6 with
  the dev checkout through `LOOPBRAKE_CMD`, and record each result under "Hand checks" in
  research.md. Act on the results:
  - **M2**: if Claude carries on after a rejection and the repeated question is annoying, open a
    follow-up for research R4's transcript check before release.
  - **M4**: if the terminal's `CLAUDE_CODE_ENTRYPOINT` isn't `cli`, update research R3 and
    `can_ask()` (T006). A missing variable means "can't ask".
  - **M5** and **M6**: any difference from the expected result blocks the release.
- [ ] T024 Builder: before release, run `loopbrake agreement --claude-code` on real use with the dev
  checkout (constitution, "Same turns live and in calibration"). It must report no live count higher
  than the history's. Record the result in research.md.
- [ ] T025 Update `specs/roadmap.md` and the README Roadmap and Status to "Phase 4d done, v0.6.0"
  with the date, then commit.
- [ ] T026 Builder go-ahead required: push the branch, merge it to main, and tag `v0.6.0`. The
  `.github/workflows/publish.yml` workflow publishes to PyPI through trusted publishing (constitution,
  Releases). Then check
  that `uvx loopbrake==0.6.0 --version` works.
- [ ] T027 Builder, after release: recalibrate the builder's main projects at the default α 5%. The 1-in-100
  stopgap of 2026-10-12 is no longer needed, because a question costs one click. Use
  `/loopbrake:calibrate` in each project; it rewrites `~/.loopbrake/calibration/cc-*.json`. The
  0.5.0 files are backed up in the scratch folder.
- [ ] T028 Follow-up in the other repo (visual-vortex-frontend, its own approval): change "Fewer than
  1 in 20 good tasks get stopped" and its `claim(loopbrake)` note to the new README wording, under
  that site's Honest Claims rule. It appears in two places:
  - `visual-vortex-frontend/src/app/loopbrake/page.tsx`, near line 249;
  - `visual-vortex-frontend/src/app/page.tsx`, near line 326.

---

## Dependencies and order

- **Setup** (T001) comes first.
- **Foundational** (T002 to T004) blocks US1, US2 and US3.
- **US1** (T005 to T008) comes before US2 (T009 to T011): both edit `claude_code.py` and its tests, and
  the deny path closes questions that US1 opens.
- **US3** (T012 to T014) depends on `can_ask()` from T006. It can follow US1 directly, in parallel
  with US2's calibration test (T011).
- **US4** (T015 to T018) and **US5** (T019 to T021) depend on the records from US1 and US2. They are
  independent of each other.
- **Polish** (T022 to T028) comes last. T026 needs T022 to T024 passing and the builder's go-ahead.
  T027 and T028 come after the release.

## Parallel examples

```text
After T003:            T004 (replay test)  ‖  T005 (US1 tests)
During US2:            T011 (calibration tests, tests/test_calibrate.py)  ‖  T009/T010 (claude_code.py)
After US2:             T012 (US3 tests)  ‖  T015 (status tests)  ‖  T017 (dashboard tests)
US4 and US5 together:  T018 (dashboard.py, app.js)  ‖  T019 (README)  ‖  T020 (calibrate wording)
```

## Implementation strategy

1. **MVP = Phases 1 to 5** (US1, US2 and US3, all P1). Release-blocking items: tests T002, T005, T009,
   T012 and the headless check T014. Ship nothing that asks without the deny path and the
   can't-ask fallback.
2. **Then US4 and US5** (P2): status and dashboard visibility, and the honest wording. US5 is required
   before the release tag (T026), because the README and messages must match what ships.
3. **Release** after the hand checks (T023) and the agreement check (T024).
