"""Run control: manual pause, network pause, cancel, and the checkpoint behind them.

Three things can stop a long crawl before the protocol finishes: the researcher
asks it to stop, the laptop loses its network, or the machine goes down. None of
them is an absence of evidence, and the difference between them matters to the
finished research, so each is a distinct state with its own reason recorded
(brief §22).

    RUNNING ──pause requested──> PAUSING ──safe boundary──> PAUSED_MANUAL
       │                                                         │
       ├──connection lost──> PAUSED_NETWORK ──restored──> RESUMING ──> RUNNING
       │                                                         │
       ├──cancel requested──> CANCELLING ──> CANCELLED           │
       │                                                         │
       └──stages finished──> COMPLETED            (resume) ──────┘

The state lives in the database, and a request to change it also lives in a file
under the output root. The file is what lets a second process — a `dcr pause`
typed in another terminal, or a button in a separate UI — reach a crawler that
is busy inside an await. The database is what lets the state survive the machine
being switched off: a run that was PAUSED_MANUAL on Friday is still
PAUSED_MANUAL on Monday, and the application offers to resume it rather than
quietly starting a new crawl (brief §21).
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .db import Database, utcnow
from .logging_setup import event, get_logger

log = get_logger("control")

# -- the states ------------------------------------------------------------
RUNNING = "RUNNING"
PAUSING = "PAUSING"
PAUSED_MANUAL = "PAUSED_MANUAL"
PAUSED_NETWORK = "PAUSED_NETWORK"
RESUMING = "RESUMING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
CANCELLING = "CANCELLING"
CANCELLED = "CANCELLED"

ALL_STATES = (RUNNING, PAUSING, PAUSED_MANUAL, PAUSED_NETWORK, RESUMING,
              COMPLETED, FAILED, CANCELLING, CANCELLED)

#: States a run can be continued from. A cancelled run is finished on purpose;
#: a completed one has nothing left to do.
RESUMABLE_STATES = (PAUSED_MANUAL, PAUSED_NETWORK, PAUSING, RESUMING, RUNNING, FAILED)

#: States that mean "not running, and not going to start again on its own".
PAUSED_STATES = (PAUSED_MANUAL, PAUSED_NETWORK)

#: States that end a run.
TERMINAL_STATES = (COMPLETED, FAILED, CANCELLED)

# Names of the request files. A researcher may create these by hand.
PAUSE_FILE = "pause.request"
RESUME_FILE = "resume.request"
CANCEL_FILE = "cancel.request"
STATUS_FILE = "status.json"


class RunCancelled(Exception):
    """Raised inside the run when the researcher has asked for CANCEL."""


@dataclass
class ControlRequest:
    """Something the researcher (or the network monitor) has asked for."""

    state: str
    by: str = "researcher"
    reason: str = ""
    ts_utc: str = ""


@dataclass
class Checkpoint:
    """Where the run had got to when it was last written down."""

    stage_no: int | None = None
    stage_name: str = ""
    source_id: str | None = None
    task_ref: str | None = None
    task_detail: str = ""
    tasks_done: int = 0
    tasks_total: int = 0
    seq: int = 0
    ts_utc: str = ""


class RunControl:
    """The pause/resume/cancel state of one run, persisted as it changes.

    Every method that changes the state writes it to the database before
    returning, so there is no window in which the crawler has stopped but the
    record still says it is running.
    """

    def __init__(
        self,
        db: Database,
        *,
        run_id: str,
        community_id: str,
        control_dir: Path,
        poll_interval_s: float = 1.0,
        shared_control_dirs: Sequence[Path] = (),
    ):
        self.db = db
        self.run_id = run_id
        self.community_id = community_id
        self.control_dir = Path(control_dir)
        self.control_dir.mkdir(parents=True, exist_ok=True)
        #: Control directories that belong to the whole run rather than to this
        #: community. PAUSE ALL writes one file at the run level and every
        #: community sees it; PAUSE C007 writes a file only C007 looks at
        #: (brief §33, §34, §35).
        self.shared_control_dirs = [Path(d) for d in shared_control_dirs]
        for directory in self.shared_control_dirs:
            directory.mkdir(parents=True, exist_ok=True)
        self.poll_interval_s = max(0.05, float(poll_interval_s))

        self._state = RUNNING
        self._pause_reason = ""
        self._connectivity = "UNKNOWN"
        self._connectivity_detail = ""
        self._checkpoint = Checkpoint()
        self._last_poll = 0.0
        self._cached_request: ControlRequest | None = None
        #: Counted for the completion report, so an interrupted run can say how
        #: often and for how long it was stopped.
        self.pauses_manual = 0
        self.pauses_network = 0
        self.paused_manual_s = 0.0
        self.offline_s = 0.0
        self._pause_started: float | None = None

        self._write_state(RUNNING, reason="", event_name="checkpoint")

    # -- reading -----------------------------------------------------------
    @property
    def state(self) -> str:
        return self._state

    @property
    def pause_reason(self) -> str:
        return self._pause_reason

    @property
    def last_checkpoint(self) -> Checkpoint:
        """Where the run had got to when it was last written down."""
        return self._checkpoint

    @property
    def connectivity(self) -> str:
        return self._connectivity

    def is_paused(self) -> bool:
        return self._state in PAUSED_STATES

    def is_cancelled(self) -> bool:
        return self._state in (CANCELLING, CANCELLED)

    # -- requests from outside the run -------------------------------------
    def poll_request(self, *, force: bool = False) -> ControlRequest | None:
        """Has anyone asked this run to pause, resume or cancel?

        Cheap enough to call in the crawler's inner loop: the filesystem is
        only consulted once every ``poll_interval_s``.
        """
        now = time.monotonic()
        if not force and (now - self._last_poll) < self.poll_interval_s:
            return self._cached_request
        self._last_poll = now
        request = self._read_file_request() or self._read_db_request()
        self._cached_request = request
        return request

    def _read_file_request(self) -> ControlRequest | None:
        # Cancel outranks pause, and pause outranks resume: the most
        # conservative instruction the researcher has left behind wins.
        for filename, state in ((CANCEL_FILE, CANCELLED),
                                (PAUSE_FILE, PAUSED_MANUAL),
                                (RESUME_FILE, RUNNING)):
            for directory in (self.control_dir, *self.shared_control_dirs):
                path = directory / filename
                if not path.exists():
                    continue
                reason = ""
                try:
                    reason = path.read_text(encoding="utf-8").strip()
                except OSError:
                    pass
                shared = directory != self.control_dir
                return ControlRequest(
                    state=state, by="researcher" if not shared else "run",
                    reason=reason, ts_utc=utcnow())
        return None

    def _read_db_request(self) -> ControlRequest | None:
        row = self.db.query_one(
            "SELECT requested_state, requested_by, pause_reason, requested_utc "
            "FROM run_control WHERE run_id = ?", (self.run_id,))
        if row is None or not row["requested_state"]:
            return None
        return ControlRequest(
            state=row["requested_state"], by=row["requested_by"] or "researcher",
            reason=row["pause_reason"] or "", ts_utc=row["requested_utc"] or "",
        )

    def clear_request(self) -> None:
        """Consume the request, so the same file does not pause the run twice.

        Run-level request files are deliberately NOT removed: they are addressed
        to every community, and the first one to see PAUSE ALL must not consume
        it on behalf of the other fifteen. The scheduler clears them when the
        researcher resumes.
        """
        for filename in (PAUSE_FILE, RESUME_FILE, CANCEL_FILE):
            path = self.control_dir / filename
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:            # a locked file must not stop the crawl
                log.warning("could not clear %s: %s", path, exc)
        self.db.update("run_control",
                       {"requested_state": None, "requested_by": None,
                        "requested_utc": None, "updated_utc": utcnow()},
                       {"run_id": self.run_id})
        self._cached_request = None
        self._last_poll = 0.0

    # -- transitions -------------------------------------------------------
    def begin_pause(self, kind: str, reason: str) -> None:
        """Enter PAUSING: stop taking new work, let running work finish."""
        if self._state in TERMINAL_STATES:
            return
        self._record_event("pause_requested", kind=kind, to_state=PAUSING, detail=reason)
        self._write_state(PAUSING, reason=reason, event_name=None)

    def enter_paused(self, kind: str, reason: str) -> None:
        """The safe boundary has been reached and everything is written down."""
        state = PAUSED_MANUAL if kind == "manual" else PAUSED_NETWORK
        if self._state == state:
            return
        self._pause_started = time.monotonic()
        if kind == "manual":
            self.pauses_manual += 1
        else:
            self.pauses_network += 1
        self._write_state(state, reason=reason, event_name=None)
        self._record_event("paused", kind=kind, to_state=state, detail=reason)
        if kind == "manual":
            event(log, "PAUSED", f"Manual pause completed safely. {self.progress_line()}")
        else:
            event(log, "PAUSED", f"Crawl paused safely — {reason}. {self.progress_line()}")

    def enter_resuming(self, kind: str, detail: str) -> None:
        if self._pause_started is not None:
            elapsed = time.monotonic() - self._pause_started
            if self._state == PAUSED_MANUAL:
                self.paused_manual_s += elapsed
            elif self._state == PAUSED_NETWORK:
                self.offline_s += elapsed
            self._pause_started = None
        self._record_event("resume_requested", kind=kind, to_state=RESUMING, detail=detail)
        self._write_state(RESUMING, reason="", event_name=None)

    def enter_running(self, detail: str = "") -> None:
        previous = self._state
        self._write_state(RUNNING, reason="", event_name=None)
        if previous != RUNNING:
            self._record_event("resumed", kind="manual" if previous == PAUSED_MANUAL
                               else "network", to_state=RUNNING, detail=detail)

    def request_cancel(self, reason: str = "") -> None:
        self._record_event("cancel_requested", kind="manual", to_state=CANCELLING,
                           detail=reason)
        self._write_state(CANCELLING, reason=reason, event_name=None)

    def enter_cancelled(self, reason: str = "") -> None:
        self._write_state(CANCELLED, reason=reason, event_name=None, resumable=False)
        self._record_event("cancelled", kind="manual", to_state=CANCELLED, detail=reason)
        event(log, "CANCELLED", f"Run cancelled. {self.progress_line()} "
                                "Everything retrieved so far is saved.")

    def finish(self, state: str, reason: str = "") -> None:
        """Close the run in a terminal state — COMPLETED, FAILED or CANCELLED."""
        resumable = state not in (COMPLETED, CANCELLED)
        self._write_state(state, reason=reason, event_name=None, resumable=resumable)

    def set_connectivity(self, status: str, detail: str = "") -> None:
        if status == self._connectivity:
            return
        previous = self._connectivity
        self._connectivity = status
        self._connectivity_detail = detail
        self.db.update("run_control",
                       {"connectivity": status, "connectivity_detail": detail[:500],
                        "updated_utc": utcnow()},
                       {"run_id": self.run_id})
        if status == "OFFLINE":
            self._record_event("connectivity_lost", kind="network", detail=detail)
        elif previous == "OFFLINE":
            self._record_event("connectivity_restored", kind="network", detail=detail)

    # -- checkpointing -----------------------------------------------------
    def checkpoint(
        self,
        *,
        stage_no: int | None = None,
        stage_name: str | None = None,
        source_id: str | None = None,
        task_ref: str | None = None,
        task_detail: str | None = None,
        tasks_done: int | None = None,
        tasks_total: int | None = None,
        record_event: bool = False,
    ) -> Checkpoint:
        """Write down where the run has got to.

        Called after each page, document, image batch, source and stage, and
        immediately when a pause is requested or the network drops (brief §24).
        """
        cp = self._checkpoint
        if stage_no is not None:
            cp.stage_no = stage_no
        if stage_name is not None:
            cp.stage_name = stage_name
        if source_id is not None:
            cp.source_id = source_id
        if task_ref is not None:
            cp.task_ref = task_ref
        if task_detail is not None:
            cp.task_detail = task_detail
        if tasks_done is not None:
            cp.tasks_done = tasks_done
        if tasks_total is not None:
            cp.tasks_total = tasks_total
        cp.seq += 1
        cp.ts_utc = utcnow()
        self.db.update(
            "run_control",
            {"stage_no": cp.stage_no, "stage_name": cp.stage_name,
             "source_id": cp.source_id, "task_ref": cp.task_ref,
             "task_detail": (cp.task_detail or "")[:500],
             "tasks_done": cp.tasks_done, "tasks_total": cp.tasks_total,
             "checkpoint_utc": cp.ts_utc, "checkpoint_seq": cp.seq,
             "updated_utc": cp.ts_utc},
            {"run_id": self.run_id},
        )
        if record_event:
            self._record_event("checkpoint", kind="unknown", detail=cp.task_detail)
        self._write_status_file()
        return cp

    # -- reporting ---------------------------------------------------------
    def progress_line(self) -> str:
        cp = self._checkpoint
        if cp.tasks_total:
            return f"{cp.tasks_done}/{cp.tasks_total} tasks complete."
        return f"{cp.tasks_done} tasks complete."

    def status(self) -> dict[str, Any]:
        cp = self._checkpoint
        return {
            "run_id": self.run_id,
            "community_id": self.community_id,
            "state": self._state,
            "pause_reason": self._pause_reason,
            "connectivity": self._connectivity,
            "connectivity_detail": self._connectivity_detail,
            "stage_no": cp.stage_no,
            "stage_name": cp.stage_name,
            "source_id": cp.source_id,
            "task_ref": cp.task_ref,
            "tasks_done": cp.tasks_done,
            "tasks_total": cp.tasks_total,
            "checkpoint_utc": cp.ts_utc,
            "pauses_manual": self.pauses_manual,
            "pauses_network": self.pauses_network,
            "updated_utc": utcnow(),
        }

    def _write_status_file(self) -> None:
        """A human- and machine-readable status the researcher can watch."""
        path = self.control_dir / STATUS_FILE
        try:
            _atomic_write_text(path, json.dumps(self.status(), indent=2, ensure_ascii=False))
        except OSError as exc:
            log.debug("could not write status file: %s", exc)

    # -- internals ---------------------------------------------------------
    def _write_state(self, state: str, *, reason: str, event_name: str | None,
                     resumable: bool | None = None) -> None:
        self._state = state
        self._pause_reason = reason
        cp = self._checkpoint
        values = {
            "run_id": self.run_id,
            "community_id": self.community_id,
            "state": state,
            "pause_reason": reason[:1000] if reason else None,
            "connectivity": self._connectivity,
            "stage_no": cp.stage_no,
            "stage_name": cp.stage_name,
            "source_id": cp.source_id,
            "task_ref": cp.task_ref,
            "tasks_done": cp.tasks_done,
            "tasks_total": cp.tasks_total,
            "updated_utc": utcnow(),
        }
        if resumable is not None:
            values["resumable"] = int(resumable)
        self.db.upsert("run_control", values, ["run_id"])
        # run_control is the detail; runs.status is what every existing report
        # already reads, so the two must never disagree.
        self.db.update("runs", {"status": _run_status_for(state), "final_state": state},
                       {"run_id": self.run_id})
        if event_name:
            self._record_event(event_name, kind="unknown", to_state=state, detail=reason)
        self._write_status_file()

    def _record_event(self, name: str, *, kind: str = "unknown",
                      to_state: str | None = None, detail: str = "") -> None:
        cp = self._checkpoint
        self.db.insert("pause_events", {
            "run_id": self.run_id,
            "community_id": self.community_id,
            "event": name,
            "kind": kind,
            "from_state": self._state,
            "to_state": to_state or self._state,
            "stage_no": cp.stage_no,
            "source_id": cp.source_id,
            "task_ref": cp.task_ref,
            "tasks_done": cp.tasks_done,
            "tasks_total": cp.tasks_total,
            "detail": (detail or "")[:2000],
            "ts_utc": utcnow(),
        })


def _run_status_for(state: str) -> str:
    """The `runs.status` value matching a control state.

    An interrupted run is never `complete`: that is the whole point of the
    distinction (brief §13).
    """
    return {
        RUNNING: "running",
        PAUSING: "running",
        RESUMING: "running",
        PAUSED_MANUAL: "paused_manual",
        PAUSED_NETWORK: "paused_network",
        COMPLETED: "complete",
        FAILED: "failed",
        CANCELLING: "running",
        CANCELLED: "cancelled",
    }.get(state, "running")


def _atomic_write_text(path: Path, text: str) -> None:
    """Write via a temporary file and rename, so a reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(path.parent), delete=False, suffix=".tmp")
    try:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    finally:
        handle.close()
    os.replace(handle.name, path)


