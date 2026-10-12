# Implementation Plan: Ask Before Stopping (Claude Code)

**Branch**: `008-ask-before-stop` | **Date**: 2026-10-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/008-ask-before-stop/spec.md`

## Words used in this plan

As in the spec. A **turn** is one prompt's work (one run); a **call** is one main-agent tool call (one
step); the **line** is the stop line. An **ask point** is the call at which LoopBrake asks. **Can ask**
is defined in research R3.

## Summary

In Claude Code, when a turn reaches its line and a person can answer, LoopBrake holds the next call
and asks through Claude Code's own approval prompt instead of ending the turn. The stop rule is
unchanged; only the action at the line changes.

1. **Ask, before the call** (R1, R2): a new `PreToolUse` hook calls the brake's certified
   `would_stop(1)`. If the next call would pass the line, it replies `permissionDecision: "ask"` with
   the question in plain words.
2. **Allow** (R4): a `PostToolUse` for the held call means the person said yes. The brake records it,
   moves the turn's line to the next ask point, 2t − 1 (R6), and counts the call as usual.
3. **Deny** (R4): the turn ends with nothing held having run. That is either Claude Code's interrupt
   after a rejection, or a `Stop`. The brake records `answer denied` and a `stop` with
   `by: "person"`. If Claude carries on after a rejection, its next call shows the same question
   again (R4, R5).
4. **Can't ask** (R3): headless or SDK sessions, `bypassPermissions`, or unknown values. The plugin
   behaves exactly as 0.5.0 does.
5. **Records, status, dashboard** (R7): two new events. Calibration code is unchanged.

A probe of real Claude Code (2026-10-12) settled the undocumented points that can be checked
headless. Six interactive points are hand checks before release (quickstart M1 to M6).

## Technical Context

**Language/Version**: Python 3.11+ (package); POSIX shell (the launcher, unchanged apart from its
pinned version).

**Primary Dependencies**: none at runtime (standard library only, Principle III). Claude Code 2.1.289
or later, the version probed.

**Storage**: the existing per-session run logs, with the new `ask` and `answer` events and a `by`
field on `stop` (data-model.md). Calibration files are unchanged.

**Testing**: pytest with synthetic hook inputs (as in `tests/test_claude_code.py`). There is one
headless Claude Code check and six interactive hand checks (quickstart.md).

**Target Platform**: macOS and Linux, wherever Claude Code runs with `uv` installed.

**Project Type**: a behavior change in an existing adapter and plugin of a CLI package.

**Performance Goals**: ≤ 200 ms per hook call at p95 (constitution 2.7.0, Principle III). Measured at
about 65 ms each (R8).

**Constraints**:
- Fail-safe: a broken plugin never holds or blocks a call (FR-012).
- No network on the hook path.
- The certified score is unchanged.
- No message is added to Claude's context on allow (no warn-first).

**Scale/Scope**:
- `brake.py`: ask and answer state, and the line after an allow;
- `claude_code.py`: the `pre-tool` event, the can-ask rule and the question's words;
- `hooks.json`: one new hook;
- status and dashboard lines;
- README and release 0.6.0.

## Constitution Check

*GATE: must pass before Phase 0 research. Re-checked after Phase 1 design.*
Constitution 2.7.0 (amended 2026-10-12 for this feature).

| Principle | Check | Result |
|---|---|---|
| I. Guarantee First | The first question of a turn comes at the certified line, from `would_stop(1)`, the same rule. So "at most α of good turns get a question" holds wherever the old stop bound held. Every question and every stop carries the plain reason. The guarantee's scope stays stated (README). | pass |
| II. One Scorer | The score is still `method("steps")`, called by the brake. The line after an allow (2t − 1) is the action rule constitution 2.7.0 names, and `Brake.from_events` rebuilds it from the log. A replay test with an allow asserts identical decisions live and offline. | pass |
| III. Stdlib-Only Core | No new dependency. The `pre-tool` hook is measured at about 65 ms, inside the budget, which now applies per hook call (2.7.0). | pass |
| IV. Evaluation Decides | No new signal, score or stop threshold. Asking again at 2t is not a stop rule (2.7.0). No new numbers claimed. The promise wording changes, with no new number. | pass |
| V. Thin Adapters | `claude_code.py` maps events to `Brake` calls (`would_stop`, `ask`, `answer`, `step`). The can-ask rule reads only hook input and environment, not scores. No transcript parsing is added to the hook path (R4 keeps that as a fallback only). | pass |
| VI. Local by Default | The records add a call number and the existing reason format, never tool content. Export is unchanged (spec FR-016). Probe logs stayed in the scratch folder. | pass |
| Claude Code hooks: asking before stopping | Implemented as written: hold on `ask`, allow continues with nothing added, deny refuses the rest, can't-ask stops as before. | pass |
| No warn-first in v1 | On allow, the held call runs unchanged and Claude sees nothing. On deny, the turn ends like a stop. | pass |
| Same turns live and in calibration | Steps are counted only in `PostToolUse`, as before. On deny the live count is one lower than the transcript's (the held call is in the transcript, unrun), which is the allowed side. `loopbrake agreement` runs on the builder's real use before release. | pass |
| Success labels | Allowed turns are successful at their real length; denied turns are left out (2.7.0). No code change in calibration (R7). | pass |
| Failing safely | `pre-tool` follows the same `hook()` wrapper: any error means no output and exit 0, and the call proceeds. | pass |
| Dashboard plain words | Adds only "asked" (2.7.0). | pass |

**Re-check after Phase 1 design**: unchanged, and every row passes. One spec change came from
research. FR-008 now allows a call already on its way to repeat the same question (R5), because
Claude Code can check a batch's next call before the first one finishes. That keeps the spec's
intent: no call past the line runs without the person, and none is refused without them. Complexity
Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/008-ask-before-stop/
├── spec.md              # the feature (FR-008 updated by research R5)
├── plan.md              # this file
├── research.md          # probe results and decisions R1 to R10
├── data-model.md        # ask and answer events, the stop's `by` field, state transitions
├── quickstart.md        # automated, headless and hand checks
├── contracts/
│   ├── hooks.md            # pre-tool, the changed tool/stop/prompt, the question's words
│   └── plugin-and-cli.md   # hooks.json, status lines, dashboard words, README
├── checklists/
│   └── requirements.md
└── tasks.md             # next: /speckit-tasks
```

