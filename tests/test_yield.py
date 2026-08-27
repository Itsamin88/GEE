"""The stopping rule: evidence per active minute, and nothing else.

These tests are the specification for the behaviour that replaces the
thirty-minute cap. The two cases that matter most are at the top: a rich
community must not be stopped, and a worked-out one must not be lingered on.
Everything below is the machinery that has to be right for those two to hold.
"""

from __future__ import annotations

import pytest

from dcr.yieldmeter import (DEFAULT_WEIGHTS, INDEPENDENT_KINDS, YieldMeter,
                            meter_from_settings)


def drive(meter: YieldMeter, *, minutes: float, finds: int, kind: str = "passage",
          scopes=("run",), start: int = 0) -> None:
    """Spend `minutes` of active time producing `finds` distinct findings."""
    seconds = minutes * 60.0
    steps = max(1, finds)
    for index in range(steps):
        meter.spend(seconds / steps, scopes)
        meter.attempt(scopes)
        if index < finds:
            meter.credit(kind, key=f"{kind}-{start + index}", scopes=scopes)


# ---------------------------------------------------------------------------
# §1, §25 — the two cases the rewrite exists for
# ---------------------------------------------------------------------------
def test_a_community_still_producing_is_never_stopped():
    """Four hours of steady evidence. The old design stopped this at thirty
    minutes and lost everything after."""
    meter = YieldMeter()
    for block in range(24):                       # 24 x 10 min = 4 hours
        drive(meter, minutes=10, finds=60, kind="passage", start=block * 60)
        assert meter.verdict("run").keep_going, (
            f"stopped after {(block + 1) * 10} minutes of productive crawling")


def test_a_community_that_has_gone_quiet_is_stopped_promptly():
    meter = YieldMeter(warmup_s=30, warmup_attempts=5)
    drive(meter, minutes=3, finds=200, kind="passage")
    assert meter.verdict("run").keep_going

    # Ten minutes of trying and finding nothing.
    for _ in range(10):
        meter.spend(60, ("run",))
        meter.attempt(("run",), 20)
    verdict = meter.verdict("run")
    assert not verdict.keep_going
    assert "yield fell" in verdict.reason or "never rose" in verdict.reason


# ---------------------------------------------------------------------------
# §66 — diminishing returns, judged against the scope's own best
# ---------------------------------------------------------------------------
def test_a_source_is_judged_against_its_own_best_rate():
    """40 units/min falling to 3 is exhaustion even though 3 is not nothing."""
    meter = YieldMeter(absolute_floor=2.0, decay_fraction=0.15,
                       warmup_s=30, warmup_attempts=5)
    scope = ("run", "source:S1")
    drive(meter, minutes=2, finds=120, kind="field_first", scopes=scope)
    assert meter.scope("source:S1").peak_rate > 100

    # Now a long tail of near-nothing.
    for index in range(12):
        meter.spend(60, scope)
        meter.attempt(scope, 10)
        if index % 6 == 0:
            meter.credit("passage", key=f"tail-{index}", scopes=scope)
    assert not meter.verdict("source:S1").keep_going


def test_a_source_that_comes_back_to_life_re_earns_its_time():
    meter = YieldMeter(absolute_floor=2.0, warmup_s=30, warmup_attempts=5)
    scope = ("run", "source:S2")
    drive(meter, minutes=2, finds=100, scopes=scope)
    for _ in range(8):                             # a quiet patch
        meter.spend(60, scope)
        meter.attempt(scope, 10)
    assert not meter.verdict("source:S2").keep_going

    drive(meter, minutes=1, finds=80, kind="document_unique", scopes=scope,
          start=500)
    assert meter.verdict("source:S2").keep_going, (
        "a source that started producing again was still treated as exhausted")


def test_a_scope_that_never_produced_much_is_stopped_without_a_peak():
    meter = YieldMeter(absolute_floor=5.0, warmup_s=30, warmup_attempts=5)
    scope = ("run", "source:S3")
    for index in range(10):
        meter.spend(60, scope)
        meter.attempt(scope, 5)
        if index % 5 == 0:
            meter.credit("passage", key=f"weak-{index}", scopes=scope)
    verdict = meter.verdict("source:S3")
    assert not verdict.keep_going
    assert "never rose" in verdict.reason


# ---------------------------------------------------------------------------
# warm-up: nothing is judged before it has had a chance
# ---------------------------------------------------------------------------
def test_nothing_is_judged_during_its_warm_up():
    meter = YieldMeter(warmup_s=60, warmup_attempts=10)
    meter.spend(30, ("run",))
    meter.attempt(("run",), 3)
    verdict = meter.verdict("run")
    assert verdict.keep_going and verdict.warming_up


def test_a_stalled_request_is_not_read_as_exhaustion():
    """Time passed but almost nothing was tried: that is a slow server, not an
    exhausted source."""
    meter = YieldMeter(warmup_s=30, warmup_attempts=25)
    meter.spend(300, ("run",))
    meter.attempt(("run",), 2)
    assert meter.verdict("run").warming_up


# ---------------------------------------------------------------------------
# §25 — repetition is not evidence
# ---------------------------------------------------------------------------
def test_the_same_find_is_credited_once():
    meter = YieldMeter()
    first = meter.credit("document_unique", key="hash-abc", scopes=("run",))
    second = meter.credit("document_unique", key="hash-abc", scopes=("run",))
    assert first == DEFAULT_WEIGHTS["document_unique"]
    assert second == 0.0
    assert meter.scope("run").duplicates == 1


