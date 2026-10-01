# Implementation Plan: Claude Code Plugin

**Branch**: `004-claude-code-plugin` | **Date**: 2026-10-01 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-claude-code-plugin/spec.md`

## Words used in this plan

As in the spec:
- **turn**: one answer from Claude; it's one run;
- **step**: one main-agent tool call;
- **stop line**: the most steps a turn may take;
- **braked**: a turn LoopBrake has told to stop.

## Summary

The plugin puts the v0.1.0 brake inside Claude Code. Four hooks turn Claude Code events into
`Brake` calls:
- a prompt opens a turn;
- each tool call is a step;
- `Stop` closes the turn.

When a turn passes its project's stop line, the hook replies `continue: false` with LoopBrake's
reason.

**How the pieces fit**:
- **State**: there's no new state store. Each hook locks the session's run log, reads the open turn
  back from it, and appends through `Brake`, the same code the experiments certified.
- **Startup**: a small launcher runs the pinned package from uv's cache without network (about 45 ms
  per call).
- **Slash commands**: calibrate, status, mistake and exclude.
- **Status line**: a `statusline` command shows the count.

**What research found** (all in [research.md](research.md)):
- **Turn boundaries**: 18 of 1,351 turn starts in local history (1.3%, mostly automatic
  compaction) come in the middle of a running turn. The calibration reader split turns there, which would lower the stop line on exactly the
  long turns. The reader now keeps those inside the running turn, matching what the live hooks see
  (R1).
- **Recalibration**: once the brake is on, the history contains turns it cut short. A stop the user
  marked a mistake now counts as a good turn longer than any line, and other stops are left out
  (R10). Without this, every recalibration would drift the line down.
- **Plain `uvx`** re-checks PyPI every 10 minutes (206 ms, and it needs the network). The launcher
  uses `--offline` first. uv also exits with code 2 when offline, and Claude Code treats exit 2 from
  a hook as blocking, so the launcher's hook path always exits 0 (R7, constitution 2.4.0).

Package v0.2.0 ships the new commands, the reader change, and the fixed PyPI README.

## Technical Context

| Item | Value |
|---|---|
| **Language/Version** | Python 3.11+ (CI on 3.11, 3.12 and 3.13); POSIX `sh` for the launcher |
| **Primary Dependencies** | None at runtime (`fcntl`, `json`, `hashlib`, `re` from the standard library). Users need `uv` and Claude Code 2.1.281 or later. |
| **Storage** | Phase 2's files under `~/.loopbrake`: `runs/<session>.jsonl` (the only live state), `calibration/<project>.json`, `exclude.txt`. No new files. |
| **Testing** | pytest. Hook tests feed JSON on stdin to `cli.main()` with a temporary `LOOPBRAKE_HOME`. Parallel steps run as separate processes to test the lock. Also: a fixture transcript for the reader change (synthetic, Principle VI), a no-network test on the hook path, a timing test, and a plugin files test (JSON, names, versions, launcher mode). |
| **Target Platform** | macOS and Linux. Windows is untested (no `fcntl`, so no lock). |
| **Project Type** | Library + CLI + Claude Code plugin (static files) |
| **Performance Goals** | Hook work after stdin of at most 10 ms; the whole hook command at most 200 ms at p95 (SC-002); about 45 ms expected (R7) |
| **Constraints** | Never blocks or breaks a turn because of its own failure (FR-004). No network on the hook path (SC-006). The decision is `Brake` unchanged (Principle II). No warnings before a stop. |
| **Scale/Scope** | Sessions up to 6,300 steps (the largest local one: a 2.7 MB log, read in about 2 ms per hook, measured); one calibration per project |

No open questions remain. Measured facts and the doc quotes are in research.md.

## Constitution Check

*GATE: must pass before Phase 0 research. Checked again after the Phase 1 design. Checked against
constitution 2.4.0, which wrote the turn rule, fail-safe hooks and the mistaken-stop rule into the
technical constraints after `/speckit-analyze` found the plan going beyond 2.3.0's text.*

| Rule | Before | After | Why it passes |
|---|---|---|---|
| I. Guarantee First | PASS | PASS | The stop line still comes from `conformal.threshold`, and watch-only when k > n. Live and calibration turns are cut the same way (R1); every known difference can only make live counts lower. SC-008 checks this on real use, and `loopbrake agreement` fails on any higher count. Recalibration treats mistaken stops conservatively (R10). The reader change touches no committed result; a task re-checks the local rows anyway. Every stop carries a reason. |
| II. One Scorer | PASS | PASS | The hook calls `Brake.step()`, which calls `_decide` with `method("steps")`. No hook-side decision. The Phase 2 replay test still runs, and a new test replays fixture turns through `loopbrake hook` against `replay()` (SC-001). |
| III. Stdlib-Only Core | PASS | PASS | Standard library only. About 45 ms per hook, measured, against the 200 ms budget. |
| IV. Evaluation Decides | PASS | PASS | No new stop rule. The step budget is the one with committed results. |
| V. Thin Adapters | PASS | PASS | `claude_code.py` turns hook JSON into `Brake` calls and decisions into Claude Code's reply. Transcript parsing stays in the single loader `traces.claude_code_turns`, whose fixture test gains the mid-turn cases. |
| VI. Local by Default | PASS | PASS | The hook path makes no network calls (tested by blocking sockets). The only download is uv fetching the package the first time. No tool outputs or prompts are written; action excerpts stay at 200 characters at most. |
| Tech constraint: Claude Code integration (2.4.0) | PASS | PASS | Repo-as-marketplace. Post hooks with matcher `*` count main-agent calls; a stop is `continue: false` with `stopReason`. Turns start at UserPromptSubmit or the first call after Stop, and end at Stop or the next prompt (R1). The reader cuts the same way, and `loopbrake agreement` checks it before release. The hook path always exits 0 (R7). |
| Tech constraint: State | PASS | PASS | The per-session run log is the single source for live state and the status line (R4). |
| Tech constraint: Success labels (2.4.0) | PASS | PASS | Not interrupted, not stopped; `/loopbrake:exclude` drops a turn. Mistaken stops count as successes longer than any line, and other stops are left out (R10). |
| No warn-first in v1 | PASS | PASS | Nothing is sent to Claude before the stop. |
| Releases (2.3.0) | PASS | PASS | v0.2.0 goes through the existing tag workflow. The plugin is static files in the public repo. |
| Simplicity | PASS | PASS | One new module, one launcher script, static plugin files. See Complexity Tracking for the two shortcuts. |

## Project Structure

### Documentation (this feature)

```text
specs/004-claude-code-plugin/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/
│   ├── hooks.md      # loopbrake hook <event>: input, output, decision, timing
│   ├── cli.md        # calibrate/status --claude-code, feedback last, agreement, statusline
│   └── plugin.md     # marketplace, manifest, hooks.json, launcher, commands, version rule
├── checklists/requirements.md
└── tasks.md          # created next by /speckit-tasks
```

### Source code (changes)

```text
src/loopbrake/__init__.py       __version__ = "0.2.0"
src/loopbrake/brake.py          pick up an open turn from its logged events (no second run_start); step(call_id=…); "turns" wording
src/loopbrake/traces.py         claude_code_turns: mid-turn prompts, notifications and compaction summaries join the running turn; each turn carries its tool call ids
src/loopbrake/calibration.py    Claude Code source: apply live stops, mistakes and excludes by call id (R10); two new source counts
src/loopbrake/records.py        locked open-and-read of a session log; open turn from events; last stop / last closed turn
src/loopbrake/claude_code.py    new: project from history folder, hook handlers (prompt, tool, tool-failed, stop), statusline, agreement
src/loopbrake/cli.py            hook, statusline, agreement; --claude-code on calibrate and status; feedback last
.claude-plugin/marketplace.json new
plugin/                         new: .claude-plugin/plugin.json, hooks/hooks.json, bin/loopbrake, commands/*.md
tests/test_claude_code.py       new: hook flow, stop at stop_line + 1, parallel lock, subagent skip, failures, statusline, no network, timing
tests/test_traces.py            more: mid-turn cases, tool call ids (synthetic fixture)
tests/test_calibrate.py         more: R10 cases, --claude-code project naming
tests/test_plugin_files.py      new: manifests, names, version agreement, launcher executable, launcher exit codes and retries (fake uvx)
tests/fixtures/claude_code/     synthetic transcripts with mid-turn records
README.md                       Claude Code section: install, calibrate, status line, what a stop looks like
specs/roadmap.md                Phase 3 status
```

Untouched: `signals.py`, `conformal.py`, `agent_sdk.py`, and everything under `eval/`. Committed results
hold no Claude Code rows, so the reader change needs no correction note (research R1).

**Structure decision**:
- **Package**: the new adapter is one module, `claude_code.py`, next to `agent_sdk.py`.
- **Plugin**: lives in `plugin/`, so the marketplace root stays clean.
- **Packaging**: `plugin/` and `.claude-plugin/` aren't part of the wheel. The existing contents
  check keeps it that way.

## Complexity Tracking

No constitution rule is broken. Two deliberate shortcuts:

| Shortcut | Limit | Fix if it becomes a problem |
|---|---|---|
| Each hook reads the whole session log (parsing only the open turn) | 2.7 MB for the largest local session, about 2 ms (measured) | Seek back from the end of the file to the last `run_start` |
| A shell launcher instead of calling `uvx` directly from `hooks.json` | One more file, and POSIX `sh` only | None needed. It's what makes the hook work offline and under budget (R7). |
