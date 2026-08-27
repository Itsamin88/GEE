"""The run-level database: the queue, and deliberately nothing else.

There are two kinds of database in a multi-community run, and keeping them apart
is what makes the isolation the brief asks for real (§8, §39).

**One database per community**, in that community's own output directory, holds
its sources, documents, evidence, claims and field values. Nothing else reads or
writes it. A half-written transaction, a corrupt page, a disk full at exactly
the wrong moment — none of it can reach another community, because no other
process has the file open. It also means sixteen workers are not queueing behind
one SQLite writer lock, which is the difference between parallelism and the
appearance of it.

**One run database**, here, holds the queue: which communities exist, what state
each is in, what it produced, and what the scheduler decided. It is small, it is
written by the parent process only, and workers never touch it. Worker progress
arrives as events over a pipe and the parent writes it down.

    Research_Web_Crawler_Output/
        run.sqlite3                 <- this file: the queue
        IC001_tamera/
            research.sqlite3        <- one community's evidence
            09_final/IC001_....xlsx
        IC002_pourgues/
            research.sqlite3
            ...

Every state change is a single transaction, so a run interrupted between two of
them comes back consistent. The queue is the authority on what has been done:
the recovery path reads it, not the filesystem.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ..db import utcnow
from ..logging_setup import get_logger

log = get_logger("orchestrator.store")

SCHEMA_VERSION = "2.0.0"

# ---------------------------------------------------------------------------
# The states a community moves through
# ---------------------------------------------------------------------------
QUEUED = "QUEUED"
RUNNING = "RUNNING"
PAUSING = "PAUSING"
PAUSED_MANUAL = "PAUSED_MANUAL"
PAUSED_NETWORK = "PAUSED_NETWORK"
RESUMING = "RESUMING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
CANCELLED = "CANCELLED"

JOB_STATES = (QUEUED, RUNNING, PAUSING, PAUSED_MANUAL, PAUSED_NETWORK, RESUMING,
              COMPLETED, FAILED, CANCELLED)

#: States from which a community can be picked up again.
RESUMABLE_JOB_STATES = (QUEUED, PAUSED_MANUAL, PAUSED_NETWORK, PAUSING, RESUMING,
                        RUNNING, FAILED)

#: States that mean the community is finished, one way or another.
TERMINAL_JOB_STATES = (COMPLETED, FAILED, CANCELLED)

#: What the scheduler as a whole is doing.
RUN_RUNNING = "RUNNING"
RUN_PAUSED = "PAUSED"
RUN_CANCELLING = "CANCELLING"
RUN_CANCELLED = "CANCELLED"
RUN_COMPLETED = "COMPLETED"

#: Priorities are on a 0-100 scale (see `RunPlan.order`). Waiting adds one point
#: a minute up to `AGE_CAP`, which is just above the full range: a community
#: that has waited a hundred minutes outranks anything that arrived after it,
#: however large. That is the anti-starvation guarantee (brief §5).
AGE_PER_MINUTE = 1.0
AGE_CAP = 110.0


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- One row per multi-community run.
CREATE TABLE IF NOT EXISTS runs (
    run_id          TEXT PRIMARY KEY,
    label           TEXT,
    status          TEXT NOT NULL,     -- RUNNING | PAUSED | CANCELLING | CANCELLED | COMPLETED
    mode            TEXT NOT NULL,     -- FULL | RESUME | EXPORT | ...
    output_root     TEXT NOT NULL,
    app_version     TEXT,
    config_sha256   TEXT,
    community_count INTEGER DEFAULT 0,
    created_utc     TEXT NOT NULL,
    started_utc     TEXT,
    finished_utc    TEXT,
    -- Wall-clock and active seconds for the whole run, kept up to date so a
    -- crash does not lose the accounting.
    wall_s          REAL DEFAULT 0,
    paused_s        REAL DEFAULT 0,
    notes           TEXT
);

-- One row per community. This IS the queue.
CREATE TABLE IF NOT EXISTS jobs (
    job_id          TEXT PRIMARY KEY,   -- C001 ... C212, the queue position
    run_id          TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    site_id         TEXT NOT NULL,      -- IC001 ... the workbook's site_id
    name            TEXT NOT NULL,
    latitude        REAL,
    longitude       REAL,
    country         TEXT,
    coder_id        TEXT,
    urls            TEXT NOT NULL,      -- JSON array, exactly as supplied
    mode            TEXT NOT NULL DEFAULT 'FULL',
    fixture         INTEGER DEFAULT 0,

    state           TEXT NOT NULL,      -- see JOB_STATES
    stage_no        INTEGER,
    stage_name      TEXT,
    detail          TEXT,
    progress        REAL DEFAULT 0,     -- 0..1, the scheduler's own estimate

    -- Sizing, before and after discovery (brief SS45, SS46).
    workload_units  REAL DEFAULT 0,
    estimate_low_s  REAL DEFAULT 0,
    estimate_high_s REAL DEFAULT 0,
    estimate_basis  TEXT,

    -- Fair scheduling.
    priority        REAL DEFAULT 0,
    queued_utc      TEXT,
    aged_priority   REAL DEFAULT 0,     -- priority + how long it has waited
    attempts        INTEGER DEFAULT 0,
    worker          TEXT,

    -- What it produced.
    pages           INTEGER DEFAULT 0,
    documents       INTEGER DEFAULT 0,
    images          INTEGER DEFAULT 0,
    evidence        INTEGER DEFAULT 0,
    claims          INTEGER DEFAULT 0,
    sources         INTEGER DEFAULT 0,
    conflicts       INTEGER DEFAULT 0,
    yield_units     REAL DEFAULT 0,
    active_s        REAL DEFAULT 0,
    wall_s          REAL DEFAULT 0,
    offline_s       REAL DEFAULT 0,
    paused_s        REAL DEFAULT 0,

    -- How it ended.
    final_status    TEXT,               -- COMPLETE | COMPLETE_WITH_TRUNCATION | ...
    workbook_path   TEXT,
    workbook_verified INTEGER DEFAULT 0,
    output_dir      TEXT,
    database_path   TEXT,
    last_error      TEXT,
    error_class     TEXT,
    started_utc     TEXT,
    finished_utc    TEXT,
    updated_utc     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_run_state ON jobs(run_id, state);
CREATE INDEX IF NOT EXISTS idx_jobs_priority ON jobs(run_id, state, aged_priority DESC);

-- Append-only. Everything that happened to a community, in order, so a run can
-- be explained afterwards rather than reconstructed.
CREATE TABLE IF NOT EXISTS job_events (
    event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     TEXT NOT NULL,
    job_id     TEXT,
    kind       TEXT NOT NULL,
    stage_no   INTEGER,
    detail     TEXT,
    payload    TEXT,
    ts_utc     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_job_events ON job_events(run_id, event_id);

-- What the scheduler decided and why, sampled as it runs. This is what makes
-- "eleven workers" an observation rather than a claim (brief SS93, SS96).
CREATE TABLE IF NOT EXISTS scheduler_samples (
    sample_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL,
    workers     INTEGER,
    target      INTEGER,
    running     INTEGER,
    queued      INTEGER,
    paused      INTEGER,
    completed   INTEGER,
    failed      INTEGER,
    cpu_pct     REAL,
    memory_pct  REAL,
    load_avg    REAL,
    open_conns  INTEGER,
    decision    TEXT,
    reason      TEXT,
    ts_utc      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scheduler_samples ON scheduler_samples(run_id, sample_id);

-- What each host did to us, pooled across communities. A host that rate-limited
-- C003 should not have to rate-limit C004 as well before anyone notices.
CREATE TABLE IF NOT EXISTS host_stats (
    host           TEXT PRIMARY KEY,
    requests       INTEGER DEFAULT 0,
    failures       INTEGER DEFAULT 0,
    rate_limited   INTEGER DEFAULT 0,
    blocked        INTEGER DEFAULT 0,
    mean_latency_s REAL DEFAULT 0,
    delay_s        REAL DEFAULT 0,     -- the politeness delay currently in force
    concurrency    INTEGER DEFAULT 0,  -- what the broker will currently allow
    updated_utc    TEXT
);

-- Errors, per community, so one failure is a row rather than a stack trace in a
-- log nobody reads (brief SS39, SS54).
CREATE TABLE IF NOT EXISTS run_errors (
    error_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL,
    job_id      TEXT,
    error_class TEXT,
    message     TEXT,
    detail      TEXT,
    fatal       INTEGER DEFAULT 0,
    ts_utc      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_run_errors ON run_errors(run_id, error_id);
"""


