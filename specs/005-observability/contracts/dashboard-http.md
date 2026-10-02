# Contract: the dashboard's HTTP interface

Served by `loopbrake dashboard` on `127.0.0.1` only (research R1).

## Access

| Rule | Behavior |
|---|---|
| `Host` isn't `127.0.0.1:<port>` or `localhost:<port>` | 403, empty body |
| `GET /?k=<key>` with the right key | sets cookie `lb=<key>; HttpOnly; SameSite=Strict; Path=/` and returns 303 to `/` |
| any other request without the right cookie | 401 with a one-line plain-text hint: "Open the address loopbrake dashboard printed." |
| `POST` whose `Origin` isn't the dashboard's own address | 403 |
| every response | `Content-Security-Policy: default-src 'self'; img-src 'self' data:; frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` |
| API responses | `Content-Type: application/json`, `Cache-Control: no-store` |

## Read endpoints (GET)

| Path | Returns |
|---|---|
| `/` and `/static/*` | the page, styles, script, fonts and icon sprite, from the package |
| `/api/changes?since=N` | `{"version": M, "last_stop": "<session>/<run>" or null}`. M is the bytes of records read so far; the page refetches only when M changed. When `last_stop` changes, the page shows a "just stopped" notice (FR-022). |
| `/api/overview` | totals (`seen`, `stopped`, `mistaken`, `normal_mistakes`), `running` tasks, `recent_stops` (up to 20), per-day `stops` and `tokens` for the last 30 days, `skipped_lines` |
| `/api/tasks?project=&status=&before=&limit=50` | task summaries, newest first, paged by `before` (an end-time cursor) |
| `/api/task/<session>/<run>?page=0` | the task summary, its plain-language reason, and tool calls 200 per page, with `repeats` and `failed` flags |
| `/api/projects` | one summary per project |
| `/api/project/<name>` | the project's limit, n, α as "fewer than 1 in K", created date, `lengths`, watch-only state and needed count, counts, and whether "Set the limit again" is available |
| `/api/export` | on or off, the endpoint host (no path or headers), whether content is included, and the last send result |

Every text the API returns for display is in plain language (spec FR-007): `reason_text`, `status`
labels, and project promises. Technical fields such as `alpha` exist only for the UI's own math,
and the UI never shows them raw.

## Change endpoints (POST, JSON body, same-origin only)

| Path | Body | Effect | Errors |
|---|---|---|---|
| `/api/mistake` | `{"task": "<session>/<run>"}` | `records.add_feedback(run, "mistaken_stop")` | 404 if the task is unknown; 409 "That one is already marked."; 400 if it wasn't stopped |
| `/api/exclude` | `{"task": "<session>/<run>"}` | `records.add_feedback(run, "exclude")` | 404, 409 |
| `/api/recalibrate` | `{"project": "<name>"}` | for a `cc-` project with a known history folder: `calibration.calibrate(folder, project=name)`; returns the plain `calibrate_message` | 400 if the project can't be recalibrated from here, with the command to run instead |
| `/api/export/send` | `{}` | runs `export --pending` in the background, then returns at once | 409 if export is off |
| `/api/export/test` | `{}` | sends one test span to the configured traces endpoint, and returns the result (status code and message, never headers) | 409 if export is off |

**Duplicates**: a double-sent action is idempotent, because Phase 3's `add_feedback` refuses a
second identical mark.
