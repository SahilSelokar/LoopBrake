# Contract: Judge request and stored judgment

## Request to Jev (one per step)

```http
POST https://api.typesafe.ai/v1/systemone
Authorization: Bearer <TYPESAFE_API_KEY>        (never logged or stored)
Content-Type: application/json
```

```json
{
  "model": "jev-1.13.0",
  "state": {
    "task": "<first 1,500 chars of the task text>",
    "earlier_actions": ["<≤200 chars>", "<≤200 chars>", "<≤200 chars>"],
    "action": "<≤600 chars>",
    "result": "<first 1,200 chars>…<last 800 chars>"
  },
  "questions": {
    "progress": {
      "type": "noul",
      "instructions": "The latest action moved the agent closer to finishing its task.",
      "criteria": {
        "true": "It found information it did not have, changed something the task needs, or confirmed the work is done.",
        "false": "It repeated earlier work, hit an earlier error again, or got nothing useful."
      }
    },
    "kind": {
      "type": "choice",
      "instructions": "What kind of step was the latest action?",
      "criteria": {
        "found_new": "Found information it did not have before",
        "changed": "Changed files or settings the task needs",
        "verified": "Ran a check that confirms progress, such as a passing test",
        "talked": "Asked or answered the user a question",
        "finished": "Finished or submitted the task",
        "repeated": "Repeated or nearly repeated an earlier action",
        "same_error": "Hit an error it had already hit",
        "dead_end": "Got an empty, irrelevant or failed result"
      }
    }
  }
}
```

**State rules**:
- `earlier_actions` holds at most 3 items, oldest first. It is an empty list on step 1.
- Long text is shortened only by the limits shown above.
- The `…` character marks where text was cut.

**Response used**:
- `answers.progress.noul` becomes `progress`;
- `answers.kind.choice` and its `probabilities[choice]` become `kind` and `kind_p`;
- `usage.input_tokens + usage.output_tokens` becomes `tokens`.

A missing or out-of-range field makes the judgment `unreadable` (`progress = null`).

**Errors**:

| Response | Action |
|---|---|
| `401` | Stop the whole run, with the message "invalid TYPESAFE_API_KEY" |
| `422` | `unreadable` for that step; no retry |
| `429`, `529`, other 5xx, or a timeout | Retry after 1, 2, 4, 8, 16, 32 s (honouring `Retry-After` if given); then `service_error` |

## Stored judgment (one JSON line)

```json
{"key": "<sha256 hex>", "group": "swe-devstral", "run": "django__django-11099", "step": 7,
 "progress": 0.12, "kind": "repeated", "kind_p": 0.81, "status": "ok", "tokens": 912, "ms": 241}
```

- `key` is the sha256 of `json.dumps(body, sort_keys=True, ensure_ascii=False)`, where `body` is
  the request JSON above (no headers).
- The full field rules are in [data-model.md](../data-model.md).

## Pure scorer used by evaluation and, later, by the product

```python
from loopbrake.signals import judged

scorer = judged("judge", lam=0.9)       # also "judge_steps", "judge_max"
scores = scorer(steps, progress, kinds)   # progress: list[float | None]; kinds (optional): list[(kind, p) | None]; both same length as steps
# -> [(score, reason), ...]; reason names the judge's view, e.g. "judge: no progress in 4 of last 5 steps (repeated, 0.81)"
```

It is pure, it never looks ahead, and `None` keeps the score unchanged (see data-model.md).
