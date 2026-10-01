# Quickstart: Validating the Offline Evaluation

This guide runs the feature end to end and checks it against the spec's success criteria. The
commands follow [contracts/eval-cli.md](contracts/eval-cli.md). The outputs follow
[contracts/results.md](contracts/results.md).

## Prerequisites

- `uv` and Python ≥ 3.11.
- About 400 MB free under `~/.loopbrake/data`.
- Network access for step 2 only.
- Run everything from the `LoopBrake/` root.

## 1. Unit checks

```bash
uv run pytest
```

**Expect**: all tests pass. Four of them carry the spec's guarantees:

| Test | Checks |
|---|---|
| conformal oracle | Simulated exchangeable scores give a mean false-kill rate within ±0.5 points of 1/21 at n = 20, α = 5%. `threshold` is `inf` at n = 18. |
| no look-ahead | For every method, scoring a prefix equals the prefix of the full scoring (Principle II). |
| liveness equivalence | `fixed` stops liveness.py's demo agents where `watch` does: looping → step 5; wandering → step 21 (`watch` reports 20). |
| Claude Code fixture | The synthetic transcript has split assistant records, parallel tool calls, an interrupt and a local-command record. It yields the expected turns, labels and de-duplicated tokens. |

## 2. Fetch data (one time, the only networked step)

```bash
uv run python eval/fetch.py
```

**Expect**: six groups, with successes/runs of 282/500, 281/500, 84/200, 278/460, 184/400 and
637/920. It exits 0, and `~/.loopbrake/data/runs/SHA256SUMS` exists.

## 3. Story 1: the calibrated baseline

```bash
uv run python eval/run.py --dev
```

**Expect** in the dev table (`swe-devstral`):

- Every calibrated row at α = 5% has a false-kill confidence interval that includes or lies
  below 0.05 (SC-001 on dev).
- The `fixed` row's false-kill rate is far above 5%. Most successful runs are longer than 20
  steps, which makes the case for calibration (SC-008).
- Running it twice prints identical tables. The rule that with too few runs it never kills is
  covered by the unit test in step 1.

## 4. Story 2: pre-register the candidate, then run the final evaluation

```bash
# choose from the --dev suggestion, then record it before looking at holdout numbers
echo '{"method": "loop", "lam": 0.9, "chosen_on": "swe-devstral", "date": "2026-10-01"}' > eval/candidate.json
git add eval/candidate.json && git commit -m "eval: pre-register gate candidate"   # once a repo exists
time uv run python eval/run.py --final
```

The candidate shown above is a placeholder. Use whatever `--dev` suggests.

**Expect**:

- **SC-002**: the run takes under 15 minutes.
- **SC-004**: `eval/results/results.md` opens with a `GO` or `NO-GO` verdict. Each dataset line
  shows the baseline used, the paired difference and its 95% interval.
- **SC-001**: no holdout row is `invalid`.
- **SC-006**: `kill-stories.md` has at least 10 stories per public group.
- **SC-005** (target): the headline `saved_all` on `swe-gpt5mini` is compared with 20.4% in the
  FailFast section.
- **Sanity anchor** (research R4): `steps` on `swe-gpt5mini` at n = 100 should land in the same
  range as FailFast's Duration control, about 10–12%. A large gap means the token accounting
  needs checking.

## 5. Reproducibility (SC-003)

```bash
cp -r eval/results /tmp/r1 && uv run python eval/run.py --final && diff -r /tmp/r1 eval/results && echo identical
```

## 6. Story 3: your own Claude Code history

```bash
uv run python eval/run.py --final --local
```

**Expect**:
- `local-k` rows appear. Projects with at least 20 successful turns get numbers; the others show
  as `insufficient`.
- Per-run details exist only under `~/.loopbrake/eval/local/`.
- **SC-007** check:

  ```bash
  uv run python -c "import json, pathlib; h = pathlib.Path.home(); names = json.loads((h / '.loopbrake/eval/local-map.json').read_text()).values(); text = ''.join(p.read_text() for p in pathlib.Path('eval/results').iterdir() if p.is_file()); print('LEAK' if str(h) in text or any(n in text for n in names) else 'clean')"
  ```

  It must print `clean`.

## 7. One kill story, for a reel

```bash
uv run python eval/run.py --story swe-gpt5mini <instance_id>
```

**Expect**: the kill step, a reason naming the signals, and the preceding actions. It should be
readable aloud in under 15 seconds.
