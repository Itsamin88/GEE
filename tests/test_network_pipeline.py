"""Losing the internet during a real crawl, and getting it back.

Brief §39, at the level that matters: not a mocked supervisor but the whole
pipeline, with the fixture web genuinely switched off underneath it. Every
request really fails, exactly as it would on a laptop whose wifi dropped.

What is being defended: pages that were never reached must not be recorded as
pages that hold nothing, and a run cut short must not be filed as finished.
"""

from __future__ import annotations

import socket
import threading
from pathlib import Path

import pytest

from dcr.app import Application
from dcr.control import PAUSED_NETWORK, clear_requests, find_interrupted_runs
from dcr.db import Database
from dcr.net.connectivity import ConnectivityMonitor
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

CUT_AFTER_PAGES = 2


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _settings(port: int, output: Path, **run_control):
    settings = fixture_settings(port, output, root=ROOT)
    settings.app["run_control"] = {
        "poll_interval_s": 0.0,
        "manual_pause_behavior": "exit",
        "resume_poll_interval_s": 0.0,
        "offline_wait_interval_s": 0.0,
        "failures_before_probe": 2,
        **run_control,
    }
    settings.app["estimation"] = {"enabled": False}
    # The outage must show up as connection failures quickly.
    settings.app["retry"]["max_attempts"] = 1
    settings.app["retry"]["backoff_base_s"] = 0.01
    settings.app["network"]["timeout_connect_s"] = 2
    settings.app["network"]["timeout_read_s"] = 2
    return settings


def _cutting_runner(server: FixtureServer, after: int = CUT_AFTER_PAGES):
    """A runner that pulls the plug on the fixture web part way through."""

    class CuttingRunner(CommunityRunner):
        def _on_page(self, page_id, parsed, context):
            found = super()._on_page(page_id, parsed, context)
            self._seen = getattr(self, "_seen", 0) + 1
            if self._seen == after:
                server.stop()
            return found

    return CuttingRunner


def _offline_monitor() -> ConnectivityMonitor:
    async def always_offline(_url: str) -> bool:
        return False

    return ConnectivityMonitor(probes=("https://a.example/", "https://b.example/"),
                               prober=always_offline, check_interval_s=0.0,
                               offline_retry_s=0.0, offline_retry_max_s=0.0)


def _run_with(app_settings, community, monitor, runner_class, mode="FULL"):
    import dcr.app as app_module

    app = Application(app_settings, monitor=monitor)
    app.preflight()
    original = app_module.CommunityRunner
    if runner_class is not None:
        app_module.CommunityRunner = runner_class
    try:
        return app.run(community, mode=mode), app
    finally:
        app_module.CommunityRunner = original


# ---------------------------------------------------------------------------
# the outage
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def outage(tmp_path_factory):
    """Crawl until the network dies, then resume once it is back."""
    output = tmp_path_factory.mktemp("network_pipeline")
    port = _free_port()
    server = FixtureServer(port=port).start()
    settings = _settings(port, output, max_offline_wait_s=0.05)
    clear_requests(settings.output_root)
    community = CommunityInput(
        name="EcoVillage de Pourgues", latitude=43.0561, longitude=1.8342,
        urls=fixture_urls(port, "pourgues"), country="France",
        coder_id="TEST", fixture=True,
    )

    first, app = _run_with(settings, community, _offline_monitor(),
                           _cutting_runner(server))
    db = Database(settings.database_path)
    cut = _snapshot(db, first["report"]["community_id"])
    interrupted = find_interrupted_runs(db)
    db.close()
    app.close()

    # The wifi comes back, and the researcher resumes.
    server = FixtureServer(port=port).start()
    try:
        online = ConnectivityMonitor(probes=("https://a.example/",),
                                     prober=_always_online, check_interval_s=0.0)
        second, resumed_app = _run_with(_settings(port, output), community, online,
                                        None, mode="RESUME")
        db = Database(settings.database_path)
        after = _snapshot(db, second["report"]["community_id"])
        yield {"cut": cut, "after": after, "first": first, "second": second,
               "interrupted": interrupted, "db": db}
        db.close()
        resumed_app.close()
    finally:
        server.stop()


async def _always_online(_url: str) -> bool:
    return True


