---

description: "Task list for Observability: the dashboard and company-tool export (LoopBrake v0.3.0)"
---

# Tasks: Observability (dashboard and company-tool export)

**Input**: `specs/005-observability/`: plan.md, spec.md, research.md (R1–R9), data-model.md,
contracts/ (dashboard-http.md, ui.md, otlp.md, cli.md), quickstart.md

**Tests**: included. The constitution asks for a runnable check on every non-trivial path. Each
story's tests come first and must fail before its code is written.

**Rules for every commit**:
- no Claude attribution lines;
- the repo-local identity (SahilSelokar <sahilselokar03@gmail.com>);
- no emoji;
- no private transcript content or local folder names in fixtures or docs (Principle VI).

**Words on screen**: plain language only: "task", "tool calls", "limit", "Stopped". Never "step",
"τ", "α", "score", "kill", or a run id (spec FR-007).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel: different files, and no unfinished dependencies.
- **[Story]**: US1–US4 from spec.md. Paths are relative to `LoopBrake/`.

---

## Phase 1: Setup

- [X] T001 Set up the branch and version:
  - create branch `005-observability` from `main` (currently the 0.2.1 release);
  - set `__version__ = "0.3.0"` in `src/loopbrake/__init__.py`, and update `tests/test_cli.py` if it
    pins a version;
  - set Phase 4 to "in progress" in `specs/roadmap.md`;
  - commit `specs/005-observability/` (spec, plan, research, data model, contracts, quickstart,
    checklist, and `collector/`) as the first commit on the branch.
- [X] T002 [P] Write the development-only script `scripts/vendor_assets.py`, then run it (research
  R6). It:
  - downloads the fonts at pinned commits from the official Google Fonts repository, checking each
    file's sha256: Inter Tight (variable `InterTight[wght].ttf`), JetBrains Mono (variable
    `JetBrainsMono[wght].ttf`), and Instrument Serif Italic (`InstrumentSerif-Italic.ttf`), each
    with its `OFL.txt`;
  - subsets them to Latin and Latin-1 punctuation with
    `uv run --with fonttools --with brotli python scripts/vendor_assets.py`, then writes
    `src/loopbrake/static/fonts/{inter-tight,jetbrains-mono,instrument-serif-italic}.woff2` and
    `src/loopbrake/static/fonts/OFL.txt` (the three licenses);
  - downloads these Lucide icons at a pinned version (`lucide-static`): `play`, `loader-circle`,
    `octagon-x`, `check`, `triangle-alert`, `repeat`, `gauge`, `shield-check`, `activity`,
    `layers`, `coins`, `clock`, `funnel`, `search`, `settings`, `external-link`, `download`,
    `square-terminal`, `sparkles`, `send`, `x`, `chevron-left`, `circle-alert`. It writes them as
    one `<symbol id="…">` sprite in `src/loopbrake/static/icons.svg`, plus
    `src/loopbrake/static/LICENSE-lucide.txt`;
  - writes `src/loopbrake/static/ASSETS.md` with each source URL, version and sha256.

  Commit the outputs. Check `uv build`: the wheel must hold `loopbrake/static/…`, and the static
  files must total under 400 KB.

---

## Phase 2: Foundational (record fields and shared helpers; needed by every story)

