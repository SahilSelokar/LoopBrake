# Implementation Plan: Codex CLI Plugin

**Branch**: `006-codex-cli-plugin` | **Date**: 2026-10-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/006-codex-cli-plugin/spec.md`

## Words used in this plan

As in the spec: a **task** is one message's work by Codex (one run); an **action** is one main-agent
tool call (one step); the **limit** is the stop line. Codex users read "tool calls"; the dashboard
says "actions".

## Summary

LoopBrake v0.3.0 stops stuck Claude Code tasks through Claude Code's hooks. This feature does the same
for Codex CLI, with the same brake, records, dashboard and export, and a new thin adapter
(constitution, Principle V):
- **Codex's hooks** become `Brake` calls: a user message opens a task, each main-agent tool call is a
  step, `Stop` closes it, `Interrupt` marks it interrupted.
- **A stop has two parts** (research R1), because no Codex event ends a turn outright:
  - the tool call that passes the limit gets its result replaced by LoopBrake's plain reason, which
    is also shown to the user;
  - every later tool call of that task is refused.
- **The limit** is learned from the user's own Codex session files, through one new reader cut at the
  same task boundaries as the live hooks (R4).
- **The plugin** is a new `codex-plugin/` folder with hooks, five skills (the commands) and the same
  launcher, installed from this repository's Codex marketplace (R5, R6).
- **Codex tasks** show in the dashboard and export as agent `codex` (R8).

**The gate comes first** (spec FR-001): a probe on a real Codex must show that refusing every call
after the limit ends the task, within 3 refused attempts, 10 of 10. If it doesn't, the feature stops
and goes back to the builder. The probe also settles seven smaller unknowns (R9).

## Technical Context

**Language/Version**: Python 3.11+ (package), POSIX shell (the launcher), Markdown (skills).

**Primary Dependencies**: none at runtime (standard library only, constitution Principle III). Codex
CLI, a recent version with hooks and plugins; the probe pins the lowest one that works.

**Storage**: the existing per-session run logs under `~/.loopbrake/runs/`; calibration files per
project. New: optional `turn_id` and `folder` on a Codex task's `run_start` (data-model.md).

**Testing**: pytest, with a pinned synthetic Codex session file; the probe and the live checks are run
by hand on a real Codex (quickstart.md).

**Target Platform**: macOS and Linux, wherever Codex CLI runs with `uv` installed.

**Project Type**: an adapter and a plugin for an existing CLI package.

**Performance Goals**: at most 200 ms added per tool call at p95, for the `PreToolUse` and
`PostToolUse` hooks together (spec SC-002).

**Constraints**: fail safe (a broken plugin never blocks Codex); no network on the hook path; Codex
history never committed (Principle VI).

**Scale/Scope**: one adapter module, one history reader, one plugin folder with five skills, small
changes to the CLI, dashboard and export.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guarantee First | The same calibrated rule and promise. Limits are per agent and per project, so live Codex tasks are exchangeable with the Codex tasks the limit came from. Every stop carries the plain reason. | pass |
| II. One Scorer | The adapter calls `Brake.step`; no scoring of its own. The agreement check compares live and history counts for Codex. | pass |
| III. Stdlib-Only Core | No new dependency. The 200 ms per-call budget is checked for the hook pair (R7). | pass |
| IV. Evaluation Decides | No new stop signal and no new numbers claimed. No savings claimed for Codex. | pass |
| V. Thin Adapters | `codex.py` turns Codex events into `Brake` calls; Codex's history is read in one place, `codex_turns()`, checked against a pinned sample. | pass |
| VI. Local by Default | No network on the hook path; export only when turned on; fixtures synthetic; the folder name stays local and is never exported. | pass |
| Failing safely; same turns live and in calibration | Written for Claude Code; this plan applies both to Codex (contracts/hooks.md, R4). | pass, with a follow-up: a PATCH amendment that words both for every agent plugin |
| No warn-first in v1 | The model learns of the stop only after the decision, and no later tool call can run (R1). | pass |
| Dashboard plain words, visual identity | Codex tools get plain names; the dashboard is otherwise unchanged. | pass |

**Re-check after Phase 1 design**: unchanged; no violations, so Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/006-codex-cli-plugin/
├── plan.md              # this file
├── research.md          # Phase 0: Codex's hooks, history, plugins; the probe's list (R9)
├── data-model.md        # Phase 1: records and state
├── quickstart.md        # Phase 1: the probe and the live checks
├── contracts/
│   ├── hooks.md         # Codex events in, replies out
│   ├── plugin.md        # the Codex plugin, its skills and marketplace entry
│   └── cli.md           # new command options
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
src/loopbrake/
├── codex.py             # new: the Codex adapter (hooks, project names, calibrate, agreement)
├── traces.py            # + codex_turns(): the one reader of Codex session files
├── cli.py               # + hook codex-* events, calibrate/status/agreement --codex
├── dashboard.py         # + agent "codex", its label from the recorded folder
├── otlp.py              # + gen_ai.agent.name "codex"
└── static/app.js        # + plain names for Codex's tools, a "Codex" mark

codex-plugin/            # new: the Codex plugin
├── .codex-plugin/plugin.json
├── hooks/hooks.json
├── bin/loopbrake        # the same launcher as plugin/bin/loopbrake (a test keeps them identical)
└── skills/loopbrake-{calibrate,status,mistake,exclude,dashboard}/SKILL.md

.agents/plugins/marketplace.json   # new: offers codex-plugin/ to `codex plugin marketplace add`

tests/
├── test_codex.py        # new: hook replies, the two-part stop, helper calls, failing safely
├── test_traces.py       # + codex_turns on the pinned sample
├── test_plugin_files.py # + the Codex plugin: manifest, hooks, skills, launcher, versions
└── fixtures/codex_rollout.jsonl   # new, synthetic
```

**Structure Decision**: the existing single package. The Codex adapter sits beside `claude_code.py`
and shares the brake, records and messages; the Codex plugin sits beside `plugin/` because Codex
installs plugins from a subfolder (R5).

## Complexity Tracking

No violations.