# ===========================================================================
# Asking a running crawl to stop, from anywhere
# ===========================================================================
def control_dir_for(output_root: Path) -> Path:
    path = Path(output_root) / "control"
    path.mkdir(parents=True, exist_ok=True)
    return path


def request_pause(output_root: Path, reason: str = "") -> Path:
    """Ask the running crawl to pause. Safe to call when nothing is running."""
    path = control_dir_for(output_root) / PAUSE_FILE
    _atomic_write_text(path, reason or f"paused by the researcher at {utcnow()}")
    _clear(control_dir_for(output_root) / RESUME_FILE)
    return path


def request_resume(output_root: Path, reason: str = "") -> Path:
    path = control_dir_for(output_root) / RESUME_FILE
    _atomic_write_text(path, reason or f"resumed by the researcher at {utcnow()}")
    _clear(control_dir_for(output_root) / PAUSE_FILE)
    return path


def request_cancel(output_root: Path, reason: str = "") -> Path:
    path = control_dir_for(output_root) / CANCEL_FILE
    _atomic_write_text(path, reason or f"cancelled by the researcher at {utcnow()}")
    return path


def clear_requests(output_root: Path) -> None:
    directory = control_dir_for(output_root)
    for name in (PAUSE_FILE, RESUME_FILE, CANCEL_FILE):
        _clear(directory / name)


