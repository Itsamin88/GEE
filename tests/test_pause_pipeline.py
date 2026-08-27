"""Pausing and resuming a real crawl, end to end against the fixture web.

The supervisor tests prove the state machine. These prove the thing the brief
actually asks for (§38.9, §38.10, §53): that a crawl stopped half way through
and started again later produces one set of evidence rather than two, loses
nothing from its queue, and is never recorded as having finished.

The crawler, extractors, evidence model, exporter and quality checks here are
the production ones. Only the endpoints point at the fixture.
"""

from __future__ import annotations

import shutil
import socket
import sys
from pathlib import Path

import pytest

from dcr.app import Application
from dcr.control import (PAUSED_MANUAL, PAUSED_NETWORK, find_interrupted_runs,
                         clear_requests, request_pause, request_resume)
from dcr.db import Database
from dcr.runner import CommunityInput, CommunityRunner
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


PAUSE_AFTER_PAGES = 3


def _settings(port: int, output: Path):
    settings = fixture_settings(port, output, root=ROOT)
    # `exit` so the pause returns control to the test instead of waiting for a
    # researcher who is not there. The waiting behaviour is covered in
    # test_control.py.
    settings.app["run_control"] = {
        "poll_interval_s": 0.0,
        "manual_pause_behavior": "exit",
        "resume_poll_interval_s": 0.0,
        "failures_before_probe": 3,
    }
    settings.app["estimation"] = dict(settings.app.get("estimation", {}))
    settings.app["estimation"]["enabled"] = False
    return settings


class _PausingRunner(CommunityRunner):
    """A runner that presses PAUSE for the researcher, part way through.

    The pause request is written from inside `_on_page`, so it lands while the
    crawl is genuinely mid-flight; the supervisor then acts on it at the next
    safe boundary, exactly as it would for a real button press.
    """

    pages_before_pause = PAUSE_AFTER_PAGES

    def _on_page(self, page_id, parsed, context):
        found = super()._on_page(page_id, parsed, context)
        self._pages_seen = getattr(self, "_pages_seen", 0) + 1
        if self._pages_seen == self.pages_before_pause:
            request_pause(self.settings.output_root, "researcher pressed PAUSE mid-crawl")
        return found


@pytest.fixture(scope="module")
def paused_then_resumed(tmp_path_factory):
    """Crawl, pause mid-flight, then resume in a fresh Application."""
    output = tmp_path_factory.mktemp("pause_pipeline")
    server = FixtureServer().start()
    try:
        settings = _settings(server.port, output)
        clear_requests(settings.output_root)
        community = CommunityInput(
            name="EcoVillage de Pourgues", latitude=43.0561, longitude=1.8342,
            urls=fixture_urls(server.port, "pourgues"), country="France",
            coder_id="TEST", fixture=True,
        )

        # -- first attempt: interrupted by the researcher ------------------
        app = Application(settings)
        app.preflight()
        import dcr.app as app_module
        original = app_module.CommunityRunner
        app_module.CommunityRunner = _PausingRunner
        try:
            first = app.run(community, mode="FULL")
        finally:
            app_module.CommunityRunner = original
        db = Database(settings.database_path)
        paused_snapshot = _snapshot(db, first["report"]["community_id"])
        interrupted = find_interrupted_runs(db)
        db.close()
        app.close()

        # -- the researcher comes back, in a new process ------------------
        clear_requests(settings.output_root)
        resumed_app = Application(_settings(server.port, output))
        resumed_app.preflight()
        second = resumed_app.run(community, mode="RESUME")
        db = Database(settings.database_path)
        resumed_snapshot = _snapshot(db, second["report"]["community_id"])
        yield {
            "first": first, "second": second,
            "paused": paused_snapshot, "resumed": resumed_snapshot,
            "interrupted": interrupted, "db": db, "settings": settings,
            "output": output,
        }
        db.close()
        resumed_app.close()
    finally:
        server.stop()


def _snapshot(db: Database, community_id: str) -> dict:
    """Everything a duplicate would show up in."""
    def rows(sql, *params):
        return db.query(sql, params or (community_id,))

    return {
        "community_id": community_id,
        "runs": rows("SELECT run_id, status, final_state, truncated FROM runs "
                     "WHERE community_id=? ORDER BY started_utc"),
        "evidence": rows("SELECT evidence_id, quote, source_id, locator FROM evidence "
                         "WHERE community_id=?"),
        "claims": rows("SELECT claim_id, field_name, value, evidence_id FROM claims "
                       "WHERE community_id=?"),
        "images": rows("SELECT image_id, sha256, original_url, local_path FROM images "
                       "WHERE community_id=?"),
        "candidates": rows("SELECT candidate_id, url_key, decision FROM image_candidates "
                           "WHERE community_id=?"),
        "documents": rows("SELECT document_id, sha256 FROM documents WHERE community_id=?"),
        "pages": rows("SELECT page_id, normalized_url FROM pages WHERE community_id=?"),
        "frontier": rows("SELECT url_key, status FROM frontier WHERE community_id=?"),
        "sources": rows("SELECT source_id, url FROM sources WHERE community_id=?"),
    }


# ---------------------------------------------------------------------------
# the pause itself
# ---------------------------------------------------------------------------
def test_the_interrupted_run_is_recorded_as_paused_not_complete(paused_then_resumed):
    """The single most important assertion in this file (brief §13)."""
    first_run = paused_then_resumed["paused"]["runs"][0]
    assert first_run["status"] == "paused_manual"
    assert first_run["final_state"] == PAUSED_MANUAL
    assert first_run["status"] != "complete"


def test_the_paused_run_is_marked_truncated(paused_then_resumed):
    assert paused_then_resumed["paused"]["runs"][0]["truncated"] == 1


