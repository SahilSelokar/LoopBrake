"""A bookshop run by two AI agents, each with its own LoopBrake brake (one limit per agent).

The desk agent talks to the customer and hands searches to the researcher agent. The researcher's calls
count only in its own tasks, never in the desk's. Nothing here is scripted to loop: the search is a plain
keyword search, the stock system is sometimes busy, and some requests have no matching book.

    python demo/bookshop.py --requests 25      # first runs: LoopBrake only watches
    loopbrake calibrate --project bookshop-desk
    loopbrake calibrate --project bookshop-researcher
    python demo/bookshop.py --requests 25      # from now on, stuck tasks get stopped

The model: any OpenAI-compatible chat endpoint (LOOPBRAKE_DEMO_URL, LOOPBRAKE_DEMO_MODEL, and
OPENAI_API_KEY if it needs one). By default a local llama.cpp server on port 8091.
"""
import argparse
import json
import math
import os
import random
import re
import urllib.request

import loopbrake

desk = loopbrake.watch("bookshop-desk")
researcher = loopbrake.watch("bookshop-researcher")

# ---- the shop: made-up books ----

R = random.Random(7)
GENRES = ["mystery", "romance", "science fiction", "fantasy", "history", "cooking", "travel", "children's"]
PLACES = ["Kyoto", "Lisbon", "Mars", "Lagos", "Oslo", "Lima", "Cairo", "Seoul", "Venice", "Nairobi"]
ADJ = ["Silent", "Golden", "Last", "Hidden", "Paper", "Midnight", "Salt", "Glass", "Winter", "Lantern"]
NOUN = ["Harbor", "Garden", "Letter", "Station", "Recipe", "Map", "Orchard", "Bridge", "Clock", "Market"]
FIRST = ["Mira", "Tomas", "Aiko", "Kwame", "Lena", "Rafael", "Noor", "Ines", "Jonah", "Sade"]
LAST = ["Okafor", "Lindqvist", "Tanaka", "Moreau", "Alvarez", "Haddad", "Kowalski", "Mensah", "Rossi", "Park"]
BOOKS = {
    f"B{i:03d}": {"id": f"B{i:03d}", "title": f"The {R.choice(ADJ)} {R.choice(NOUN)}",
                  "author": f"{R.choice(FIRST)} {R.choice(LAST)}", "genre": R.choice(GENRES),
                  "setting": R.choice(PLACES), "price": round(R.uniform(6, 38), 2), "copies": R.choice([0, 0, 1, 2, 3, 5])}
    for i in range(1, 151)
}
STOP = {"a", "an", "and", "the", "in", "on", "of", "for", "set", "book", "books", "about", "by", "with", "any"}


# ---- the researcher's tools ----

@researcher.tool
def search_catalog(query: str, page: int = 1) -> str:
    words = [w for w in re.findall(r"[a-z']+", query.lower()) if w not in STOP and len(w) > 2]
    hits = [b for b in BOOKS.values()
            if all(w in f"{b['title']} {b['author']} {b['genre']} {b['setting']}".lower() for w in words)]
    pages = max(1, math.ceil(len(hits) / 5))
    if not hits:
        return "No books match."
    shown = hits[(page - 1) * 5:page * 5]
    rows = "\n".join(f"{b['id']}: {b['title']} by {b['author']} ({b['genre']}, {b['setting']})" for b in shown)
    return f"Page {page} of {pages}, {len(hits)} books:\n{rows}"


@researcher.tool
def book_details(book_id: str) -> str:
    b = BOOKS.get(book_id.strip().upper())
    return json.dumps({k: v for k, v in b.items() if k != "copies"}) if b else f"No book {book_id}."


@researcher.tool
def check_stock(book_id: str) -> str:
    if random.random() < 0.3:
        return "The stock system is busy. Try again."
    b = BOOKS.get(book_id.strip().upper())
    return f"{b['copies']} in stock." if b else f"No book {book_id}."


RESEARCHER = ("You find books in a small shop's catalog. search_catalog is a plain keyword search (every word must "
              "match the title, author, genre or place; 5 results per page). book_details gives the price. "
              "check_stock is sometimes busy. Reply with matching books (id, title, price, in stock or not), or "
              "say plainly that there are none. Be brief.")
RESEARCHER_TOOLS = {f.__name__: f for f in (search_catalog, book_details, check_stock)}


# ---- the desk's tools ----

SEEN = []  # (agent, actions, stopped) for each task of the current request


def note(agent, task):
    SEEN.append((agent, len(task.brake.steps) if task.brake else 0, task.stopped))


