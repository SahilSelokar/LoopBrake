# LoopBrake offline evaluation: results

## 1. Reproduce

```bash
uv run python eval/fetch.py
uv run python eval/run.py --final --seed 0 --splits 1000 --boot 1000
```

Data fingerprints (sha256 of each runs file):

```text
456b539a611de14f2a340a4258becce1748e52148a9279fdfb92bc1e518e63de  swe-devstral.jsonl
34b4706178eabab3eaa302b342f50cb5ae569dfe7268d7c8e218ae8caedd1a1c  swe-gpt5mini.jsonl
a61374db098730f9dd7367f221621ee3c3d43f152176c4487dac6591369f7011  tau-gpt4o-airline.jsonl
4c6e3d443b01979e039aba2160d2e95d0f024cce74ebfa4dcd249ce2e5df7fbc  tau-gpt4o-retail.jsonl
bbd839e07178e01360e2730beaf3ef272ff7700ab96d88b0bedafa73cedd3c59  tau-sonnet35-airline.jsonl
a8ff74e82504d7c14f33ede2158f271fdbe50599c05b0c48a349812dfb26bf71  tau-sonnet35-retail.jsonl
```

Corrections to earlier runs are listed in [CORRECTIONS.md](CORRECTIONS.md).

## 2. Verdict: NO-GO

Method chosen in advance on `swe-devstral` (2026-10-01): **max (λ 0.9)**.

| Dataset | Groups tested | Bar to beat | Extra tokens saved [95% interval] | Above zero |
|---|---|---|---|---|
| swe-bench-verified | swe-gpt5mini | steps | 1.5% [-9.7%, 13.2%] | no |
| tau-bench | tau-gpt4o-airline, tau-gpt4o-retail, tau-sonnet35-airline, tau-sonnet35-retail | steps | 0.9% [-3.1%, 5.0%] | no |

Candidate within its false-stop limit on every holdout group: yes.

GO means: on every dataset the candidate saves more than the stronger simple method, with the whole
95% interval above zero, and it never breaks its false-stop limit. The interval resamples tasks, so it
includes the noise of having a limited number of tasks.

## 3. Main table (α = 5%, calibrated on n = 20 successful runs)

| Group | Method | False stops [95%] | Tokens saved, all runs [95%] | Saved on failed runs | Status |
|---|---|---|---|---|---|
| swe-devstral (dev) | fixed | 99.3% [99.3%, 99.3%] | 78.1% [71.1%, 84.8%] | 74.9% | ok |
| swe-devstral (dev) | exact | 4.1% [3.9%, 4.3%] | 21.4% [9.8%, 34.1%] | 27.7% | ok |
| swe-devstral (dev) | steps | 4.8% [4.5%, 5.1%] | 20.8% [6.8%, 36.4%] | 26.8% | ok |
| swe-devstral (dev) | max (λ 0.9) | 5.0% [4.7%, 5.3%] | 26.5% [15.1%, 39.4%] | 34.5% | ok |
| swe-gpt5mini | fixed | 29.1% [29.1%, 29.2%] | 33.2% [28.6%, 38.1%] | 41.0% | ok |
| swe-gpt5mini | exact | 2.6% [2.4%, 2.7%] | 3.2% [0.2%, 8.9%] | 4.3% | ok |
| swe-gpt5mini | steps | 4.4% [4.1%, 4.6%] | 9.3% [0.8%, 22.8%] | 13.3% | ok |
| swe-gpt5mini | max (λ 0.9) | 4.7% [4.4%, 4.9%] | 10.8% [1.2%, 26.6%] | 15.1% | ok |
| tau-gpt4o-airline | fixed | 1.2% [1.1%, 1.2%] | 9.6% [2.8%, 16.6%] | 11.8% | ok |
| tau-gpt4o-airline | exact | 2.1% [1.9%, 2.4%] | 3.3% [0.0%, 15.5%] | 3.8% | ok |
| tau-gpt4o-airline | steps | 2.9% [2.7%, 3.2%] | 9.2% [1.8%, 17.8%] | 11.3% | ok |
| tau-gpt4o-airline | max (λ 0.9) | 3.4% [3.1%, 3.7%] | 10.9% [0.0%, 23.1%] | 13.1% | ok |
| tau-gpt4o-retail | fixed | 8.2% [8.1%, 8.3%] | 4.6% [2.2%, 8.0%] | 7.3% | ok |
| tau-gpt4o-retail | exact | 1.8% [1.6%, 1.9%] | 1.5% [0.0%, 7.4%] | 1.7% | ok |
| tau-gpt4o-retail | steps | 2.7% [2.4%, 2.9%] | 1.7% [0.0%, 7.7%] | 2.9% | ok |
| tau-gpt4o-retail | max (λ 0.9) | 3.1% [2.9%, 3.3%] | 2.8% [0.1%, 11.3%] | 4.6% | ok |
| tau-sonnet35-airline | fixed | 2.2% [2.1%, 2.3%] | 5.4% [1.0%, 13.7%] | 6.6% | ok |
| tau-sonnet35-airline | exact | 2.0% [1.8%, 2.2%] | 1.2% [0.0%, 10.9%] | 1.4% | ok |
| tau-sonnet35-airline | steps | 3.5% [3.2%, 3.7%] | 5.7% [0.3%, 18.5%] | 6.9% | ok |
| tau-sonnet35-airline | max (λ 0.9) | 4.9% [4.6%, 5.2%] | 5.6% [0.0%, 19.8%] | 5.7% | ok |
| tau-sonnet35-retail | fixed | 5.1% [5.1%, 5.2%] | 2.3% [1.1%, 4.1%] | 4.2% | ok |
| tau-sonnet35-retail | exact | 1.8% [1.7%, 2.0%] | 1.9% [0.0%, 8.0%] | 3.3% | ok |
| tau-sonnet35-retail | steps | 2.6% [2.4%, 2.8%] | 1.3% [0.0%, 5.4%] | 2.3% | ok |
| tau-sonnet35-retail | max (λ 0.9) | 3.1% [2.9%, 3.3%] | 2.9% [0.1%, 11.9%] | 5.1% | ok |

