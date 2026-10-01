"""The `loopbrake` command. Contract: specs/003-core-package/contracts/cli.md."""
import argparse
import os
import sys

from loopbrake import __version__, calibration, records
from loopbrake.brake import replay
from loopbrake.traces import read_runs


def _calibrate(args):
    rec = calibration.calibrate(args.source, project=args.project, alpha=args.alpha)
    if rec["watch_only"]:
        more = calibration.runs_needed(args.alpha) - rec["n"]
        print(f"watch-only: {rec['n']} successful runs found; need {more} more for α {args.alpha:.0%}")
    else:
        print(f"stop line: {rec['stop_line']} steps (from {rec['n']} successful runs, k = {rec['k']}, α {args.alpha:.0%})")
    print(f"saved: {calibration.path(args.project, records.home())}")
    return 0


def _status(args):
    h = records.home()
    projects = [args.project] if args.project else sorted(p.stem for p in (h / "calibration").glob("*.json")) or ["default"]
    for project in projects:
        rec = calibration.load(project, h)
        if rec is None:
            line = "no calibration (watch-only)"
        elif rec["watch_only"]:
            line = f"watch-only (only {rec['n']} successful runs)"
        else:
            line = f"stop line: {rec['stop_line']} steps (from {rec['n']} successful runs, α {rec['alpha']:.0%}, {rec['source']['kind']}, {rec['created']})"
        st = records.status(h, project)
        print(f"project {project}: {line}")
        print(f"  runs watched: {st['watched']} (of {st['runs']} recorded)")
        print(f"  runs stopped: {st['stopped']}")
        print(f"  mistaken stops: {st['mistaken']} of an allowance of {st['allowance']:.1f}")
    return 0


def _feedback(args):
    verdict = "mistaken_stop" if args.mistaken else "exclude"
    try:
        records.add_feedback(records.home(), args.run, verdict)
    except LookupError as e:
        print(f"loopbrake: {e}", file=sys.stderr)
        return 1
    print(f"recorded: {args.run} {'marked as a mistaken stop' if args.mistaken else 'left out of future calibration'}")
    return 0


def _replay(args):
    if args.stop_line is not None:
        cal = {"stop_line": args.stop_line, "watch_only": False}
    else:
        cal = calibration.load(args.project, records.home())
        if cal is None or cal["watch_only"]:
            print(f"loopbrake: project {args.project} has no stop line yet; calibrate it first", file=sys.stderr)
            return 2
    runs, _ = read_runs(args.runs_file)
    stopped_ok = stopped_failed = 0
    for r in runs:
        if not r.steps:
            continue
        step = replay(r, cal)
        if step is not None:
            stopped_ok += r.success
            stopped_failed += not r.success
        print(f"{r.run}\t{'-' if step is None else f'stop at {step}'}\t{'success' if r.success else 'failed'}")
    print(f"runs {sum(1 for r in runs if r.steps)}, stopped {stopped_ok + stopped_failed} ({stopped_ok} successful, {stopped_failed} failed)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="loopbrake", description="Stops stuck AI agent runs, with a guaranteed limit on stopping good ones.")
    ap.add_argument("--version", action="store_true", help="print the version")
    sub = ap.add_subparsers(dest="command")
    c = sub.add_parser("calibrate", help="set a stop line from past runs")
    c.add_argument("source", help="a runs file, or a Claude Code project folder")
    c.add_argument("--project", default="default")
    c.add_argument("--alpha", type=float, default=0.05, help="highest share of good runs you accept stopping (default 0.05)")
    s = sub.add_parser("status", help="stop line, runs watched and stopped, mistaken stops")
    s.add_argument("--project")
    f = sub.add_parser("feedback", help="mark a stop as a mistake, or leave a run out of calibration")
    f.add_argument("run")
    g = f.add_mutually_exclusive_group(required=True)
    g.add_argument("--mistaken", action="store_true")
    g.add_argument("--exclude", action="store_true")
    r = sub.add_parser("replay", help="show where recorded runs would stop (writes nothing)")
    r.add_argument("runs_file")
    g2 = r.add_mutually_exclusive_group(required=True)
    g2.add_argument("--project")
    g2.add_argument("--stop-line", type=int)
    args = ap.parse_args(argv)
    if args.version:
        print(f"loopbrake {__version__}")
        return 0
    if not args.command:
        ap.print_help()
        return 0
    try:
        return {"calibrate": _calibrate, "status": _status, "feedback": _feedback, "replay": _replay}[args.command](args)
    except (OSError, ValueError, KeyError) as e:
        if os.environ.get("LOOPBRAKE_DEBUG") == "1":
            raise
        print(f"loopbrake: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
