# Research: Claude Code Plugin

**Feature**: [spec.md](spec.md) | **Date**: 2026-10-01

**Sources**:
- **Claude Code docs**: the hooks reference, the hooks guide, plugin creation, and plugin marketplaces.
- **Local measurements** on the builder's M3 Pro, with Claude Code 2.1.285.
- **A scan of all local Claude Code history**: 12 projects, about 1,350 turn starts.

Each point gives the decision, why, and what else was considered.

## R1. Where a turn starts and ends, and what counts as a step

**The problem**: the stop line is measured on turns as the calibration reader cuts them out of
transcripts. Live, the plugin must cut turns the same way, or the guarantee is about a different
thing. Counting more steps live than calibration saw is the dangerous direction, because it causes
extra false stops. Counting fewer only stops later.

**What the history scan found**: of 1,351 turn starts, 1,298 came right after Claude finished
answering. 35 came after the user pressed Esc, and the reader already ends the turn there as
interrupted. 18 (1.3%) fall *inside* a running turn, where Claude was still waiting on a tool:

| Kind of record | Inside a running turn |
|---|---|
| Summary after automatic compaction | 15 |
| Prompt typed while Claude was working | 2 |
| Background task notification | 1 |

Today the reader starts a new turn at each of these, but Claude Code doesn't. The live turn keeps
going, so live counts would be higher than calibration's on exactly the long turns.

**Decision**:

The live hooks:

| Event | What the plugin does |
|---|---|
| `UserPromptSubmit` | Closes any open run (as `interrupted`, or `stopped` if braked), then opens a new run |
| `PostToolUse` | One step, for a tool call that succeeded |
| `PostToolUseFailure` | One step, for a tool call that failed |
| `Stop` | Closes the run (`finished`, or `stopped` if braked) |

- **A step with no open run**: it opens one first. This happens when a background task wakes Claude
  after a `Stop`.
- **Subagents**: inputs that carry `agent_id` are ignored, as calibration ignores subagent
  transcripts. `agent_type` alone doesn't count, because it's also set on the main thread when a
  session runs with `--agent`.

The calibration reader (`traces.claude_code_turns`):
- **When a turn starts**: a prompt starts a new turn only when the previous turn is over. That
  means its last main-thread answer stopped for a reason other than `tool_use`, or it was
  interrupted.
- **Mid-turn records**: a prompt, notification or compaction summary that arrives while Claude is
  waiting on a tool joins the current turn.
- **Compaction summaries**: they never start a turn.

**Why**: after this change, the remaining known differences can only make live counts *lower*:
- tool calls denied at a permission prompt (R2);
- a queued prompt that fires `UserPromptSubmit` mid-turn, which would split a live turn that
  calibration keeps whole.

Both make stops later, never earlier. The live check in spec SC-008 measures the real agreement.

**Alternatives considered**:
- **Turns defined only by `UserPromptSubmit`**: no. Steps after a background-task wake-up would join
  the previous turn, which is the dangerous direction.
- **Keep the reader as it is**: no. It cuts long turns short, which lowers the stop line on exactly
  the turns that matter.

**Effect on Phase 1**: the reader change only touches Claude Code history, which the evaluation loads
only with `--local`.
- **Committed results**: `eval/results/results.csv` has no `local-k` rows (checked). The public
  held-out splits that Principle I judges don't use this reader, so no committed number changes.
- **Local check**: a task still re-runs the local rows under the new turn rule, and confirms the
  step budget's false-stop rate stays within α on the builder's own history (analysis D3). Those
  rows stay local, as before.

## R2. Gaps between live counts and transcript counts

| Case | Live vs transcript | Direction |
|---|---|---|
| A tool call denied at a permission prompt | Likely not counted live: the docs don't promise a Post event | Lower, so safe |
| A tool call blocked by another plugin's PreToolUse hook | Not counted live | Lower, so safe |
| A Claude Code version without `PostToolUseFailure` | Failed calls not counted | Lower, so safe |
| Parallel tool calls | Each fires its own Post event, and each is one `tool_use` block | Equal |

**Live agreement check (SC-008)**: `loopbrake agreement --claude-code` compares each recorded live
turn with the reader's turn that holds the same tool call ids. It's run after a week of real use,
and before every plugin release.

