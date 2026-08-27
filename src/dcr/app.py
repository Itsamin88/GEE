"""The application: interactive prompts, run modes, and the export pipeline.

The researcher opens the project in PyCharm, presses RUN, types a name and some
URLs, and presses Enter. Everything else belongs inside the software (brief §5).
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import __version__
from .config import Settings, detect_optional_features, load_settings
from .control import (InterruptedRun, PAUSED_MANUAL, clear_requests,
                      control_dir_for, find_interrupted_runs, read_status,
                      request_cancel, request_pause, request_resume)
from .db import Database
from .estimate import Estimate, Estimator
from .export import manifests, report as report_mod
from .export.finalise import finalise_workbook
from .export.workbook import WorkbookExporter
from .ids import safe_name
from .logging_setup import event, get_logger, setup_logging
from .net.connectivity import ConnectivityMonitor
from .qc.checks import QualityControl, completion_status
from .runner import CommunityInput, CommunityRunner, MODE_STAGES, RunOutcome
from .storage import CommunityStorage
from .workbook_audit import audit

log = get_logger("app")

RUN_MODES = ("FULL", "SOURCE", "ACADEMIC", "RECONCILE", "RESUME", "RETRY_FAILED", "AUDIT", "EXPORT")

BANNER = f"""
==============================================================================
  DEEP DOCUMENTARY RESEARCH CRAWLER  v{__version__}
  Stage 1 documentary coding for intentional sustainable communities
------------------------------------------------------------------------------
  This program records what published sources SAY about one community.
  It does not evaluate ecological performance, never infers a practice from
  imagery, and never estimates an area or a polygon.
