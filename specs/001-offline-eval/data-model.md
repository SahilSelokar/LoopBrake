# Data Model: Offline Evaluation Experiment

**Feature**: [spec.md](spec.md) | **Research**: [research.md](research.md)

Plain records only: NamedTuples or dicts, no class hierarchy. The JSON shapes are fixed in
[contracts/normalized-runs.md](contracts/normalized-runs.md) and
[contracts/results.md](contracts/results.md).

## Step

One agent action plus the result it got back.

| Field | Type | Rules |
|---|---|---|
| `action` | str | Normalized action text: `tool_name` + JSON args with sorted keys, or the extracted shell command, or the message sent to the user. Never empty. |
| `observation` | str | The tool output or user reply. May be empty. |
| `error` | bool \| None | True or false when the source says so (return code, `is_error`). None means unknown, and the text fallback applies (research R6). |
| `tokens` | int ≥ 0 | Billed tokens charged to this step (research R3). |

## Run

One recorded attempt at one task. For Claude Code, one user turn.

| Field | Type | Rules |
|---|---|---|
| `group` | str | The group id (research R1), or `local-<k>`. |
| `dataset` | str | `swe-bench-verified`, `tau-bench` or `claude-code-local` |
| `task` | str | The task id. Splits happen on this field. |
| `run` | str | Unique within the group. |
| `success` | bool | Taken from the dataset label (`resolved`, `reward == 1`) or from the Claude Code proxy (R10). |
| `exit` | str \| None | The source's exit status (`Submitted`, `LimitsExceeded`, `interrupted`, …). Informational only. |
| `tokens_measured` | bool | False means the step tokens are chars/4 estimates. |
| `steps` | list[Step] | Ordered. Length ≥ 1. A run with no steps is skipped and counted (FR-015). |

A run's total tokens are the sum of its step tokens. Runs are immutable after loading.

## Group

All runs from one agent on one dataset. This is the unit for calibration and testing.

| Field | Type | Rules |
|---|---|---|
| `id` | str | e.g. `swe-gpt5mini` |
| `dataset` | str | `swe-bench-verified`, `tau-bench` or `claude-code-local` |
| `role` | `dev` \| `holdout` \| `local` | Only `swe-devstral` is `dev` (research R9). |
| `runs` | list[Run] | |
| `skipped` | dict[str, int] | Count of skipped items for each reason. |

## Method

A way of scoring steps. Each method is a pure function (constitution Principle II):

```text
score(steps: list[Step]) -> list[(score: float, reason: str)]   # one entry per step
```

| Field | Values |
|---|---|
| `name` | `fixed`, `exact`, `steps`, `fuzzy`, `stale`, `errors`, `mean`, `max`, `loop` |
| `lam` | λ ∈ {0.8, 0.9, 1.0} for the six signal methods. None for the baselines. |
| `calibrated` | False only for `fixed`. Its kill rule is built in: a score ≥ 1 kills. |

**Invariant (no look-ahead)**: for every t, `score(steps[:t]) == score(steps)[:t]`.

**Derived per run** (computed once per method, then reused by every split):
- `peak`: the running maximum of the scores. It never decreases, so the kill step can be found
  with a bisect.
- `run_score = peak[-1]`.
- `tail_tokens[t]`: the tokens saved if the run is killed after step t.

## Threshold

| Field | Rules |
|---|---|
| `alpha` | One of {0.01, 0.05, 0.10} |
| `n` | One of {20, 50, 100}: the calibration sample size |
| `k` | ⌈(n+1)(1−α)⌉, computed exactly with `Fraction` |
| `tau` | The k-th smallest calibration run score, or `inf` when k > n |

## Split

| Field | Rules |
|---|---|
| `calibration` | n successful runs from n different tasks, one run per task |
| `held_out` | All runs whose `task` doesn't appear among the calibration runs' tasks |
| `kind` | `plain` (original data) or `boot` (resampled tasks; every copy of a calibration task is excluded from `held_out`) |

**Status**: `insufficient` when fewer than n tasks have a success, or the held-out set has
fewer than 20 successes.

## Kill event

Produced when a held-out run's peak first goes above τ at step t.

| Field | Rules |
|---|---|
| `run`, `group`, `method` | References |
| `step` | 1-based kill step; `total_steps` is the run's length |
| `reason` | From the method's reason at step t. Names the signals that fired (Principle I). |
| `tokens_saved` | `tail_tokens[t]`, which is 0 when the kill lands on the last step |
| `false_kill` | `run.success` |

Kill stories (FR-012) are kill events on failed runs, rendered with up to 5 preceding actions,
each trimmed to 80 characters.

## Result row

One row per group × method × λ × α × n. The columns are listed in
[contracts/results.md](contracts/results.md).

**Validity**:
- `invalid` when the lower bound of the Monte Carlo confidence interval of the mean false-kill
  rate is above α.
- `insufficient` per the Split rules.
- `fixed` rows are never judged against α. Their false-kill rate is reported as a finding
  (SC-008).

## Candidate (pre-registration)

`eval/candidate.json`: `{"method": "<name>", "lam": <float>, "chosen_on": "swe-devstral",
"date": "YYYY-MM-DD"}`. It must exist and be committed before `--final` runs (research R9).

## Verdict

| Field | Rules |
|---|---|
| `candidate` | Taken from candidate.json |
| `baseline` | For each dataset, whichever of `exact` and `steps` has the higher mean savings at the headline setting |
| `per_dataset` | For `swe-bench-verified` and `tau-bench`: the mean paired difference, its 95% bootstrap interval, and pass (lower bound > 0) |
| `valid_everywhere` | The candidate isn't `invalid` in any holdout group |
| `result` | `go` when every dataset passes and `valid_everywhere`; otherwise `no-go` |

## Relationships

```text
Group 1─* Run 1─* Step
Method × Group → per-run (peak, tail_tokens)
Split (seeded, shared across methods) + Method → Threshold → Kill events → Result row
Candidate + Result rows (holdout, headline setting) → Verdict
```
