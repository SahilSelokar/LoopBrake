# Contract: Normalized runs file

`eval/fetch.py` writes one file per group: `~/.loopbrake/data/runs/<group>.jsonl`. Its only reader
is `loopbrake.traces.read_runs`. Dataset-specific parsing never reaches the package
(constitution Principle V).

The file is UTF-8 JSON Lines, with one run per line and keys in this order:

```json
{"group": "swe-gpt5mini", "dataset": "swe-bench-verified", "task": "django__django-11099",
 "run": "django__django-11099", "success": true, "exit": "Submitted", "tokens_measured": true,
 "steps": [
   {"action": "bash {\"command\": \"grep -rn UsernameValidator django/\"}",
    "observation": "django/contrib/auth/validators.py:9:class ASCIIUsernameValidator(...", "error": false,
    "tokens": 4182}
 ]}
```

Rules, with data-model.md giving the full field semantics:

- `steps` is non-empty and in order. Every `tokens` value is an int ≥ 0.
- `error` is `true`, `false` or `null`.
- `action` is never empty. Tool calls are written as `<tool> <json args, sorted keys>`. A shell
  command extracted from text is written as `bash {"command": "<cmd>"}`, so both sources compare
  the same way.
- **Observation size**: observations are stored as the source gives them. The source cuts outputs
  over 10k characters to head and tail. No further truncation, because the `stale` signal needs
  the lines.
- **Validation**: a line that fails validation is skipped, and its reason is counted. Loading
  never raises because of one bad run.
- **Checksums**: the fetch step writes the sha256 of each file to
  `~/.loopbrake/data/runs/SHA256SUMS`. `results.md` records them.

**Source mapping** (fetch.py, per research R1/R3):

| Source | `task` | `success` | `action` | `observation` | `tokens` |
|---|---|---|---|---|---|
| mini-SWE-agent 2.x | instance id | `per_instance_details[iid].resolved` | `tool_calls[].function` | `role:"tool"` message; `error = returncode != 0` | `usage.input_tokens + output_tokens` |
| mini-SWE-agent 1.17 | instance id | same | command parsed with `info.config.agent.action_regex` | next user message; `error` from `<returncode>` | `extra.response.usage.prompt_tokens + completion_tokens` |
| τ-bench | `task_id` | `reward == 1` | `tool_calls[]` or the assistant text to the user | `role:"tool"` or the next `user` message; `error` = output starts with `Error` | estimated: chars/4 of prior messages + this one |