def test_the_paused_run_is_offered_for_resume_afterwards(paused_then_resumed):
    interrupted = paused_then_resumed["interrupted"]
    assert interrupted, "a paused run must be findable after the process ends"
    assert interrupted[0].state == PAUSED_MANUAL
    assert interrupted[0].was_manual
    assert "PAUSE" in interrupted[0].pause_reason or interrupted[0].pause_reason


def test_the_pause_left_work_still_in_the_queue(paused_then_resumed):
    """A pause part way through must leave something to come back to."""
    statuses = [row["status"] for row in paused_then_resumed["paused"]["frontier"]]
    assert statuses, "the frontier must not be empty after a mid-crawl pause"
    assert any(status in ("queued", "in_flight") for status in statuses), (
        "the pause happened after the crawl had already drained the queue; "
        "increase the fixture size or lower PAUSE_AFTER_PAGES")


def test_stages_after_the_pause_are_recorded_as_never_begun(paused_then_resumed):
    db = paused_then_resumed["db"]
    run_id = paused_then_resumed["paused"]["runs"][0]["run_id"]
    stages = db.query("SELECT stage_no, status, detail FROM run_stages WHERE run_id=?",
                      (run_id,))
    unreached = [s for s in stages if s["status"] == "not_reached"]
    for stage in unreached:
        assert "never begun" in (stage["detail"] or ""), (
            "an unreached stage must say it was never begun, not imply it found nothing")


# ---------------------------------------------------------------------------
# the resume
# ---------------------------------------------------------------------------
def test_the_resumed_run_completes(paused_then_resumed):
    runs = paused_then_resumed["resumed"]["runs"]
    assert len(runs) >= 2, "the resume must be a run of its own"
    assert runs[-1]["status"] == "complete"
    assert runs[-1]["final_state"] == "COMPLETED"


def test_the_resume_carried_on_rather_than_starting_again(paused_then_resumed):
    """Work done before the pause is kept, not thrown away and redone."""
    before = paused_then_resumed["paused"]
    after = paused_then_resumed["resumed"]
    assert len(after["pages"]) >= len(before["pages"])
    assert len(after["sources"]) >= len(before["sources"])
    # Every page opened before the pause is still there afterwards.
    before_urls = {row["normalized_url"] for row in before["pages"]}
    after_urls = {row["normalized_url"] for row in after["pages"]}
    assert before_urls <= after_urls


def test_the_queue_was_drained_by_the_resume(paused_then_resumed):
    left = [row for row in paused_then_resumed["resumed"]["frontier"]
            if row["status"] in ("queued", "in_flight")]
    assert not left, f"{len(left)} task(s) were never picked back up"


def test_nothing_is_left_in_flight_after_a_resume(paused_then_resumed):
    """`in_flight` must never be mistaken for done (brief §25)."""
    in_flight = [r for r in paused_then_resumed["resumed"]["frontier"]
                 if r["status"] == "in_flight"]
    assert in_flight == []


# ---------------------------------------------------------------------------
# §27 — no duplicate evidence after a resume
# ---------------------------------------------------------------------------
def test_no_duplicate_evidence_rows(paused_then_resumed):
    evidence = paused_then_resumed["resumed"]["evidence"]
    keys = [(row["source_id"], row["locator"], row["quote"]) for row in evidence]
    duplicates = {key for key in keys if keys.count(key) > 1}
    assert not duplicates, f"{len(duplicates)} quote(s) recorded twice after the resume"


def test_no_duplicate_claims(paused_then_resumed):
    claims = paused_then_resumed["resumed"]["claims"]
    keys = [(row["field_name"], row["value"], row["evidence_id"]) for row in claims]
    duplicates = {key for key in keys if keys.count(key) > 1}
    assert not duplicates, f"{len(duplicates)} claim(s) recorded twice"


def test_no_duplicate_pages_documents_or_images(paused_then_resumed):
    snapshot = paused_then_resumed["resumed"]
    urls = [row["normalized_url"] for row in snapshot["pages"]]
    assert len(urls) == len(set(urls)), "a page was stored twice"
    hashes = [row["sha256"] for row in snapshot["documents"]]
    assert len(hashes) == len(set(hashes)), "a document was stored twice"
    image_hashes = [row["sha256"] for row in snapshot["images"]]
    assert len(image_hashes) == len(set(image_hashes)), "an image was stored twice"


def test_no_image_is_downloaded_twice_after_the_resume(paused_then_resumed):
    candidates = paused_then_resumed["resumed"]["candidates"]
    downloaded = [row["url_key"] for row in candidates if row["decision"] == "downloaded"]
    assert len(downloaded) == len(set(downloaded)), (
        "the same image address was downloaded more than once")


def test_every_saved_image_file_exists_exactly_once(paused_then_resumed):
    snapshot = paused_then_resumed["resumed"]
    paths = [row["local_path"] for row in snapshot["images"] if row["local_path"]]
    assert len(paths) == len(set(paths))


# ---------------------------------------------------------------------------
# the finished account of what happened
# ---------------------------------------------------------------------------
def test_the_completion_report_records_the_interruption(paused_then_resumed):
    report = paused_then_resumed["second"]["report"]
    interruptions = report.get("interruptions")
    assert interruptions is not None, "the report must account for interruptions"
    assert interruptions["pauses_manual"] >= 1
    assert interruptions["events"], "the pause events belong in the report"


def test_the_workbook_is_produced_after_a_resume(paused_then_resumed):
    workbook = paused_then_resumed["second"]["workbook"]
    assert Path(workbook).exists()
    assert Path(workbook).stat().st_size > 0