### Source Code (repository root)

```text
src/loopbrake/
├── brake.py         # ask(), answer(), the line after an allow; from_events rebuilds both
├── claude_code.py   # EVENTS += "pre-tool"; the can-ask rule; the question text; status lines
├── records.py       # status(): questions asked, allowed, denied
├── cli.py           # `hook` accepts pre-tool (through claude_code.EVENTS)
├── dashboard.py     # "asked here" marker, summary counts
└── static/app.js    # the marker and counts on screen; "asked" in the words list (app.css only if needed)
plugin/
├── hooks/hooks.json # + PreToolUse → hook pre-tool
└── bin/loopbrake    # V=0.6.0
tests/
├── test_claude_code.py   # ask, allow, deny, calls on their way, can't ask, fail-safe, speed
├── test_brake.py         # ask/answer state and the replay test (Principle II)
├── test_calibrate.py     # allowed long turn counted; denied turn left out
├── test_dashboard.py     # asked marker and counts
├── test_records.py       # status counts of questions
└── test_plugin_files.py  # the new hook entry, the launcher's pinned version
README.md                 # Claude Code section and promise wording
pyproject.toml            # version 0.6.0
```

**Structure decision**: the existing single-package layout. No new module. `codex.py`, `agent_sdk.py`,
`watcher.py` and `otlp.py` don't change; their tests guard that.

## Complexity Tracking

No violations to justify.