def _snapshot(db: Database, community_id: str) -> dict:
    def rows(sql):
        return db.query(sql, (community_id,))

    return {
        "community_id": community_id,
        "runs": rows("SELECT run_id, status, final_state, truncated FROM runs "
                     "WHERE community_id=? ORDER BY started_utc"),
        "stages": rows("SELECT stage_no, status, detail FROM run_stages WHERE run_id IN "
                       "(SELECT run_id FROM runs WHERE community_id=?)"),
        "fields": rows("SELECT field_name, value, status FROM field_values "
                       "WHERE community_id=?"),
        "frontier": rows("SELECT url_key, status FROM frontier WHERE community_id=?"),
        "sources": rows("SELECT source_id, crawl_status, access_status FROM sources "
                        "WHERE community_id=?"),
        "evidence": rows("SELECT evidence_id, source_id, locator, quote FROM evidence "
                         "WHERE community_id=?"),
        "pages": rows("SELECT normalized_url FROM pages WHERE community_id=?"),
        "events": rows("SELECT event, kind FROM pause_events WHERE community_id=?"),
    }


# ---------------------------------------------------------------------------
# §13 — an outage is never an absence of evidence
# ---------------------------------------------------------------------------
def test_the_run_is_recorded_as_network_paused_not_complete(outage):
    run = outage["cut"]["runs"][0]
    assert run["status"] == "paused_network"
    assert run["final_state"] == PAUSED_NETWORK
    assert run["status"] != "complete"


def test_the_outage_is_recorded_as_a_connectivity_loss(outage):
    events = {(e["event"], e["kind"]) for e in outage["cut"]["events"]}
    assert ("connectivity_lost", "network") in events
    assert ("paused", "network") in events


def test_stages_never_reached_say_so_rather_than_reading_as_empty(outage):
    unreached = [s for s in outage["cut"]["stages"] if s["status"] == "not_reached"]
    assert unreached, "the outage happened too late to leave any stage unreached"
    for stage in unreached:
        assert "never begun" in (stage["detail"] or "")
        assert PAUSED_NETWORK in (stage["detail"] or "")


def test_the_queue_is_preserved_across_the_outage(outage):
    statuses = [row["status"] for row in outage["cut"]["frontier"]]
    assert any(s in ("queued", "in_flight") for s in statuses), (
        "work that was never reached must still be queued after an outage")


def test_the_paused_run_can_be_found_again_afterwards(outage):
    assert outage["interrupted"]
    assert outage["interrupted"][0].state == PAUSED_NETWORK
    assert not outage["interrupted"][0].was_manual


def test_no_field_was_coded_not_found_because_of_the_outage(outage):
    """The heart of §13.

    A field may legitimately be NOT FOUND — the sources really are silent. What
    must never happen is a NOT FOUND produced by a run that stopped before it
    could look. A network-paused run is truncated, and the report says so, so
    nothing here may be read as a finished negative result.
    """
    run = outage["cut"]["runs"][0]
    assert run["truncated"] == 1, (
        "a run cut short by an outage must be marked truncated, or its NOT FOUND "
        "values would be indistinguishable from searched-and-absent")


# ---------------------------------------------------------------------------
# §16 — coming back
# ---------------------------------------------------------------------------
def test_the_resumed_run_completes_once_the_network_is_back(outage):
    assert outage["after"]["runs"][-1]["status"] == "complete"
    assert outage["after"]["runs"][-1]["final_state"] == "COMPLETED"


def test_the_resume_reaches_more_than_the_outage_allowed(outage):
    assert len(outage["after"]["pages"]) > len(outage["cut"]["pages"])
    assert len(outage["after"]["evidence"]) >= len(outage["cut"]["evidence"])


def test_hosts_condemned_during_the_outage_are_crawled_again(outage):
    """A host that 'failed' with no network was never really tested (§16.6)."""
    unreachable = [s for s in outage["after"]["sources"]
                   if (s["access_status"] or "") == "unreachable"]
    crawled = [s for s in outage["after"]["sources"]
               if (s["crawl_status"] or "") in ("crawled", "partial", "complete")]
    assert crawled, "no source was crawled after the network came back"
    assert len(unreachable) < len(outage["after"]["sources"]), (
        "every source is still marked unreachable; the outage was recorded as a "
        "property of the sites rather than of the machine")


def test_the_outage_left_no_duplicate_evidence(outage):
    evidence = outage["after"]["evidence"]
    keys = [(row["source_id"], row["locator"], row["quote"]) for row in evidence]
    duplicates = {key for key in keys if keys.count(key) > 1}
    assert not duplicates


def test_the_final_report_accounts_for_the_outage(outage):
    interruptions = outage["second"]["report"]["interruptions"]
    assert interruptions["pauses_network"] >= 1
    assert interruptions["connectivity_losses"] >= 1
