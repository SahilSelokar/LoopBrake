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
    def __init__(self, project, session, run, home, calibration, record=True, unit="runs", traceparent=None, extra=None,
                 asks=False):
        self.project, self.session, self.run, self.home, self.unit = project, session, run, home, unit
        self.calibration = calibration
        line = calibration.get("stop_line") if calibration and not calibration.get("watch_only") else None
        self.stop_line = line  # the calibrated line; `line` is the one in force (specs/008)
        self.watch_only = line is None
        self.steps, self.stopped, self.reason, self.ended, self.tokens = [], False, "", False, None
        self.stop_step = None  # the step at which it stopped
        # Asking before stopping (specs/008, constitution 2.7.0): with `asks`, the run never stops on its own;
        # the adapter asks the person at the line, and only a denied question stops it.
        self.asks, self.stop_by, self.allowed_point = asks, None, None
        self._question = None  # (ask_point, held call ids, reason) while a question waits for its answer
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
    def from_events(cls, project, session, home, events, unit="runs", asks=False):
        """Pick up an open run from its logged events (its run_start first), in a new process.

        Writes no second run_start. Logged steps come back as their action excerpts: the `steps`
        rule only counts them, so the decision is exactly the one a single brake would make. Questions
        and answers come back too, so the line in force is the one a single brake would use.
        """
        start, rest = events[0], events[1:]
        b = cls(project, session, start["run"], home, start.get("calibration"), record=False, unit=unit, asks=asks)
        b._writer.on = True
        logged = [e for e in rest if e.get("event") == "step"]
        b.steps = [Step(e.get("action_excerpt") or "", "", None, 0) for e in logged]
        known = [e["tokens"] for e in logged if e.get("tokens") is not None]
        b.tokens = sum(known) if known else None
        for e in rest:
            kind = e.get("event")
            if kind == "ask":
                if b._question is None or b._question[0] != e.get("ask_point"):
                    b._question = (e.get("ask_point"), set(), e.get("reason", ""))
                b._question[1].add(e.get("call_id"))
            elif kind == "answer" and b._question is not None:
                if e.get("verdict") == "allowed":
                    b.allowed_point = b._question[0]
                b._question = None
        stop = next((e for e in rest if e.get("event") == "stop"), None)
        if stop:
            b.stopped, b.reason, b.stop_step, b.stop_by = True, stop.get("reason", ""), stop.get("step"), stop.get("by")
        return b

    # ---- public ----

    def step(self, action, result="", *, tool=None, tokens=None, error=None, call_id=None, duration_ms=None):
        """Report one step. Returns a Decision; once it says stop, it keeps saying stop."""
        try:
            return self._step(action, result, tool, tokens, error, call_id, duration_ms)
        except Exception as e:  # never hurt the host agent (spec FR-005)
            self._fail(e)
            return Decision(self.stopped, len(self.steps), self.reason, self.watch_only)

    @property
    def line(self):
        """The line in force: the calibrated one, or 2t - 1 after the person let the run go on at ask point t
        (constitution 2.7.0). The score compared with it is unchanged."""
        if self.stop_line is None:
            return None
        return 2 * self.allowed_point - 1 if self.allowed_point else self.stop_line

    @property
    def open_question(self):
        """(ask_point, held call ids) while a question waits for its answer, else None."""
        return self._question and self._question[:2]

    def would_stop(self, more):
        """Whether `more` further steps would take this run past its stop line, by the same certified
        rule. Lets an adapter refuse calls that would only run after the stop (parallel calls already
        on their way), without a rule of its own (constitution Principle V)."""
        steps = self.steps + [Step("", "", None, 0)] * more
        return self.stopped or (bool(steps) and _decide(steps, self.line))

    def ask(self, call_id=None, pending=0):
        """Whether to hold the next call and ask the person (specs/008). `pending`: calls already let
        through that haven't finished, so a batch can't slip past the line unasked.

        Returns the reason to ask with, or None to let the call go. While a question is open, every
        call repeats it (research R5). Any internal error means "don't ask", never a block."""
        try:
            if self.stopped or self.line is None:
                return None
            held = len(self.steps) + 1 + pending
            if self._question is None:
                if not self.would_stop(1 + pending):
                    return None
                self._question = (held, set(), self._explain(held, "asked"))
            point, calls, reason = self._question
            calls.add(call_id)
            self._record("ask", step=held, ask_point=point, stop_line=self.line, reason=reason, call_id=call_id)
            return reason
        except Exception as e:
            self._fail(e)
            return None

    def answer(self, verdict, call_id=None):
        """What came of the open question: "allowed" (a held call ran) or "denied" (the run ended
        with none run). A denied question stops the run, by the person. No open question: nothing."""
        try:
            if self._question is None or verdict not in ("allowed", "denied"):
                return
            point, _, reason = self._question
            line = self.line
            self._question = None
            self._record("answer", ask_point=point, verdict=verdict, call_id=call_id)
            if verdict == "allowed":
                self.allowed_point = point
                return
            self.stopped, self.stop_step, self.stop_by, self.reason = True, len(self.steps), "person", reason
            self._record("stop", step=self.stop_step, stop_line=line, reason=reason, by="person")
            if self._writer.on:
                otlp.spawn_pending(self.home)
        except Exception as e:
            self._fail(e)

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
        if self.asks:  # only the person's answer stops a run that asks
            return Decision(False, t, "", self.watch_only)
        if _decide(self.steps, self.line):
            self.stopped, self.stop_step = True, t
            self.reason = self._explain(t)
            self._record("stop", step=t, stop_line=self.stop_line, reason=self.reason, **ref)
            if self._writer.on:  # final at its stop: the agent may never end it (research R7)
                otlp.spawn_pending(self.home)
            return Decision(True, t, self.reason, False)
        return Decision(False, t, "", self.watch_only)

    def _explain(self, t, verb="stopped"):
        cal = self.calibration or {}
        reason = f"{verb} at step {t}: past the stop line of {self.line} steps"
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
