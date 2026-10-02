# Research: Codex CLI Plugin

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Checked**: 2026-10-02, from Codex's
own documentation (its hooks and plugin-building pages). Codex isn't installed on the builder's Mac,
so every "the probe confirms" item below is a task, not a fact yet.

## R1. Stopping a Codex task (spec FR-001, FR-003: the gate)

**What Codex offers** (its hooks page):
- **`PreToolUse`** can refuse a tool call: `{"hookSpecificOutput": {"hookEventName": "PreToolUse",
  "permissionDecision": "deny", "permissionDecisionReason": "..."}}` (or exit code 2 with the
  reason on stderr). The tool doesn't run; the model is told why; Codex carries on with the turn.
- **`PostToolUse`** with `{"continue": false, "stopReason": "..."}` replaces that tool's result with
  the text and carries on. It also takes `systemMessage`, shown to the user.
- **`Stop`** with `decision: "block"` makes Codex *continue* (a new automatic prompt), the opposite of
  what we need.
- No event ends a turn outright.

**Decision**: a stop has two parts.
1. **At the decision** (`PostToolUse` of the call that passes the limit): reply `continue: false`
   with LoopBrake's plain reason as `stopReason`, so the model reads it instead of the tool's output,
   plus the same reason as `systemMessage`, so the user sees it in Codex.
2. **After it** (`PreToolUse` of every later call in that task): refuse, with the same reason. No
   later tool call of the task runs.

The model, unable to act, is expected to end its turn and relay the reason. **The probe must show
this** (FR-001): with a limit of 3 and a request to run a harmless command 10 times, at most 4 run,
and the turn ends after at most 3 refused attempts, in 10 of 10 runs. If the model keeps retrying
without end, the gate fails and the feature goes back to the builder.

**Constitution**: this is a stop, not a warning. The model learns of it only after the decision, and
nothing it does afterwards can run a tool ("No warn-first in v1" holds).

**Alternatives considered**:
- `PostToolUse` alone: the model reads the reason but can keep calling tools. Not a stop.
- Killing the Codex process: loses the user's session and fails silently. No.

## R2. The events and what each gets (spec FR-002, FR-007)

| Codex event | LoopBrake does | Fields it uses |
|---|---|---|
| `UserPromptSubmit` | opens a task (closes an open one as interrupted, as in Claude Code) | `session_id`, `cwd`, `turn_id`, `transcript_path` |
| `PreToolUse` | refuses the call if this task is stopped; otherwise nothing | `session_id`, `turn_id` |
| `PostToolUse` | counts a main-agent call; decides | `session_id`, `turn_id`, `tool_name`, `tool_use_id`, `tool_input` |
| `Stop` | closes the task | `session_id`, `turn_id` |
| `Interrupt` | closes the task as interrupted | `session_id`, `turn_id` |
| `SubagentStart` / `SubagentStop` | used only if the probe needs them to tell helper calls apart (R3) | `agent_id` |

- **`turn_id`** (a Codex extension) names the task. It's recorded on the task's start, so a stray
  event from another turn is never counted in this one.
- **No duration** on `PostToolUse` (Claude Code has `duration_ms`), and **no trace context**. So
  Codex actions show no duration in the dashboard, and Codex tasks don't nest in a Codex trace.
- **Hosted tools** such as web search "don't use the local function-tool hook path": they never reach
  a hook, so they aren't counted live, and calibration must skip them too (R4).

## R3. Helper agents (spec FR-002, SC-006)

**What the docs say**: helpers' tool calls fire the normal `PreToolUse`/`PostToolUse`, with the
**parent's** `session_id`. No `agent_id` on those two events; `agent_id` appears only on
`SubagentStart`/`SubagentStop` (with `agent_transcript_path` on the latter).

**Decision**: tell them apart by `transcript_path`. The task's start records the main session's
transcript path; a tool call whose path differs is a helper's and isn't counted. **The probe
confirms** helpers' calls carry their own transcript path. If they don't, the fallback counts nothing
between a `SubagentStart` and its `SubagentStop` for the same `turn_id`, and the probe also checks
whether the main agent works in parallel with a helper (which would make the fallback undercount:
safe, since a lower count can only stop later).

## R4. Learning the limit from Codex history (spec FR-007, FR-010)

