"""The application: interactive prompts, run modes, and the export pipeline.

The researcher opens the project in PyCharm, presses RUN, types a name and some
URLs, and presses Enter. Everything else belongs inside the software (brief §5).
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import __version__
from .config import Settings, detect_optional_features, load_settings
from .db import Database
from .export import manifests, report as report_mod
from .export.workbook import WorkbookExporter
from .ids import safe_name
from .logging_setup import event, get_logger, setup_logging
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

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or load_settings()
        self.settings.output_root.mkdir(parents=True, exist_ok=True)
        self.db = Database(self.settings.database_path)
        self.features = detect_optional_features(self.settings)

    def close(self) -> None:
        self.db.close()

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
            target: str | None = None) -> dict[str, Any]:
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

        runner = CommunityRunner(self.settings, self.db, run_mode=mode, target=target)
        temporary_id = community_row["community_id"] if community_row else safe_name(community.name)
        storage = CommunityStorage.create(storage_root, temporary_id, community.name)
        setup_logging(storage.logs,
                      console_level=self.settings.get("logging", "console_level", default="INFO"),
                      file_level=self.settings.get("logging", "file_level", default="DEBUG"),
                      jsonl=bool(self.settings.get("logging", "jsonl", default=True)))
        event(log, "RUN", f"{mode} run for {community.name!r}")

        outcome = asyncio.run(runner.run(community))
        storage = runner.storage
        return self._finalise(community, outcome.community_id, storage, outcome, mode,
                              coder_id=community.coder_id)

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

        exporter = WorkbookExporter(
            self.settings.workbook_template, self.settings.schema, self.db,
            coder_id=coder_id or f"DCR/{__version__}",
            decisions=self.settings.decisions,
        )
        workbook_name = (
            f"{community_id}_{safe_name(community.name)}_Stage1_Documentary_Coding.xlsx"
        )
        workbook_path = storage.final / workbook_name
        export_result = exporter.export(community_id, workbook_path, manifest=manifest)
        event(log, "EXPORT", f"workbook written: {workbook_path.name} "
                             f"({sum(export_result.rows_written.values())} rows)")
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
        )
        self.db.update("communities", {"completion_status": status},
                       {"community_id": community_id})

        manifest["export"] = {
            "workbook": str(workbook_path),
            "rows_written": export_result.rows_written,
            "refusals": export_result.refusals,
            "manifests": manifest_counts,
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
        return {"report": report, "qc": qc_report, "workbook": workbook_path,
                "status": status, "output_dir": storage.root}

    def _print_summary(self, report: Mapping[str, Any], qc_report: Any,
                       workbook_path: Path, storage: CommunityStorage) -> None:
        print("\n" + "=" * 78)
        print(f"  {report['community']}  —  {report['completion_status']}")
        print("=" * 78)
        print(f"  Sources supplied     {report['sources_supplied']}")
        print(f"  Sources discovered   {report['sources_discovered']}")
        print(f"  Independence groups  {report['independence_groups']}"
              "   <- corroboration counts these, not URLs")
        print(f"  Pages opened         {report['pages_opened']}"
              f"  ({report['archived_pages_opened']} archived)")
        print(f"  Documents            {report['documents_downloaded']}"
              f"  ({report['documents_parsed']} parsed)")
        print(f"  Images retained      {report['images_retained']}"
              f"  ({report['images_likely_relevant']} likely relevant)")
        print(f"  Evidence items       {report['evidence_items']}")
        print(f"  Academic databases   {report['academic_databases_searched']} searched, "
              f"{report['academic_records_verified']} records verified")
        print(f"  Fields coded         {report['fields_coded']}"
              f"  ({report['fields_not_found']} NOT FOUND, "
              f"{report['fields_requiring_review']} for review)")
        print(f"  Conflicts            {report['conflicts']} "
              f"({report['conflicts_unresolved']} unresolved)")
        print(f"  crawl_truncated      {report['crawl_truncated']}")
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
