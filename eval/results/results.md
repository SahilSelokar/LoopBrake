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

## 2. Verdict: NO-GO

Method chosen in advance on `swe-devstral` (2026-10-01): **max (λ 0.9)**.

| Dataset | Groups tested | Bar to beat | Extra tokens saved [95% interval] | Above zero |
|---|---|---|---|---|
| swe-bench-verified | swe-gpt5mini | steps | 1.5% [-10.6%, 15.1%] | no |
| tau-bench | tau-gpt4o-airline, tau-gpt4o-retail, tau-sonnet35-airline, tau-sonnet35-retail | steps | 2.2% [-2.1%, 7.4%] | no |

Candidate within its false-stop limit on every holdout group: no (tau-gpt4o-airline, tau-sonnet35-retail).

GO means: on every dataset the candidate saves more than the stronger simple method, with the whole
95% interval above zero, and it never breaks its false-stop limit. The interval resamples tasks, so it
includes the noise of having a limited number of tasks.

## 3. Main table (α = 5%, calibrated on n = 20 successful runs)

| Group | Method | False stops [95%] | Tokens saved, all runs [95%] | Saved on failed runs | Status |
|---|---|---|---|---|---|
| swe-devstral (dev) | fixed | 99.3% [99.3%, 99.3%] | 78.1% [70.7%, 85.6%] | 74.9% | ok |
| swe-devstral (dev) | exact | 4.1% [3.9%, 4.3%] | 21.4% [10.0%, 34.9%] | 27.7% | ok |
| swe-devstral (dev) | steps | 4.8% [4.5%, 5.1%] | 20.8% [7.6%, 36.6%] | 26.8% | ok |
| swe-devstral (dev) | max (λ 0.9) | 5.0% [4.7%, 5.3%] | 26.5% [15.6%, 40.0%] | 34.5% | ok |
| swe-gpt5mini | fixed | 29.1% [29.1%, 29.2%] | 33.2% [28.7%, 38.4%] | 41.0% | ok |
| swe-gpt5mini | exact | 2.6% [2.4%, 2.7%] | 3.2% [0.0%, 9.0%] | 4.3% | ok |
| swe-gpt5mini | steps | 4.4% [4.1%, 4.6%] | 9.3% [0.7%, 21.8%] | 13.3% | ok |
| swe-gpt5mini | max (λ 0.9) | 4.7% [4.4%, 4.9%] | 10.8% [1.2%, 26.8%] | 15.1% | ok |
| tau-gpt4o-airline | fixed | 1.5% [1.4%, 1.6%] | 9.3% [3.8%, 15.0%] | 11.5% | ok |
| tau-gpt4o-airline | exact | 3.1% [2.8%, 3.3%] | 4.2% [0.0%, 13.9%] | 4.9% | ok |
| tau-gpt4o-airline | steps | 5.0% [4.6%, 5.4%] | 9.8% [2.7%, 20.7%] | 12.0% | ok |
| tau-gpt4o-airline | max (λ 0.9) | 6.4% [5.9%, 6.9%] | 13.1% [0.0%, 34.7%] | 15.5% | invalid |
| tau-gpt4o-retail | fixed | 8.6% [8.5%, 8.6%] | 4.7% [2.4%, 8.0%] | 7.3% | ok |
| tau-gpt4o-retail | exact | 1.9% [1.7%, 2.1%] | 1.6% [0.0%, 7.3%] | 1.7% | ok |
| tau-gpt4o-retail | steps | 4.2% [3.9%, 4.5%] | 2.5% [0.1%, 12.9%] | 4.0% | ok |
| tau-gpt4o-retail | max (λ 0.9) | 5.0% [4.7%, 5.3%] | 4.5% [0.1%, 16.4%] | 6.8% | ok |
| tau-sonnet35-airline | fixed | 2.0% [1.9%, 2.0%] | 4.8% [0.8%, 10.1%] | 5.8% | ok |
| tau-sonnet35-airline | exact | 1.8% [1.6%, 2.1%] | 1.2% [0.0%, 12.4%] | 1.4% | ok |
| tau-sonnet35-airline | steps | 4.8% [4.4%, 5.2%] | 5.5% [0.3%, 18.2%] | 6.5% | ok |
| tau-sonnet35-airline | max (λ 0.9) | 5.4% [5.0%, 5.8%] | 5.1% [0.0%, 23.4%] | 5.2% | ok |
| tau-sonnet35-retail | fixed | 5.3% [5.3%, 5.4%] | 2.5% [1.2%, 4.4%] | 4.2% | ok |
| tau-sonnet35-retail | exact | 2.1% [2.0%, 2.3%] | 2.2% [0.0%, 7.9%] | 3.7% | ok |
| tau-sonnet35-retail | steps | 4.5% [4.2%, 4.8%] | 2.0% [0.0%, 7.9%] | 3.4% | ok |
| tau-sonnet35-retail | max (λ 0.9) | 5.4% [5.1%, 5.7%] | 4.4% [0.2%, 13.9%] | 7.0% | invalid |

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
| tau-gpt4o-airline | steps | 9.8% | not enough data | not enough data |
| tau-gpt4o-airline | max (λ 0.9) | 13.1% | not enough data | not enough data |
| tau-gpt4o-retail | steps | 2.5% | 2.5% | 3.6% |
| tau-gpt4o-retail | max (λ 0.9) | 4.5% | 4.8% | 7.2% |
| tau-sonnet35-airline | steps | 5.5% | 6.0% | not enough data |
| tau-sonnet35-airline | max (λ 0.9) | 5.1% | 5.0% | not enough data |
| tau-sonnet35-retail | steps | 2.0% | 1.6% | 2.4% |
| tau-sonnet35-retail | max (λ 0.9) | 4.4% | 4.0% | 5.8% |

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
| tau-gpt4o-airline | fixed | 1.5% | 9.3% | ok |
| tau-gpt4o-airline | exact | 3.1% | 4.2% | ok |
| tau-gpt4o-airline | steps | 5.0% | 9.8% | ok |
| tau-gpt4o-airline | fuzzy (λ 0.9) | 6.4% | 11.5% | invalid |
| tau-gpt4o-airline | stale (λ 0.9) | 5.1% | 13.3% | ok |
| tau-gpt4o-airline | errors (λ 0.9) | 1.5% | 5.9% | ok |
| tau-gpt4o-airline | mean (λ 0.9) | 6.6% | 14.5% | invalid |
| tau-gpt4o-airline | max (λ 0.9) | 6.4% | 13.1% | invalid |
| tau-gpt4o-airline | loop (λ 0.9) | 5.9% | 13.4% | invalid |
| tau-gpt4o-retail | fixed | 8.6% | 4.7% | ok |
| tau-gpt4o-retail | exact | 1.9% | 1.6% | ok |
| tau-gpt4o-retail | steps | 4.2% | 2.5% | ok |
| tau-gpt4o-retail | fuzzy (λ 0.9) | 5.0% | 4.1% | ok |
| tau-gpt4o-retail | stale (λ 0.9) | 2.6% | 2.5% | ok |
| tau-gpt4o-retail | errors (λ 0.9) | 2.4% | 2.2% | ok |
| tau-gpt4o-retail | mean (λ 0.9) | 4.8% | 4.2% | ok |
| tau-gpt4o-retail | max (λ 0.9) | 5.0% | 4.5% | ok |
| tau-gpt4o-retail | loop (λ 0.9) | 3.9% | 2.9% | ok |
| tau-sonnet35-airline | fixed | 2.0% | 4.8% | ok |
| tau-sonnet35-airline | exact | 1.8% | 1.2% | ok |
| tau-sonnet35-airline | steps | 4.8% | 5.5% | ok |
| tau-sonnet35-airline | fuzzy (λ 0.9) | 5.9% | 9.9% | invalid |
| tau-sonnet35-airline | stale (λ 0.9) | 5.4% | 4.0% | ok |
| tau-sonnet35-airline | errors (λ 0.9) | 0.7% | 0.4% | ok |
| tau-sonnet35-airline | mean (λ 0.9) | 5.5% | 6.3% | invalid |
| tau-sonnet35-airline | max (λ 0.9) | 5.4% | 5.1% | ok |
| tau-sonnet35-airline | loop (λ 0.9) | 5.5% | 8.6% | invalid |
| tau-sonnet35-retail | fixed | 5.3% | 2.5% | ok |
| tau-sonnet35-retail | exact | 2.1% | 2.2% | ok |
| tau-sonnet35-retail | steps | 4.5% | 2.0% | ok |
| tau-sonnet35-retail | fuzzy (λ 0.9) | 5.3% | 4.5% | ok |
| tau-sonnet35-retail | stale (λ 0.9) | 5.0% | 4.4% | ok |
| tau-sonnet35-retail | errors (λ 0.9) | 1.0% | 2.5% | ok |
| tau-sonnet35-retail | mean (λ 0.9) | 5.3% | 5.0% | ok |
| tau-sonnet35-retail | max (λ 0.9) | 5.4% | 4.4% | invalid |
| tau-sonnet35-retail | loop (λ 0.9) | 5.2% | 4.5% | ok |

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
