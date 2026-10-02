---

description: "Task list for the Claude Code Plugin (LoopBrake v0.2.0)"
---

# Tasks: Claude Code Plugin

**Input**: `specs/004-claude-code-plugin/`: plan.md, spec.md, research.md, data-model.md,
contracts/ (hooks.md, cli.md, plugin.md), quickstart.md

**Tests**: included. The constitution asks for a runnable check on every non-trivial path,
including hook I/O and trace loaders. Each story's tests come first and must fail before its code
is written.

**Rules for every commit**:
- no Claude attribution lines;
- the repo-local identity (SahilSelokar <sahilselokar03@gmail.com>);
- no emoji;
- no private transcript content in fixtures (Principle VI).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel: different files, and no unfinished dependencies.
- **[Story]**: US1–US3 from spec.md. Paths are relative to `LoopBrake/`.

---

## Phase 1: Setup

- [X] T001 Set up the branch and version:
  - create branch `004-claude-code-plugin` from `main` and work there; it's merged to `main` only at
    release (T032), so nobody can install a plugin that pins a version not yet on PyPI;
  - set `__version__ = "0.2.0"` in `src/loopbrake/__init__.py`;
  - set Phase 3 to "in progress" in `specs/roadmap.md`;
  - commit `specs/004-claude-code-plugin/`, the constitution amendment (2.4.0) and the roadmap as the first commit on the branch. No local folder names appear in them
    (analysis D4).
- [X] T002 [P] Write the synthetic transcript `tests/fixtures/claude_code/midturn.jsonl`, in the
  record shape of `tests/fixtures/claude_code_session.jsonl`, but with `stop_reason` on assistant
  messages. In order:
  1. **Turn p1**: prompt `p1`, then tool_use `t1` (`stop_reason: "tool_use"`) and its result, then
     a compaction summary (a user text record with `"isCompactSummary": true`), then tool_use `t2`
     (`tool_use`) and its result, then a prompt typed mid-turn (uuid `q1`), then tool_use `t3` and
     its result, then a text answer with `end_turn`.
  2. **Turn n1**: a background task notification (uuid `n1`, `"origin": {"kind": "task-notification"}`,
     text starting `<task-notification>`), then tool_use `t4`, its result, and `end_turn`.
  3. **Turn p2**: prompt `p2`, then tool_use `t5` (`tool_use`) and its result, then a user record
     `[Request interrupted by user]`.
  4. **Turn p3**: prompt `p3`, then one assistant message holding two parallel tool_uses `t6` and
     `t7`, both results, and `end_turn`.

  Add a line to `tests/fixtures/NOTICE.md` saying the file is synthetic.

---

## Phase 2: Foundational (needed by every story)

- [X] T003 [P] Add reader tests to `tests/test_traces.py` (research R1):
  - `claude_code_turns(midturn.jsonl)` gives runs `["p1", "n1", "p2", "p3"]`, with step counts
    `[3, 1, 1, 2]` and success `[True, True, False, True]`;
  - with `call_ids={}` passed in, it fills
    `{"p1": ("t1","t2","t3"), "n1": ("t4",), "p2": ("t5",), "p3": ("t6","t7")}`;
  - the existing tests on `claude_code_session.jsonl` still pass unchanged. Its assistant records
    have no `stop_reason`, which must behave as before (new turn at each prompt).
- [X] T004 Change `claude_code_turns(transcript, exclude=(), call_ids=None)` in
  `src/loopbrake/traces.py`:
  - **Track the last stop reason**: `_Turn` keeps `last_stop`, set from every main-thread assistant
    record that has a non-null `message.stop_reason`.
  - **Compaction summaries**: a user record with `isCompactSummary` true never starts a turn. Skip
    it.
  - **Prompt-like records** (not a tool_result, not meta, not the interrupt marker, not
    `<local-command`): they start a new turn only when there's no turn yet, or the turn is
    interrupted, or `turn.last_stop != "tool_use"`. Otherwise they join the running turn.
  - **Call ids**: when `call_ids` is a dict, fill `call_ids[turn id] = tuple(tool_use ids in step
    order)`.
  - **Callers**: the return value `(runs, skipped)` and `Run` stay unchanged, so `eval/run.py` and
    `calibration.py` keep working.

  Makes T003 pass.
- [X] T005 [P] Add tests to `tests/test_brake.py` for picking up an open turn (research R5):
  - **Same decisions**: a brake built with `Brake.from_events(...)` from the events of a turn with 5
    logged steps (stop line 6) says go at step 6 and stop at step 7. Those are the same decisions a
    single brake makes stepping 7 times.
  - **No second start**: no second `run_start` is written.
  - **Call ids**: `step(..., call_id="t9")` writes `"call_id": "t9"` on the `step` event, and on the
    `stop` event when it stops.
  - **Already braked**: with a `stop` event already in the events, the brake keeps answering stop,
    with the logged reason.
  - **Wording**: `unit="turns"` makes the reason say "past successful turns".
  - **Phase 2 unchanged**: `test_replay_data.py` still passes.
