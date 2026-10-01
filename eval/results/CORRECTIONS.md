# Corrections

Every change to how results are computed after the first final run, with before and after numbers.
The first run's outputs are kept unchanged in git history (commit `e655b96`).

## 2026-10-01: stop line set from at most one run per task

**What was wrong.** The stop line was set from 20 successful runs drawn without regard to their
task. τ-bench repeats every task 4–8 times, so a sample could hold several attempts at the same
task. Those repeats are not independent: the stop line came out too low for new tasks, and the
guarantee broke. The check built into the evaluation caught this, marking the rows `invalid`.

**Fix.** Calibration now uses at most one run per task (`make_split` in `eval/run.py`, and research
R7). SWE-bench has one run per task, so its main numbers are identical. Only its bootstrap
intervals moved slightly, because bootstrap samples repeat tasks.

**The method chosen in advance did not change** (`max`, λ 0.9, commit `8b8eaf3`).

| | First run (`e655b96`) | After the fix |
|---|---|---|
| Verdict | NO-GO | NO-GO |
| SWE-bench: extra tokens saved vs step count | +1.5% [−10.6%, +15.1%] | +1.5% [−9.7%, +13.2%] |
| τ-bench: extra tokens saved vs step count | +2.2% [−2.1%, +7.4%] | +0.9% [−3.1%, +5.0%] |
| `tau-gpt4o-airline`, `max`: false stops (limit 5%) | 6.4% (invalid) | 3.4% |
| `tau-sonnet35-retail`, `max`: false stops (limit 5%) | 5.4% (invalid) | 3.1% |
| Holdout rows breaking the 5% limit | 2 for the chosen method, 8 in total | none |

**Cost of the fix.** The number of past runs used can't exceed the number of tasks with a success,
so `tau-gpt4o-airline` has no result at n = 50 or n = 100.
