"""Quality control, discovery, frontier state and resumability."""

from __future__ import annotations

import pytest

from dcr.crawl.frontier import Frontier, SourceBudget, score_url
from dcr.crawl.platform import default_source_class, detect_platform, is_website_like, profile_for
from dcr.db import utcnow
from dcr.discovery.academic import (
    AcademicRecord, build_queries, parse_response, score_relevance, titles_match,
    verification_targets,
)
from dcr.discovery.grey import classify_grey_type
from dcr.discovery.search import filetype_queries, parse_results, site_queries
from dcr.discovery.sitemap import parse_feed, parse_sitemap
from dcr.discovery.wayback import parse_archive_url, parse_cdx, select_snapshots
from dcr.ids import image_filename, safe_name
from dcr.qc.checks import QualityControl, completion_status
from dcr.storage import CommunityStorage


# -- identifiers and storage -------------------------------------------------
def test_safe_name_is_traversal_proof_and_stable():
    assert "/" not in safe_name("../../etc/passwd")
    assert ".." not in safe_name("../../etc/passwd")
    assert safe_name("EcoVillage de Pourgues") == "EcoVillage_de_Pourgues"
    assert safe_name("日本の村").startswith("unnamed_")
    assert safe_name("") == "unnamed"
    assert safe_name("CON") == "_CON"


def test_image_filename_is_traceable():
    name = image_filename(image_id="IC027-IMG0042", topic="site plan", year=2017,
                          source="IC027-S018", page_number=12, extension=".JPG")
    assert name.startswith("IC027-IMG0042")
    assert "site_plan" in name and "2017" in name and "p12" in name
    assert name.endswith(".jpg")


def test_storage_refuses_to_write_outside_its_tree(tmp_path):
    storage = CommunityStorage.create(tmp_path / "out", "IC001", "Test")
    written = storage.write_bytes(storage.documents, "../../escape.txt", b"x")
    assert written.parent == storage.documents.resolve()
    assert not (tmp_path / "escape.txt").exists()


# -- platform typing ---------------------------------------------------------
@pytest.mark.parametrize("url, platform, source_class", [
    ("https://www.facebook.com/x", "Facebook", "S7"),
    ("https://ecovillage.org/projects/x", "directory listing", "S3"),
    ("https://www.kickstarter.com/projects/x", "crowdfunding", "S3"),
    ("https://theses.fr/2019ABC", "own website", "S1"),
    ("https://cordis.europa.eu/project/id/1", "own website", "S2"),
])
def test_platform_and_class_detection(settings, url, platform, source_class):
    patterns = settings.sources["platform_patterns"]
    assert detect_platform(url, patterns) == platform
    assert default_source_class(url, detect_platform(url, patterns)) == source_class


def test_the_full_website_protocol_applies_only_to_websites():
    assert is_website_like("own website")
    assert is_website_like("secondary or former website")
    assert not is_website_like("Instagram")


def test_a_login_walled_platform_is_flagged_before_it_is_fetched(settings):
    profile = profile_for("https://instagram.com/x", "Instagram",
                          settings.sources["platform_endpoints"])
    assert profile.login_walled
    assert "feed position is never a date" in profile.notes.lower()


def test_a_former_domain_earns_the_highest_retrieval_priority(settings):
    endpoints = settings.sources["platform_endpoints"]
    former = profile_for("https://old.org/", "secondary or former website", endpoints)
    current = profile_for("https://new.org/", "own website", endpoints)
    assert former.retrieval_priority == "A"
    assert current.retrieval_priority == "B"


