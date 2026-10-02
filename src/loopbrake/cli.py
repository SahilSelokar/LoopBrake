"""The `loopbrake` command. Contract: specs/003-core-package/contracts/cli.md."""
import argparse
import os
import sys

from loopbrake import __version__, calibration, claude_code, records
from loopbrake.brake import replay
from loopbrake.traces import read_runs


def _fail(message, code=2):
    print(f"loopbrake: {message}", file=sys.stderr)
    return code


def _calibrate(args):
    if args.claude_code and (args.source or args.project):
        return _fail("--claude-code takes no source and no --project: both come from the current folder")
    if not args.claude_code and not args.source:
        return _fail("give a runs file or a Claude Code project folder, or use --claude-code")
    if args.claude_code:  # what Claude Code users read: plain words (contracts/cli.md)
        print(claude_code.calibrate_message(claude_code.calibrate_claude_code(alpha=args.alpha)))
        return 0
    rec = calibration.calibrate(args.source, project=args.project or "default", alpha=args.alpha)
    if rec["watch_only"]:
        more = calibration.runs_needed(args.alpha, rec["source"].get("mistakes_counted", 0)) - rec["n"]
        print(f"watch-only: {rec['n']} successful runs found; need {more} more for α {args.alpha:.0%}")
    else:
        print(f"stop line: {rec['stop_line']} steps (from {rec['n']} successful runs, k = {rec['k']}, α {args.alpha:.0%})")
    print(f"saved: {calibration.path(rec['project'], records.home())}")
    return 0


def _status(args):
    h = records.home()
    if args.claude_code and args.project:
        return _fail("--claude-code and --project can't be used together")
    if args.claude_code:
        project = claude_code.project_name(claude_code.history_folder().name)
        print(claude_code.status_message(calibration.load(project, h), records.status(h, project)))
        return 0
    projects = [args.project] if args.project else sorted(p.stem for p in (h / "calibration").glob("*.json")) or ["default"]
    for project in projects:
        rec = calibration.load(project, h)
        unit = "turns" if rec and rec["source"].get("kind") == "claude-code" else "runs"
        if rec is None:
            line = "no calibration (watch-only)"
        elif rec["watch_only"]:
            needed = calibration.runs_needed(rec["alpha"], rec["source"].get("mistakes_counted", 0))
            line = f"watch-only ({rec['n']} successful {unit}; {needed} needed)"
        else:
            line = f"stop line: {rec['stop_line']} steps (from {rec['n']} successful {unit}, α {rec['alpha']:.0%}, {rec['source']['kind']}, {rec['created']})"
        st = records.status(h, project)
        print(f"project {project}: {line}")
        print(f"  {unit} watched: {st['watched']} (of {st['runs']} recorded)")
        print(f"  {unit} stopped: {st['stopped']}")
        print(f"  mistaken stops: {st['mistaken']} of an allowance of {st['allowance']:.1f}")
    return 0


def _feedback(args):
    verdict = "mistaken_stop" if args.mistaken else "exclude"
    h = records.home()
    if args.run == "last":  # /loopbrake:mistake and /loopbrake:exclude: plain words (contracts/cli.md)
        return _feedback_last(h, args.mistaken, verdict)
    try:
        records.add_feedback(h, args.run, verdict)
    except (LookupError, ValueError) as e:
        return _fail(str(e).strip("'\""), 1)
    print(f"recorded: {args.run} {'marked as a mistaken stop' if args.mistaken else 'left out of future calibration'}")
    return 0


def _feedback_last(h, mistaken, verdict):
    found = records.last_run(h, "stop") if mistaken else records.last_run(h, "run_end", min_steps=1)
    if found is None:
        return _fail("there's no stop to mark yet: LoopBrake hasn't stopped anything." if mistaken
                     else "there's no finished task to leave out yet.", 1)
    start, e = found
    try:
        records.add_feedback(h, start["run"], verdict)
    except ValueError:
        return _fail("that one is already marked.", 1)
    if mistaken:
        print(f"Done: the stop after {e.get('step')} tool calls is marked as a mistake. The next /loopbrake:calibrate "
              "will count that task as a long good one, so the stop line can only go up.")
    else:
        print(f"Done: your last finished task ({claude_code._n(e.get('steps'), 'tool call')}) will be left out "
              "the next time you run /loopbrake:calibrate.")
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


def _hook(argv):
    """`loopbrake hook <event>`: always exits 0, whatever goes wrong (contracts/hooks.md)."""
    try:
        text = sys.stdin.read()
    except Exception:
        text = ""
    out = claude_code.hook(argv[1] if len(argv) > 1 else "", text)
    if out:
        print(out)
    return 0


def _statusline(args):
    try:
        text = sys.stdin.read()
    except Exception:
        text = ""
    print(claude_code.statusline(text))
    return 0


def _agreement(args):
    if not args.claude_code:
        return _fail("agreement needs --claude-code")
    lines, higher = claude_code.agreement()
    print("\n".join(lines))
    return 1 if higher else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["hook"]:  # before argparse, which exits 2 on bad arguments: a hook must never do that
        return _hook(argv)
    ap = argparse.ArgumentParser(prog="loopbrake", description="Stops stuck AI agent runs, with a guaranteed limit on stopping good ones.")
    ap.add_argument("--version", action="store_true", help="print the version")
    sub = ap.add_subparsers(dest="command")
    c = sub.add_parser("calibrate", help="set a stop line from past runs")
    c.add_argument("source", nargs="?", help="a runs file, or a Claude Code project folder")
    c.add_argument("--project", help="project name (default: default)")
    c.add_argument("--claude-code", action="store_true", help="the Claude Code project of the current folder, from its own history")
    c.add_argument("--alpha", type=float, default=0.05, help="highest share of good runs you accept stopping (default 0.05)")
    s = sub.add_parser("status", help="stop line, runs watched and stopped, mistaken stops")
    s.add_argument("--project")
    s.add_argument("--claude-code", action="store_true", help="the Claude Code project of the current folder")
    f = sub.add_parser("feedback", help="mark a stop as a mistake, or leave a run out of calibration")
    f.add_argument("run", help="a run id, or 'last': the latest stop (--mistaken) or finished turn (--exclude)")
    g = f.add_mutually_exclusive_group(required=True)
    g.add_argument("--mistaken", action="store_true")
    g.add_argument("--exclude", action="store_true")
    sub.add_parser("hook", help="Claude Code hook entry point (reads the event from stdin)").add_argument("event", choices=claude_code.EVENTS)
    sub.add_parser("agreement", help="check live step counts against calibration's, turn by turn (writes nothing)").add_argument(
        "--claude-code", action="store_true", help="the Claude Code project of the current folder")
    sub.add_parser("statusline", help="one line for Claude Code's status line (reads its input from stdin)")
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
        return {"calibrate": _calibrate, "status": _status, "feedback": _feedback, "replay": _replay, "statusline": _statusline, "agreement": _agreement}[args.command](args)
    except (OSError, ValueError, KeyError) as e:
        if os.environ.get("LOOPBRAKE_DEBUG") == "1":
            raise
        print(f"loopbrake: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
