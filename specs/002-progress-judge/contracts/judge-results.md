# Contract: Published results (`eval/results/judge/`)

Phase 1's `eval/results/` stays untouched. Everything here is public-dataset content or aggregate
numbers.

## `results.csv`

The Phase 1 columns (`specs/001-offline-eval/contracts/results.md`), plus:

| Column | Meaning |
|---|---|
| `setup` | The judge setup id, empty for methods without a judge |
| `ask_level` | Empty, or the "ask only when needed" level |
| `net_saved_mean, net_saved_lo, net_saved_hi` | Net tokens saved: mean over plain splits, and the bootstrap 95% interval |
| `judge_share` | Judge tokens / held-out agent tokens (mean) |
| `asked_share` | Share of held-out steps the judge was asked about (mean) |

## `results.md`

Sections, in this order:

1. **Reproduce**: the commands, the seed, data fingerprints, the judge setup id and the stored
   judgment file fingerprints.
2. **Verdict**: GO or NO-GO on **net** tokens saved, the chosen method (from `judge_candidate.json`),
   and for each dataset the bar, the paired difference with its 95% interval, and validity.
3. **Main table** (α 5%, n 20): `exact`, `steps`, Phase 1's `max` (λ 0.9) and the chosen judge
   method. Shows false stops, tokens saved, net tokens saved and judge share.
4. **Against Phase 1 and FailFast**: the same three caveats as Phase 1.
5. **Ask only when needed**: share asked, net saved, and the expected extra delay per agent step
   (typical and worst 5%).
6. **The judge itself**: total calls, tokens, cost in dollars, no-opinion share by reason, how
   often inputs were shortened, judge time (median and 95th percentile), and the re-check agreement
   rate.
7. **All methods** (exploratory; development rows marked in-sample).
8. **Skipped and missing**: per-group counts.

## `kill-stories.md`

At least 10 per public group. Each uses the Phase 1 format, and its "Reason" line also gives the
judge's view of the stop step:

```text
Reason: judge: no progress in 4 of last 5 steps (repeated, 0.81); repeating in 5 of last 5 steps (similar to step 19)
```

## Corrections

Any later change to how these results are computed goes into `eval/results/CORRECTIONS.md`, under a
dated heading that names this feature.
