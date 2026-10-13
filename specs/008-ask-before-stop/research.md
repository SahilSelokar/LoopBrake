# Research: Ask Before Stopping (Claude Code)

**Feature**: [spec.md](spec.md) | **Date**: 2026-10-12

Sources: the Claude Code hooks documentation (checked 2026-10-12), and a probe of the real Claude Code
CLI (2.1.289, headless, model Haiku) run on 2026-10-12. The probe registered a logging hook on every
hook event and made `PreToolUse` answer `ask` for any Bash command containing a marker. Its scripts and
logs stayed in the scratch folder, as in specs/006 R10. Interactive behavior can't be probed headless;
those points are hand checks in [quickstart.md](quickstart.md) (M1 to M6).

## Probe results (2026-10-12, Claude Code 2.1.289)

| # | Run | What happened |
|---|---|---|
| A | headless, default mode, `ask` on the 1st of 2 commands | The asked command **did not run**. No `PostToolUse`, `PostToolUseFailure` or any other hook event came for it. Claude got the reason text and **went on to the 2nd command**, which ran. |
| B | headless, `--permission-mode bypassPermissions`, same | Same as A: refused, no event, Claude carried on. |
| C | headless, default mode, 3 parallel commands, no `ask` | `Pre(P1) Post(P1) Pre(P2) Pre(P3) Post(P3) Post(P2)`: a later call's `PreToolUse` can come **before** an earlier call's `PostToolUse`. |
| - | every event | `PreToolUse` and `PostToolUse` input carries `permission_mode` (`default`, `bypassPermissions` seen). Hooks inherit `CLAUDE_CODE_ENTRYPOINT`: `sdk-cli` for `claude -p`, `claude-vscode` in the VS Code extension. |
| - | registered but never fired | `PermissionRequest`, `PermissionDenied`, `Notification`. |
| - | launcher speed | `loopbrake hook` through the plugin launcher took 63 to 67 ms median and 67 to 82 ms at the slowest of 12 runs, on the builder's Mac. |

## R1. How to ask

**Decision**: in `PreToolUse`, reply
`{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": "<question>"}}`.

**Rationale**:
- The docs say `ask` shows the person a permission prompt carrying the reason, and that it forces a
  prompt even in auto-accept mode.
- The held call runs only if the person allows it. Nothing reaches Claude when they do, so there is
  no warn-first (constitution 2.7.0).

**Alternatives considered**:
- `PostToolUse` with `continue: false` (today): it ends the turn, which is the problem.
- `additionalContext` warnings to Claude: warn-first, ruled out.
- Asking Claude to judge itself: also warn-first.

## R2. Deciding before the call

**Decision**: the question comes from `PreToolUse`, using `Brake.would_stop(1)`: "would this call take
the turn past its line?" This is the certified rule that the Codex adapter already uses for calls on
their way.

**Rationale**: today the decision comes in `PostToolUse`, after the (N + 1)th call has already run.
Asking has to happen before that call.

**Effects**:
- In a session that asks, the (N + 1)th call waits for the answer.
- On a deny, the turn ends after N calls. A live count can only be lower than the history's (the
  held call is in the transcript), which is the safe side under "Same turns live and in calibration".

## R3. Who can be asked

**Decision**: ask only when both are true:
- `CLAUDE_CODE_ENTRYPOINT` doesn't start with `sdk` (not headless or Agent SDK);
- `permission_mode` is one of `default`, `acceptEdits`, `plan` or `auto`.

In every other case, including a missing or unknown value and `bypassPermissions`, stop exactly as
today: `PostToolUse` replies `continue: false`.

**Rationale**:
- Probes A and B show headless sessions refuse an asked call, after which Claude carries on.
- How `ask` behaves in an *interactive* `bypassPermissions` session is undocumented. Stopping there
  avoids relying on it.
- Unknown values fall to today's behavior, the side the spec calls safe (FR-007).

**To confirm by hand**: the terminal CLI's entrypoint value, expected `cli` (quickstart M4).

**Alternatives considered**:
- Ask everywhere and rely on headless refusal. It would need the two-part stop in headless too, and
  it changes headless from "stops at N + 1" to "refused at N + 1", against FR-007's "exactly as today".
- `CLAUDE_CODE_SESSION_ATTENDED`: undocumented, and it read `0` even in an attended VS Code session.

