# Contract: command line additions

Everything else is as in Phases 3 and 4.

## `loopbrake hook codex-<event>`

The Codex hook entry point (contracts/hooks.md). Like `loopbrake hook <event>`, it's handled before
argument parsing and always exits 0.

## `loopbrake calibrate --codex`

Sets the limit for the Codex project of the current folder, from its Codex session files
(data-model.md, "History task"). Output: exactly the Claude Code wording of
`calibrate --claude-code`, from `claude_code.calibrate_message`. With no Codex history for this
folder, one plain line and exit code 2, as for Claude Code.

## `loopbrake status --codex`

The Codex project's status, worded as `status --claude-code`.

## `loopbrake agreement --codex`

Compares each live Codex task with the history task holding its first call id; prints the same
summary as `agreement --claude-code` ("tasks matched N, equal …, live higher …"). Exit code 1 if any
live count is higher (constitution: a release gate).

## Where Codex history is

`$CODEX_HOME/sessions`, or `~/.codex/sessions` when `CODEX_HOME` isn't set.