def _clear(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def read_status(output_root: Path) -> dict[str, Any] | None:
    path = control_dir_for(output_root) / STATUS_FILE
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# ===========================================================================
# Finding a run that was left unfinished
# ===========================================================================
@dataclass
class InterruptedRun:
    """A previous run the application can offer to continue (brief §21)."""

    run_id: str
    community_id: str
    community_name: str
    state: str
    pause_reason: str
    stage_no: int | None
    stage_name: str
    source_id: str | None
    tasks_done: int
    tasks_total: int
    checkpoint_utc: str
    mode: str
    pending_tasks: int = 0

    @property
    def was_manual(self) -> bool:
        return self.state == PAUSED_MANUAL

    def describe(self) -> str:
        where = f"Stage {self.stage_no}" if self.stage_no is not None else "before stage 0"
        if self.stage_name:
            where += f" ({self.stage_name})"
        if self.source_id:
            where += f" / source {self.source_id}"
        progress = (f"{self.tasks_done}/{self.tasks_total}" if self.tasks_total
                    else str(self.tasks_done))
        return (f"{self.community_name} — {self.state} at {where}, "
                f"{progress} tasks complete, last checkpoint {self.checkpoint_utc}")


def find_interrupted_runs(db: Database, *, limit: int = 10) -> list[InterruptedRun]:
    """Runs that stopped without finishing, newest first.

    A run left in RUNNING is included: that is what a power cut or a closed
    PyCharm looks like from the outside, and `RUNNING` must never be read as
    `finished` (brief §25).
    """
    marks = ", ".join("?" for _ in RESUMABLE_STATES)
    rows = db.query(
        "SELECT c.*, r.mode AS run_mode, cm.name_input AS community_name "
        "FROM run_control c "
        "JOIN runs r ON r.run_id = c.run_id "
        "LEFT JOIN communities cm ON cm.community_id = c.community_id "
        f"WHERE c.state IN ({marks}) AND COALESCE(c.resumable, 1) = 1 "
        "ORDER BY c.updated_utc DESC LIMIT ?",
        list(RESUMABLE_STATES) + [limit],
    )
    found: list[InterruptedRun] = []
    for row in rows:
        pending = int(db.scalar(
            "SELECT COUNT(*) FROM frontier WHERE community_id = ? "
            "AND status IN ('queued', 'in_flight')", (row["community_id"],)) or 0)
        found.append(InterruptedRun(
            run_id=row["run_id"],
            community_id=row["community_id"],
            community_name=row["community_name"] or row["community_id"],
            state=row["state"],
            pause_reason=row["pause_reason"] or "",
            stage_no=row["stage_no"],
            stage_name=row["stage_name"] or "",
            source_id=row["source_id"],
            tasks_done=int(row["tasks_done"] or 0),
            tasks_total=int(row["tasks_total"] or 0),
            checkpoint_utc=row["checkpoint_utc"] or row["updated_utc"],
            mode=row["run_mode"] or "FULL",
            pending_tasks=pending,
        ))
    return found
