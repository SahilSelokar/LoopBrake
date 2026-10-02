"""The brake: one per run. Stops a run once it goes past the stop line set from your own past
successful runs, and says why. Contract: specs/003-core-package/contracts/python-api.md.

v1's stop rule is the calibrated step budget (constitution 2.2.0). The stuck signals only explain.
"""
import re
import uuid
import warnings
from typing import NamedTuple

from loopbrake import calibration, otlp, records
from loopbrake.signals import Step, method

EXCERPT = 200
_TRACEPARENT = re.compile(r"00-(?!0{32})[0-9a-f]{32}-(?!0{16})[0-9a-f]{16}-[0-9a-f]{2}")


def _traceparent(value):
    """A W3C trace context the agent passed (Claude Code sets TRACEPARENT when its tracing is on), or None."""
    return value if isinstance(value, str) and _TRACEPARENT.fullmatch(value) else None


class Decision(NamedTuple):
    stop: bool
    step: int
    reason: str
    watch_only: bool


def _decide(steps, stop_line):
    """The certified rule, unchanged from the experiments: stop when the `steps` score passes the line."""
    # ponytail: rescores every step so far (O(t)) to call the certified scorer literally; about 0.1 ms
    # at 250 steps. A running count is the upgrade, with tests/test_replay_data.py guarding agreement.
    return stop_line is not None and method("steps")(steps)[-1][0] > stop_line


class Brake:
    def __init__(self, project, session, run, home, calibration, record=True, unit="runs", traceparent=None, extra=None):
        self.project, self.session, self.run, self.home, self.unit = project, session, run, home, unit
        self.calibration = calibration
        line = calibration.get("stop_line") if calibration and not calibration.get("watch_only") else None
        self.stop_line = line
        self.watch_only = line is None
        self.steps, self.stopped, self.reason, self.ended, self.tokens = [], False, "", False, None
        self.stop_step = None  # the step at which it stopped
        self._warned = False
        self._writer = records.RunWriter(home / "runs" / f"{session}.jsonl")
        self._writer.on = record
        cal = calibration or {}
        trace = {"traceparent": t} if (t := _traceparent(traceparent)) else {}
        export = {"export": True} if record and otlp.begin(home) else {}  # only marked tasks are ever sent
        self._record("run_start", project=project, calibration={
            "method": "steps", "alpha": cal.get("alpha"), "n": cal.get("n"), "k": cal.get("k"),
            "stop_line": self.stop_line, "watch_only": self.watch_only}, **trace, **export, **(extra or {}))

    @classmethod
    def from_events(cls, project, session, home, events, unit="runs"):
        """Pick up an open run from its logged events (its run_start first), in a new process.

        Writes no second run_start. Logged steps come back as their action excerpts: the `steps`
        rule only counts them, so the decision is exactly the one a single brake would make.
        """
        start, rest = events[0], events[1:]
        b = cls(project, session, start["run"], home, start.get("calibration"), record=False, unit=unit)
        b._writer.on = True
        logged = [e for e in rest if e.get("event") == "step"]
        b.steps = [Step(e.get("action_excerpt") or "", "", None, 0) for e in logged]
        known = [e["tokens"] for e in logged if e.get("tokens") is not None]
        b.tokens = sum(known) if known else None
        stop = next((e for e in rest if e.get("event") == "stop"), None)
        if stop:
            b.stopped, b.reason, b.stop_step = True, stop.get("reason", ""), stop.get("step")
        return b

    # ---- public ----

    def step(self, action, result="", *, tool=None, tokens=None, error=None, call_id=None, duration_ms=None):
        """Report one step. Returns a Decision; once it says stop, it keeps saying stop."""
        try:
            return self._step(action, result, tool, tokens, error, call_id, duration_ms)
        except Exception as e:  # never hurt the host agent (spec FR-005)
            self._fail(e)
            return Decision(self.stopped, len(self.steps), self.reason, self.watch_only)

    def end(self, status=None):
        try:
            if self.ended:
                return
            self.ended = True
            status = status or ("stopped" if self.stopped else "finished")
            self._record("run_end", status=status, steps=len(self.steps), tokens=self.tokens)
            if not self.stopped and self._writer.on:  # a stopped run was sent at its stop
                otlp.spawn_pending(self.home)
        except Exception as e:
            self._fail(e)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.end("stopped" if self.stopped else "interrupted" if exc_type else "finished")
        return False

    # ---- internals ----

    def _step(self, action, result, tool, tokens, error, call_id=None, duration_ms=None):
        action = str(action)
        self.steps.append(Step(action, "" if result is None else str(result), error, int(tokens or 0)))
        if tokens is not None:
            self.tokens = (self.tokens or 0) + int(tokens)
        t = len(self.steps)
        ref = {"call_id": call_id} if call_id is not None else {}
        took = {"duration_ms": duration_ms} if isinstance(duration_ms, int) and not isinstance(duration_ms, bool) and duration_ms >= 0 else {}
        self._record("step", step=t, tool=tool, action_excerpt=action[:EXCERPT], tokens=tokens, error=error, **ref, **took)
        if self.stopped:
            return Decision(True, t, self.reason, False)
        if _decide(self.steps, self.stop_line):
            self.stopped, self.stop_step = True, t
            self.reason = self._explain(t)
            self._record("stop", step=t, stop_line=self.stop_line, reason=self.reason, **ref)
            if self._writer.on:  # final at its stop: the agent may never end it (research R7)
                otlp.spawn_pending(self.home)
            return Decision(True, t, self.reason, False)
        return Decision(False, t, "", self.watch_only)

    def _explain(self, t):
        cal = self.calibration or {}
        reason = f"stopped at step {t}: past the stop line of {self.stop_line} steps"
        if cal.get("n") and cal.get("alpha"):
            reason += f" set from your {cal['n']} past successful {self.unit} (α {cal['alpha']:.0%})"
        seen = method("max", lam=0.9)(self.steps)[-1][1]  # explains only; never decides
        return f"{reason}; {seen}" if seen else reason

    def _record(self, event, **fields):
        self._writer.write({"event": event, "session": self.session, "run": self.run} | fields)

    def _fail(self, e):
        self.stop_line, self.watch_only = None, True
        if not self._warned:
            self._warned = True
            warnings.warn(f"loopbrake: internal error ({e!r}); watching only for the rest of this run", RuntimeWarning, stacklevel=3)


def replay(run, calibration):
    """Feed a recorded run through a brake, writing no records. Returns the stop step, or None."""
    b = Brake("replay", "replay", run.run, records.home(), calibration, record=False)
    for s in run.steps:
        if b.step(s.action, s.observation, tokens=s.tokens, error=s.error).stop:
            return len(b.steps)
    return None


def start(project="default", *, session=None, run=None, home=None, unit="runs", traceparent=None, extra=None):
    """Start one run. Missing or damaged calibration means watch-only, never an exception.

    `extra`: adapter fields for the run_start record (Codex: turn_id, transcript, folder); readers ignore
    fields they don't know."""
    if not records.valid_project(project):
        raise ValueError(f"project names may use letters, digits, '.', '_' and '-' (got {project!r})")
    h = records.home(home)
    return Brake(project, session or uuid.uuid4().hex, run or uuid.uuid4().hex[:12], h, calibration.load(project, h),
                 unit=unit, traceparent=traceparent, extra=extra)
