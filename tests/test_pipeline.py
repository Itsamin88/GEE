"""End-to-end pipeline tests against the local fixture web.

These exercise the production crawler, extractors, evidence model, exporter and
quality checks — only the endpoints are redirected at the fixture.
"""

from __future__ import annotations

import shutil
import socket
import sys
from pathlib import Path

import pytest
from openpyxl import load_workbook

from dcr.app import Application
from dcr.db import Database
from dcr.runner import CommunityInput
from fixtures.harness import fixture_settings, fixture_urls
from fixtures.server import FixtureServer

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_HOSTS = ("pourgues.test", "ancien-pourgues.test", "annuaire.test", "theses.test",
                 "facebook.test", "archive.test", "boekel.test", "oud-boekel.test")


def _hosts_resolve() -> bool:
    try:
        for host in FIXTURE_HOSTS:
            socket.gethostbyname(host)
        return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _hosts_resolve(),
    reason="the fixture hostnames do not resolve; run tools/run_pilot.py once to add them",
)


@pytest.fixture(scope="module")
def pilot(tmp_path_factory):
    output = tmp_path_factory.mktemp("pilot")
    server = FixtureServer().start()
    try:
        settings = fixture_settings(server.port, output, root=ROOT)
        app = Application(settings)
        app.preflight()
        community = CommunityInput(
            name="EcoVillage de Pourgues", latitude=43.0561, longitude=1.8342,
            urls=fixture_urls(server.port, "pourgues"), country="France",
            coder_id="TEST", fixture=True,
        )
        result = app.run(community, mode="FULL")
        db = Database(settings.database_path)
        yield {"result": result, "db": db, "settings": settings, "app": app,
               "community": community, "server": server, "output": output}
        db.close()
        app.close()
    finally:
        server.stop()


# -- what the crawl retrieved ----------------------------------------------
def test_the_supplied_and_discovered_addresses_are_all_recorded(pilot):
    db, cid = pilot["db"], pilot["result"]["report"]["community_id"]
    sources = db.query("SELECT * FROM sources WHERE community_id=?", (cid,))
    assert len(sources) >= 3
    assert all(s["source_class"] for s in sources)
    assert all(s["independence_group"] for s in sources)
    assert all(s["crawl_status"] != "not attempted" for s in sources)


def test_a_login_walled_platform_is_blocked_not_described(pilot):
    db, cid = pilot["db"], pilot["result"]["report"]["community_id"]
    facebook = db.query_one(
        "SELECT * FROM sources WHERE community_id=? AND platform_type='Facebook'", (cid,))
    assert facebook["crawl_status"] == "blocked"
    assert facebook["pages_opened"] == 0
    # Nothing may be claimed from a source that was never read.
    claims = db.query("SELECT * FROM claims WHERE source_id=?", (facebook["source_id"],))
    assert claims == []


def test_a_page_linked_only_from_the_sitemap_is_reached(pilot):
    db, cid = pilot["db"], pilot["result"]["report"]["community_id"]
    orphan = db.query_one(
        "SELECT * FROM pages WHERE community_id=? AND normalized_url LIKE '%pages-orphelines%'",
        (cid,))
    assert orphan is not None


def test_archived_snapshots_are_retrieved_and_marked(pilot):
    db, cid = pilot["db"], pilot["result"]["report"]["community_id"]
    archived = db.query(
        "SELECT * FROM pages WHERE community_id=? AND archive_timestamp IS NOT NULL", (cid,))
    assert archived, "no archived snapshot was opened"
    assert all(page["archived_original"] for page in archived)


def test_documents_of_every_kind_are_parsed(pilot):
    db, cid = pilot["db"], pilot["result"]["report"]["community_id"]
    extensions = {r["extension"] for r in db.query(
        "SELECT DISTINCT extension FROM documents WHERE community_id=?", (cid,))}
    assert {"pdf", "xlsx", "docx"} <= extensions


def test_a_corrupt_document_is_stored_and_reported_not_skipped(pilot):
    db, cid = pilot["db"], pilot["result"]["report"]["community_id"]
    corrupt = db.query_one(
        "SELECT * FROM documents WHERE community_id=? AND parser_status='corrupt'", (cid,))
    assert corrupt is not None
    assert corrupt["sha256"]
    assert corrupt["storage_path"]


def test_a_mislabelled_file_is_parsed_by_its_bytes(pilot):
    db, cid = pilot["db"], pilot["result"]["report"]["community_id"]
    rows = db.query(
        "SELECT * FROM documents WHERE community_id=? AND mime_sniffed='application/pdf'", (cid,))
    assert rows


