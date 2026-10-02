# LoopBrake Roadmap: Outcomes, Architecture and Phases

**Date**: 2026-10-01 | **Constitution**: v2.5.0 | **Status**: Phase 1 and the progress-judge experiment are done, both NO-GO. Decision: v1 ships the calibrated step budget. Phase 2 is done: v0.1.0 is on PyPI (2026-10-01). Phase 3 is done: the Claude Code plugin ships with v0.2.1 (2026-10-02, PyPI and this repo's marketplace). Phase 4 is done: the dashboard and OpenTelemetry export ship with v0.3.0 (2026-10-02). Next: Phase 4b, a Codex CLI plugin (the builder's decision, 2026-10-02), then Launch.

This is the master plan for the whole project. Each phase becomes its own Spec Kit feature
(`specs/00N-*`) and goes through `/speckit-specify`, then `/speckit-plan`, `/speckit-tasks` and
`/speckit-implement`. Each phase's spec is seeded from its section below. Where this file
disagrees with a phase's own spec or plan, the phase documents win, and this roadmap gets
updated.

## Why this exists

The project builds credibility through rigor, not a demo trick. It ends with a launch video:
"my agents kept getting stuck, so I built this; if you have the same problem, use it." Every
number in that video comes from committed evaluation results. The stuck run shown is a real
recording, not a staged script.

## Outcomes

| # | Outcome | Done when (measurable) | Phase |
|---|---|---|---|
| O1 | **Proof** | A committed report gives held-out tokens saved at a guaranteed false-kill rate on public SWE-bench and τ-bench runs, against a calibrated step-budget baseline, with a pre-registered go/no-go verdict | 1 |
| O2 | **Package** | `uvx loopbrake` / `pip install loopbrake` installs with zero dependencies. A custom Python agent loop gets brakes by adding 3 lines. Live kills match the offline evaluation exactly in a replay test. | 2 |
| O3 | **Claude Code** | One plugin install. It calibrates from the user's own history, kills a real stuck session live with a readable reason, and adds at most 200 ms (p95) to each tool call. | 3 |
| O4 | **Observability** | A working local dashboard in the liquid glass theme, plus OpenTelemetry export verified end to end into an OTel Collector, Datadog, Grafana and Honeycomb. LoopBrake spans nest inside Claude Code's own traces when tracing is on. | 4 |
| O5 | **Launch** | Public repository, a published package, and a plugin marketplace listing. A stranger reaches their first kill in under 5 minutes. A demo agent's real stuck run is caught on camera. The launch video is out. | 5 |

## Shared architecture (fixed now, built over phases)

```text
            ┌──────────── scoring core (Phase 1) ────────────┐
            │ signals.py   conformal.py   traces.py           │  pure, stdlib, certified offline
            └──────────────────────┬─────────────────────────┘
                                   │ same functions (Principle II)
   offline eval (P1) ◄─────────────┼─────────────► Brake (P2): stateful wrapper, one per run
                                   │                    │ writes
                                   │                    ▼
                                   │        run log: ~/.loopbrake/runs/<session>.jsonl
                                   │        (append-only events: the single source of truth)
                                   │                    │ read by
        ┌───────────────┬──────────┴──────┬─────────────┴──┬──────────────────┐
   hook / CLI (P2–P3)  status line (P3)  dashboard (P4)   OTel exporter (P4)  demo agent (P5)
```

### Run log events: the cross-phase contract

Phase 2 defines and versions the run log. All later phases only read it.

| Event | Key fields |
|---|---|
| `run_start` | `v`, `ts`, `run`, `session`, `agent`, `project`, `calibration{method, lam, alpha, n, k, tau}` (τ = ∞ means observe-only) |
| `step` | `run`, `step`, `tool`, `tool_call_id`, `action_excerpt` (≤ 200 chars, local only), `score`, `signals{fuzzy, stale, errors}`, `tokens`, `reason` |
| `stop` | `run`, `step`, `stop_line`, `reason` (renamed from `kill`; the exact fields are in `specs/003-core-package/contracts/records.md`) |
| `run_end` | `run`, `status` (`finished`, `killed`, `interrupted`), `steps`, `tokens` |
| `feedback` | `run`, `verdict` (`mistaken_stop`, `exclude`), `ts`. Feeds the false-kill budget and recalibration. |

