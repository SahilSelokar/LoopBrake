# Quickstart: validate the Claude Code plugin

Runnable checks showing the feature works end to end. The formats are in
[contracts/](contracts/) and [data-model.md](data-model.md).

## Prerequisites

- `uv`, and Claude Code 2.1.281 or later (`claude --version`).
- A checkout of this repo.
- For scenarios 2 to 6, a throwaway home, so your real records stay clean:
  `export LOOPBRAKE_HOME=/tmp/lb-check`.

## 1. Automated tests

```sh
uv run python -m pytest
```

**Expect**: all tests pass. In particular:
- `test_claude_code.py`: hook flow, the lock under parallel steps, subagent skip, failures, the
  status line, no network, timing;
- `test_traces.py`: mid-turn cases;
- `test_calibrate.py`: R10 cases;
- `test_plugin_files.py`.

SC-001 is the hook-versus-`replay()` agreement test in `test_claude_code.py`.

## 2. Install the plugin from the local checkout

```sh
export LOOPBRAKE_CMD="uv run --project '$PWD' loopbrake"   # hooks use this checkout; quoted, as paths can hold spaces
claude plugin validate . && claude plugin validate ./plugin
claude plugin marketplace add ./
claude plugin install loopbrake@loopbrake
```

**Expect**: both validations pass, and `/plugin` lists `loopbrake` as enabled. Restart Claude Code
so the hooks load.

## 3. A stuck turn gets stopped (US1, SC-005)

1. Make an empty project folder (for example `/tmp/lb-demo`) and start `claude` in it.
2. Run `/loopbrake:status`. Note the project name (`cc-…`). It should be watch-only.
3. Give that project a stop line of 3 by hand. Write `$LOOPBRAKE_HOME/calibration/<project>.json`
   with every field the Phase 2 loader checks. A file missing any of them loads as damaged
   (watch-only).

   ```json
   {"v": 1, "project": "<project>", "method": "steps", "alpha": 0.05, "n": 19, "k": 19,
    "stop_line": 3, "watch_only": false,
    "source": {"kind": "claude-code", "sha256": "manual", "runs_seen": 19, "excluded": 0},
    "created": "2026-10-01", "version": "0.2.0"}
   ```

   Check it with `loopbrake status --claude-code`. It should show `stop line: 3 steps`.
4. Ask Claude: "Run `echo hi` ten times, one Bash call each."

**Expect**:
- Claude stops right after the 4th call, and the reason is shown ("LoopBrake stopped this task after
  4 tool calls …").
- `runs/<session>.jsonl` holds `run_start`, 4 `step` events with `call_id`, a `stop` with
  `call_id`, and then a `run_end` with status `stopped`, either at `Stop` or at your next prompt.

Then send any new prompt.

**Expect**: a new `run_start`, with counting from 0 again (acceptance scenario 4).

## 4. Watch-only never stops (US1 scenario 3)

Delete the calibration file and repeat step 4 of scenario 3.

**Expect**: all ten calls run, and the turn is recorded as `finished` with 10 steps.

## 5. Plugin failures never hurt a turn (SC-004)

Run step 4 of scenario 3 once in each of these setups:

| Setup | Expect |
|---|---|
| `LOOPBRAKE_CMD=/no/such/command` | All calls run. The hook error shows only in debug output (`claude --debug`). |
| `chmod 500 $LOOPBRAKE_HOME/runs` | All calls run. Nothing is recorded, and nothing is stopped. |
| The calibration file replaced with `{` | All calls run (watch-only). |

Undo each setup afterwards.

## 6. Slash commands (US2)

Run these in a project with real history (19 or more finished turns), using your real
`LOOPBRAKE_HOME`:

| Command | Expect |
|---|---|
| `/loopbrake:calibrate` | `LoopBrake is set up for this project.`, then the limit and how many past tasks it came from. A project with less history gets `Not enough history yet: …`. |
| `/loopbrake:status` | The stop line, turns watched, turns stopped, and mistaken stops against the allowance |
| `/loopbrake:mistake`, right after a stop | `Done: the stop after N tool calls is marked as a mistake. …` Status shows mistaken + 1. |
| `/loopbrake:exclude` | `Done: your last finished task (N tool calls) will be left out …` |
| `/loopbrake:calibrate` again | The output names the stops left out and the mistakes counted (research R10). The line never drops because of a marked mistake. |

Two different project folders get different `cc-…` names and their own stop lines.

## 7. Status line (US3, SC-007)

Add this to `~/.claude/settings.json`:

```json
"statusLine": {"type": "command", "command": "uvx --offline loopbrake statusline"}
```

While developing, use `uv run --project <repo> loopbrake statusline` instead.

**Expect**:
- `LoopBrake: 0 of 38 tool calls` when a task starts, counting up by one per tool call;
- `LoopBrake: ready` after the task ends;
- `LoopBrake: N tool calls (watching only)` in a project without a stop line.

## 8. Speed and offline through the real launcher (SC-002, SC-006)

This runs **before release**, against a locally built wheel. Afterwards it's repeated once against
PyPI.

1. Run `uv build`, then `export UV_FIND_LINKS=$PWD/dist` and `unset LOOPBRAKE_CMD`. uv now finds
   the new version in `dist/` even before it's on PyPI.
2. Prime the cache by piping a saved `PostToolUse` input into `plugin/bin/loopbrake hook tool`
   once, while online.
3. Time 100 more calls of the same command.
4. Turn the network off. Pipe the same input in again, then a `UserPromptSubmit` input into
   `plugin/bin/loopbrake hook prompt`.
5. Still offline, with uv's cache for loopbrake removed (`uv cache clean loopbrake`), run
   `plugin/bin/loopbrake hook prompt < input.json; echo $?`.

**Expect**:
- p95 at most 200 ms, and about 45 ms median;
- with the network off, the hook still records steps and still stops at the line;
- with nothing cached and no network, exit code `0` and empty stdout. It's never 2, which would
  block the prompt.

## 9. Live agreement (SC-008, before release)

After at least 200 turns of real use with the plugin on, run
`loopbrake agreement --claude-code` in each project you used.

**Expect**: `live higher 0`. Any higher count is a bug to fix before release (research R1, R2).

## 10. Release (after all of the above; 0.2.0 was published 2026-10-02, 0.2.1 is next)

Before tagging, do research R13's checks:
- `loopbrake agreement --claude-code` shows `live higher 0` in every project you used since the
  last release (SC-008 (b));
- scenario 8 passes against a locally built wheel;
- the README shows no numbers that don't come from committed results.

Then:
1. Tag the head of the feature branch `v0.2.1`, and push only the tag. That runs the existing
   publish workflow, and the PyPI page shows the new README.
2. Once 0.2.1 is on PyPI, merge the branch into `main` and push. That way `main` never pins a version
   that isn't on PyPI.
3. Check a clean install: `/plugin marketplace add SahilSelokar/LoopBrake`, then
   `/plugin install loopbrake@loopbrake`. Time it from the first command to the first watched turn.

**Expect**: under 2 minutes (SC-003).
