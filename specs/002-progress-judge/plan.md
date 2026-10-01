# Implementation Plan: Progress Judge Experiment

**Branch**: `002-progress-judge` | **Date**: 2026-10-01 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-progress-judge/spec.md`

## Words used in this plan

The Phase 1 words (run, step, stuck score, stop line, false stop, α, calibration) mean the same as
in `specs/001-offline-eval/plan.md`. New words:

| Word | Meaning |
|---|---|
| **Judge** | Jev, Typesafe's hosted decision model. For each step it returns P(progress) and the most likely kind of step. |
| **Judgment** | One stored answer for one step |
| **Net tokens saved** | Tokens saved by stopping runs, minus every token the judge used |
| **Ask only when needed** | Consult the judge only on steps the cheap Phase 1 score already finds suspicious |

## Summary

Phase 1 showed that cheap signals barely beat "stop runs that go on too long". This experiment asks
whether a fast decision model that *understands* each step does better, measured honestly.

- **Judging**: every step of the six public groups is sent once to Jev, about 74k requests for
  about $3. The answers are stored, and from then on every evaluation reads the stored answers, so
  results repeat exactly.
- **Scoring**: three judge-based stuck scores reuse Phase 1's stop-line rule, splits and intervals.
- **Cost**: savings are counted **net** of the judge's own tokens.
- **Protocol**: the method is chosen on the development group and committed before any holdout
  group is judged, and the tooling enforces that order.
- **Live use**: an "ask only when needed" variant measures how practical a judge would be in a
  running agent.

## Technical Context

| Item | Value |
|---|---|
| **Language/Version** | Python ≥ 3.11 |
| **Primary Dependencies** | None new. The Jev client uses the standard library (`urllib`, `json`, `concurrent.futures`, `hashlib`). pytest for tests. |
| **External service** | Typesafe System One API, model `jev-1.13.0` (pinned). Used by experiment tooling only, never by the package core. |
| **Storage** | Task texts in `~/.loopbrake/data/tasks/`; judgments in `~/.loopbrake/judgments/<setup>/`; published results in `eval/results/judge/` |
| **Testing** | pytest with a fake HTTP opener (no network in tests): request building, parsing, retries, refusals, the judged scorer and net savings |
| **Target Platform** | The builder's laptop (Apple M3 Pro) with internet access during judging only |
| **Project Type** | The same library core plus experiment scripts |
| **Performance Goals** | Judging about 45 minutes at 30 requests a second (SC-003 allows 12 h); each evaluation run under 5 minutes |
| **Constraints** | Only public-dataset steps are sent. The access key never enters the repo, results or logs. Holdout groups can't be judged before the candidate is committed. Phase 1 code and results stay unchanged. |
| **Scale/Scope** | 73,812 steps, about 61M input tokens, about $2.60 (research R3) |

Every unknown is resolved in [research.md](research.md):
- **R1**: which judge (Laya rejected);
- **R2**: the request design;
- **R3**: speed and cost;
- **R4**: storage;
- **R5**: task texts;
- **R6**: the methods;
- **R7**: net savings;
- **R8**: the variant;
- **R9**: the protocol;
- **R10**: privacy;
- **R11**: implications for live use.

## Constitution Check

*GATE: must pass before Phase 0 research. Checked again after the Phase 1 design.*

| Principle | Before research | After design | Why it passes |
|---|---|---|---|
| I. Guarantee First | PASS | PASS | The same stop-line rule and the one-run-per-task split. Every stop names the judge's view. SC-001 checks the limit on every holdout group. |
| II. One Scorer | PASS | PASS | `loopbrake.signals.judged()` is pure: same steps and same judgments give the same scores, with no look-ahead (tested). The product would call it with live judgments. |
| III. Stdlib-Only Core | PASS | PASS | No new dependency, and the Jev client is plain `urllib`. A judge model as an optional extra is allowed now that Phase 1 showed a plateau. Live delay is measured for Phase 3, not assumed. |
| IV. Evaluation Decides | PASS | PASS | The same gate as Phase 1, made stricter by using net savings. Results are committed with the reproduce commands; corrections are logged. |
| V. Thin Adapters | PASS | PASS | The Jev client lives in `eval/judge.py`, outside the core. The core gains only the pure scorer. |
| VI. Local by Default | PASS (see note) | PASS | LoopBrake itself still makes no network calls. The experiment tooling sends **public** dataset steps to Jev, with the builder's explicit approval (2026-10-01). Private history is excluded and refused in code. The key stays outside the repo. |
| Workflow: phase gate | PASS | PASS | No product code: the package (Phase 2) still waits for a GO |
| Workflow: simplicity | PASS | PASS | One setup, decided in advance. Three scripts, one pure function, no SDK. |

**Note on Principle VI**: the principle governs what LoopBrake, the product, does on a user's
machine. This feature is experiment tooling run by the builder on public data, like
`eval/fetch.py`. If a hosted judge ever goes into the product, it would count as content export and
need its own explicit opt-in (research R10).

## Project Structure

### Documentation (this feature)

```text
specs/002-progress-judge/
├── plan.md              # this file
├── research.md          # R1–R13
├── data-model.md        # task text, judge setup, judgment, judge method, net result row, candidate
├── quickstart.md        # end-to-end validation against SC-001…SC-008
├── contracts/
│   ├── judge-request.md     # the Jev request, the stored judgment line, the pure scorer
│   ├── judge-cli.md         # eval/tasks.py, eval/judge.py, eval/judge_eval.py
│   └── judge-results.md     # eval/results/judge/ files
├── checklists/requirements.md
└── tasks.md             # created next by /speckit-tasks
```

### Source code (changes only)

```text
src/loopbrake/signals.py      + judged(name, lam): pure scorer over (steps, progress)   (R6)
eval/tasks.py                 new: task texts from the raw files                        (R5)
eval/judge.py                 new: Jev client: build, call, retry, store, resume, re-check, refuse   (R2–R4, R9, R10)
eval/judge_eval.py            new: --dev / --final / --story for judge methods; net savings; variant (R6–R8, R12)
eval/judge_candidate.json     new: the pre-registered choice, committed before holdout judging
eval/results/judge/           new: published results (contracts/judge-results.md)
tests/test_judge.py           new: request building, parsing, retries, refusals (fake opener)
tests/test_judge_eval.py      new: net savings, variant cost, candidate refusal
tests/test_signals.py         + judged scorer: no look-ahead, no-opinion behavior
specs/roadmap.md              updated: this experiment comes before the package
```

Untouched: `eval/run.py`, `eval/fetch.py`, `eval/results/*` from Phase 1, and the Phase 1 tests.

**Structure decision**: it follows Phase 1's layout. The new scripts sit next to the Phase 1 ones
and import their machinery.

## Complexity Tracking

No constitution rule is broken. One deliberate shortcut:

| Shortcut | Limit | Fix if it becomes a problem |
|---|---|---|
| One judge setup decided in advance, with no prompt search | A better wording may exist | A logged `v2` is allowed on the development group only (research R9). A real prompt search would need its own development/holdout split. |