The docs also list a `PermissionDenied` event, but only for auto mode's denials. It isn't counted:
a denied call never ran, so not counting it is the safe direction.

## R3. How a stop is delivered

**Decision**: on a stop, the Post hook prints `{"continue": false, "stopReason": "<reason>"}` and
exits 0.

The hooks reference lists `continue` as a field every hook can return: "If `false`, Claude stops
processing entirely after the hook runs". It adds that "for `PreToolUse` and `PostToolUse` hooks,
the stop applies even when the tool call fails or completes while Claude is still streaming a
response". `stopReason` is the "message shown to the user when `continue` is `false`". It stays in
the conversation, so Claude sees it if the user continues.

**What happens next**:
- **Parallel tool calls** still in flight get the same answer, because a braked run keeps saying
  stop.
- **The `Stop` event**: the docs don't say whether it fires afterwards. If it doesn't, the next
  `UserPromptSubmit` closes the run as `stopped`.
- **Slash commands**: the docs don't say whether a slash command fires `UserPromptSubmit`. A
  separate `UserPromptExpansion` event exists for typed commands.

**The risk if both answers are "no"**: the stopped turn stays open. `/loopbrake:mistake`'s own Bash
call then joins that braked turn and is told to stop, so Claude stops before reporting. The
feedback is still recorded.

**Decision**:
- **Make `prompt` safe to fire twice**: on an open turn with no steps that isn't braked, it does
  nothing.
- **Measure both unknowns in T015**: if slash commands don't fire `UserPromptSubmit`, also register
  `UserPromptExpansion` to `loopbrake hook prompt`. The first rule makes double firing harmless.

## R4. State between hook calls

**Facts**:
- Every hook call is a new process.
- The transcript is written asynchronously and can lag behind the hooks, so hooks can't count from
  it.

**Decision**: the session's run log, `runs/<session>.jsonl`, *is* the state, as the constitution
asks ("the single source for live state, the dashboard and the status line"). Each hook:
1. **Locks the log**: opens it for appending, then takes an exclusive `fcntl.flock` on that file.
   Parallel tool calls fire Post hooks at the same moment, and without the lock two of them could
   both read step 7 and both write step 8.
2. **Reads the open turn**: reads the file, finds the last `run_start`, and takes the events after
   it. That gives the run id, the calibration in force, the steps so far, and any `stop`. If a
   `run_end` follows it, no turn is open.
3. **Hands over to `Brake`**: picks up the turn in a `Brake` (R5) and appends the new events through
   it.
4. **Unlocks**.

**Why**:
- **No new file format** and nothing to clean up.
- **One reader**: the status line and the Phase 4 dashboard read the same thing.

**Measured cost**:
- **Biggest log**: the largest local session holds 6,300 main-agent tool calls. Its run log would be
  about 2.7 MB, with one excerpt-length line per step.
- **Time per hook**: reading that file, finding the last `run_start` from the end, and parsing only
  the open turn took 2.0 ms median, 2.3 ms p95, over 200 runs. That's well inside the hook's 10 ms
  share.
`# ponytail: reads the whole session log per hook; seek from the end if logs ever reach tens of MB.`

**Windows**: there's no `fcntl` there, so it runs without the lock. Windows is untested in v1.

**Alternatives considered**: a separate per-session state file. That would mean a second format,
deletion rules, and a break from the constitution's single source, all to save about 2 ms per hook.

## R5. Using the brake exactly as certified

**Decision**: the hook uses `Brake` itself, so it doesn't copy its logic.
- **Continuing a run**: `Brake` gets a way to pick up a run in a new process from its logged events
  (the `run_start` calibration, the step events, any `stop`), without writing a second `run_start`.
- **The steps it rebuilds**: each logged step becomes `Step(action_excerpt, "", None, 0)`. The
  `steps` rule only looks at how many steps there are, so the decision is exact.
- **Tool call ids**: `Brake.step()` gains an optional `call_id`. It's recorded on `step` and `stop`
  events, which is how calibration (R10) and the live check (R2) find the same tool call in the
  transcript.
- **The reason**: it says "turns" instead of "runs" when the source is Claude Code.

**Why**: Principle II, one decision function for evaluation, the package and the plugin.