@desk.tool
def ask_researcher(request: str) -> str:
    with researcher.task() as t:  # the researcher's work is its own task, with its own limit
        try:
            return run_agent(researcher, RESEARCHER, RESEARCHER_TOOLS, request)
        finally:
            note("researcher", t)


@desk.tool
def place_hold(book_id: str, customer: str) -> str:
    b = BOOKS.get(book_id.strip().upper())
    return f"Held {b['title']} for {customer}." if b and b["copies"] else f"Can't hold {book_id}: not in stock."


DESK = ("You are the front desk of a small bookshop. You can't search the catalog yourself: ask the researcher "
        "with ask_researcher. If the customer asks for a hold, use place_hold with the book id. When you're done, "
        "answer the customer in one or two sentences without calling tools.")
DESK_TOOLS = {f.__name__: f for f in (ask_researcher, place_hold)}

SCHEMAS = {
    "search_catalog": {"query": {"type": "string"}, "page": {"type": "integer"}},
    "book_details": {"book_id": {"type": "string"}},
    "check_stock": {"book_id": {"type": "string"}},
    "ask_researcher": {"request": {"type": "string"}},
    "place_hold": {"book_id": {"type": "string"}, "customer": {"type": "string"}},
}


# ---- one agent: the model calls tools until it answers ----

def chat(messages, tools):
    body = {"model": os.environ.get("LOOPBRAKE_DEMO_MODEL", "qwen3-4b"), "messages": messages, "tools": [
        {"type": "function", "function": {"name": name, "parameters": {"type": "object", "properties": SCHEMAS[name],
                                                                          "required": [next(iter(SCHEMAS[name]))]}}}
        for name in tools]}
    req = urllib.request.Request(os.environ.get("LOOPBRAKE_DEMO_URL", "http://127.0.0.1:8091/v1") + "/chat/completions",
                                 json.dumps(body).encode(), {"Content-Type": "application/json"})
    if os.environ.get("OPENAI_API_KEY"):
        req.add_header("Authorization", "Bearer " + os.environ["OPENAI_API_KEY"])
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)["choices"][0]["message"]


def run_agent(watcher, system, tools, request, max_turns=60):
    messages = [{"role": "system", "content": system}, {"role": "user", "content": request}]
    for _ in range(max_turns):
        msg = chat(messages, tools)
        messages.append({k: v for k, v in msg.items() if k in ("role", "content", "tool_calls")})
        if not msg.get("tool_calls"):
            return msg.get("content") or ""
        for call in msg["tool_calls"]:
            try:
                out = tools[call["function"]["name"]](**json.loads(call["function"]["arguments"] or "{}"))
            except loopbrake.Stopped as e:
                if e.name == watcher.name:
                    raise  # this agent's own task was stopped: it ends here
                out = f"Error: {e}"  # a helper was stopped: tell this agent, which carries on
            except Exception as e:
                out = f"Error: {e}"
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": str(out)})
    return "(gave up)"


# ---- customers ----

def requests(n):
    rng, names, out = random.Random(11), ["Ana", "Bo", "Chen", "Dara", "Eli", "Femi", "Gus", "Hana"], []
    for i in range(n):
        b, who = rng.choice(list(BOOKS.values())), rng.choice(names)
        out.append([
            f"Hi, I'd like a {b['genre']} book set in {b['setting']}, under ${math.ceil(b['price']) + 3}. What do you have?",
            f"Do you have anything by {b['author']} in stock? Please hold one for {who}.",
            f"Is '{b['title']}' by {b['author']} in stock? If yes, hold it for {who}.",
            rng.choice([f"Do you have a poetry book set in {b['setting']}?",  # the shop has no poetry
                        f"I'm looking for a {b['genre']} book set in Reykjavik.",  # nor any book set in Reykjavik
                        f"Anything about whales by {b['author']}?"]),
        ][i % 4])
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--requests", type=int, default=25)
    a = p.parse_args()
    for i, text in enumerate(requests(a.requests), 1):
        SEEN.clear()
        try:
            with desk.task() as t:
                try:
                    answer = run_agent(desk, DESK, DESK_TOOLS, text)
                finally:
                    note("desk", t)
        except loopbrake.Stopped as e:
            answer = f"[desk stopped] {e}"
        except Exception as e:  # the model's server, for example
            answer = f"[error] {e!r}"
        tasks = ", ".join(f"{who} {n}{' STOPPED' if stopped else ''}" for who, n, stopped in SEEN)
        print(f"#{i:02d} {text}\n    actions: {tasks}\n    -> {' '.join(str(answer).split())[:300]}", flush=True)


if __name__ == "__main__":
    main()
