# Contract: Evaluation commands

These are developer scripts, run from the repository root through `uv run`. Phase 2 may wrap
them as `loopbrake eval`, but this contract doesn't promise that.

## `uv run python eval/fetch.py [--data DIR] [--only GROUP ...]`

- **Network**: yes. This is the only step that uses it (FR-016). It downloads the sources listed
  in research R1 into `DIR/raw/` (default `~/.loopbrake/data`), then writes
  `DIR/runs/<group>.jsonl` and `SHA256SUMS`.
- **Idempotent**: files already present are not downloaded again.
- **Output**: one line per group, with runs, successes, failures and skipped counts.
- **Exit codes**:
  - 0: OK.
  - 1: a download failed, or a group's resolved count differs from research R1.

## `uv run python eval/run.py [MODE] [options]`

| Mode | What it evaluates | Writes |
|---|---|---|
| `--dev` (default) | `swe-devstral` only; every method × λ grid × (α, n) | `~/.loopbrake/eval/dev-results.csv` |
| `--final` | Every public group: the ablation, plus the gate for the pre-registered candidate | `eval/results/results.csv`, `results.md`, `kill-stories.md` |
| `--story GROUP RUN` | One run: the kill story at the headline setting, at the median τ over plain splits | stdout only |

**Options**:

| Option | Meaning |
|---|---|
| `--local` | Add Claude Code groups from `~/.claude/projects/*/`. Per-run details go to `~/.loopbrake/eval/local/`; committed outputs only get anonymized aggregate rows (`local-k`). |
| `--method M --lam L` | Used with `--story`. Defaults to candidate.json. |
| `--seed INT` | Default 0. |
| `--splits INT` | Default 1000; minimum 500 (FR-008). |
| `--boot INT` | Default 1000. |
| `--data DIR` | Default `~/.loopbrake/data`. |

**Behavior**:
- **Deterministic**: the same data, seed and options produce byte-identical outputs (SC-003). No
  timestamps go inside the result files; the date comes from candidate.json.
- **Paired splits**: splits are generated once per group and configuration, then shared by every
  method.
- **`--dev`** prints the dev table plus the best method and λ by mean `saved_all` at the headline
  setting, among valid rows. That's a suggestion only. The builder writes `eval/candidate.json`
  by hand.
- **`--final`** refuses to run (exit code 2) without `eval/candidate.json`. If the folder is a
  git repository and the file isn't committed, it prints a warning.
- **Offline**: it makes no network calls.

**Exit codes**:
- 0: OK. A no-go verdict is still exit 0, because it's a result, not a failure.
- 1: data missing or unreadable.
- 2: candidate.json missing in `--final`.
