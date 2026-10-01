# Research: Progress Judge Experiment

**Feature**: [spec.md](spec.md) | **Date**: 2026-10-01

**Sources**:
- Typesafe docs (api.md, models.md, legal) and the builder's `~/JevWorkshop` notebook;
- the Laya model card;
- a workload count over the Phase 1 runs files.

**Builder's decision (2026-10-01)**: hosted APIs are fine, so the judge does not have to run
offline.

## R1. Which judge

**Decision**: Jev, Typesafe's hosted "System One" decision model, pinned to `jev-1.13.0`.
`jev-latest` would silently change the judge in the middle of an experiment.

**Rationale**:
- **Built for this**: it answers typed questions about a piece of text. A yes/no question (`noul`)
  returns P(yes) directly; a choice question returns a probability for each option.
- **No text parsing**: the judgment is a number, so there's nothing to parse.
- **Cheap**: $0.042 per million input tokens, and output is free.
- **Fast**: limits of 40 requests a second and 100k tokens a second.
- **Fits the project**: plain HTTPS + JSON, so a standard-library client works (Principle III).
- **Builder's interest**: the builder has worked with it (`~/JevWorkshop`), and the project's
  plans already name it as the System 1 model.

**Alternatives considered**:
- **Laya** (Convai Innovations, Apache-2.0, runs locally, same request format): rejected.
  - It reads only 512–1,024 tokens, and our steps are often longer.
  - Its own card reports near-chance accuracy on typed decisions without fine-tuning.
  - It ships over-confident until it is recalibrated.
  - It is worth revisiting only if a fine-tuning phase happens.
- **A general hosted LLM** (for example a small Claude model): rejected for now.
  - It doesn't return token probabilities, so we would have to ask for a number, which is less
    trustworthy.
  - It costs about 20× more.
- **A small open model on the builder's laptop**: kept as a fallback if Jev becomes unavailable.
  See R13.

## R2. What the judge sees, and what it's asked

**Decision**: one request per step. The `state` is a small object:

| Field | Content | Limit |
|---|---|---|
| `task` | The task as given to the agent: the first user message | first 1,500 characters |
| `earlier_actions` | The last 3 actions before this step | each ≤ 200 characters |
| `action` | This step's action (the shell command, tool call or reply) | ≤ 600 characters |
| `result` | This step's result | first 1,200 + `…` + last 800 characters |

Two questions go in the same request. The state is billed once.

- **`progress`** (`noul`). Instructions: *"The latest action moved the agent closer to finishing its
  task."* Criteria: true = *"It found information it did not have, changed something the task
  needs, or confirmed the work is done."* False = *"It repeated earlier work, hit an earlier error
  again, or got nothing useful."*
- **`kind`** (`choice`). Instructions: *"What kind of step was the latest action?"* Options:

  | Key | Description |
  |---|---|
  | `found_new` | Found information it did not have before |
  | `changed` | Changed files or settings the task needs |
  | `verified` | Ran a check that confirms progress, such as a passing test |
  | `talked` | Asked or answered the user a question |
  | `finished` | Finished or submitted the task |
  | `repeated` | Repeated or nearly repeated an earlier action |
  | `same_error` | Hit an error it had already hit |
  | `dead_end` | Got an empty, irrelevant or failed result |

**Rationale**:
- **Short, focused state**: Typesafe's notes say accuracy drops when the state holds unrelated
  text. So the state is limited to the task, a short history and this step.
- **Statement wording**: questions are phrased as statements because P(yes) for a statement and
  1 − P(yes) for its negation "may not be directly comparable".
- **Reasons without text**: the `kind` answer gives the one-line reason (spec FR-002) without any
  free-text output.

**Setup version**: `v1`, which is this exact template. The setup id is
`jev-1.13.0/v1/<first 8 hex chars of sha256(template)>`, so stored judgments always name their
setup.

## R3. Speed, retries, cost

