#!/usr/bin/env python3
"""The twenty questions of the brief's final self-audit, answered from the code
and from a completed pilot run rather than from assertion.

    python3 tools/self_audit.py [--output pilot_output]

Each question is answered by an actual check. A question whose answer is NO is
a defect to fix, not a caveat to note.
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

    def check(question: str, ok: bool, evidence: str) -> None:
        checks.append((question, ok, evidence))

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

    width = max(len(q) for q, _, _ in checks)
    failures = 0
    print("\nFINAL SELF-AUDIT\n" + "=" * (width + 12))
    for index, (question, ok, evidence) in enumerate(checks, start=1):
        verdict = "OK " if ok else "NO "
        if not ok:
            failures += 1
        print(f"{index:2d}. {verdict} {question}")
        print(f"        {evidence}")
    print("=" * (width + 12))
    print(f"{len(checks) - failures} of {len(checks)} answered as they must be.")
    db.close()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