**Calibration file**: `~/.loopbrake/calibration/<project>.json` holds the method, λ, α, n, k, τ,
the calibration run ids and their scores, the date and the version. Phase 2 writes it and Phases
3–4 read it.

**What can be claimed live, and what can't**:
- A live run that's been killed never shows what it *would* have cost, so **tokens saved is only
  claimed from the offline evaluation**.
- Live surfaces show kills, tokens spent, and the **false-kill budget**: kills the user marked
  as mistakes, compared against α × runs.

## Phases

### Phase 1: Experiment (`001-offline-eval`, status: done, verdict NO-GO on 2026-10-01)

- **Goal**: show that the idea works, or doesn't, before building the product.
- **Deliverables**:
  - scoring core: `src/loopbrake/{signals, conformal, traces}.py`;
  - `eval/fetch.py` and `eval/run.py`;
  - committed `eval/results/`, including kill stories.
- **Exit gate**: the pre-registered candidate beats the stronger calibrated baseline on the
  holdout groups, on both datasets (details in plan.md).
  - **No-go**: rework the signals, or trigger the System 1 model (conditional).
- **Risks**:
  - The S3 trajectory license is unstated. Only short excerpts are quoted.
  - Runtime could exceed 15 minutes. Fallback in research R12.
- **Reels**:
  - "The naive 20-step rule kills most successful runs."
  - The first real number.
- **Size**: L.

### Decision after two NO-GOs (2026-10-01)

Neither the cheap stuck signals nor the progress judge beat the calibrated step count on held-out
agents. So **v1's stop rule is the calibrated step budget**: stop a run once it has gone on longer
than a stop line set from your own past successful runs, with the false-stop guarantee. The stuck
signals still run, but only to explain *why* a stopped run looked stuck.

**Measured savings at 5% false stops** (committed in `eval/results/`):
- 9.3% at n = 20, and 11.2% at n = 100, on GPT-5-mini;
- 20.7–24.7% on Devstral;
- 0.9–9.2% on τ-bench.

The range depends on the agent: long, wandering runs leave the most to save.

### Phase 2: Core package (`003-core-package`)

**Open core and releases** (constitution 2.3.0): the package is public (MIT) and published to PyPI
from GitHub tags with trusted publishing. Private features, if any, are hosted services in a separate
private repository, and never ship in the package.


**v1 scope**: the `steps` method is the stop rule. `fixed`, `exact` and the signal methods stay in the
package for explanations and future experiments, but they never decide a stop.


- **Goal**: turn the certified scorer into a product API that never re-implements it.
- **Deliverables**:
  - `Brake` (`step(...)` returns a decision `{kill, score, reason}`; `end(status)`), which
    writes the run log;
  - calibration from Claude Code history or a normalized runs file;
  - CLI: `loopbrake calibrate | status | hook`;
  - a Claude Agent SDK adapter (an in-process PostToolUse callback);
  - an integration snippet for custom loops;
  - `pyproject` packaging, CI (pytest on push), `LICENSE`.
- **Interfaces fixed here**: the run log events and calibration file above, and the public
  Python API (semver from 0.1.0).
- **Exit gate**:
  - **Replay test**: `Brake` fed recorded runs step by step kills at exactly the step the
    offline evaluation reports (Principle II).
  - Zero runtime dependencies.
  - A cold `uvx loopbrake --version` works.
- **Risks**: the stop mechanism in the Agent SDK. `continue: false` is verified in the
  Claude Code CLI hooks docs, but it needs checking in the SDK (Phase 2 research).
- **Reel**: "3 lines that put brakes on any agent."
- **Size**: M.

### Phase 3: Claude Code plugin (`004-claude-code-plugin`, status: done, v0.2.1 on 2026-10-02)

- **Goal**: zero-friction install for Claude Code users.
- **Deliverables**:
  - the plugin (`hooks.json`: PostToolUse `*` for scoring and kills, UserPromptSubmit for
    run start, Stop for run end);
  - commands `/loopbrake:calibrate`, `/loopbrake:status`, `/loopbrake:mistake`, `/loopbrake:exclude`;
  - a `loopbrake statusline` command (`brake 12/38`, the step count against the stop line);
  - the repo doubles as a marketplace (`.claude-plugin/marketplace.json`).
- **Exit gate**:
  - A recorded real stuck turn is killed live, with the reason shown to the user.
  - It stays observe-only until calibrated.
  - Hook p95 is at most 200 ms, measured.
  - Uninstalling leaves nothing behind except `~/.loopbrake/`.
