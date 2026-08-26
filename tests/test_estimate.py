"""Runtime estimation: how long, and why that changed.

Brief §30-§35. The estimate is a band, not a promise; active processing time
and wall-clock duration are reported separately because they are different
quantities; and the figure is built from countable work rather than a
hard-coded duration.
"""

from __future__ import annotations

import asyncio

import pytest

from dcr.db import utcnow
from dcr.estimate import DiscoveryProbe, Estimate, Estimator, Workload
from dcr.runner import CommunityInput


@pytest.fixture()
def estimator(settings, db):
    return Estimator(settings, db)


def community(**kwargs) -> CommunityInput:
    kwargs.setdefault("name", "Test Community")
    return CommunityInput(**kwargs)


# ---------------------------------------------------------------------------
# §31 — the initial estimate comes from observable factors
# ---------------------------------------------------------------------------
def test_more_addresses_means_more_work(estimator):
    one = estimator.initial(community(urls=["https://a.example/"]))
    three = estimator.initial(community(urls=["https://a.example/",
                                              "https://b.example/",
                                              "https://c.example/"]))
    assert three.active_low_s > one.active_low_s
    assert three.workload.sources == 3
    assert three.workload.domains == 3


def test_the_estimate_is_not_a_hard_coded_duration(estimator):
    """Change the workload and the number must move (brief §31)."""
    small = estimator.initial(community(urls=["https://a.example/"]))
    large = estimator.initial(community(urls=[f"https://s{i}.example/" for i in range(8)]))
    assert large.active_high_s > small.active_high_s * 2


def test_a_run_with_no_addresses_says_why_it_is_uncertain(estimator):
    estimate = estimator.initial(community(urls=[]))
    assert estimate.workload.search_queries > 0
    assert any("discover them first" in note for note in estimate.workload.notes)


def test_a_missing_country_is_flagged_as_a_cost(estimator):
    estimate = estimator.initial(community(urls=["https://a.example/"]))
    assert any("no country supplied" in note for note in estimate.workload.notes)


def test_a_lighter_mode_estimates_less_work(estimator):
    full = estimator.initial(community(urls=["https://a.example/"]), mode="FULL")
    academic = estimator.initial(community(urls=["https://a.example/"]), mode="ACADEMIC")
    assert academic.active_low_s < full.active_low_s
    assert academic.workload.pages == 0        # ACADEMIC does not crawl pages


# ---------------------------------------------------------------------------
# §33 — active time and wall-clock time are different quantities
# ---------------------------------------------------------------------------
def test_wall_clock_is_reported_separately_and_is_never_shorter(estimator):
    estimate = estimator.initial(community(urls=["https://a.example/"]))
    assert estimate.wall_low_s >= estimate.active_low_s
    assert estimate.wall_high_s >= estimate.active_high_s
    lines = estimate.lines()
    assert any("active processing time" in line for line in lines)
    assert any("wall-clock duration" in line for line in lines)


def test_the_estimate_is_a_band_not_a_single_number(estimator):
    estimate = estimator.initial(community(urls=["https://a.example/"]))
    assert estimate.active_high_s > estimate.active_low_s
    assert "–" in estimate.active_band


# ---------------------------------------------------------------------------
# §32 — the updated estimate, and why it changed
# ---------------------------------------------------------------------------
def test_a_bigger_site_than_assumed_raises_the_estimate_and_says_so(estimator):
    initial = estimator.initial(community(urls=["https://a.example/"]))
    probe = DiscoveryProbe(sources=1, domains=1, sitemaps_found=1,
                           estimated_pages=600, documents_seen=40)
    updated = estimator.after_discovery(probe, initial)
    assert updated.active_low_s > initial.active_low_s
    assert "600 pages" in updated.reason
    assert updated.phase == "after_discovery"


def test_a_smaller_site_than_assumed_lowers_the_estimate(estimator):
    initial = estimator.initial(community(urls=["https://a.example/",
                                                "https://b.example/"]))
    probe = DiscoveryProbe(sources=2, domains=2, sitemaps_found=2,
                           estimated_pages=8, documents_seen=1)
    updated = estimator.after_discovery(probe, initial)
    assert updated.active_low_s < initial.active_low_s
    assert "smaller than assumed" in updated.reason


def test_a_javascript_site_costs_more_and_the_reason_says_so(estimator):
    initial = estimator.initial(community(urls=["https://a.example/"]))
    plain = estimator.after_discovery(
        DiscoveryProbe(sources=1, domains=1, estimated_pages=100), initial)
    js = estimator.after_discovery(
        DiscoveryProbe(sources=1, domains=1, estimated_pages=100,
                       javascript_sources=1), initial)
    assert js.active_low_s > plain.active_low_s
    assert js.workload.browser_pages > 0


def test_confirmation_is_reported_when_nothing_much_changed(estimator):
    initial = estimator.initial(community(urls=["https://a.example/"]))
    probe = DiscoveryProbe(sources=1, domains=1,
                           estimated_pages=initial.workload.pages,
                           documents_seen=initial.workload.documents)
    updated = estimator.after_discovery(probe, initial)
    assert "broadly confirmed" in updated.reason


def test_image_triage_lowers_the_expected_download_count(estimator):
    initial = estimator.initial(community(urls=["https://a.example/"]))
    probe = DiscoveryProbe(sources=1, domains=1, estimated_pages=100,
                           images_per_page=20.0, image_keep_rate=0.05)
    updated = estimator.after_discovery(probe, initial)
    assert updated.workload.image_candidates == 2000
    assert updated.workload.image_downloads == 100      # 5% of them