**Decision**:
- **Concurrency**: 16 worker threads, paced client-side to at most 30 requests a second, under the
  limit of 40.
- **Retries**: on 429, 529, 5xx or a timeout, retry with growing waits (1, 2, 4 … 32 s, at most
  6 tries). After that, record "no opinion" with the reason `service_error`.

**Workload** (counted from the runs files): 73,812 steps and about 50M state tokens. With roughly
150 instruction tokens per request, that is about 61M input tokens.

**Estimates** (to be measured):
- **Cost**: about **$2.60** (output tokens are free).
- **Time**: about **45 minutes** at 30 requests a second. That's far inside SC-003's 12 hours.

**Alternative considered**: the official async SDK. Rejected because it adds a dependency, and
threads plus `urllib` are enough here.

## R4. Storing judgments (reproducible and resumable)

**Decision**:
- **Where**: one append-only JSON Lines file per setup and group:
  `~/.loopbrake/judgments/<setup-id-with-slashes-as-dashes>/<group>.jsonl`.
- **Key**: `sha256(canonical JSON of the request body)`. The key never contains the access key.
- **Resume**: skip any key already stored, so a step is never judged twice.
- **Evaluation**: reads only stored judgments. It never calls Jev.

**Repeatability check** (SC-004): re-judge a fixed, seeded sample of 200 stored steps. A pair
agrees when |Δ P(progress)| ≤ 0.05 and the top `kind` is the same. Typesafe describes Jev as
"extremely consistent" but not bit-for-bit, so the stored copy is what makes reruns identical.

## R5. Task texts

**Decision**: a new script `eval/tasks.py` reads the raw files that are already downloaded and
writes `~/.loopbrake/data/tasks/<group>.jsonl`, with one `{task, text}` record per task.

| Source | Where the task text is |
|---|---|
| SWE-bench (mini-SWE-agent) | `messages[1].content`, the instance prompt with the issue |
| τ-bench | the first `user` message, the customer's request (the long system policy is left out) |

**Rationale**: the Phase 1 runs files don't carry the task text. Adding it there would change
Phase 1's files and checksums (spec FR-001), so it goes in a separate file.

## R6. Judge methods (spec FR-005)

**Decision**: turning judgments into a stuck score.
- **Progress value**: p = P(progress) per step.
- **"No opinion"** (unreadable answer or service error) leaves the running score exactly where it
  was: S_t = S_(t−1). It neither adds nor fades.
- **λ grid** on the development group: {0.8, 0.9, 1.0}.

| Method | Per-step value u_t | Meaning |
|---|---|---|
| `judge` | 1 − p_t | Unproductive steps add up. With λ = 1 this counts unproductive steps. |
| `judge_steps` | (1 + (1 − p_t)) / 2 | Every step adds at least 0.5 (time); unproductive steps add up to 1 |
| `judge_max` | max(1 − p_t, Phase 1 `max` signal value) | The judge or the cheap signals, whichever looks more stuck |

The running score is S_t = λ·S_(t−1) + u_t, as in Phase 1.

**Code placement**: `loopbrake.signals.judged(name, lam)` returns a pure
`scorer(steps, progress)`, where `progress` is a list of floats or None, aligned with the steps.
The product would call the same function after getting live judgments (Principle II). The Jev
client stays in `eval/`, outside the core (Principle V).

## R7. Net tokens saved (spec FR-006)

**Decision**: for each held-out run, the judge's cost is the tokens Jev reported for every step it
judged up to and including the stop step, or for every step if the run was never stopped.

- **Net saved** = (agent tokens saved − judge tokens spent) over held-out runs, divided by all
  held-out agent tokens.
- **Baselines** have a judge cost of zero.
- Judge tokens count one for one against agent tokens. That is strict: at $0.042 per million, a
  judge token is cheaper than the agent models' tokens. Any fairer exchange rate would only make
  the judge look better.

## R8. "Ask only when needed" (spec FR-011)

