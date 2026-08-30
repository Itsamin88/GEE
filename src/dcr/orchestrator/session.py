"""The run, from the researcher's side: enter, estimate, START, walk away.

This is the flow §99 asks for, and nothing more:

    1. launch                     RUN.py, the green button in PyCharm
    2. select or create a run     a previous run is offered before a new one
    3. how many communities       1, 20, 212 — nothing here has an upper bound
    4. enter their details        typed, or read from a file
    5. enter their URLs
    6. review the workload        a queue table and an honest range
    7. START
    8. PAUSE / RESUME / CANCEL    optional, at any point, one or all
    9. wait
   10. outputs                    one workbook per community, plus the run's own

Typing two hundred and twelve communities at a keyboard is not a workflow, so
step 4 accepts a CSV or a JSON file as readily as it accepts typing. Both routes
produce exactly the same queue; the file is a convenience, not a different mode.

## The global outputs

Per-community output is unchanged — its own directory, its own database, its own
workbook, nothing shared (brief §53). Beside them the run writes its own record
(brief §54):

    global_run_manifest.json     what was asked for, and with what configuration
    global_progress.json         where it got to, rewritten as it goes
    global_error_log.csv         every failure, with the community it belonged to
    global_summary.md            the numbers §107 asks for, in prose
    community_status_table.csv   one row per community, whatever happened to it

`global_progress.json` is rewritten during the run rather than at the end, so a
run interrupted by a power cut still leaves a readable account of where it was.
"""

from __future__ import annotations

import csv
import json
import time
from multiprocessing.managers import BaseManager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .. import __version__
from ..config import Settings, load_settings
from ..control import clear_requests, control_dir_for
from ..logging_setup import event, get_logger
from .dashboard import Dashboard, community_table, format_duration, format_range
from .governor import ResourceGovernor
from .hosts import HostBroker
from .plan import RunPlan, build_plan, scalability
from .pool import WorkerPool
from .recovery import (OFFLINE_MODES, RecoveryPlan, apply_resume, find_interrupted,
                       plan_resume, queue_offline_pass, repair)
from .scheduler import RunScheduler
from .store import (CANCELLED, COMPLETED, FAILED, PAUSED_MANUAL, PAUSED_NETWORK,
                    QUEUED, RUN_CANCELLED, RUN_COMPLETED, RunStore)

log = get_logger("orchestrator.session")


class _BrokerManager(BaseManager):
    """Serves the one `HostBroker` that every worker process shares.

    Must stay at module level: see `RunSession._start_broker`.
    """

#: Columns a community file may carry. Only `name` is required; a community
#: with no addresses at all is a legitimate job — stage 0 goes looking.
FILE_COLUMNS = ("name", "latitude", "longitude", "country", "urls", "coder_id", "mode")


