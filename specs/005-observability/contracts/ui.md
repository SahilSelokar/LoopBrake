# Contract: dashboard screens, words and look

## Screens (one page, address-hash routing; research R5)

| Screen | Hash | Shows | Actions |
|---|---|---|---|
| Overview | `#/` | tasks running now (each with "<calls> of <limit> tool calls" and a progress bar); recent stops; totals; per-day stops and tokens (last 30 days); "Stops you marked as mistakes: M (up to about X would be normal by now)"; a one-sentence getting-started note when there are no records | filter by project |
| Task | `#/task/<session>/<run>` | header (project, status chip, when); the chart of tool calls rising against the limit line, with the stop marker; the plain reason card; tool-call rows (number, tool icon, action text, "failed", "repeats an earlier call", duration) | Mark as mistake (stopped tasks); Leave out of future limits (finished tasks) |
| Project | `#/project/<name>` | the limit and its promise ("fewer than 1 in 20 good tasks should go past it"); the past task lengths as dots, with the limit line; when it was set; watch-only state and needed count; counts | Set the limit again (for `cc-` projects with history) |
| Export | `#/export` | on or off; where it sends (host only); content included or not; last send result; how to turn it on (copyable lines) | Send now; Test connection |

**Updates**: every screen polls `/api/changes` once a second, and refetches only what changed
(SC-001).

## Words (spec FR-007)

- **Status labels**: Running, Running (no activity) (an open task with no new records for 24 hours), Finished, Stopped, Interrupted.
- **Buttons**: "Mark as mistake", "Leave out of future limits", "Set the limit again", "Send now",
  "Test connection".
- **Units**: "tool calls", "tasks", "limit". Never "step", "τ", "α", "score", "kill", or a run id
  on screen. Ids appear only in the page address.
- **Confirmations**: every change asks first, with one sentence saying what it does, e.g. "LoopBrake
  will count this task as a long good one next time you set the limit."

## Look (constitution, visual identity; research R6)

| Rule | Check |
|---|---|
| **Colors**: night `#08110D`, lime `#CFFF3E`, green `#0F3D2E`, red `#E5341F`, paper `#ECEBE4`, ink `#0D0E0B`, defined once as CSS custom properties | a test reads the CSS and checks text/background pairs for WCAG AA contrast (4.5:1, or 3:1 for large text) |
| **Glass** only on the top bar, side navigation, toolbars, dialogs and toasts; tables, charts and lists on near-opaque night panels | review against this table |
| **Red** is a fill only, never text; a stop always shows the `octagon-x` icon plus the word "Stopped" | a test finds no `color: var(--red)` in the CSS |
| **Icons**: Lucide only, from the vendored sprite; stroke `currentColor`, width 1.75 | a test checks every `<use href="#…">` exists in the sprite |
| **No emoji anywhere** | a test scans the static files and API strings |
| **Fonts**: Inter Tight for headings, JetBrains Mono for numbers, Instrument Serif italic for notes; vendored woff2 with `OFL.txt` | a test checks every `url(` in the CSS is local |
| **"Glass off"** switch in the top bar, remembered; reduced transparency and more contrast force it; forced colors respected | manual checks in quickstart |
| **Motion**: the sheen and transitions only under `prefers-reduced-motion: no-preference` | manual |
| **Focus**: `:focus-visible` shows a 2px lime outline with a night halo; every action reachable by keyboard | the Lighthouse audit plus a manual tab-through |
| **Phone width (9:16)**: no sideways scrolling; navigation collapses to a bottom bar | quickstart at 390×844 |
| **Nothing from the internet**: no CDN; the CSP blocks it anyway | a test finds no `http://` or `https://` in the static files, except license text |