- **Risks**:
  - `uvx` cold start eats the latency budget. Mitigation: recommend
    `uv tool install loopbrake` and call the binary directly.
  - The transcript format changes. Mitigation: a pinned fixture plus a version check.
- **Reel**: LoopBrake kills a stuck Claude Code session live. This is the strongest reel.
- **Size**: M.

### Phase 4: Observability (`005-observability`, status: done, v0.3.0 on 2026-10-02)

- **Goal**: a working observability tool, local first, that also plugs into company tools.

#### Dashboard

`loopbrake dashboard` runs a stdlib HTTP server that serves vendored static assets and a small
JSON API over the run logs. Live updates come from polling. Screens:

| Screen | Contents |
|---|---|
| Overview | KPI tiles (runs, kills, false-kill budget used, tokens spent); live runs with status; kill feed |
| Run | Score line, τ line and kill marker over steps; step table (tool, action excerpt, signal values, tokens); reason card; **Mark as mistaken kill** |
| Calibration | For each project: n, α, τ, method and age; dot plot of calibration scores with the τ line; observe-only badge; **Recalibrate**; **Exclude runs** |
| Integrations | Export on/off, endpoint, protocol, last send result, **Test connection**; content export opt-in (off by default) |

**Security**: binds to `127.0.0.1` only, uses a per-launch token in the URL, and checks the
`Host` header against DNS rebinding. Write actions require POST with the token.

#### Liquid glass design system

The decisions below come from the Phase 4 research (2026-10-01). Detailed specs come in that
phase.

- **Where glass goes**: only on chrome and floating controls (top bar, sidebar, toolbars,
  dialogs, toasts). Following Apple's own rule, content such as tables, charts and step lists
  sits on near-opaque night panels. This is right for legibility, and it's fast: `backdrop-filter`
  over scrolling tables is expensive.
- **Layers, bottom to top**:
  1. Night `#08110D`.
  2. One fixed layer of lime and deep-green glows, at 35% alpha or less (the reel background).
  3. Content panels.
  4. Glass controls: tint (night at about 0.6), blur 20px or less with 170% saturation, a 1px
     rim with an inset top highlight, a pointer-following sheen, and an outer shadow.
  - At most 3–4 glass layers per screen.
- **Progressive enhancement**:
  1. An opaque base that works everywhere.
  2. `@supports (backdrop-filter)` adds blur.
  3. SVG refraction (`feDisplacementMap`) in Chromium only. Safari and Firefox can't apply SVG
     filters inside a backdrop, and Firefox drops the whole property.
  4. The sheen, only with `prefers-reduced-motion: no-preference`.
- **Accessibility**:
  - `prefers-reduced-transparency` works in Chromium only, so there's also a manual **Glass
    off** toggle that works in every browser.
  - `prefers-contrast: more` gives opaque panels with 2px borders. `forced-colors` is respected.
  - Focus rings: `:focus-visible`, a 2px lime outline with a night halo.
  - **Red `#E5341F` is a fill, never text.** It is 4.42:1 on night, which fails WCAG AA for
    text. Kill states always pair the red fill with the `octagon-x` icon and the word "Killed".
- **Icons**: Lucide (ISC, 1,857 icons), vendored as `static/icons.svg` and used through
  `<use href>`. Styling: stroke `currentColor`, stroke width 1.75, round caps and joins. The
  core set:
  - run states: `play`, `loader-circle`, `octagon-x`, `check`, `triangle-alert`;
  - signals and metrics: `repeat`, `gauge`, `shield-check`, `activity`, `layers`, `coins`,
    `clock`;
  - controls: `funnel`, `search`, `settings`, `external-link`, `download`, `square-terminal`.

  **No emoji anywhere in the UI.** SF Symbols are licensed for Apple platforms only, so they
  can't be used.
- **Type**: Inter Tight (headings, variable), JetBrains Mono (numbers, variable), Instrument
  Serif italic (annotations, regular only). All are OFL 1.1, subset to woff2 and vendored with
  `OFL.txt`.
- **No runtime network**: no CDN fonts or scripts (Principle VI).

#### OpenTelemetry export

A stdlib OTLP/HTTP **JSON** exporter (`urllib` + `json`).

