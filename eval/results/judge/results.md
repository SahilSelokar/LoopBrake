# LoopBrake progress judge: results

## 1. Reproduce

```bash
uv run python eval/fetch.py
uv run python eval/tasks.py
uv run python eval/judge.py --group swe-devstral swe-gpt5mini tau-gpt4o-airline tau-gpt4o-retail tau-sonnet35-airline tau-sonnet35-retail
uv run python eval/judge_eval.py --final --seed 0 --splits 1000 --boot 1000
```

Judge setup: `jev-1.13.0/v1/1a9e81db`. Fingerprints (sha256) of the runs and the stored judgments:

```text
456b539a611de14f2a340a4258becce1748e52148a9279fdfb92bc1e518e63de  swe-devstral.jsonl
34b4706178eabab3eaa302b342f50cb5ae569dfe7268d7c8e218ae8caedd1a1c  swe-gpt5mini.jsonl
a61374db098730f9dd7367f221621ee3c3d43f152176c4487dac6591369f7011  tau-gpt4o-airline.jsonl
4c6e3d443b01979e039aba2160d2e95d0f024cce74ebfa4dcd249ce2e5df7fbc  tau-gpt4o-retail.jsonl
bbd839e07178e01360e2730beaf3ef272ff7700ab96d88b0bedafa73cedd3c59  tau-sonnet35-airline.jsonl
a8ff74e82504d7c14f33ede2158f271fdbe50599c05b0c48a349812dfb26bf71  tau-sonnet35-retail.jsonl
91b71d780127c115245ce1592824f927b4075811a5047762d99ac09c4cccf7fd  judgments/swe-devstral.jsonl
667103eb15a2b003944eac0c259ce398c0a54f416572490fae70f76a38fbafe3  judgments/swe-gpt5mini.jsonl
df30c9a986c580638e6f707ca003f47a84515bc1853e99171b3b2ae152061ef7  judgments/tau-gpt4o-airline.jsonl
55fee33ab0fcbc300ccfd971bf9356fd431bc1b853503ef77234cd7dd36f2d2b  judgments/tau-gpt4o-retail.jsonl
42e12c406c08ef8701c35eeadc90fce63e227726908571e6eeaae6ee178472f1  judgments/tau-sonnet35-airline.jsonl
426726ab0baa831b7573fbac01d2fa99520edb809a67aaec4fe8b1cd1668e35a  judgments/tau-sonnet35-retail.jsonl
```

## 2. Verdict: NO-GO

Method chosen in advance on `swe-devstral` (2026-10-01): **judge_max (λ 0.9), ask ≥ 7.79**.

| Dataset | Groups tested | Bar to beat | Extra NET tokens saved [95% interval] | Above zero |
|---|---|---|---|---|
| swe-bench-verified | swe-gpt5mini | steps | -6.3% [-18.9%, 1.9%] | no |
| tau-bench | tau-gpt4o-airline, tau-gpt4o-retail, tau-sonnet35-airline, tau-sonnet35-retail | steps | -4.2% [-8.2%, -1.5%] | no |

Chosen method within its false-stop limit on every holdout group: yes.

Net means the judge's own tokens are subtracted, counted one for one with the agent's tokens, although they cost less.

## 3. Main table (α = 5%, n = 20)