**Format** (Codex session files, `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`, one JSON object per
line with a `type` and a `payload`):
- `session_meta`: the session `id` and `cwd` (picks the project);
- `turn_context`: per-turn settings;
- `event_msg`: `user_message`, `task_started`/`task_complete`, `turn_aborted`, `agent_message`;
- `response_item`: `function_call` (with `name`, `arguments`, `call_id`), `function_call_output`,
  `custom_tool_call` (for tools such as `apply_patch`), `message`, `reasoning`, and hosted tools'
  items such as `web_search_call`.

**Decision**: one reader, `codex_turns()`, beside `claude_code_turns()` in `traces.py`, checked
against a pinned synthetic sample (constitution, Principle V):
- **a task** runs from a user message to its `task_complete` (finished) or `turn_aborted`
  (interrupted, left out);
- **its steps** are the local tool calls (`function_call`, `custom_tool_call`, `local_shell_call`) of
  the main session's file, in order; hosted tools are skipped (R2);
- **helpers** write their own session files, so a main session's file holds only main-agent calls
  (the probe confirms);
- **stops**: a task LoopBrake stopped is left out, as in Claude Code, matched by call ids, which are
  the same as the hooks' `tool_use_id` (the probe confirms);
- **messages that arrive while Codex is working** stay in the running task, as Phase 3's R1 found
  for Claude Code; the probe checks Codex's equivalent (steering and queued messages).

**The agreement check** (constitution): `loopbrake agreement --codex` compares each live task with
the history task holding its first call id; live higher must be 0 before release.

## R5. Packaging and installing the plugin (spec FR-013)

**What Codex offers** (its plugin-building page):
- a plugin is a folder with `.codex-plugin/plugin.json`, and optionally `skills/`, `hooks/`,
  `scripts/`, `assets/`;
- hooks come from `hooks/hooks.json` by default, and hook commands get `PLUGIN_ROOT` (the installed
  plugin) and `PLUGIN_DATA` (a writable folder);
- a repository offers plugins through `.agents/plugins/marketplace.json`, with a `git-subdir`
  source; users add it with `codex plugin marketplace add owner/repo`, then install the plugin.