- [X] T006 Change `src/loopbrake/brake.py`:
  - **New `unit` argument**: add `unit="runs"` to `Brake.__init__`, used in `_explain`'s
    "past successful {unit}".
  - **New `call_id` argument**: add `call_id=None` to `step()`, recorded as `call_id` on the `step`
    event and, when it stops, on the `stop` event (left out when None).
  - **New classmethod `Brake.from_events(project, session, home, events, unit="runs")`**:
    - `events` is the open turn: its `run_start` first, then the events after it;
    - it builds the brake without writing a `run_start`, taking `run` and the calibration from the
      `run_start` event's `calibration` field;
    - each `step` event becomes `Step(action_excerpt, "", None, 0)`;
    - a `stop` event sets `stopped` and `reason`.
  - **`start()`**: gains the same `unit="runs"` keyword and passes it to `Brake`. Nothing else in it
    changes.
  - **Unchanged**: `_decide`.

  Makes T005 pass.
- [X] T007 [P] Add tests to `tests/test_records.py`:
  - **Locking**: `session_lock(home, session)` creates `runs/<session>.jsonl` with mode `0o600`.
    Eight processes that each lock, read the line count, and append one line end with 8 distinct
    counts.
  - **Open turn**: `open_turn(events)` follows data-model.md: "Find the last `run_start` … If a
    `run_end` with the same `run` comes after it, no turn is open." It returns the open turn's
    events (its `run_start` first), or None.
  - **Bad lines**: `session_events(home, session)` skips them.
  - **Last runs**: `last_run(home, "stop")` and `last_run(home, "run_end")` return the run id (and
    its events) of the most recent such event across all projects, or None.
- [X] T008 Add the following to `src/loopbrake/records.py`:
  - **`session_lock(home, session)`**: a context manager. It opens `runs/<session>.jsonl` with
    `O_WRONLY | O_APPEND | O_CREAT` and mode `0o600`, and holds `fcntl.flock(LOCK_EX)`. Where
    `fcntl` isn't available, it locks nothing
    (`# ponytail: no lock on Windows; untested platform in v1`).
  - **`session_events(home, session)`**: reads one session file. It parses only the lines from the
    last `"event": "run_start"` line onward, found by scanning the lines from the end.
  - **`open_turn(events)`** and **`last_run(home, event)`**.

  Makes T007 pass.
- [X] T009 [P] Write `src/loopbrake/claude_code.py` with project helpers, and their tests in
  `tests/test_claude_code.py` (research R6):
  - **`history_folder(cwd)`**: returns `$CLAUDE_CONFIG_DIR/projects/<slug>` (default
    `~/.claude/projects/<slug>`), where slug is `re.sub(r"[^A-Za-z0-9]", "-", str(cwd))`. Test:
    the made-up `/home/me/my app?` gives `-home-me-my-app-`, and `project_name` of that gives
    `cc-home-me-my-app-c57a41`. Never use real local folder names in tests.
  - **`project_name(folder_name)`**: returns `cc-` + the last 40 characters of
    `folder_name.lstrip("-")`, then `-` + `sha256(folder_name)` hex `[:6]`.
  - **Name tests**: the result passes `records.valid_project` ("`[A-Za-z0-9._-]{1,64}`"). Two
    folders with the same last 40 characters get different names, and a long path still fits 64
    characters.

---

## Phase 3: User Story 1: stuck turns get stopped, live (Priority: P1). MVP.

**Goal**: four hooks count main-agent tool calls per turn, and stop the turn with
`{"continue": false, "stopReason": …}` at `stop_line + 1`, using `Brake` unchanged. Without a stop
line, they only record. Nothing the plugin does can break a turn.

**Independent test**: quickstart scenario 3. With a stop line of 3, asking Claude for ten `echo hi`
calls stops right after the 4th, with the reason shown.

- [X] T010 [P] [US1] Add hook tests to `tests/test_claude_code.py`. Call `claude_code.hook(event, stdin_text, home)` with JSON shaped like Claude Code's input (`session_id`, `transcript_path` under a temporary `CLAUDE_CONFIG_DIR`, `tool_name`, `tool_input`, `tool_use_id`).
  - **Stopping** (stop line 3 written for the derived project):
    - `prompt`, then 3× `tool`, return None;
    - the 4th `tool` returns JSON `{"continue": false, "stopReason": "LoopBrake stopped at step 4: … If this stop was wrong, run /loopbrake:mistake."}`;
    - a 5th parallel `tool` also returns stop;
    - `stop` writes `run_end` with status `stopped`.
  - **Turn boundaries**:
    - `prompt`, `tool`, `prompt`: the first turn closes `interrupted`, and the second starts at count 0;
    - `prompt`, `tool`, `stop`: closes `finished`;
    - `stop`, then `tool`: the `tool` with no open turn opens a new run;
    - braked, then `prompt`: closes `stopped`;
    - `prompt`, `prompt` with no tool call in between: one open turn, no `run_end`, and no second
      `run_start` (a second prompt event is harmless, research R3).
  - **Watch-only**: no calibration means 10 `tool`s never stop, and `run_start.calibration.watch_only` is true.
  - **Ignored inputs**: an input with `agent_id` writes nothing and returns None. So does a `session_id` not matching `[A-Za-z0-9._-]{1,128}`, and a missing `transcript_path`.
  - **Failed tools**: `tool-failed` records `error: true`.
  - **Actions**: the step event's `action_excerpt` equals the first 200 characters of `f"{tool_name} {json.dumps(tool_input, sort_keys=True, ensure_ascii=False)}"`, which is the reader's format.
  - **No outputs stored**: `tool_response` text appears in no file under `LOOPBRAKE_HOME`.
  - **Failures return None and never raise**: garbage stdin, a damaged log line, a calibration file containing `{`, and a read-only `runs/` folder.
  - **Parallel steps**: 8 `loopbrake hook tool` subprocesses started at once on one open turn give step numbers 1–8 with no repeats.
  - **No network**: with sockets blocked (reuse the `tests/test_no_network.py` approach), a full turn works.
  - **SC-001 (CI)**: each turn of `midturn.jsonl` is fed through `hook` (prompt, its tool calls, stop) with stop lines 0–3. The stop step equals `brake.replay(run, {"stop_line": L, "watch_only": False})` for the reader's run.
  - **SC-001 (local)**: the same check over the builder's real history in `~/.claude/projects`, at the stop lines 10, 20 and 38. It's skipped when that folder is missing, like `tests/test_replay_data.py`. It reads private data but writes and prints nothing from it, only counts.
  - **Timing (SC-002)**:
    - the in-process `hook("tool", …)` takes at most 10 ms at p95 over 250 steps;
    - also on a session log already holding 6,300 steps, the largest local session (research R4).
