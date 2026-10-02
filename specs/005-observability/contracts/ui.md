# Contract: dashboard screens, words and look

Redesigned on 2026-10-02 (User Story 5, constitution 2.5.0): for people who don't code.

## Screens (one page, address-hash routing; research R5)

Navigation: Home, Tasks, Projects, Settings. A side bar on wide screens, a bottom bar on phones.

| Screen | Hash | Shows | Actions |
|---|---|---|---|
| Home | `#/` | a greeting, and one sentence on how things are going (a stop today, all quiet, or only watching); a card per task working now ("23 of 59 actions", a bar that warns near the limit); three tiles with small trend lines (tasks this week, stopped, tokens or actions); recent stops as cards (project, when, "Stopped after N actions", the symptom in a few words); projects with their limit and normal task size; stops per day (30 days); a getting-started guide when there are no records | See why; It wasn't stuck |
| Tasks | `#/tasks` | every task, newest first, in pages: project, "Stopped after N actions", status, when, progress | filter by status and project; search by project |
| Task | `#/task/<session>/<run>` | the story ("Stopped after 60 actions in 10 minutes"); why, as a picture: the project's past tasks as dots, the limit line, this task marked; "What it kept doing": repeated actions grouped with counts; actions over time against the limit, each point explained on hover or tap; every action named by what it did, with time, duration and Failed/Repeated tags, expandable to its full text | It wasn't stuck (stopped tasks); Leave out of future limits (finished tasks); filter actions: All, Failed, Repeated |
| Project | `#/project/<name>` | the real folder name; the limit and its promise; the past tasks as dots (hover for each); how and when it was set; mistakes marked against how many are expected; its recent tasks | Set the limit again (Claude Code projects with history) |
| Settings | `#/settings` (`#/export` lands here) | Appearance: system, light or dark; Send to your tools: on or off, where (host only), content or not, last result, setup lines per tool; How LoopBrake works, in three steps; what the words mean | Send now; Test connection; Copy |

**Updates**: every screen polls `/api/changes` once a second, and refetches only what changed
(SC-001). When a new stop appears, a notice links to it (FR-022).

## Words (spec FR-007; constitution 2.5.0, "Plain words")

- **Ideas**: task, action (one tool call), limit, stopped, mistake. Each has a "?" with one line.
- **Status labels**: Working, No recent activity (an open task with no records for 24 hours),
  Finished, Stopped, Interrupted.
- **Actions by what they did**: Ran a command, Read a file, Edited a file, Wrote a file, Searched
  the code, Looked for files, Opened a web page, Searched the web, Asked a helper, Updated its to-do
  list; other tools: "Used <tool>".
- **Buttons**: "It wasn't stuck", "Leave out of future limits", "Set the limit again", "Send now",
  "Test connection".
- **Never on screen**: "step", "tool call" (except where "?" explains an action), "τ", "α",
  "score", "kill", or run and session ids. Ids appear only in the page address.
- **Confirmations**: every change asks first, with one sentence saying what it does.

## Look (constitution, visual identity; research R6)

| Rule | Check |
|---|---|
| **Colors**: night `#08110D`, lime `#CFFF3E`, green `#0F3D2E`, red `#E5341F`, paper `#ECEBE4`, ink `#0D0E0B`; each theme token is one `light-dark()` pair | a test reads both themes and checks every text/background pair for WCAG AA (4.5:1) |
| **Themes**: light and dark follow the system; Settings stores system, light or dark | manual |
| **Lime** on light backgrounds is a fill only, with ink text | the contrast test |
| **Glass** only on the side bar, bottom bar, dialogs, notices and pop-ups; content on near-opaque panels | review against this table |
| **Glass turns itself off** under reduced transparency or more contrast; forced colors use system colors; no manual switch | emulated checks |
| **Red** is a fill only, never text; a stop always shows the `octagon-x` icon plus the word "Stopped" | a test finds no `color: var(--red)` in the CSS |
| **Icons**: Lucide only, from the vendored sprite; stroke `currentColor`, width 1.75 | a test checks every icon used exists in the sprite |
| **No emoji anywhere** | a test scans the static files and API strings |
| **Fonts**: Inter Tight for headings, JetBrains Mono for numbers, Instrument Serif italic for notes; vendored woff2 with `OFL.txt` | a test checks every `url(` in the CSS is local |
| **Motion**: the sheen and transitions only under `prefers-reduced-motion: no-preference` | emulated check |
| **Focus**: `:focus-visible` shows a 2px outline with a halo; every action reachable by keyboard | Lighthouse plus a tab-through |
| **Phone width (9:16)**: no sideways scrolling; navigation becomes a bottom bar | 390×844 check |
| **Nothing from the internet**: no CDN; the CSP blocks it anyway | a test finds no `http://` or `https://` in the static files, except license text and the copyable setup lines |
