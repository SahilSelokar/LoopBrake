# Contract: CLI additions (v0.2.0; plain-language replies since v0.2.1)

The Phase 2 commands are unchanged ([cli contract](../003-core-package/contracts/cli.md)). The
additions below follow the same rules:
- exit 2 on errors, with one line on stderr;
- `LOOPBRAKE_DEBUG=1` shows the full error;
- no emoji.

## `loopbrake hook <prompt|tool|tool-failed|stop>`

See [hooks.md](hooks.md). Always exits 0.

## Plain-language replies (v0.2.1)

Everything a Claude Code user reads, through `--claude-code` and `feedback last`, is written in
plain words: "task" for a turn, "tool calls" for steps, and "fewer than 1 in 20" for α 5%. No run
ids or α symbols. The exact texts are pinned in `tests/test_cli.py` and `tests/test_claude_code.py`,
and the README shows them. The developer forms (a runs file, `--project`, `feedback RUN`) keep the
v0.2.0 output below.

## `loopbrake calibrate --claude-code [--alpha A]`

Sets the stop line for the Claude Code project in the current folder, from that project's own
history (research R6, R10).

- **The source**: the `source` argument becomes optional, and exactly one of `source` or
  `--claude-code` is required.
- **The project**: derived from the history folder, so `--project` isn't allowed with
  `--claude-code`.
- **Earlier LoopBrake stops**: taken into account as research R10 describes.

**Output**:

```text
project cc-home-me-my-app-c57a41
stop line: 38 steps (from 898 successful turns, k = 854, α 5%)
LoopBrake: turns left out (stopped or excluded): 3; mistaken stops counted as long good turns: 1
saved: /home/me/.loopbrake/calibration/cc-home-me-my-app-c57a41.json
```

The third line appears only when the history has LoopBrake stops or excludes. In watch-only, the second line
is `watch-only: 12 successful turns found; need 7 more for α 5%`.

**Errors** (exit 2):
- `no Claude Code history for this folder at <path>; run loopbrake calibrate <folder> --project <name>`
- `no Claude Code session files (*.jsonl) in <path>`

## `loopbrake status --claude-code`

The same output as `status --project <the derived project>`. `--project` and `--claude-code` can't
be used together.

**Wording**: for a project calibrated from Claude Code history, the lines say "turns" instead of
"runs". A watch-only line reads `watch-only (31 successful turns; 39 needed)`. The needed count
includes mistaken stops: they count as longer than any line, so they take the top places
(`calibration.runs_needed(alpha, unbounded=<mistakes counted>)`). The same rule gives `need N more`
in `calibrate`'s watch-only line.

**When the hooks may not be running**: if the project has a calibration but no recorded turns, it
adds one line:
`no turns recorded yet for this project; if you have used Claude Code here since installing, the hooks may not be running (see the README's troubleshooting)`.

## `loopbrake feedback last (--mistaken | --exclude)`

`last` is a run id that's looked up from the run records of every project:

| Flag | `last` means | Output |
|---|---|---|
| `--mistaken` | the run of the most recent `stop` event | `recorded: run a1b2c3d4e5f6 (project cc-…, stopped at step 39) marked as a mistaken stop` |
| `--exclude` | the run of the most recent `run_end` with `steps` ≥ 1 | `recorded: run a1b2c3d4e5f6 (project cc-…, 14 steps, finished) left out of future calibration` |

**Errors** (exit 1, one line on stderr):
- `loopbrake: no stops recorded yet` (or `no finished turns recorded yet`);
- `loopbrake: run … is already marked`, for the same verdict twice.

Phase 2's `feedback RUN` with an explicit id still works.

## `loopbrake agreement --claude-code`

Checks spec SC-008 for this folder's project:
1. For each live turn in the run logs, find the transcript turn holding its first `call_id`.
2. Compare the step counts.

**Output** (one line per mismatch, then a summary):

```text
higher  run a1b2c3d4e5f6  live 41  transcript 40
turns matched 214, equal 209, live lower 5, live higher 0
```

It exits 1 when any live count is higher. It writes nothing.

## `loopbrake statusline`

It reads the status line's input from stdin (it needs only `session_id`), reads the open turn from
that session's log without locking, and prints one line:

| State | Output |
|---|---|
| An open turn with a stop line | `LoopBrake: 12 of 38 tool calls` |
| An open turn, watch-only | `LoopBrake: 12 tool calls (watching only)` |
| A braked turn | `LoopBrake: stopped this task at 39 tool calls` |
| No open turn, or bad input | `LoopBrake: ready` |

It always exits 0 and never writes anything. Plain text only, with no colors in v1.
