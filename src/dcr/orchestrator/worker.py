"""The child process: one community, from its addresses to a verified workbook.

This module is the boundary between the run and the research. Everything above
it schedules; everything below it is the existing single-community engine,
unchanged. What happens here is setup, isolation and reporting.

## Why a process and not a thread or a coroutine

The brief asks for the choice to be reasoned rather than fashionable (§41), and
three properties decide it.

**Failure isolation.** A malformed PDF can take a C parser down hard — not a
Python exception, a segmentation fault. In a thread that kills the run; in a
process it kills one community, the parent notices the exit code, records
`FAILED_TECHNICALLY` for that community and gives the worker slot to the next
one. Nothing else about C001–C006 or C008–C212 changes (brief §39).

**The GIL.** Retrieval is I/O-bound and belongs in one event loop, which is what
the engine inside already does. But PDF text extraction, image hashing and
perceptual comparison are CPU-bound, and sixteen communities doing them in
threads would take turns rather than run. Separate processes use separate cores.

**Windows.** There is no `fork`, so `spawn` is the only option and the child is a
fresh interpreter. Everything crossing the boundary is therefore picklable
primitives, and nothing here assumes inherited state — which is also why the
same code behaves identically on Linux (brief §42).

The cost is process startup, roughly a second of imports. Against a community
that takes twenty minutes to research, that is not a consideration.

## What the child does NOT share

Its database — its own file, in its own directory. Its logging — its own files.
Its HTTP client, its browser if it needs one, its caches. The only things it
reaches back for are the event queue it writes progress to and the host broker
it asks before touching a shared server, and both degrade to "carry on alone"
if the parent has gone away.
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path
from typing import Any, Mapping

# ---------------------------------------------------------------------------
# Nothing at module scope may be expensive: on Windows this module is imported
# fresh in every worker process. The heavy imports happen inside `run_job`.
# ---------------------------------------------------------------------------


def _install_path() -> None:
    """Make `dcr` importable in a spawned interpreter.

    A spawned child inherits `sys.path` through the spawn payload in most
    setups, but not when the parent was started from a directory that is no
    longer current. Re-deriving it from this file is cheap and removes a class
    of "works on my machine" failure.
    """
    here = Path(__file__).resolve()
    src = here.parent.parent.parent            # .../src
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def run_job(payload: Mapping[str, Any], event_queue: Any = None,
            broker: Any = None) -> dict[str, Any]:
    """Research one community. Returns a summary; never raises.

    `payload` is a plain dict because it crossed a process boundary. Everything
    it contains was decided by the parent: the community's identity, its own
    directory, its own database path, and the run's configuration root.
    """
    _install_path()

    from ..app import Application
    from ..config import load_settings
    from ..logging_setup import event, get_logger, setup_logging
    from ..runner import CommunityInput
    from ..storage import CommunityStorage
    from .events import EventKind, EventSink

    job_id = str(payload.get("job_id") or "")
    site_id = str(payload.get("site_id") or "")
    worker_name = str(payload.get("worker") or f"w{os.getpid()}")
    sink = EventSink(event_queue, worker=worker_name, job_id=job_id)

    summary: dict[str, Any] = {
        "job_id": job_id,
        "site_id": site_id,
        "worker": worker_name,
        "pid": os.getpid(),
        "final_status": "FAILED_TECHNICALLY",
        "ok": False,
    }

    application = None
    try:
        settings = load_settings(
            root=Path(payload["config_root"]) if payload.get("config_root") else None)
        output_dir = Path(payload["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)

        # ONE DATABASE PER COMMUNITY. This is the whole isolation guarantee:
        # no other process has this file open, so nothing another community
        # does can reach this one's evidence (brief §8).
        settings = settings.with_database(Path(payload["database_path"]))

        storage = CommunityStorage.create(settings.output_root, site_id,
                                          str(payload.get("name") or ""))
        setup_logging(
            storage.logs,
            console_level=payload.get("console_log_level")
            or settings.get("logging", "console_level", default="WARNING"),
            file_level=settings.get("logging", "file_level", default="DEBUG"),
            jsonl=bool(settings.get("logging", "jsonl", default=True)),
        )
        log = get_logger("worker")

        community = CommunityInput(
            name=str(payload.get("name") or ""),
            latitude=payload.get("latitude"),
            longitude=payload.get("longitude"),
            urls=list(payload.get("urls") or []),
            country=payload.get("country"),
            coder_id=str(payload.get("coder_id") or ""),
            fixture=bool(payload.get("fixture", False)),
            assigned_id=site_id or None,
        )

        sink.started(detail=f"{community.name} on {worker_name}",
                     payload={"pid": os.getpid(), "urls": len(community.urls)})

        application = Application(settings)
        # The worker tells the scheduler what it is doing as it goes. The
        # crawl never blocks on this: a full queue drops the message.
        application.on_progress = _progress_bridge(sink)
        _attach_broker(application, broker, community_id=job_id)

        mode = str(payload.get("mode") or "FULL")
        result = application.run(
            community,
            mode=mode,
            estimate_first=bool(payload.get("estimate_first", False)),
            on_status=lambda line: sink.status(line),
        )

        summary.update(_summarise(result))
        summary["ok"] = bool(summary.get("workbook_verified"))
        sink.finished(summary["final_status"], payload={
            key: summary.get(key) for key in
            ("pages", "documents", "images", "evidence", "claims", "sources",
             "conflicts", "yield_units", "active_s", "wall_s", "offline_s",
             "paused_s", "workbook_path", "workbook_verified", "site_id")
        })
        event(log, "WORKER", f"{job_id} finished as {summary['final_status']}")
        return summary

    except KeyboardInterrupt:
        summary["final_status"] = "CANCELLED"
        summary["error"] = "interrupted"
        sink.send(EventKind.FINISHED, detail="CANCELLED")
        return summary
    except BaseException as exc:              # noqa: BLE001 - the boundary
        # NOTHING escapes this function. An exception crossing a process
        # boundary is an exit code and a lost community; a summary is a row in
        # the run's error table and fifteen other communities still running
        # (brief §39, §82).
        detail = "".join(traceback.format_exception(type(exc), exc,
                                                    exc.__traceback__))[-4000:]
        summary["error"] = f"{type(exc).__name__}: {exc}"
        summary["traceback"] = detail
        try:
            sink.error(type(exc).__name__, summary["error"],
                       payload={"traceback": detail[-1500:]})
            sink.finished("FAILED_TECHNICALLY", payload={"error": summary["error"]})
        except Exception:
            pass
        return summary
    finally:
        if application is not None:
            try:
                application.close()
            except Exception:
                pass


def _progress_bridge(sink: Any):
    """Turn the engine's stage callbacks into events for the scheduler."""

    def report(kind: str, **kwargs: Any) -> None:
        try:
            sink.send(kind, **kwargs)
        except Exception:
            pass

    return report


