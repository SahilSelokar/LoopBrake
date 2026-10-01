---
description: Show LoopBrake's stop line, turns watched and stopped, and mistaken stops for this project
allowed-tools: Bash(loopbrake status --claude-code)
---

Run `loopbrake status --claude-code` with the Bash tool. Then repeat its output to me exactly as
printed, adding nothing.

Only if the output shows no stop line yet (it says watch-only or no calibration), add one line: the
step count can also be shown in the status line by adding
`"statusLine": {"type": "command", "command": "uvx --offline loopbrake statusline"}` to
`~/.claude/settings.json`.