# -- discovery ---------------------------------------------------------------
def test_sitemap_index_and_entries():
    entries, nested = parse_sitemap(
        '<sitemapindex><sitemap><loc>https://x.org/p.xml</loc></sitemap></sitemapindex>',
        "https://x.org/sitemap.xml")
    assert nested == ["https://x.org/p.xml"] and entries == []

    entries, _ = parse_sitemap(
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        '<url><loc>https://x.org/a</loc><lastmod>2019-03-01</lastmod></url>'
        '<url><loc>https://x.org/r.pdf</loc></url></urlset>',
        "https://x.org/sitemap.xml")
    kinds = {e.url: e.kind for e in entries}
    assert kinds["https://x.org/a"] == "page"
    assert kinds["https://x.org/r.pdf"] == "document"


def test_feed_dates_are_publication_dates():
    entries = parse_feed(
        "<rss><channel><item><title>T</title><link>https://x.org/p</link>"
        "<pubDate>Tue, 22 Mar 2016 09:00:00 +0000</pubDate></item></channel></rss>",
        "https://x.org")
    assert entries[0].published == "2016-03-22"


def test_cdx_parsing_and_snapshot_selection():
    import json

    rows = [["original", "timestamp", "mimetype", "statuscode", "digest"],
            ["http://x.org/", "20110412000000", "text/html", "200", "A"],
            ["http://x.org/", "20150412000000", "text/html", "200", "B"],
            ["http://x.org/docs/r.pdf", "20140101000000", "application/pdf", "200", "D"]]
    result = parse_cdx(json.dumps(rows))
    assert result.ok and len(result.entries) == 3

    chosen = select_snapshots(result.entries, priority_paths=["/"], max_total=10)
    assert chosen[0].kind == "document"          # a deleted PDF wins
    assert any(s.timestamp.startswith("2011") for s in chosen)   # the earliest is kept


def test_an_empty_archive_is_not_an_error():
    assert parse_cdx("").status == "empty"
    assert parse_cdx("").ok


def test_a_malformed_archive_response_is_an_error_not_zero_results():
    result = parse_cdx("[not json")
    assert not result.ok and result.status == "error"


def test_archive_url_round_trip():
    assert parse_archive_url(
        "https://web.archive.org/web/20160901000000id_/http://x.org/a") == (
        "20160901000000", "http://x.org/a")
    assert parse_archive_url("https://x.org/a") is None


def test_academic_queries_cover_every_route():
    queries = build_queries(
        names=["Tamera", "Tamera Heilungsbiotop"], locality="Colos", region="Alentejo",
        country="Portugal", founders=["Sabine Lichtenfels"], networks=["GEN Europe"],
        terms_by_language={"pt": ["ecoaldeia"], "en": ["ecovillage", "permaculture"]},
        languages=["pt", "en"])
    text = " | ".join(q for q, _ in queries)
    assert '"Tamera"' in text
    assert "ecoaldeia" in text and "ecovillage" in text
    assert "Colos" in text and "Alentejo" in text
    assert "Sabine Lichtenfels" in text and "GEN Europe" in text


def test_relevance_needs_the_name_or_a_topic_term():
    record = AcademicRecord(title="A study of soil carbon in Bavaria", database_id="openalex")
    assert score_relevance(record, names=["Tamera"], locality=None, region=None,
                           country="Portugal")[0] == 0.0


def test_verification_never_constructs_an_identifier():
    record = AcademicRecord(title="T", database_id="openalex")
    assert verification_targets(record) == []
    record.doi = "10.1/x"
    assert any(kind == "doi" for kind, _ in verification_targets(record))


def test_titles_match_tolerates_case_and_punctuation():
    assert titles_match("Agroecological transition at Pourgues",
                        "AGROECOLOGICAL TRANSITION AT POURGUES.")
    assert not titles_match("Soil carbon in Bavaria", "Water use in Andalusia")


def test_grey_types_are_named_from_the_record():
    assert classify_grey_type("LIFE programme grant award 2014") == "grant record"
    assert classify_grey_type("Master thesis on agroecology") == "thesis"
    assert classify_grey_type("Omgevingsvergunning gemeente") == "planning permit"