# ---------------------------------------------------------------------------
# §34 — learning from what actually happened
# ---------------------------------------------------------------------------
def test_history_calibrates_a_later_estimate(settings, db, community_id="IC001"):
    naive = Estimator(settings, db)
    before = naive.initial(community(urls=["https://a.example/"]))
    assert not before.calibrated

    # Two previous runs that each took twice as long as predicted.
    for index in range(2):
        db.upsert("run_history", {
            "run_id": f"IC001-RUN00{index + 1}", "community_id": community_id,
            "mode": "FULL", "estimated_active_s": 1000.0, "actual_active_s": 2000.0,
            "wall_clock_s": 2400.0, "ts_utc": utcnow(),
        }, ["run_id"])

    wiser = Estimator(settings, db)
    after = wiser.initial(community(urls=["https://a.example/"]))
    assert after.calibrated
    assert after.calibration_factor == pytest.approx(2.0, abs=0.01)
    assert after.active_low_s == pytest.approx(before.active_low_s * 2.0, rel=0.01)


def test_one_pathological_run_cannot_wreck_the_model(settings, db):
    for index in range(3):
        ratio = 400.0 if index == 0 else 1.0      # one run that took forever
        db.upsert("run_history", {
            "run_id": f"IC001-RUN10{index}", "community_id": "IC001", "mode": "FULL",
            "estimated_active_s": 100.0, "actual_active_s": 100.0 * ratio,
            "wall_clock_s": 100.0, "ts_utc": utcnow(),
        }, ["run_id"])
    estimator = Estimator(settings, db)
    estimate = estimator.initial(community(urls=["https://a.example/"]))
    # The median ignores the outlier, and the clamp would catch it anyway.
    assert estimate.calibration_factor <= 3.0


def test_a_single_previous_run_is_not_enough_to_calibrate(settings, db):
    db.upsert("run_history", {
        "run_id": "IC001-RUN001", "community_id": "IC001", "mode": "FULL",
        "estimated_active_s": 100.0, "actual_active_s": 500.0,
        "wall_clock_s": 600.0, "ts_utc": utcnow(),
    }, ["run_id"])
    estimate = Estimator(settings, db).initial(community(urls=["https://a.example/"]))
    assert not estimate.calibrated


def test_the_actuals_are_recorded_for_next_time(settings, db):
    estimator = Estimator(settings, db)
    estimator.record_actual(
        run_id="IC001-RUN009", community_id="IC001", mode="FULL",
        estimated_active_s=900.0, actual_active_s=1200.0, wall_clock_s=1800.0,
        offline_s=300.0, paused_manual_s=120.0,
        stats={"pages_opened": 140, "documents": 12, "images_kept": 17,
               "pauses_network": 1, "pauses_manual": 1},
        final_state="COMPLETED")
    row = db.query_one("SELECT * FROM run_history WHERE run_id='IC001-RUN009'")
    assert row["actual_active_s"] == 1200.0
    assert row["offline_s"] == 300.0
    assert row["pages_processed"] == 140
    assert row["images_kept"] == 17
    assert row["final_state"] == "COMPLETED"


def test_an_estimate_is_stored_against_the_run(settings, db):
    estimator = Estimator(settings, db)
    estimate = estimator.initial(community(urls=["https://a.example/"]))
    estimator.record(estimate, run_id="IC001-RUN001", community_id="IC001")
    row = db.query_one("SELECT * FROM run_estimates WHERE run_id='IC001-RUN001'")
    assert row["phase"] == "initial"
    assert row["active_low_s"] > 0
    assert row["unit_count"] > 0


# ---------------------------------------------------------------------------
# §35 — estimating must not become the crawl
# ---------------------------------------------------------------------------
def test_the_discovery_probe_makes_only_a_handful_of_requests(settings):
    """Three questions per address: robots, its sitemaps, its home page."""
    from dcr.discovery.probe import probe_workload

    class CountingFetcher:
        def __init__(self):
            self.calls: list[str] = []

        async def robots_for(self, url):
            self.calls.append(f"robots:{url}")
            return type("Policy", (), {"sitemaps": []})()

        async def fetch(self, url, **kwargs):
            self.calls.append(url)
            return type("Result", (), {
                "ok": False, "content": b"", "text": "", "mime": "",
                "error_type": "http_404",
            })()

    fetcher = CountingFetcher()
    urls = [f"https://s{i}.example/" for i in range(4)]
    probe = asyncio.run(probe_workload(urls, fetcher=fetcher, lexicon=settings.lexicon))
    assert probe.sources == 4
    # robots + one guessed sitemap + the home page, per address.
    assert len(fetcher.calls) <= 4 * 4
    assert probe.requests_made <= 4 * 4


def test_an_address_that_does_not_answer_is_still_counted(settings):
    from dcr.discovery.probe import probe_workload

    class DeadFetcher:
        async def robots_for(self, url):
            return type("Policy", (), {"sitemaps": []})()

        async def fetch(self, url, **kwargs):
            return type("Result", (), {"ok": False, "content": b"", "text": "",
                                       "mime": "", "error_type": "connection_error"})()

    probe = asyncio.run(probe_workload(["https://gone.example/"],
                                       fetcher=DeadFetcher(), lexicon=settings.lexicon))
    assert probe.unreachable_sources == 1
    assert any("not unreachable later" in note for note in probe.notes)
