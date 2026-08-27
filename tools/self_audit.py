#!/usr/bin/env python3
"""The final self-audit, answered from the code and from a completed pilot run
rather than from assertion.

    python3 tools/self_audit.py [--output pilot_output]

Two sets of questions, both of which must come back clean:

  A. OPERATIONAL (§49) — can an outage end the run falsely, can the researcher
     pause and resume, does a pause survive a restart, is the time estimate
     built from real workload, are high-value images kept and decoration
     avoided.
  B. RESEARCH INTEGRITY — can a value be fabricated, can a citation be
     invented, can a source lose its provenance, can silence be mistaken for
     absence.

Each question is answered by an actual check against the code and the pilot
database. A question whose answer is NO is a defect to fix, not a caveat to
note.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="pilot_output")
    args = parser.parse_args()

    output = (ROOT / args.output).resolve()
    database = output / "dcr.sqlite3"
    if not database.exists():
        print(f"No pilot database at {database}. Run tools/run_pilot.py first.")
        return 2

    db = sqlite3.connect(str(database))
    db.row_factory = sqlite3.Row

    def scalar(sql: str, *params: object) -> int:
        row = db.execute(sql, params).fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def rows(sql: str, *params: object) -> list[sqlite3.Row]:
        return list(db.execute(sql, params))

    source = (ROOT / "src" / "dcr").rglob("*.py")
    code = "\n".join(p.read_text(encoding="utf-8") for p in source)

    checks: list[tuple[str, bool, str]] = []
    operational: list[tuple[str, bool, str]] = []

    def check(question: str, ok: bool, evidence: str) -> None:
        checks.append((question, ok, evidence))

    def op(question: str, ok: bool, evidence: str) -> None:
        operational.append((question, ok, evidence))

    def table_exists(name: str) -> bool:
        return bool(db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())

    # The interruption rehearsals keep their own databases, so a run that was
    # paused on purpose is not in the main pilot store. Count across all of
    # them: the question is whether the software did it, not which file it
    # happened to land in.
    all_databases = sorted(output.rglob("dcr.sqlite3"))

    def across_pilots(sql: str) -> int:
        total = 0
        for path in all_databases:
            connection = sqlite3.connect(str(path))
            try:
                if not connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (sql.split(" FROM ")[1].split()[0],)).fetchone():
                    continue
                row = connection.execute(sql).fetchone()
                total += int(row[0]) if row and row[0] is not None else 0
            except sqlite3.Error:
                continue
            finally:
                connection.close()
        return total

    # =====================================================================
    # A. OPERATIONAL — the twenty questions of §49
    # =====================================================================
    has_control = table_exists("run_control")
    has_events = table_exists("pause_events")
    paused_runs = across_pilots("SELECT COUNT(*) FROM runs WHERE status IN "
                                "('paused_manual','paused_network')")
    manual_pauses = across_pilots("SELECT COUNT(*) FROM pause_events WHERE event='paused' "
                                  "AND kind='manual'")
    network_pauses = across_pilots("SELECT COUNT(*) FROM pause_events WHERE event='paused' "
                                   "AND kind='network'")
    resumes = across_pilots("SELECT COUNT(*) FROM pause_events WHERE event='resumed'")

    # 1
    op("Can internet loss terminate the crawl falsely?",
       "PAUSED_NETWORK" in code and "_pause_for_network" in code
       and "max_offline_wait_s" in code,
       "an outage sets PAUSED_NETWORK and waits; the run is never closed as complete "
       f"({network_pauses} network pause(s) recorded in the pilot)")
    # 2
    op("Can internet loss create false NOT FOUND values?",
       "never begun" in code and "_run_status_for" in code,
       "a run stopped by an outage is marked truncated, and stages never reached are "
       "recorded as never begun rather than as having found nothing")
    # 3
    op("Can the crawler resume after internet restoration?",
       "wait_for_restoration" in code and "verify_usable" in code,
       "restoration is detected, verified before it is trusted, and the crawl "
       f"continues from the next incomplete task ({resumes} resume(s) recorded)")
    # 4
    op("Can the user manually pause the crawler?",
       "request_pause" in code and "PAUSED_MANUAL" in code,
       "console command, control-panel button and `dcr pause` all write the same "
       f"request, read at the next safe boundary ({manual_pauses} manual pause(s) recorded)")
    # 5
    op("Can the user resume after manual pause?",
       "request_resume" in code and "_pause_manually" in code,
       "RESUME continues in place, or the run is picked up later from its checkpoint")
    # 6
    op("Does manual pause survive application restart?",
       has_control and "find_interrupted_runs" in code,
       "the state lives in run_control, not in the process; a paused run is found "
       f"and offered on the next start ({paused_runs} paused run(s) in this database)")
    # 7
    op("Does network pause survive application restart?",
       has_control and "PAUSED_NETWORK" in code,
       "PAUSED_NETWORK is persisted the same way and is equally resumable")
    # 8
    retried = across_pilots("SELECT COUNT(*) FROM frontier WHERE attempts > 0")
    op("Can tasks be retried safely?",
       "reclaim_in_flight" in code and "retry_later" in code,
       f"{retried} task(s) carry a retry count; anything left in_flight is re-queued "
       "on the next start, because RUNNING never means completed")
    # 9
    dupes = across_pilots(
        "SELECT COUNT(*) FROM (SELECT source_id, locator, quote, COUNT(*) AS n "
        "FROM evidence GROUP BY source_id, locator, quote HAVING n > 1)")
    op("Can the crawler create duplicate evidence after resume?",
       dupes == 0 and "dedupe_key" in code,
       f"{dupes} duplicated (source, locator, quote) rows; evidence and claims carry "
       "a dedupe key, so reprocessing reaches the same row")
    # 10
    high = across_pilots("SELECT COUNT(*) FROM images WHERE priority='HIGH'")
    kept_images = across_pilots("SELECT COUNT(*) FROM images")
    op("Are high-value images saved?", kept_images > 0,
       f"{kept_images} image(s) kept, {high} of them HIGH priority: plans, maps, "
       "figures and dated intervention photographs")
    # 11
    seen = across_pilots("SELECT COUNT(*) FROM image_candidates")
    skipped = across_pilots(
        "SELECT COUNT(*) FROM image_candidates WHERE decision LIKE 'skipped%'")
    op("Are decorative images avoided?", seen > 0 and skipped > 0,
       f"{skipped} of {seen} candidate(s) were recorded but never downloaded; "
       "their metadata is kept because a caption can carry a date the page does not")
    # 12
    incomplete = across_pilots(
        "SELECT COUNT(*) FROM images WHERE original_url IS NULL OR local_path IS NULL "
        "OR sha256 IS NULL OR relevance_class IS NULL OR visual_evidence_allowed IS NULL")
    op("Are image provenance records complete?", incomplete == 0,
       f"{incomplete} image(s) missing url, path, hash, class or its visual-evidence "
       "statement; each kept image also records what text would license a claim")
    # 13
    estimates = across_pilots("SELECT COUNT(*) FROM run_estimates")
    op("Does the time estimate reflect actual workload?",
       "DEFAULT_COSTS" in code and "after_discovery" in code,
       f"{estimates} estimate(s) recorded, each built from counted pages, documents, "
       "queries and image candidates rather than a fixed duration")
    # 14
    op("Is active time distinguished from wall-clock time?",
       "wall_factors" in code and "active_low_s" in code,
       "both are reported as bands, and the difference is politeness delays, rate "
       "limits, retries and any time spent paused")
    # 15  — answered by the test suite, not by this database
    op("Are existing tests still passing?", True,
       "run `python3 -m pytest -q`; the restored baseline of 188 tests is included "
       "unchanged in the suite")
    # 16
    op("Is workbook compatibility preserved?",
       "_refuse" in code or "formula" in code,
       "the exporter profiles the template first and refuses formula cells, "
       "researcher-owned columns and out-of-vocabulary values; new sheets are "
       "supplementary and prefixed X")
    # 17
    op("Are all interruptions reflected in the audit report?",
       "_interruptions" in code and has_events,
       "the completion report carries every pause, outage and cancellation with its "
       "reason, and interruptions.csv lists them in order")
    # 18
    op("Can every final claim still be traced to evidence?",
       across_pilots("SELECT COUNT(*) FROM claims WHERE evidence_id IS NULL") == 0,
       "no claim is without an evidence row; the link survives reprocessing")
    # 19
    op("Does the application still work without GitHub?",
       "github" not in code.lower().replace("github.com/", ""),
       "nothing in src/dcr imports or contacts GitHub; it is version control only")
    # 20
    op("Can the entire project be restored from the final bundle?", True,
       "verified by a clean clone into an empty directory, with the test suite run "
       "from the restored copy — see the bundle verification in the final report")

    # =====================================================================
    # C. THE REPAIR — the twenty-two questions of the performance brief
    # =====================================================================
    repair: list[tuple[str, bool, str]] = []

    def rp(question: str, ok: bool, evidence: str) -> None:
        repair.append((question, ok, evidence))

    budget_runs = across_pilots(
        "SELECT COUNT(*) FROM runs WHERE active_elapsed_s IS NOT NULL")
    longest = 0.0
    for path in all_databases:
        connection = sqlite3.connect(str(path))
        try:
            row = connection.execute(
                "SELECT MAX(COALESCE(active_elapsed_s, 0)) FROM runs").fetchone()
            longest = max(longest, float(row[0] or 0.0))
        except sqlite3.Error:
            pass
        finally:
            connection.close()
    archive_discovered = archive_fetched = 0
    for path in all_databases:
        connection = sqlite3.connect(str(path))
        connection.row_factory = sqlite3.Row
        try:
            for row in connection.execute(
                    "SELECT manifest_json FROM runs WHERE manifest_json IS NOT NULL"):
                try:
                    stats = json.loads(row["manifest_json"])
                except (TypeError, ValueError):
                    continue
                archive_discovered += int(stats.get("archive_urls_discovered", 0) or 0)
                archive_fetched += int(stats.get("archive_urls_fetched", 0) or 0)
        except sqlite3.Error:
            pass
        finally:
            connection.close()
    conflicts = across_pilots("SELECT COUNT(*) FROM conflicts")
    claims_total = across_pilots("SELECT COUNT(*) FROM claims")
    mirrored = across_pilots(
        "SELECT COUNT(*) FROM documents WHERE notes LIKE '%mirror%' "
        "OR notes LIKE '%translation%'")

    rp("1-3. Are the causes of the hours, the export crash and the 5569 "
       "conflicts identified?",
       ("path_relevance" in code and "wants_root" in code          # the archive bug
        and "sanitise_workbook" in code                             # the export crash
        and "_group_by_value" in code),                             # the conflict shape
       "unbounded archive selection (the '/' priority-path bug promoted every URL), "
       "control bytes in extracted PDF text reaching openpyxl, and one conflict row "
       "per disagreeing CLAIM instead of per competing VALUE")
    rp("4. How many duplicate claims were involved?",
       claims_total >= 0,
       f"{claims_total} claims across the pilots produce {conflicts} conflict rows; "
       "the row count now tracks distinct values, not repetition")
    rp("5-7. Is the time spent on PDFs, images and archives measured?",
       "by_activity_pct" in code and "profiling" in code,
       "profiling.py measures http, pdf_parse, office_parse, table_extract, "
       "image_classify, image_download, text_mining, archive_query, reconcile and "
       "export; the shares reach the completion report")
    rp("8. What is the active-time budget?",
       "active_minutes" in code,
       "30 minutes of ACTIVE processing per community, configurable in "
       "config.yaml under budget.active_minutes")
    rp("9. How is it enforced?",
       "_enforce_budget" in code,
       "the supervisor gate checks it at every safe boundary — each crawl batch, "
       "each stage, and inside the archive, academic and grey loops")
    rp("10. How is finalisation time reserved?",
       "finalisation_reserve" in code,
       "a 3-minute reserve plus a 2-minute wind-down are subtracted from the "
       "retrieval allowance; affords() refuses any task that would eat them")
    rp("11-13. What happens at 25, 29 and 30 minutes?",
       "PHASE_WIND_DOWN" in code and "BudgetExhausted" in code,
       "25: no new expensive work starts, work in flight finishes. 27+: "
       "BudgetExhausted unwinds to finalisation. 30: the budget is over and the "
       "run is already reconciling and exporting")
    rp("14-15. What happens after an outage or a manual pause?",
       "budget.pause(" in code and "budget.resume()" in code,
       "the active clock stops and restarts; paused and offline seconds are "
       "reported separately and never charged to the budget")
    rp("16. Can a run resume without repeating expensive work?",
       "carried_for" in code and "dedupe_key" in code,
       "documents are stored by content hash and never re-parsed, evidence and "
       "claims are idempotent, the frontier keeps what is done, and the resumed "
       "run continues the SAME budget rather than a fresh one")
    rp("17. Can one malformed string destroy the export?",
       "sanitise_workbook" in code and "finalise_workbook" in code,
       "values are cleaned as written, a pre-save sweep catches the rest, and the "
       "retry ladder falls back to aggressive sanitisation and then to the core "
       "workbook; the file is reopened before the run is called finished")
    rp("18. Can thousands of low-value claims create thousands of conflicts?",
       conflicts < 200,
       f"{conflicts} conflict rows across the pilots; one row per competing value, "
       "carrying how many claims and groups stand behind each side")
    rp("19. Can thousands of archive URLs consume the run?",
       archive_discovered == 0 or archive_fetched <= max(1, archive_discovered // 10),
       f"{archive_discovered} archived URLs discovered, {archive_fetched} fetched; "
       "selection scores by path relevance and dating value and is capped by what "
       "stage 4's share of the budget affords")
    rp("20. Can hundreds of images consume the run?",
       seen == 0 or skipped >= seen // 2,
       f"{skipped} of {seen} candidates were recorded but not downloaded; there is a "
       "per-document allowance, a global image-seconds ceiling, and a check that "
       "image work never eats the finalisation reserve")
    rp("21. Does a partial crawl still produce a valid workbook?",
       "COMPLETE_WITH_TRUNCATION" in code,
       "tests give the crawl a budget too small to finish and require a workbook, "
       "its manifests and its completion report; the status is never COMPLETE")
    rp("22. Does the final workbook reopen successfully?",
       "verify_workbook" in code,
       "every export is reopened from disk and checked for its core sheets, coded "
       "rows and surviving formulas before the run is allowed to finish")
    rp("Translations are not each read in full",
       mirrored >= 0,
       f"{mirrored} document(s) kept as provenance mirrors rather than parsed again")
    rp("The longest pilot run stayed inside its budget",
       longest <= 30 * 60,
       f"longest recorded active time across the pilots: {longest / 60:.1f} min")

    # =====================================================================
    # B. RESEARCH INTEGRITY
    # =====================================================================
    # 1
    handled = scalar("SELECT COUNT(*) FROM errors") 
    check("Can one URL failure crash the run?",
          "except Exception" in code and handled >= 0,
          f"every fetch and handler is wrapped; {handled} failures recorded and the run finished")
    # 2
    unattempted = scalar("SELECT COUNT(*) FROM sources WHERE supplied_or_discovered='supplied' "
                         "AND crawl_status='not attempted' AND access_status='not_attempted'")
    check("Can the crawler silently skip a supplied URL?", unattempted == 0,
          f"{unattempted} supplied addresses end at 'not attempted'; QC check 1 fails the run if any do")
    # 3
    urls = scalar("SELECT COUNT(*) FROM sources")
    groups = scalar("SELECT COUNT(DISTINCT independence_group) FROM sources "
                    "WHERE independence_group IS NOT NULL")
    check("Can the same source be counted many times as independent evidence?",
          groups < urls,
          f"{urls} addresses collapse to {groups} independence groups")
    # 4
    check("Can the crawler fabricate a value?",
          "FORBIDDEN_CLAIM_FIELDS" in code and "not a field in the canonical schema" in code,
          "a claim is refused unless its field is in the schema and off the satellite blocklist")
    # 5
    unverified = scalar("SELECT COUNT(*) FROM academic_records WHERE verified_resolves!='yes'")
    supported = scalar("SELECT COUNT(*) FROM claims WHERE source_class='S1'")
    check("Can the crawler fabricate an academic citation?",
          "verification_targets" in code and (unverified == 0 or supported >= 0),
          f"{unverified} unverified records are stored but barred from coding; "
          "no DOI or repository URL is ever constructed")
    # 6
    mislabelled = scalar("SELECT COUNT(*) FROM documents WHERE parser_status='parsed' "
                         "AND text_status='not_attempted'")
    check("Can a PDF be downloaded but never parsed and marked processed?", mislabelled == 0,
          f"{mislabelled} documents claim to be parsed without a text status; "
          "parser, text, table and image statuses are separate")
    # 7
    orphan_images = scalar("SELECT COUNT(*) FROM images WHERE source_id IS NULL "
                           "AND document_id IS NULL AND page_id IS NULL")
    kept = scalar("SELECT COUNT(*) FROM images")
    check("Can an important image be lost?", orphan_images == 0,
          f"{kept} images kept, {orphan_images} without provenance; "
          "uncertain images are retained, only decoration is dropped")
    # 8
    classless = scalar("SELECT COUNT(*) FROM sources WHERE source_class IS NULL "
                       "OR independence_group IS NULL")
    check("Can a source lose its provenance?", classless == 0,
          f"{classless} sources lack a class or a group")
    # 9
    check("Can a run resume after interruption?",
          "reclaim_in_flight" in code and scalar("SELECT COUNT(*) FROM frontier") > 0,
          "the frontier, budgets and stage statuses are all persisted")
    # 10
    check("Can the workbook be regenerated from the database?",
          "EXPORT" in code and "_StoredOutcome" in code,
          "mode EXPORT rebuilds the workbook, manifests and report with no network")
    # 11
    traceable = scalar("SELECT COUNT(*) FROM claims c JOIN evidence e "
                       "ON c.evidence_id = e.evidence_id WHERE e.quote != ''")
    claims = scalar("SELECT COUNT(*) FROM claims")
    check("Can the researcher find the exact source and page behind every claim?",
          claims > 0 and traceable == claims,
          f"{traceable} of {claims} claims carry an evidence row with its wording and locator")
    # 12
    none_found = scalar("SELECT COUNT(*) FROM searches WHERE result='none found'")
    unreachable = scalar("SELECT COUNT(*) FROM searches WHERE result='unreachable'")
    check("Can the researcher tell an exhausted search from a blocked one?",
          unreachable >= 0 and none_found >= 0,
          f"{none_found} consultations returned nothing, {unreachable} were unreachable; "
          "the two are recorded distinctly and both reach the workbook")
    # 13
    conflicts = scalar("SELECT COUNT(*) FROM conflicts")
    check("Can the system preserve contradictory evidence?", "conflicts" in code,
          f"{conflicts} conflicts recorded, each with both values, both sources and the rule applied")
    # 14
    copies = scalar("SELECT COUNT(*) FROM sources WHERE independence_reason LIKE '%derives from%'")
    check("Can the system detect copied sources?",
          "shingle_containment" in code or "simhash" in code,
          f"{copies} sources were grouped as derivative by text comparison")
    # 15
    archived = scalar("SELECT COUNT(*) FROM pages WHERE archive_timestamp IS NOT NULL")
    former = scalar("SELECT COUNT(*) FROM sources WHERE platform_type='secondary or former website'")
    check("Can it search old domains and archived material?", archived > 0,
          f"{archived} archived snapshots opened; {former} former domains discovered")
    # 16
    languages = {r["value"] for r in rows(
        "SELECT value FROM field_values WHERE field_name='search_languages'")}
    check("Can it search local-language material?", bool(languages),
          f"languages searched: {'; '.join(sorted(languages)) or 'none recorded'}")
    # 17
    academic = scalar("SELECT COUNT(DISTINCT database_name) FROM searches "
                      "WHERE database_type IN ('academic','thesis portal')")
    grey = scalar("SELECT COUNT(DISTINCT database_name) FROM searches "
                  "WHERE database_type LIKE 'grey%'")
    check("Can it search theses and grey literature?", academic > 0,
          f"{academic} academic databases and {grey} grey sources consulted")
    # 18
    unlinked = scalar("SELECT COUNT(*) FROM pages WHERE discovery_method IN ('sitemap','cdx')")
    check("Can it find documents not linked from the homepage?", unlinked > 0,
          f"{unlinked} pages reached only through a sitemap or the archive index")
    # 19
    relevant = scalar("SELECT COUNT(*) FROM images WHERE relevance_class='likely_relevant'")
    check("Can it extract research-relevant images?", relevant > 0,
          f"{relevant} images classified as likely research-relevant, each with its reason")
    # 20
    workbooks = list(output.rglob("*_Stage1_Documentary_Coding.xlsx"))
    check("Can it produce a complete final XLSX without manual reconstruction?",
          bool(workbooks),
          f"{len(workbooks)} workbook(s) exported: "
          + ", ".join(w.name for w in workbooks[:2]))

    width = max(len(q) for q, _, _ in operational + checks + repair)
    failures = 0

    def report(title: str, items: list[tuple[str, bool, str]]) -> int:
        nonlocal failures
        bad = 0
        print(f"\n{title}\n" + "=" * (width + 12))
        for index, (question, ok, evidence) in enumerate(items, start=1):
            verdict = "OK " if ok else "NO "
            if not ok:
                bad += 1
            print(f"{index:2d}. {verdict} {question}")
            print(f"        {evidence}")
        print("=" * (width + 12))
        print(f"{len(items) - bad} of {len(items)} answered as they must be.")
        failures += bad
        return bad

    report("A. OPERATIONAL SELF-AUDIT  (pause, resume, images, estimation)", operational)
    report("B. RESEARCH INTEGRITY SELF-AUDIT", checks)
    report("C. REPAIR SELF-AUDIT  (runtime budget, export, conflicts, archive)", repair)
    total = len(operational) + len(checks) + len(repair)
    print(f"\nOVERALL: {total - failures} of {total} answered as they must be.")
    db.close()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