| Group | Method | False stops [95%] | Tokens saved | Net saved [95%] | Judge share | Status |
|---|---|---|---|---|---|---|
| swe-devstral (dev) | exact | 4.1% [3.9%, 4.3%] | 21.4% | 21.4% [9.8%, 34.1%] | 0.0% | ok |
| swe-devstral (dev) | steps | 4.8% [4.5%, 5.1%] | 20.8% | 20.8% [6.8%, 36.4%] | 0.0% | ok |
| swe-devstral (dev) | max (λ 0.9) | 5.0% [4.7%, 5.3%] | 26.5% | 26.5% [15.1%, 39.4%] | 0.0% | ok |
| swe-devstral (dev) | judge_max (λ 0.9), ask ≥ 7.79 | 5.0% [4.7%, 5.4%] | 26.4% | 25.8% [15.3%, 40.2%] | 0.6% | ok |
| swe-gpt5mini | exact | 2.6% [2.4%, 2.7%] | 3.2% | 3.2% [0.2%, 8.9%] | 0.0% | ok |
| swe-gpt5mini | steps | 4.4% [4.1%, 4.6%] | 9.3% | 9.3% [0.8%, 22.8%] | 0.0% | ok |
| swe-gpt5mini | max (λ 0.9) | 4.7% [4.4%, 4.9%] | 10.8% | 10.8% [1.2%, 26.6%] | 0.0% | ok |
| swe-gpt5mini | judge_max (λ 0.9), ask ≥ 7.79 | 0.7% [0.7%, 0.7%] | 2.8% | 2.8% [0.5%, 5.1%] | 0.0% | ok |
| tau-gpt4o-airline | exact | 2.1% [1.9%, 2.4%] | 3.3% | 3.3% [0.0%, 15.5%] | 0.0% | ok |
| tau-gpt4o-airline | steps | 2.9% [2.7%, 3.2%] | 9.2% | 9.2% [1.8%, 17.8%] | 0.0% | ok |
| tau-gpt4o-airline | max (λ 0.9) | 3.4% [3.1%, 3.7%] | 10.9% | 10.9% [0.0%, 23.1%] | 0.0% | ok |
| tau-gpt4o-airline | judge_max (λ 0.9), ask ≥ 7.79 | 0.0% [0.0%, 0.0%] | 0.0% | 0.0% [0.0%, 0.0%] | 0.0% | ok |
| tau-gpt4o-retail | exact | 1.8% [1.6%, 1.9%] | 1.5% | 1.5% [0.0%, 7.4%] | 0.0% | ok |
| tau-gpt4o-retail | steps | 2.7% [2.4%, 2.9%] | 1.7% | 1.7% [0.0%, 7.7%] | 0.0% | ok |
| tau-gpt4o-retail | max (λ 0.9) | 3.1% [2.9%, 3.3%] | 2.8% | 2.8% [0.1%, 11.3%] | 0.0% | ok |
| tau-gpt4o-retail | judge_max (λ 0.9), ask ≥ 7.79 | 0.0% [0.0%, 0.0%] | 0.0% | 0.0% [0.0%, 0.0%] | 0.0% | ok |
| tau-sonnet35-airline | exact | 2.0% [1.8%, 2.2%] | 1.2% | 1.2% [0.0%, 10.9%] | 0.0% | ok |
| tau-sonnet35-airline | steps | 3.5% [3.2%, 3.7%] | 5.7% | 5.7% [0.3%, 18.5%] | 0.0% | ok |
| tau-sonnet35-airline | max (λ 0.9) | 4.9% [4.6%, 5.2%] | 5.6% | 5.6% [0.0%, 19.8%] | 0.0% | ok |
| tau-sonnet35-airline | judge_max (λ 0.9), ask ≥ 7.79 | 1.1% [1.0%, 1.1%] | 2.3% | 2.2% [0.0%, 8.5%] | 0.1% | ok |
| tau-sonnet35-retail | exact | 1.8% [1.7%, 2.0%] | 1.9% | 1.9% [0.0%, 8.0%] | 0.0% | ok |
| tau-sonnet35-retail | steps | 2.6% [2.4%, 2.8%] | 1.3% | 1.3% [0.0%, 5.4%] | 0.0% | ok |
| tau-sonnet35-retail | max (λ 0.9) | 3.1% [2.9%, 3.3%] | 2.9% | 2.9% [0.1%, 11.9%] | 0.0% | ok |
| tau-sonnet35-retail | judge_max (λ 0.9), ask ≥ 7.79 | 0.0% [0.0%, 0.0%] | 0.0% | 0.0% [0.0%, 0.0%] | 0.0% | ok |