**Decision**:
- **When the judge is consulted**: only on steps whose Phase 1 `max` score (λ 0.9) is at or above
  a level L.
- **Choosing L**: on the development group, from the three levels that consult the top 50%, 25% and
  10% of development steps by that score.
- **Other steps**: count as "no opinion", at no judge cost.
- **Delay estimate**:
  - typical: (share of steps consulted) × (median measured judge time);
  - worst 5%: the 95th-percentile judge time on a consulted step.

## R9. Protocol (spec FR-008)

**Decision**:
1. Fetch task texts.
2. Judge **only** the development group with setup `v1`. If `v1` looks broken, a `v2` may be tried
   on the development group only, and the switch is logged. "Broken" means either:
   - more than 90% of p values sit within 0.1 of each other; or
   - more than 10% of steps get "no opinion".
3. Run `judge_eval.py --dev`, choose the method, λ and (for the variant) L, write
   `eval/judge_candidate.json` and commit it.
4. Only then judge the holdout groups. `judge.py` refuses holdout groups until the candidate file
   is committed.
5. Run `judge_eval.py --final`.

**Rationale**: the same pre-registration as Phase 1, now enforced by the tooling as well as by
habit.

## R10. Privacy and the access key (spec FR-003, SC-008)

**Decision**:
- **Key**: read from the `TYPESAFE_API_KEY` environment variable, or else from
  `~/.loopbrake/typesafe_key` (one line, readable only by the owner). It lives outside the
  repository.
- **No leaks**: the `Authorization` header is never logged or stored. Error messages drop it.
- **Public data only**: `judge.py` accepts only the six public group ids. It refuses `local-*`
  groups and any unknown group.
- **For the product**: a hosted judge would count as exporting content under Principle VI, so it
  would need its own explicit opt-in. That's a Phase 2/3 matter, recorded here.

## R11. What this means for live use (input to Phase 3, not built here)

The docs publish no latency figure. The Typesafe homepage shows 0.114 s, and a third party claims
a median of 236–276 ms (unverified). Network time comes on top.

A judge on every step would probably break Phase 3's 200 ms per-step target. "Ask only when
needed", plus judging in the background (deciding at the next step), are the levers. This
experiment measures real numbers (spec SC-007) so Phase 3 can choose.

## R12. Evaluation reuse (spec FR-001)

**Decision**: a new `eval/judge_eval.py` imports from `eval/run.py`:
- loading;
- splits (one run per task);
- `threshold`;
- summaries and intervals;
- `decide` and `stronger_baseline`.

It adds the judge methods, net savings and the variant. `eval/run.py` and its outputs stay
unchanged. Judge results go to `eval/results/judge/`.

## R13. Fallback judge (only if Jev is unavailable)

A small open model served on the laptop, reading next-token probabilities of "yes" and "no".
Measured on the builder's M3 Pro (36 GB) with 60 real agent-step prompts averaging about 1,045
tokens, one request at a time:

| Runtime + model | Judgments / s | 74k steps | Notes |
|---|---|---|---|
| llama.cpp `llama-server` + Qwen3.5-0.8B (Q8_0, Apache-2.0) | 3.05 | about 6.7 h | Fits the 12 h budget |
| llama.cpp `llama-server` + Qwen3-1.7B (Q4_K_M, Apache-2.0) | 1.47 | about 14 h | Over budget unless prompts shrink below about 940 tokens |
| Qwen3-4B class | about 0.6 | about 34 h | Too slow |

**Measurement notes**:
- **Which runtime**: `llama-server`'s `/completion` (`n_probs`) gives full-precision log-probabilities
  and returns the same value for the same prompt. MLX rounds log-probabilities coarsely, and Ollama
  wraps the same engine.
- **Sending requests in parallel** added no speed (reading the prompt is the bottleneck), and it
  broke exact repeatability.
- **Not yet checked**: how accurate the judge is, and whether speed holds up over a long run
  (heat).

This route stays a fallback. It would need its own setup id, and it would be judged under the same
protocol.