- [ ] T003 [P] Add tests for the new optional record fields (data-model.md, "Changes to existing
  records"):
  - **`tests/test_records.py`**: `ts` now has milliseconds
    (`^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}\+00:00$`), and the old seconds format still reads.
  - **`tests/test_brake.py`**:
    - `step(..., duration_ms=68)` records `"duration_ms": 68`, and leaves it out when it's None;
    - `start(project, traceparent="00-…-…-01")` records `traceparent` on `run_start`, and drops an
      invalid one (not matching `^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$`, or all zeros);
    - `from_events` keeps working.
  - **`tests/test_calibrate.py`**: new records carry `lengths`, the sorted step counts with `null`
    for a mistaken stop counted as unbounded; it holds no text.
  - **`tests/test_claude_code.py`**:
    - a `tool` hook input with `"duration_ms": 64` records it;
    - with `TRACEPARENT` set in the environment, the `prompt` hook records it on `run_start`;
    - without it, there's no field.
- [ ] T004 Make T003 pass:
  - **`src/loopbrake/records.py`**: `_now()` uses `timespec="milliseconds"`.
  - **`src/loopbrake/brake.py`**:
    - `Brake.__init__(…, traceparent=None)` records it on `run_start` when it's valid;
    - `step(…, duration_ms=None)`;
    - `start(…, traceparent=None)` passes it through.
  - **`src/loopbrake/calibration.py`**: `rec["lengths"] = sorted(...)`, with `math.inf` written as
    `null`.
  - **`src/loopbrake/claude_code.py`**: passes `data.get("duration_ms")` (an int ≥ 0, or nothing) to
    `step`, and `os.environ.get("TRACEPARENT")` to `start`.
- [ ] T005 Refactor the plain stop message into a function of plain values, so the dashboard and
  export can use it without a `Brake`. In `src/loopbrake/claude_code.py`:
  - add `plain_stop(step, limit, n, alpha, reason, next_step)`, where `next_step` is the closing
    sentence;
  - `stop_message(b)` calls it with " If it wasn't stuck, run /loopbrake:mistake, then tell Claude
    to continue.";
  - add `reason_codes(reason) -> list`: `past_limit`, plus `same_error`, `repeating` or
    `nothing_new` (the same order as the symptoms).

  Add tests to `tests/test_claude_code.py`. The existing stop-message tests must still pass
  unchanged.

---

## Phase 3: User Story 1: see what LoopBrake is doing (Priority: P1). MVP.

**Goal**: `loopbrake dashboard` shows running tasks updating live, recent stops, totals, each task's
tool calls against its limit with the plain reason, and each project's limit. The page is local,
behind a key.

**Independent test**: quickstart scenarios 2, 3 and 5.

- [ ] T006 [P] [US1] Write `tests/test_dashboard.py`, part 1 (the index), against a temporary
  `LOOPBRAKE_HOME`, with run records written through `records.RunWriter` and `Brake`:
  - **Summaries** (data-model.md, "Task summary"):
    - status `running`, `finished`, `stopped` or `interrupted`;
    - "A run with a `stop` event and no `run_end` is shown as `stopped`";
    - "An open run whose session hasn't been written to for 24 hours is shown as
      `running (no activity)`";
    - `calls`, `limit`, `stop_at`, `marks`, `tokens`, and `agent` (`claude-code` for `cc-`
      projects).
  - **Incremental reads**: append lines after `refresh()`; the next `refresh()` reads only the new
    bytes (check with a counter) and updates `version`.
  - **Damaged lines**: they're skipped and counted in `skipped_lines`.
  - **The task page**: tool calls in pages of 200, with `repeats` true exactly when
    `signals.method("fuzzy")` scores 1.0 against one of the previous 10, `failed`, and
    `duration_ms`.
  - **The overview**: per-day `stops` and `tokens` for the last 30 days, `recent_stops` capped at 20,
    and `running`.
  - **Projects**: from calibration records and run starts, with `lengths`, `needed` when watch-only,
    and `history` found for a `cc-` project by scanning a temporary `CLAUDE_CONFIG_DIR/projects`.
  - **Claude Code tokens** (FR-017, research R5): a `cc-` task whose first `call_id` appears in a
    synthetic transcript (with `usage` on its assistant messages) gets that transcript turn's token
    total. A task with no match gets null. The per-day tokens chart sums them. The transcript is
    read once and cached by size and modification time.
  - **Speed**: 220,000 synthetic lines load in under 3 s, and `overview()` then answers in under
    100 ms.
- [ ] T007 [US1] Implement the index in `src/loopbrake/dashboard.py`: class `Index(home, days=None)`
  with `refresh()`, `overview()`, `tasks(project, status, before, limit)`, `task(session, run, page)`,
  `projects()` and `project(name)`. Rules:
  - **Reading**: per-file byte offsets. Step lines are counted by a text check, and only parsed when
    a task is opened (research R3).
  - **Words**: plain reason text from `claude_code.plain_stop(...)`, with the closing sentence
    "Use "Mark as mistake" if it wasn't stuck.". Status labels are Running, Finished, Stopped and
    Interrupted.
  - **Shortcut note**: `# ponytail: whole history read at start; keep a summary cache on disk if
    starts get slow`.
  - **Claude Code tokens**: through `traces.claude_code_turns(f, call_ids=…)` on the project's
    history folder (the single loader, Principle V), for session files changed in the last 30 days,
    cached per file by `(size, mtime)`. Only numbers are kept.

  Makes T006 pass.
- [ ] T008 [P] [US1] Write `tests/test_dashboard.py`, part 2 (server and access, contracts/
  dashboard-http.md), starting the real server on `127.0.0.1:0` in a thread:
  - **The key exchange**: `GET /?k=KEY` gives 303 to `/` and sets the cookie `lb=KEY; HttpOnly;
    SameSite=Strict; Path=/`; a wrong key gives 401.
  - **Without the cookie**: `/api/overview` gives 401 with the plain hint.
  - **`Host: evil.example`** gives 403. A `POST` with `Origin: http://evil.example` gives 403.
  - **Headers**: the CSP is exactly `default-src 'self'; img-src 'self' data:; frame-ancestors
    'none'`, plus `nosniff`, `no-referrer`, and `Cache-Control: no-store` on the API.
  - **Bind address**: the server's socket is bound to `127.0.0.1`.
  - **Read endpoints**: `/api/changes`, `/api/overview`, `/api/tasks`, `/api/task/<s>/<r>`,
    `/api/projects` and `/api/project/<name>` return the shapes in the contract.
  - **Path traversal**: `/static/../records.py` gives 404, and so do unknown paths.
  - **Live update (SC-001)**: after a hook writes a step, `/api/changes` reports a new version
    within 2 s.
- [ ] T009 [US1] Implement the server in `src/loopbrake/dashboard.py`: `serve(port=0,
  open_browser=True, days=None, home=None)`.
  - `http.server.ThreadingHTTPServer(("127.0.0.1", port))`, with a request handler holding the
    access rules from research R1;
  - static files through `importlib.resources.files("loopbrake") / "static"`, served only from that
    folder;
  - the key from `secrets.token_urlsafe(32)`;
  - the browser opened with `webbrowser.open`.

  Makes T008 pass.
- [ ] T010 [US1] Add `loopbrake dashboard [--port N] [--no-open] [--days D]` to
  `src/loopbrake/cli.py`, per contracts/cli.md:
  - it prints the two lines and exits 0 on Ctrl+C;
  - a taken port exits 2 with one line.

  Add `loopbrake replay FILE … --record`: it writes records for each replayed run under project
  `replay-<file stem>`, through `Brake` with `record=True`. Without `--record`, replay still writes
  nothing. Add both to `tests/test_cli.py`.
- [ ] T011 [P] [US1] Write the page `src/loopbrake/static/index.html` and
  `src/loopbrake/static/app.js` (plain ES2020, no build, no libraries), per contracts/ui.md:
  - **Routing**: hash routes `#/`, `#/task/<session>/<run>`, `#/project/<name>` and `#/export`, plus
    a nav (top bar on wide screens, bottom bar under 640 px).
  - **Updates**: polls `/api/changes` every 1 s, and refetches only the current view when the
    version changes.
  - **Overview**:
    - "Running now", with "<calls> of <limit> tool calls" and a progress bar;
    - "Recent stops";
    - totals;
    - two inline-SVG bar charts per day (stops, and tokens when any);
    - "Stops you marked as mistakes: M (up to about X would be normal by now)";
    - a project filter;
    - a one-sentence getting-started note when empty.
  - **Task**:
    - a header with the status chip;
    - an inline-SVG chart: a line rising one per tool call, a dashed horizontal limit line, and the
      stop marker with the `octagon-x` icon and the word "Stopped";
    - the plain reason card;
    - rows: number, tool, action text, "failed", "repeats an earlier call", and duration;
    - "Load more" for pages after the first.
  - **Project**: the limit and its promise; past task lengths as dots, with the limit line (when
    `lengths` exists); when it was set; watch-only state and needed count; counts.
  - **Export**: a placeholder until US3.
  - **Icons**: only through `<svg><use href="/static/icons.svg#name"/></svg>`.
- [ ] T012 [P] [US1] Write the base styles in `src/loopbrake/static/app.css`, from contracts/ui.md
  and the constitution:
  - **Tokens**: CSS custom properties for night `#08110D`, lime `#CFFF3E`, green `#0F3D2E`, red
    `#E5341F`, paper `#ECEBE4` and ink `#0D0E0B`.
  - **Fonts**: `@font-face` for the three vendored fonts, as local URLs only.
  - **Panels**: near-opaque night for tables, charts and lists.
  - **Glass**: on the top bar, side nav, toolbars, dialogs and toasts only. An opaque base first,
    with blur added under `@supports (backdrop-filter: blur(1px))`.
  - **Red**: only as a fill.
  - **Focus**: `:focus-visible` gets a 2 px lime outline with a night halo.
  - **Phone width**: below 640 px the nav becomes a bottom bar, with no sideways scrolling.

  The refraction, sheen and accessibility switches come in US4.
- [ ] T013 [P] [US1] Write `tests/test_static.py`:
  - **No emoji**: none in any file under `src/loopbrake/static/` (the emoji regex used in
    `tests/test_cli.py`).
  - **No external URLs**: no `http://` or `https://` outside `OFL.txt`, `LICENSE-lucide.txt` and
    `ASSETS.md`.
  - **Icons exist**: every `#name` used in `index.html` and `app.js` exists as a `<symbol id>` in
    `icons.svg`.
  - **Local fonts**: every `url(` in `app.css` points under `/static/`.
  - **Red is a fill only**: no `color: var(--red)` in `app.css`.
  - **Contrast**: the text and background token pairs listed in a table in the test meet WCAG AA
    (4.5:1 for body text, 3:1 for large text), computed from the hex values.
  - **Size**: the static folder totals under 400 KB.
  - **Words**: `app.js` and the dashboard's API strings contain none of "τ", "α", " kill", "score",
    or "step " as on-screen words. The test checks the user-facing string literals listed in
    `app.js`'s `TEXT` object.
- [ ] T014 [US1] Manual: run quickstart scenarios 2 (replayed evaluation records), 3 (a live Claude
  Code task with a low limit) and 5 (the security checks). Note the results under "Outcome".
  **Checkpoint: MVP.**

---

## Phase 4: User Story 2: act on what you see (Priority: P2)

**Goal**: mark a mistake, leave a task out, and set the limit again from the dashboard, with exactly
the commands' effects.

**Independent test**: quickstart scenario 4.

- [ ] T015 [P] [US2] Add tests to `tests/test_dashboard.py`, part 3 (actions, contracts/
  dashboard-http.md, "Change endpoints"):
  - **`POST /api/mistake`** on a stopped task writes `feedback mistaken_stop` (the same as
    `records.add_feedback`). A second time gives 409 "That one is already marked."; an unknown task
    gives 404; a task that wasn't stopped gives 400.
  - **`/api/exclude`** works the same way.
  - **`/api/recalibrate`**:
    - on a `cc-` project with a history folder (a synthetic transcript in a temporary
      `CLAUDE_CONFIG_DIR`), it returns exactly `claude_code.calibrate_message(rec)`, and the
      calibration file changes;
    - on a project without a findable history, it gives 400 with the command to run.
  - **Bad bodies**: a task id not matching `[A-Za-z0-9._-]{1,128}/[A-Za-z0-9._-]{1,128}` gives 400.
  - **Origin**: a `POST` without the right `Origin` gives 403.
- [ ] T016 [US2] Implement the POST handlers in `src/loopbrake/dashboard.py`, reusing
  `records.add_feedback`, `calibration.calibrate` and `claude_code.calibrate_message`. Makes T015
  pass.
- [ ] T017 [P] [US2] Add the action buttons and confirmation dialogs (a glass dialog, with focus
  trapped and Esc to cancel) to `src/loopbrake/static/app.js` and `index.html`:
  - "Mark as mistake" on stopped tasks; "Leave out of future limits" on finished tasks; "Set the
    limit again" on `cc-` projects with history;
  - each confirmation is one plain sentence, from contracts/ui.md;
  - results show as a toast; errors show the server's plain message.
- [ ] T018 [US2] Manual: run quickstart scenario 4. Note the result under "Outcome".

---

## Phase 5: User Story 3: see it in the company's tools (Priority: P2)

**Goal**: with `LOOPBRAKE_EXPORT=otlp`, each finished task is sent in the background as OTLP/HTTP
JSON: one trace per task, a span per tool call, the stop event, and four counters. Metadata only
unless content is opted in. The agent never waits.

**Independent test**: quickstart scenarios 6 and 7.

- [ ] T019 [P] [US3] Write `tests/test_otlp.py`, per contracts/otlp.md and research R8, with a tiny
  in-process receiver recording every request:
  - **Settings**:
    - off unless `LOOPBRAKE_EXPORT=otlp`; with only `OTEL_EXPORTER_OTLP_ENDPOINT` set, nothing is
      sent;
    - the base endpoint plus `/v1/traces` and `/v1/metrics`, while per-signal endpoints are used as
      given, and `_METRICS_ENDPOINT=none` skips metrics;
    - headers parsed as `k=v,k2=v2` and percent-decoded;
    - a protocol other than `http/json` records the one-line warning.
  - **Mapping**:
    - trace and span ids are lowercase hex, 32 and 16 characters, never all zeros, and stable across
      two sends;
    - with `traceparent` on `run_start`, the task span uses its trace id and parent;
    - times are decimal-string nanoseconds;
    - a step span starts `duration_ms` before its `ts`;
    - a stopped task has status code 2, `error.type=loopbrake.stopped`, and the `loopbrake.stop`
      event with `reason_code`;
    - `invoke_agent claude-code` and `execute_tool <tool>` names;
    - the `gen_ai.*` attributes as listed;
    - no `gen_ai.system` and no `gen_ai.provider.name`.
  - **Content**:
    - without `LOOPBRAKE_EXPORT_CONTENT=1`, no request body contains any stored action text,
      reason text, or readable project name (search the bytes for each fixture action and for the
      project name, which holds a made-up folder path); only `loopbrake.project_id`
      (`sha256(project)[:12]`) is sent (FR-012);
    - with it, `loopbrake.project`, `loopbrake.action` and `loopbrake.reason` appear.
  - **Finished tasks** (research R7):
    - a stopped task is sent at its `stop`, even with no `run_end` yet;
    - tool calls recorded after the stop aren't sent;
    - a task whose `run_start` lies before the starting point saved when export was first turned on
      is never sent, not even after it ends.
  - **Metrics**:
    - four Sum metrics, `isMonotonic`, `asInt` as strings;
    - delta (1) by default, with the window from the last send;
    - cumulative (2) when `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=cumulative`, counting
      from `state.started`;
    - `lowmemory` counts as delta.
  - **State**:
    - the first run with no state records each file's end as its starting point;
    - offsets move forward only after success;
    - two exporters at once don't double-send (the lock).
  - **Responses**:
    - `{"partialSuccess":{}}` counts as ok;
    - `rejectedSpans>0` moves forward and records the message;
    - 429 with `Retry-After: 1` retries once, then gives up;
    - 400 is never retried;
    - a refused connection is recorded;
    - no recorded message contains the header values.
  - **Background start**: `spawn_pending()` calls `subprocess.Popen` with `start_new_session=True`
    and stdio set to `DEVNULL`, and only when export is on (monkeypatched).
  - **Hook timing (SC-006)**: with export on and the receiver stopped, 50 `hook("tool")` calls plus
    a `stop` stay within 10 ms of work at p95.
- [ ] T020 [P] [US3] Write `tests/mimic_backends.py` and `tests/test_export_backends.py` (research
  R9):
  - one stand-in per tool, as a stdlib `http.server` on `127.0.0.1:0`:
    - it validates the generic OTLP JSON rules: hex ids, string 64-bit integers, integer enums,
      lowerCamelCase keys, and `Content-Type: application/json`;
    - it applies that tool's rules from the R9 table: Datadog (`dd-api-key`, delta only), Grafana
      (Basic auth, cumulative only), Honeycomb (`x-honeycomb-team`), Langfuse
      (`/api/public/otel/v1/traces`, Basic, traces only), Jaeger (traces only), Phoenix (415 for
      JSON) and Collector (anything valid);
  - **Right settings**: the README's settings for each tool (contracts/otlp.md, "Settings per tool")
    are accepted;
  - **Wrong settings**: cumulative to Datadog, delta to Grafana, metrics to Langfuse or Jaeger, or
    JSON to Phoenix are rejected, recorded in `export/state.json` `last`, and not retried.
- [ ] T021 [US3] Implement `src/loopbrake/otlp.py`:
  - `settings()` from the environment;
  - `State` (the `export/state.json` file, under `export/lock` with `fcntl`, replaced atomically);
  - `finished_tasks(home, state)`: a task is final at its `run_end` or its `stop`, whichever comes
    first, and only tasks whose `run_start` lies after the starting point count;
  - `build_traces(tasks, content)` and `build_metrics(counts, temporality, window)`;
  - `send(url, body, headers)`: `urllib.request`, 10 s timeout, one `Retry-After` retry capped at
    10 s;
  - `export_pending(home, quiet)`, `test_connection(home)` and `spawn_pending()`.
  - Attribute names live in one table at the top of the file (the roadmap's mitigation against
    convention changes).

  Makes T019 and T020 pass.
- [ ] T022 [US3] Wire export in:
  - **`src/loopbrake/brake.py`**: `Brake.end()` calls `otlp.spawn_pending()` when export is on.
  - **`src/loopbrake/claude_code.py`**: it calls `spawn_pending()` after closing a task in `prompt`
    and `stop`, and after a stop decision, since a stopped task may never get `Stop`.
  - **`src/loopbrake/cli.py`**: `loopbrake export --pending | --test [--quiet]`, per contracts/
    cli.md.

  Add CLI tests to `tests/test_cli.py`.
- [ ] T023 [US3] Wire the dashboard's export screen:
  - **`src/loopbrake/dashboard.py`**: `GET /api/export` (on or off, the endpoint host only, content
    yes or no, `last`); `POST /api/export/send` (runs `spawn_pending`; 409 when off);
    `POST /api/export/test` (409 when off).
  - **`src/loopbrake/static/app.js`**: the Export screen per contracts/ui.md, including copyable
    setup lines for each tool from contracts/otlp.md.

  Add tests to `tests/test_dashboard.py`.
- [ ] T024 [US3] Manual: run quickstart scenarios 6 and 7 with the real Collector and Jaeger
  (`docker compose up -d` in `specs/005-observability/collector/`). Run a Claude Code task that
  gets stopped, with export on.
  - **Confirm**:
    - the trace in Jaeger is nested under Claude Code's own trace when Claude Code's tracing is on
      (FR-014);
    - the counters in the Collector's debug output;
    - no action text without content opt-in (SC-005).
  - **Then**: stop the Collector, run 50 tool calls, and confirm the per-call time stays under budget
    and the Export screen shows the failure (SC-006).

  Note the results.

---

## Phase 6: User Story 4: readable, accessible, on-brand (Priority: P3)

**Goal**: the liquid glass look with its accessibility switches, at an accessibility score of at
least 95 with glass on and off, and phone-width ready.

**Independent test**: quickstart scenario 8.

- [ ] T025 [US4] Finish the glass system in `src/loopbrake/static/app.css` and `app.js` (research
  R6, constitution "Glass behavior"):
  - **Layers**: one fixed background layer of lime and deep-green glows at 35% alpha or less.
  - **Glass controls**: a tint of night at about 0.6; blur ≤ 20 px with 170% saturation; a 1 px rim
    with an inset top highlight; an outer shadow; at most 3–4 glass layers per screen.
  - **Refraction**: an SVG `feDisplacementMap` filter, applied only when `CSS.supports` and the
    browser is Chromium.
  - **The sheen**: follows the pointer, only under `prefers-reduced-motion: no-preference`.
  - **"Glass off"**:
    - a switch in the top bar that sets `data-glass="off"` on `<html>`, saved in `localStorage`
      inside `try/catch`, and also set by `?glass=off`;
    - `prefers-reduced-transparency: reduce` and `prefers-contrast: more` force it (opaque panels and
      2 px borders);
    - `forced-colors: active` uses system colors.
  - **Stopped state**: always the red fill, plus `octagon-x`, plus the word "Stopped".
- [ ] T026 [US4] Manual: quickstart scenario 8.
  - **Lighthouse**: run accessibility on every screen, glass on and `?glass=off`; every score must
    be ≥ 95.
  - **macOS settings**: check "Reduce motion", "Reduce transparency" and "Increase contrast".
  - **Phone width**: check a 390×844 window for no sideways scrolling.

  Fix what fails, then note the scores.

---

## Phase 7: Polish, docs and release

- [ ] T027 [P] Update `README.md`:
  - **A "Dashboard" section**: `loopbrake dashboard`, what each screen shows, and the security model
    in one paragraph.
  - **A "Send to your observability tools" section**:
    - the `LOOPBRAKE_EXPORT=otlp` setting, and the separate content opt-in;
    - the per-tool settings table from contracts/otlp.md;
    - the protobuf-only note (use a Collector);
    - the honest limit from research R9: "checked against each tool's published intake rules and a
      real OpenTelemetry Collector and Jaeger, not against live accounts".
  - **Public-claims rule**: no numbers except configuration. Absolute links only, no Mermaid; check
    with `readme_renderer`.
- [ ] T028 [P] Mark Phase 4 done in `specs/roadmap.md` (at T033), and record any changes from the
  roadmap's Phase 4 text (the step-budget chart, plain words, account-free checks).
- [ ] T029 Run the full suite:
  - `uv run python -m pytest`, and `uv run --with claude-agent-sdk python -m pytest
    tests/test_agent_sdk.py`;
  - push the branch, and confirm GitHub's tests pass on 3.11–3.13.
- [ ] T030 Manual: quickstart scenario 9 (nothing leaves the computer, SC-003). Note the result.
- [ ] T031 Raise the Claude Code plugin to 0.3.0: set `plugin/.claude-plugin/plugin.json` `version`
  and `plugin/bin/loopbrake` `V=` to `0.3.0`, because its hooks now record `duration_ms` and
  `traceparent`, and start export. `tests/test_plugin_files.py` checks they agree with
  `__version__`. Re-run Phase 3's release checks:
  - `claude plugin validate` for both;
  - launcher speed against a local 0.3.0 wheel;
  - `loopbrake agreement --claude-code` on real use since 0.2.1, which must show live higher 0
    (constitution 2.4.0).
- [ ] T032 Release, with the builder's go-ahead (a release is public):
  1. tag the branch head `v0.3.0` and push only the tag;
  2. confirm PyPI serves 0.3.0;
  3. merge into `main` and push;
  4. confirm `main`'s tests pass;
  5. update the builder's installed plugin (`claude plugin update loopbrake@loopbrake`, or reinstall).
- [ ] T033 Wrap up:
  - roadmap Phase 4 done, and README status;
  - stop the local Collector (`docker compose down`);
  - note the outcomes here.
- [ ] T034 After release (SC-008, not a release gate): quickstart scenario 10. Three people new to
  LoopBrake each try to find why the last task stopped, within 30 seconds of opening the dashboard.
  Note their times here. If one of them can't, file the confusing wording as a fix for the next
  release.

---

## Dependencies and order

**Phases**:
- **Setup**: T001–T002.
- **Foundational**: T003–T005. T004 needs T003, and T005 is independent.
- **US1**: T006–T014, the MVP. It needs T004 and T005. T007 needs T006, T009 needs T007 and T008,
  and T010 needs T009. T011–T013 can be written alongside, and need the static assets from T002.
- **US2**: T015–T018. It needs T009.
- **US3**: T019–T024. It needs T004 (record fields). T021 needs T019 and T020, T022 needs T021, and
  T023 needs T021 and T009.
- **US4**: T025–T026. It needs T011 and T012.
- **Polish**: T027–T033, and T034 after the release.

**Gates**:
- T031 (the agreement check) and T029 (CI) block T032.
- T032 needs the builder's go-ahead.

**Same file, in order**:
- `src/loopbrake/dashboard.py`: T007 → T009 → T016 → T023.
- `src/loopbrake/static/app.js`: T011 → T017 → T023 → T025.
- `src/loopbrake/static/app.css`: T012 → T025.
- `src/loopbrake/cli.py`: T010 → T022.
- `src/loopbrake/claude_code.py`: T004 → T005 → T022.
- `tests/test_dashboard.py`: T006 → T008 → T015 → T023.

**Can run in parallel**:
- T002 next to T003–T005;
- T011, T012 and T013 next to T006–T010;
- T019 and T020 next to each other;
- US2 and US3 after US1's server (T009);
- T027 and T028 any time after their features exist.

## Parallel examples

```text
Foundational: T003 (tests) | T005 (plain_stop) | T002 (assets)
US1:          T006 → T007, T008 → T009 → T010, alongside T011 (page) | T012 (styles) | T013 (static checks)
US3:          T019 (otlp tests) | T020 (stand-ins) → T021 → T022, T023
```

## Implementation strategy

1. **MVP**: T001–T014. A working local dashboard on live and replayed records, behind its key.
2. **Then**: US2 (actions) and US3 (export), which can go in parallel once the server exists.
3. **Then**: US4 (the full glass system and the accessibility audit).
4. **Last**: docs, the plugin bump, the agreement check, and the release on the builder's go-ahead.

**Total**: 34 tasks. T014, T018, T024, T026, T030, T031 and T034 are run by hand. T032 also needs
the go-ahead, and T034 comes after the release.

## Outcome

(Filled in during `/speckit-implement`.)