**Limit**: the log keeps actions (up to 200 characters) but no tool outputs (FR-010). So in the
plugin, reasons name repeats ("repeating in 5 of last 5 steps"), but not "nothing new" or "same
error again". With `error` set to `None`, the error signal reads the empty output and never fires,
so it can't claim a false "same error". Explanation only; it never decides.

## R6. Project identity

**Decision**: a project is the folder Claude Code keeps its history in.
- **In hooks**: the folder holding `transcript_path`.
- **For calibration**: that folder's name is the working folder with every character other than a
  letter or digit replaced by `-`, under `$CLAUDE_CONFIG_DIR/projects/` (default
  `~/.claude/projects/`). This was checked against all 12 local folders. For example, a folder
  `/home/me/my app?` becomes `-home-me-my-app-`. (The example is made up: local folder names never
  go into the repo.)
- **Project name**: `cc-` + the last 40 characters of the folder name, without leading `-`, then `-`
  + the first 6 hex characters of the folder name's sha256. That fits LoopBrake's name rule
  (at most 64 characters, from `A-Za-z0-9._-`) and keeps same-named folders apart.

Both sides derive the name from the folder name the same way, so they always agree.

**If the folder isn't found** (for example, Claude Code shortened a very long path),
`calibrate --claude-code` stops, names the path it expected, and suggests
`loopbrake calibrate <folder> --project <name>`.

## R7. Speed, and working without network (FR-005, SC-002, SC-006)

**Measured**: 30 runs each, warm cache.

| Command | Median | p95 |
|---|---|---|
| `uvx --from loopbrake==0.1.0 loopbrake --version` | 42 ms | 43 ms |
| `uvx --offline --from loopbrake==0.1.0 loopbrake --version` | 42 ms | 43 ms |
| Python start + `import loopbrake.cli` | 28 ms | 29 ms |

**What was found**: plain `uvx` re-checks PyPI once its cached copy of the index is stale (after
about 10 minutes). That check took 206 ms, which alone would break the 200 ms budget, and it needs
the network. `uvx --offline` used the cached copy and worked.

**Also measured**: when uv can't reach the network, it exits with code **2**. In Claude Code, exit
code 2 from a hook is a blocking error:
- from `UserPromptSubmit`, it blocks the user's prompt;
- from `Stop`, it keeps Claude working.

uv also exits 1 when a pinned version isn't available. And `loopbrake` itself exits 1 or 2 on
ordinary errors (`feedback` with nothing to mark, a missing history folder). So the launcher can't
treat "non-zero" as "uv failed".

**Decision**: the plugin ships a small launcher, `plugin/bin/loopbrake` (POSIX `sh`), that hooks and
commands call:

| Case | What it does |
|---|---|
| `$LOOPBRAKE_CMD` is set | Runs that instead, for development (`uv run --project ~/code/LoopBrake loopbrake`) or for a `loopbrake` installed without uv (its full path). |
| A `hook` call | Runs `uvx --offline --from loopbrake==<pin> loopbrake hook …`. If that fails (not cached yet), it starts the download in the background and doesn't wait for it. It **always exits 0** with nothing on stdout, whatever uv did. |
| Any other command | First checks the cached copy with `uvx --offline --from loopbrake==<pin> loopbrake --version`, silently. If the cache is there, runs the command offline; if not, runs it online. Either way it runs exactly once and passes its exit code through. |

**Why the two paths differ**:
- **Hooks**: a hook never waits on the network. Measured during implementation: with the network
  blocked and nothing cached, a foreground retry took 11.7 s per hook call. So the first hooks after
  install return at once and record nothing until the background download lands.
- **Commands**: the version check costs about 42 ms once per command, which doesn't matter for a
  user-run command. Hooks skip it to save that time on every tool call.

**Guarding against a loop**: `LOOPBRAKE_CMD=loopbrake` could find the launcher itself on PATH,
because the plugin's `bin/` is on the Bash tool's PATH. So the launcher sets `LOOPBRAKE_LAUNCHER=1`
before running anything, and stops if it finds that already set: a `hook` call exits 0, any other
command exits 2 with a one-line message.

**Expected cost** per tool call: about 45 to 50 ms, against a 200 ms budget. Before release, this is
measured through the launcher against a locally built wheel (`UV_FIND_LINKS=dist`), not only after
publishing.

**Hook timeout**: 30 seconds on every event, which covers the one-time download.