## 4. Against Phase 1 and FailFast

| Method | Net tokens saved at 5% false stops (swe-gpt5mini) |
|---|---|
| steps, n = 20 | 9.3% |
| steps, n = 100 | 11.2% |
| max (λ 0.9), n = 20 | 10.8% |
| max (λ 0.9), n = 100 | 12.9% |
| judge_max (λ 0.9), ask ≥ 7.79, n = 20 | 2.8% |
| judge_max (λ 0.9), ask ≥ 7.79, n = 100 | 3.2% |
| FailFast (trained monitor) (paper, other models) | 14.6–20.4% |
| AgentStop (paper, other models) | 10.2–12.5% |
| Duration (step count only) (paper, other models) | 10.0–12.0% |

Caveats, as in Phase 1: FailFast set its 5% line on the data it reports on; it used other models; it does not say which tokens it counts.

## 5. Ask only when needed

- swe-devstral: judge asked on 15.5% of steps; expected extra delay per agent step 125 ms typical, 6031 ms worst 5%.
- swe-gpt5mini: judge asked on 0.1% of steps; expected extra delay per agent step 1 ms typical, 6031 ms worst 5%.
- tau-gpt4o-airline: judge asked on 0.0% of steps; expected extra delay per agent step 0 ms typical, 6031 ms worst 5%.
- tau-gpt4o-retail: judge asked on 0.0% of steps; expected extra delay per agent step 0 ms typical, 6031 ms worst 5%.
- tau-sonnet35-airline: judge asked on 0.3% of steps; expected extra delay per agent step 2 ms typical, 6031 ms worst 5%.
- tau-sonnet35-retail: judge asked on 0.0% of steps; expected extra delay per agent step 0 ms typical, 6031 ms worst 5%.

Phase 3's live target is 200 ms per step.

## 6. The judge itself

- Calls: 73,812; tokens: 93,075,660; cost: about $3.91
- No opinion: 0.0% (7 unreadable, 0 service errors)
- Inputs shortened to fit: 90.5%
- Time per call: median 809 ms, 95th percentile 6031 ms
- Re-check (same answer when asked again): 94.0% of 200 steps
- Most common kinds of step: found_new 27,826, talked 11,207, dead_end 9,540, changed 9,378, repeated 7,146

## 7. All methods (α = 5%, n = 20)

Exploratory. Development rows are in-sample.

