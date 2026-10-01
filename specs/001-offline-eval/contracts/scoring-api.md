# Contract: Scoring core (`src/loopbrake/`)

This is the code the experiment certifies. Phase 2's `Brake` and Phase 3's hook MUST call these
functions and MUST NOT re-implement them (constitution Principle II). It is stdlib only
(Principle III).

## `loopbrake.signals`

```python
class Step(NamedTuple):
    action: str
    observation: str
    error: bool | None
    tokens: int

def method(name: str, lam: float | None = None) -> Callable[[Sequence[Step]], list[tuple[float, str]]]:
    """Return the scorer for a method in METHODS. Raises ValueError on an unknown name, or on a
    missing or extra lam."""

METHODS: tuple[str, ...]   # ("fixed", "exact", "steps", "fuzzy", "stale", "errors", "mean", "max", "loop")
```

**Guarantees**:
- The scorer returns one `(score, reason)` per step. `reason` is a short human-readable string;
  it can be empty when nothing fired.
- It is pure: the same input gives the same output, with no I/O, clock, randomness or globals.
- No look-ahead: `scorer(steps[:t]) == scorer(steps)[:t]` for every t.
- `fixed` reproduces `liveness.watch` from liveness.py. On its demo agents, the first step with
  score ≥ 1 is where `watch` stops:
  - for "stuck", the step count `watch` returns;
  - for "over_budget", `max_steps + 1`, the step `watch` pulls and refuses.

  Its model call was already paid for, so its tokens count as spent.

## `loopbrake.conformal`

```python
def rank(n: int, alpha: float) -> int:
    """k = ceil((n + 1) * (1 - alpha)), computed exactly via Fraction(str(alpha))."""

def threshold(run_scores: Sequence[float], alpha: float) -> float:
    """The k-th smallest of run_scores; math.inf when k > len(run_scores)."""
```

**Guarantees**:
- `threshold(xs, 0.05)` is `inf` for `len(xs) ≤ 18` and `max(xs)` for `len(xs) in (19, 20)`.
- With exchangeable continuous scores, P(new score > τ) = (n + 1 − k)/(n + 1) ≤ α. A test checks
  this by simulation.

## `loopbrake.traces`

```python
class Run(NamedTuple):
    group: str
    dataset: str  # added while building: needed to group results by dataset
    task: str
    run: str
    success: bool
    exit: str | None
    tokens_measured: bool
    steps: tuple[Step, ...]

def read_runs(path: str | Path) -> tuple[list[Run], Counter]:
    """Read a normalized runs file (contracts/normalized-runs.md). Returns (runs, skipped reasons)."""

def write_runs(path: str | Path, runs: Iterable[Run]) -> None: ...

def claude_code_turns(transcript: str | Path, exclude: Container[str] = ()) -> tuple[list[Run], Counter]:
    """Split one Claude Code session transcript into turns (one Run each), following research R10.
    Returns (runs, counts of unrecognised or skipped records). The only parser of this format."""
```

## Kill semantics (shared by evaluation and the later live paths)

A run is killed after step t, where t is the first step with `score > tau`. For `fixed`, the
condition is `score >= 1`. Tokens of steps 1..t are spent; tokens after t are saved.
