"""Write the task text of every run, for the judge to read (research R5 of specs/002-progress-judge).

Reads the raw files eval/fetch.py already downloaded; no network. Phase 1's runs files stay untouched.
Usage: uv run python eval/tasks.py [--data DIR]
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

from loopbrake.traces import read_runs


def _load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fetch = _load("fetch")


def as_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # content blocks
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def group_tasks(group, data):
    """{task id: task text} for one group, straight from the raw files."""
    source, name, _, _ = fetch.GROUPS[group]
    raw = data / "raw" / name
    tasks = {}
    if source == "tau":
        for entry in json.loads((raw / f"{name}.json").read_text()):
            first_user = next((m for m in entry["traj"] if m.get("role") == "user"), None)
            tasks.setdefault(str(entry["task_id"]), as_text(first_user["content"]) if first_user else "")
        return tasks
    for path in sorted(raw.glob("*.traj.json")):
        traj = json.loads(path.read_text())
        user = next((m for m in traj["messages"] if m.get("role") == "user"), None)  # the instance prompt
        tasks[traj["instance_id"]] = as_text(user["content"]) if user else ""
    return tasks


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=fetch.DATA)
    args = ap.parse_args(argv)
    out_dir = args.data / "tasks"
    out_dir.mkdir(parents=True, exist_ok=True)
    ok = True
    for group in fetch.GROUPS:
        try:
            tasks = group_tasks(group, args.data)
        except FileNotFoundError as e:
            print(f"{group}: raw file missing ({e.filename}); run eval/fetch.py first", file=sys.stderr)
            ok = False
            continue
        runs, _ = read_runs(args.data / "runs" / f"{group}.jsonl")
        missing = sorted({r.task for r in runs if not tasks.get(r.task)})
        with open(out_dir / f"{group}.jsonl", "w", encoding="utf-8") as f:
            for task in sorted(tasks):
                f.write(json.dumps({"task": task, "text": tasks[task]}, ensure_ascii=False) + "\n")
        print(f"{group:22} tasks {len(tasks):4}" + (f"  MISSING TEXT for {len(missing)} tasks" if missing else ""))
        ok &= not missing
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
