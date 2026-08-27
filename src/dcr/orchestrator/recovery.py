"""Picking a run back up after the machine was switched off.

A run of two hundred communities lasts hours. Over hours, PyCharm gets closed,
Windows decides to restart, the power goes, a laptop lid comes down. None of
those is a research finding, and none of them may cost the run (brief §37,
§100, §101).

Recovery is a database question, not a filesystem question. The queue records
what each community was doing; the filesystem records what it produced. Reading
the queue is exact; guessing from directories is not — a half-written workbook
looks exactly like a finished one from the outside, and a community that crashed
at stage 8 has all the directories a completed one has.

## What is offered, and what is never assumed

    Previous run detected: R20260827-141233
      212 communities
       37 completed
       11 were active when it stopped     -> requeued
      164 queued
        4 paused by the researcher        -> LEFT PAUSED

    RESUME ALL / RESUME ONE / EXPORT ONLY / START A NEW RUN

**A community that was RUNNING when the power went is requeued**, because
nothing was watching it and its worker is gone. Its own crawl resumes from its
last checkpoint — the community database knows where it was — so requeueing
costs the tail of one stage, not the community.

**A community the researcher PAUSED stays paused.** It was stopped on purpose,
and quietly restarting it would be the software overruling a decision. Resuming
it is a separate, explicit choice (brief §33).

**A community that COMPLETED is never re-run.** Its workbook exists and has been
verified; re-running it would cost hours and change a verified research record.

## Recovery that does not touch the network

Three of the recovery modes exist because the expensive part succeeded and only
the cheap part failed, and re-fetching the web to fix a spreadsheet would be
absurd (brief §102, §103, §105):

    EXPORT      the crawl succeeded, the workbook did not — rebuild it
    RECONCILE   the evidence is in, the reconciliation failed — redo it
    AUDIT       check evidence, sources and workbook offline, fetch nothing
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ..logging_setup import event, get_logger
from .store import (CANCELLED, COMPLETED, FAILED, PAUSED_MANUAL, PAUSED_NETWORK,
                    PAUSING, QUEUED, RESUMING, RUNNING, RUN_CANCELLED,
                    RUN_COMPLETED, JobRow, RunStore)

log = get_logger("orchestrator.recovery")

#: Modes that need no network at all. Offered whenever the crawl itself worked.
OFFLINE_MODES = ("EXPORT", "RECONCILE", "AUDIT")

#: Final statuses that mean the community produced a usable research record and
#: must not be re-crawled.
FINISHED_STATUSES = ("COMPLETE", "COMPLETE_WITH_UNCERTAINTY",
                     "COMPLETE_WITH_TRUNCATION")


@dataclass
class InterruptedRun:
    """A run the application can offer to continue."""

    run_id: str
    status: str
    created_utc: str
    output_root: str
    mode: str = "FULL"
    total: int = 0
    completed: int = 0
    running: int = 0
    queued: int = 0
    paused: int = 0
    failed: int = 0
    cancelled: int = 0
    workbooks: int = 0

    @property
    def outstanding(self) -> int:
        return self.running + self.queued + self.paused + self.failed

    @property
    def resumable(self) -> bool:
        return self.outstanding > 0 and self.status not in (RUN_CANCELLED,)

    def describe(self) -> str:
        parts = [f"{self.total} communities", f"{self.completed} completed"]
        if self.running:
            parts.append(f"{self.running} active when it stopped")
        if self.queued:
            parts.append(f"{self.queued} queued")
        if self.paused:
            parts.append(f"{self.paused} paused")
        if self.failed:
            parts.append(f"{self.failed} failed")
        return f"{self.run_id} ({self.created_utc}): " + ", ".join(parts)

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id, "status": self.status,
            "created_utc": self.created_utc, "output_root": self.output_root,
            "total": self.total, "completed": self.completed,
            "running_at_interruption": self.running, "queued": self.queued,
            "paused": self.paused, "failed": self.failed,
            "cancelled": self.cancelled, "workbooks_verified": self.workbooks,
            "resumable": self.resumable,
        }


def find_interrupted(store: RunStore, *, limit: int = 5) -> list[InterruptedRun]:
    """Runs that stopped without finishing, newest first (brief §100)."""
    out: list[InterruptedRun] = []
    for row in store.unfinished_runs()[:limit]:
        run_id = str(row["run_id"])
        counts = store.counts(run_id)
        totals = store.totals(run_id)
        out.append(InterruptedRun(
            run_id=run_id,
            status=str(row["status"]),
            created_utc=str(row["created_utc"]),
            output_root=str(row["output_root"]),
            mode=str(row["mode"]),
            total=int(counts.get("TOTAL", 0)),
            completed=int(counts.get(COMPLETED, 0)),
            running=int(counts.get(RUNNING, 0)) + int(counts.get(RESUMING, 0))
            + int(counts.get(PAUSING, 0)),
            queued=int(counts.get(QUEUED, 0)),
            paused=int(counts.get(PAUSED_MANUAL, 0)) + int(counts.get(PAUSED_NETWORK, 0)),
            failed=int(counts.get(FAILED, 0)),
            cancelled=int(counts.get(CANCELLED, 0)),
            workbooks=int(totals.get("workbooks", 0) or 0),
        ))
    return out


@dataclass
class RecoveryPlan:
    """What resuming this run would actually do, decided before anything runs."""

    run_id: str
    requeue: list[str] = field(default_factory=list)
    leave_paused: list[str] = field(default_factory=list)
    keep_complete: list[str] = field(default_factory=list)
    retry_failed: list[str] = field(default_factory=list)
    already_queued: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def to_run(self) -> list[str]:
        return self.requeue + self.retry_failed + self.already_queued

    def describe(self) -> str:
        lines = []
        if self.requeue:
            lines.append(
                f"  {len(self.requeue)} community(ies) were active when the run "
                "stopped and will be requeued; each resumes from its own last "
                "checkpoint rather than from the beginning")
        if self.already_queued:
            lines.append(f"  {len(self.already_queued)} still queued")
        if self.retry_failed:
            lines.append(f"  {len(self.retry_failed)} failed and will be retried")
        if self.keep_complete:
            lines.append(
                f"  {len(self.keep_complete)} already complete and will NOT be "
                "re-run: their workbooks are written and verified")
        if self.leave_paused:
            lines.append(
                f"  {len(self.leave_paused)} paused by the researcher and will be "
                "LEFT paused; resuming one is a separate choice")
        return "\n".join(lines) or "  nothing left to do"


def plan_resume(store: RunStore, run_id: str, *, retry_failed: bool = False,
                include_paused: bool = False) -> RecoveryPlan:
    """Decide what RESUME ALL would do, without doing any of it."""
    plan = RecoveryPlan(run_id=run_id)
    for job in store.jobs(run_id):
        if job.state == COMPLETED and job.final_status in FINISHED_STATUSES:
            plan.keep_complete.append(job.job_id)
        elif job.state in (RUNNING, RESUMING, PAUSING):
            plan.requeue.append(job.job_id)
        elif job.state == QUEUED:
            plan.already_queued.append(job.job_id)
        elif job.state in (PAUSED_MANUAL, PAUSED_NETWORK):
            if include_paused or job.state == PAUSED_NETWORK:
                # A network pause is not a decision the researcher made; when
                # the connection is back there is nothing to consult them about.
                plan.requeue.append(job.job_id)
            else:
                plan.leave_paused.append(job.job_id)
        elif job.state == FAILED:
            (plan.retry_failed if retry_failed else plan.keep_complete).append(job.job_id)
        elif job.state == CANCELLED:
            plan.keep_complete.append(job.job_id)
    return plan


def apply_resume(store: RunStore, plan: RecoveryPlan) -> int:
    """Put the plan into effect. Returns how many communities were requeued."""
    moved = 0
    for job_id in plan.requeue:
        store.update_job(job_id, {
            "state": QUEUED, "worker": None,
            "detail": "requeued after the run was interrupted; resumes from its "
                      "own last checkpoint",
        })
        moved += 1
    for job_id in plan.retry_failed:
        job = store.job(job_id)
        store.update_job(job_id, {
            "state": QUEUED, "worker": None, "attempts": 0,
            "detail": f"retried after failing: {(job.last_error if job else '')[:200]}",
        })
        moved += 1
    if moved:
        store.add_event(plan.run_id, "resumed",
                        detail=f"{moved} community(ies) requeued after an interruption")
        event(log, "RESUME", f"{moved} community(ies) requeued")
    return moved


def resume_community(store: RunStore, job_id: str, *, mode: str = "RESUME") -> bool:
    """Put one community back in the queue, without touching the others (§101)."""
    job = store.job(job_id)
    if job is None:
        return False
    if job.state == COMPLETED and job.final_status in FINISHED_STATUSES and mode == "RESUME":
        return False
    store.update_job(job_id, {
        "state": QUEUED, "worker": None, "mode": mode,
        "detail": f"{mode} requested for this community alone",
    })
    row = store.query_one("SELECT run_id FROM jobs WHERE job_id = ?", (job_id,))
    if row is not None:
        store.add_event(str(row["run_id"]), "resumed", job_id=job_id,
                        detail=f"{mode} requested for this community alone")
    return True


def queue_offline_pass(store: RunStore, run_id: str, mode: str, *,
                       job_ids: Sequence[str] | None = None) -> list[str]:
    """Queue EXPORT, RECONCILE or AUDIT over communities already crawled.

    The expensive part is done and stored; these rebuild what comes after it
    without a single request to the network. A run whose crawling succeeded and
    whose export failed must never have to crawl again to get a workbook
    (brief §102, §103, §105).
    """
    if mode not in OFFLINE_MODES:
        raise ValueError(f"{mode!r} is not an offline recovery mode; "
                         f"expected one of {', '.join(OFFLINE_MODES)}")
    wanted = set(job_ids or ())
    queued: list[str] = []
    for job in store.jobs(run_id):
        if wanted and job.job_id not in wanted:
            continue
        if not job.database_path or not Path(job.database_path).exists():
            # Nothing was ever stored for this community, so there is nothing to
            # export or reconcile. Saying so beats a puzzling empty workbook.
            continue
        store.update_job(job.job_id, {
            "state": QUEUED, "mode": mode, "worker": None, "attempts": 0,
            "detail": f"{mode}: rebuilt from stored evidence, no network access",
        })
        queued.append(job.job_id)
    if queued:
        store.add_event(run_id, "started",
                        detail=f"{mode} queued for {len(queued)} community(ies), "
                               "offline")
    return queued


def needs_export(store: RunStore, run_id: str) -> list[JobRow]:
    """Communities whose crawl worked but whose workbook did not (brief §102)."""
    return [job for job in store.jobs(run_id)
            if job.evidence > 0 and not job.workbook_path]


def stale_workers(store: RunStore, run_id: str) -> list[JobRow]:
    """Communities left RUNNING with nobody running them.

    After a crash the queue still says RUNNING, because nothing got the chance
    to say otherwise. Every one of these is retryable, and treating them as
    still-in-progress is how a resumed run stalls (brief §106).
    """
    return [job for job in store.jobs(run_id)
            if job.state in (RUNNING, RESUMING, PAUSING)]


def repair(store: RunStore, run_id: str) -> dict[str, int]:
    """Startup check: make the queue consistent before anything is scheduled.

    A run interrupted mid-transaction comes back consistent because SQLite's
    WAL guarantees it. What it does NOT come back with is a truthful view of
    what was running: those rows still say RUNNING, and nothing is running them.
    This is where that is corrected, once, at startup (brief §106).
    """
    stale = stale_workers(store, run_id)
    for job in stale:
        store.update_job(job.job_id, {
            "state": QUEUED, "worker": None,
            "detail": "left RUNNING by an interrupted session; marked retryable",
        })
    if stale:
        event(log, "REPAIR",
              f"{len(stale)} community(ies) were left RUNNING by an interrupted "
              "session and are retryable")
        store.add_event(run_id, "started",
                        detail=f"startup repair: {len(stale)} stale RUNNING row(s) requeued")
    return {"requeued": len(stale)}


__all__ = [
    "FINISHED_STATUSES", "InterruptedRun", "OFFLINE_MODES", "RecoveryPlan",
    "apply_resume", "find_interrupted", "needs_export", "plan_resume",
    "queue_offline_pass", "repair", "resume_community", "stale_workers",
]
