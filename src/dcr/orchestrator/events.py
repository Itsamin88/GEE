"""What a worker tells the scheduler while it works.

A worker is a separate operating-system process — which is what makes a
segmentation fault inside a PDF library one dead community rather than a dead
run — so it cannot simply update a shared object. It sends small immutable
messages up a queue, and the parent writes them down.

Three properties matter more than richness here:

**Everything must pickle.** Windows has no `fork`, so the child is a fresh
interpreter and every message crosses a pipe. Dataclasses of primitives do;
exceptions with tracebacks, database handles and open sockets do not, so failure
is reported as text that has already been formatted.

**Nothing may block the worker.** A full queue must never stall the crawl, so
sends are best-effort: a dropped progress message costs a dashboard refresh, and
the authoritative record is the community's own database in any case.

**The parent must survive a mad child.** Every field is bounded before it is
sent, so a worker that has gone wrong cannot exhaust the parent's memory with a
gigabyte of "detail".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


class EventKind:
    """The vocabulary. Kept as strings so an unknown one is merely ignored."""

    STARTED = "started"
    STAGE = "stage"
    PROGRESS = "progress"
    STATUS = "status"            # a human-readable line for the dashboard
    PAUSED = "paused"
    RESUMED = "resumed"
    YIELD = "yield"
    HOST = "host"                # what a host did: rate limits, blocks, latency
    ERROR = "error"              # survivable: recorded, the community continues
    FINISHED = "finished"        # the community reached a final status
    CRASHED = "crashed"          # the worker died; the parent decides what next
    HEARTBEAT = "heartbeat"


#: Longest string any single field may carry across the pipe.
MAX_TEXT = 4000


def _clip(value: Any, limit: int = MAX_TEXT) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass(frozen=True)
class WorkerEvent:
    """One message from a worker to the scheduler.

    Frozen and primitive-only: it crosses a process boundary, and anything that
    cannot be pickled would fail at the far end of a pipe rather than here.
    """

    kind: str
    job_id: str
    worker: str = ""
    stage_no: int | None = None
    stage_name: str = ""
    detail: str = ""
    progress: float = 0.0
    payload: Mapping[str, Any] = field(default_factory=dict)
    ts: float = 0.0

    @classmethod
    def make(cls, kind: str, job_id: str, *, worker: str = "",
             stage_no: int | None = None, stage_name: str = "", detail: str = "",
             progress: float = 0.0,
             payload: Mapping[str, Any] | None = None) -> "WorkerEvent":
        import time

        return cls(
            kind=str(kind)[:40],
            job_id=str(job_id)[:40],
            worker=str(worker)[:40],
            stage_no=stage_no,
            stage_name=_clip(stage_name, 120),
            detail=_clip(detail),
            progress=max(0.0, min(1.0, float(progress or 0.0))),
            payload=_sanitise(payload),
            ts=time.time(),
        )


def _sanitise(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Keep only what will pickle, and bound what it costs.

    A worker sending an object the parent cannot unpickle would kill the reader
    thread, which is a far worse failure than losing one progress update.
    """
    if not payload:
        return {}
    out: dict[str, Any] = {}
    for key, value in list(payload.items())[:60]:
        name = str(key)[:60]
        if isinstance(value, (int, float, bool)) or value is None:
            out[name] = value
        elif isinstance(value, str):
            out[name] = _clip(value, 1000)
        elif isinstance(value, (list, tuple)):
            out[name] = [_clip(item, 200) if isinstance(item, str) else item
                         for item in list(value)[:50]
                         if isinstance(item, (str, int, float, bool))]
        elif isinstance(value, Mapping):
            out[name] = {str(k)[:60]: (_clip(v, 300) if isinstance(v, str) else v)
                         for k, v in list(value.items())[:40]
                         if isinstance(v, (str, int, float, bool)) or v is None}
        else:
            out[name] = _clip(value, 300)
    return out


class EventSink:
    """The worker's end of the pipe. Never blocks, never raises.

    A crawl must not stop because a dashboard is slow, so a send that cannot
    complete is dropped. The community's own database is the record; this is
    only what the researcher watches (brief §51).
    """

    def __init__(self, queue: Any, *, worker: str = "", job_id: str = ""):
        self._queue = queue
        self.worker = worker
        self.job_id = job_id
        self.dropped = 0

    def send(self, kind: str, **kwargs: Any) -> None:
        if self._queue is None:
            return
        kwargs.setdefault("worker", self.worker)
        event = WorkerEvent.make(kind, kwargs.pop("job_id", self.job_id), **kwargs)
        try:
            self._queue.put_nowait(event)
        except Exception:
            self.dropped += 1

    # Convenience wrappers, so call sites read as what happened.
    def started(self, **kwargs: Any) -> None:
        self.send(EventKind.STARTED, **kwargs)

    def stage(self, stage_no: int, stage_name: str, **kwargs: Any) -> None:
        self.send(EventKind.STAGE, stage_no=stage_no, stage_name=stage_name, **kwargs)

    def status(self, detail: str, **kwargs: Any) -> None:
        self.send(EventKind.STATUS, detail=detail, **kwargs)

    def progress(self, fraction: float, **kwargs: Any) -> None:
        self.send(EventKind.PROGRESS, progress=fraction, **kwargs)

    def paused(self, reason: str, kind: str = "manual") -> None:
        self.send(EventKind.PAUSED, detail=reason, payload={"pause_kind": kind})

    def resumed(self, reason: str = "") -> None:
        self.send(EventKind.RESUMED, detail=reason)

    def error(self, error_class: str, message: str, **kwargs: Any) -> None:
        self.send(EventKind.ERROR, detail=message,
                  payload={"error_class": error_class, **(kwargs.pop("payload", {}) or {})},
                  **kwargs)

    def finished(self, final_status: str, payload: Mapping[str, Any] | None = None) -> None:
        self.send(EventKind.FINISHED, detail=final_status, payload=payload or {})

    def heartbeat(self, **kwargs: Any) -> None:
        self.send(EventKind.HEARTBEAT, **kwargs)


__all__ = ["EventKind", "EventSink", "WorkerEvent"]
