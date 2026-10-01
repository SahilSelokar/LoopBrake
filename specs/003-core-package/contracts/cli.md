# Contract: Command line

The `loopbrake` command is installed with the package (`[project.scripts]`). Every command reads and
writes only under `$LOOPBRAKE_HOME` (default `~/.loopbrake`).

| Command | What it does | Exit codes |
|---|---|---|
| `loopbrake --version` | Prints `loopbrake 0.1.0` | 0 |
| `loopbrake calibrate SOURCE [--project P] [--alpha 0.05]` | Sets the stop line from a runs file or a Claude Code project folder ([python-api.md](python-api.md)). Prints the stop line, n, k and α, or "watch-only: need X more successful runs". | 0 when written, watch-only included; 2 when the source is unreadable |
| `loopbrake status [--project P]` | Shows the stop line in force, its source and date, runs watched, runs stopped, mistaken stops and the allowance ([records.md](records.md)) | 0 |
| `loopbrake feedback RUN (--mistaken \| --exclude)` | `--mistaken` records that a stop was wrong. `--exclude` also keeps that run out of future calibration. | 0; 1 when the run id isn't found |
| `loopbrake replay RUNS_FILE (--project P \| --stop-line N)` | Feeds each recorded run through a brake and prints, per run, the stop step (or `-`) and a summary: runs, stopped, stopped successes. It writes no records. | 0; 2 when unreadable |

The output is plain text, with no emoji (builder's rule). Errors go to stderr, without stack traces
unless `LOOPBRAKE_DEBUG=1` is set.
