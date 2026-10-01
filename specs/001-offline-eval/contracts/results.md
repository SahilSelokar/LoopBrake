# Contract: Committed results (`eval/results/`)

Everything here is aggregate or public-dataset content only (FR-014). Local groups appear only as
`local-k` aggregate rows.

## `results.csv`

One row per group × method × λ × α × n.

| Column(s) | Meaning |
|---|---|
| `group, dataset, role, method, lam, alpha, n` | Configuration. `lam` is empty for baselines. |
| `splits` | Number of plain splits actually used (splits with fewer than 20 held-out successes are dropped) |
| `status` | `ok`, `insufficient` or `invalid` (data-model.md) |
| `runs, successes, failures, skipped, tokens_measured` | Data used |
| `fk_mean, fk_lo, fk_hi, fk_p05, fk_p95` | False-kill rate: plain-split mean, the Monte Carlo 95% confidence interval of the mean, and the 5th–95th percentile across splits |
| `saved_all_mean, saved_all_lo, saved_all_hi, saved_all_p05, saved_all_p95` | Tokens saved overall (the headline; research R4): plain-split mean, bootstrap 95% interval, split percentiles |
| `saved_fail_mean, saved_fail_lo, saved_fail_hi` | Tokens saved on failed runs |
| `lost_mean` | Tokens thrown away by false kills (tokens spent before the kill on killed successful runs), as a share of all held-out tokens |
| `kill_step_median` | Median kill step on killed failed runs |

- Rates are fractions with 4 decimals.
- Rows are sorted by `group, method, lam, alpha, n`.

## `results.md` (human report)

Sections, in this order:

1. **Reproduce**: the exact command, the seed, the split and bootstrap counts, and each group's
   data sha256.
2. **Verdict**: `GO` or `NO-GO`, the candidate (from candidate.json), and for each dataset the
   baseline used, the mean paired difference and its 95% interval, plus the validity status.
3. **Headline** (α = 5%, n = 20): for each group, `fixed`, `exact`, `steps` and the candidate,
   with their false-kill and saved-overall values.
4. **Against FailFast**: our `steps` and candidate on `swe-gpt5mini` next to FailFast's published
   numbers, with the three caveats from research R4.
5. **Price of the guarantee**: candidate and `steps` savings at n ∈ {20, 50, 100}, α = 5%.
6. **Ablation** (exploratory): every method at the headline setting. Dev rows are marked
   in-sample.
7. **Token estimate check**: the chars/4 estimate against measured usage on the SWE-bench groups.
8. **Skipped**: counts and reasons for each group.

## `kill-stories.md`

At least 10 stories per public group (SC-006), taken from failed runs the candidate kills at the
median τ, ordered by tokens saved:

```text
### swe-gpt5mini · django__django-11099 · killed at step 23 of 61 · saved 412,880 tokens (71%)
Reason: same command as step 12 (5 of last 5 steps); 0 of 38 output lines new
  19  python reproduce.py
  20  sed -n 1,40p django/core/validators.py
  …   (up to 5 preceding actions, each ≤ 80 chars)
```

Each story stays under 60 words of prose, so it can be read aloud in under 15 seconds.
