"""The scheduler: who runs next, how many at once, and what happens when.

This is the loop the researcher starts and then walks away from. It owns the
queue, the workers and the decision to keep going; everything else in the
package is something it asks.

    ┌──────────────────────────────────────────────────────────────┐
    │  age the queue        waiting must be worth something (§5)   │
    │  ask the governor     how many workers this machine can take │
    │  fill the slots       claim the highest-priority runnable    │
    │  drain the events     write down what the workers said       │
    │  reap the dead        a crash is one community, not the run  │
    │  check for controls   PAUSE ALL / RESUME ALL / CANCEL ALL    │
    └──────────────────────────────────────────────────────────────┘
                       every second, until the queue is empty

## Fairness, and why ageing is not optional

The plan orders communities largest-first, which is the right opening move: it
keeps one enormous community from being the last thing running while fifteen
workers idle. Left alone, though, that ordering means the twenty largest
communities take every worker that frees up and the short ones sit behind them
for the whole run — exactly the starvation the brief forbids in §5.

So a queued community's effective priority rises with the time it has waited,
capped so age alone cannot outrank everything for ever. A twenty-document
community that has waited an hour outranks a five-thousand-URL one that arrived
five minutes ago. Both make progress; neither monopolises.

## One failure is one row

Every way a community can fail — a crash, a hang, a refused site, an
unreadable workbook — ends the same way: a row in the queue with a final status,
a row in the error table with the reason, and the worker slot handed to the next
community. Nothing propagates. That is the whole of §39, and it is why the loop
below catches broadly and records rather than raising.

## Nothing here is a research decision

The scheduler never decides what to crawl, how deep to go or when a community
has found enough. Those belong to the yield governor inside each worker. This
decides only *who runs*, and that separation is what keeps a busy machine from
quietly changing the research.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from ..control import (CANCEL_FILE, PAUSE_FILE, RESUME_FILE, control_dir_for,
                       request_cancel, request_pause, request_resume)
from ..logging_setup import event, get_logger
from .events import EventKind, WorkerEvent
from .governor import ResourceGovernor, ResourceSample, sample_resources
from .plan import CommunityJob, RunPlan
from .pool import WorkerExit, WorkerPool
from .store import (AGE_CAP, AGE_PER_MINUTE, CANCELLED, COMPLETED, FAILED, PAUSED_MANUAL, PAUSING, PAUSED_NETWORK,
                    QUEUED, RESUMING, RUNNING, RUN_CANCELLED, RUN_CANCELLING,
                    RUN_COMPLETED, RUN_PAUSED, RUN_RUNNING, JobRow, RunStore)

log = get_logger("orchestrator.scheduler")

#: How often the loop goes round. Cheap: a few file stats and a queue drain.
DEFAULT_TICK_S = 1.0

#: How often the governor is asked and a sample is written down.
DEFAULT_SAMPLE_EVERY_S = 15.0

#: How many times a community is retried after a crash before it is left
#: FAILED. Two: once for the transient case, and no more, because a community
#: that crashes three times is a bug to look at rather than work to redo.
DEFAULT_MAX_ATTEMPTS = 3

#: Final statuses that mean the community produced a usable research record.
GOOD_STATUSES = ("COMPLETE", "COMPLETE_WITH_UNCERTAINTY", "COMPLETE_WITH_TRUNCATION")


@dataclass
class SchedulerStats:
    ticks: int = 0
    dispatched: int = 0
    completed: int = 0
    failed: int = 0
    crashed: int = 0
    retried: int = 0
    hung: int = 0
    started_at: float = 0.0
    finished_at: float = 0.0
    paused_s: float = 0.0
    peak_workers: int = 0
    worker_seconds: float = 0.0

    @property
    def wall_s(self) -> float:
        end = self.finished_at or time.monotonic()
        return max(0.0, end - self.started_at) if self.started_at else 0.0


class RunScheduler:
    """Runs a queue of communities to completion, adapting as it goes."""

    def __init__(
        self,
        store: RunStore,
        plan: RunPlan,
        *,
        output_root: Path,
        pool: WorkerPool | None = None,
        governor: ResourceGovernor | None = None,
        config: Mapping[str, Any] | None = None,
        on_update: Callable[["RunScheduler"], None] | None = None,
        clock: Any = None,
        payload_extra: Mapping[str, Any] | None = None,
    ):
        self.store = store
        self.plan = plan
        self.run_id = plan.run_id
        self.output_root = Path(output_root)
        self.config = dict(config or {})
        self.pool = pool if pool is not None else WorkerPool()
        self.governor = governor or ResourceGovernor(
            config=self.config.get("workers") or {})
        self.stats = SchedulerStats()
        self._clock = clock or time.monotonic
        self._on_update = on_update
        self._payload_extra = dict(payload_extra or {})
        self.tick_s = float(self.config.get("tick_seconds", DEFAULT_TICK_S))
        self.sample_every_s = float(
            self.config.get("sample_seconds", DEFAULT_SAMPLE_EVERY_S))
        self.max_attempts = int(self.config.get("max_attempts", DEFAULT_MAX_ATTEMPTS))
        self.age_per_minute = float(
            self.config.get("age_priority_per_minute", AGE_PER_MINUTE))
        self.age_cap = float(self.config.get("age_priority_cap", AGE_CAP))
        self._last_sample_at = 0.0
        self._paused_since: float | None = None
        self.cancelled = False
        self.control_dir = control_dir_for(self.output_root)
        #: The last dashboard line for each community, kept so a renderer does
        #: not have to re-read the database every second.
        self.live: dict[str, dict[str, Any]] = {}

    # =====================================================================
    # the loop
    # =====================================================================
    def run(self, *, max_ticks: int | None = None) -> SchedulerStats:
        """Work the queue until it is empty, paused for good, or cancelled."""
        self.stats.started_at = self._clock()
        self.store.set_run_status(self.run_id, RUN_RUNNING)
        event(log, "RUN", f"{len(self.plan.jobs)} communities queued; starting with "
                          f"{self.governor.target} workers")
        ticks = 0
        try:
            while True:
                ticks += 1
                self.stats.ticks = ticks
                self.tick()
                if self.finished():
                    break
                if max_ticks is not None and ticks >= max_ticks:
                    break
                time.sleep(self.tick_s)
        finally:
            self.stats.finished_at = self._clock()
            self._shutdown()
        return self.stats

    def tick(self) -> None:
        """One pass. Kept small enough to call from a test without a clock."""
        control = self._poll_controls()
        self.store.age_priorities(self.run_id, per_minute=self.age_per_minute,
                                  cap=self.age_cap)
        self._handle_events(self.pool.drain_events())
        self._handle_exits(self.pool.reap())
        self._check_hung()

        if control == "cancel":
            self._cancel_all()
        elif control == "pause":
            self._ensure_paused()
        else:
            if self._paused_since is not None:
                self._resume_all()
            self._sample_and_adapt()
            self._fill_slots()

        self._accumulate_worker_seconds()
        if self._on_update is not None:
            try:
                self._on_update(self)
            except Exception:
                log.debug("dashboard update failed", exc_info=True)

    def finished(self) -> bool:
        if self.cancelled and not self.pool.running:
            return True
        counts = self.store.counts(self.run_id)
        outstanding = (counts.get(QUEUED, 0) + counts.get(RUNNING, 0)
                       + counts.get(RESUMING, 0) + counts.get(PAUSED_NETWORK, 0))
        if outstanding == 0 and not self.pool.running:
            return True
        # Everything left is paused by the researcher and nothing is running:
        # the run is not finished, but it is not going to progress either.
        if (self._paused_since is not None and not self.pool.running
                and counts.get(QUEUED, 0) == 0):
            return True
        return False

    # =====================================================================
    # filling slots
    # =====================================================================
    def _fill_slots(self) -> None:
        target = self.governor.target
        while self.pool.running < target:
            job = self.store.claim_next(self.run_id, worker=f"w{self.pool.started + 1}",
                                        exclude=self.pool.busy_jobs)
            if job is None:
                return
            if job.attempts > self.max_attempts:
                self._finish_job(job.job_id, FAILED, "FAILED_TECHNICALLY",
                                 detail=f"gave up after {job.attempts - 1} attempts")
                continue
            self._dispatch(job)

    def _dispatch(self, job: JobRow) -> None:
        payload = {
            "job_id": job.job_id,
            "site_id": job.site_id,
            "name": job.name,
            "urls": list(job.urls),
            "latitude": job.latitude,
            "longitude": job.longitude,
            "country": job.country,
            "coder_id": job.coder_id,
            "mode": job.mode,
            "fixture": job.fixture,
            "output_dir": job.output_dir or str(self.output_root / job.site_id),
            "database_path": job.database_path,
            "worker": f"w{self.pool.started + 1}",
            **self._payload_extra,
        }
        try:
            self.pool.start(payload)
        except Exception as exc:
            # Starting a process can fail for reasons that have nothing to do
            # with this community — too many handles, no memory. Put it back.
            log.error("could not start a worker for %s: %s", job.job_id, exc)
            self.store.release(job.job_id, state=QUEUED,
                               detail=f"worker could not be started: {exc}")
            self.store.add_error(self.run_id, job_id=job.job_id,
                                 error_class="WORKER_START",
                                 message=str(exc))
            return
        self.stats.dispatched += 1
        self.stats.peak_workers = max(self.stats.peak_workers, self.pool.running)
        self.store.update_job(job.job_id, {"state": RUNNING, "detail": "started"})
        self.store.add_event(self.run_id, EventKind.STARTED, job_id=job.job_id,
                             detail=f"{job.name} on {payload['worker']}")
        self.live[job.job_id] = {"name": job.name, "state": RUNNING, "stage_no": 0,
                                 "stage_name": "starting", "detail": "", "progress": 0.0}

    # =====================================================================
    # what the workers say
    # =====================================================================
    def _handle_events(self, events: Sequence[WorkerEvent]) -> None:
        for message in events:
            try:
                self._handle_event(message)
            except Exception:
                # An event must never be able to stop the scheduler; the
                # community's own database is the record in any case.
                log.debug("could not handle a worker event", exc_info=True)

    def _handle_event(self, message: WorkerEvent) -> None:
        job_id = message.job_id
        live = self.live.setdefault(job_id, {})
        updates: dict[str, Any] = {}

        if message.kind == EventKind.STAGE:
            live.update(stage_no=message.stage_no, stage_name=message.stage_name,
                        progress=message.progress)
            updates.update(stage_no=message.stage_no, stage_name=message.stage_name,
                           progress=message.progress)
            self.store.add_event(self.run_id, EventKind.STAGE, job_id=job_id,
                                 stage_no=message.stage_no,
                                 detail=message.stage_name)
        elif message.kind == EventKind.PROGRESS:
            live["progress"] = message.progress
            updates["progress"] = message.progress
        elif message.kind == EventKind.STATUS:
            live["detail"] = message.detail
            updates["detail"] = message.detail[:500]
        elif message.kind == EventKind.PAUSED:
            kind = str(message.payload.get("pause_kind") or "manual")
            state = PAUSED_NETWORK if kind == "network" else PAUSED_MANUAL
            live["state"] = state
            updates["state"] = state
            updates["detail"] = message.detail[:500]
            self.store.add_event(self.run_id, EventKind.PAUSED, job_id=job_id,
                                 detail=f"{kind}: {message.detail}")
        elif message.kind == EventKind.RESUMED:
            live["state"] = RUNNING
            updates["state"] = RUNNING
            self.store.add_event(self.run_id, EventKind.RESUMED, job_id=job_id,
                                 detail=message.detail)
        elif message.kind == EventKind.ERROR:
            self.store.add_error(
                self.run_id, job_id=job_id,
                error_class=str(message.payload.get("error_class") or "UNKNOWN"),
                message=message.detail,
                detail=str(message.payload.get("traceback") or ""))
        elif message.kind == EventKind.HOST:
            host = str(message.payload.get("host") or "")
            if host:
                self.store.note_host(host, {
                    key: message.payload[key]
                    for key in ("requests", "failures", "rate_limited", "blocked",
                                "delay_s", "concurrency")
                    if key in message.payload})
        elif message.kind == EventKind.FINISHED:
            live["state"] = message.detail
            self.store.add_event(self.run_id, EventKind.FINISHED, job_id=job_id,
                                 detail=message.detail,
                                 payload=dict(message.payload))
            updates.update(self._counts_from(message.payload))

        if updates:
            self.store.update_job(job_id, updates)

    @staticmethod
    def _counts_from(payload: Mapping[str, Any]) -> dict[str, Any]:
        wanted = ("pages", "documents", "images", "evidence", "claims", "sources",
                  "conflicts", "yield_units", "active_s", "wall_s", "offline_s",
                  "paused_s", "workbook_path")
        out: dict[str, Any] = {}
        for key in wanted:
            if key in payload and payload[key] is not None:
                out[key] = payload[key]
        if "workbook_verified" in payload:
            out["workbook_verified"] = int(bool(payload["workbook_verified"]))
        return out

    # =====================================================================
    # what happens when a worker ends
    # =====================================================================
    def _handle_exits(self, exits: Sequence[WorkerExit]) -> None:
        for ended in exits:
            try:
                self._handle_exit(ended)
            except Exception:
                log.error("could not record the end of %s", ended.job_id, exc_info=True)

    def _handle_exit(self, ended: WorkerExit) -> None:
        job = self.store.job(ended.job_id)
        summary = dict(ended.summary)
        self.governor.note_completion(workers=max(1, self.pool.running + 1),
                                      active_s=max(1.0, ended.elapsed_s))

        if ended.crashed:
            self.stats.crashed += 1
            self.store.add_error(self.run_id, job_id=ended.job_id,
                                 error_class="WORKER_CRASH", message=ended.reason,
                                 detail=f"exit code {ended.exitcode}", fatal=False)
            attempts = job.attempts if job else self.max_attempts
            if attempts < self.max_attempts:
                # One community's crash costs one community a retry. The other
                # 211 are unaffected, which is the whole point (brief §39).
                self.stats.retried += 1
                self.store.release(ended.job_id, state=QUEUED,
                                   detail=f"worker crashed ({ended.reason}); requeued")
                event(log, "WORKER",
                      f"{ended.job_id} crashed and was requeued "
                      f"(attempt {attempts} of {self.max_attempts})")
                return
            self._finish_job(ended.job_id, FAILED, "FAILED_TECHNICALLY",
                             detail=ended.reason)
            return

        final_status = str(summary.get("final_status") or "FAILED_TECHNICALLY")
        updates = self._counts_from(summary)
        updates["final_status"] = final_status
        if summary.get("workbook_path"):
            updates["workbook_path"] = summary["workbook_path"]
        if summary.get("output_dir"):
            updates["output_dir"] = summary["output_dir"]
        if summary.get("error"):
            updates["last_error"] = str(summary["error"])[:1000]
        self.store.update_job(ended.job_id, updates)

        state = COMPLETED if final_status in GOOD_STATUSES else FAILED
        if final_status in ("PAUSED_MANUAL", "PAUSED_NETWORK"):
            state = final_status
        elif final_status == "CANCELLED":
            state = CANCELLED
        self._finish_job(ended.job_id, state, final_status,
                         detail=str(summary.get("error") or ""))

    def _finish_job(self, job_id: str, state: str, final_status: str,
                    *, detail: str = "") -> None:
        self.store.update_job(job_id, {"state": state, "final_status": final_status,
                                       "worker": None,
                                       "detail": detail[:500] or None})
        self.store.set_job_state(job_id, state, detail=detail)
        if state == COMPLETED:
            self.stats.completed += 1
        elif state == FAILED:
            self.stats.failed += 1
        self.live.setdefault(job_id, {})["state"] = state
        event(log, "RUN", f"{job_id} finished: {final_status}")

    def _check_hung(self) -> None:
        for handle in self.pool.hung_workers():
            self.stats.hung += 1
            silent = handle.silent_s() / 60.0
            reason = (f"no progress for {silent:.0f} minutes; presumed hung and "
                      "terminated so the worker can be given to another community")
            self.store.add_error(self.run_id, job_id=handle.job_id,
                                 error_class="WORKER_HUNG", message=reason)
            self.pool.terminate(handle.job_id, reason=reason)

    # =====================================================================
    # adapting
    # =====================================================================
    def _sample_and_adapt(self) -> None:
        now = self._clock()
        # Always take the first sample. Without it a run shorter than the
        # sampling interval records nothing, and "how many workers did it
        # actually use" becomes unanswerable for exactly the short runs a
        # benchmark is made of.
        if self._last_sample_at and now - self._last_sample_at < self.sample_every_s:
            return
        self._last_sample_at = now
        counts = self.store.counts(self.run_id)
        sample = sample_resources()
        decision = self.governor.decide(running=self.pool.running,
                                        queued=counts.get(QUEUED, 0),
                                        sample=sample)
        self.store.add_sample(self.run_id, {
            "workers": self.pool.running,
            "target": decision.target,
            "running": counts.get(RUNNING, 0),
            "queued": counts.get(QUEUED, 0),
            "paused": counts.get(PAUSED_MANUAL, 0) + counts.get(PAUSED_NETWORK, 0),
            "completed": counts.get(COMPLETED, 0),
            "failed": counts.get(FAILED, 0),
            "cpu_pct": sample.cpu_pct,
            "memory_pct": sample.memory_pct,
            "load_avg": sample.load_avg,
            "open_conns": 0,
            "decision": "grow" if decision.target > decision.previous else (
                "shrink" if decision.target < decision.previous else "hold"),
            "reason": decision.reason[:500],
        })

    def _accumulate_worker_seconds(self) -> None:
        self.stats.worker_seconds += self.pool.running * self.tick_s

    # =====================================================================
    # the researcher's controls
    # =====================================================================
    def _poll_controls(self) -> str:
        """Has the researcher asked for something? (brief §33, §35, §36)"""
        directory = self.control_dir
        if (directory / CANCEL_FILE).exists():
            return "cancel"
        if (directory / RESUME_FILE).exists() and not (directory / PAUSE_FILE).exists():
            return "resume"
        if (directory / PAUSE_FILE).exists():
            return "pause"
        status = self.store.run_status(self.run_id)
        if status == RUN_CANCELLING:
            return "cancel"
        if status == RUN_PAUSED:
            return "pause"
        return ""

    def _ensure_paused(self) -> None:
        """PAUSE ALL: stop starting work, and let the running workers stop.

        The workers see the same run-level request file and pause themselves at
        their own next safe boundary, so nothing is half-written. The scheduler
        does not kill them; it stops filling slots and waits.
        """
        if self._paused_since is None:
            self._paused_since = self._clock()
            self.store.set_run_status(self.run_id, RUN_PAUSED)
            self.store.add_event(self.run_id, EventKind.PAUSED,
                                 detail="PAUSE ALL requested by the researcher")
            event(log, "RUN", "PAUSE ALL — no new communities will start; running "
                              "ones will stop at their next safe boundary")

    def _resume_all(self) -> None:
        if self._paused_since is not None:
            self.stats.paused_s += self._clock() - self._paused_since
            self._paused_since = None
            self.store.set_run_status(self.run_id, RUN_RUNNING)
            self.store.add_event(self.run_id, EventKind.RESUMED, detail="RESUME ALL")
            event(log, "RUN", "RESUME ALL — the queue is moving again")

    def _cancel_all(self) -> None:
        """CANCEL ALL: stop starting, checkpoint, preserve everything (brief §36)."""
        if self.cancelled:
            return
        self.cancelled = True
        self.store.set_run_status(self.run_id, RUN_CANCELLING)
        self.store.add_event(self.run_id, EventKind.FINISHED,
                             detail="CANCEL ALL requested by the researcher")
        event(log, "RUN", "CANCEL ALL — letting running communities checkpoint; "
                          "everything already completed is kept")
        for job in self.store.jobs(self.run_id, states=[QUEUED]):
            self.store.update_job(job.job_id, {
                "state": CANCELLED, "final_status": "CANCELLED",
                "detail": "cancelled before it started"})
        self.pool.stop_all(reason="cancelled by the researcher")
        self._handle_exits(self.pool.reap())
        self.store.set_run_status(self.run_id, RUN_CANCELLED)

    # -- public controls ---------------------------------------------------
    def pause_all(self, reason: str = "") -> None:
        request_pause(self.output_root, reason or "PAUSE ALL")

    def resume_all(self, reason: str = "") -> None:
        request_resume(self.output_root, reason or "RESUME ALL")

    def cancel_all(self, reason: str = "") -> None:
        request_cancel(self.output_root, reason or "CANCEL ALL")

    def pause_community(self, job_id: str, reason: str = "") -> bool:
        """Pause one community without touching the others (brief §34).

        The request goes into that community's own control directory, which is
        the only one its worker reads. Its worker stops at its next safe
        boundary and exits; the slot goes back to the scheduler for the next
        queued community, so pausing C007 speeds the rest of the run up rather
        than holding a worker idle.
        """
        job = self.store.job(job_id)
        if job is None or not job.output_dir:
            return False
        request_pause(Path(job.output_dir), reason or f"{job_id} paused")
        self.store.update_job(job_id, {"state": PAUSING,
                                       "detail": reason or "pause requested"})
        return True

    def resume_community(self, job_id: str, reason: str = "") -> bool:
        job = self.store.job(job_id)
        if job is None or not job.output_dir:
            return False
        request_resume(Path(job.output_dir), reason or f"{job_id} resumed")
        self.store.update_job(job_id, {"state": QUEUED,
                                       "detail": reason or "resume requested"})
        return True

    # =====================================================================
    # shutdown and reporting
    # =====================================================================
    def _shutdown(self) -> None:
        self._handle_events(self.pool.drain_events())
        self._handle_exits(self.pool.reap())
        self.pool.close()
        counts = self.store.counts(self.run_id)
        outstanding = counts.get(QUEUED, 0) + counts.get(RUNNING, 0)
        if self.cancelled:
            self.store.set_run_status(self.run_id, RUN_CANCELLED)
        elif outstanding == 0 and self._paused_since is None:
            self.store.set_run_status(self.run_id, RUN_COMPLETED)
        elif self._paused_since is not None:
            self.store.set_run_status(self.run_id, RUN_PAUSED)

    def snapshot(self) -> dict[str, Any]:
        """Everything the dashboard and the final summary need (brief §50)."""
        counts = self.store.counts(self.run_id)
        totals = self.store.totals(self.run_id)
        remaining_low, remaining_high = self._remaining_estimate(counts)
        return {
            "run_id": self.run_id,
            "counts": counts,
            "totals": totals,
            "workers": {
                "running": self.pool.running,
                "target": self.governor.target,
                "maximum": self.governor.maximum,
                "peak": self.stats.peak_workers,
            },
            "wall_s": self.stats.wall_s,
            "paused_s": self.stats.paused_s
            + (self._clock() - self._paused_since if self._paused_since else 0.0),
            "remaining_low_s": remaining_low,
            "remaining_high_s": remaining_high,
            "cancelled": self.cancelled,
            "paused": self._paused_since is not None,
            "dispatched": self.stats.dispatched,
            "crashed": self.stats.crashed,
            "retried": self.stats.retried,
            "hung": self.stats.hung,
            "live": dict(self.live),
        }

    def _remaining_estimate(self, counts: Mapping[str, int]) -> tuple[float, float]:
        """How much longer, from what has actually been observed (brief §46).

        Once communities have finished, their real durations are a far better
        predictor than the estimate made from typed addresses — so the estimate
        switches over as soon as there is anything to switch to, and says which
        it is using.
        """
        outstanding = [job for job in self.store.jobs(self.run_id)
                       if job.state in (QUEUED, RUNNING, RESUMING, PAUSED_NETWORK)]
        if not outstanding:
            return 0.0, 0.0
        done = [job for job in self.store.jobs(self.run_id, states=[COMPLETED])
                if job.active_s > 0]
        workers = max(1, self.governor.target)
        if done:
            mean = sum(job.active_s for job in done) / len(done)
            low = mean * 0.7 * len(outstanding) / workers
            high = mean * 1.6 * len(outstanding) / workers
        else:
            low = sum(job.estimate_low_s for job in outstanding) / workers
            high = sum(job.estimate_high_s for job in outstanding) / workers
        # Never claim to finish sooner than the single longest job still going.
        longest = max((job.estimate_high_s for job in outstanding), default=0.0)
        return round(max(low, longest * 0.4), 1), round(max(high, longest), 1)


__all__ = ["GOOD_STATUSES", "RunScheduler", "SchedulerStats"]
