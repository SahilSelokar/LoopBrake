# Contract: plugin files and commands (changes in 0.6.0)

Extends specs/004 [plugin.md](../../004-claude-code-plugin/contracts/plugin.md) and
[cli.md](../../004-claude-code-plugin/contracts/cli.md). Anything not named here is unchanged.

## `plugin/hooks/hooks.json`

One new entry, alongside the four that exist:

```json
"PreToolUse": [
  { "matcher": "*",
    "hooks": [ { "type": "command", "command": "\"${CLAUDE_PLUGIN_ROOT}/bin/loopbrake\" hook pre-tool", "timeout": 30 } ] }
]
```

The `hook` subcommand's `event` choices gain `pre-tool`. The launcher's pinned version (`V=`) becomes
`0.6.0`. The Codex plugin's files don't change (constitution, Codex "Trust").

## `/loopbrake:status` (and `loopbrake status --claude-code`)

There is one new line after "Tasks stopped". It shows only when the project has had at least one
question:

```text
  Tasks stopped: 2
  Questions asked: 5 (you let 4 keep going, you stopped 1; about 2.0 expected by now)
```

- "Tasks stopped" still counts every stop, the person's included.
- "Expected by now" is the same allowance as the mistakes line (α × tasks watched): on good tasks,
  about that many questions are expected (spec FR-014).
- The mistakes line is unchanged. It counts only stops made where nobody could be asked.

## Dashboard (plain words, constitution 2.7.0)

- **Task view**: at the action where it asked, a marker reads "asked here" and then either "you let
  it keep going" or "you stopped it". A task stopped by the person shows "you stopped it" in place
  of the stop reason's first sentence.
- **Project summary**: next to stops and mistakes, "asked N, you let M keep going".
- **Words**: no new words beyond "asked". "Question" appears only in the summary's sentence.

## `loopbrake calibrate`

The command and its output are unchanged. Asked tasks are counted as data-model.md's calibration
mapping says, with no new flag.

## README

The "Claude Code" section describes:
- the question;
- Allow and Deny;
- the second question at twice the line;
- the headless and bypass fallback.

The promise reads "fewer than 1 in 20 good tasks get a question", and keeps its condition (spec
FR-015).
