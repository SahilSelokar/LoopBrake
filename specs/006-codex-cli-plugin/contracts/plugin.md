# Contract: the Codex plugin

Facts and decisions in [research.md](../research.md), R5 and R6. The probe confirms the install
commands and the manifest fields before release.

## Layout

```text
codex-plugin/
├── .codex-plugin/plugin.json   # name "loopbrake", version = the package's, description, hooks
├── hooks/hooks.json            # the hooks of contracts/hooks.md (seven events)
└── bin/loopbrake               # the launcher, byte for byte plugin/bin/loopbrake (V = the version)
```

**Hook definitions never change between versions** (research R10): Codex runs a plugin's hooks only
after the user trusts their exact definitions with `/hooks`, and a changed definition needs trusting
again. Only the launcher's pinned version changes from release to release.

**Versions in step**: the manifest's `version`, the launcher's `V=` and `loopbrake.__version__` agree;
`tests/test_plugin_files.py` checks it, and that the two launchers are identical.

## The commands: typed messages (research R10)

Codex's sandbox stops commands the model runs from writing `~/.loopbrake` or starting `uvx`, so the
commands aren't skills. The user types one as the whole message; the `UserPromptSubmit` hook, which
runs outside the sandbox, runs it and hands its output to the model as `additionalContext`, to repeat
exactly (contracts/hooks.md).

| Typed message | Runs | Same as |
|---|---|---|
| `loopbrake: calibrate` | `calibrate --codex` | `/loopbrake:calibrate` |
| `loopbrake: status` | `status --codex` | `/loopbrake:status` |
| `loopbrake: mistake` | `feedback last --mistaken` | `/loopbrake:mistake` |
| `loopbrake: exclude` | `feedback last --exclude` | `/loopbrake:exclude` |
| `loopbrake: dashboard` | `dashboard --background` | `/loopbrake:dashboard` |
| `loopbrake: dashboard stop` | `dashboard --stop` | `/loopbrake:dashboard stop` |
| `loopbrake: help` | lists these | |

Matching: the whole message, trimmed, case-insensitive, with or without the colon (`loopbrake
status` works too). Anything else is an ordinary message.

## Installing (README)

```text
codex plugin marketplace add SahilSelokar/LoopBrake
```

then `codex plugin add loopbrake@loopbrake`, then open Codex once and trust LoopBrake's hooks with
`/hooks` (until then Codex skips them silently, research R10). The
repository's `.agents/plugins/marketplace.json` lists one plugin, `loopbrake`, with a `git-subdir`
source at `./codex-plugin` on `main`.

## Uninstalling

Removing the plugin leaves nothing behind except `~/.loopbrake/`, as for Claude Code.
