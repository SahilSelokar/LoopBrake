<!--
Sync Impact Report
- Version change: 2.1.0 → 2.2.0 (MINOR: development workflow materially changed)
- Modified sections:
  - Development Workflow, phase gate. Two pre-registered experiments (cheap stuck signals; a hosted
    progress judge) did not beat the calibrated step count on held-out agents. v1 therefore ships the
    calibrated step budget as its stop rule, and the signals only explain stops. Phase 2 is unblocked on
    that basis. A new stop signal enters the product only after it beats the step count on held-out
    agents, pre-registered. Builder's decision, 2026-10-01.
  - Phase order, item 2: now says what the core package ships.
- Principles: unchanged. Principle I's guarantee applies to any score, including run length.
  Principle IV is satisfied: the step budget's numbers are committed (eval/results/).
- Templates: none affected.
- Dependent docs: specs/roadmap.md and README.md updated to match.
- History: 2.1.0 added the liquid glass rules and the stdlib OTLP exporter; 2.0.0 redefined Principle VI
  as Local by Default.
-->

# LoopBrake Constitution

## Core Principles

### I. Guarantee First (NON-NEGOTIABLE)

LoopBrake kills stuck agent runs while bounding how often it kills a run that would have
succeeded. Every rule below exists to keep that promise true.

- A run's score MUST be the highest step score it reaches. The kill threshold τ MUST come from
  split-conformal calibration: τ is the k-th smallest run score among n successful calibration
  runs, where k = ⌈(n+1)(1−α)⌉.
- When k > n (too few calibration runs for the chosen α, e.g. n < 19 at α = 5%), τ = ∞ and
  LoopBrake MUST NOT kill: it runs in observe-only mode.
- Every kill MUST carry a human-readable reason naming the signals that fired.
- README, docs and public content MUST state the guarantee's scope: it is marginal and holds only
  when live runs are exchangeable with the calibration runs (same agent, same task mix).
  Calibration is per project.
- No change may ship if it pushes the measured false-kill rate above α on the eval's held-out
  splits.

Rationale: without the bound, LoopBrake is one more loop detector. The bound is the product.

### II. One Scorer

- Scoring MUST be a pure function of the steps observed so far: no clock, randomness, network
  access or hidden global state.
- The live path (hooks, SDK), calibration and evaluation MUST call the same scoring function.
  No surface re-implements it.
- A test MUST replay one recorded trace through the live path and the offline path and assert
  identical scores.

Rationale: calibration certifies the function it ran. If live scoring differs, the guarantee
certifies nothing.

### III. Stdlib-Only Core

- The `loopbrake` package MUST have zero runtime dependencies (Python standard library only).
  Eval and dev tooling MAY use dev-only dependencies.
- The hook path SHOULD complete in ≤ 200 ms per PostToolUse call on a warm `uvx` cache,
  because it runs after every tool call.
- A System 1 model (Laya or Jev) MAY be added only as an optional extra, and only after
  Principle IV shows the cheap signals have plateaued.

Rationale: a stop controller that is slow to install or slow per step costs more than the loops
it catches.

### IV. Evaluation Decides

- No signal, score change or threshold rule ships without eval numbers: the share of tokens
  saved (overall, and on failed runs) at a false-kill rate ≤ α, averaged over random
  calibration/test splits.
- Evals MUST run on public traces (SWE-bench agent runs, τ-bench) and MAY add local Claude Code
  transcripts.
- Every result MUST be reported against the calibrated `liveness.py` exact-match baseline.
  The external bar is FailFast: 20.4% tokens saved at 5% false-positive rate.
- Results MUST be committed as a table under `eval/`, together with the command that reproduces
  them.

Rationale: "it feels smarter" is not evidence. The headline number is the only claim the project
makes.

### V. Thin Adapters

- The core MUST NOT import or name any agent framework.
- Each surface (Claude Code plugin, Claude Agent SDK, custom agent loops) is an adapter. It turns
  its events into steps and turns decisions back into its own format. Adapters MUST NOT contain
  scoring or calibration logic.
- Claude Code transcript parsing MUST live in a single loader function covered by a pinned
  fixture test, because the transcript format is internal and can change between releases.

Rationale: one engine, many entry points. Every new surface costs a small adapter, never a fork
of the logic.

### VI. Local by Default

- LoopBrake MUST NOT make network calls unless the user explicitly enables an export. With
  nothing enabled, transcripts, run logs and calibration data never leave `~/.loopbrake/`.
  Standard telemetry variables that are already set for other tools (for example
  `OTEL_EXPORTER_OTLP_ENDPOINT`) MUST NOT turn export on by themselves.
- By default, exports MUST carry only run metadata: ids, step numbers, tool names, scores,
  signal values, kill events, reason codes and token counts. Prompt text, tool inputs, tool
  outputs and the excerpts quoted in kill reasons MUST NOT be exported unless the user
  separately opts in to content export.
- Private transcript content MUST NOT appear in commits, test fixtures or public content.
  Fixtures are synthetic or come from public datasets.

Rationale: LoopBrake reads agent transcripts that contain users' code and prompts. Teams adopt
an observability tool only when they control exactly what leaves the machine.

## Technical Constraints

- **Language & packaging**: Python ≥ 3.11. One PyPI package, `loopbrake`, with one CLI:
  `loopbrake hook | calibrate | eval | statusline | dashboard`.
- **Claude Code integration**: the repo doubles as a Claude Code plugin marketplace. A PostToolUse
  hook (matcher `*`) runs `uvx loopbrake hook` and kills with
  `{"continue": false, "stopReason": "<reason>"}`. A run is one turn, from UserPromptSubmit to
  Stop. UserPromptSubmit resets per-turn state.