@dataclass
class JobRow:
    """A community as the scheduler sees it. A thin view over one `jobs` row."""

    job_id: str
    site_id: str
    name: str
    state: str
    urls: list[str]
    latitude: float | None = None
    longitude: float | None = None
    country: str | None = None
    coder_id: str = ""
    mode: str = "FULL"
    fixture: bool = False
    priority: float = 0.0
    aged_priority: float = 0.0
    workload_units: float = 0.0
    estimate_low_s: float = 0.0
    estimate_high_s: float = 0.0
    attempts: int = 0
    stage_no: int | None = None
    stage_name: str = ""
    detail: str = ""
    progress: float = 0.0
    final_status: str = ""
    workbook_path: str = ""
    #: True only once the workbook has been written AND reopened from disk.
    #: The column has always been recorded; leaving it off this view meant
    #: anything reading a JobRow could see the path but not whether the file
    #: behind it had verified (brief §12, §91, §92).
    workbook_verified: bool = False
    output_dir: str = ""
    database_path: str = ""
    last_error: str = ""
    active_s: float = 0.0
    wall_s: float = 0.0
    yield_units: float = 0.0
    pages: int = 0
    documents: int = 0
    images: int = 0
    evidence: int = 0
    sources: int = 0
    conflicts: int = 0

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "JobRow":
        def get(key: str, default: Any = None) -> Any:
            try:
                value = row[key]
            except (KeyError, IndexError):
                return default
            return default if value is None else value

        return cls(
            job_id=get("job_id", ""), site_id=get("site_id", ""), name=get("name", ""),
            state=get("state", QUEUED), urls=json.loads(get("urls", "[]") or "[]"),
            latitude=row["latitude"], longitude=row["longitude"],
            country=row["country"], coder_id=get("coder_id", ""),
            mode=get("mode", "FULL"), fixture=bool(get("fixture", 0)),
            priority=float(get("priority", 0.0)),
            aged_priority=float(get("aged_priority", 0.0)),
            workload_units=float(get("workload_units", 0.0)),
            estimate_low_s=float(get("estimate_low_s", 0.0)),
            estimate_high_s=float(get("estimate_high_s", 0.0)),
            attempts=int(get("attempts", 0)), stage_no=row["stage_no"],
            stage_name=get("stage_name", ""), detail=get("detail", ""),
            progress=float(get("progress", 0.0)),
            final_status=get("final_status", ""),
            workbook_path=get("workbook_path", ""),
            workbook_verified=bool(get("workbook_verified", 0)),
            output_dir=get("output_dir", ""), database_path=get("database_path", ""),
            last_error=get("last_error", ""), active_s=float(get("active_s", 0.0)),
            wall_s=float(get("wall_s", 0.0)),
            yield_units=float(get("yield_units", 0.0)),
            pages=int(get("pages", 0)), documents=int(get("documents", 0)),
            images=int(get("images", 0)), evidence=int(get("evidence", 0)),
            sources=int(get("sources", 0)), conflicts=int(get("conflicts", 0)),
        )