**Alternatives considered**:
- **Plain `uvx`**: has a network check every 10 minutes, and fails offline once the cache is stale.
- **Asking users to `uv tool install loopbrake`**: an extra setup step, and the version can drift
  from the plugin's.

## R8. Plugin files and installing (FR-009)

**Marketplace file** (`.claude-plugin/marketplace.json`, at the repo root): it gives the
marketplace name (`loopbrake`), the owner, and one plugin entry named `loopbrake` with source
`./plugin`. The entry name must equal the plugin's own name.

**Plugin manifest** (`plugin/.claude-plugin/plugin.json`): name, description, version, and
author.name.

**Install** (two commands):
1. `/plugin marketplace add SahilSelokar/LoopBrake`
2. `/plugin install loopbrake@loopbrake`

**Commands**: `plugin/commands/calibrate.md`, `status.md`, `mistake.md` and `exclude.md`, run as
`/loopbrake:calibrate` and so on.
- **What each does**: tells Claude to run one `loopbrake …` command with the Bash tool and report
  its output.
- **How `loopbrake` is found**: the docs say that while a plugin is enabled, Claude Code puts the
  plugin's `bin/` folder on the PATH of the shell it runs commands in (Claude Code 2.1.281 or
  later). So the launcher is found by name.
- **Permissions**: `allowed-tools` pre-approves only that one command.

**Minimum Claude Code version**: 2.1.281, for `bin/` on PATH. `PostToolUseFailure` is older.

**Version pins**: the plugin version, the pin in the launcher, and the package `__version__` move
together. A test checks they're equal.

**Checking**: `claude plugin validate` on both the marketplace and the plugin, run locally before a
release.

## R9. Status line (FR-008, US3)

**What it shows**: `loopbrake statusline` reads the status line's input (`session_id`) and that
session's run log (the open turn, as in R4, with no lock because it only reads), then prints one
of:
- `brake 12/38`
- `brake 12 (watching)`
- `brake stopped at 39`
- `brake idle`

**Setup**: plugins can't set a status line, so the user adds one line to `~/.claude/settings.json`:
`"statusLine": {"type": "command", "command": "uvx --offline loopbrake statusline"}`.

**Choices in that line**:
- **`--offline`**: no network use, matching FR-010. The package is already in uv's cache from the
  first hook call.
- **No version pin**: it only reads the run log, and a pin in the user's settings would go stale on
  every plugin update.

## R10. Calibrating again after the brake has been on

**The problem**: once the brake is live, the history it calibrates from contains turns it cut
short.
- If those count as successes, their length is the stop line + 1, not what it would have been.
- If they're simply dropped, the long good turns that were stopped by mistake disappear, and the
  next stop line comes out lower than it should. That is quietly more false stops over time
  (Principle I).

**Decision**: calibration reads the project's run logs and finds each live turn in the transcripts
through the `call_id`s of its steps (R5). The reader returns each turn's tool call ids. Then, for
each turn:

| Live turn | In calibration |
|---|---|
| Stopped and marked mistaken | A successful turn longer than any stop line (infinite length) |
| Marked exclude (`/loopbrake:exclude`) | Left out |
| Stopped, not marked | Left out: it was judged stuck, not a success |
| Anything else | As the reader says: a success unless interrupted |

- **Why infinite length for a mistaken stop**: the real length is unknown but above the line, so
  this is the cautious choice. Marking mistakes can only raise the line, or turn it watch-only.
- **Marked both mistaken and exclude**: counted as mistaken, the cautious side.

This follows the constitution's success label ("reached Stop with no user interrupt and was not
killed"), with the cautious treatment for mistaken stops.

**This changes spec FR-007**: earlier it said a mistaken stop is kept out of calibration. That
would bias the line down, so the spec now follows this decision.

**`/loopbrake:exclude`**: the constitution names this command, so it's in. It marks the most
recent *closed* turn that has at least one step: the turn the user just watched. Empty turns are
skipped, because a slash command can leave one behind.

## R11. Release

The new commands need package **v0.2.0**: `hook`, `statusline`, `calibrate --claude-code`,
`status --claude-code`, `feedback last`, and `agreement --claude-code`. They also pick up the
reader change (R1). It also fixes the PyPI page with the new README. The
release flow is Phase 2's (tag `v0.2.0`, trusted publishing). The plugin pins `0.2.0`.