- [X] T011 [US1] Write the hook handler in `src/loopbrake/claude_code.py`, per contracts/hooks.md: `hook(event, stdin_text, home=None) -> str | None`.
  - **Parsing**: parse the JSON, and ignore it (return None) when `agent_id` is present, the session id is invalid, or `transcript_path` is missing.
  - **Project**: `project_name(Path(transcript_path).parent.name)`.
  - **Locking and reading**: inside `records.session_lock`, read `open_turn(session_events(...))`.
  - **Opening a turn**: on `prompt`, an open turn with no steps that isn't braked is kept as it is. Otherwise end any open turn first (`stopped` if braked, else `interrupted`), then open one. On `tool` or `tool-failed`, open one if none is open. A new turn starts with `start(project, session=session_id, home=home, unit="turns")`.
  - **Steps**: `tool` and `tool-failed` call `step(action, tool=tool_name, error=<event is tool-failed>, call_id=tool_use_id)`. On a stop decision, return `json.dumps({"continue": False, "stopReason": "LoopBrake " + reason + ". If this stop was wrong, run /loopbrake:mistake."})`.
  - **Ending**: `stop` calls `end()` on an open turn.
  - **Errors**: catch every exception and every warning. Each becomes one stderr line, `loopbrake: …`, and the call returns None. `LOOPBRAKE_DEBUG=1` re-raises.

  Makes T010 pass.
- [X] T012 [US1] Add `loopbrake hook {prompt,tool,tool-failed,stop}` to `src/loopbrake/cli.py`. It reads all of stdin, prints `claude_code.hook(...)` when not None, and always returns 0, even on argument errors past the subcommand. Add a `tests/test_cli.py` case: piping a stop-line-crossing input prints the JSON and exits 0.
- [X] T013 [P] [US1] Write the plugin files exactly as in contracts/plugin.md:
  - **`.claude-plugin/marketplace.json`**: name `loopbrake`, owner, and one plugin entry with source `./plugin`.
  - **`plugin/.claude-plugin/plugin.json`**: version `0.2.0`.
  - **`plugin/hooks/hooks.json`**: four events, `"timeout": 30`, matcher `*` for both Post events, and the command `"${CLAUDE_PLUGIN_ROOT}/bin/loopbrake" hook <event>` with the path quoted.
  - **`plugin/bin/loopbrake`**: POSIX sh with `V=0.2.0`, `chmod 755`, committed with mode 755. It follows the four steps in contracts/plugin.md exactly:
    1. **Loop guard**: if `LOOPBRAKE_LAUNCHER` is already set, it stops; otherwise it exports `LOOPBRAKE_LAUNCHER=1`.
    2. **`LOOPBRAKE_CMD`**: execs it when it's set.
    3. **`hook`**: runs offline, then online only if that failed, then **always `exit 0`**. uv exits 2 when offline, and Claude Code treats exit 2 from a hook as blocking (research R7, constitution 2.4.0 "Failing safely").
    4. **Other commands**: a silent offline `--version` check picks offline or online, then runs the command exactly once and passes its exit code through.
- [X] T014 [P] [US1] Write `tests/test_plugin_files.py`:
  - both JSON files parse, and the marketplace entry name equals `plugin.json` `name`;
  - `plugin.json` `version`, the `loopbrake==X` pin in `plugin/bin/loopbrake`, and `loopbrake.__version__` are equal;
  - the launcher is executable;
  - `hooks.json` has exactly `UserPromptSubmit`, `PostToolUse`, `PostToolUseFailure` and `Stop`, each with `timeout` 30;
  - the wheel contents check in `tests.yml` still excludes `plugin/`;
  - **launcher behavior**: put a fake `uvx` script first on `PATH` that appends its arguments to a log file and exits with a chosen code. Then check:
    - `hook prompt` exits 0 with empty stdout when the fake exits 2, and when it exits 1;
    - `hook tool` calls uvx online only after the offline call failed, and only once;
    - `status` with the fake's offline `--version` check succeeding and the command exiting 2: one real call, and exit code 2 passed through;
    - with `LOOPBRAKE_CMD` set to the launcher's own path, `hook stop` exits 0 at once, and `status` exits 2 with the loop message.
