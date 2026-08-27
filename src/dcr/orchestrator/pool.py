"""The worker processes, and surviving their deaths.

One process per community, started fresh and thrown away when the community
finishes. Not a pool of long-lived workers reused across communities, and the
reason is the failure the brief names in §39: a corrupt PDF, a malformed image,
a C parser that segfaults. A reused worker carries whatever the last community
did to it — leaked file handles, a wedged event loop, a browser that will not
close — into the next one. A fresh process carries nothing.

The cost is process startup, about a second of imports on a spawned
interpreter. Against a community that takes twenty minutes, it does not
register; against the class of bug it removes, it is free.

## What the parent guarantees

**A dead worker is one dead community.** The parent watches exit codes. A
non-zero exit with no `finished` event is a crash: the community is recorded
`FAILED_TECHNICALLY` with the exit code, and the slot goes to the next in the
queue. Nothing else in the run notices.

**A silent worker is not left running for ever.** Workers heartbeat. One that
has said nothing for the timeout is terminated and its community requeued, up to
the retry limit — because a hung process holds a worker slot that fifteen other
communities could use.

**Stopping is orderly.** `CANCEL ALL` stops starting new work, lets running
workers reach their next safe boundary, and waits. Only a worker that ignores
that is killed, and killing is the last resort because a `SIGKILL` in the middle
of a database write is exactly what the WAL and the per-community isolation are
there to make survivable, not something to do on purpose (brief §36).

## Windows

`spawn` throughout, on every platform, so the behaviour under test on Linux is
the behaviour in PyCharm on Windows. That means every argument crossing to a
child is pickled, the child re-imports everything, and nothing may rely on
inherited memory. Following the same rules on both removes an entire class of
"it worked in testing" (brief §42).
"""

from __future__ import annotations

import multiprocessing
import os
import queue as queue_mod
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from ..logging_setup import event, get_logger
from .events import EventKind, WorkerEvent

log = get_logger("orchestrator.pool")

#: How long a worker may say nothing before it is presumed hung. Generous: a
#: single large PDF, or one very slow archive request, can legitimately take
#: minutes with nothing to report.
DEFAULT_HEARTBEAT_TIMEOUT_S = 20 * 60

#: How long to wait for a worker to finish after being asked to stop, before
#: terminating it.
DEFAULT_SHUTDOWN_GRACE_S = 90.0


@dataclass
class WorkerHandle:
    """One running community, from the parent's side."""

    job_id: str
    name: str
    process: Any
    started_at: float
    last_seen: float
    payload: Mapping[str, Any] = field(default_factory=dict)
    finished_reported: bool = False
    summary: dict[str, Any] = field(default_factory=dict)
    stopping: bool = False

    @property
    def alive(self) -> bool:
        return bool(self.process is not None and self.process.is_alive())

    @property
    def pid(self) -> int | None:
        return getattr(self.process, "pid", None)

    @property
    def exitcode(self) -> int | None:
        return getattr(self.process, "exitcode", None)

    def elapsed_s(self, now: float | None = None) -> float:
        return (now or time.monotonic()) - self.started_at

    def silent_s(self, now: float | None = None) -> float:
        return (now or time.monotonic()) - self.last_seen


@dataclass
class WorkerExit:
    """How one worker ended, as the scheduler needs to hear it."""

    job_id: str
    name: str
    ok: bool
    crashed: bool
    exitcode: int | None
    summary: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    elapsed_s: float = 0.0


