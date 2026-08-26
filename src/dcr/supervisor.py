"""The supervisor: the one place that decides whether the crawl may continue.

The crawler, the runner and the discovery stages all ask the same question at
their safe boundaries — *may I start the next piece of work?* — and this answers
it. Keeping the decision in one object is what stops manual pause and network
pause drifting apart, and what makes "we stopped, and here is exactly why"
something the software knows rather than something a person reconstructs
afterwards.

A safe boundary is a point where nothing is half-written: the previous task has
been committed to the database and the next has not started. Pausing there is
what makes resuming exact (brief §23).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Sequence

from .control import (CANCELLED, PAUSED_MANUAL, PAUSED_NETWORK, RUNNING,
                      RunCancelled, RunControl)
from .logging_setup import event, get_logger
from .net.connectivity import FULL, OFFLINE, PARTIAL, ConnectivityMonitor, classify_failures

log = get_logger("supervisor")


class RunPaused(Exception):
    """Raised to unwind the run when a pause should end the process.

    Only used when `manual_pause_behavior` is `exit`: the state is already
    PAUSED_MANUAL in the database, and the run will be continued later.
    """

    def __init__(self, state: str, reason: str = ""):
        super().__init__(reason or state)
        self.state = state
        self.reason = reason


@dataclass
class SupervisorStats:
    gates: int = 0
    manual_pauses: int = 0
    network_pauses: int = 0
    connectivity_checks: int = 0
    offline_s: float = 0.0
    paused_manual_s: float = 0.0


class Supervisor:
    """Gate-keeper for a running crawl.

    ``gate()`` is cheap — a clock comparison and, at most, a stat of three
    files — so it can be called between every task without slowing the crawl.
    The expensive part, an actual connectivity probe, happens only when
    failures suggest it is worth making.
    """

    def __init__(
        self,
        control: RunControl,
        monitor: ConnectivityMonitor | None = None,
        *,
        config: Mapping[str, Any] | None = None,
        on_status: Callable[[str], None] | None = None,
        on_resume: Callable[[str], None] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ):
        self.control = control
        self.monitor = monitor
        config = dict(config or {})
        #: `wait` keeps the process alive so RESUME continues in place;
        #: `exit` checkpoints and returns, leaving the run PAUSED_MANUAL for a
        #: later session to pick up (brief §45).
        self.manual_pause_behavior = str(config.get("manual_pause_behavior", "wait"))
        self.resume_poll_s = float(config.get("resume_poll_interval_s", 2.0))
        self.offline_wait_s = float(config.get("offline_wait_interval_s", 15.0))
        #: How long to wait for the network before giving up and leaving the run
        #: PAUSED_NETWORK. `0` means wait indefinitely, which is the default:
        #: an outage is not a reason to declare the research finished.
        self.max_offline_wait_s = float(config.get("max_offline_wait_s", 0) or 0)
        #: Consecutive network-shaped failures before a probe is worth making.
        self.failure_threshold = int(config.get("failures_before_probe", 3))
        self.stats = SupervisorStats()
        self._on_status = on_status
        #: Called when a pause ends, so the fetcher can forget the circuits it
        #: opened while nothing was reachable.
        self._on_resume = on_resume
        self._sleep = sleep or asyncio.sleep
        self._recent_failures: list[str] = []
        self._suspended = False

    # -- what the crawl reports to us --------------------------------------
    def note_failure(self, error_type: str | None) -> None:
        """A fetch failed. Enough of these, of the right shape, triggers a probe."""
        if not error_type:
            return
        self._recent_failures.append(error_type)
        if len(self._recent_failures) > 12:
            del self._recent_failures[:-12]

    def note_success(self) -> None:
        """A fetch worked, so the machine is demonstrably online."""
        self._recent_failures.clear()
        if self.control.connectivity == OFFLINE:
            self.control.set_connectivity(FULL, "a request succeeded")

    def _failures_suggest_outage(self) -> bool:
        if len(self._recent_failures) < self.failure_threshold:
            return False
        recent = self._recent_failures[-self.failure_threshold:]
        return classify_failures(recent, minimum=self.failure_threshold) == OFFLINE

    # -- the gate ----------------------------------------------------------
    async def gate(
        self,
        *,
        stage_no: int | None = None,
        stage_name: str | None = None,
        source_id: str | None = None,
        task_ref: str | None = None,
        task_detail: str | None = None,
        tasks_done: int | None = None,
        tasks_total: int | None = None,
        probe: bool | None = None,
    ) -> None:
        """May the next task start?

        Returns normally when the answer is yes. Blocks while the run is
        paused, raises :class:`RunCancelled` when the researcher has cancelled,
        and raises :class:`RunPaused` when a pause should end this process.
        """
        self.stats.gates += 1
        self.control.checkpoint(
            stage_no=stage_no, stage_name=stage_name, source_id=source_id,
            task_ref=task_ref, task_detail=task_detail,
            tasks_done=tasks_done, tasks_total=tasks_total,
        )

        request = self.control.poll_request()
        if request is not None:
            if request.state == CANCELLED:
                self.control.clear_request()
                self.control.enter_cancelled(request.reason or "cancelled by the researcher")
                raise RunCancelled(request.reason or "cancelled by the researcher")
            if request.state == PAUSED_MANUAL:
                self.control.clear_request()
                await self._pause_manually(request.reason)
            elif request.state == RUNNING and self.control.is_paused():
                self.control.clear_request()
                self.control.enter_running("resume requested")

        should_probe = probe if probe is not None else self._failures_suggest_outage()
        if should_probe and self.monitor is not None:
            await self._check_network()

    # -- manual pause ------------------------------------------------------
    async def _pause_manually(self, reason: str) -> None:
        detail = reason or "paused by the researcher"
        self.control.begin_pause("manual", detail)
        # Everything up to here is already committed; write the boundary down
        # before announcing the pause, so a machine switched off during the
        # pause still resumes from the right place.
        self.control.checkpoint(record_event=True)
        self.control.enter_paused("manual", detail)
        self.stats.manual_pauses += 1
        self._status(f"Status: PAUSED_MANUAL   {self.control.progress_line()}")

        if self.manual_pause_behavior == "exit":
            raise RunPaused(PAUSED_MANUAL, detail)

        started = time.monotonic()
        while True:
            await self._sleep(self.resume_poll_s)
            request = self.control.poll_request(force=True)
            if request is None:
                continue
            if request.state == CANCELLED:
                self.control.clear_request()
                self.control.enter_cancelled(request.reason or "cancelled while paused")
                raise RunCancelled(request.reason or "cancelled while paused")
            if request.state == RUNNING:
                self.control.clear_request()
                break
        waited = time.monotonic() - started
        self.stats.paused_manual_s += waited
        self.control.enter_resuming("manual", f"paused for {waited:.0f}s")
        # A laptop that was closed for an hour may have lost its network in the
        # meantime, so check before trusting it.
        if self.monitor is not None:
            report = await self.monitor.verify_usable()
            self.control.set_connectivity(report.status, report.detail)
            if report.offline:
                await self._pause_for_network(report.detail)
        self._notify_resume("manual")
        self.control.enter_running("resumed by the researcher")
        self._status(f"Status: RUNNING   resumed at {self._where()}")

    # -- network pause -----------------------------------------------------
    async def _check_network(self) -> None:
        if self.monitor is None:
            return
        self.stats.connectivity_checks += 1
        report = await self.monitor.check(force=True)
        self.control.set_connectivity(report.status, report.detail)
        if report.status == PARTIAL:
            # One service is down; that is an ordinary research fact and the
            # source's own record will say so. The crawl continues.
            self._recent_failures.clear()
            return
        if report.offline:
            await self._pause_for_network(report.detail)

    async def _pause_for_network(self, detail: str) -> None:
        """Stop, write everything down, and wait for the network to come back."""
        if self.monitor is None:
            return
        reason = detail or "the machine has no internet connection"
        self.control.begin_pause("network", reason)
        self.control.checkpoint(record_event=True)
        self.control.enter_paused("network", reason)
        self.stats.network_pauses += 1
        self._suspended = True
        self._status(
            f"Status: PAUSED_NETWORK   Internet unavailable. "
            f"{self.control.progress_line()} Waiting for connectivity...")

        started = time.monotonic()
        cancelled: list[str] = []

        def should_stop() -> bool:
            request = self.control.poll_request(force=True)
            if request is not None and request.state == CANCELLED:
                cancelled.append(request.reason or "cancelled while offline")
                return True
            return False

        def on_attempt(attempt: int, report: Any, delay: float) -> None:
            if attempt == 1 or attempt % 5 == 0:
                self._status(f"  still offline; rechecking in {delay:.0f}s "
                             f"(attempt {attempt})")

        report = await self.monitor.wait_for_restoration(
            should_stop=should_stop,
            on_attempt=on_attempt,
            max_wait_s=self.max_offline_wait_s or None,
            sleep=self._sleep,
        )
        waited = time.monotonic() - started
        self.stats.offline_s += waited

        if cancelled:
            self.control.enter_cancelled(cancelled[0])
            raise RunCancelled(cancelled[0])

        if not report.online:
            # Waited as long as we were told to and the network never came
            # back. The run stops UNFINISHED, in PAUSED_NETWORK: never
            # complete, and never a page of NOT FOUND (brief §13).
            self.control.set_connectivity(OFFLINE, report.detail)
            raise RunPaused(
                PAUSED_NETWORK,
                f"the network did not return within {self.max_offline_wait_s:.0f}s; "
                f"the run is paused with {self.control.progress_line()}")

        self.control.enter_resuming("network", f"offline for {waited:.0f}s")
        verified = await self.monitor.verify_usable()
        self.control.set_connectivity(verified.status, verified.detail)
        if verified.offline:
            # It flickered. Go round again rather than resuming onto a dead
            # connection and recording live sources as unreachable.
            await self._pause_for_network(verified.detail)
            return
        self._recent_failures.clear()
        self._suspended = False
        self._notify_resume("network")
        self.control.enter_running("the network came back")
        self._status(f"Status: RUNNING   Internet restored. Resuming from {self._where()}.")

    # -- helpers -----------------------------------------------------------
    def _notify_resume(self, kind: str) -> None:
        if self._on_resume is None:
            return
        try:
            self._on_resume(kind)
        except Exception:                          # never let cleanup stop a resume
            log.debug("resume callback failed", exc_info=True)

    @property
    def suspended(self) -> bool:
        return self._suspended

    def _where(self) -> str:
        cp = self.control.last_checkpoint
        parts = []
        if cp.stage_no is not None:
            parts.append(f"Stage {cp.stage_no}")
        if cp.source_id:
            parts.append(f"source {cp.source_id}")
        parts.append("the next incomplete task")
        return " / ".join(parts)

    def _status(self, line: str) -> None:
        event(log, "STATUS", line)
        if self._on_status is not None:
            try:
                self._on_status(line)
            except Exception:                       # a display must never stop a crawl
                log.debug("status callback failed", exc_info=True)


class NullSupervisor:
    """A supervisor that always says yes.

    Lets every call site use the same code path whether or not run control is
    active — in EXPORT and AUDIT modes, for instance, which touch no network.
    """

    stats = SupervisorStats()
    suspended = False

    async def gate(self, **kwargs: Any) -> None:
        return None

    def note_failure(self, error_type: str | None) -> None:
        return None

    def note_success(self) -> None:
        return None
