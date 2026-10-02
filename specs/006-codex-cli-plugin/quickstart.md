# Quickstart: checking the Codex CLI plugin

Run these on a real Codex. Scenario 0 is the gate: nothing else is built until it passes.

**Prerequisites**:
- Codex CLI installed (`npm install -g @openai/codex`), and either signed in (a ChatGPT login or an
  OpenAI API key) or pointed at a local model through a custom provider, as in research R10;
- `uv` installed;
- a scratch folder to work in, and a scratch LoopBrake folder (`LOOPBRAKE_HOME`), so real records
  stay untouched.

## 0. The probe (research R9; spec FR-001)

A throwaway probe plugin whose hooks log every event's input to a file, and whose `PreToolUse`
refuses every call after the third in a task, with a reason.

1. In the scratch folder, run `codex exec "Run 'echo hi' ten times, one command at a time."` ten
   times.
2. Read the log and the session files.

**Expect (the gate)**: in each of the 10 runs, at most 4 commands ran, and the task ended within 3
refused attempts.

**Also record** (R9, items 2–8):
- what the user saw for `systemMessage` and for the refusal;
- a helper agent's tool calls, and whether they carry their own `transcript_path`;
- the `tool_name` values, and whether each `tool_use_id` equals the session file's `call_id`;
- the session file's task boundaries, including a message sent while Codex works;
- installing a plugin from a local marketplace, and `$PLUGIN_ROOT` in a hook command;
- a command run by the model under the default sandbox (`uvx`, writing `~/.loopbrake`);
- hook times.

If the gate fails, stop and report to the builder.

## 1. Install (spec FR-013)

```text
codex plugin marketplace add <this repository, or a local path to it>
```

then install `loopbrake` (contracts/plugin.md). **Expect**: the hooks run on the next task (a run log
appears under `LOOPBRAKE_HOME/runs/`) once the hooks are trusted with `/hooks` (or with
`--dangerously-bypass-hook-trust` for a scripted check).

## 2. Set the limit (User Story 2)

Send `loopbrake: calibrate` in a folder with enough Codex history. **Expect**: the Claude Code
wording, with a limit; in a folder with too little, "Not enough history yet … needs N".

## 3. A live stop (User Story 1; SC-001)

Set a limit of 3 for a scratch project, then ask Codex to run a harmless command 10 times.
**Expect**: at most 4 ran, the plain reason was shown, and the next message starts a new count.
10 of 10.

## 4. Failing safely (SC-003)

Break LoopBrake three ways: point the launcher at a missing program, damage the run log, make
`LOOPBRAKE_HOME` read-only. **Expect**: 10 of 10 Codex tasks finish normally, and nothing is refused.

## 5. Helpers don't count (SC-006)

Ask for work that uses a helper agent. **Expect**: the task's count equals the main agent's tool
calls alone.

## 6. Speed (SC-002)

Time 100 tool calls with the plugin on and off. **Expect**: at most 200 ms added at p95.

## 7. Agreement (SC-004)

After some real Codex use, `loopbrake agreement --codex`. **Expect**: live higher 0.

## 8. Dashboard and export (User Story 3; SC-007)

Open the dashboard (`loopbrake: dashboard`) during a Codex task. **Expect**: the count rises
within 2 seconds of each tool call; the task is marked Codex, with plain action names. With export
on, the task reaches a local Collector named as `codex`.

## 9. Nothing leaves the computer (Principle VI)

With export off, run a Codex task and watch the hooks' connections. **Expect**: none.
