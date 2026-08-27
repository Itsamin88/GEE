"""Communities that behave badly, on purpose, in a real spawned process.

The scheduler's job is to survive things the research engine cannot be made to
do on demand: a worker that segfaults, a worker that hangs, a worker that
finishes without producing a workbook. Simulating those inside the real engine
would mean corrupting a PDF and hoping; here the behaviour is asked for
directly, and the scheduler cannot tell the difference because it only ever sees
a process, an event queue and an exit code.

Everything is at module level and takes only picklable arguments, because these
run under `spawn` exactly as the real worker does.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Mapping


def _sink(events: Any, payload: Mapping[str, Any]):
    src = Path(__file__).resolve().parent.parent.parent / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from dcr.orchestrator.events import EventSink

    return EventSink(events, worker=str(payload.get("worker") or ""),
                     job_id=str(payload.get("job_id") or ""))


def fake_worker(payload: Mapping[str, Any], events: Any, broker: Any,
                results: Any) -> None:
    """A community that behaves as its `behaviour` says.

    behaviour:
        ok        works for `work_s`, reports a verified workbook
        slow      the same, but takes `work_s` (used for fairness tests)
        fail      finishes cleanly reporting FAILED_TECHNICALLY
        crash     dies the way a native parser crash dies: no result, hard exit
        hang      never says anything again
        blocked   finishes as PARTIAL_BLOCKED, which is a result, not a failure
    """
    sink = _sink(events, payload)
    job_id = str(payload.get("job_id") or "")
    behaviour = str(payload.get("behaviour") or "ok")
    work_s = float(payload.get("work_s") or 0.05)

    sink.started(detail=f"{payload.get('name')} ({behaviour})")

    if behaviour == "crash":
        # Not an exception: the way a C library dies. No summary reaches the
        # parent, and the exit code is all it has to go on.
        sink.stage(2, "enumerate every page")
        os._exit(139)

    if behaviour == "hang":
        sink.stage(2, "enumerate every page")
        while True:
            time.sleep(1.0)

    for stage in (0, 2, 3, 9):
        sink.stage(stage, f"stage {stage}")
        time.sleep(work_s / 4.0)

    if behaviour == "fail":
        summary = {"job_id": job_id, "ok": False,
                   "final_status": "FAILED_TECHNICALLY",
                   "error": "the workbook could not be produced"}
    elif behaviour == "blocked":
        summary = {"job_id": job_id, "ok": False, "final_status": "PARTIAL_BLOCKED",
                   "pages": 3, "sources": 2,
                   "error": "every address refused the crawler"}
    else:
        summary = {
            "job_id": job_id, "ok": True, "final_status": "COMPLETE",
            "site_id": payload.get("site_id"),
            "pages": int(payload.get("pages") or 12),
            "documents": 4, "images": 2, "evidence": 30, "claims": 22,
            "sources": 3, "conflicts": 1, "yield_units": 140.0,
            "active_s": work_s, "wall_s": work_s,
            "workbook_path": str(Path(payload.get("output_dir") or ".")
                                 / f"{payload.get('site_id')}.xlsx"),
            "workbook_verified": True,
        }
    sink.finished(summary["final_status"], payload=summary)
    if results is not None:
        results.put(summary)


def counting_worker(payload: Mapping[str, Any], events: Any, broker: Any,
                    results: Any) -> None:
    """Writes its start and end times to a file, so overlap can be measured.

    This is how "sixteen workers" is checked as an observation rather than a
    claim: the test reads the intervals back and works out how many were
    genuinely concurrent (brief §96).
    """
    sink = _sink(events, payload)
    job_id = str(payload.get("job_id") or "")
    work_s = float(payload.get("work_s") or 0.2)
    started = time.time()
    sink.stage(2, "enumerate every page")
    time.sleep(work_s)
    finished = time.time()
    trace = payload.get("trace_path")
    if trace:
        with open(trace, "a", encoding="utf-8") as handle:
            handle.write(f"{job_id}\t{started}\t{finished}\t{os.getpid()}\n")
    summary = {"job_id": job_id, "ok": True, "final_status": "COMPLETE",
               "active_s": work_s, "wall_s": work_s, "workbook_verified": True}
    sink.finished("COMPLETE", payload=summary)
    if results is not None:
        results.put(summary)


def host_pressure_worker(payload: Mapping[str, Any], events: Any, broker: Any,
                         results: Any) -> None:
    """Hammers one shared host through the broker and records what it got.

    Used to show that sixteen communities do not become sixteen concurrent
    requests to web.archive.org (brief §4, §40).
    """
    src = Path(__file__).resolve().parent.parent.parent / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from dcr.orchestrator.hosts import BrokerClient

    sink = _sink(events, payload)
    job_id = str(payload.get("job_id") or "")
    host = str(payload.get("host") or "web.archive.org")
    requests = int(payload.get("requests") or 4)
    client = BrokerClient(broker, community=job_id)
    stamps: list[tuple[float, float]] = []
    for _ in range(requests):
        if not client.acquire(host, timeout_s=30):
            continue
        start = time.time()
        time.sleep(0.02)
        stamps.append((start, time.time()))
        client.release(host, latency_s=0.02, status=200)
    trace = payload.get("trace_path")
    if trace:
        with open(trace, "a", encoding="utf-8") as handle:
            for start, end in stamps:
                handle.write(f"{job_id}\t{start}\t{end}\t{host}\n")
    summary = {"job_id": job_id, "ok": True, "final_status": "COMPLETE",
               "active_s": 0.1, "workbook_verified": True}
    sink.finished("COMPLETE", payload=summary)
    if results is not None:
        results.put(summary)
