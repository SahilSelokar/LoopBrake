"""Watch your own agent (spec 007): name what you watch, wrap its tools, mark each task.

    brake = loopbrake.watch("my-agent")

    @brake.tool
    def search(query): ...

    with brake.task():
        agent.run("fix the login bug")

A thin adapter (constitution Principle V): every decision is the brake's own rule. Teams of agents use
one watcher for the whole job, or one per agent. Each watcher tracks its open task per thread and per
async task, so tasks running at the same time, and a worker's task inside its manager's, never mix.
"""
import contextvars
import functools
import inspect
import json
import logging
import threading
import time
import warnings

from loopbrake import records
from loopbrake.agent_sdk import _text
from loopbrake.brake import start
from loopbrake.claude_code import _n, plain_stop

log = logging.getLogger("loopbrake")  # silent unless the app turns logging on (NullHandler in __init__)
NEXT_STEP = ' If it wasn\'t stuck, run "loopbrake feedback last --mistaken".'
NOT_RUN = "not run: LoopBrake stopped the task before this call"


class Stopped(Exception):
    """Raised by a wrapped tool once its task is stopped. `str(e)` is the reason, in plain words;
    `e.name` is the watcher that stopped it."""

    def __init__(self, reason, name):
        super().__init__(reason)
        self.name = name


def watch(name, *, home=None):
    """A watcher: LoopBrake watches every task under `name`, with its own limit, set by
    `loopbrake calibrate --project <name>` once it has watched enough good tasks."""
    return Watcher(name, home)


class Watcher:
    def __init__(self, name, home=None):
        if not records.valid_project(name):
            raise ValueError(f"watcher names may use letters, digits, '.', '_' and '-' (got {name!r})")
        self.name, self.home, self._told = name, home, False
        self._open = contextvars.ContextVar(f"loopbrake:{name}", default=None)

    def task(self):
        """One task: `with watcher.task():`, or `async with watcher.task():`."""
        return Task(self)

    def tool(self, fn=None, *, name=None):
        """Wraps a tool so each call counts as one action: `@watcher.tool`, or `watcher.tool(fn)`."""
        if fn is None:
            return lambda f: self.tool(f, name=name)
        label = name or getattr(fn, "__name__", "tool")
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            sig = None

        def action(args, kwargs):
            try:
                given = dict(sig.bind_partial(*args, **kwargs).arguments)
                given.pop("self", None)
            except (AttributeError, TypeError):
                given = {"args": args, "kwargs": kwargs}
            return f"{label} {json.dumps(given, sort_keys=True, ensure_ascii=False, default=str)}"

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def run_async(*args, **kwargs):
                task = self._task(label)
                if task is None:
                    return await fn(*args, **kwargs)
                act, t0 = task._admit(action(args, kwargs), label), time.monotonic()
                try:
                    out = await fn(*args, **kwargs)
                except BaseException as e:
                    task._done(act, label, repr(e), True, t0)
                    raise
                task._done(act, label, out, False, t0)
                return out
            return run_async

        @functools.wraps(fn)
        def run(*args, **kwargs):
            task = self._task(label)
            if task is None:
                return fn(*args, **kwargs)
            act, t0 = task._admit(action(args, kwargs), label), time.monotonic()
            try:
                out = fn(*args, **kwargs)
            except BaseException as e:
                task._done(act, label, repr(e), True, t0)
                raise
            task._done(act, label, out, False, t0)
            return out
        return run

    def _task(self, label):
        task = self._open.get()
        if task is None and not self._told:
            self._told = True
            warnings.warn(f"loopbrake: {label} was called outside a task of {self.name!r}, so it isn't counted; "
                          "run the agent's work inside `with watcher.task():`", RuntimeWarning, stacklevel=3)
        return task if task is not None and task.brake is not None else None


class Task:
    """One task of a watcher. `stopped` and `reason` say whether LoopBrake stopped it, and why."""

    def __init__(self, watcher):
        self.watcher, self.brake, self._lock = watcher, None, threading.Lock()
        self._pending, self._refused, self._token = 0, None, None

    def __enter__(self):
        try:
            self.brake = start(self.watcher.name, home=self.watcher.home)
        except Exception as e:  # LoopBrake's own problem: the agent runs unwatched (constitution, failing safely)
            warnings.warn(f"loopbrake: couldn't start a task ({e!r}); this one isn't watched", RuntimeWarning, stacklevel=2)
        self._token = self.watcher._open.set(self)
        return self

    def __exit__(self, kind, err, tb):
        self.watcher._open.reset(self._token)
        b = self.brake
        if b is not None:
            with self._lock:
                if self._refused and not b.stopped:
                    b.step(self._refused[0], NOT_RUN, tool=self._refused[1])
            status = "stopped" if b.stopped else "interrupted" if kind else "finished"
            b.end(status)
            log.info("%s: task %s after %s", self.watcher.name, status, _n(len(b.steps), "tool call"))
        return False

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, kind, err, tb):
        return self.__exit__(kind, err, tb)

    @property
    def stopped(self):
        return self.brake is not None and (self.brake.stopped or self._refused is not None)

    @property
    def reason(self):
        b = self.brake
        if not self.stopped:
            return ""
        cal = b.calibration or {}
        step = b.stop_step if b.stopped else b.stop_line + 1  # a refusal still waiting for calls on their way
        return plain_stop(step, b.stop_line, cal.get("n"), cal.get("alpha"), b.reason, NEXT_STEP)

    def _admit(self, act, label):
        """Before a call: raise Stopped if it would take the task past its limit, counting the calls
        already on their way; otherwise count it as on its way. The call past the limit never runs."""
        b = self.brake
        with self._lock:
            if not self.stopped and not b.would_stop(self._pending + 1):
                self._pending += 1
                return act
            first = not self.stopped
            if first:
                if self._pending:
                    self._refused = (act, label)  # recorded once the calls on their way are done
                else:
                    b.step(act, NOT_RUN, tool=label)  # the brake records its stop at this call
        reason = self.reason
        if first:
            log.warning("%s: stopped a task at %s. %s", self.watcher.name, label, reason)
        else:
            log.debug("%s: refused %s: the task is already stopped", self.watcher.name, label)
        raise Stopped(reason, self.watcher.name)

    def _done(self, act, label, out, failed, t0):
        b = self.brake
        with self._lock:
            self._pending -= 1
            b.step(act, _text(out)[:4000], tool=label, error=failed, duration_ms=int((time.monotonic() - t0) * 1000))
            if self._refused and not self._pending and not b.stopped:
                b.step(self._refused[0], NOT_RUN, tool=self._refused[1])