def test_filetype_and_site_queries():
    assert '"X" filetype:pdf' in filetype_queries("X", ["pdf"])
    assert "site:x.org 2012" in site_queries("x.org", years=[2012])


def test_search_result_redirects_are_unwrapped():
    hits = parse_results("duckduckgo_html",
                         '<a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fx.org%2Fa">Titre</a>')
    assert hits[0].url == "https://x.org/a"


# -- frontier and budget -----------------------------------------------------
def test_priority_prefers_history_documents_and_old_material():
    history = score_url("https://x.org/histoire", depth=1, kind="page")
    generic = score_url("https://x.org/contact", depth=1, kind="page")
    document = score_url("https://x.org/r.pdf", depth=1, kind="document")
    old = score_url("https://x.org/2011/03/post", depth=1, kind="page")
    recent = score_url("https://x.org/2022/03/post", depth=1, kind="page")
    assert history > generic
    assert document > generic
    assert old > recent


def test_a_guessed_path_never_outranks_a_published_url():
    guessed = score_url("https://x.org/about", depth=1, kind="page",
                        discovery_method="path_probe")
    published = score_url("https://x.org/about", depth=1, kind="page",
                          discovery_method="sitemap")
    assert published > guessed


def test_frontier_deduplicates_and_survives_restart(db, community):
    frontier = Frontier(db, community)
    assert frontier.add("https://x.org/a", discovery_method="seed")
    assert frontier.add("https://x.org/a/", discovery_method="seed") is None
    assert frontier.pending() == 1

    batch = frontier.next_batch(1)
    assert frontier.pending() == 0                     # in flight

    reopened = Frontier(db, community)
    assert reopened.reclaim_in_flight() == 1
    assert reopened.pending() == 1
    reopened.complete(batch[0].url_key, "done")
    assert reopened.pending() == 0


def test_failed_urls_can_be_requeued(db, community):
    frontier = Frontier(db, community)
    frontier.add("https://x.org/a", discovery_method="seed")
    item = frontier.next_batch(1)[0]
    frontier.complete(item.url_key, "failed", "timeout")
    assert frontier.pending() == 0
    assert frontier.requeue_failed() == 1
    assert frontier.pending() == 1


def test_a_budget_grows_while_a_source_pays_and_stops_when_it_does_not():
    budget = SourceBudget("S1", base=3, maximum=9, yield_window=3, yield_threshold=0.3,
                          increment=3, exhaustion_window=4)
    for _ in range(3):
        budget.record(yielded_evidence=True, new_urls=2)
    assert budget.limit > 3 and not budget.exhausted
    for _ in range(4):
        budget.record(yielded_evidence=False, new_urls=0)
    assert budget.exhausted


def test_speculative_probe_failures_do_not_exhaust_a_source():
    """Forty well-known paths mostly 404; that is the protocol, not exhaustion."""
    budget = SourceBudget("S1", base=40, maximum=80, exhaustion_window=5)
    for _ in range(40):
        budget.record_failure()
    assert not budget.exhausted


def test_a_source_where_nothing_responds_is_eventually_declared_dead():
    budget = SourceBudget("S1", base=40, maximum=80, exhaustion_window=5)
    for _ in range(200):
        budget.record_failure()
    assert budget.exhausted
    assert "dead" in budget.exhausted_reason