def _attach_broker(application: Any, broker: Any, *, community_id: str) -> None:
    """Give the community's fetcher the run-wide politeness broker.

    Without one it behaves exactly as a single-community run does, which is the
    right failure mode: never stop researching because a coordinator went away.
    """
    if broker is None:
        return
    try:
        from .hosts import BrokerClient

        application.host_broker = BrokerClient(broker, community=community_id)
    except Exception:
        application.host_broker = None


def _summarise(result: Mapping[str, Any]) -> dict[str, Any]:
    """Reduce a completion report to the handful of numbers the queue holds."""
    stats = dict(result.get("stats") or {})
    timing = dict(stats.get("timing") or {})
    workbook = dict(result.get("workbook") or {})
    finalisation = dict(result.get("finalisation") or {})
    verification = dict(finalisation.get("verification") or {})
    return {
        "final_status": str(result.get("completion_status")
                            or result.get("final_status") or "FAILED_TECHNICALLY"),
        "site_id": str(result.get("community_id") or ""),
        "run_id": str(result.get("run_id") or ""),
        "pages": int(stats.get("pages", 0) or 0),
        "documents": int(stats.get("documents", 0) or 0),
        "images": int(stats.get("images", 0) or 0),
        "evidence": int(stats.get("evidence", 0) or 0),
        "claims": int(stats.get("claims", 0) or 0),
        "sources": int(stats.get("sources", 0) or 0),
        "conflicts": int(stats.get("conflicts", 0) or 0),
        "archive_discovered": int(stats.get("archive_discovered", 0) or 0),
        "archive_fetched": int(stats.get("archive_fetched", 0) or 0),
        "academic_records": int(stats.get("academic_records", 0) or 0),
        "yield_units": float((result.get("yield") or {}).get("units", 0.0) or 0.0),
        "active_s": float(timing.get("active_s", 0.0) or 0.0),
        "wall_s": float(timing.get("wall_clock_s", 0.0) or 0.0),
        "offline_s": float(timing.get("offline_s", 0.0) or 0.0),
        "paused_s": float(timing.get("paused_manual_s", 0.0) or 0.0),
        "workbook_path": str(workbook.get("path") or result.get("workbook_path") or ""),
        "workbook_verified": bool(verification.get("reopened",
                                                   workbook.get("verified", False))),
        "output_dir": str(result.get("output_dir") or ""),
        "review_items": int(result.get("review_items", 0) or 0),
        "truncated": bool(result.get("crawl_truncated", False)),
    }


def worker_main(payload: Mapping[str, Any], event_queue: Any = None,
                broker: Any = None, result_queue: Any = None) -> None:
    """The spawned process's entry point.

    A module-level function taking picklable arguments, because that is what
    `spawn` requires: the child imports this module and calls this name.
    """
    summary = run_job(payload, event_queue, broker)
    if result_queue is not None:
        try:
            result_queue.put(summary)
        except Exception:
            pass


__all__ = ["run_job", "worker_main"]