- **Turning it on**: only with `LOOPBRAKE_EXPORT=otlp` (Principle VI). The endpoint and headers
  come from the standard `OTEL_EXPORTER_OTLP_*` variables. If the protocol variable is set to
  something other than `http/json`, it warns and points the user to a local Collector.
- **Spans**: following the GenAI conventions, which are still at *Development* status:
  - run span: `invoke_agent {agent}`, INTERNAL, with `gen_ai.operation.name`,
    `gen_ai.agent.name`, `gen_ai.conversation.id` (the session id),
    `gen_ai.usage.input_tokens` / `output_tokens`, and `loopbrake.*` (α, τ, n, method,
    status);
  - step span: `execute_tool {tool}`, INTERNAL, with `gen_ai.tool.name`,
    `gen_ai.tool.call.id`, `loopbrake.score` and `loopbrake.signal.*`;
  - kill: a `loopbrake.kill` event, and the run span status set to ERROR with
    `error.type=loopbrake.killed`;
  - `gen_ai.system` is not emitted (deprecated).
- **Correlation with Claude Code**: when `TRACEPARENT` is set, the run span uses it as its
  parent, so LoopBrake appears inside Claude Code's trace. `session.id` and the tool-call ids
  are copied from the hook payload.
- **Metrics**: delta counters (Datadog direct only accepts delta): `loopbrake.runs`,
  `loopbrake.kills`, `loopbrake.false_kills` (user-reported) and `loopbrake.tokens.spent`.
- **Backends**:

  | Path | Backends |
  |---|---|
  | JSON, direct | OTel Collector, Datadog (Agent and direct), Honeycomb, Grafana Cloud (low volume), Langfuse (traces only), Jaeger |
  | Through a Collector | Phoenix (protobuf only); New Relic (JSON unverified) |

- **Out of scope**: logs signal, gRPC, retries beyond honouring one `Retry-After`.

**Exit gate**:
- Every screen works on live and replayed logs.
- Lighthouse accessibility ≥ 95 with glass on and with glass off.
- No requests leave localhost.
- Spans are visible end to end in a Collector, Datadog, Grafana and Honeycomb.
- Content stays excluded unless opted in, checked by inspecting the payloads.

**Risks**:
- GenAI conventions change while still at Development. Mitigation: attribute names in one table
  in the code.
- Grafana advises JSON for low traffic only. Mitigation: document the Collector path.

**Reels**:
- The liquid glass dashboard catching a loop.
- "It shows up in your Datadog too."

**Size**: L.

**What changed while building** (details in `specs/005-observability/tasks.md`, "Outcome"):
- **Plain words everywhere**: tasks, tool calls, limit, "Stopped", "Mark as mistake"; never τ, α,
  score or kill on screen. The screens became Overview, Task, Project and Export.
- **The chart shows the rule v1 uses**: the tool-call count climbing toward the limit, not a score
  line. The project page shows the past task lengths the limit came from. "Exclude runs" became
  "Leave out of future limits" on each finished task, and "Recalibrate" became "Set the limit
  again". The overview shows stops marked as mistakes next to how many would be normal, not a
  budget. No live "tokens saved" (constitution).
- **Security**: the per-launch key in the address is swapped for an HttpOnly cookie on first load;
  changes also need the page's own `Origin`; a strict CSP blocks every outside load.
- **Spans**: no `loopbrake.score` or `loopbrake.signal.*` (v1 decides by count), and no token usage
  on spans (Claude Code's hooks don't report it). A project is sent as a short hash unless content
  is opted in, because Claude Code project names hold folder paths. A stopped task is sent at its
  stop, since Claude Code may never end it. Only tasks that *started* with export on are sent.
- **Counters**: `loopbrake.tasks`, `loopbrake.stops`, `loopbrake.mistaken_stops` and
  `loopbrake.tokens.spent`; delta by default, cumulative on request (Grafana).
- **The redesign** (constitution 2.5.0 and 2.6.0): written for people who don't code, with "actions"
  for tool calls, a light and a dark theme in the Visual Vortex colors (coral, rose and plum on
  near-black), no glass switch and no logo mark.
- **The exit gate's vendor check**: no vendor accounts (the builder's decision). Instead, stand-ins
  in the tests enforce each tool's published intake rules, and a real OpenTelemetry Collector and
  Jaeger ran end to end, with LoopBrake's task nested inside Claude Code's own trace.

