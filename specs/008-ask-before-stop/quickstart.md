# Quickstart: validating Ask Before Stopping

How to check that the feature works, from unit tests to a real Claude Code session. Contracts:
[hooks.md](contracts/hooks.md) and [plugin-and-cli.md](contracts/plugin-and-cli.md). Records:
[data-model.md](data-model.md).

## 1. Automated checks (no Claude Code needed)

```sh
uv run pytest -q
```

The new tests feed synthetic hook inputs through `claude_code.hook()`, as the 0.5.0 tests do, and
cover:
- **Asking**: line 3 in a session that can ask. The 4th `pre-tool` replies `ask`, no step is counted,
  and an `ask` record is written.
- **Allow**: `tool` for the held call writes `answer allowed`, counts the step and never replies
  `continue: false`. The next question comes before call 8 (2 × 4).
- **Deny**: `stop` (or a new `prompt`) with the question open writes `answer denied`, then a `stop` with
  `by: "person"`, then `run_end stopped`. If Claude carries on instead, a `pre-tool` with the question
  still open repeats the question.
- **A call on its way**: a second `pre-tool` while the question is open repeats it (the same
  `ask_point`). A `tool` for either held call allows the ask point.
- **Can't ask**: entrypoint `sdk-cli`, mode `bypassPermissions`, or a missing value. Exactly the 0.5.0
  behavior, with `continue: false` at line + 1.
- **One scorer**: a recorded trace with an allow replays through `Brake.from_events` to the same
  decisions (Principle II).
- **Calibration**: an allowed long turn counts at its real length; a denied turn is left out.
- **Fail-safe**: a damaged log or calibration on `pre-tool` prints nothing and exits 0.
- **Speed**: `pre-tool` work stays within the existing hook-speed test.
- **Status and dashboard**: the "Questions asked" line, and the task view's "asked here" marker.
- **Codex**: its tests still pass unchanged.

## 2. Headless check (a real Claude Code, no person)

Set up a test project with a stop line of 3. Run the dev checkout through the plugin with
`LOOPBRAKE_CMD="uv run --project <repo> loopbrake"`, then:

```sh
claude -p "Run 'echo hi' with the Bash tool 10 times, one call each." --allowedTools Bash
```

**Expected**: 4 commands run, then the turn stops with LoopBrake's 0.5.0 message (spec Story 3).
`~/.loopbrake/runs/<session>.jsonl` has a `stop` with no `by` field, and no `ask`.

## 3. Hand checks in interactive Claude Code (the builder, before release)

Use the same test project, line 3, and the same prompt typed in the terminal CLI. Record each result
in research.md under "Hand checks".

| # | Check | Expected |
|---|---|---|
| M1 | Allow both questions | The 4th command waits and the prompt shows LoopBrake's question. After Yes, commands 4 to 7 run. A second question comes before command 8 (twice 4). After Yes, all 10 run and the turn finishes. |
| M2 | Deny at the first question | The 4th command doesn't run. Claude Code ends the turn and hands back to the person; or, if Claude carries on, the next call shows the question again (research R4 fallback). Once the turn ends, the log has `answer denied` and `stop by person`. |
| M3 | Ask Claude for 4 parallel commands with the line at 2 | The person sees the question once or repeated per held call (research R5). Yes lets the batch run. |
| M4 | Entrypoint value in the terminal | A debug hook line shows `CLAUDE_CODE_ENTRYPOINT=cli`. If it differs, update R3 before release. |
| M5 | `--permission-mode bypassPermissions`, interactive | No question; the turn stops at call 4 as in 0.5.0. |
| M6 | Auto-accept edits (`acceptEdits`) | The question still appears. |

## 4. Real use (spec SC-001, SC-002, SC-007)

After release, the builder uses it for two weeks on their main projects. Then:
- **Counts**: `/loopbrake:status` gives questions asked, allowed and denied, and stops. Questions
  should be at most about 1 in 20 good tasks.
- **No surprise endings**: no task ended at the line without the person choosing it.
- **No mistakes needed**: `/loopbrake:mistake` wasn't needed for asked tasks.
- **Agreement**: `loopbrake agreement --claude-code` reports no live count higher than the history's
  (constitution, "Same turns live and in calibration").
