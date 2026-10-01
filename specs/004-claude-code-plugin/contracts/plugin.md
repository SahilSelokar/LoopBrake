# Contract: Plugin and marketplace files

The repository is its own Claude Code plugin marketplace (FR-009). Install:

```text
/plugin marketplace add SahilSelokar/LoopBrake
/plugin install loopbrake@loopbrake
```

This needs Claude Code 2.1.281 or later (`bin/` on PATH) and `uv`.

## Layout

```text
.claude-plugin/marketplace.json     the marketplace (repo root)
plugin/
├── .claude-plugin/plugin.json      the plugin manifest
├── hooks/hooks.json                four hooks
├── bin/loopbrake                   launcher (sh, mode 755)
└── commands/
    ├── calibrate.md                /loopbrake:calibrate
    ├── status.md                   /loopbrake:status
    ├── mistake.md                  /loopbrake:mistake
    └── exclude.md                  /loopbrake:exclude
```

## `.claude-plugin/marketplace.json`

```json
{
  "name": "loopbrake",
  "description": "LoopBrake: stops stuck Claude Code turns, with a guaranteed limit on stopping good ones.",
  "owner": {"name": "Sahil Selokar"},
  "plugins": [
    {"name": "loopbrake", "source": "./plugin",
     "description": "Stops a Claude Code turn once it goes past a stop line set from your own past turns."}
  ]
}
```

## `plugin/.claude-plugin/plugin.json`

```json
{
  "name": "loopbrake",
  "version": "0.2.0",
  "description": "Stops a Claude Code turn once it goes past a stop line set from your own past turns.",
  "author": {"name": "Sahil Selokar"},
  "homepage": "https://github.com/SahilSelokar/LoopBrake",
  "license": "MIT"
}
```

## `plugin/hooks/hooks.json`

Every hook uses `"type": "command"` and `"timeout": 30` (seconds).

| Event | Matcher | Command |
|---|---|---|
| `UserPromptSubmit` | none | `"${CLAUDE_PLUGIN_ROOT}/bin/loopbrake" hook prompt` |
| `PostToolUse` | `*` | `"${CLAUDE_PLUGIN_ROOT}/bin/loopbrake" hook tool` |
| `PostToolUseFailure` | `*` | `"${CLAUDE_PLUGIN_ROOT}/bin/loopbrake" hook tool-failed` |
| `Stop` | none | `"${CLAUDE_PLUGIN_ROOT}/bin/loopbrake" hook stop` |

The path is quoted, because install folders can contain spaces.

**If T015 finds that slash commands don't fire `UserPromptSubmit`**, add a fifth entry:
`UserPromptExpansion`, with no matcher, running `… hook prompt`. `hook prompt` does nothing on an
open turn that has no steps, so firing twice is harmless (research R3).

## `plugin/bin/loopbrake` (launcher)

POSIX `sh`, mode 755, with `V=0.2.0` near the top (research R7):

```text
0. If LOOPBRAKE_LAUNCHER is already set: this is a loop.
   For `hook`: exit 0. Otherwise: print "loopbrake: LOOPBRAKE_CMD points back at the plugin launcher; set it to the real loopbrake" to stderr and exit 2.
   Then export LOOPBRAKE_LAUNCHER=1.
1. If $1 is `hook`:
     if LOOPBRAKE_CMD is set: run $LOOPBRAKE_CMD "$@"
     else: uvx --offline --from loopbrake==$V loopbrake "$@"
           if that failed (not cached yet): start `uvx --from loopbrake==$V loopbrake --version`
           in the background, detached, and don't wait for it
     exit 0                       (never 1 or 2: exit 2 would block a prompt or keep Claude running)
2. If LOOPBRAKE_CMD is set: exec $LOOPBRAKE_CMD "$@".
3. Otherwise (calibrate, status, feedback, agreement, ...):
     if uvx --offline --from loopbrake==$V loopbrake --version >/dev/null 2>&1
     then exec uvx --offline --from loopbrake==$V loopbrake "$@"
     else exec uvx --from loopbrake==$V loopbrake "$@"
     fi                           (runs once; its exit code passes through)
```

- **No waiting on the network**: a hook never downloads in the foreground. Measured before this
  rule: with the network blocked and nothing cached, the online try took 11.7 s per hook call,
  stalling every tool call. Now the first hooks after install return at once and record nothing
  until the background download lands. `/loopbrake:calibrate` downloads in the foreground anyway.
- **`LOOPBRAKE_CMD`**: it runs through `eval`, so it can hold arguments and a quoted path with spaces,
  for example `LOOPBRAKE_CMD="uv run --project '/path/with space' loopbrake"`.
- **Exit codes**: the hook path never exits with anything other than 0. uv exits 2 when it can't
  reach the network (measured).
- **Paths**: no hard-coded paths, and nothing outside `~/.loopbrake` and uv's own cache is touched
  (FR-012).

## Commands

Each file has `description`, `allowed-tools` (only its one command), and a body that tells Claude
to run the command with the Bash tool and repeat its output, adding nothing:

| File | Runs | `allowed-tools` |
|---|---|---|
| `calibrate.md` | `loopbrake calibrate --claude-code` | `Bash(loopbrake calibrate --claude-code)` |
| `status.md` | `loopbrake status --claude-code` | `Bash(loopbrake status --claude-code)` |
| `mistake.md` | `loopbrake feedback last --mistaken` | `Bash(loopbrake feedback last --mistaken)` |
| `exclude.md` | `loopbrake feedback last --exclude` | `Bash(loopbrake feedback last --exclude)` |

`status.md` also tells Claude to show the status line setup line when there's no stop line yet
([cli.md](cli.md), statusline).

## Version rule

These three always carry the same version, and a test checks it:
- `plugin.json` `version`;
- the pin in `bin/loopbrake`;
- `src/loopbrake/__init__.py` `__version__`.

**Release order**: tag the head of the feature branch as `vX.Y.Z` and push only the tag. Wait for the
publish workflow to put the package on PyPI. Then merge into `main`, so `main` never pins a version
that isn't on PyPI yet.

## Checks

- **Validation**: `claude plugin validate .` and `claude plugin validate ./plugin` pass, run
  locally before each release, since CI has no Claude Code.
- **CI test**: both JSON files parse, the names match, the launcher is executable, and the versions
  agree.
- **Launcher test**, with a fake `uvx` script first on PATH that logs each call:
  - `hook` exits 0 with empty stdout when the fake exits 2, and when it exits 1;
  - `hook` retries online once, only when the offline call fails;
  - a command like `status` runs exactly once, and passes its exit code through, even when it
    exits 1 or 2;
  - `LOOPBRAKE_CMD` pointing at the launcher itself doesn't loop.
