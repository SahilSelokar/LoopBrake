<div align="center">

# LoopBrake

**Brakes for stuck AI agents.**

Stop agent runs that are going in circles, with a guaranteed limit on how often a good run gets stopped.

[![Status](https://img.shields.io/badge/status-research%20phase-orange)](#status)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB)](https://github.com/SahilSelokar/LoopBrake/blob/main/pyproject.toml)
[![Dependencies](https://img.shields.io/badge/runtime%20dependencies-0-brightgreen)](https://github.com/SahilSelokar/LoopBrake/blob/main/pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-blue)](https://github.com/SahilSelokar/LoopBrake/blob/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/loopbrake)](https://pypi.org/project/loopbrake/)

</div>

---

## The problem

AI agents get stuck. They run the same command again and again, re-read the same file, or hit the
same error, and they keep spending tokens until a step or budget limit finally stops them.

The usual fixes are blunt: a fixed step limit, or a rule like "stop after the same action 3 times".
Set them tight and you kill runs that would have succeeded. Set them loose and you pay for every loop.

## The idea

LoopBrake watches a run one step at a time and gives each step a **stuck score**. When the score
crosses a **stop line**, it stops the run and says why.

The stop line is not guessed. It is set from **your own past successful runs**, so that at most a
chosen share of good runs, for example 5 in 100, would ever cross it. That is a statistical
guarantee (split-conformal calibration), not a tuned target.

**In v1 the stuck score is simply how long the run has gone on.** Two experiments (below) tested
smarter scores, and neither beat it on agents they were not tuned on. The stuck signals (repeats,
nothing new, same error again) still run, but only to explain why a stopped run looked stuck.

```text
  your past successful runs ──▶ stop line (a number of steps), with a guaranteed
                                    │      limit on stopping good runs
                                    ▼
  agent takes a step ──▶ how many steps so far? ──▶ past the stop line?
                                                      │             │
                                                      no            yes
                                                      │             │
                                                      ▼             ▼
                                                 keep going    stop the run and say why
```

## What a stop looks like

A real run from the public SWE-bench data (GPT-5-mini), replayed through LoopBrake. The agent kept
searching the same files for a function and found nothing new:

```text
swe-gpt5mini · matplotlib__matplotlib-25775 · stopped at step 27 of 72 · saved 2,023,115 tokens (84%)
Reason: repeating in 5 of last 5 steps (similar to step 19); nothing new in 2 of last 5 steps (0 of 21 output lines new)

  23  sed -n '760,1080p' lib/matplotlib/backend_bases.py
  24  grep -n "def set_antialiased" -n lib/matplotlib/backend_bases.py || true
  25  sed -n '892,932p' lib/matplotlib/backend_bases.py
  26  sed -n '1,220p' lib/matplotlib/patches.py
  27  grep -n "set_antialiased" -n lib -R || true
```

More in [eval/results/kill-stories.md](https://github.com/SahilSelokar/LoopBrake/blob/main/eval/results/kill-stories.md).

## Use it

**Install.** `pip install loopbrake`, or `uv add loopbrake` ([PyPI](https://pypi.org/project/loopbrake/)).
No other packages are needed.

**1. Set your stop line from your own past runs.** It needs at least 19 successful runs (at α 5%);
with fewer, LoopBrake only watches.

```bash
loopbrake calibrate ~/.claude/projects/<your-project>/ --project my-agent   # your Claude Code history
loopbrake calibrate my_runs.jsonl --project my-agent                         # or recorded runs
```

**2. Add it to your agent loop.**

```python
import loopbrake

with loopbrake.start(project="my-agent") as brake:
    for action, result in my_agent_steps():          # your loop
        decision = brake.step(action, result)
        if decision.stop:
            print(decision.reason); break
```

**3. See how it's doing.**

```bash
loopbrake status --project my-agent        # runs watched, stops, and stops you marked as mistakes
loopbrake feedback <run-id> --mistaken     # tell LoopBrake a stop was wrong
```

**Claude's agent toolkit:** `pip install "loopbrake[agent-sdk]"`, then
`ClaudeAgentOptions(hooks=loopbrake.agent_sdk.hooks(project="my-agent"))`.

Everything stays on your machine, in `~/.loopbrake`. LoopBrake never uses the network. If something
inside it fails, it switches to watching only. It never crashes or stops your agent because of its
own problem.

## Use it with Claude Code

**Install the plugin.** It needs Claude Code 2.1.281 or later and [uv](https://docs.astral.sh/uv/).

```text
/plugin marketplace add SahilSelokar/LoopBrake
/plugin install loopbrake@loopbrake
```

**Set it up** for the project you are in. LoopBrake looks at how many tool calls your past successful
tasks in this project needed, and picks a limit:

```text
/loopbrake:calibrate
```

```text
LoopBrake is set up for this project.
It will stop a task that goes past <limit> tool calls. That limit comes from your <n> past
successful tasks here: fewer than 1 in 20 good tasks should go past it.
```

A **task** is everything Claude does for one message you send. Tool calls made by subagents don't
count. From then on, when a task goes past the limit, Claude stops and tells you why:

```text
LoopBrake stopped this task after <limit + 1> tool calls. Based on your <n> past successful tasks
in this project, good tasks almost never need more than <limit> (fewer than 1 in 20 do). This one
also looks stuck: its last few tool calls repeat each other. If it wasn't stuck, run
/loopbrake:mistake, then tell Claude to continue.
```

| Command | What it does |
|---|---|
| `/loopbrake:calibrate` | Sets the limit from this project's past tasks (run it again any time) |
| `/loopbrake:status` | Shows the limit, how many tasks it saw and stopped, and the stops you marked as mistakes |
| `/loopbrake:mistake` | Tells LoopBrake its last stop was wrong. The next calibration counts that task as a long good one, so the limit can only go up. |
| `/loopbrake:exclude` | Leaves your last finished task out of future calibration (for example, a task that went badly) |

**See the count while you work** (optional; plugins can't add a status line themselves). Add this to
`~/.claude/settings.json` to see `LoopBrake: <calls> of <limit> tool calls` at the bottom of Claude Code:

```json
"statusLine": {"type": "command", "command": "uvx --offline loopbrake statusline"}
```

**What the promise means here.** Each project gets its own limit. On average, fewer than 1 in 20 of
your good tasks will be stopped (5%), as long as your future tasks are like your past ones: the same
kind of work, done the same way. When your work changes, run `/loopbrake:calibrate` again.

**No uv?** Install `loopbrake==0.2.1` with pip, then set `LOOPBRAKE_CMD` to its full path, quoted,
in the environment Claude Code starts from: `export LOOPBRAKE_CMD="'$(which loopbrake)'"`.

**Troubleshooting.** If `/loopbrake:status` says "No tasks recorded here yet" after you have worked in the
project, the hooks are not running. Start Claude Code with `claude --debug` and look for `loopbrake`
hook errors, and check that `uv` is on the PATH Claude Code sees. The plugin never blocks Claude
because of its own problem; it just stops recording.

## Phase 1 results

Before building the product, we tested the idea offline. We replayed **2,979 recorded runs** from
six agent groups, on coding tasks
([SWE-bench Verified](https://github.com/SWE-bench/experiments)) and customer-service tasks
([τ-bench](https://github.com/sierra-research/tau-bench)).

| Finding | Result |
|---|---|
| The guarantee held: good runs stopped by the chosen method, on every test group | **at most 4.9%** (limit 5%) |
| The naive rule "stop at 20 steps or 3 repeats" stops good runs | **99.3%** (Devstral), **29.1%** (GPT-5-mini) |
| Tokens saved by a calibrated step limit (GPT-5-mini, 100 past runs) | **11.2%** |
| Tokens saved by the stuck signals (same setting) | **12.9%** |
| Extra saving from stuck signals over the step limit, with 95% interval | SWE-bench **+1.5%** [−9.7%, +13.2%]<br>τ-bench **+0.9%** [−3.1%, +5.0%] |

**Verdict: NO-GO.** The cheap stuck signals do not clearly beat a calibrated step limit. Following
the plan set in advance, a second experiment tested a progress judge (below).
For comparison, [FailFast](https://arxiv.org/abs/2608.03222), a trained monitor, reports 14.6–20.4%
saved at 5% of good runs stopped. Its threshold was set on the same data it reports on, though, so
that 5% is a target, not a guarantee.

Full report: [eval/results/results.md](https://github.com/SahilSelokar/LoopBrake/blob/main/eval/results/results.md)

## Progress judge: also NO-GO

Counting repeats is not the same as understanding a step, so the second experiment asked a fast
hosted decision model, [Jev](https://docs.typesafe.ai) (`jev-1.13.0`), about every step: *did this
move the agent closer to finishing?* and *what kind of step was it?* Savings are counted **net**:
every token the judge reads is subtracted. The method was chosen on one agent and committed
(`0827ece`) before any other agent was judged.

| Dataset | Extra net saving over the step limit, with 95% interval |
|---|---|
| SWE-bench (GPT-5-mini) | **−6.3%** [−18.9%, +1.9%] |
| τ-bench (4 groups) | **−4.2%** [−8.2%, −1.5%] |

What we learned:

- **A threshold tuned on one agent did not travel.** The chosen method asked the judge only when the
  cheap score passed a level set on Devstral's long runs. On the other agents that level was almost
  never reached (0–0.3% of steps), so the method rarely stopped anything.
- **A judge on every step is expensive.** On short customer-service tasks it used about as many
  tokens as the agent itself.
- **Even ignoring its cost, the judge did not spot stuck runs better than counting steps**: for
  example 7.3% vs 9.3% of tokens saved on GPT-5-mini.
- The guarantee held on every group. The whole experiment took 73,812 judgments, for about $3.91.

Full report: [eval/results/judge/results.md](https://github.com/SahilSelokar/LoopBrake/blob/main/eval/results/judge/results.md)

## How the results are kept honest

- **Chosen in advance.** The method was picked using one agent's runs and committed *before* any
  test runs were scored (commits `8b8eaf3` and, for the judge, `0827ece`).
- **Mistakes stay visible.** The first results were committed exactly as they came out, including a
  flaw in how runs were split (`e655b96`). The fix is a separate, documented commit (`76e8cdc`), with
  before-and-after numbers in [CORRECTIONS.md](https://github.com/SahilSelokar/LoopBrake/blob/main/eval/results/CORRECTIONS.md).
- **Tested on unseen runs.** The stop line is always checked on runs it was not set from.
- **Reproducible.** Every number above comes from `eval/results/` and comes out identical on every run.

## How the guarantee works

1. Each step gets a stuck score. A run's score is the highest score it reaches.
2. Take *n* past successful runs and sort their scores. The stop line is the *k*-th smallest score,
   where *k* = ⌈(*n* + 1)(1 − α)⌉ and α is the share of good runs you accept losing (for example 5%).
3. A new successful run then crosses the stop line with probability at most α.

With α = 5%, LoopBrake needs at least 19 past successful runs. With fewer, it only watches and
never stops anything.

The guarantee holds when new runs look like the past ones (same agent, same kind of tasks), and when
the past runs come from different tasks. We learned the second condition the hard way: see
[CORRECTIONS.md](https://github.com/SahilSelokar/LoopBrake/blob/main/eval/results/CORRECTIONS.md).

## Reproduce

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11+.

```bash
git clone https://github.com/SahilSelokar/LoopBrake && cd LoopBrake
uv run pytest                        # the test suite
uv run python eval/fetch.py          # one-time download, about 450 MB, into ~/.loopbrake/data
uv run python eval/run.py --final    # about 1 minute; writes eval/results/
```

The progress judge needs a [Typesafe](https://typesafe.ai) API key in `TYPESAFE_API_KEY` (or in
`~/.loopbrake/typesafe_key`). Judging every public step costs about $4:

```bash
uv run python eval/tasks.py                              # task texts for the judge
uv run python eval/judge.py --group swe-devstral         # one group at a time; resumable
uv run python eval/judge_eval.py --final                 # reads stored answers only; writes eval/results/judge/
```

## Repository layout

```text
src/loopbrake/   the package: brake, stop-line rule, run readers, Claude Code hooks (standard library only)
plugin/          the Claude Code plugin: hooks, slash commands and the launcher; .claude-plugin/ is the marketplace
eval/            the experiments: fetch.py downloads the data, run.py replays runs, judge.py asks the
                 progress judge, judge_eval.py scores its answers; results/ holds the published numbers
specs/           design: constitution, roadmap, and the spec, plan, research and tasks of each experiment
tests/           tests, including a check of the guarantee on simulated data
liveness.py      the original naive rule, kept as the baseline
```

## Roadmap

| Phase | What | Status |
|---|---|---|
| 1 | **Experiment**: does it work on real runs? | Done: NO-GO for cheap signals |
| 1b | **Progress judge**: a hosted decision model judges whether each step moved the run forward | Done: NO-GO |
| 2 | **Python package**: `pip install loopbrake`; a stop line on run length, with a guarantee and a readable reason | Done: v0.1.0 on PyPI |
| 3 | **Claude Code plugin**: stop stuck turns live, calibrated on your own history | Done: v0.2.1 |
| 4 | **Observability**: live dashboard, plus export to Datadog, Grafana and others via OpenTelemetry | Planned |
| 5 | **Launch**: a demo agent, the public release and a video | Planned |

The full plan is in [specs/roadmap.md](https://github.com/SahilSelokar/LoopBrake/blob/main/specs/roadmap.md).

## Status

v0.2.1 is on PyPI (`pip install loopbrake`), with the Claude Code plugin in this repository. The stop
rule is a stop line on run length, set from your own past successful runs, with a guaranteed limit on
stopping good runs. Next: the observability dashboard and OpenTelemetry export.

## License

[MIT](https://github.com/SahilSelokar/LoopBrake/blob/main/LICENSE). One test fixture is a trimmed τ-bench run, used under τ-bench's own MIT license
(see [tests/fixtures/NOTICE.md](https://github.com/SahilSelokar/LoopBrake/blob/main/tests/fixtures/NOTICE.md)).
