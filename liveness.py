"""Liveness check for agents: does it ever finish, or is it stuck?"""
import json
from collections import Counter


def watch(steps, max_steps=20, repeat_limit=3):
    """Run an agent's steps. Returns (verdict, steps_taken).

    steps: iterable of (tool, args) pairs, one per agent step.
    verdict: "done" | "stuck" | "over_budget"
    """
    # ponytail: exact-match repeat counting. Misses loops whose args change a
    # little each time, and flags legit polling. Upgrade: ask a judge model
    # (Jev) "did this step make progress?" per step.
    seen = Counter()
    n = 0
    for n, (tool, args) in enumerate(steps, 1):
        if n > max_steps:
            return "over_budget", max_steps
        key = (tool, json.dumps(args, sort_keys=True))
        seen[key] += 1
        if seen[key] >= repeat_limit:
            return "stuck", n
    return "done", n


# --- demo agents (scripted, no LLM) ---

def healthy():
    yield "search", {"q": "flights to Goa"}
    yield "read", {"url": "result-1"}
    yield "book", {"flight": "6E-203"}


def looping():
    while True:  # never decides it's done
        yield "search", {"q": "flights to Goa"}
        yield "read", {"url": "result-1"}


def wandering():
    page = 0
    while True:  # something new every step, still never finishes
        page += 1
        yield "search", {"q": f"flights to Goa, page {page}"}


def traced(steps):
    for i, (tool, args) in enumerate(steps, 1):
        print(f"  step {i:>2}  {tool}({json.dumps(args)})")
        yield tool, args


if __name__ == "__main__":
    expected = {healthy: ("done", 3), looping: ("stuck", 5), wandering: ("over_budget", 20)}
    for agent, want in expected.items():
        print(f"\n{agent.__name__} agent")
        got = watch(traced(agent()))
        print(f"  -> {got[0].upper()} after {got[1]} steps")
        assert got == want, f"{agent.__name__}: expected {want}, got {got}"
    print("\nall checks passed")
