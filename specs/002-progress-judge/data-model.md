# Data Model: Progress Judge Experiment

**Feature**: [spec.md](spec.md) | **Research**: [research.md](research.md)

Phase 1's records (Step, Run, Group, Split, Result row) are reused unchanged; see
`specs/001-offline-eval/data-model.md`. This feature adds the records below.

## Task text

One per task, stored in `~/.loopbrake/data/tasks/<group>.jsonl`.

| Field | Type | Rules |
|---|---|---|
| `task` | str | The same id as `Run.task` |
| `text` | str | The task as given to the agent (research R5). Never empty. Shortened only when the judge's input is built. |

## Judge setup

A fixed setup with a version; it is never edited in place.

| Field | Rules |
|---|---|
| `id` | `jev-1.13.0/v1/<8 hex>`: the model, the version and a template fingerprint |
| `model` | `jev-1.13.0`, pinned |
| `template` | The questions and the state layout from research R2 |
| `limits` | Task 1,500 characters; 3 earlier actions of ≤ 200 characters each; action 600; result 1,200 head + 800 tail |

## Judgment

One per judged step, stored in `~/.loopbrake/judgments/<setup>/<group>.jsonl` (append-only).

| Field | Type | Rules |
|---|---|---|
| `key` | str | `sha256` of the canonical request body. Unique per setup. |
| `group`, `run`, `step` | str, str, int | Where the step sits (`step` counts from 1) |
| `progress` | float \| null | P(progress) from 0 to 1. `null` means "no opinion". |
| `kind` | str \| null | The most likely kind of step (one of the 8 keys in research R2) |
| `kind_p` | float \| null | That kind's probability |
| `status` | `ok` \| `unreadable` \| `service_error` \| `truncated_ok` | `truncated_ok`: the state had to be shortened, and the answer is fine |
| `tokens` | int ≥ 0 | `usage.input_tokens + usage.output_tokens` |
| `ms` | int ≥ 0 | Wall time of the successful call, including retries |

**Rules**:
- `progress` is `null` exactly when `status` is `unreadable` or `service_error`.
- No record ever contains the access key.

## Judge method

A pure scorer: `judged(name, lam)(steps, progress, kinds=None)` returns `[(score, reason), …]`, one
per step (research R6). `kinds`, if given, only feeds the reason text; it never changes a score.

| Field | Values |
|---|---|
| `name` | `judge`, `judge_steps`, `judge_max` |
| `lam` | {0.8, 0.9, 1.0} |
| `ask_level` | None (judge every step), or L for the "ask only when needed" variant |

**Invariants**:
- **No look-ahead**: `scorer(steps[:t], progress[:t]) == scorer(steps, progress)[:t]`.
- **No opinion**: a `None` in `progress` leaves the running score unchanged at that step.

## Net result row

A Phase 1 result row plus:

| Column | Meaning |
|---|---|
| `net_saved_mean`, `net_saved_lo`, `net_saved_hi` | (agent tokens saved − judge tokens spent) / held-out agent tokens: the mean over plain splits and the bootstrap 95% interval |
| `judge_share` | Judge tokens spent / held-out agent tokens |
| `asked_share` | Share of held-out steps the judge was consulted on (1.0 unless `ask_level` is set) |

## Judge candidate (pre-registration)

`eval/judge_candidate.json`:

```json
{"setup": "jev-1.13.0/v1/…", "method": "judge", "lam": 0.9, "ask_level": null,
 "chosen_on": "swe-devstral", "date": "YYYY-MM-DD"}
```

It must be committed before any holdout group is judged (research R9).

## Verdict

The same as Phase 1, computed on `net_saved` instead of `saved_all`. The bar is the stronger of
`exact` and `steps` (their net equals their gross, because they have no judge cost).

## Relationships

```text
Task text 1─* Run 1─* Step ──(setup)── 0..1 Judgment
Judge setup 1─* Judgment
Judge method × Group → per-run (peak, tail tokens, judge-tokens-so-far) → splits → Net result rows → Verdict
```