==============================================================================
"""


def prompt(text: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{text}{suffix}: ").strip()
    except EOFError:
        return default
    return answer or default


def collect_input() -> tuple[CommunityInput, str, str | None]:
    """Ask the researcher for the four things only they can supply."""
    print(BANNER)
    name = ""
    while not name:
        name = prompt("Community name (for example: EcoVillage de Pourgues)")
        if not name:
            print("  A name is required.")

    latitude = _float_or_none(prompt("Latitude (optional, press Enter to skip)"))
    longitude = _float_or_none(prompt("Longitude (optional, press Enter to skip)"))
    if (latitude is None) != (longitude is None):
        print("  Only one coordinate was given; both are needed, so both are ignored.")
        print("  coordinate_agreement will be left blank rather than guessed.")
        latitude = longitude = None

    country = prompt("Country (optional, improves local-language and registry searches)") or None

    print("\nURLs — one per line. Website, old domain, Facebook, Instagram, YouTube,")
    print("Vimeo, directory listing, academic page, blog, archive: paste them all.")
    print("Type NONE if you have none, then press Enter on an empty line to finish.")
    urls: list[str] = []
    while True:
        line = prompt(f"  URL {len(urls) + 1}")
        if not line:
            break
        if line.strip().upper() == "NONE":
            urls = []
            break
        urls.append(line.strip())

    print("\nRun modes:")
    print("  FULL          all ten stages (the default)")
    print("  SOURCE        deep crawl of one address only")
    print("  ACADEMIC      academic, grey literature and local language only")
    print("  RESUME        continue an interrupted run")
    print("  RETRY_FAILED  retry only the failed or blocked addresses")
    print("  RECONCILE     merge previous runs without re-fetching")
    print("  AUDIT         re-run validation and reconciliation offline")
    print("  EXPORT        regenerate the workbook and reports from stored evidence")
    mode = (prompt("\nRun mode", "FULL") or "FULL").upper()
    if mode not in RUN_MODES:
        print(f"  {mode!r} is not a run mode; using FULL.")
        mode = "FULL"

    target = None
    if mode == "SOURCE":
        target = prompt("Which address id (for example IC001-02)") or None

    coder = prompt("Coder id to stamp on the rows", f"DCR/{__version__}")

    community = CommunityInput(
        name=name, latitude=latitude, longitude=longitude, urls=urls,
        country=country, coder_id=coder,
    )
    return community, mode, target


def _float_or_none(value: str) -> float | None:
    if not value:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        print(f"  {value!r} is not a number; ignoring it.")
        return None


class Application:
    """Wires configuration, database, runner, exporter and quality control."""

    def __init__(self, settings: Settings | None = None, *, monitor: Any = None):
        self.settings = settings or load_settings()
        self.settings.output_root.mkdir(parents=True, exist_ok=True)
        self.db = Database(self.settings.database_path)
        self.features = detect_optional_features(self.settings)
        self.estimator = Estimator(self.settings, self.db)
        self._monitor = monitor
        #: The estimates made for the run in progress, kept for the report.
        self.estimates: list[Estimate] = []
        #: Set by the run orchestrator when this Application is one worker of
        #: many: a callback the engine reports stage changes through, and the
        #: run-wide host politeness broker. Both are None for a single run, and
        #: everything downstream is written to work without them.
        self.on_progress: Any = None
        self.host_broker: Any = None
        self._probe_summary = ""

    def close(self) -> None:
        self.db.close()

    # -- connectivity ------------------------------------------------------
    @property
    def monitor(self) -> ConnectivityMonitor:
        """The connectivity monitor, built from configuration on first use."""
        if self._monitor is None:
            cfg = dict(self.settings.get("connectivity", default={}) or {})
            self._monitor = ConnectivityMonitor(
                probes=cfg.get("probes"),
                timeout_s=float(cfg.get("timeout_s", 8.0)),
                min_reachable=int(cfg.get("min_reachable", 1)),
                check_interval_s=float(cfg.get("check_interval_s", 30.0)),
                offline_retry_s=float(cfg.get("offline_retry_s", 15.0)),
                offline_retry_max_s=float(cfg.get("offline_retry_max_s", 300.0)),
                verify_tls=bool(self.settings.get("network", "verify_tls", default=True)),
                user_agent=self.settings.user_agent,
            )
        return self._monitor

    # -- unfinished runs ---------------------------------------------------
    def interrupted_runs(self) -> list[InterruptedRun]:
        """Runs that stopped without finishing, newest first (brief §21)."""
        return find_interrupted_runs(self.db)

    def offer_resume(self) -> InterruptedRun | None:
        """Tell the researcher about a paused run and ask what to do with it.

        A run the researcher deliberately paused is never restarted without
        being asked, and never quietly continued as if it had not been paused.
        """
        runs = self.interrupted_runs()
        if not runs:
            return None
        print("\n" + "=" * 78)
        print("  UNFINISHED RUN FOUND")
        print("=" * 78)
        for index, run in enumerate(runs[:5], start=1):
            print(f"  {index}. {run.describe()}")
            if run.pause_reason:
                print(f"     reason: {run.pause_reason}")
            if run.pending_tasks:
                print(f"     {run.pending_tasks} queued task(s) still waiting")
        print("-" * 78)
        print("  This run was not finished. Resuming continues from its last")
        print("  checkpoint; starting a new run leaves it untouched and resumable.")
        answer = prompt("\n  Resume it? (yes / no)", "yes").strip().lower()
        if answer.startswith("y"):
            return runs[0]
        return None

    # -- the researcher's controls ----------------------------------------
    def pause(self, reason: str = "") -> None:
        request_pause(self.settings.output_root, reason)

    def resume(self, reason: str = "") -> None:
        request_resume(self.settings.output_root, reason)

    def cancel(self, reason: str = "") -> None:
        request_cancel(self.settings.output_root, reason)

    def status(self) -> dict[str, Any] | None:
        return read_status(self.settings.output_root)

    # -- startup -----------------------------------------------------------
    def preflight(self) -> None:
        """Audit the workbook and report which optional features are available."""
        result = audit(self.settings.workbook_template, self.settings.schema)
        for note in result.notes:
            event(log, "SCHEMA", note)
        for warning in result.warnings:
            log.warning("[SCHEMA] %s", warning)
        result.raise_if_failed()

        available = [f for f in self.features if f.available]
        missing = [f for f in self.features if not f.available]
        event(log, "SETUP", f"{len(available)} optional features available, {len(missing)} not")
        for feature in missing:
            log.info("[SETUP] %s unavailable (%s) — %s",
                     feature.name, feature.detail, feature.degrades_to)

    # -- running -----------------------------------------------------------
    def run(self, community: CommunityInput, *, mode: str = "FULL",
            target: str | None = None, estimate_first: bool = False,
            on_status: Any = None) -> dict[str, Any]:
        storage_root = self.settings.output_root
        community_row = None
        if mode in ("EXPORT", "AUDIT", "RECONCILE", "RESUME", "RETRY_FAILED"):
            community_row = self.db.query_one(
                "SELECT * FROM communities WHERE name_input = ?", (community.name,))
            if community_row is None and mode in ("EXPORT", "AUDIT"):
                raise SystemExit(
                    f"No stored run for {community.name!r}. Run FULL at least once first."
                )

        if mode == "EXPORT":
            community_id = community_row["community_id"]
            storage = CommunityStorage.create(storage_root, community_id, community.name)
            setup_logging(storage.logs,
                          console_level=self.settings.get("logging", "console_level", default="INFO"))
            outcome = _StoredOutcome(self.db, community_id)
            return self._finalise(community, community_id, storage, outcome, mode,
                                  coder_id=community.coder_id)

        estimate = self.estimate_workload(community, mode=mode) if estimate_first else None
        runner = CommunityRunner(self.settings, self.db, run_mode=mode, target=target,
                                 monitor=self.monitor, on_status=self._on_status,
                                 estimate=estimate, on_progress=self.on_progress,
                                 host_broker=self.host_broker)
        temporary_id = community_row["community_id"] if community_row else safe_name(community.name)
        storage = CommunityStorage.create(storage_root, temporary_id, community.name)
        setup_logging(storage.logs,
                      console_level=self.settings.get("logging", "console_level", default="INFO"),
                      file_level=self.settings.get("logging", "file_level", default="DEBUG"),
                      jsonl=bool(self.settings.get("logging", "jsonl", default=True)))
        event(log, "RUN", f"{mode} run for {community.name!r}")

        started = time.monotonic()
        outcome = asyncio.run(runner.run(community))
        wall_clock_s = time.monotonic() - started
        storage = runner.storage
        self._record_timings(outcome, estimate, wall_clock_s, mode)
        return self._finalise(community, outcome.community_id, storage, outcome, mode,
                              coder_id=community.coder_id)

    def _record_timings(self, outcome: RunOutcome, estimate: Estimate | None,
                        wall_clock_s: float, mode: str) -> None:
        """Write down what it actually took, so the next estimate is better."""
        for made in self.estimates:
            self.estimator.record(made, run_id=outcome.run_id,
                                  community_id=outcome.community_id)
        # Active time is the clock minus the time nobody was working: a pause
        # and an outage tell us nothing about how fast the machine is.
        idle_s = (outcome.offline_s or 0.0) + (outcome.paused_manual_s or 0.0)
        active_s = max(0.0, wall_clock_s - idle_s)
        estimated_active = 0.0
        if estimate is not None:
            estimated_active = (estimate.active_low_s + estimate.active_high_s) / 2
        stats = dict(outcome.stats)
        self.estimator.record_actual(
            run_id=outcome.run_id, community_id=outcome.community_id, mode=mode,
            estimated_active_s=estimated_active, actual_active_s=active_s,
            wall_clock_s=wall_clock_s, offline_s=outcome.offline_s,
            paused_manual_s=outcome.paused_manual_s,
            stats={**stats,
                   "errors": int(self.db.scalar(
                       "SELECT COUNT(*) FROM errors WHERE community_id=?",
                       (outcome.community_id,)) or 0),
                   "pauses_manual": outcome.pauses_manual,
                   "pauses_network": outcome.pauses_network,
                   "image_candidates": stats.get("image_candidates", 0)},
            final_state=outcome.final_state,
        )
        outcome.estimate = estimate.as_dict() if estimate is not None else {}
        outcome.stats["timing"] = {
            "wall_clock_s": round(wall_clock_s, 1),
            "active_s": round(active_s, 1),
            "offline_s": round(outcome.offline_s, 1),
            "paused_manual_s": round(outcome.paused_manual_s, 1),
            "estimated_active_s": round(estimated_active, 1),
        }

    # -- estimation --------------------------------------------------------
    def estimate_workload(self, community: CommunityInput, *,
                          mode: str = "FULL") -> Estimate | None:
        """Say how long this is likely to take, before the expensive part.

        Two figures, in this order (brief §31, §32): one from the researcher's
        input alone, then a revised one after a handful of cheap requests have
        shown how big the sites actually are. The second is the useful one, and
        the difference between them is explained rather than left to be noticed.
        """
        if not bool(self.settings.get("estimation", "enabled", default=True)):
            return None
        if mode in ("EXPORT", "AUDIT", "RECONCILE"):
            return None       # these touch no network and take seconds

        initial = self.estimator.initial(community, mode=mode)
        self.estimates = [initial]
        print("\n" + "-" * 78)
        print("  ESTIMATED WORKLOAD  (an estimate, not a guarantee)")
        print("-" * 78)
        for line in initial.lines():
            print(f"  {line}")
        for note in initial.workload.notes[:4]:
            print(f"    - {note}")

        if not bool(self.settings.get("estimation", "probe_sources", default=True)):
            print("-" * 78)
            return initial
        if not community.urls:
            print("-" * 78)
            return initial

        print("\n  Looking briefly at each address to size the job "
              "(robots, sitemaps, home page)...")
        try:
            updated = asyncio.run(self._probe_and_estimate(community, initial, mode))
        except Exception as exc:                  # sizing must never stop research
            log.warning("[ESTIMATE] discovery probe failed: %s", exc)
            print(f"  Discovery probe failed ({exc}); the initial estimate stands.")
            print("-" * 78)
            return initial
        if updated is None:
            print("-" * 78)
            return initial

        self.estimates.append(updated)
        print(f"\n  Initial estimate:  {initial.active_band} active")
        print(f"  Updated estimate:  {updated.active_band} active "
              f"({updated.wall_band} wall-clock)")
        print(f"  Why it changed:    {updated.reason}")
        for note in updated.workload.notes[:5]:
            print(f"    - {note}")
        print(f"\n  Discovery cost {self._probe_summary}")
        print("-" * 78)
        return updated

    async def _probe_and_estimate(self, community: CommunityInput,
                                  initial: Estimate, mode: str) -> Estimate | None:
        from .discovery.probe import probe_workload
        from .net.fetcher import Fetcher

        fetcher = Fetcher(user_agent=self.settings.user_agent, config=self.settings.app)
        try:
            probe = await probe_workload(
                community.urls, fetcher=fetcher, lexicon=self.settings.lexicon,
                max_sources=int(self.settings.get(
                    "estimation", "max_probe_sources", default=12) or 12),
            )
        finally:
            await fetcher.aclose()
        self._probe_summary = (f"{probe.requests_made} request(s) in "
                               f"{probe.elapsed_s:.1f}s.")
        return self.estimator.after_discovery(probe, initial, mode=mode)

    def _on_status(self, line: str) -> None:
        print(f"  {line}")

    # -- export and QC -----------------------------------------------------
    def _finalise(self, community: CommunityInput, community_id: str,
                  storage: CommunityStorage, outcome: Any, mode: str,
                  *, coder_id: str) -> dict[str, Any]:
        manifest = {
            "run_mode": mode,
            "run_id": getattr(outcome, "run_id", None),
            "community": community.name,
            "community_id": community_id,
            "latitude_supplied": community.latitude is not None,
            "longitude_supplied": community.longitude is not None,
            "country": community.country,
            "stages_in_mode": MODE_STAGES.get(mode, []),
            **self.settings.reproducibility_record(self.features),
        }

        workbook_name = (
            f"{community_id}_{safe_name(community.name)}_Stage1_Documentary_Coding.xlsx"
        )
        workbook_path = storage.final / workbook_name

        def build_exporter(*, aggressive: bool = False, core_only: bool = False):
            return WorkbookExporter(
                self.settings.workbook_template, self.settings.schema, self.db,
                coder_id=coder_id or f"DCR/{__version__}",
                decisions=self.settings.decisions,
                aggressive_sanitize=aggressive, core_only=core_only,
            )

        finalisation = finalise_workbook(
            exporter_factory=build_exporter, community_id=community_id,
            destination=workbook_path, manifest=manifest,
        )
        export_result = finalisation.export or _EmptyExport(workbook_path)
        if finalisation.ok:
            event(log, "EXPORT",
                  f"workbook written and reopened: {workbook_path.name} "
                  f"({sum(export_result.rows_written.values())} rows, "
                  f"{finalisation.verification.core_rows} coded rows verified)")
        else:
            log.error("[EXPORT] no usable workbook: %s", finalisation.failure_reason)
        if finalisation.sanitisation.occurred:
            event(log, "EXPORT", f"excel_sanitized=yes — "
                                 f"{finalisation.sanitisation.summary()}")
        for refusal in export_result.refusals[:10]:
            log.warning("[EXPORT] %s", refusal)

        manifest_counts = manifests.export_all(self.db, community_id, storage.final)

        qc = QualityControl(self.db, community_id, self.settings.schema,
                            storage_root=storage.root)
        qc_report = qc.run(workbook_path=workbook_path)

        pages = int(self.db.scalar(
            "SELECT COUNT(DISTINCT normalized_url) FROM pages WHERE community_id=?",
            (community_id,)) or 0)
        blocking = int(self.db.scalar(
            "SELECT COUNT(*) FROM review_queue WHERE community_id=? AND severity='blocking'",
            (community_id,)) or 0)
        status = completion_status(
            qc_report,
            truncated=bool(getattr(outcome, "truncated", False)),
            blocking_review=blocking,
            pages_opened=pages,
            min_pages=int(self.settings.get("quality", "min_pages_opened", default=25)),
            workbook_verified=finalisation.ok,
            budget_exhausted=bool(getattr(outcome, "budget_exhausted", False)),
            retrieval_stop_cause=str(getattr(outcome, "retrieval_stop_cause", "") or ""),
            blocked_sources=int(self.db.scalar(
                "SELECT COUNT(*) FROM sources WHERE community_id=? "
                "AND (crawl_status='blocked' OR access_status IN "
                "('blocked','login_required','forbidden'))", (community_id,)) or 0),
            reachable_sources=int(self.db.scalar(
                "SELECT COUNT(*) FROM sources WHERE community_id=? "
                "AND crawl_status='crawled'", (community_id,)) or 0),
        )
        self.db.update("communities", {"completion_status": status},
                       {"community_id": community_id})

        manifest["export"] = {
            "workbook": str(workbook_path),
            "rows_written": export_result.rows_written,
            "refusals": export_result.refusals,
            "manifests": manifest_counts,
            "finalisation": finalisation.as_dict(),
            "excel_sanitized": finalisation.sanitisation.as_dict()["excel_sanitized"],
        }
        report = report_mod.build_report(
            self.db, community_id, qc=qc_report, outcome=outcome, manifest=manifest,
            completion_status=status,
        )
        report_mod.write_markdown(report, storage.final / "completion_report.md")
        report_mod.write_json(report, storage.final / "completion_report.json")
        report_mod.write_json(manifest, storage.final / "run_manifest.json")
        report_mod.write_run_readme(report, storage.root / "README_run.md")

        self._print_summary(report, qc_report, workbook_path, storage)
        return {
            "report": report, "qc": qc_report, "workbook": workbook_path,
            "status": status, "output_dir": storage.root,
            # The flat view the run orchestrator stores in the queue. Built here
            # rather than dug out of the report by the caller, so one change to
            # the report cannot silently empty the multi-community summary.
            "completion_status": status,
            "community_id": community_id,
            "run_id": getattr(outcome, "run_id", ""),
            "crawl_truncated": bool(getattr(outcome, "truncated", False)),
            "review_items": blocking,
            "finalisation": finalisation.as_dict(),
            "workbook_path": str(workbook_path),
            "workbook_verified": bool(finalisation.ok),
            "yield": dict(getattr(outcome, "yield_summary", {}) or {}),
            "stats": {
                **dict(getattr(outcome, "stats", {}) or {}),
                "pages": pages,
                "conflicts": int(self.db.scalar(
                    "SELECT COUNT(*) FROM conflicts WHERE community_id=?",
                    (community_id,)) or 0),
                "evidence": int(self.db.scalar(
                    "SELECT COUNT(*) FROM evidence WHERE community_id=?",
                    (community_id,)) or 0),
                "claims": int(self.db.scalar(
                    "SELECT COUNT(*) FROM claims WHERE community_id=?",
                    (community_id,)) or 0),
                "sources": int(self.db.scalar(
                    "SELECT COUNT(*) FROM sources WHERE community_id=?",
                    (community_id,)) or 0),
                "documents": int(self.db.scalar(
                    "SELECT COUNT(*) FROM documents WHERE community_id=?",
                    (community_id,)) or 0),
                "images": int(self.db.scalar(
                    "SELECT COUNT(*) FROM images WHERE community_id=?",
                    (community_id,)) or 0),
            },
        }

    def _print_summary(self, report: Mapping[str, Any], qc_report: Any,
                       workbook_path: Path, storage: CommunityStorage) -> None:
        # The completion summary is for a researcher reading one community's
        # result. In a run of two hundred it is two hundred summaries scrolling
        # past the dashboard, so the orchestrator turns it off and the
        # per-community completion_report.md carries the same content.
        if self.settings.get("logging", "quiet_summary", default=False):
            return
        print("\n" + "=" * 78)
        print(f"  {report['community']}  —  {report['completion_status']}")
        print("=" * 78)
        state = report.get("final_state", "COMPLETED")
        if state in ("PAUSED_MANUAL", "PAUSED_NETWORK"):
            print(f"  RUN STATE            {state}  —  THIS RUN DID NOT FINISH")
            reason = (report.get("interruptions") or {}).get("pause_reason", "")
            if reason:
                print(f"                       {reason}")
            print("  Resume it with:      dcr --name \"%s\" --mode RESUME"
                  % report["community"])
            print("-" * 78)
        elif state == "CANCELLED":
            print("  RUN STATE            CANCELLED by the researcher; "
                  "what was found is kept")
            print("-" * 78)
        print(f"  Sources supplied     {report['sources_supplied']}")
        print(f"  Sources discovered   {report['sources_discovered']}")
        print(f"  Independence groups  {report['independence_groups']}"
              "   <- corroboration counts these, not URLs")
        print(f"  Pages opened         {report['pages_opened']}"
              f"  ({report['archived_pages_opened']} archived)")
        print(f"  Documents            {report['documents_downloaded']}"
              f"  ({report['documents_parsed']} parsed)")
        triage = report.get("image_triage") or {}
        print(f"  Images retained      {report['images_retained']}"
              f"  ({report['images_likely_relevant']} likely relevant)")
        if triage.get("candidates_seen"):
            print(f"  Image candidates     {triage['candidates_seen']} seen, "
                  f"{triage['downloaded']} downloaded "
                  f"({triage['download_rate']:.0%})"
                  "   <- the rest were recorded, not fetched")
        print(f"  Evidence items       {report['evidence_items']}")
        print(f"  Academic databases   {report['academic_databases_searched']} searched, "
              f"{report['academic_records_verified']} records verified")
        print(f"  Fields coded         {report['fields_coded']}"
              f"  ({report['fields_not_found']} NOT FOUND, "
              f"{report['fields_requiring_review']} for review)")
        print(f"  Conflicts            {report['conflicts']} "
              f"({report['conflicts_unresolved']} unresolved)")
        print(f"  crawl_truncated      {report['crawl_truncated']}")
        interruptions = report.get("interruptions") or {}
        if interruptions.get("pauses_manual") or interruptions.get("pauses_network"):
            print(f"  Interruptions        {interruptions.get('pauses_manual', 0)} manual, "
                  f"{interruptions.get('pauses_network', 0)} network "
                  f"({interruptions.get('offline_s', 0):.0f}s offline)")
        budget = report.get("budget") or {}
        if budget:
            ceiling = budget.get("ceiling_s")
            cause = report.get("retrieval_stop_cause") or ""
            note = {
                "exhausted": "   <- the community was worked out",
                "ceiling": "   <- the configured ceiling stopped this run",
                "requested": "   <- stopped on request",
            }.get(cause, "")
            print(f"  Active time          {budget.get('active_s', 0) / 60:.1f} min"
                  + (f" of a {ceiling / 60:.0f} min ceiling" if ceiling else "")
                  + note)
        measured = report.get("yield") or {}
        if measured.get("evidence_yield_per_min"):
            print(f"  Evidence yield       "
                  f"{measured['evidence_yield_per_min']:.1f} units/min "
                  f"({measured.get('independent_yield_per_min', 0):.1f} independent)")
        activities = ((report.get("profile") or {}).get("activities") or {})
        shares = activities.get("by_activity_pct") or {}
        if shares:
            top = ", ".join(f"{k} {v}%" for k, v in list(shares.items())[:4])
            print(f"  Where time went      {top}")
        timing = report.get("timing") or {}
        if timing:
            print(f"  Time                 {timing.get('active_s', 0):.0f}s active, "
                  f"{timing.get('wall_clock_s', 0):.0f}s wall-clock"
                  + (f" (estimated {timing.get('estimated_active_s', 0):.0f}s active)"
                     if timing.get("estimated_active_s") else ""))
        failures = qc_report.failures
        warnings = qc_report.warnings
        print(f"  Quality checks       {len(qc_report.results) - len(failures) - len(warnings)}"
              f" passed, {len(warnings)} warnings, {len(failures)} failures")
        for check in failures[:5]:
            print(f"      FAIL  {check.number}. {check.name}: {check.detail}")
        if report["human_review_blocking"]:
            print(f"  HUMAN REVIEW         {report['human_review_blocking']} blocking item(s) "
                  "— see X8_Review_Queue")
        print("-" * 78)
        print(f"  Workbook   {workbook_path}")
        print(f"  Report     {storage.final / 'completion_report.md'}")
        print(f"  Folder     {storage.root}")
        print("=" * 78 + "\n")


class _EmptyExport:
    """Stands in when no export attempt produced a workbook.

    The run is still reported, with the failure recorded, rather than the
    process dying and leaving the researcher nothing at all.
    """

    def __init__(self, path):
        self.path = path
        self.rows_written: dict[str, int] = {}
        self.refusals: list[str] = []
        self.warnings: list[str] = ["no workbook could be produced"]
        self.omitted_sheets: dict[str, str] = {}


class _StoredOutcome:
    """Reconstructs a run summary from the database, for EXPORT mode."""

    def __init__(self, db: Database, community_id: str):
        row = db.query_one(
            "SELECT * FROM runs WHERE community_id=? ORDER BY started_utc DESC LIMIT 1",
            (community_id,))
        self.run_id = row["run_id"] if row else None
        self.community_id = community_id
        self.truncated = bool(row["truncated"]) if row else False
        self.truncation_reasons = (
            [r for r in (row["truncation_reason"] or "").split("; ") if r] if row else []
        )
        self.stats = json.loads(row["manifest_json"]) if row and row["manifest_json"] else {}
        stages = db.query(
            "SELECT * FROM run_stages WHERE run_id=? ORDER BY stage_no", (self.run_id,)
        ) if self.run_id else []
        self.stages = {
            r["stage_no"]: type("Stage", (), {"status": r["status"], "detail": r["detail"] or ""})()
            for r in stages
        }


def main(argv: Sequence[str] | None = None) -> int:
    from .cli import main as cli_main

    return cli_main(argv)