- [X] T015 [US1] Manual: run quickstart scenarios 2–5 (local install with `LOOPBRAKE_CMD`, live stop, watch-only, failures) and `claude plugin validate .` and `claude plugin validate ./plugin`.
  - **Two unknowns from research R3**, read from the run log after a live stop:
    - does a `Stop` event follow the stop (is there a `run_end` before your next prompt)?
    - does a slash command such as `/loopbrake:status` fire `UserPromptSubmit` (does a new `run_start` appear)?
  - **If slash commands don't fire it**: add the `UserPromptExpansion` entry from contracts/plugin.md to `plugin/hooks/hooks.json`, update the `hooks.json` check in `tests/test_plugin_files.py`, and repeat the check.
  - Note the results under "Outcome" at the end of this file. **Checkpoint: MVP.**

---

## Phase 4: User Story 2: set up and manage it from inside Claude Code (Priority: P2)

**Goal**: `/loopbrake:calibrate`, `/loopbrake:status`, `/loopbrake:mistake` and `/loopbrake:exclude`
work in any project folder. Recalibration treats past LoopBrake stops as research R10 says.

**Independent test**: quickstart scenario 6.

- [X] T016 [P] [US2] Add tests to `tests/test_calibrate.py`. Build a temporary `CLAUDE_CONFIG_DIR/projects/<slug>/` folder from a helper that writes N synthetic finished turns with known tool_use ids, plus matching run logs under `LOOPBRAKE_HOME`.
  - **`calibrate_claude_code(cwd)`**:
    - uses that folder and `project_name(slug)`;
    - with 18 turns it's watch-only, and with 19 it sets a stop line;
    - when the folder is missing, it raises `FileNotFoundError` naming the expected path.
  - **R10 cases**, each changing the stop line exactly as the rule predicts:
    - a turn with a logged LoopBrake `stop` and no feedback is left out;
    - the same with `mistaken_stop` counts as infinite length (the line goes up, or turns watch-only);
    - an `exclude` on a live run drops the transcript turn holding its `call_id`s;
    - `mistaken_stop` plus `exclude` counts as mistaken.
  - **Source counts**: `source.stops_left_out` and `source.mistakes_counted` are right, and the record holds no transcript text.
- [X] T017 [US2] Change `src/loopbrake/calibration.py`:
  - **`_from_claude_code(folder, exclude, home=None, project=None)`**:
    - passes `call_ids={}` to `claude_code_turns`;
    - when `project` is given, reads that project's run logs (runs whose `run_start.project` equals it) and applies research R10 to each transcript turn whose ids contain a live run's `call_id`: mistaken counts as `math.inf`, exclude or a plain stop is left out;
    - adds `stops_left_out` and `mistakes_counted` to `source`.
  - **`calibrate_claude_code(cwd=None, *, alpha=0.05, home=None)`** (built in `src/loopbrake/claude_code.py`, not here: calibration.py importing the adapter would be a circular import): derives the folder and project, raises `FileNotFoundError(f"no Claude Code history for this folder at {path}; run loopbrake calibrate <folder> --project <name>")` when the folder is missing, and calls `calibrate`'s saving path with that project.
  - **`threshold`**: already handles `math.inf`, and is unchanged.

  Makes T016 pass.
- [X] T018 [P] [US2] Add tests to `tests/test_cli.py`, matching contracts/cli.md:
  - **`calibrate --claude-code`**: prints the project line, the stop line (or watch-only) line, the LoopBrake stops line only when there are stops, and the `saved:` line;
  - **Argument errors** (exit 2): `calibrate` with both a source and `--claude-code`, with neither, or with `--project` and `--claude-code`;
  - **`status --claude-code`**: equals `status --project <derived>`, plus the "no turns recorded yet …" line from contracts/cli.md when the project has a calibration but no recorded turns, and not otherwise;
  - **`feedback last --mistaken`**: marks the most recent `stop`'s run and prints `recorded: run … (project …, stopped at step N) marked as a mistaken stop`;
  - **`feedback last --exclude`**: marks the run of the most recent `run_end` with `steps` ≥ 1, skipping a later empty turn, and prints `… left out of future calibration`;
  - **`feedback` errors** (exit 1): no stops yet, or the same verdict twice ("already marked").
- [X] T019 [US2] In `src/loopbrake/records.py`, make `add_feedback` raise `ValueError(f"run {run!r} is already marked")` when the same verdict exists for that run. Then implement the CLI in `src/loopbrake/cli.py`:
  - **`calibrate`**: `source` becomes optional (`nargs="?"`), with `--claude-code`, and the mutual-exclusion errors from T018.
  - **`status --claude-code`**: with the "no turns recorded yet …" line.
  - **`feedback last`**: resolved through `records.last_run(home, "stop")` for `--mistaken`, or `records.last_run(home, "run_end", min_steps=1)` for `--exclude`. Add `min_steps=0` to `last_run` in T008's function.
  - **Exit codes**: `LookupError` or `ValueError` from feedback exit 1, with one stderr line.

  Makes T018 pass.
- [X] T020 [P] [US2] Write `plugin/commands/calibrate.md`, `status.md`, `mistake.md` and `exclude.md`, per contracts/plugin.md:
  - **Frontmatter**: `description`, and `allowed-tools: Bash(loopbrake <exact command>)`.
  - **Body**: tells Claude to run that single command with the Bash tool and repeat its output, adding nothing.
  - **`status.md`**: also says that when the output shows no stop line, Claude should show the status line setup line from quickstart scenario 7.