def new_run_id(now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    return f"R{stamp}"


# ===========================================================================
# Getting the communities in
# ===========================================================================
def read_community_file(path: Path) -> list[dict[str, Any]]:
    """Read communities from CSV or JSON.

    Typing two hundred and twelve communities at a keyboard is not a workflow.
    The file produces exactly the same queue as typing would; it is a
    convenience, not a different mode.

    CSV wants a header row with a name column — `name`, or one of the aliases
    in `NAME_COLUMNS`, because the researcher's own sheet calls it
    `Ecovillage_Name` and a file that reads as zero communities with no error
    is the worst failure this function has. URLs may be one column separated
    by `;`, `|` or whitespace, or several columns named `url`, `url1`, `url2`
    and so on — because that is how the two shapes of spreadsheet a researcher
    already has actually look. Columns that merely *begin* with "url", such as
    `url_count`, are not addresses and are left alone.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"no community file at {path}")
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        entries = payload if isinstance(payload, list) else payload.get("communities", [])
        return [_normalise_entry(dict(entry)) for entry in entries]

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(8192)
        handle.seek(0)
        for raw in csv.DictReader(handle, dialect=_dialect_for(sample)):
            entry = {str(k or "").strip().lower(): (v or "").strip()
                     for k, v in raw.items() if k}
            name = next((entry[key] for key in NAME_COLUMNS
                         if entry.get(key)), "")
            if not name:
                continue
            entry["name"] = name
            urls: list[str] = []
            for key, value in entry.items():
                if _is_url_column(key):
                    urls.extend(_split_urls(value))
            entry["urls"] = _dedupe(urls)
            rows.append(_normalise_entry(entry))
    return rows


#: Header names that mean "the community's name", most specific first. The
#: researcher's own cohort file uses `Ecovillage_Name`; accepting it here is
#: what stops that file loading as zero communities.
NAME_COLUMNS = ("name", "community_name_normalized", "community_name",
                "ecovillage_name", "community")


def _dialect_for(sample: str) -> type[csv.Dialect] | csv.Dialect:
    """Choose a dialect, then check it actually produced a usable header.

    `csv.Sniffer` counts candidate delimiters, so a file whose URL column holds
    a `;`-separated list can out-vote its own commas. The sniffed answer is
    therefore treated as a proposal: if reading the header with it does not
    yield a name column, it is discarded for plain comma-separated Excel.
    """
    candidates: list[type[csv.Dialect] | csv.Dialect] = []
    try:
        candidates.append(csv.Sniffer().sniff(sample, delimiters=",;\t"))
    except csv.Error:
        pass
    candidates.append(csv.excel)
    for dialect in candidates:
        try:
            header = next(csv.reader(sample.splitlines()[:1], dialect=dialect), [])
        except csv.Error:
            continue
        keys = {str(cell or "").strip().lower() for cell in header}
        if keys & set(NAME_COLUMNS):
            return dialect
    return csv.excel


def _is_url_column(key: str) -> bool:
    """Is this header an address column, rather than one that merely starts 'url'?

    `urls`, `url`, `url1`, `url_2`, `url-10` are addresses. `url_count`,
    `url_notes`, `urls_verified_count` are not, and feeding their values to the
    frontier would queue `7` as a page to fetch.
    """
    if key in {"url", "urls"}:
        return True
    if not key.startswith("url"):
        return False
    rest = key[3:].lstrip("_- ")
    return rest.isdigit()


def _dedupe(urls: list[str]) -> list[str]:
    """Keep first occurrence order; the same address twice is one address."""
    seen: set[str] = set()
    out: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _split_urls(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value or "").strip()
    if not text or text.upper() == "NONE":
        return []
    for separator in (";", "|", "\n"):
        if separator in text:
            return [part.strip() for part in text.split(separator) if part.strip()]
    # Comma last, and only when every piece still looks like an address: query
    # strings carry commas (`?bbox=1,2,3`), and splitting one URL into two
    # fragments is worse than leaving a rare comma-separated pair joined.
    if "," in text:
        parts = [part.strip() for part in text.split(",") if part.strip()]
        if len(parts) > 1 and all(_looks_like_url(part) for part in parts):
            return parts
    return [part for part in text.split() if part]


def _looks_like_url(text: str) -> bool:
    return text.startswith(("http://", "https://", "www.")) or (
        "." in text.split("/")[0] and " " not in text)


def _normalise_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    def number(value: Any) -> float | None:
        text = str(value or "").strip().replace(",", ".")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    latitude = number(entry.get("latitude") or entry.get("lat"))
    longitude = number(entry.get("longitude") or entry.get("lon") or entry.get("lng"))
    if (latitude is None) != (longitude is None):
        # One coordinate is not a location. Recording half of one would put a
        # community somewhere it is not; blank is honest (register rule 3).
        latitude = longitude = None
    return {
        "name": str(entry.get("name") or "").strip(),
        "latitude": latitude,
        "longitude": longitude,
        "country": (str(entry.get("country") or "").strip() or None),
        "coder_id": str(entry.get("coder_id") or "").strip(),
        "mode": (str(entry.get("mode") or "").strip().upper() or "FULL"),
        "urls": _split_urls(entry.get("urls")),
        # --- crawl policy, when the master file carries it ------------------
        # Optional by design: a plain two-column sheet of names and URLs still
        # loads, and simply gets the standard treatment for every address.
        #
        # Three scopes, because three kinds of address are three different jobs:
        # the community's own site is walked in full; somebody else's site gives
        # up exactly the one page that mentions the community; a direct document
        # link is downloaded and nothing around it is crawled.
        "site_urls": _split_urls(entry.get("site_urls")),
        "page_urls": _split_urls(entry.get("page_urls")),
        "file_urls": _split_urls(entry.get("file_urls")),
        # The old name, still accepted so an older master file keeps working.
        "deep_crawl_urls": _split_urls(
            entry.get("site_urls") or entry.get("deep_crawl_urls")),
        "academic_search_terms": _split_terms(entry.get("academic_search_terms")),
        "crawl_policy": (str(entry.get("crawl_policy") or "").strip().upper() or None),
    }


def _split_terms(value: Any) -> list[str]:
    """Search strings, split only on the pipe.

    Not `_split_urls`: a query is ordinary prose. It contains spaces, and it may
    contain a comma or a semicolon - "Baireni, Udayapur" is one term, not two -
    so only the pipe delimiter the master file uses may separate them.
    """
    if isinstance(value, (list, tuple)):
        items = [str(v) for v in value]
    else:
        items = str(value or "").split("|")
    out: list[str] = []
    for item in items:
        term = item.strip()
        if term and term not in out:
            out.append(term)
    return out


# ===========================================================================
# The run
# ===========================================================================
@dataclass
class RunSession:
    """One multi-community run, from the queue to the final summary."""

    settings: Settings
    run_id: str = ""
    store: RunStore | None = None
    plan: RunPlan | None = None
    scheduler: RunScheduler | None = None
    dashboard: Dashboard | None = None
    #: Configuration overrides applied identically in every worker (brief §98).
    settings_overrides: Mapping[str, Any] = field(default_factory=dict)
    sources_overrides: Mapping[str, Any] = field(default_factory=dict)
    _broker_manager: Any = None
    _progress_written_at: float = 0.0

    def __post_init__(self) -> None:
        self.output_root = Path(self.settings.output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.run_id = self.run_id or new_run_id()
        if self.store is None:
            self.store = RunStore(self.output_root / "run.sqlite3")

    # -- setting the run up -------------------------------------------------
    def create(self, entries: Sequence[Mapping[str, Any]], *, mode: str = "FULL",
               label: str = "") -> RunPlan:
        """Turn what the researcher supplied into a sized, ordered queue."""
        calibration = self._calibration()
        self.plan = build_plan(
            entries, run_id=self.run_id, output_root=self.output_root, mode=mode,
            calibration=calibration,
            unit_seconds=float(self.settings.get(
                "orchestrator", "workload_unit_seconds", default=60.0) or 60.0),
        )
        self.store.create_run(
            self.run_id, mode=mode, output_root=self.output_root, label=label,
            app_version=__version__,
            config_sha256=next(
                (entry.get("sha256", "") for entry in self.settings.config_lock()
                 if entry.get("filename") == "config/config.yaml"), ""),
        )
        self.store.execute("UPDATE runs SET community_count = ? WHERE run_id = ?",
                           (len(self.plan.jobs), self.run_id))
        for job in self.plan.jobs:
            self.store.add_job(self.run_id, job.as_dict())
        self._write_manifest(mode=mode, label=label)
        return self.plan

    def _calibration(self) -> dict[str, float]:
        """What previous runs actually cost, if any have been recorded.

        The per-address costs shipped in `plan.py` are a starting point for a
        machine with no history. Once real runs exist their durations are a far
        better predictor, and the estimate says which it is using (brief §46).
        """
        try:
            rows = self.store.query(
                "SELECT urls, active_s FROM jobs WHERE active_s > 0 "
                "AND state = ? ORDER BY finished_utc DESC LIMIT 60", (COMPLETED,))
        except Exception:
            return {}
        samples: list[tuple[int, float]] = []
        for row in rows:
            try:
                count = len(json.loads(row["urls"] or "[]"))
            except (TypeError, ValueError):
                continue
            if count:
                samples.append((count, float(row["active_s"] or 0.0)))
        if len(samples) < 5:
            return {}
        per_url = sum(seconds / count for count, seconds in samples) / len(samples)
        minutes = per_url / 60.0
        # Scale every address kind by how the observed average compares with the
        # shipped assumption, keeping their relative costs.
        from .plan import ADDRESS_COST

        baseline = sum(ADDRESS_COST.values()) / len(ADDRESS_COST)
        if baseline <= 0 or minutes <= 0:
            return {}
        factor = max(0.25, min(4.0, minutes / baseline))
        return {kind: round(cost * factor, 2) for kind, cost in ADDRESS_COST.items()}

    def estimate_text(self, *, workers_low: int = 8, workers_high: int = 16) -> str:
        """The block the researcher reads before pressing START (brief §45)."""
        if self.plan is None:
            return ""
        low, high = self.plan.wall_clock_estimate_s(workers_low=workers_low,
                                                    workers_high=workers_high)
        active_low = self.plan.active_low_s
        active_high = self.plan.active_high_s
        return "\n".join([
            "ESTIMATED WORKLOAD  (an estimate, not a guarantee)",
            f"  Communities .................. {len(self.plan.jobs)}",
            f"  Total active processing ...... {format_range(active_low, active_high)}",
            f"  Expected wall-clock .......... {format_range(low, high)}",
            f"  Effective workers ............ {workers_low}–{workers_high} "
            f"(≈{scalability(workers_high):.1f}× a single worker, not {workers_high}×)",
            "",
            "  Wall-clock is not active time divided by the number of workers.",
            "  Per-host politeness, the tail of the queue and the machine's own",
            "  limits all take a share; the estimate accounts for them, and the",
            "  run reports what actually happened.",
        ])

    # -- running ------------------------------------------------------------
    def start(self, *, workers_max: int | None = None, show_dashboard: bool = True,
              max_ticks: int | None = None) -> dict[str, Any]:
        """Work the queue to the end. Returns the run's summary."""
        if self.plan is None:
            raise RuntimeError("create() the run before starting it")
        clear_requests(self.output_root)
        repair(self.store, self.run_id)

        config = dict(self.settings.get("orchestrator", default={}) or {})
        worker_config = dict(config.get("workers") or {})
        if workers_max:
            worker_config["max_workers"] = int(workers_max)
        governor = ResourceGovernor(config=worker_config)

        broker = self._start_broker(config)
        pool = WorkerPool(
            broker=broker,
            heartbeat_timeout_s=float(config.get("heartbeat_timeout_minutes", 20)) * 60,
            shutdown_grace_s=float(config.get("shutdown_grace_seconds", 90)),
        )
        self.dashboard = Dashboard() if show_dashboard else None
        self.scheduler = RunScheduler(
            self.store, self.plan, output_root=self.output_root, pool=pool,
            governor=governor, config=config,
            on_update=self._on_update,
            payload_extra={
                "config_root": str(self.settings.root),
                "settings_overrides": dict(self.settings_overrides),
                "sources_overrides": dict(self.sources_overrides),
            },
        )

        event(log, "RUN", f"{self.run_id}: {len(self.plan.jobs)} communities")
        try:
            self.scheduler.run(max_ticks=max_ticks)
        finally:
            self._stop_broker()
        return self.finish()

    def _start_broker(self, config: Mapping[str, Any]) -> Any:
        """Expose one host broker to every worker process.

        A `multiprocessing.Manager` proxy, which behaves identically on Windows
        and POSIX — there is no forked shared memory here, and nothing assumes
        any (brief §42).

        `_BrokerManager` is defined at module level, and that is not a style
        preference. `multiprocessing` on Windows starts its manager process with
        `spawn`, which re-imports the module and looks the class up by qualified
        name; a class defined inside this method is
        `RunSession._start_broker.<locals>._BrokerManager`, which no import can
        resolve. The manager then failed to start on Windows and every run fell
        back to per-worker politeness — silently, because the fallback is
        deliberately non-fatal. That matters most where it is least visible:
        `https://ecovillage.org` is a seed on all 212 rows of the cohort, so
        without the shared broker sixteen workers hit one host at once, which is
        both rude and a good way to be blocked halfway through an overnight run.
        """
        try:
            _BrokerManager.register(
                "HostBroker", HostBroker,
                exposed=("acquire", "release", "defer", "shared", "snapshot", "stats"))
            manager = _BrokerManager()
            manager.start()
            self._broker_manager = manager
            return manager.HostBroker(config=dict(config.get("hosts") or {}))
        except Exception as exc:
            # Politeness degrades to what one community would have done alone,
            # which is the correct failure direction: never stop researching
            # because a coordinator could not start.
            log.warning("[HOSTS] no shared host broker (%s); each community will "
                        "apply its own politeness only", exc)
            return None

    def _stop_broker(self) -> None:
        if self._broker_manager is not None:
            try:
                self._broker_manager.shutdown()
            except Exception:
                pass
            self._broker_manager = None

    def _on_update(self, scheduler: RunScheduler) -> None:
        snapshot = scheduler.snapshot()
        if self.dashboard is not None:
            self.dashboard.draw(snapshot)
        now = time.monotonic()
        if now - self._progress_written_at >= 5.0:
            self._progress_written_at = now
            self._write_progress(snapshot)

    # -- the researcher's controls -----------------------------------------
    def pause_all(self, reason: str = "") -> None:
        if self.scheduler:
            self.scheduler.pause_all(reason)

    def resume_all(self, reason: str = "") -> None:
        if self.scheduler:
            self.scheduler.resume_all(reason)

    def cancel_all(self, reason: str = "") -> None:
        if self.scheduler:
            self.scheduler.cancel_all(reason)

    def pause_community(self, job_id: str, reason: str = "") -> bool:
        return bool(self.scheduler and self.scheduler.pause_community(job_id, reason))

    def resume_community(self, job_id: str, reason: str = "") -> bool:
        return bool(self.scheduler and self.scheduler.resume_community(job_id, reason))

    # -- finishing ----------------------------------------------------------
    def finish(self) -> dict[str, Any]:
        """Write the run's own outputs and return its summary (brief §54, §107)."""
        snapshot = self.scheduler.snapshot() if self.scheduler else {
            "counts": self.store.counts(self.run_id),
            "totals": self.store.totals(self.run_id),
            "workers": {}, "wall_s": 0.0,
        }
        jobs = self.store.jobs(self.run_id)
        summary = self._summary(snapshot, jobs)
        final = self.output_root
        self._write_progress(snapshot)
        self._write_status_table(jobs)
        self._write_error_log()
        (final / "global_summary.md").write_text(
            self._summary_markdown(summary, jobs), encoding="utf-8")
        (final / "global_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        if self.dashboard is not None:
            self.dashboard.finish(snapshot)
        return summary

    def _summary(self, snapshot: Mapping[str, Any],
                 jobs: Sequence[Any]) -> dict[str, Any]:
        counts = dict(snapshot.get("counts") or {})
        totals = dict(snapshot.get("totals") or {})
        by_status: dict[str, int] = {}
        for job in jobs:
            key = job.final_status or job.state
            by_status[key] = by_status.get(key, 0) + 1
        governor = self.scheduler.governor if self.scheduler else None
        stats = self.scheduler.stats if self.scheduler else None
        return {
            "run_id": self.run_id,
            "app_version": __version__,
            "communities": {
                "total": counts.get("TOTAL", 0),
                "completed": counts.get(COMPLETED, 0),
                "failed": counts.get(FAILED, 0),
                "cancelled": counts.get(CANCELLED, 0),
                "paused": counts.get(PAUSED_MANUAL, 0) + counts.get(PAUSED_NETWORK, 0),
                "queued": counts.get(QUEUED, 0),
                "by_final_status": dict(sorted(by_status.items())),
            },
            "evidence": {
                "sources": int(totals.get("sources", 0) or 0),
                "documents": int(totals.get("documents", 0) or 0),
                "images": int(totals.get("images", 0) or 0),
                "evidence_items": int(totals.get("evidence", 0) or 0),
                "claims": int(totals.get("claims", 0) or 0),
                "conflicts": int(totals.get("conflicts", 0) or 0),
                "yield_units": round(float(totals.get("yield_units", 0) or 0), 1),
                "workbooks_verified": int(totals.get("workbooks", 0) or 0),
            },
            "time": {
                "wall_clock_s": round(float(snapshot.get("wall_s", 0.0)), 1),
                "paused_s": round(float(snapshot.get("paused_s", 0.0)), 1),
                "total_active_s": round(float(totals.get("active_s", 0) or 0), 1),
                "total_offline_s": round(float(totals.get("offline_s", 0) or 0), 1),
                "retries": int(totals.get("attempts", 0) or 0) - len(jobs),
            },
            "workers": {
                **dict(snapshot.get("workers") or {}),
                **(governor.report() if governor else {}),
            },
            "scheduler": {
                "dispatched": getattr(stats, "dispatched", 0),
                "crashed": getattr(stats, "crashed", 0),
                "retried": getattr(stats, "retried", 0),
                "hung": getattr(stats, "hung", 0),
                "worker_seconds": round(getattr(stats, "worker_seconds", 0.0), 1),
            },
            "errors": len(self.store.errors(self.run_id)),
        }

    def _summary_markdown(self, summary: Mapping[str, Any],
                          jobs: Sequence[Any]) -> str:
        communities = summary["communities"]
        evidence = summary["evidence"]
        timing = summary["time"]
        workers = summary.get("workers") or {}
        lines = [
            f"# Run {summary['run_id']}",
            "",
            f"{communities['completed']} of {communities['total']} communities "
            f"completed in {format_duration(timing['wall_clock_s'])} wall-clock.",
            "",
            "## Communities",
            "",
            "| Outcome | Count |",
            "| --- | ---: |",
        ]
        for status, count in communities["by_final_status"].items():
            lines.append(f"| {status} | {count} |")
        lines += [
            "",
            "## Evidence",
            "",
            "| | |",
            "| --- | ---: |",
            f"| Sources | {evidence['sources']:,} |",
            f"| Documents | {evidence['documents']:,} |",
            f"| High-value images | {evidence['images']:,} |",
            f"| Evidence items | {evidence['evidence_items']:,} |",
            f"| Claims | {evidence['claims']:,} |",
            f"| Conflicts | {evidence['conflicts']:,} |",
            f"| Workbooks written AND reopened | {evidence['workbooks_verified']} |",
            "",
            "## Time",
            "",
            f"- Wall-clock: {format_duration(timing['wall_clock_s'])}",
            f"- Total active processing across all communities: "
            f"{format_duration(timing['total_active_s'])}",
            f"- Paused: {format_duration(timing['paused_s'])}",
            f"- Offline: {format_duration(timing['total_offline_s'])}",
            f"- Retries: {max(0, timing['retries'])}",
        ]
        if timing["wall_clock_s"] > 0 and timing["total_active_s"] > 0:
            observed = timing["total_active_s"] / timing["wall_clock_s"]
            lines.append(
                f"- **Observed speed-up: {observed:.1f}×** — total active "
                f"processing divided by wall-clock, on up to "
                f"{workers.get('peak', workers.get('target', '?'))} workers. "
                "This is measured, not modelled.")
        lines += [
            "",
            "## Communities, one row each",
            "",
            "```",
            community_table(jobs),
            "```",
        ]
        return "\n".join(lines) + "\n"

    # -- the run's own files ------------------------------------------------
    def _write_manifest(self, *, mode: str, label: str) -> None:
        payload = {
            "run_id": self.run_id,
            "label": label,
            "mode": mode,
            "app_version": __version__,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "output_root": str(self.output_root),
            "communities": [job.as_dict() for job in (self.plan.jobs if self.plan else [])],
            "estimate": {
                "total_workload_units": self.plan.total_units if self.plan else 0,
                "active_low_s": self.plan.active_low_s if self.plan else 0,
                "active_high_s": self.plan.active_high_s if self.plan else 0,
            },
            **self.settings.reproducibility_record([]),
        }
        _write_json(self.output_root / "global_run_manifest.json", payload)

    def _write_progress(self, snapshot: Mapping[str, Any]) -> None:
        """Rewritten as the run goes, so a power cut still leaves an account."""
        _write_json(self.output_root / "global_progress.json", {
            "run_id": self.run_id,
            "updated_utc": datetime.now(timezone.utc).isoformat(),
            **{k: v for k, v in snapshot.items() if k != "live"},
            "running": {job_id: dict(state)
                        for job_id, state in (snapshot.get("live") or {}).items()
                        if str(state.get("state")) == "RUNNING"},
        })

    def _write_status_table(self, jobs: Sequence[Any]) -> None:
        path = self.output_root / "community_status_table.csv"
        columns = ("job_id", "site_id", "name", "state", "final_status", "sources",
                   "documents", "images", "evidence", "claims", "conflicts",
                   "yield_units", "active_s", "wall_s", "attempts",
                   "workbook_path", "output_dir", "last_error")
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            for job in jobs:
                writer.writerow([getattr(job, column, "") for column in columns])

    def _write_error_log(self) -> None:
        path = self.output_root / "global_error_log.csv"
        rows = self.store.errors(self.run_id)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(("error_id", "job_id", "error_class", "message",
                             "detail", "fatal", "ts_utc"))
            for row in rows:
                writer.writerow([row["error_id"], row["job_id"], row["error_class"],
                                 row["message"], (row["detail"] or "")[:2000],
                                 row["fatal"], row["ts_utc"]])

    def close(self) -> None:
        self._stop_broker()
        if self.store is not None:
            self.store.close()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Atomically, so an interrupted write never leaves a truncated file."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                         encoding="utf-8")
    temporary.replace(path)


__all__ = ["FILE_COLUMNS", "RunSession", "new_run_id", "read_community_file"]