## 4. Against FailFast

| Method | Data | Tokens saved at 5% false stops |
|---|---|---|
| LoopBrake steps, n = 20 | swe-gpt5mini | 9.3% |
| LoopBrake steps, n = 100 | swe-gpt5mini | 11.2% |
| LoopBrake max (λ 0.9), n = 20 | swe-gpt5mini | 10.8% |
| LoopBrake max (λ 0.9), n = 100 | swe-gpt5mini | 12.9% |
| FailFast (trained monitor) | FailFast paper (other models) | 14.6–20.4% |
| AgentStop | FailFast paper (other models) | 10.2–12.5% |
| Duration (step count only) | FailFast paper (other models) | 10.0–12.0% |

Read this comparison with care:
1. FailFast set its 5% line on the same data it reports on, so its 5% is a target, not a guarantee. Ours is set on separate runs.
2. Different models: FailFast used Qwen3.5/3.6, Gemma4 and Gemini 3 Flash; these numbers use GPT-5-mini.
3. FailFast does not say exactly which tokens it counts. We count every token each model call reads and writes.

## 5. Price of the guarantee (α = 5%)

Tokens saved, all runs. More past runs give a tighter stop line.

| Group | Method | n = 20 | n = 50 | n = 100 |
|---|---|---|---|---|
| swe-devstral | steps | 20.8% | 20.7% | 24.7% |
| swe-devstral | max (λ 0.9) | 26.5% | 26.6% | 29.2% |
| swe-gpt5mini | steps | 9.3% | 9.2% | 11.2% |
| swe-gpt5mini | max (λ 0.9) | 10.8% | 10.6% | 12.9% |
| tau-gpt4o-airline | steps | 9.2% | not enough data | not enough data |
| tau-gpt4o-airline | max (λ 0.9) | 10.9% | not enough data | not enough data |
| tau-gpt4o-retail | steps | 1.7% | 1.7% | not enough data |
| tau-gpt4o-retail | max (λ 0.9) | 2.8% | 2.9% | not enough data |
| tau-sonnet35-airline | steps | 5.7% | not enough data | not enough data |
| tau-sonnet35-airline | max (λ 0.9) | 5.6% | not enough data | not enough data |
| tau-sonnet35-retail | steps | 1.3% | 0.9% | not enough data |
| tau-sonnet35-retail | max (λ 0.9) | 2.9% | 2.5% | not enough data |

## 6. All methods (α = 5%, n = 20)

Exploratory. Rows on the development group are in-sample: the candidate was chosen there.