## R4. Telling "keep going" from "stop here"

**Decision**:
- **Allowed**: a `PostToolUse` arrives for a call that a question held.
- **Not allowed**: the turn ends (a `Stop`, or a new prompt) while no held call has run. The plugin
  records `denied`.

**Rationale**:
- Probes A and B: a refused call produces no hook event at all, so only an absence can mark it.
- In Claude Code's interactive UI, rejecting a tool call interrupts the turn and waits for the person
  (expected; confirmed by hand, quickstart M2).
- Esc at the prompt also ends the turn. That too means "don't keep going", and both kinds of turn are
  left out of calibration.

**Fallback**: if M2 shows that Claude carries on after a rejection, its next calls are past the line,
so they are asked again (R5). The person sees a second prompt and can deny again. If that proves
annoying, the next step is the transcript check below.

**Alternatives considered**:
- `PermissionDenied` or `PermissionRequest` events: none fired in the probe.
- Reading the transcript tail for the held call's rejected result. It works, but it puts transcript
  parsing on the hook path, outside the single loader (Principle V). Kept as the fallback's fallback.

## R5. Calls already on their way

**Decision**: while a question is open, any other main-agent call that is also past the line gets the
same question (`ask`, the same reason). It is never `allow`, which would run it unasked, and never
`deny`, which would act as a stop without the person. The ask point counts as allowed if any held
call runs.

**Rationale**: probe C shows that in a parallel batch, the next call's `PreToolUse` can come before
the earlier call finishes. The plugin can't wait for the person's answer inside a hook, because hooks
time out.

**Spec change**: FR-008 now reads "one ask point per question; calls already on their way at that
point may each show the same question". Updated in spec.md with this plan. Batches at the exact line
are rare (quickstart M3 shows what the person sees).

**Alternatives considered**:
- Block the hook until the first call's answer. The hook timeout (30 s) is shorter than a person's
  answer.
- Refuse the batch's other calls and let Claude retry them. That pushes an extra round trip on every
  allowed batch.

## R6. When to ask again

**Decision**: after an allow at call t, ask again when the next call would be call 2t. The brake
compares the turn's count with 2t − 1 from then on.

**Rationale**:
- The spec and constitution 2.7.0 fix this rule.
- The score is unchanged (`method("steps")`), and the first question of a good turn still comes at the
  certified line, so the bound is untouched.
- A turn twice the line gets 1 question, four times the line 2 (SC-006).

**Alternatives considered**:
- Every further line's worth (39, 78, 117): more questions on very long tasks.
- Never again: a loop that starts late would never be caught.
- A second calibrated line: it needs more history per project than most have.

## R7. Records and calibration

**Decision**: two new events in the session log, `ask` and `answer` (data-model.md). A deny also
writes the existing `stop` event, with `by: "person"`. So status, the dashboard, export and
calibration's `_live_verdicts` already treat it as a stop: left out, as stuck.

**Rationale**:
- No calibration code has to change. An allowed turn is an ordinary successful turn in the
  transcript, with its real length (every call ran).
- A denied turn is marked "out" through its `stop` event, and the transcript shows it interrupted
  anyway.
- `/loopbrake:mistake` stays for stops where nobody could be asked.

## R8. Speed

**Decision**: the `PreToolUse` hook uses the same launcher with no fast path.

**Rationale**: about 65 ms per hook call, measured, is under the 200 ms budget that applies to each
hook call (constitution 2.7.0, Principle III). The pair adds about 130 ms per tool call.

**Alternative considered**: a marker-file check in the launcher that skips Python when no question is
near. It isn't needed at these numbers.

## R9. The question's words

**Decision**: [contracts/hooks.md](contracts/hooks.md) gives the exact text. It is built by the same
`plain_stop` helper's parts, so the hook, the dashboard and export share their words. It states:
- the tool calls so far;
- the limit, and the past tasks it comes from;
- "fewer than 1 in 20";
- any stuck signal;
- what Yes and No do.

## R10. Release

**Decision**:
- Package 0.6.0 (a behavior change for Claude Code users). The launcher's pinned version moves with
  it.
- README "Claude Code" section and its promise wording (spec FR-015).
- The website's LoopBrake page updates after the release (spec Dependencies).