- **No warn-first in v1**: feeding warnings back to the agent changes its trajectory and breaks
  exchangeability with the calibration runs. It may be added only with calibration done under
  the same warnings.
- **Success labels**: a turn counts as successful when it reached Stop with no user interrupt and
  was not killed. Users can drop turns with `/loopbrake:exclude`.
- **State**: one append-only JSONL log per session at `~/.loopbrake/runs/<session_id>.jsonl`.
  It is the single source for live state, the dashboard and the status line. The status line
  ships as a CLI command because plugins cannot install one.
- **Dashboard**: a working local observability app served by `loopbrake dashboard`. It uses a
  standard-library HTTP server, with no framework and no build step. It reads the run logs live
  and shows:
  - every run with its status: running, finished or killed;
  - a step-by-step run view with signal values, the score line and the τ line;
  - kill reasons;
  - calibration state per project (sample size, α, τ), with actions to refresh calibration and
    exclude runs;
  - kills and tokens spent over time, and the false-kill budget: kills the user marked as
    mistakes, against α × runs.

  It MUST NOT show live "tokens saved". A killed run's counterfactual cost is unknown, so savings
  are claimed only from the offline evaluation (Principle IV).

  - **Security**: it binds to `127.0.0.1` only. It requires a per-launch token, checks the
    `Host` header, and accepts write actions only as POST.
  - **Visual identity**: the Episode 1 reel brand in a **liquid glass** theme.
    - Colors: night `#08110D`, lime `#CFFF3E`, green `#0F3D2E`, red `#E5341F`, paper `#ECEBE4`,
      ink `#0D0E0B`.
    - Fonts: Inter Tight for headings, JetBrains Mono for numbers, Instrument Serif italic for
      annotations.
  - **Glass placement**: glass goes on chrome and floating controls only: navigation, toolbars,
    dialogs, toasts. Content such as tables, charts and step lists sits on near-opaque panels.
  - **Glass behavior**: it MUST degrade gracefully, with an opaque base, blur where supported and
    refraction where supported. It MUST respect reduced motion, reduced transparency, increased
    contrast and forced colors, and it MUST offer a manual "Glass off" toggle.
  - **Red** is used as a fill, never as text. A kill state always pairs it with an icon and a
    word.
  - **Icons**: an SVG icon set (Lucide) only. **No emoji anywhere in the UI.**
  - **Assets**: fonts and icons are vendored with their licenses. The page MUST NOT load
    anything from the network (Principle VI).
  - **Layout**: phone-first, so it records cleanly at 9:16.
- **Integrations**: OpenTelemetry export over OTLP, so LoopBrake data lands in the tools teams
  already run: Datadog, Grafana, Honeycomb, New Relic, Langfuse, Phoenix, or any backend behind
  an OpenTelemetry Collector.
  - **What is exported**: one trace per run and one span per step. A kill is a span event.
    Metrics cover runs, kills, user-reported false kills and tokens spent, as delta counters.
    Attributes follow the OpenTelemetry GenAI semantic conventions where they fit, plus
    `loopbrake.*` attributes.
  - **Configuration**: export is enabled explicitly. The endpoint and headers come from the
    standard `OTEL_EXPORTER_OTLP_*` variables.
  - **Dependencies**: the exporter is implemented with the standard library, as OTLP/HTTP JSON.
    Backends that accept only protobuf are reached through an OpenTelemetry Collector.

## Development Workflow

- **Spec Kit flow** for every feature: specify → clarify (when needed) → plan → tasks →
  implement. One feature per phase.
- **Phase order**:
  1. Experiment
  2. Core package. v1's stop rule is the calibrated step budget; the stuck signals only explain stops.
  3. Claude Code plugin
  4. Observability: the dashboard plus OpenTelemetry export
  5. Launch: a demo agent that gets stuck and is caught by LoopBrake, the public repository, and
     the launch video

  A System 1 model is added only if Principle IV shows a plateau. If that happens, it slots in
  before Launch.

  A phase starts only after the previous phase passes its gate. **Signal gate**: a stop signal enters
  the product only if it beats the calibrated step count on held-out agents, in a pre-registered
  experiment. Until one does, the product stops runs on the calibrated step budget alone, and the
  signals are used only to explain a stop.

  **Decision record (2026-10-01)**: the cheap signals (`specs/001-offline-eval`) and the progress
  judge (`specs/002-progress-judge`) both got a NO-GO. Phase 2 starts with the step budget.
- **Tests**: every non-trivial path (signals, conformal threshold, trace loaders, hook I/O) leaves
  at least one runnable check. pytest is the only test dependency.
- **Simplicity**: the shortest design that works. No abstraction with a single implementation,
  and no configuration for values that never change. Any deviation MUST be justified in the
  plan's Complexity Tracking table.
- **Build in public**: before the repository goes public, `.claude/` MUST be in `.gitignore` and
  the history MUST contain no private transcript content (Principle VI).
- **Public claims**: every number shown in a video, post or README MUST come from committed
  evaluation results (Principle IV). The demo agent's stuck run MUST be a real recorded run,
  not a staged script.

## Governance

- This constitution supersedes other project practices. Every `/speckit-plan` Constitution
  Check MUST evaluate Principles I–VI explicitly, each as pass or fail.
- A failing principle blocks the plan unless the violation is justified in Complexity Tracking.
  Principle I cannot be waived.
- Amendments are made through `/speckit-constitution`. Each one includes a Sync Impact Report,
  a version bump and a commit message that names the change.
- Versioning follows semver:
  - MAJOR: a principle is removed or redefined.
  - MINOR: a principle or section is added or materially expanded.
  - PATCH: wording or clarifications only.

**Version**: 2.2.0 | **Ratified**: 2026-10-01 | **Last Amended**: 2026-10-01