def test_images_are_kept_with_provenance_and_decoration_is_dropped(pilot):
    db, cid = pilot["db"], pilot["result"]["report"]["community_id"]
    images = db.query("SELECT * FROM images WHERE community_id=?", (cid,))
    assert images
    assert all(i["original_url"] and i["sha256"] and i["local_path"] for i in images)
    assert not any("logo" in (i["filename"] or "") for i in images)
    plans = [i for i in images if i["image_type"] == "site plan"]
    assert plans and plans[0]["relevance_class"] == "likely_relevant"


def test_a_photograph_alone_never_evidences_a_practice(pilot):
    db, cid = pilot["db"], pilot["result"]["report"]["community_id"]
    for image in db.query("SELECT * FROM images WHERE community_id=?", (cid,)):
        assert "practice" not in (image["visual_evidence_allowed"] or "").lower()
    # No claim on a practice code may cite an image as its only support.
    for row in db.query(
        "SELECT * FROM claims WHERE community_id=? AND field_name LIKE 'pc%' "
        "AND image_id IS NOT NULL", (cid,)
    ):
        assert row["exact_wording"]


# -- what the evidence layer produced ---------------------------------------
def test_every_claim_carries_its_wording_and_provenance(pilot):
    db, cid = pilot["db"], pilot["result"]["report"]["community_id"]
    claims = db.query("SELECT * FROM claims WHERE community_id=?", (cid,))
    assert claims
    for claim in claims:
        assert claim["evidence_id"]
        assert claim["extractor"]
        evidence = db.query_one("SELECT quote FROM evidence WHERE evidence_id=?",
                                (claim["evidence_id"],))
        assert evidence and evidence["quote"].strip()


def test_onset_is_dated_and_banded(pilot):
    db, cid = pilot["db"], pilot["result"]["report"]["community_id"]
    values = {r["field_name"]: r["value"] for r in db.query(
        "SELECT field_name, value FROM field_values WHERE community_id=?", (cid,))}
    assert values["date_intervention_onset"] == "2016"
    assert int(values["onset_lower_bound"]) <= 2016 <= int(values["onset_upper_bound"])
    assert values["onset_evidence_rank"] in {"1", "2", "3", "4", "5"}
    assert values["onset_proxy_flag"] == "no"


def test_managed_area_is_never_confused_with_the_whole_holding(pilot):
    db, cid = pilot["db"], pilot["result"]["report"]["community_id"]
    values = {r["field_name"]: r["value"] for r in db.query(
        "SELECT field_name, value FROM field_values WHERE community_id=?", (cid,))}
    assert float(values["total_holding_ha"]) == 55.0
    assert float(values["managed_area_ha"]) < 55.0
    assert values["area_type"] == "both recorded"


def test_a_denial_is_coded_explicitly_absent(pilot):
    db, cid = pilot["db"], pilot["result"]["report"]["community_id"]
    value = db.query_one(
        "SELECT value FROM field_values WHERE community_id=? AND field_name='pc03_irrigation'",
        (cid,))
    assert value["value"] == "explicitly absent"


def test_silence_is_recorded_as_not_mentioned(pilot):
    db, cid = pilot["db"], pilot["result"]["report"]["community_id"]
    levels = {r["field_name"]: r["value"] for r in db.query(
        "SELECT field_name, value FROM field_values WHERE community_id=? AND field_name LIKE 'pc%'",
        (cid,))}
    assert len(levels) == 13
    assert "not mentioned" in levels.values()


def test_negative_and_unreachable_consultations_are_distinguished(pilot):
    db, cid = pilot["db"], pilot["result"]["report"]["community_id"]
    results = {r["result"] for r in db.query(
        "SELECT DISTINCT result FROM searches WHERE community_id=?", (cid,))}
    assert "unreachable" in results
    note = db.query_one(
        "SELECT value FROM field_values WHERE community_id=? "
        "AND field_name='negative_consultations'", (cid,))
    assert "unreachable" in (note["value"] or "")


def test_an_academic_record_must_be_verified_to_support_a_value(pilot):
    db, cid = pilot["db"], pilot["result"]["report"]["community_id"]
    records = db.query("SELECT * FROM academic_records WHERE community_id=?", (cid,))
    assert records
    for record in records:
        assert record["verified_resolves"] in ("yes", "no")
        assert record["verification_detail"]


def test_crawl_truncation_is_explicit_with_a_reason(pilot):
    db, cid = pilot["db"], pilot["result"]["report"]["community_id"]
    row = db.query_one(
        "SELECT value, rationale FROM field_values WHERE community_id=? "
        "AND field_name='crawl_truncated'", (cid,))
    assert row["value"] in ("yes", "no")
    assert row["rationale"]