| Group | Method | False stops | Tokens saved, all runs | Status |
|---|---|---|---|---|
| swe-devstral (dev) | fixed | 99.3% | 78.1% | ok |
| swe-devstral (dev) | exact | 4.1% | 21.4% | ok |
| swe-devstral (dev) | steps | 4.8% | 20.8% | ok |
| swe-devstral (dev) | fuzzy (λ 0.9) | 4.7% | 23.4% | ok |
| swe-devstral (dev) | stale (λ 0.9) | 4.9% | 25.0% | ok |
| swe-devstral (dev) | errors (λ 0.9) | 4.7% | 15.0% | ok |
| swe-devstral (dev) | mean (λ 0.9) | 5.0% | 26.2% | ok |
| swe-devstral (dev) | max (λ 0.9) | 5.0% | 26.5% | ok |
| swe-devstral (dev) | loop (λ 0.9) | 5.0% | 25.2% | ok |
| swe-gpt5mini | fixed | 29.1% | 33.2% | ok |
| swe-gpt5mini | exact | 2.6% | 3.2% | ok |
| swe-gpt5mini | steps | 4.4% | 9.3% | ok |
| swe-gpt5mini | fuzzy (λ 0.9) | 4.7% | 11.5% | ok |
| swe-gpt5mini | stale (λ 0.9) | 4.7% | 7.1% | ok |
| swe-gpt5mini | errors (λ 0.9) | 2.8% | 6.1% | ok |
| swe-gpt5mini | mean (λ 0.9) | 4.8% | 9.1% | ok |
| swe-gpt5mini | max (λ 0.9) | 4.7% | 10.8% | ok |
| swe-gpt5mini | loop (λ 0.9) | 4.7% | 6.4% | ok |
| tau-gpt4o-airline | fixed | 1.2% | 9.6% | ok |
| tau-gpt4o-airline | exact | 2.1% | 3.3% | ok |
| tau-gpt4o-airline | steps | 2.9% | 9.2% | ok |
| tau-gpt4o-airline | fuzzy (λ 0.9) | 3.8% | 9.6% | ok |
| tau-gpt4o-airline | stale (λ 0.9) | 2.9% | 9.7% | ok |
| tau-gpt4o-airline | errors (λ 0.9) | 1.2% | 5.7% | ok |
| tau-gpt4o-airline | mean (λ 0.9) | 3.2% | 11.3% | ok |
| tau-gpt4o-airline | max (λ 0.9) | 3.4% | 10.9% | ok |
| tau-gpt4o-airline | loop (λ 0.9) | 3.3% | 9.2% | ok |
| tau-gpt4o-retail | fixed | 8.2% | 4.6% | ok |
| tau-gpt4o-retail | exact | 1.8% | 1.5% | ok |
| tau-gpt4o-retail | steps | 2.7% | 1.7% | ok |
| tau-gpt4o-retail | fuzzy (λ 0.9) | 3.1% | 2.6% | ok |
| tau-gpt4o-retail | stale (λ 0.9) | 2.6% | 2.6% | ok |
| tau-gpt4o-retail | errors (λ 0.9) | 2.8% | 2.6% | ok |
| tau-gpt4o-retail | mean (λ 0.9) | 3.7% | 3.4% | ok |
| tau-gpt4o-retail | max (λ 0.9) | 3.1% | 2.8% | ok |
| tau-gpt4o-retail | loop (λ 0.9) | 3.7% | 2.8% | ok |
| tau-sonnet35-airline | fixed | 2.2% | 5.4% | ok |
| tau-sonnet35-airline | exact | 2.0% | 1.2% | ok |
| tau-sonnet35-airline | steps | 3.5% | 5.7% | ok |
| tau-sonnet35-airline | fuzzy (λ 0.9) | 2.9% | 7.5% | ok |
| tau-sonnet35-airline | stale (λ 0.9) | 5.0% | 4.4% | ok |
| tau-sonnet35-airline | errors (λ 0.9) | 0.5% | 0.5% | ok |
| tau-sonnet35-airline | mean (λ 0.9) | 4.1% | 6.0% | ok |
| tau-sonnet35-airline | max (λ 0.9) | 4.9% | 5.6% | ok |
| tau-sonnet35-airline | loop (λ 0.9) | 3.8% | 6.9% | ok |
| tau-sonnet35-retail | fixed | 5.1% | 2.3% | ok |
| tau-sonnet35-retail | exact | 1.8% | 1.9% | ok |
| tau-sonnet35-retail | steps | 2.6% | 1.3% | ok |
| tau-sonnet35-retail | fuzzy (λ 0.9) | 3.8% | 3.3% | ok |
| tau-sonnet35-retail | stale (λ 0.9) | 3.4% | 3.2% | ok |
| tau-sonnet35-retail | errors (λ 0.9) | 1.1% | 2.4% | ok |
| tau-sonnet35-retail | mean (λ 0.9) | 3.8% | 3.7% | ok |
| tau-sonnet35-retail | max (λ 0.9) | 3.1% | 2.9% | ok |
| tau-sonnet35-retail | loop (λ 0.9) | 3.8% | 3.2% | ok |

## 7. Token estimate check

τ-bench records no token counts, so they are estimated as characters / 4 of everything each call reads and writes.
On the SWE-bench groups we can compare that estimate with measured usage (estimate / measured, per run).
The estimate ignores the system prompt, the task text and hidden reasoning, so it should come out low.

| Group | Median ratio | Middle half |
|---|---|---|
| swe-devstral | 0.66 | 0.57–0.73 |
| swe-gpt5mini | 0.75 | 0.64–0.83 |

## 8. Skipped runs

- swe-devstral: 1 (no steps)
- swe-gpt5mini: none
- tau-gpt4o-airline: none
- tau-gpt4o-retail: none
- tau-sonnet35-airline: none
- tau-sonnet35-retail: none
