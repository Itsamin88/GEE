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
        # How the run ended, and every time it stopped on the way. Without this
        # a reader cannot tell a stage that found nothing from a stage that was
        # never allowed to run (brief §37).
        "final_state": getattr(outcome, "final_state", "COMPLETED"),
        "interruptions": _interruptions(db, community_id, outcome),
        "queue": _queue_state(db, community_id),
        "image_triage": _image_triage(db, community_id),
        "timing": dict(getattr(outcome, "stats", {}).get("timing", {})),
        "estimate": dict(getattr(outcome, "estimate", {}) or {}),
        # The clock: what the run was allowed, what it used, and whether the
        # ceiling — rather than the sources — is why it stopped (brief §29).
        "budget": dict(getattr(outcome, "budget", {}) or {}),
        "retrieval_stop_cause": getattr(outcome, "retrieval_stop_cause", ""),
        # What the crawl found per active minute, and the shape of the curve
        # the stopping decision reacted to (brief §25, §93).
        "yield": dict(getattr(outcome, "yield_summary", {}) or {}),
        "archive_truncated": list(getattr(outcome, "archive_truncated", []) or []),
        "profile": dict(getattr(outcome, "profile", {}) or {}),
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


def _interruptions(db: Database, community_id: str, outcome: Any) -> dict[str, Any]:
    """Every pause, outage and cancellation, so none of them reads as absence."""
    run_id = getattr(outcome, "run_id", None)
    events = db.query(
        "SELECT event, kind, from_state, to_state, stage_no, source_id, "
        "tasks_done, tasks_total, detail, ts_utc FROM pause_events "
        "WHERE community_id=? ORDER BY event_id", (community_id,))
    interesting = [dict(row) for row in events
                   if row["event"] not in ("checkpoint",)]
    # Counted over every run for this community, not just the last one. The
    # workbook is built from all the evidence gathered across runs, so a reader
    # asking "was anything interrupted?" must be told about the run that was
    # paused, not only about the run that finished (brief §37).
    counted = {
        "manual": sum(1 for e in interesting
                      if e["event"] == "paused" and e["kind"] == "manual"),
        "network": sum(1 for e in interesting
                       if e["event"] == "paused" and e["kind"] == "network"),
    }
    return {
        "final_state": getattr(outcome, "final_state", "COMPLETED"),
        "pause_reason": getattr(outcome, "pause_reason", ""),
        "pauses_manual": max(counted["manual"],
                             int(getattr(outcome, "pauses_manual", 0) or 0)),
        "pauses_network": max(counted["network"],
                              int(getattr(outcome, "pauses_network", 0) or 0)),
        "pauses_this_run": {
            "manual": int(getattr(outcome, "pauses_manual", 0) or 0),
            "network": int(getattr(outcome, "pauses_network", 0) or 0),
        },
        "offline_s": round(float(getattr(outcome, "offline_s", 0.0) or 0.0), 1),
        "paused_manual_s": round(float(getattr(outcome, "paused_manual_s", 0.0) or 0.0), 1),
        "connectivity_losses": sum(1 for e in interesting
                                   if e["event"] == "connectivity_lost"),
        "events": interesting[-40:],
        "run_id": run_id,
    }


def _queue_state(db: Database, community_id: str) -> dict[str, int]:
    """What was completed, what remains, what failed (brief §26, §37)."""
    rows = db.query(
        "SELECT status, COUNT(*) AS n FROM frontier WHERE community_id=? GROUP BY status",
        (community_id,))
    return {row["status"]: int(row["n"]) for row in rows}


def _image_triage(db: Database, community_id: str) -> dict[str, Any]:
    """What the image triage saw and what it decided (brief §5, §10)."""
    rows = db.query(
        "SELECT decision, COUNT(*) AS n FROM image_candidates WHERE community_id=? "
        "GROUP BY decision", (community_id,))
    decisions = {row["decision"]: int(row["n"]) for row in rows}
    priorities = {
        row["priority"]: int(row["n"]) for row in db.query(
            "SELECT priority, COUNT(*) AS n FROM image_candidates WHERE community_id=? "
            "GROUP BY priority", (community_id,))
    }
    seen = sum(decisions.values())
    downloaded = decisions.get("downloaded", 0)
    return {
        "candidates_seen": seen,
        "downloaded": downloaded,
        "by_decision": decisions,
        "by_priority": priorities,
        "download_rate": round(downloaded / seen, 3) if seen else 0.0,
    }

