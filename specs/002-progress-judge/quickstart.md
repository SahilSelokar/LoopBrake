# Quickstart: Validating the Progress Judge Experiment

This guide runs the feature end to end and checks it against the spec's success criteria. The
commands follow [contracts/judge-cli.md](contracts/judge-cli.md).

## Prerequisites

- **Phase 1 data**: already fetched (`~/.loopbrake/data/runs/` holds 6 files; see Phase 1's
  quickstart).
- **Typesafe access key** in your environment, never typed into a chat or committed:

  ```bash
  read -rs "k?Typesafe key: " && printf '%s' "$k" > ~/.loopbrake/typesafe_key && chmod 600 ~/.loopbrake/typesafe_key && unset k
  ```

  (In bash, use `read -rsp 'Typesafe key: ' k` instead.)
- **Budget**: about $3 of Jev usage and about 1.5 hours of judging in total (research R3).

## 1. Unit checks

```bash
uv run pytest
```

**Expect**: all Phase 1 tests plus the new ones pass:

| Test | Checks |
|---|---|
| request building | State limits, the `…` cut mark, the canonical key (stable, and without the access key) |
| response reading | `noul` and `choice` parsing; missing fields become `unreadable` |
| retries | A fake server returns 429 and then 200, and the client retries. A fake 401 stops everything. |
| refusals | `local-*` and unknown groups are refused. Holdout groups are refused before the candidate is committed. |
| judged scorer | It never looks ahead, and "no opinion" keeps the score unchanged |
| net savings | Hand-made runs check judge tokens up to the stop step, and that skipped steps cost nothing |

## 2. Task texts

```bash
uv run python eval/tasks.py
```

**Expect**: six groups. The task counts are 500, 500, 50, 115, 50 and 115, the same as Phase 1's
tasks per group.

## 3. Story 1: judge the development group

```bash
uv run python eval/judge.py --group swe-devstral --runs 100 --seed 0   # quick look first (~7,500 steps)
uv run python eval/judge.py --group swe-devstral                       # the rest (~30,000 steps)
uv run python eval/judge.py --group swe-devstral --recheck 200
uv run python eval/judge_eval.py --dev
```

**Expect**:
- **Judging**: progress lines with a running dollar estimate, staying under $1.50 for this group.
  An interrupted run resumes without judging anything twice.
- **Repeatability**: agreement of at least 95%, or the true rate is reported (SC-004).
- **Setup health**: if the judge looks broken (research R9), switch to a `v2` setup on this group
  only and write down why.
- **Results**: a development table with the judge methods next to `steps`, `exact` and Phase 1's
  `max`, showing net tokens saved and judge share. The same command twice gives identical output.

## 4. Story 3: ask only when needed

Shown by the same `--dev` run. **Expect**:
- rows for the 3 levels, with the share asked, net saved, and the expected extra delay per step
  (typical and worst 5%);
- SC-006 target: at most half the steps asked, while keeping at least 80% of the full judge's net
  savings.

## 5. Story 2: choose, commit, then judge the holdout groups

```bash
# choose from the --dev table, then record the choice BEFORE any holdout judging
echo '{"setup": "<id from the dev table>", "method": "<name>", "lam": 0.9, "ask_level": null, "chosen_on": "swe-devstral", "date": "YYYY-MM-DD"}' > eval/judge_candidate.json
git add eval/judge_candidate.json && git commit -m "eval: pre-register judge candidate"
uv run python eval/judge.py --group swe-gpt5mini tau-gpt4o-airline tau-gpt4o-retail tau-sonnet35-airline tau-sonnet35-retail
time uv run python eval/judge_eval.py --final
```

**Expect**:
- **Refusal check**: running `judge.py` on a holdout group *before* the commit exits with code 3.
- **SC-002**: `eval/results/judge/results.md` opens with GO or NO-GO, based on net tokens saved.
- **SC-001**: no holdout row is invalid for the chosen method.
- **SC-005** (target): compare the chosen method's net savings on `swe-gpt5mini` with 20.4%.
- **SC-007**: section 5 states the expected delay per agent step.
- **Kill stories**: `kill-stories.md` has at least 10 per group, each with the judge's view.

## 6. Reproducibility and privacy

```bash
cp -r eval/results/judge /tmp/j1 && uv run python eval/judge_eval.py --final && diff -r /tmp/j1 eval/results/judge && echo identical
git grep -n "$(cat ~/.loopbrake/typesafe_key)" && echo LEAK || echo "key not in repo"
```

**Expect**:
- `identical` (SC-003, SC-004);
- `key not in repo` (SC-008);
- judging inputs contain only public group ids, which `judge.py` enforces.
