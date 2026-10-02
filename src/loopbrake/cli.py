"""The `loopbrake` command. Contract: specs/003-core-package/contracts/cli.md."""
import argparse
import os
import sys

import re
from pathlib import Path

from loopbrake import __version__, calibration, claude_code, codex, dashboard, otlp, records
from loopbrake.brake import Brake, replay
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
    stem = re.sub(r"[^A-Za-z0-9._-]", "-", Path(args.runs_file).stem)[:50]
    for r in runs:
        if not r.steps:
            continue
        step = _record_replay(r, cal, stem) if args.record else replay(r, cal)
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
    event = argv[1] if len(argv) > 1 else ""
    out = (codex.hook if event.startswith("codex-") else claude_code.hook)(event, text)
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


def _record_replay(run, cal, stem):
    """Replay one run through a recording brake, so the dashboard can show it (spec SC-007)."""
    rid = re.sub(r"[^A-Za-z0-9._-]", "-", run.run)[:128]
    b = Brake(f"replay-{stem}", f"replay-{stem}", rid, records.home(), cal)
    stop = None
    for s in run.steps:
        if b.step(s.action, s.observation, tokens=s.tokens, error=s.error).stop:
            stop = len(b.steps)
            break
    b.end("stopped" if stop else "finished")
    return stop


def _dashboard(args):
    if args.stop:
        print("Stopped the LoopBrake dashboard." if dashboard.stop() else "No LoopBrake dashboard is running.")
        return 0
    if args.background:
        info = dashboard.start_background(port=args.port, open_browser=not args.no_open, days=args.days)
        if info is None:
            return _fail("the dashboard didn't start; run loopbrake dashboard to see why", 1)
        print(f"LoopBrake dashboard: {info['url']}")
        print(("It's open in your browser. " if not args.no_open else "") + "It keeps running in the background, and only this "
              "computer can open it.")
        print("To stop it, run /loopbrake:dashboard stop in Claude Code, or loopbrake dashboard --stop in a terminal.")
        return 0
    try:
        dashboard.serve(port=args.port, open_browser=not args.no_open, days=args.days)
    except OSError as e:
        return _fail(f"port {args.port} is taken ({e.strerror}); pick another with --port", 2)
    return 0


def _export(args):
    s = otlp.settings()
    if not s["on"]:
        if not args.quiet:
            print("export is off; set LOOPBRAKE_EXPORT=otlp to turn it on")
        return 0
    where = otlp.host(s["traces"])
    if s["warning"] and not args.quiet:
        print(f"loopbrake: {s['warning']}", file=sys.stderr)
    r = otlp.test_connection() if args.test else otlp.export_pending()
    if r["ok"]:
        if not args.quiet:
            n = claude_code._n
            print(f"test span accepted by {where}" if args.test else
                  f"sent {n(r['tasks'], 'task')} ({n(r['spans'], 'span')}) to {where}" if r["tasks"] else "nothing new to send")
        return 0
    if not args.quiet:
        print(f"loopbrake: {otlp.problem(r, where)}", file=sys.stderr)
    return 1


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
    d = sub.add_parser("dashboard", help="open the local dashboard (only this computer can reach it)")
    d.add_argument("--port", type=int, default=0, help="a fixed port (default: any free one)")
    d.add_argument("--no-open", action="store_true", help="don't open a browser")
    d.add_argument("--days", type=int, help="read only the last D days of records")
    g4 = d.add_mutually_exclusive_group()
    g4.add_argument("--background", action="store_true", help="keep it running in the background and return at once (reuses one already running)")
    g4.add_argument("--stop", action="store_true", help="stop the dashboard running in the background")
    e = sub.add_parser("export", help="send finished tasks to your OpenTelemetry tools (needs LOOPBRAKE_EXPORT=otlp)")
    g3 = e.add_mutually_exclusive_group(required=True)
    g3.add_argument("--pending", action="store_true", help="send every finished task not sent yet")
    g3.add_argument("--test", action="store_true", help="send one test span")
    e.add_argument("--quiet", action="store_true", help="print nothing (used when it runs in the background)")
    sub.add_parser("statusline", help="one line for Claude Code's status line (reads its input from stdin)")
    r = sub.add_parser("replay", help="show where recorded runs would stop (writes nothing, unless --record)")
    r.add_argument("runs_file")
    r.add_argument("--record", action="store_true", help="write the replayed runs as records, for the dashboard")
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
        return {"calibrate": _calibrate, "status": _status, "feedback": _feedback, "replay": _replay, "statusline": _statusline, "agreement": _agreement, "dashboard": _dashboard, "export": _export}[args.command](args)
    except (OSError, ValueError, KeyError) as e:
        if os.environ.get("LOOPBRAKE_DEBUG") == "1":
            raise
        print(f"loopbrake: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
