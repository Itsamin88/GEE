"""The completion report — human-readable and machine-readable.

Brief §56 and §57: what was searched, what was found, what was not, and which
of the six completion statuses this community ended in.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..db import Database
from ..qc.checks import QcReport

VERDICT_MARK = {"pass": "PASS", "fail": "FAIL", "warn": "WARN"}


def build_report(
    db: Database,
    community_id: str,
    *,
    qc: QcReport,
    outcome: Any,
    manifest: Mapping[str, Any],
    completion_status: str,
) -> dict[str, Any]:
    community = db.query_one("SELECT * FROM communities WHERE community_id=?", (community_id,))
    sources = db.query("SELECT * FROM sources WHERE community_id=?", (community_id,))
    supplied = [s for s in sources if s["supplied_or_discovered"] == "supplied"]
    discovered = [s for s in sources if s["supplied_or_discovered"] == "discovered"]

    def count(sql: str, params: Sequence[Any] = ()) -> int:
        return int(db.scalar(sql, tuple(params) or (community_id,)) or 0)

    by_extension = {
        row["extension"]: row["n"] for row in db.query(
            "SELECT extension, COUNT(*) AS n FROM documents WHERE community_id=? "
            "GROUP BY extension", (community_id,))
    }
    fields = db.query(
        "SELECT field_name, value, status, group_count FROM field_values WHERE community_id=?",
        (community_id,))
    coded = [f for f in fields if f["status"] == "coded"]
    not_found = [f for f in fields if f["status"] == "not_found"]
    review_needed = [f for f in fields if f["status"] == "review_required"]
    uncertain = [f for f in coded if (f["group_count"] or 0) < 2]

    report = {
        "community": community["name_input"],
        "community_id": community_id,
        "site_id": community["site_id"],
        "provenance_mode": community["provenance_mode"],
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_id": getattr(outcome, "run_id", None),
        "run_mode": manifest.get("run_mode"),
        "completion_status": completion_status,
        "sources_supplied": len(supplied),
        "sources_discovered": len(discovered),
        "unique_domains": len({s["registrable_domain"] for s in sources if s["registrable_domain"]}),
        # Read the resolved field rather than recounting: a verified thesis and
        # a dated grant record are independent voices without being crawled
        # addresses, and the report must not under-report them.
        "independence_groups": _independence_groups(db, community_id, sources),
        "pages_opened": count("SELECT COUNT(DISTINCT normalized_url) FROM pages WHERE community_id=?"),
        "archived_pages_opened": count(
            "SELECT COUNT(*) FROM pages WHERE community_id=? AND archive_timestamp IS NOT NULL"),
        "documents_downloaded": count("SELECT COUNT(*) FROM documents WHERE community_id=?"),
        "documents_by_type": by_extension,
        "documents_parsed": count(
            "SELECT COUNT(*) FROM documents WHERE community_id=? AND parser_status='parsed'"),
        "documents_unparsed": count(
            "SELECT COUNT(*) FROM documents WHERE community_id=? AND parser_status != 'parsed'"),
        "images_retained": count("SELECT COUNT(*) FROM images WHERE community_id=?"),
        "images_likely_relevant": count(
            "SELECT COUNT(*) FROM images WHERE community_id=? AND relevance_class='likely_relevant'"),
        "tables_extracted": count("SELECT COUNT(*) FROM document_tables WHERE community_id=?"),
        "evidence_items": count("SELECT COUNT(*) FROM evidence WHERE community_id=?"),
        "claims": count("SELECT COUNT(*) FROM claims WHERE community_id=?"),
        "academic_databases_searched": count(
            "SELECT COUNT(DISTINCT database_name) FROM searches WHERE community_id=? "
            "AND database_type IN ('academic','thesis portal')"),
        "academic_records_found": count(
            "SELECT COUNT(*) FROM academic_records WHERE community_id=?"),
        "academic_records_verified": count(
            "SELECT COUNT(*) FROM academic_records WHERE community_id=? AND verified_resolves='yes'"),
        "academic_full_texts_opened": count(
            "SELECT COUNT(*) FROM academic_records WHERE community_id=? "
            "AND full_text_status='full text'"),
        "grey_sources_searched": count(
            "SELECT COUNT(DISTINCT database_name) FROM searches WHERE community_id=? "
            "AND database_type LIKE 'grey%'"),
        "archive_domains_searched": count(
            "SELECT COUNT(*) FROM searches WHERE community_id=? AND database_type='archive'"),
        "negative_consultations": count(
            "SELECT COUNT(*) FROM searches WHERE community_id=? AND result='none found'"),
        "unreachable_consultations": count(
            "SELECT COUNT(*) FROM searches WHERE community_id=? AND result='unreachable'"),
        "errors_recorded": count("SELECT COUNT(*) FROM errors WHERE community_id=?"),
        "errors_unresolved": count(
            "SELECT COUNT(*) FROM errors WHERE community_id=? AND unresolved=1"),
        "blocked_sources": count(
            "SELECT COUNT(*) FROM sources WHERE community_id=? AND crawl_status='blocked'"),
        "fields_coded": len(coded),
        "fields_not_found": len(not_found),
        "fields_requiring_review": len(review_needed),
        "fields_on_one_group": len(uncertain),
        "conflicts": count("SELECT COUNT(*) FROM conflicts WHERE community_id=?"),
        "conflicts_unresolved": count(
            "SELECT COUNT(*) FROM conflicts WHERE community_id=? AND resolution_type='unresolved'"),
        "human_review_items": count("SELECT COUNT(*) FROM review_queue WHERE community_id=?"),
        "human_review_blocking": count(
            "SELECT COUNT(*) FROM review_queue WHERE community_id=? AND severity='blocking'"),
        "stages": {
            str(number): {"status": stage.status, "detail": stage.detail}
            for number, stage in getattr(outcome, "stages", {}).items()
        },
        "crawl_truncated": "yes" if getattr(outcome, "truncated", False) else "no",
        "truncation_reasons": list(getattr(outcome, "truncation_reasons", [])),
        "not_found_fields": sorted(f["field_name"] for f in not_found),
        "review_fields": sorted(f["field_name"] for f in review_needed),
        "quality_checks": [
            {"number": r.number, "name": r.name, "verdict": r.verdict, "detail": r.detail,
             "evidence": r.evidence}
            for r in qc.results
        ],
        "coverage_matrix": qc.coverage,
        "crawl_stats": getattr(outcome, "stats", {}),
        "manifest": dict(manifest),
    }
    return report


def _independence_groups(db: Database, community_id: str, sources: Sequence[Any]) -> int:
    row = db.query_one(
        "SELECT value FROM field_values WHERE community_id=? AND field_name='independence_groups' "
        "AND status='coded'", (community_id,))
    if row and str(row["value"]).isdigit():
        return int(row["value"])
    return len({s["independence_group"] for s in sources if s["independence_group"]})


def write_markdown(report: Mapping[str, Any], path: Path) -> Path:
    lines: list[str] = []
    add = lines.append
    add(f"# Completion report — {report['community']}")
    add("")
    if report.get("provenance_mode") == "FIXTURE":
        add("> **FIXTURE RUN.** This community was crawled against a local test fixture, not the "
            "live web. Nothing here is research evidence.")
        add("")
    add(f"- **Community id**: `{report['community_id']}`  ")
    add(f"- **Run**: `{report.get('run_id')}` ({report.get('run_mode')})  ")
    add(f"- **Generated**: {report['generated_utc']}  ")
    add(f"- **Completion status**: **{report['completion_status']}**  ")
    add(f"- **crawl_truncated**: **{report['crawl_truncated']}**")
    if report["truncation_reasons"]:
        add("")
        add("**Why the run is marked truncated**")
        for reason in report["truncation_reasons"]:
            add(f"- {reason}")
    add("")
    add("## What was retrieved")
    add("")
    add("| Measure | Count |")
    add("| --- | ---: |")
    for label, key in (
        ("Sources supplied", "sources_supplied"),
        ("Sources discovered", "sources_discovered"),
        ("Unique domains", "unique_domains"),
        ("Independence groups", "independence_groups"),
        ("Pages opened", "pages_opened"),
        ("  of which archived snapshots", "archived_pages_opened"),
        ("Documents downloaded", "documents_downloaded"),
        ("  parsed", "documents_parsed"),
        ("  stored but not parsed", "documents_unparsed"),
        ("Tables extracted", "tables_extracted"),
        ("Images retained", "images_retained"),
        ("  likely research-relevant", "images_likely_relevant"),
        ("Evidence items", "evidence_items"),
        ("Claims", "claims"),
        ("Academic databases searched", "academic_databases_searched"),
        ("Academic records found", "academic_records_found"),
        ("  verified", "academic_records_verified"),
        ("  full texts opened", "academic_full_texts_opened"),
        ("Grey-literature sources searched", "grey_sources_searched"),
        ("Archive domains searched", "archive_domains_searched"),
        ("Consultations returning nothing", "negative_consultations"),
        ("Consultations unreachable", "unreachable_consultations"),
        ("Errors recorded", "errors_recorded"),
        ("  unresolved", "errors_unresolved"),
        ("Blocked sources", "blocked_sources"),
    ):
        add(f"| {label} | {report.get(key, 0)} |")
    if report.get("documents_by_type"):
        add("")
        add("Documents by type: "
            + ", ".join(f"{k or 'unknown'} {v}" for k, v in
                        sorted(report["documents_by_type"].items())))

    add("")
    add("## Stages")
    add("")
    add("| Stage | Status | Detail |")
    add("| --- | --- | --- |")
    for number in sorted(report["stages"], key=lambda n: int(n)):
        stage = report["stages"][number]
        add(f"| {number} | {stage['status']} | {_escape(stage['detail'])} |")

    add("")
    add("## Source coverage")
    add("")
    add("| Source class | Searched | Found | Opened | Evidence yielded | Failed or blocked |")
    add("| --- | ---: | ---: | ---: | ---: | ---: |")
    for row in report["coverage_matrix"]:
        add(f"| {row['source_class']} {row['label']} | {row['searched']} | {row['found']} | "
            f"{row['opened']} | {row['evidence_yielded']} | {row['failed_or_blocked']} |")

    add("")
    add("## Fields")
    add("")
    add(f"- Coded: **{report['fields_coded']}**")
    add(f"- NOT FOUND: **{report['fields_not_found']}**")
    add(f"- Requiring human review: **{report['fields_requiring_review']}**")
    add(f"- Resting on a single independence group: **{report['fields_on_one_group']}**")
    add(f"- Conflicts recorded: **{report['conflicts']}** "
        f"({report['conflicts_unresolved']} left for a human)")
    if report["not_found_fields"]:
        add("")
        add("**NOT FOUND**: " + ", ".join(f"`{f}`" for f in report["not_found_fields"]))
    if report["review_fields"]:
        add("")
        add("**For review**: " + ", ".join(f"`{f}`" for f in report["review_fields"]))

    add("")
    add("## Quality control")
    add("")
    add("| # | Check | Verdict | Detail |")
    add("| ---: | --- | --- | --- |")
    for check in report["quality_checks"]:
        add(f"| {check['number']} | {_escape(check['name'])} | "
            f"{VERDICT_MARK.get(check['verdict'], check['verdict'])} | "
            f"{_escape(check['detail'])} |")

    add("")
    add("## Human review queue")
    add("")
    add(f"{report['human_review_items']} item(s), of which "
        f"{report['human_review_blocking']} block completion. "
        "See `X8_Review_Queue` in the workbook and `review_queue.jsonl`.")
    add("")
    add("---")
    add("")
    add("*This report states what was retrieved and what was not. An absence of evidence and an "
        "absence of effort are recorded differently: check `crawl_truncated`, the unreachable "
        "consultations, and the coverage matrix before reading a gap as a finding.*")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_json(report: Mapping[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8")
    return path


def write_run_readme(report: Mapping[str, Any], path: Path) -> Path:
    """A short orientation note inside the community's output folder."""
    text = f"""# {report['community']} — run output

This folder holds everything retrieved for this community.

| Folder | What is in it |
| --- | --- |
| `01_raw_sources/` | The exact HTML of every page opened |
| `02_documents/` | Every downloaded file, named by document id |
| `03_images/` | Retained images, named so each is traceable to its source |
| `04_archives/` | Files retrieved from web-archive snapshots |
| `05_extracted_text/` | Plain text extracted from pages and documents |
| `06_tables/` | Tables pulled out of PDFs and spreadsheets, as CSV |
| `07_evidence/` | Evidence exports |
| `08_logs/` | `run.log` and the machine-readable `events.jsonl` |
| `09_final/` | The workbook, the manifests and this report |
| `10_debug/` | Diagnostic output |

**Completion status: {report['completion_status']}**  
**crawl_truncated: {report['crawl_truncated']}**

{report['pages_opened']} pages opened · {report['documents_downloaded']} documents ·
{report['images_retained']} images · {report['evidence_items']} evidence items ·
{report['independence_groups']} independence groups

Start with `09_final/completion_report.md`. Every value in the workbook can be traced
from `X10_Field_Provenance` to a claim in `X2_Claim_Register`, to a passage in
`X1_Evidence_Register`, to a file in this folder.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _escape(text: Any) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ")[:300]