| Group | Method | False stops | Net saved | Status |
|---|---|---|---|---|
| swe-devstral (dev) | fixed | 99.3% | 78.1% | ok |
| swe-devstral (dev) | exact | 4.1% | 21.4% | ok |
| swe-devstral (dev) | steps | 4.8% | 20.8% | ok |
| swe-devstral (dev) | max (λ 0.9) | 5.0% | 26.5% | ok |
| swe-devstral (dev) | judge (λ 0.9) | 4.8% | 12.8% | ok |
| swe-devstral (dev) | judge_steps (λ 0.9) | 4.8% | 13.2% | ok |
| swe-devstral (dev) | judge_max (λ 0.9) | 4.8% | 22.0% | ok |
| swe-devstral (dev) | judge_max (λ 0.9), ask ≥ 7.79 | 5.0% | 25.8% | ok |
| swe-gpt5mini | fixed | 29.1% | 33.2% | ok |
| swe-gpt5mini | exact | 2.6% | 3.2% | ok |
| swe-gpt5mini | steps | 4.4% | 9.3% | ok |
| swe-gpt5mini | max (λ 0.9) | 4.7% | 10.8% | ok |
| swe-gpt5mini | judge (λ 0.9) | 4.7% | -3.2% | ok |
| swe-gpt5mini | judge_steps (λ 0.9) | 4.8% | -1.9% | ok |
| swe-gpt5mini | judge_max (λ 0.9) | 4.6% | -2.4% | ok |
| swe-gpt5mini | judge_max (λ 0.9), ask ≥ 7.79 | 0.7% | 2.8% | ok |
| tau-gpt4o-airline | fixed | 1.2% | 9.6% | ok |
| tau-gpt4o-airline | exact | 2.1% | 3.3% | ok |
| tau-gpt4o-airline | steps | 2.9% | 9.2% | ok |
| tau-gpt4o-airline | max (λ 0.9) | 3.4% | 10.9% | ok |
| tau-gpt4o-airline | judge (λ 0.9) | 3.3% | -23.7% | ok |
| tau-gpt4o-airline | judge_steps (λ 0.9) | 3.3% | -22.4% | ok |
| tau-gpt4o-airline | judge_max (λ 0.9) | 3.1% | -20.4% | ok |
| tau-gpt4o-airline | judge_max (λ 0.9), ask ≥ 7.79 | 0.0% | 0.0% | ok |
| tau-gpt4o-retail | fixed | 8.2% | 4.6% | ok |
| tau-gpt4o-retail | exact | 1.8% | 1.5% | ok |
| tau-gpt4o-retail | steps | 2.7% | 1.7% | ok |
| tau-gpt4o-retail | max (λ 0.9) | 3.1% | 2.8% | ok |
| tau-gpt4o-retail | judge (λ 0.9) | 4.7% | -34.4% | ok |
| tau-gpt4o-retail | judge_steps (λ 0.9) | 4.4% | -34.3% | ok |
| tau-gpt4o-retail | judge_max (λ 0.9) | 4.7% | -33.9% | ok |
| tau-gpt4o-retail | judge_max (λ 0.9), ask ≥ 7.79 | 0.0% | 0.0% | ok |
| tau-sonnet35-airline | fixed | 2.2% | 5.4% | ok |
| tau-sonnet35-airline | exact | 2.0% | 1.2% | ok |
| tau-sonnet35-airline | steps | 3.5% | 5.7% | ok |
| tau-sonnet35-airline | max (λ 0.9) | 4.9% | 5.6% | ok |
| tau-sonnet35-airline | judge (λ 0.9) | 3.3% | -23.2% | ok |
| tau-sonnet35-airline | judge_steps (λ 0.9) | 3.4% | -22.7% | ok |
| tau-sonnet35-airline | judge_max (λ 0.9) | 4.1% | -22.2% | ok |
| tau-sonnet35-airline | judge_max (λ 0.9), ask ≥ 7.79 | 1.1% | 2.2% | ok |
| tau-sonnet35-retail | fixed | 5.1% | 2.3% | ok |
| tau-sonnet35-retail | exact | 1.8% | 1.9% | ok |
| tau-sonnet35-retail | steps | 2.6% | 1.3% | ok |
| tau-sonnet35-retail | max (λ 0.9) | 3.1% | 2.9% | ok |
| tau-sonnet35-retail | judge (λ 0.9) | 4.6% | -29.8% | ok |
| tau-sonnet35-retail | judge_steps (λ 0.9) | 4.4% | -30.5% | ok |
| tau-sonnet35-retail | judge_max (λ 0.9) | 3.9% | -30.9% | ok |
| tau-sonnet35-retail | judge_max (λ 0.9), ask ≥ 7.79 | 0.0% | 0.0% | ok |

## 8. Skipped and missing

- swe-devstral: skipped runs 1 (no steps); steps without a judgment: 0
- swe-gpt5mini: skipped runs none; steps without a judgment: 0
- tau-gpt4o-airline: skipped runs none; steps without a judgment: 0
- tau-gpt4o-retail: skipped runs none; steps without a judgment: 0
- tau-sonnet35-airline: skipped runs none; steps without a judgment: 0
- tau-sonnet35-retail: skipped runs none; steps without a judgment: 0