def test_stages_completed_is_generated_from_recorded_status(pilot):
    db, cid = pilot["db"], pilot["result"]["report"]["community_id"]
    value = db.query_one(
        "SELECT value FROM field_values WHERE community_id=? AND field_name='stages_completed'",
        (cid,))["value"]
    assert "complete:" in value


# -- outputs ----------------------------------------------------------------
def test_the_output_tree_is_complete(pilot):
    root = pilot["result"]["output_dir"]
    for name in ("01_raw_sources", "02_documents", "03_images", "04_archives",
                 "05_extracted_text", "06_tables", "07_evidence", "08_logs",
                 "09_final", "10_debug"):
        assert (root / name).is_dir()
    assert (root / "README_run.md").exists()


def test_the_final_folder_carries_every_manifest(pilot):
    final = pilot["result"]["output_dir"] / "09_final"
    # These always carry content.
    for name in ("completion_report.md", "completion_report.json", "run_manifest.json",
                 "source_manifest.csv", "evidence_manifest.csv", "document_manifest.csv",
                 "search_log.csv", "claims.jsonl", "field_values.csv"):
        assert (final / name).exists(), name
        assert (final / name).stat().st_size > 0, name
    # These are legitimately empty when there is nothing to report.
    for name in ("image_manifest.csv", "errors.jsonl", "review_queue.jsonl",
                 "conflicts.jsonl"):
        assert (final / name).exists(), name


def test_the_workbook_opens_and_holds_the_coded_row(pilot):
    workbook = load_workbook(pilot["result"]["workbook"])
    sheet = workbook["O1_Community_Attributes"]
    assert sheet["A3"].value.startswith("TEST-IC")
    assert sheet["B3"].value == "EcoVillage de Pourgues"
    assert isinstance(sheet["V3"].value, (int, float))     # managed area, as a number
    assert workbook["O11_Source_Set"]["A3"].value          # one row per address
    assert workbook["O7_Search_Log"]["A3"].value           # one row per database
    workbook.close()


def test_the_run_manifest_locks_the_research_document_versions(pilot):
    import json

    manifest = json.loads(
        (pilot["result"]["output_dir"] / "09_final" / "run_manifest.json").read_text())
    names = {d["filename"] for d in manifest["research_documents"]}
    assert any("Workbook_v6" in n for n in names)
    assert all(len(d["sha256"]) == 64 for d in manifest["research_documents"])
    assert manifest["register_version"] == "2.4"


def test_quality_checks_pass(pilot):
    qc = pilot["result"]["qc"]
    assert not qc.failures, [f"{r.number}: {r.detail}" for r in qc.failures]
    assert len(qc.results) == 18
    assert qc.coverage


def test_completion_status_is_one_of_the_six(pilot):
    assert pilot["result"]["status"] in {
        "COMPLETE", "COMPLETE_WITH_UNCERTAINTY", "PARTIAL_TRUNCATED",
        "PARTIAL_BLOCKED", "FAILED_TECHNICALLY", "REQUIRES_HUMAN_REVIEW",
    }


def test_a_fixture_run_is_stamped_so_it_cannot_pass_as_research_data(pilot):
    db, cid = pilot["db"], pilot["result"]["report"]["community_id"]
    row = db.query_one("SELECT provenance_mode FROM communities WHERE community_id=?", (cid,))
    assert row["provenance_mode"] == "FIXTURE"
    assert cid.startswith("TEST-")


# -- resume, re-export and crash recovery ------------------------------------
def test_export_mode_rebuilds_everything_offline(pilot):
    """The workbook must be regenerable from the database alone (brief 67)."""
    app, community = pilot["app"], pilot["community"]
    before = pilot["result"]["workbook"].stat().st_mtime
    result = app.run(community, mode="EXPORT")
    assert result["workbook"].exists()
    assert result["workbook"].stat().st_mtime >= before
    assert result["report"]["fields_coded"] == pilot["result"]["report"]["fields_coded"]


def test_an_interrupted_run_resumes_from_the_frontier(pilot):
    """Anything left mid-flight is re-queued rather than lost."""
    from dcr.crawl.frontier import Frontier

    db, cid = pilot["db"], pilot["result"]["report"]["community_id"]
    db.execute("UPDATE frontier SET status='in_flight' WHERE community_id=? AND status='done' "
               "AND rowid IN (SELECT rowid FROM frontier WHERE community_id=? LIMIT 3)",
               (cid, cid))
    frontier = Frontier(db, cid)
    assert frontier.reclaim_in_flight() == 3
    assert frontier.pending() >= 3
