# Contract: Commands

All commands run from the repository root with `uv run`.

## `uv run python eval/tasks.py [--data DIR]`

- **What it does**: reads the raw files already downloaded by `eval/fetch.py` and writes
  `DIR/tasks/<group>.jsonl` (default `~/.loopbrake/data`). It makes no network calls.
- **Output**: one line per group with the number of tasks.
- **Exit codes**: 0 OK; 1 if a raw file is missing, or if any run in the runs file has a task with
  no text.

## `uv run python eval/judge.py --group G [--group G ...] [options]`

This calls Jev for every step of each group that isn't already stored.

| Option | Meaning |
|---|---|
| `--setup v1` | Which judge setup (research R2). Default `v1`. |
| `--runs N --seed S` | Judge only a fixed random sample of N runs (for trying a setup). Default: all runs. |
| `--recheck 200` | Re-judge a fixed, seeded sample of already-stored steps and print the agreement rate (SC-004). Nothing is stored. |
| `--rate 30 --workers 16` | Pacing (research R3) |
| `--data DIR` | Default `~/.loopbrake/data` |

**Refusals**:
- **Unknown group**: any group that isn't one of the six public ones (`local-*` included). Exit 2.
- **Holdout too early**: a holdout group while `eval/judge_candidate.json` isn't committed
  (research R9). Exit 3.
- **No key**: neither `TYPESAFE_API_KEY` nor `~/.loopbrake/typesafe_key` is set. Exit 4.
- **Bad key**: a `401` response. Exit 5.

**Progress**: one line per group every 1,000 steps, with steps done, no-opinion count, tokens so far
and an estimated cost. Stopping with Ctrl-C is safe: everything stored stays, and a rerun resumes
where it stopped.

## `uv run python eval/judge_eval.py [MODE] [options]`

| Mode | What it evaluates | Writes |
|---|---|---|
| `--dev` (default) | `swe-devstral`: Phase 1 methods, the judge methods × λ {0.8, 0.9, 1.0}, and the "ask only when needed" variant at the 3 levels from research R8 | `~/.loopbrake/eval/judge-dev-results.csv` |
| `--final` | Every public group, plus the gate for the chosen method in `eval/judge_candidate.json` | `eval/results/judge/results.csv`, `results.md`, `kill-stories.md` |
| `--story GROUP RUN` | One kill story with the judge's reason | stdout |

**Shared options**: `--seed`, `--splits` (minimum 500), `--boot`, `--data`, and `--setup` (default:
the setup in the candidate file, or `v1`).

**Behavior**:
- It reads stored judgments only, and never calls Jev.
- A step with no stored judgment counts as "no opinion". The count is reported, and `--final`
  refuses to run if any holdout step is missing (exit 1).
- Same inputs, same outputs, byte for byte.

**Exit codes**: 0 OK (a NO-GO is still exit 0); 1 for missing data or judgments; 2 when
`--final` has no committed candidate.
