# Contributing to LoopBrake

Thanks for wanting to help. LoopBrake stops AI agent tasks that run far past their normal length, and
says why, with a promise about how rarely it stops a good task. Issues marked
[good first issue](https://github.com/SahilSelokar/LoopBrake/labels/good%20first%20issue) are the
easiest places to start.

## Set up

You need Python 3.11 or later and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/SahilSelokar/LoopBrake.git
cd LoopBrake
uv run pytest            # about 30 seconds; everything should pass
```

## Where things are

| Folder | What's in it |
|---|---|
| `src/loopbrake/brake.py`, `calibration.py`, `conformal.py` | The engine: counting a task's tool calls, the limit, and the promise behind it |
| `src/loopbrake/watcher.py` | The API for your own agents: `watch()`, `@tool`, `task()` |
| `src/loopbrake/claude_code.py`, `codex.py`, `agent_sdk.py` | Adapters for Claude Code, Codex CLI and Claude's agent toolkit |
| `src/loopbrake/dashboard.py`, `static/` | The local dashboard |
| `src/loopbrake/otlp.py` | Export to observability tools |
| `plugin/`, `codex-plugin/` | The Claude Code and Codex plugins |
| `demo/` | A bookshop run by two agents, each with its own brake |
| `eval/` | The evaluation on public agent runs, and its results |
| `specs/` | The design of each feature, written before it was built |

## The rules

These keep LoopBrake's promise true. The full version is in
[.specify/memory/constitution.md](.specify/memory/constitution.md).

1. **The promise comes first.** No change may make LoopBrake stop good tasks more often than it
   promises. How stops are decided changes only with numbers from `eval/` on public agent runs.
2. **No dependencies in the core.** The `loopbrake` package uses only Python's standard library.
   An adapter for another framework can be an optional extra.
3. **Adapters stay thin.** They turn an agent's events into brake calls and the brake's answer back
   into the agent's format. They never decide a stop themselves.
4. **Local by default.** Nothing leaves the user's computer unless they turn export on. Never commit
   real agent transcripts; test data is made up or comes from public datasets.
5. **Plain words** in anything a user reads: "task", "tool calls" (or "actions" in the dashboard),
   "limit", "fewer than 1 in 20". No jargon, no ids.
6. **Fail safely.** If LoopBrake itself breaks, the agent must carry on as if it weren't there.

## Making a change

- For anything beyond a small fix, open an issue first, so we can agree on the approach.
- Add or update tests with every change. GitHub runs them on Python 3.11, 3.12 and 3.13.
- Keep changes small and focused; one pull request per idea.
- Bigger features get a short design in `specs/` first. We'll help with that, so don't let it stop you
  from opening the issue.

By contributing, you agree that your work is released under the [MIT license](LICENSE).