**Decision**: a new folder `codex-plugin/` beside `plugin/` (Claude Code's), with its own copy of
the launcher, and `.agents/plugins/marketplace.json` pointing at it. A test keeps the two launchers
identical and the versions in step with the package. **The probe confirms** the install commands
and that `"$PLUGIN_ROOT/bin/loopbrake"` runs from a hook command.

## R6. The commands, as Codex skills (spec FR-009)

**What Codex offers**: plugins ship skills (`SKILL.md` files) that the user invokes from the skills
menu or by name; there's no documented slash-command folder like Claude Code's.

**Decision**: five skills, `loopbrake-calibrate`, `loopbrake-status`, `loopbrake-mistake`,
`loopbrake-exclude` and `loopbrake-dashboard`. Each tells the model to run one `loopbrake` command
and repeat its output as printed, like the Claude Code commands.

**Two things the probe checks**, because skills run through the model's shell, which is sandboxed:
- **finding the program**: the skill runs `uvx --offline --from loopbrake==<version> loopbrake ...`,
  which needs no network once cached (the hooks prime the cache);
- **writing `~/.loopbrake`**: Codex's default sandbox may refuse writes outside the project, which
  setting the limit, marking a mistake and leaving a task out all need. If so, the skill asks for
  Codex's usual approval for that one command, and the README says so.

## R7. Hook speed (spec SC-002)

Every tool call now runs two hooks (`PreToolUse` and `PostToolUse`) through the launcher, about 65
ms each on this Mac (v0.3.0's measurement). **Decision**: keep both; the `PreToolUse` path reads
only whether the task is stopped (one small file read) and returns. The budget (200 ms per tool
call at p95) is checked for the pair.

## R8. Projects, the dashboard and export (spec FR-008, FR-011, FR-012)

- **Project name**: `codex-<folder tail>-<hash>` from `cwd`, built like Claude Code's `cc-` names, so
  the same folder gives two separate projects and limits.
- **Dashboard**: the agent is `codex` for `codex-` projects; its label comes from the `cwd` (no
  history scan needed). Codex's tools get plain names: `shell` and `exec_command` "Ran a command",
  `apply_patch` "Edited files", `update_plan` "Updated its plan", `view_image` "Looked at an image";
  MCP tools "Used <server>". **The probe confirms** the exact `tool_name` values.
- **Export**: `gen_ai.agent.name` is `codex`; everything else as for Claude Code tasks.

## R9. What the probe must establish before anything else is built

1. Refusing every call after the limit ends the turn, within 3 refused attempts, 10 of 10 (R1). **The
   gate.**
2. What the user sees in Codex for `systemMessage` and `stopReason` (R1).
3. Helpers' calls carry their own `transcript_path` (R3).
4. The exact `tool_name` values, and that `tool_use_id` equals the history's `call_id` (R4, R8).
5. The history's task boundaries, including messages sent while Codex works (R4).
6. Installing from this repository, and `PLUGIN_ROOT` in hook commands (R5).
7. Skills under the default sandbox: running `uvx`, and writing `~/.loopbrake` (R6).
8. Hook times for the pair on a real Codex (R7).

**Needs from the builder**: Codex CLI installed (`npm install -g @openai/codex` or Homebrew) and
signed in, with a ChatGPT login or an OpenAI API key.

## R10. Probe results (2026-10-02, Codex CLI 0.160.0)

**How it was run**: the builder has no Codex account, so Codex ran on a local model instead: a
llama.cpp server with Qwen3-4B-Instruct, set as a custom provider (`-c model_provider=…`). Hooks,
plugins, history files and the sandbox are Codex's own, whatever the model; what a GPT model does
after a refused call may differ from this small model (see "Limits" below). The probe plugin and its
logs stayed in the scratch folder.

| R9 item | Finding |
|---|---|
| 1. **The gate** | **Passed, 10 of 10**: each run executed exactly 4 commands and the task ended. In 9 runs the model stopped after reading the stop message in place of the 4th result; in 1 it tried a 5th call, the `PreToolUse` refusal blocked it, and the task then ended. With LoopBrake's real message (which doesn't say "call no more tools"). |
| 2. What the user sees | The model relays the stop message ("The command was stopped after 4 executions…"). `systemMessage` isn't printed by `codex exec`. |
| 3. Helpers | **Not settled**: the small model claimed to start a helper but didn't (no `SubagentStart`; both calls came from the main session). |
| 4. Tool names and ids | Hooks see `tool_name: "Bash"` for shell commands (the history says `exec_command`); `tool_use_id` equals the history's `call_id` exactly. |
| 5. History boundaries | `event_msg` `task_started` and `task_complete` carry the `turn_id`, the same id the hooks get; a stopped task's 4th result holds LoopBrake's message and the task ends `task_complete`. |
| 6. Install and `PLUGIN_ROOT` | `codex plugin marketplace add <path or owner/repo>`, then `codex plugin add <plugin>@<marketplace>`. Plugin hooks get `PLUGIN_ROOT` and `PLUGIN_DATA`. |
| 7. Commands under the sandbox | **Blocked**: under Codex's normal (`workspace-write`) sandbox, a command the model runs can't write `~/.loopbrake`, and `uvx` can't open its cache even with `--offline`. The 4B model also couldn't operate a skill. |
| 8. Hook times | Each probe hook took under 1 ms of its own work; the launcher's cost is measured with the real plugin (T011). |

**Three findings the docs didn't make plain:**
1. **Hooks must be trusted first.** Codex runs a non-managed hook (plugin hooks included) only after
   the user reviews and trusts its exact definition with `/hooks`; the trust is tied to the hook's
   hash, and `codex exec` skips untrusted hooks **with no warning**. So: the README tells users to open
   `/hooks` once after installing; the hook definitions must never change between versions (only the
   launcher's pinned version changes); and status says to check `/hooks` when nothing was recorded.
2. **Commands can't run as skills** (item 7). **Decision**: the user types the command as their
   message, `loopbrake: status`, `loopbrake: calibrate`, `loopbrake: mistake`, `loopbrake: exclude`,
   `loopbrake: dashboard` or `loopbrake: dashboard stop`. The `UserPromptSubmit` hook, which runs outside
   the sandbox, runs the command and passes its output as `additionalContext` with "repeat it exactly";
   the model repeats it (checked: exact, no tool calls, about 380 tokens). A command message never
   opens a LoopBrake task. (A hook reply with `continue: false` also stops the prompt, but `codex exec`
   shows neither its `stopReason` nor its `systemMessage`.)
3. **Task boundaries come from `turn_id`** in both the hooks and the history, so live and learned
   tasks match by construction (constitution, "Same turns live and in calibration").

**Limits, said plainly**: the gate ran on a small local model. A GPT model may try more refused calls
before ending the task; refused calls never run, so the limit still holds, but a stubborn model would
spend a few more tokens. Helpers are untested; the design counts nothing that comes from a helper's
transcript or between `SubagentStart` and `SubagentStop`, so a mistake there can only lower the count
(the safe side). Both need a check on a real Codex account before the README calls the Codex plugin
more than "tested on a local model".