# -- quality control ---------------------------------------------------------
def _seed_minimal(db, community):
    now = utcnow()
    db.insert("sources", {
        "source_id": f"{community}-S001", "community_id": community,
        "address_id": f"{community}-01", "url": "https://x.org/",
        "registrable_domain": "x.org", "platform_type": "own website", "source_class": "S4",
        "supplied_or_discovered": "supplied", "independence_group": "G1",
        "crawl_status": "crawled", "access_status": "ok", "pages_opened": 5,
        "first_discovered_utc": now,
    })
    db.insert("searches", {
        "search_id": "Q1", "community_id": community, "database_name": "OpenAlex",
        "database_type": "academic", "query": "x", "language": "en", "hits_returned": 0,
        "result": "none found", "searched_utc": now, "stage": 5,
    })
    db.insert("discovery_log", {
        "discovery_id": "D1", "community_id": community, "method": "search",
        "outcome": "duplicate", "ts_utc": now,
    })
    db.upsert("field_values", {
        "community_id": community, "field_name": "crawl_truncated", "value": "no",
        "status": "coded", "method": "run_state", "rationale": "all stages complete",
        "updated_utc": now,
    }, ["community_id", "field_name"])
    db.upsert("field_values", {
        "community_id": community, "field_name": "negative_consultations",
        "value": "none found: OpenAlex", "status": "coded", "method": "search_log",
        "updated_utc": now,
    }, ["community_id", "field_name"])


def test_quality_control_runs_all_eighteen_checks(db, community, schema, tmp_path):
    _seed_minimal(db, community)
    report = QualityControl(db, community, schema, storage_root=tmp_path).run()
    assert len(report.results) == 18
    assert {r.number for r in report.results} == set(range(1, 19))
    assert all(r.detail for r in report.results)


def test_a_supplied_address_left_unattempted_fails_check_one(db, community, schema, tmp_path):
    _seed_minimal(db, community)
    db.update("sources", {"crawl_status": "not attempted", "access_status": "not_attempted"},
              {"source_id": f"{community}-S001"})
    report = QualityControl(db, community, schema, storage_root=tmp_path).run()
    assert any(r.number == 1 and r.verdict == "fail" for r in report.results)


def test_a_source_without_an_independence_group_fails_check_four(db, community, schema, tmp_path):
    _seed_minimal(db, community)
    db.update("sources", {"independence_group": None}, {"source_id": f"{community}-S001"})
    report = QualityControl(db, community, schema, storage_root=tmp_path).run()
    assert any(r.number == 4 and r.verdict == "fail" for r in report.results)


def test_an_unlogged_academic_search_fails_check_seven(db, community, schema, tmp_path):
    _seed_minimal(db, community)
    db.execute("DELETE FROM searches WHERE community_id=?", (community,))
    report = QualityControl(db, community, schema, storage_root=tmp_path).run()
    assert any(r.number == 7 and r.verdict == "fail" for r in report.results)


def test_a_missing_truncation_flag_fails_check_twelve(db, community, schema, tmp_path):
    _seed_minimal(db, community)
    db.execute("DELETE FROM field_values WHERE field_name='crawl_truncated'")
    report = QualityControl(db, community, schema, storage_root=tmp_path).run()
    assert any(r.number == 12 and r.verdict == "fail" for r in report.results)


def test_a_value_outside_its_vocabulary_fails_check_fourteen(db, community, schema, tmp_path):
    _seed_minimal(db, community)
    db.upsert("field_values", {
        "community_id": community, "field_name": "e5_active_currently", "value": "perhaps",
        "status": "coded", "method": "rule", "updated_utc": utcnow(),
    }, ["community_id", "field_name"])
    report = QualityControl(db, community, schema, storage_root=tmp_path).run()
    assert any(r.number == 14 and r.verdict == "fail" for r in report.results)


def test_the_coverage_matrix_reports_every_source_class(db, community, schema, tmp_path):
    _seed_minimal(db, community)
    coverage = QualityControl(db, community, schema, storage_root=tmp_path).coverage_matrix()
    assert {row["source_class"] for row in coverage} == set(schema["source_classes"])
    assert all(set(row) >= {"searched", "found", "opened", "evidence_yielded",
                            "failed_or_blocked"} for row in coverage)