class RunStore:
    """The queue, on disk. Opened by the parent process; never by a worker."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), timeout=30.0,
                                     check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # WAL so a reader — the dashboard, or a second terminal asking for
        # status — never blocks the scheduler's writes (brief §37).
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
                (SCHEMA_VERSION,))
            self._conn.commit()

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        with self._lock:
            try:
                self._conn.commit()
            finally:
                self._conn.close()

    def __enter__(self) -> "RunStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- low level ---------------------------------------------------------
    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._conn.execute(sql, tuple(params))
            self._conn.commit()
            return cursor

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, tuple(params)))

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        row = self.query_one(sql, params)
        return row[0] if row else None

    # -- runs --------------------------------------------------------------
    def create_run(self, run_id: str, *, mode: str, output_root: Path,
                   label: str = "", app_version: str = "",
                   config_sha256: str = "") -> None:
        self.execute(
            "INSERT OR REPLACE INTO runs(run_id, label, status, mode, output_root, "
            "app_version, config_sha256, created_utc, started_utc) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (run_id, label, RUN_RUNNING, mode, str(output_root), app_version,
             config_sha256, utcnow(), utcnow()))

    def set_run_status(self, run_id: str, status: str, *, notes: str = "") -> None:
        values = {"status": status}
        if status in (RUN_CANCELLED, RUN_COMPLETED):
            values["finished_utc"] = utcnow()
        if notes:
            values["notes"] = notes
        assignments = ", ".join(f"{k} = ?" for k in values)
        self.execute(f"UPDATE runs SET {assignments} WHERE run_id = ?",
                     (*values.values(), run_id))

    def run_status(self, run_id: str) -> str:
        return str(self.scalar("SELECT status FROM runs WHERE run_id = ?",
                               (run_id,)) or "")

    def latest_run(self) -> sqlite3.Row | None:
        return self.query_one("SELECT * FROM runs ORDER BY created_utc DESC LIMIT 1")

    def unfinished_runs(self) -> list[sqlite3.Row]:
        """Runs that were interrupted rather than finished (brief §100)."""
        return self.query(
            "SELECT * FROM runs WHERE status NOT IN (?, ?) ORDER BY created_utc DESC",
            (RUN_COMPLETED, RUN_CANCELLED))

    # -- jobs --------------------------------------------------------------
    def add_job(self, run_id: str, job: Mapping[str, Any]) -> None:
        values = {
            "job_id": job["job_id"],
            "run_id": run_id,
            "site_id": job["site_id"],
            "name": job["name"],
            "latitude": job.get("latitude"),
            "longitude": job.get("longitude"),
            "country": job.get("country"),
            "coder_id": job.get("coder_id", ""),
            "urls": json.dumps(list(job.get("urls") or [])),
            "mode": job.get("mode", "FULL"),
            "fixture": int(bool(job.get("fixture", False))),
            "state": job.get("state", QUEUED),
            "priority": float(job.get("priority", 0.0)),
            "aged_priority": float(job.get("priority", 0.0)),
            "queued_utc": utcnow(),
            "workload_units": float(job.get("workload_units", 0.0)),
            "estimate_low_s": float(job.get("estimate_low_s", 0.0)),
            "estimate_high_s": float(job.get("estimate_high_s", 0.0)),
            "estimate_basis": job.get("estimate_basis", ""),
            "output_dir": job.get("output_dir", ""),
            "database_path": job.get("database_path", ""),
            "updated_utc": utcnow(),
        }
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        self.execute(f"INSERT OR REPLACE INTO jobs({columns}) VALUES({placeholders})",
                     tuple(values.values()))

    def update_job(self, job_id: str, values: Mapping[str, Any]) -> None:
        if not values:
            return
        payload = {**values, "updated_utc": utcnow()}
        assignments = ", ".join(f"{key} = ?" for key in payload)
        self.execute(f"UPDATE jobs SET {assignments} WHERE job_id = ?",
                     (*payload.values(), job_id))

    def set_job_state(self, job_id: str, state: str, *, detail: str = "") -> None:
        values: dict[str, Any] = {"state": state}
        if detail:
            values["detail"] = detail
        if state == RUNNING:
            values["started_utc"] = utcnow()
        if state in TERMINAL_JOB_STATES:
            values["finished_utc"] = utcnow()
        self.update_job(job_id, values)

    def job(self, job_id: str) -> JobRow | None:
        row = self.query_one("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        return JobRow.from_row(row) if row else None

    def jobs(self, run_id: str, *, states: Sequence[str] | None = None) -> list[JobRow]:
        if states:
            marks = ", ".join("?" for _ in states)
            rows = self.query(
                f"SELECT * FROM jobs WHERE run_id = ? AND state IN ({marks}) "
                "ORDER BY job_id", (run_id, *states))
        else:
            rows = self.query("SELECT * FROM jobs WHERE run_id = ? ORDER BY job_id",
                              (run_id,))
        return [JobRow.from_row(row) for row in rows]

    def counts(self, run_id: str) -> dict[str, int]:
        rows = self.query(
            "SELECT state, COUNT(*) AS n FROM jobs WHERE run_id = ? GROUP BY state",
            (run_id,))
        counts = {state: 0 for state in JOB_STATES}
        for row in rows:
            counts[str(row["state"])] = int(row["n"])
        counts["TOTAL"] = sum(int(row["n"]) for row in rows)
        return counts

    def claim_next(self, run_id: str, *, worker: str,
                   exclude: Iterable[str] = ()) -> JobRow | None:
        """Take the highest-priority runnable community, atomically.

        The claim is a single UPDATE guarded by the state, so two workers asking
        at the same moment cannot both get the same community: the second one's
        UPDATE matches no row and it asks again.
        """
        blocked = {str(item) for item in exclude}
        with self._lock:
            candidates = self._conn.execute(
                "SELECT * FROM jobs WHERE run_id = ? AND state IN (?, ?, ?) "
                "ORDER BY aged_priority DESC, workload_units DESC, job_id ASC",
                (run_id, QUEUED, PAUSED_NETWORK, RESUMING))
            for row in candidates:
                job_id = str(row["job_id"])
                if job_id in blocked:
                    continue
                cursor = self._conn.execute(
                    "UPDATE jobs SET state = ?, worker = ?, attempts = attempts + 1, "
                    "started_utc = COALESCE(started_utc, ?), updated_utc = ? "
                    "WHERE job_id = ? AND state IN (?, ?, ?)",
                    (RUNNING, worker, utcnow(), utcnow(), job_id,
                     QUEUED, PAUSED_NETWORK, RESUMING))
                if cursor.rowcount:
                    self._conn.commit()
                    row = self._conn.execute(
                        "SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
                    return JobRow.from_row(row)
            self._conn.commit()
        return None

    def release(self, job_id: str, *, state: str = QUEUED, detail: str = "") -> None:
        """Put a claimed community back, without losing what it has done."""
        self.update_job(job_id, {"state": state, "worker": None,
                                 "detail": detail or None})

    def age_priorities(self, run_id: str, *, per_minute: float = AGE_PER_MINUTE,
                       cap: float = AGE_CAP) -> int:
        """Waiting must be worth something, or the small never run (brief §5).

        A community's effective priority rises with the time it has spent
        queued. Without this, twenty large communities scheduled first would
        keep taking every freed worker and the short ones would sit behind them
        for the whole run.

        The cap is deliberately a little ABOVE the priority range rather than a
        fraction of it. A cap of half the range would mean the largest community
        always outranks the smallest however long the small one has waited,
        which is starvation with extra steps. At `AGE_CAP`, a community that has
        waited long enough outranks anything that arrived after it — so every
        community reaches a worker, and the ordering only decides how soon.
        """
        cursor = self.execute(
            "UPDATE jobs SET aged_priority = MIN(priority + "
            "  MIN(?, (julianday('now') - julianday(queued_utc)) * 1440.0 * ?), "
            "  priority + ?) "
            "WHERE run_id = ? AND state = ?",
            (cap, per_minute, cap, run_id, QUEUED))
        return cursor.rowcount

    # -- events, samples and errors ----------------------------------------
    def add_event(self, run_id: str, kind: str, *, job_id: str | None = None,
                  stage_no: int | None = None, detail: str = "",
                  payload: Mapping[str, Any] | None = None) -> None:
        self.execute(
            "INSERT INTO job_events(run_id, job_id, kind, stage_no, detail, payload, ts_utc) "
            "VALUES(?,?,?,?,?,?,?)",
            (run_id, job_id, kind, stage_no, detail[:2000],
             json.dumps(dict(payload)) if payload else None, utcnow()))

    def events(self, run_id: str, *, limit: int = 200,
               job_id: str | None = None) -> list[sqlite3.Row]:
        if job_id:
            return self.query(
                "SELECT * FROM job_events WHERE run_id = ? AND job_id = ? "
                "ORDER BY event_id DESC LIMIT ?", (run_id, job_id, limit))
        return self.query(
            "SELECT * FROM job_events WHERE run_id = ? ORDER BY event_id DESC LIMIT ?",
            (run_id, limit))

    def add_sample(self, run_id: str, values: Mapping[str, Any]) -> None:
        payload = {"run_id": run_id, **values, "ts_utc": utcnow()}
        columns = ", ".join(payload)
        placeholders = ", ".join("?" for _ in payload)
        self.execute(
            f"INSERT INTO scheduler_samples({columns}) VALUES({placeholders})",
            tuple(payload.values()))

    def samples(self, run_id: str) -> list[sqlite3.Row]:
        return self.query(
            "SELECT * FROM scheduler_samples WHERE run_id = ? ORDER BY sample_id",
            (run_id,))

    def add_error(self, run_id: str, *, job_id: str | None, error_class: str,
                  message: str, detail: str = "", fatal: bool = False) -> None:
        self.execute(
            "INSERT INTO run_errors(run_id, job_id, error_class, message, detail, "
            "fatal, ts_utc) VALUES(?,?,?,?,?,?,?)",
            (run_id, job_id, error_class, message[:1000], detail[:4000],
             int(fatal), utcnow()))

    def errors(self, run_id: str) -> list[sqlite3.Row]:
        return self.query(
            "SELECT * FROM run_errors WHERE run_id = ? ORDER BY error_id", (run_id,))

    # -- hosts -------------------------------------------------------------
    def note_host(self, host: str, values: Mapping[str, Any]) -> None:
        payload = {"host": host, **values, "updated_utc": utcnow()}
        columns = ", ".join(payload)
        placeholders = ", ".join("?" for _ in payload)
        updates = ", ".join(f"{key} = excluded.{key}" for key in payload if key != "host")
        self.execute(
            f"INSERT INTO host_stats({columns}) VALUES({placeholders}) "
            f"ON CONFLICT(host) DO UPDATE SET {updates}",
            tuple(payload.values()))

    def hosts(self) -> list[sqlite3.Row]:
        return self.query("SELECT * FROM host_stats ORDER BY requests DESC")

    # -- summary -----------------------------------------------------------
    def totals(self, run_id: str) -> dict[str, Any]:
        row = self.query_one(
            "SELECT COUNT(*) AS jobs, "
            "SUM(pages) AS pages, SUM(documents) AS documents, SUM(images) AS images, "
            "SUM(evidence) AS evidence, SUM(claims) AS claims, SUM(sources) AS sources, "
            "SUM(conflicts) AS conflicts, SUM(yield_units) AS yield_units, "
            "SUM(active_s) AS active_s, SUM(wall_s) AS wall_s, "
            "SUM(offline_s) AS offline_s, SUM(paused_s) AS paused_s, "
            "SUM(attempts) AS attempts, "
            "SUM(CASE WHEN workbook_verified = 1 THEN 1 ELSE 0 END) AS workbooks "
            "FROM jobs WHERE run_id = ?", (run_id,))
        if row is None:
            return {}
        return {key: (row[key] or 0) for key in row.keys()}