- [X] T021 [US2] Manual: run quickstart scenario 6 in two real project folders. Note the results under "Outcome".

---

## Phase 5: User Story 3: see the brake at a glance (Priority: P3)

**Goal**: `loopbrake statusline` shows `brake 12/38`, `brake 12 (watching)`, `brake stopped at 39`
or `brake idle`.

**Independent test**: quickstart scenario 7.

- [X] T022 [P] [US3] Add tests to `tests/test_claude_code.py` for `statusline(stdin_text, home)`:
  - the four states from contracts/cli.md, built with the T010 hook calls;
  - garbage stdin or an unknown session gives `brake idle`;
  - nothing under `LOOPBRAKE_HOME` changes (compare a file listing and modification times);
  - after each of 5 `tool` calls, the count equals the step count (SC-007).
- [X] T023 [US3] Implement `statusline(stdin_text, home=None) -> str` in `src/loopbrake/claude_code.py`. It reads `open_turn(session_events(...))` without a lock and never raises. Add `loopbrake statusline` to `src/loopbrake/cli.py`, which prints it and always exits 0. Makes T022 pass.
- [X] T024 [US3] Manual: run quickstart scenario 7. Note the result under "Outcome".

---

## Phase 6: Polish, agreement check, and release

- [X] T025 [P] Add `agreement` tests to `tests/test_claude_code.py`:
  - **Setup**: a temporary history folder holding `midturn.jsonl`, and run logs with live turns whose `call_id`s match `t1…t7`.
  - **One live turn with an extra step** gives one `higher` line, and `agreement()` reports 1 higher (exit 1).
  - **Equal or lower counts** report 0 higher (exit 0).
  - **Live turns whose ids aren't found** are counted as unmatched, not as errors.