def test_a_site_that_repeats_itself_does_not_look_productive():
    """Two hundred pages all saying the same thing."""
    meter = YieldMeter(warmup_s=30, warmup_attempts=5)
    for _ in range(200):
        meter.spend(3, ("run",))
        meter.attempt(("run",))
        meter.credit("passage", key="we are a community in Portugal", scopes=("run",))
    assert not meter.verdict("run").keep_going
    assert meter.scope("run").units == pytest.approx(DEFAULT_WEIGHTS["passage"])


def test_independent_value_is_counted_separately_from_repetition():
    meter = YieldMeter()
    meter.credit("passage", key="p1", scopes=("run",))
    meter.credit("field_first", key="e3_population_value", scopes=("run",))
    run = meter.scope("run")
    assert run.units > run.independent_units > 0
    assert "field_first" in INDEPENDENT_KINDS
    assert "passage" not in INDEPENDENT_KINDS


# ---------------------------------------------------------------------------
# scopes are nested views, not competing budgets
# ---------------------------------------------------------------------------
def test_one_second_of_work_is_charged_to_every_account_it_belongs_to():
    meter = YieldMeter()
    scopes = ("run", "stage:3", "source:S1")
    meter.spend(60, scopes)
    meter.credit("land_area", key="managed_area_ha", scopes=scopes)
    for name in scopes:
        assert meter.scope(name).active_s == pytest.approx(60)
        assert meter.scope(name).units == DEFAULT_WEIGHTS["land_area"]


def test_a_quiet_stage_does_not_end_a_productive_run():
    meter = YieldMeter(warmup_s=30, warmup_attempts=5)
    drive(meter, minutes=4, finds=250, scopes=("run", "stage:2"))
    for _ in range(8):
        meter.spend(60, ("run", "stage:5"))
        meter.attempt(("run", "stage:5"), 10)
    assert not meter.verdict("stage:5").keep_going
    assert meter.verdict("run", absolute_floor=1.0, decay_fraction=0.05).keep_going


# ---------------------------------------------------------------------------
# earned extensions
# ---------------------------------------------------------------------------
def test_a_productive_scope_earns_more_time_than_a_poor_one():
    meter = YieldMeter(absolute_floor=2.0)
    drive(meter, minutes=1, finds=60, kind="field_first", scopes=("rich",))
    for _ in range(20):
        meter.spend(3, ("poor",))
        meter.attempt(("poor",))
    meter.credit("passage", key="one", scopes=("poor",))
    rich = meter.earned_extension_s("rich", base_s=100)
    poor = meter.earned_extension_s("poor", base_s=100)
    assert rich > poor
    assert rich <= 800


# ---------------------------------------------------------------------------
# §37, §73 — resuming must not re-credit what is already held
# ---------------------------------------------------------------------------
def test_a_resumed_meter_does_not_re_credit_stored_evidence():
    first = YieldMeter()
    for index in range(30):
        first.credit("document_unique", key=f"hash-{index}", scopes=("run",))
    saved = first.state_for_resume()

    second = YieldMeter()
    second.restore(saved)
    assert second.scope("run").units == pytest.approx(first.scope("run").units)
    earned = sum(second.credit("document_unique", key=f"hash-{i}", scopes=("run",))
                 for i in range(30))
    assert earned == 0.0, (
        "a resumed crawl re-counted documents it already had, and would have "
        "concluded that an exhausted source was productive again")


def test_a_resumed_scope_starts_its_warm_up_again():
    """'Recent' means recent in this session, not last Tuesday."""
    first = YieldMeter(warmup_s=60, warmup_attempts=10)
    drive(first, minutes=5, finds=200)
    second = YieldMeter(warmup_s=60, warmup_attempts=10)
    second.restore(first.state_for_resume())
    assert second.verdict("run").warming_up


def test_restoring_nothing_is_harmless():
    meter = YieldMeter()
    meter.restore(None)
    meter.restore({})
    assert meter.scope("run").units == 0


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------
def test_the_snapshot_reports_the_rate_the_brief_asks_for():
    meter = YieldMeter()
    drive(meter, minutes=4, finds=120, kind="practice")
    snapshot = meter.snapshot()
    assert snapshot["evidence_yield_per_min"] > 0
    assert snapshot["independent_yield_per_min"] > 0
    assert snapshot["by_kind"]["practice"] == 120
    assert snapshot["scopes"][0]["scope"] == "run"


def test_the_curve_shows_whether_the_run_was_still_climbing():
    meter = YieldMeter()
    drive(meter, minutes=2, finds=150)                       # busy
    for _ in range(10):                                       # then quiet
        meter.spend(60, ("run",))
        meter.attempt(("run",))
    curve = meter.curve(buckets=6)
    assert len(curve) == 6
    assert curve[0]["per_min"] > curve[-1]["per_min"]


def test_measurement_never_raises_on_an_unknown_kind():
    meter = YieldMeter()
    assert meter.credit("something-nobody-defined", key="k", scopes=("run",)) == 0.0


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------
def test_the_weights_and_floors_come_from_configuration(settings):
    meter = meter_from_settings(settings)
    assert meter.absolute_floor > 0
    assert meter.weights["field_first"] > meter.weights["passage"]
    assert meter.weights["onset_evidence"] >= meter.weights["document_unique"], (
        "onset dating is the study's hardest field and must outrank a document"
    )


def test_a_meter_built_from_nothing_still_works():
    meter = meter_from_settings(None)
    assert meter.credit("field_first", key="x", scopes=("run",)) > 0