class WorkerPool:
    """Starts community workers, collects their events, and buries the dead."""

    def __init__(
        self,
        *,
        event_queue: Any = None,
        broker: Any = None,
        context: Any = None,
        heartbeat_timeout_s: float = DEFAULT_HEARTBEAT_TIMEOUT_S,
        shutdown_grace_s: float = DEFAULT_SHUTDOWN_GRACE_S,
        target: Callable[[Mapping[str, Any], Any, Any, Any], None] | None = None,
        clock: Any = None,
    ):
        # spawn everywhere, so Linux behaves as Windows does (brief §42).
        self._ctx = context or multiprocessing.get_context("spawn")
        self._manager = None
        if event_queue is None:
            event_queue = self._ctx.Queue(maxsize=10000)
        self.events: Any = event_queue
        self.results: Any = self._ctx.Queue(maxsize=1000)
        self.broker = broker
        self.heartbeat_timeout_s = float(heartbeat_timeout_s)
        self.shutdown_grace_s = float(shutdown_grace_s)
        self._clock = clock or time.monotonic
        self._target = target
        self.workers: dict[str, WorkerHandle] = {}
        self.started = 0
        self.crashed = 0
        self.hung = 0

    # -- lifecycle ---------------------------------------------------------
    @property
    def running(self) -> int:
        return sum(1 for handle in self.workers.values() if handle.alive)

    @property
    def busy_jobs(self) -> set[str]:
        return set(self.workers)

    def start(self, payload: Mapping[str, Any]) -> WorkerHandle:
        """Give one community to a fresh process."""
        job_id = str(payload["job_id"])
        if job_id in self.workers:
            raise RuntimeError(f"{job_id} is already running")
        target = self._target or _default_target
        process = self._ctx.Process(
            target=target,
            args=(dict(payload), self.events, self.broker, self.results),
            name=f"dcr-{job_id}",
            daemon=False,          # a daemon child cannot have children of its own
        )
        process.start()
        now = self._clock()
        handle = WorkerHandle(job_id=job_id, name=str(payload.get("name") or ""),
                              process=process, started_at=now, last_seen=now,
                              payload=dict(payload))
        self.workers[job_id] = handle
        self.started += 1
        event(log, "WORKER", f"{job_id} started as pid {process.pid} "
                             f"({handle.name or 'unnamed'})")
        return handle

    # -- events ------------------------------------------------------------
    def drain_events(self, *, limit: int = 500) -> list[WorkerEvent]:
        """Everything the workers have said since last time.

        Non-blocking and bounded: the scheduler has other things to do, and a
        chatty worker must not be able to hold the loop.
        """
        out: list[WorkerEvent] = []
        for _ in range(limit):
            try:
                message = self.events.get_nowait()
            except (queue_mod.Empty, OSError, ValueError):
                break
            except Exception:                       # a corrupt message
                continue
            if not isinstance(message, WorkerEvent):
                continue
            handle = self.workers.get(message.job_id)
            if handle is not None:
                handle.last_seen = self._clock()
                if message.kind == EventKind.FINISHED:
                    handle.finished_reported = True
            out.append(message)
        self._drain_results()
        return out

    def _drain_results(self) -> None:
        while True:
            try:
                summary = self.results.get_nowait()
            except (queue_mod.Empty, OSError, ValueError):
                return
            except Exception:
                continue
            if not isinstance(summary, dict):
                continue
            handle = self.workers.get(str(summary.get("job_id") or ""))
            if handle is not None:
                handle.summary = summary
                handle.last_seen = self._clock()

    # -- reaping -----------------------------------------------------------
    def reap(self) -> list[WorkerExit]:
        """Collect the workers that have ended, however they ended."""
        self._drain_results()
        now = self._clock()
        finished: list[WorkerExit] = []
        for job_id, handle in list(self.workers.items()):
            if handle.alive:
                continue
            # A process that has exited may still have a summary in flight.
            handle.process.join(timeout=1.0)
            self._drain_results()
            exitcode = handle.exitcode
            summary = dict(handle.summary)
            crashed = not summary and exitcode not in (0,)
            if crashed:
                self.crashed += 1
                reason = (f"the worker process exited with code {exitcode} without "
                          "reporting a result")
                if exitcode is not None and exitcode < 0:
                    reason = (f"the worker process was killed by signal {-exitcode} — "
                              "usually a native crash inside a parser")
            elif not summary:
                reason = "the worker exited cleanly but reported no result"
            else:
                reason = str(summary.get("error") or "")
            finished.append(WorkerExit(
                job_id=job_id,
                name=handle.name,
                ok=bool(summary.get("ok")),
                crashed=crashed,
                exitcode=exitcode,
                summary=summary,
                reason=reason,
                elapsed_s=handle.elapsed_s(now),
            ))
            del self.workers[job_id]
        return finished

    def hung_workers(self) -> list[WorkerHandle]:
        """Workers that have said nothing for longer than they should have."""
        now = self._clock()
        return [handle for handle in self.workers.values()
                if handle.alive and not handle.stopping
                and handle.silent_s(now) > self.heartbeat_timeout_s]

    def terminate(self, job_id: str, *, reason: str = "") -> None:
        """Stop one worker. Asked first, killed only if it will not go."""
        handle = self.workers.get(job_id)
        if handle is None or handle.process is None:
            return
        handle.stopping = True
        log.warning("[WORKER] terminating %s — %s", job_id, reason or "asked to stop")
        try:
            handle.process.terminate()
        except Exception:
            pass
        handle.process.join(timeout=10.0)
        if handle.process.is_alive():
            try:
                handle.process.kill()
            except Exception:
                pass
            handle.process.join(timeout=5.0)
        self.hung += 1

    def stop_all(self, *, grace_s: float | None = None,
                 reason: str = "cancelled") -> None:
        """Ask every worker to stop, wait, then insist.

        Waiting matters: a worker interrupted at a safe boundary has committed
        everything it retrieved and can be resumed exactly; one killed mid-write
        relies on the WAL to recover. Both work, but only the first is tidy
        (brief §36).
        """
        deadline = self._clock() + (self.shutdown_grace_s if grace_s is None
                                    else float(grace_s))
        for handle in self.workers.values():
            handle.stopping = True
        while self._clock() < deadline and self.running:
            self._drain_results()
            time.sleep(0.2)
        for job_id in list(self.workers):
            handle = self.workers.get(job_id)
            if handle is not None and handle.alive:
                self.terminate(job_id, reason=reason)

    def close(self) -> None:
        for job_id in list(self.workers):
            handle = self.workers.get(job_id)
            if handle is not None and handle.alive:
                self.terminate(job_id, reason="shutting down")
        for candidate in (self.events, self.results):
            try:
                candidate.close()
                candidate.join_thread()
            except Exception:
                pass

    def stats(self) -> dict[str, Any]:
        return {
            "started": self.started,
            "running": self.running,
            "crashed": self.crashed,
            "terminated": self.hung,
        }


def _default_target(payload: Mapping[str, Any], events: Any, broker: Any,
                    results: Any) -> None:
    """What a spawned process runs.

    A module-level function, imported by name in the child, because that is what
    `spawn` requires — a closure or a bound method could not be pickled.
    """
    from .worker import worker_main

    worker_main(payload, events, broker, results)


__all__ = ["WorkerExit", "WorkerHandle", "WorkerPool"]