### Phase 4b: Codex CLI plugin (next; the builder's decision, 2026-10-02)

- **Goal**: the same live stops for OpenAI's Codex CLI that the Claude Code plugin gives: a Codex
  plugin with hooks, the slash commands and the dashboard, calibrated on the user's own Codex history.
- **Known so far** (Codex docs, checked 2026-10-02): hooks run by default and plugins can ship them;
  `PostToolUse` gets `session_id`, `transcript_path`, `turn_id`, `tool_name`, `tool_use_id` and
  `tool_input`. Unlike Claude Code, `continue: false` there replaces the tool result and Codex carries
  on, so a stop likely means refusing every further tool call in `PreToolUse`. That must be proven
  first, in a probe, as Phase 3's hook probe did. Subagent calls fire the same hooks and must be told
  apart (they never count), and calibration needs a reader for Codex's session files.
- **Not possible**: ChatGPT itself. Its old plugins closed in 2024, and today's apps are tools ChatGPT
  calls, with no way to watch or stop its own work.

### Phase 5: Launch (`005-launch`)

- **Goal**: the public release and the video.
- **Deliverables**:
  - **Demo agent**, built on the package. Its type is chosen in the Phase 5 spec, against these
    criteria: relatable to non-engineers, cheap to run 30+ times for calibration, and gets stuck
    naturally on realistic tools (pagination, flaky errors, dead ends). It is never scripted to
    loop.
  - Calibrate it on its own successful runs, record runs until a real stuck run happens, and
    capture the dashboard and a Datadog/Grafana trace of it.
  - README:
    - the problem;
    - 60-second install for Claude Code and for Python;
    - the committed numbers;
    - the guarantee's scope;
    - the FailFast comparison, with caveats.
  - Publish the package. List the marketplace entry. Scrub the history and make the repo public
    (Principle VI checklist). Then the launch video.
- **Exit gate**: a clean-machine test, where a stranger follows the README to a first kill in
  under 5 minutes. Every number in the video traces back to `eval/results/`.
- **Risks**:
  - The demo agent rarely gets stuck. Mitigation: pick task and tool designs where real models
    do loop, and record enough runs. Staging stays forbidden.
- **Reel**: the launch video.
- **Size**: M.

### Progress judge experiment (`002-progress-judge`, status: done, verdict NO-GO on 2026-10-01)

Triggered by Phase 1's NO-GO. Jev (Typesafe's hosted decision model) judges each step's progress,
and it's tested with the same pre-registered gate, using **net** tokens saved. A GO opens Phase 2.
A NO-GO leads to training a dedicated monitor, or to shipping the guaranteed step budget. See
`specs/002-progress-judge/plan.md`.

### Conditional: System 1 model

Triggered only when Phase 1, or a later evaluation, shows the cheap signals have plateaued. It
goes before Launch and is an optional extra (Principle III). It is scoped then, not now.

## Order and parallel work

```text
P1 ──► P2 ──► P3 ──► P4 ──► P5
              │      ▲
              └──────┘  P4 UI work can start once P2 fixes the run log (use replayed logs)
       P2 ──► demo-agent prototype can start early; its stuck-run recording waits for P4
```

The critical path is the Phase 1 gate. Nothing after Phase 1 is built until it reads "go".

## Cross-cutting decisions

| Topic | Decision | Status |
|---|---|---|
| Git repository | `git init` before Phase 1 implementation, so the candidate pre-registration commit means something | default |
| License | MIT. Lucide's ISC notice and the fonts' OFL ship alongside (Phase 4). The τ-bench fixture's MIT notice is in `tests/fixtures/NOTICE.md`. | confirmed 2026-10-01 |
| PyPI and npm name `loopbrake` | Free as of 2026-10-01. Reserve it at the start of Phase 2 by publishing 0.0.1 from your account. | **needs your account** |
| Versioning | 0.x until launch; 1.0.0 at Phase 5 | default |
| CI | GitHub Actions running pytest on push, from Phase 2 | default |
| Emoji | None in the dashboard, CLI output, README or logs | user rule |

## Workflow from here

1. Phase 1: `/speckit-tasks` → `/speckit-implement` → gate verdict.
2. If "go": run `/speckit-specify` with the Phase 2 section above, then plan → tasks →
   implement. Repeat for each later phase.
3. After each phase, update this roadmap's status line and record any outcome changes.