@pytest.mark.parametrize("truncated, blocking, pages, expected", [
    (False, 0, 40, "COMPLETE"),
    (True, 0, 40, "COMPLETE_WITH_TRUNCATION"),
    (False, 2, 40, "REQUIRES_HUMAN_REVIEW"),
    (False, 0, 3, "COMPLETE_WITH_TRUNCATION"),
])
def test_completion_status_never_calls_a_partial_crawl_complete(truncated, blocking, pages,
                                                                expected):
    from dcr.qc.checks import QcReport

    assert completion_status(QcReport(), truncated=truncated, blocking_review=blocking,
                             pages_opened=pages, min_pages=25) == expected


def test_only_the_six_statuses_the_brief_names_are_ever_produced():
    """§92 lists six. `PARTIAL_TRUNCATED`, which this used to produce, is not
    one of them, and a status nobody defined is a status nobody can act on."""
    from dcr.qc.checks import COMPLETION_STATUSES, QcReport

    produced = set()
    for truncated in (True, False):
        for blocking in (0, 2):
            for pages in (3, 40):
                for cause in ("", "exhausted", "ceiling", "requested"):
                    for blocked, reachable in ((0, 3), (3, 0), (1, 4)):
                        produced.add(completion_status(
                            QcReport(), truncated=truncated, blocking_review=blocking,
                            pages_opened=pages, min_pages=25,
                            retrieval_stop_cause=cause,
                            blocked_sources=blocked, reachable_sources=reachable))
    produced.add(completion_status(QcReport(), truncated=False, blocking_review=0,
                                   pages_opened=40, min_pages=25,
                                   workbook_verified=False))
    assert produced <= set(COMPLETION_STATUSES), produced - set(COMPLETION_STATUSES)


def test_a_community_that_was_worked_out_is_complete_not_truncated():
    """The change the yield governor brings: a run that stopped because every
    source went quiet followed the protocol to its end (brief §61)."""
    from dcr.qc.checks import QcReport

    assert completion_status(QcReport(), truncated=True, blocking_review=0,
                             pages_opened=400, min_pages=25,
                             retrieval_stop_cause="exhausted") == "COMPLETE"


def test_a_ceiling_or_a_request_leaves_work_undone():
    from dcr.qc.checks import QcReport

    for cause in ("ceiling", "requested"):
        assert completion_status(QcReport(), truncated=False, blocking_review=0,
                                 pages_opened=400, min_pages=25,
                                 retrieval_stop_cause=cause) == "COMPLETE_WITH_TRUNCATION"


def test_refused_access_is_not_the_same_as_nothing_published():
    """§60: BLOCKED says the evidence exists and could not be reached."""
    from dcr.qc.checks import QcReport

    assert completion_status(
        QcReport(), truncated=True, blocking_review=0, pages_opened=40, min_pages=25,
        blocked_sources=3, reachable_sources=0) == "PARTIAL_BLOCKED"


def test_one_login_walled_page_does_not_make_a_community_blocked():
    """A Facebook page behind a login beside a fully crawled website is an
    ordinary result, not a blocked community."""
    from dcr.qc.checks import QcReport

    assert completion_status(
        QcReport(), truncated=False, blocking_review=0, pages_opened=200, min_pages=25,
        retrieval_stop_cause="exhausted",
        blocked_sources=1, reachable_sources=4) == "COMPLETE"


def test_an_unreachable_third_party_index_is_not_a_blocked_community():
    """An academic database being down is an infrastructure gap, not a refusal
    by this community, and must not change its status."""
    from dcr.qc.checks import QcReport

    assert completion_status(
        QcReport(), truncated=True, blocking_review=0, pages_opened=200, min_pages=25,
        retrieval_stop_cause="exhausted",
        blocked_sources=0, reachable_sources=4) == "COMPLETE"


def test_a_critical_check_failure_is_technical_failure():
    from dcr.qc.checks import CheckResult, QcReport

    report = QcReport(results=[CheckResult(17, "workbook opens", "fail", "it does not")])
    assert completion_status(report, truncated=False, blocking_review=0, pages_opened=40,
                             min_pages=25) == "FAILED_TECHNICALLY"
