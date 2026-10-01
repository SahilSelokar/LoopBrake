# Implementation Plan: Offline Evaluation Experiment

**Branch**: `001-offline-eval` (no git repository yet) | **Date**: 2026-10-01 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-offline-eval/spec.md`

## Words used in this plan

| Word | Meaning |
|---|---|
| **Run** | One attempt by an agent at one task |
| **Step** | One action the agent takes (for example, running a command) plus the result it gets back |
| **Stuck score** | A number LoopBrake computes after each step. Higher means "looks more stuck". |
| **Stop line (τ)** | The score above which LoopBrake stops a run |
| **False stop** | Stopping a run that would have succeeded. Its rate is the *false-kill rate*. |
| **α (alpha)** | The highest false-stop rate we allow. 5% means at most 5 in 100 good runs. |
| **Calibration** | Setting the stop line from *n* past successful runs, using the rule in constitution Principle I. This rule is what keeps the false-stop rate at or below α. |

## Summary

One question, answered with real data: if we stop agent runs that look stuck, how many tokens do
we save, while stopping at most α of the runs that would have succeeded?

**Data**:
- **SWE-bench Verified**: coding tasks, two sets. Each step records its real token count.
- **τ-bench**: customer-service tasks, four sets. Token counts are estimated from text length.
- **Optionally**: your own Claude Code history.

Every run in these sets is marked as succeeded or failed.

**How the experiment works**:
- **Replay**: we feed each recorded run to LoopBrake one step at a time, exactly as if it were
  happening live. At each step it may only look at the steps so far.
- **Stop line**: set from a random sample of *n* successful runs. When a task was attempted
  several times, all of its runs go on the same side (sample or test), so the test never
  includes a task the stop line was set on.
- **What we measure**: the share of all tokens saved, the same measure FailFast uses. We
  compare against three simple methods based on liveness.py. One of them just stops runs that
  go on too long; FailFast calls this "Duration". It's the real bar to beat.
- **Go/no-go**: we choose one method using one agent's data only (Devstral), then write it down
  and commit it. After that, we test it on the other agents. "Go" means it beats the best simple
  method on both datasets, and its error bars stay above zero.

**Code**: the scoring code is written once in `src/loopbrake/`, and the product reuses it
unchanged later. The experiment code lives in `eval/`.

## Technical Context

| Item | Value |
|---|---|
| **Language/Version** | Python 3.11 or newer |
| **Primary Dependencies** | None. Only Python's built-in library (constitution Principle III). pytest is used for tests only. Commands run with `uv run`. |
| **Storage** | Downloaded data in `~/.loopbrake/data/`. Results from your own history in `~/.loopbrake/eval/`. Results we publish in `eval/results/`. |
| **Testing** | pytest. The four key tests:<br>1. The stop line gives the expected false-stop rate on simulated data.<br>2. Scoring never looks at future steps.<br>3. The old liveness.py rule gives the same answers as before.<br>4. A made-up Claude Code history file is read correctly. |
| **Target Platform** | A laptop (macOS or Linux). No internet needed after the one-time download. |
| **Project Type** | A Python library (the scoring code) plus two scripts for the experiment |
| **Performance Goals** | The full final run finishes in under 15 minutes. Expected: about 6–7 minutes (research R12). |
| **Constraints** | Internet is used only by `eval/fetch.py`. The same inputs and random seed always give identical results. Nothing from your private history goes into published files. |
| **Scale/Scope** | About 2,900 public runs (about 70,000 steps), plus about 700 of your own Claude Code turns |

All open questions are answered in [research.md](research.md):
- which datasets to use (R1, R2);
- how tokens are counted (R3);
- how FailFast measures savings (R4);
- how the error bars are computed (R8);
- how Claude Code history files are laid out (R10).

## Constitution Check

*GATE: must pass before Phase 0 research. Checked again after the Phase 1 design.*

| Principle | Before research | After design | Why it passes |
|---|---|---|---|
| I. Guarantee First | PASS | PASS | The stop line is computed with exact math, so there are no rounding errors. With too few successful runs, LoopBrake never stops anything. Every stop says why. The results report states plainly when the guarantee holds and when it doesn't. |
| II. One Scorer | PASS | PASS | The scoring code lives in one place (`src/loopbrake/signals.py`), and the experiment imports it. A test checks that scoring never uses future steps. The live-versus-replay test comes in Phase 2, once a live path exists. |
| III. Stdlib-Only Core | PASS | PASS | No extra libraries anywhere; downloads use Python's built-in `urllib`. pytest is for tests only. No AI model is used for scoring. |
| IV. Evaluation Decides | PASS | PASS | This feature *is* the evaluation. Results are published with the exact command and data fingerprints (checksums) needed to reproduce them. |
| V. Thin Adapters | PASS | PASS | The scoring code sees only plain steps and runs. Code that understands each dataset's file format lives in `eval/fetch.py`. Claude Code files are read by one function that has its own test. |
| VI. Local by Default | PASS | PASS | Phase 1 sends nothing anywhere; the only internet use is the one-time download. Your history stays in `~/.loopbrake/`, and published rows about it are renamed `local-1`, `local-2`. Test files are made up, or come from τ-bench (MIT license). |
| Workflow: phase gate | PASS (see note) | PASS | Phase 1 writes only the scoring code the experiment tests. The product parts (Brake, the command line, the plugin) wait for a "go". |
| Workflow: simplicity | PASS | PASS | Three small modules, two scripts and plain records. No extra layers. |

**Note on the phase gate**: the constitution says no "package code" gets written before the
experiment passes. We read that as the product parts. The scoring code has to exist for the
experiment to run, and Principle II says the product must use that very same code. Writing it
in `eval/` and copying it later would break that rule.

## Project Structure

### Documentation (this feature)

```text
specs/001-offline-eval/
├── plan.md              # this file
├── research.md          # answers to the open questions (R1–R12)
├── data-model.md        # the records we use: step, run, group, method, stop line, result row, verdict
├── quickstart.md        # how to run everything and check it against the success criteria
├── contracts/
│   ├── normalized-runs.md   # the common file format all datasets are converted into
│   ├── scoring-api.md       # the scoring functions the product must reuse
│   ├── eval-cli.md          # how to run eval/fetch.py and eval/run.py
│   └── results.md           # the layout of the published results
├── checklists/requirements.md
└── tasks.md             # created next by /speckit-tasks
```

### Source Code (repository root: `LoopBrake/`)

```text
pyproject.toml            # package name loopbrake, Python 3.11+, no dependencies; pytest for tests
.gitignore                # .claude/ (constitution rule), __pycache__/, .venv/
liveness.py               # unchanged: the original simple rule, used as a baseline
src/loopbrake/
├── __init__.py
├── signals.py            # stuck-score methods; each step's score comes with a reason (R5, R6)
├── conformal.py          # the stop-line rule (R7)
└── traces.py             # read and write runs; read Claude Code history (R10)
eval/
├── fetch.py              # one-time download, converted to ~/.loopbrake/data/runs/*.jsonl (R1, R3)
├── run.py                # random splits, error bars, results, go/no-go, kill stories (R7–R9)
├── candidate.json        # the chosen method, written by hand and committed before the final run (R9)
└── results/              # published results (contracts/results.md)
tests/
├── test_conformal.py     # stop-line edge cases; false-stop rate on simulated data (expected 1/21)
├── test_signals.py       # each signal on small hand-made runs; never looks ahead; liveness.py match
├── test_traces.py        # file round-trip; made-up Claude Code history file
├── test_eval.py          # task-level splits; identical results on rerun; "not enough data" cases
└── fixtures/             # made-up history file + a few trimmed τ-bench runs (MIT)
```

**Structure decision**: one project. `src/` holds the code that becomes the package; `eval/`
holds code used only for the experiment. Tests sit in one folder, since there are only a few.

## Complexity Tracking

No constitution rule is broken. There are two deliberate shortcuts with known limits. Each one
gets a `ponytail:` comment in the code.

| Shortcut | Limit | Fix if it becomes a problem |
|---|---|---|
| At each step, the score is recomputed from all steps so far | Work grows with the square of the run's length. Still fine for the longest runs here (250 steps). | Phase 2's `Brake` keeps a running total instead. The "never looks ahead" test checks both give the same scores. |
| The 1,000 random splits are computed in plain Python | About 7 minutes | First, compute error bars only for the main setting. If that's not enough, precompute the savings for every possible stop line (R12). |
