<!--
Sync Impact Report
- Version change: 2.6.0 → 2.6.1 (PATCH: wording, for the Codex CLI plugin, specs/006 T021)
- Modified: Technical Constraints. "Failing safely" and "Same turns live and in calibration" now
  apply to every agent plugin, not only Claude Code; the Claude Code example of what stays in a
  running turn moved under its own "Turns". Added a "Codex CLI integration" note: the Codex
  marketplace, the two-part stop, trusting hooks once with `/hooks`, turns named by `turn_id`, and
  typed commands. No principle changes.
- History:
  - 2.6.0 changed the dashboard's colors to the Visual Vortex brand.

Previous report (2.6.0):
- Version change: 2.5.0 → 2.6.0 (MINOR: the dashboard's visual identity changed)
- Modified: Technical Constraints, "Dashboard", "Visual identity" (the builder's decision,
  2026-10-02).
  - Was: the Episode 1 reel colors (night, lime, green, red, paper, ink).
  - Now: the Visual Vortex brand (visualvortexcreatives.dev): night, surface and paper, coral as the
    main accent, the coral to rose to plum gradient, green and blue as secondary colors. Red stays,
    for the stopped state only.
  - On light backgrounds coral is a fill only; text accents there use a deep plum (coral on white
    is 2.99:1, below WCAG AA).
  - No logo mark next to the LoopBrake name. Fonts unchanged.
- Principles I–VI: unchanged.
- Dependent docs: specs/005-observability contracts/ui.md ("Look") and the roadmap's Phase 4 design
  notes follow in the dashboard tasks.
- History:
  - 2.5.0 made the dashboard plain-worded, light and dark, with no glass switch.
  - 2.4.1 made export counters delta by default, cumulative on request.
  - 2.4.0 set turn boundaries, fail-safe hooks, and the mistaken-stop rule.
  - 2.3.0 added open core and releases.
  - 2.2.0 recorded the step-budget decision and the signal gate.
  - 2.1.0 added liquid glass and the OTLP exporter.
  - 2.0.0 redefined Principle VI as Local by Default.
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
- **Claude Code integration**: the repo doubles as a Claude Code plugin marketplace.
  - **Hooks**: they run the version-pinned `loopbrake hook` through the plugin's launcher, which
    uses uv's cached copy first, so the hook path needs no network. PostToolUse and
    PostToolUseFailure hooks (matcher `*`) count the main agent's tool calls. Tool calls made inside
    subagents never count. A stop is `{"continue": false, "stopReason": "<reason>"}`.
  - **Turns**: a run is one turn.
    - It starts at UserPromptSubmit, or at the first main-agent tool call after Stop (work woken by
      a background task).
    - It ends at Stop. If a new prompt arrives first, it ends there as interrupted (or stopped, if
      LoopBrake stopped it).
    - A record that arrives while Claude is still waiting on a tool (a compaction summary, a prompt
      typed mid-turn, a task notification) stays in the running turn.
- **Codex CLI integration**: the repo also offers a Codex plugin (`codex-plugin/`) from its Codex
  marketplace (`.agents/plugins/marketplace.json`).
  - **Hooks**: through the same launcher. `PostToolUse` counts the main agent's tool calls; helper
    agents' calls never count. A stop is a `PostToolUse` reply with `continue: false`, and every
    later tool call of that task is refused in `PreToolUse`, including calls of a parallel batch
    already on their way that would run after the stop (asked of the brake, never decided by the
    adapter).
  - **Trust**: Codex runs a plugin's hooks only after the user trusts them once with `/hooks`, so
    the hook definitions MUST NOT change between versions; only the launcher's pinned version does.
  - **Turns**: a run is one Codex turn, named by Codex's own `turn_id` in both the hooks and the
    session history.
  - **Commands**: typed as a message (`loopbrake: status` and so on) and run by the prompt hook,
    outside Codex's sandbox.
- **Every agent plugin** (Claude Code and Codex CLI):
  - **Failing safely**: a failure in the plugin's own hook path MUST NOT block a prompt, a tool call
    or the agent stopping. It exits 0 with no output.
  - **Same turns live and in calibration**: each agent's history reader MUST cut its history at the
    same boundaries its live hooks see. Where live and calibration counts can still differ, the live
    count MUST be the lower one, because a lower count can only stop later. Every plugin release
    MUST check this on the builder's real use (`loopbrake agreement`).
- **No warn-first in v1**: feeding warnings back to the agent changes its trajectory and breaks
  exchangeability with the calibration runs. It may be added only with calibration done under
  the same warnings.
- **Success labels**: a turn counts as successful when it reached Stop with no user interrupt and
  was not killed. Users can drop turns with `/loopbrake:exclude`.
  - **Mistaken stops**: a kill the user marked as a mistake counts in later calibrations as a
    successful turn longer than any stop line. Its real length is unknown, but it's above the line.
    So marking mistakes can only raise the line, and recalibrating can never quietly lower it.
  - **Other kills**: left out, as stuck turns.
- **State**: one append-only JSONL log per session at `~/.loopbrake/runs/<session_id>.jsonl`.
  It is the single source for live state, the dashboard and the status line. The status line
  ships as a CLI command because plugins cannot install one.
- **Dashboard**: a working local observability app served by `loopbrake dashboard`. It uses a
  standard-library HTTP server, with no framework and no build step. It reads the run logs live
  and shows:
  - every task with its status: running, finished, stopped or interrupted;
  - a task view: its actions over time against the limit, the repeats that show a loop, and every
    action in plain words;
  - why a task stopped, in plain words, with the project's past tasks drawn as a picture next to
    the limit;
  - per project: the limit and the past tasks it came from, with actions to set the limit again
    and to leave tasks out;
  - stops and tokens spent over time, and the stops the user marked as mistakes next to how many
    are expected (α × tasks watched).

  It MUST NOT show live "tokens saved". A stopped run's counterfactual cost is unknown, so savings
  are claimed only from the offline evaluation (Principle IV).

  - **Plain words**: the dashboard MUST be readable by people who don't code.
    - One word per idea: "task", "action" (one tool call; a "?" explains it), "limit", "stopped",
      "mistake".
    - Tools are named by what they did ("Ran a command", "Read a file").
    - τ, α, score, kill, step and run or session ids MUST NOT appear on screen. Ids appear only in
      page addresses.
  - **Security**: it binds to `127.0.0.1` only. It requires a per-launch token, checks the
    `Host` header, and accepts write actions only as POST.
  - **Visual identity**: the Visual Vortex brand (visualvortexcreatives.dev), with **liquid
    glass** on chrome.
    - Colors: night `#0A0A0A`, surface `#111218`, paper `#EDEDED`, coral `#EA7252` (the main
      accent), rose `#C7576C` and plum `#A6447F` (coral to rose to plum is the brand gradient),
      green `#1D9E75` and blue `#378ADD` (secondary), and red `#E5341F` for the stopped state only.
    - Themes: a light theme and a dark theme from these colors. The page follows the system's
      setting, and Settings offers light, dark or system. Every text color pair in both themes MUST
      meet WCAG AA. On light backgrounds coral is a fill only, never text; text accents there use a
      deep plum.
    - The LoopBrake name stands alone, with no logo mark next to it.
    - Fonts: Inter Tight for headings, JetBrains Mono for numbers, Instrument Serif italic for
      annotations.
  - **Glass placement**: glass goes on chrome and floating controls only: navigation, toolbars,
    dialogs, toasts. Content such as tables, charts and action lists sits on near-opaque panels,
    so glass never stands behind information.
  - **Glass behavior**: it MUST degrade gracefully, with an opaque base, blur where supported and
    refraction where supported. It MUST respect reduced motion, reduced transparency, increased
    contrast and forced colors: under reduced transparency or increased contrast, glass turns off
    by itself. There is no manual glass switch (the builder's decision, 2026-10-02).
  - **Red** is used as a fill, never as text. A stopped state always pairs it with an icon and a
    word.
  - **Icons**: an SVG icon set (Lucide) only. **No emoji anywhere in the UI.**
  - **Assets**: fonts and icons are vendored with their licenses. The page MUST NOT load
    anything from the network (Principle VI).
  - **Layout**: phone-first, so it records cleanly at 9:16.
- **Integrations**: OpenTelemetry export over OTLP, so LoopBrake data lands in the tools teams
  already run: Datadog, Grafana, Honeycomb, New Relic, Langfuse, Phoenix, or any backend behind
  an OpenTelemetry Collector.
  - **What is exported**: one trace per run and one span per step. A kill is a span event.
    Metrics cover runs, kills, user-reported false kills and tokens spent, as counters. They are
    delta by default (Datadog's direct intake accepts only delta). They are cumulative only when the
    standard `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=cumulative` asks for it (Grafana and
    other Prometheus-based backends need cumulative).
    Attributes follow the OpenTelemetry GenAI semantic conventions where they fit, plus
    `loopbrake.*` attributes.
  - **Configuration**: export is enabled explicitly. The endpoint and headers come from the
    standard `OTEL_EXPORTER_OTLP_*` variables.
  - **Dependencies**: the exporter is implemented with the standard library, as OTLP/HTTP JSON.
    Backends that accept only protobuf are reached through an OpenTelemetry Collector.

- **Open core**:
  - **Public**: the `loopbrake` package (brake, calibration, command line, adapters) and this
    repository are MIT-licensed and public.
  - **Private**: features kept private (for example a hosted team dashboard, managed calibration, or
    a judge as a service) live in a separate private repository and run only as services the builder
    operates.
  - **Rules**: nothing private may ship inside the package, because Python packages are readable.
    The package MUST work fully on its own and MUST NOT require any private service. Sending run
    content to such a service is an export under Principle VI and needs explicit opt-in.
- **Releases**: the package is published to PyPI by a GitHub Actions workflow on a version tag
  (`vX.Y.Z`), using PyPI trusted publishing. No upload token is ever stored or pasted. The tag MUST
  match the package version.

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

**Version**: 2.6.1 | **Ratified**: 2026-10-01 | **Last Amended**: 2026-10-02