- [X] T026 Implement `agreement(cwd=None, home=None)` in `src/loopbrake/claude_code.py`, plus `loopbrake agreement --claude-code` in `src/loopbrake/cli.py`, per contracts/cli.md:
  - for each live run of the derived project with at least one step, find the transcript turn holding its first `call_id` (using `call_ids` from the reader), and compare step counts;
  - print a `higher` line per higher count, then `turns matched N, equal N, live lower N, live higher N` (and `unmatched N` when it isn't 0);
  - exit 1 when any count is higher;
  - write nothing.

  Makes T025 pass.
- [X] T027 [P] Update `README.md` with a "Claude Code" section:
  - the two install commands, and the need for `uv` and Claude Code 2.1.281 or later;
  - `/loopbrake:calibrate`;
  - what a stop looks like (the contracts/hooks.md example);
  - the four commands;
  - the one-line status line setup, `uvx --offline loopbrake statusline`;
  - **No uv?** Install `loopbrake==0.2.0` another way and set `LOOPBRAKE_CMD` to its full path (`which loopbrake`), not to the bare name;
  - **Troubleshooting**: "no turns recorded yet" in status means the hooks aren't running. Check `claude --debug`, and that `uv` is on the PATH Claude Code sees.

  Also state the guarantee's scope (Principle I): marginal, per project, and holding only while live turns are like the calibration turns. Keep all links absolute and no Mermaid (the PyPI rule from Phase 2). Check with `readme_renderer`.
- [X] T028 Local re-check of the turn rule (Principle I, analysis D3). After T004:
  1. Run `uv run python eval/run.py --final --local --seed 0 --splits 1000 --boot 1000`. That's the committed reproduce command plus `--local`.
  2. In `eval/results/results.csv`, check every `local-k` row with `method` `steps` and `alpha` 0.05: `status` must be `ok`, not `invalid`. Note each group's `fk_mean`.
  3. Restore the committed files with `git checkout eval/results/`, because local rows are never committed. Before restoring, `git diff eval/results/results.md eval/results/kill-stories.md` must be empty: the public results must come out unchanged.
  4. Note the counts (group labels and rates only, never folder names) under "Outcome". Any `invalid` local row is a bug in the reader change: fix it before T030.
- [X] T029 Run the full suite over `tests/`: `uv run python -m pytest` and `uv run --with claude-agent-sdk python -m pytest tests/test_agent_sdk.py`. All must pass. Fix anything that fails before going on.
- [X] T030 Manual, over about a week (SC-008): use Claude Code normally with the plugin installed from the branch (`LOOPBRAKE_CMD` pointing at the checkout) until there are at least 200 turns. Then run `loopbrake agreement --claude-code` in each project used. **Gate**: `live higher 0`. Any higher count is a bug: fix it (reader or hooks) and repeat this task. Note the counts under "Outcome" in this file.
- [X] T031 Manual, before release:
  - re-run `claude plugin validate .` and `claude plugin validate ./plugin`;
  - check `git ls-files -s plugin/bin/loopbrake` shows mode `100755`;
  - run quickstart scenario 8 against a locally built wheel (`uv build`, `UV_FIND_LINKS=$PWD/dist`): p95 at most 200 ms through the launcher, working offline, and exit code 0 with nothing cached and no network. Note the timings under "Outcome".
- [X] T032 Manual, with the builder's go-ahead (a release is public). Done for 0.2.0 (tag `v0.2.0`, on PyPI 2026-10-02); step 3, the merge to `main`, moved to T037 so `main` pins 0.2.1:
  1. tag the head of `004-claude-code-plugin` as `v0.2.0`, and push only the tag;
  2. watch the publish workflow, and confirm PyPI shows 0.2.0 with the new README;
  3. only then merge the branch into `main` and push, so `main` never pins a version that isn't on PyPI (contracts/plugin.md).
- [ ] T033 Manual, after T032:
  - **Clean install (SC-003)**: unset `LOOPBRAKE_CMD`, uninstall the dev plugin, then run `/plugin marketplace add SahilSelokar/LoopBrake` and `/plugin install loopbrake@loopbrake`. Time it from the first command to the first watched turn: under 2 minutes.
  - **Speed and offline**: repeat quickstart scenario 8 against PyPI's 0.2.0, without `UV_FIND_LINKS`.
  - **Uninstall (FR-012)**: uninstall, and confirm nothing was left outside `~/.loopbrake` (and uv's cache).

  Note all results under "Outcome", and mark Phase 3 done in `specs/roadmap.md`.

---

## Phase 7: Release 0.2.1 (plain-language messages; research R13)

Added 2026-10-02 after `/speckit-analyze` and the plan revision. They run in this order, and each
must pass before the next.

- [X] T034 Replace the sample numbers in `README.md` with placeholders, per constitution "Public
  claims" (research R13):
  - the setup reply: `<limit>` tool calls, `<n>` past successful tasks;
  - the stop message: `<limit + 1>`, `<n>`, `<limit>`;
  - the status line: `LoopBrake: <calls> of <limit> tool calls`;
  - the diagram's "for example 38 steps", replaced with words.

  Keep "fewer than 1 in 20", which is the guarantee itself. Check with `readme_renderer`.
- [X] T035 SC-008 (b), real use since 0.2.0: for every project with live turns recorded in
  `~/.loopbrake/runs/` whose Claude Code history folder exists, run the agreement check
  (`claude_code.agreement` with that folder). **Gate**: live higher 0 in every project. Note the
  counts under "Outcome", with project labels only, never folder names.
- [ ] T036 T031's checks for 0.2.1:
  - the full suite, and GitHub's tests on 3.11–3.13;
  - `claude plugin validate` for both;
  - launcher mode `100755`;
  - quickstart scenario 8 against a locally built 0.2.1 wheel (p95 ≤ 200 ms, offline works,
    exit 0 with nothing cached).
- [ ] T037 Release:
  1. tag the branch head `v0.2.1` and push only the tag;
  2. confirm the publish workflow succeeds and PyPI serves 0.2.1;
  3. merge `004-claude-code-plugin` into `main` and push;
  4. confirm `main`'s tests pass.
- [ ] T038 Switch the builder to the public plugin (replaces T033):
  - remove the local marketplace and uninstall the dev plugin;
  - in `~/.claude/settings.json`, remove `env.LOOPBRAKE_CMD` and set the status line to
    `uvx --offline loopbrake statusline`;
  - `claude plugin marketplace add SahilSelokar/LoopBrake` and
    `claude plugin install loopbrake@loopbrake`, timed until a headless session records its first
    turn, which must be under 2 minutes (SC-003);
  - FR-012: uninstall, and confirm nothing is left outside `~/.loopbrake` and uv's cache; then
    reinstall.
- [ ] T039 Wrap up:
  - Phase 3 done in `specs/roadmap.md` (and README status);
  - update the memory note about the temporary settings;
  - outcomes noted here.

## Dependencies and order

**Phase order**:
- **Setup**: T001–T002.
- **Foundational**: T003–T009. T004 needs T002 and T003, T006 needs T005, T008 needs T007, and T009
  stands alone.
- **US1**: T010–T015, the MVP. It needs T004, T006, T008 and T009.
- **US2**: T016–T021. It needs the Foundational tasks, and T011 for the live logs used in tests.
- **US3**: T022–T024. It needs T011.
- **Polish**: T025–T033. T028 needs only T004, so it can run as soon as the reader change is in.

**Gates**:
- T028 (local re-check) and T030 (a week of real use) block T032.
- T032 needs the builder's go-ahead.
- T033 follows T032.

**Same file, in order**:
- `src/loopbrake/claude_code.py`: T009 → T011 → T023 → T026.
- `src/loopbrake/cli.py`: T012 → T019 → T023 → T026.
- `src/loopbrake/records.py`: T008 → T019.
- `tests/test_claude_code.py`: T009 → T010 → T022 → T025.

**Can run in parallel**:
- **Foundational**: T003, T005, T007 and T009 (different files).
- **US1**: T013 and T014, next to T010–T012.
- **US2**: T020, next to T016–T019.
- **Polish**: T027 next to anything, and T028 once T004 is done.

## Parallel examples

```text
Foundational: T003 (test_traces.py) | T005 (test_brake.py) | T007 (test_records.py) | T009 (claude_code.py helpers)
US1:          T010 → T011 → T012, alongside T013 (plugin files) | T014 (test_plugin_files.py)
US2:          T016 → T017, T018 → T019, alongside T020 (command files)
```

## Implementation strategy

1. **MVP**: T001–T015. Live stops work in Claude Code from the local checkout. This alone is enough
   for the launch demo moment (SC-005).
2. **Then**: US2 (setup from inside Claude Code, and safe recalibration), US3 (status line), and the
   agreement check.
3. **Last**: a week of real use (T030), then the release (T032–T033) on the builder's go-ahead.

**Total**: 33 tasks. T015, T021, T024, T028 and T030–T033 are run by hand, and T032 also needs the
builder's go-ahead.

## Outcome

**2026-10-02, implementation run 1**

- **T001–T014, T016–T020, T022, T023, T025–T027**: done. The full suite passes (see T029).
- **T013, launcher**: one change from the contract. `LOOPBRAKE_CMD` now runs through `eval`, so a
  path with spaces can be quoted inside it. The repo path itself has a space, which caught this.
  contracts/plugin.md is updated.
- **T017**: `calibrate_claude_code` lives in `claude_code.py`, to avoid a circular import.
- **SC-001 locally**: the hooks stop every one of 300 real local turns exactly where `replay()`
  does, at stop lines 10, 20 and 38. That's `test_hooks_agree_on_real_history`.
- **T028**: under the new turn rule, no local row is invalid (0 of 18). The `steps` rows with enough
  data, at α 5%:

  | Group | n | False-stop rate |
  |---|---|---|
  | local-2 | 20 | 4.05% |
  | local-5 | 20 | 4.58% |
  | local-5 | 50 | 3.68% |
  | local-5 | 100 | 4.77% |
  | local-6 | 20 | 4.61% |

  The other rows have too few runs. Public results came out unchanged: 0 public CSV rows changed,
  `kill-stories.md` was identical, and `results.md` differed only in the echoed command
  (`--local`). Restored with `git checkout eval/results/`.
- **Live checks (part of T015)**: headless `claude -p` with `--plugin-dir plugin`, a stop line of
  3, and `LOOPBRAKE_CMD` set to this checkout.
  - **Live stop**: asked for ten `echo hi` calls, Claude was stopped right after the 4th. The log
    has 4 steps with `call_id`s and a `stop` at step 4 with the reason.
  - **Research R3, first question**: no `Stop` event came after the stop. Resuming the session
    with a new prompt closed the turn as `stopped` and opened a new one, which finished normally.
  - **Research R3, second question**: `/loopbrake:status` fires `UserPromptSubmit` (a new turn
    opened, 1 step, finished), so the `UserPromptExpansion` hook isn't needed. The command worked
    through the plugin.
  - **Still to see**: in `-p` mode the stop reason isn't printed. Check that it shows in an
    interactive session.
- **Failing safely, live**: a headless session with the real launcher and no `LOOPBRAKE_CMD`
  (0.2.0 isn't on PyPI yet, so every hook call fails) still finished its turn normally ("done"),
  with nothing recorded.
- **T031, through the launcher** against the local 0.2.0 wheel (`UV_FIND_LINKS=dist`, a separate
  uv cache):
  - median 46 ms, p95 48 ms, max 74 ms over 100 `hook tool` calls;
  - with the network blocked and the cache present: exit 0 in 45 ms, steps still recorded;
  - with the network blocked and nothing cached: exit 0 with empty stdout. That first took 11.7 s
    (uv retrying), which would stall every tool call. The launcher now downloads in the
    background on a cache miss, and the same case takes 47 ms (contracts/plugin.md, research R7).
  - `claude plugin validate` passes for the marketplace and the plugin, and the launcher's git
    mode is 100755.
  - Re-run if code changes after T030.
- **T029**: 148 passed, 1 skipped (`claude-agent-sdk` not installed); with the extra,
  `tests/test_agent_sdk.py` passes 4 of 4.
- **T015, by the builder in an interactive session** (2026-10-02, `claude --plugin-dir plugin` in the
  Project Building folder, `LOOPBRAKE_CMD` set to this checkout):
  - `/loopbrake:calibrate` gave a stop line of 59 steps from 53 successful turns;
  - a turn asked for 70 `echo hi` calls was stopped right after the 60th, and the reason showed on
    screen: "PostToolUse:Bash hook stopped continuation: LoopBrake stopped at step 60: past the stop
    line of 59 steps set from your 53 past successful turns (α 5%); repeating in 5 of last 5 steps
    (similar to step 59). If this stop was wrong, run /loopbrake:mistake." (SC-005);
  - `/loopbrake:status` showed 1 stop, 3 turns watched of 4 recorded;
  - `/loopbrake:mistake` with no stop yet answered "no stops recorded yet".
  - The marketplace install route is checked at T033.
- **T021, every command through headless Claude Code** (2026-10-02; a scratch project, a separate
  `LOOPBRAKE_HOME`, and a made-up history of 25 three-step turns, so your real records stayed
  untouched). Your Project Building folder was the second project.
  - `/loopbrake:status` before calibrating: watch-only, plus the status line tip;
  - `/loopbrake:calibrate`: stop line 3 from 25 turns;
  - a turn asked for ten `echo` calls was stopped right after step 4, with the reason recorded;
  - `/loopbrake:mistake` marked that stop, and a second try was refused ("already marked");
  - `/loopbrake:exclude` marked the last finished turn;
  - `/loopbrake:status` showed 1 stop and 1 mistaken stop.
  - **Recalibration with the real test sessions added to the history**: 1 turn left out
    (excluded), 1 mistaken stop counted as a long good turn, so the result is watch-only. That's
    the cautious result research R10 predicts.
  - **Bug found and fixed**: that watch-only message said "need -12 more". Mistaken stops take the
    top places, so the count must include them: `runs_needed(alpha, unbounded=...)`. It now says
    "need 8 more". Also fixed: "1 steps", and "runs" now reads "turns" in status for Claude Code
    projects.
  - `loopbrake statusline` gave `brake stopped at 4` for the stopped session and `brake idle` for an
    unknown one.
  - `loopbrake agreement --claude-code` on these real sessions: 10 of 10 turns matched with equal
    counts, and 0 higher.
  - Claude repeats command output with "project" capitalized, even though it's asked to repeat it
    exactly. That's cosmetic.
- **Fixes after the command tests (2026-10-02)**:
  - Project names no longer have a double dash (`cc-apple-...`, not `cc--apple-...`).
  - A tool call reported twice (the plugin loaded twice) is counted once, so it can't halve the
    stop line.
  - The builder's earlier test log was moved to the new project name, and the project was
    recalibrated: stop line 58 from 60 turns. Recalibration found the 70-call test stop in the real
    transcripts by its tool call ids, and left it out as a stuck turn (research R10, live on real
    data).
- **T024**: `statusLine` was added to `~/.claude/settings.json` (backed up first), running this
  checkout until 0.2.0 is on PyPI; the command answers correctly. After release, it switches to
  `uvx --offline loopbrake statusline`.
- **T030, started**:
  - The plugin is installed from this repo as a local marketplace (`loopbrake@loopbrake`, user
    scope), with `env.LOOPBRAKE_CMD` in `~/.claude/settings.json`, so every Claude Code session
    (terminal and VS Code) runs it from this checkout.
  - A plain session with no flags recorded its turn correctly.
  - The first agreement run in Project Building gave "turns matched 5, equal 3, live lower 2,
    live higher 0". The two lower counts were real: the reader had joined the 70-call stopped turn
    and the next prompt's turn into one 61-step turn, because Claude's last answer before the stop
    still said `tool_use`.
  - **Fix**: Claude Code writes a `hook_stopped_continuation` attachment when a hook stops Claude,
    and the reader now ends the turn there (exit `stopped`, not a success; research R1). After the
    fix: "turns matched 5, equal 5, live lower 0, live higher 0". Project Building was recalibrated
    with the fixed reader.
- **T030 (SC-008), 2026-10-02: 200 turns, 0 higher.** At the builder's request the turns were
  generated, not typed by hand: 200 headless `claude -p` prompts (Sonnet), 40 sessions of 5 in
  4 scratch copies of the repo.
  - **Setup**: the installed plugin (no `--plugin-dir`), a stop line of 12, and a separate records
    folder.
  - **What the prompts did**: real coding requests (read and explain, find usages, run tests, add
    docstrings, write a test, git diff and checkout, subagent searches, parallel reads,
    `/loopbrake:status`).
  - **Results**: 200 of 200 prompts succeeded, and 205 turns were recorded (199 finished, 6 stopped
    by LoopBrake at step 13). Reported usage: $32.89.
  - **`loopbrake agreement --claude-code`**:

    | Copy | Turns matched | Equal | Live lower | Live higher |
    |---|---|---|---|---|
    | repo-1 | 40 | 31 | 9 | 0 |
    | repo-2 | 42 | 35 | 7 | 0 |
    | repo-3 | 38 | 34 | 4 | 0 |
    | repo-4 | 41 | 33 | 8 | 0 |
    | **Total** | **161** | **133** | **28** | **0** |

    The other turns made no tool calls.
  - **Every lower count has one cause**: Bash commands that Claude Code's permission system refused
    to run (62 calls: "requires approval", "cannot be checked in advance"). They fire no Post hook.
    That's research R2's predicted gap, in the safe direction.
  - **Hook-stop markers**: each stopped turn had 4–6 `hook_stopped_continuation` markers, one per
    tool call answered with stop, including calls running alongside it. The reader handled them.
  - **Subagents**: 5 ran. Claude Code keeps their transcripts in subfolders, which the reader
    doesn't read, and the hooks ignore `agent_id` events.
  - **Not covered by generated turns**: Esc interrupts, prompts typed mid-turn, and automatic
    compaction. Those stay covered by the history scan (research R1) and the unit tests.
- **Plain-language messages (0.2.1, the builder's request after 0.2.0 was published)**: everything a
  Claude Code user reads now uses everyday words ("task", "tool calls", "fewer than 1 in 20"). That
  covers the stop message, the four commands' replies, and the status line. The run records keep the
  technical reason. Version 0.2.1 in the package, `plugin.json` and the launcher. 0.2.0 stays on PyPI;
  the plugin on `main` will pin 0.2.1.
- **T034**: the README's sample replies, the status line example and the diagram now use
  placeholders (`<limit>`, `<n>`, `<calls>`) instead of numbers from the builder's history.
  "Fewer than 1 in 20" stays. `readme_renderer` passes.
- **T035, SC-008 (b)**: one project has the builder's own turns since 0.2.0 (project-1 = Project
  Building): turns matched 5, equal 5, live lower 0, live higher 0. A small sample: the plugin only
  runs in sessions started after it was installed, and the builder has worked mostly in this
  long-running session since.
- **T036**:
  - 151 passed, 1 skipped; `test_agent_sdk.py` 4 of 4; both validations pass; launcher mode
    100755;
  - local 0.2.1 wheel through the launcher: median 72 ms, p95 77 ms (46 ms earlier the same day,
    likely a busier machine; budget 200 ms);
  - network blocked and cached: exit 0, 72 ms; nothing cached: exit 0, empty stdout, 59 ms.