def _add_interruptions(add: Any, report: Mapping[str, Any]) -> None:
    """The honest account of every time the run stopped (brief §37)."""
    interruptions = report.get("interruptions") or {}
    queue = report.get("queue") or {}
    state = interruptions.get("final_state", "COMPLETED")
    stopped = (interruptions.get("pauses_manual", 0)
               + interruptions.get("pauses_network", 0))
    if not stopped and state == "COMPLETED":
        return

    add("## Interruptions")
    add("")
    if state in ("PAUSED_MANUAL", "PAUSED_NETWORK"):
        add(f"> **This run did not finish.** It stopped in `{state}` and is waiting to be "
            "resumed. Anything the protocol had not reached was NOT searched and NOT "
            "found to be absent — the two are different, and the stage table below says "
            "which is which.")
        add("")
    elif state == "CANCELLED":
        add("> **This run was cancelled by the researcher.** What it had already found is "
            "kept and exported; the rest was never attempted.")
        add("")
    if interruptions.get("pause_reason"):
        add(f"- Reason given: {interruptions['pause_reason']}")
    add(f"- Manual pauses: {interruptions.get('pauses_manual', 0)} "
        f"({interruptions.get('paused_manual_s', 0)} s)")
    add(f"- Network pauses: {interruptions.get('pauses_network', 0)} "
        f"({interruptions.get('offline_s', 0)} s offline)")
    if queue:
        add(f"- Queue at the end: "
            + ", ".join(f"{n} {status}" for status, n in sorted(queue.items())))
    events = interruptions.get("events") or []
    if events:
        add("")
        add("| When | Event | Kind | Where | Detail |")
        add("| --- | --- | --- | --- | --- |")
        for item in events[-20:]:
            where = f"stage {item.get('stage_no')}" if item.get("stage_no") is not None else ""
            if item.get("source_id"):
                where += f" / {item['source_id']}"
            add(f"| {item.get('ts_utc', '')} | {item.get('event', '')} | "
                f"{item.get('kind', '')} | {where} | "
                f"{_escape_cell(item.get('detail', ''))} |")
    add("")


def _add_budget(add: Any, report: Mapping[str, Any]) -> None:
    """The clock, and where its seconds went (brief §29, §49)."""
    budget = report.get("budget") or {}
    profile = report.get("profile") or {}
    if not budget and not profile:
        return
    add("## Time")
    add("")
    if budget:
        ceiling = budget.get("ceiling_s")
        add(f"- Active processing: **{budget.get('active_s', 0) / 60:.1f} min**"
            + (f" of a {ceiling / 60:.0f}-minute safety ceiling" if ceiling else
               " — no ceiling was set; the crawl ran while it was producing evidence"))
        add(f"- Wall clock: {budget.get('wall_clock_s', 0) / 60:.1f} min "
            f"(paused {budget.get('paused_manual_s', 0) / 60:.1f} min, offline "
            f"{budget.get('offline_s', 0) / 60:.1f} min — neither counts as active time)")
        cause = report.get("retrieval_stop_cause") or ""
        reason = budget.get("stop_reason") or ""
        if cause == "exhausted":
            add(f"- Retrieval ended because the community was worked out: {reason}. "
                "This is a complete search, not a truncated one.")
        elif cause == "ceiling":
            add("- **The configured safety ceiling, not the sources, is why this run "
                "stopped.** What it did not reach is listed above; nothing here may be "
                "read as an exhaustive search.")
        elif cause == "requested":
            add(f"- Retrieval was ended on request: {reason}. Nothing here may be read "
                "as an exhaustive search.")
    activities = (profile.get("activities") or {})
    shares = activities.get("by_activity_pct") or {}
    if shares:
        add("")
        add("| Activity | Share | Seconds | Calls |")
        add("| --- | ---: | ---: | ---: |")
        for activity, pct in list(shares.items())[:10]:
            seconds = (activities.get("by_activity_s") or {}).get(activity, 0)
            calls = (activities.get("calls") or {}).get(activity, 0)
            add(f"| {activity} | {pct}% | {seconds:.1f} | {calls} |")
        add("")
        add("Measured time can exceed wall clock: requests run concurrently.")
    stages = profile.get("by_stage_pct") or {}
    if stages:
        add("")
        add("Per stage: " + ", ".join(f"{k} {v}%" for k, v in stages.items() if v))
    add("")

def _add_image_triage(add: Any, report: Mapping[str, Any]) -> None:
    """What the image triage saw, kept and passed over (brief §5)."""
    triage = report.get("image_triage") or {}
    if not triage.get("candidates_seen"):
        return
    add("## Image triage")
    add("")
    add(f"{triage['candidates_seen']} image candidate(s) were seen and "
        f"{triage['downloaded']} downloaded "
        f"({triage['download_rate']:.0%}). Every candidate is recorded in "
        "`image_candidates` with its caption, alt text and file name, including "
        "the ones passed over: a gallery caption often carries a date that no "
        "text on the page gives.")
    add("")
    add("| Decision | Candidates |")
    add("| --- | ---: |")
    for decision, count in sorted(triage.get("by_decision", {}).items()):
        add(f"| {decision} | {count} |")
    add("")
    add("A photograph never sets a practice code. Each kept image records what it "
        "alone may evidence, and the sentence — if there is one — that would "
        "license a claim.")
    add("")


def _escape_cell(text: Any) -> str:
    return str(text or "").replace("|", "/").replace("\n", " ")[:160]

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
    add(f"- **How the run ended**: **{report.get('final_state', 'COMPLETED')}**")
    if report["truncation_reasons"]:
        add("")
        add("**Why the run is marked truncated**")
        for reason in report["truncation_reasons"]:
            add(f"- {reason}")
    add("")
    _add_interruptions(add, report)
    _add_budget(add, report)
    _add_image_triage(add, report)
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