**Rationale**: the Codex plugin's hook definitions don't change, so Codex users don't re-trust
anything (constitution, Codex "Trust").

## Hand checks

| Check | Date, version | Result |
|---|---|---|
| Headless (quickstart §2, T014) | 2026-10-12, Claude Code 2.1.289, dev checkout through `LOOPBRAKE_CMD` and `--plugin-dir plugin` | **Pass.** `claude -p` (Haiku) asked to run `echo hi` 10 times with line 3: 4 commands ran, then the turn stopped with the 0.5.0 reason. The log has steps 1 to 4 and `stop` at 4 with no `by` field, and no `ask` or `approve` record. |
| Agreement baseline (T024, before real 0.6.0 use) | 2026-10-12, dev checkout on the builder's main Claude Code project | **Pass.** `loopbrake agreement --claude-code`: 247 turns matched, 157 equal, 90 live lower, **0 live higher**. These are 0.5.0-recorded turns; counting is unchanged in 0.6.0 (`pre-tool` counts nothing). The release check repeats this after real use with 0.6.0. |
| M1 to M6 (interactive, T023) | 2026-10-13, Claude Code 2.1.289, terminal CLI driven through a pseudo-terminal (a script typed the prompt and answered each dialog from LoopBrake's records), dev checkout through `LOOPBRAKE_CMD` and `--plugin-dir plugin`, line 3, model Haiku | All pass, below. |

Hand check details (the dialog text was read from the terminal screen):

- **M1, allow both**: the prompt read "Hook PreToolUse:Bash requires confirmation for this command: LoopBrake: this task has made 3 tool calls. In this project, good tasks almost never need more than 3 (fewer than 1 in 20 of your 19 past tasks did). Its last few tool calls repeat each other. Allow to keep going: LoopBrake asks again at 8. Deny to stop the task here.", with the options "1. Yes, 2. No". After Yes, calls 4 to 7 ran; a second question came before call 8 ("…has made 7 tool calls… asks again at 16"); after Yes, all 10 ran and the turn finished. Log: `ask 4, answer allowed, …, ask 8, answer allowed, …, run_end finished`.
- **M2, deny**: Esc at the first question. The 4th call didn't run and Claude made no further calls: Claude Code ended the turn and handed back. The next message closed it: `answer denied`, `stop` at 3 with `by: "person"`, `run_end stopped`. The new message then ran as a new turn. **Known gap**: if the person denies and then quits Claude Code without another message, the turn stays open in the log (no hook fires). Calibration isn't affected (the transcript shows the interrupt); the dashboard shows the task as idle.
- **M3, a batch across the line**: one call, then four in one message. The first two of the batch were let through (counted as on their way); the 3rd and 4th each showed the same question (`ask` twice at ask point 4), as research R5 expected. Yes on the first ran it; the other waited for its own answer. So in a batch at the line the person may answer the same question more than once.
- **M4, entrypoint**: hooks saw `CLAUDE_CODE_ENTRYPOINT=cli` in the terminal, as R3 assumed.
- **M5, `--permission-mode bypassPermissions`**: no question; the turn stopped at call 4 with the 0.5.0 message (`stop` at 4, no `by`).
- **M6, `--permission-mode acceptEdits`**: the question still appeared at 4 and at 8; both allowed, all 10 ran.
- The default interactive mode was reported as `auto` in some sessions and `default` in others; both are in the can-ask set.

## Release checks (v0.6.0, 2026-10-13)

- **Tests**: 303 passed, 1 skipped.
- **Launcher speed**, plugin launcher against the local 0.6.0 wheel (`UV_FIND_LINKS`), a session that
  can ask, 100 calls each: `pre-tool` 80 ms median and 88 ms p95; `tool` 80 ms median and 94 ms p95.
  Both are under 200 ms. All 100 steps were recorded.
- **Agreement, Claude Code**, the builder's real use: 299 turns matched, 186 equal, 113 live lower,
  **0 live higher**.
- **Agreement, Codex**: 0 turns matched. The 0.4.0 test sessions were recorded under a scratch
  LoopBrake home, so there is nothing live to compare, and the builder still has no real Codex use.
  The Codex adapter and its hooks are unchanged in 0.6.0 (only the launcher's pinned version moves),
  and its tests pass. The first real-use result is still owed (constitution 2.6.2).
