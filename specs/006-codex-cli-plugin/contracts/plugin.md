# Contract: the Codex plugin

Facts and decisions in [research.md](../research.md), R5 and R6. The probe confirms the install
commands and the manifest fields before release.

## Layout

```text
codex-plugin/
├── .codex-plugin/plugin.json   # name "loopbrake", version = the package's, description, hooks
├── hooks/hooks.json            # the five hooks of contracts/hooks.md
├── bin/loopbrake               # the launcher, byte for byte plugin/bin/loopbrake (V = the version)
└── skills/
    ├── loopbrake-calibrate/SKILL.md
    ├── loopbrake-status/SKILL.md
    ├── loopbrake-mistake/SKILL.md
    ├── loopbrake-exclude/SKILL.md
    └── loopbrake-dashboard/SKILL.md
```

**Versions in step**: the manifest's `version`, the launcher's `V=` and `loopbrake.__version__` agree;
`tests/test_plugin_files.py` checks it, and that the two launchers are identical.

## The skills (the commands)

Each skill's instructions: run one command with the shell tool, then repeat its output exactly as
printed, adding nothing. The program is the pinned package from uv's cache:
`uvx --offline --from loopbrake==<version> loopbrake …`.

| Skill | Runs | Same as |
|---|---|---|
| `loopbrake-calibrate` | `calibrate --codex` | `/loopbrake:calibrate` |
| `loopbrake-status` | `status --codex` | `/loopbrake:status` |
| `loopbrake-mistake` | `feedback last --mistaken` | `/loopbrake:mistake` |
| `loopbrake-exclude` | `feedback last --exclude` | `/loopbrake:exclude` |
| `loopbrake-dashboard` | `dashboard --background`, or `--stop` when asked to stop | `/loopbrake:dashboard [stop]` |

**Sandbox** (R6): if Codex's sandbox refuses the write to `~/.loopbrake` for calibrate, mistake or
exclude, the skill asks for Codex's normal approval for that one command; the README says so.

## Installing (README)

```text
codex plugin marketplace add SahilSelokar/LoopBrake
```

then install `loopbrake` from that marketplace (the probe records the exact command). The
repository's `.agents/plugins/marketplace.json` lists one plugin, `loopbrake`, with a `git-subdir`
source at `./codex-plugin` on `main`.

## Uninstalling

Removing the plugin leaves nothing behind except `~/.loopbrake/`, as for Claude Code.
