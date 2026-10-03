# Demo: a bookshop run by two agents, each with its own brake

A small, made-up bookshop where two AI agents work together:

- **desk** talks to the customer and can place a hold on a book;
- **researcher** searches the catalog, reads book details and checks stock.

Each agent has its own LoopBrake watcher, so each learns its own limit (one limit per agent). The desk
hands searches to the researcher, and the researcher's tool calls count only in the researcher's own
task, never in the desk's.

Nothing is scripted to loop. The search is a plain keyword search (every word must match), the stock
system is sometimes busy, and some customers ask for books the shop doesn't have. When an agent goes in
circles, that's the model's own doing.

## Run it

You need a model behind an OpenAI-compatible chat endpoint. By default the demo uses a local llama.cpp
server on port 8091 (any model with tool calling; we used Qwen3-4B-Instruct and Qwen3-1.7B). To use another one:

```bash
export LOOPBRAKE_DEMO_URL=https://api.openai.com/v1 LOOPBRAKE_DEMO_MODEL=gpt-5-mini OPENAI_API_KEY=...
```

It needs LoopBrake 0.5.0 or later (`pip install loopbrake`). From a clone of this repository:

```bash
uv run python demo/bookshop.py --requests 25        # first runs: LoopBrake only watches
uv run loopbrake calibrate --project bookshop-desk  # each agent learns its own limit
uv run loopbrake calibrate --project bookshop-researcher
uv run python demo/bookshop.py --requests 30        # now stuck tasks get stopped
uv run loopbrake dashboard                          # see every task, and why any was stopped
```

Each request prints how many tool calls each agent used, and whether LoopBrake stopped it. Small local
models sometimes say they placed a hold without calling the tool; the action counts show what really
ran.

Each agent's limit comes only from the tasks it was watched doing, so watch it doing its normal work
first. If a stop was wrong, `loopbrake feedback last --mistaken` makes the next limit higher.

## How the brakes are set up

```python
desk = loopbrake.watch("bookshop-desk")
researcher = loopbrake.watch("bookshop-researcher")

@researcher.tool
def search_catalog(query, page=1): ...

@desk.tool
def ask_researcher(request):
    with researcher.task():          # the researcher's own task, with its own limit
        return run_agent(researcher, ...)

with desk.task():                    # one customer request
    run_agent(desk, ...)
```

When a task goes past its limit, the next tool call doesn't run: it raises `loopbrake.Stopped` with the
reason. The demo's agent loop lets an agent's own stop end that agent's task, and hands a helper's stop
to the agent that asked for the help, which then tells the customer.
