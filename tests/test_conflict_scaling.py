"""Disagreement must scale with disagreement, not with repetition.

The reported run ended with 5569 conflicts, in runs of near-identical lines:

    population_value: 200 vs 100
    population_value: 200 vs 350
    population_value: 200 vs 240

That is one field with a handful of competing figures, printed once for every
claim that carried one. The real disagreements were buried under repetitions of
the same two numbers, and no coder could use the result.

One row per competing VALUE; the individual claims stay in the claims table
with their own wording and source (brief §31, §32).
"""

from __future__ import annotations

import pytest

from dcr.evidence.conflict import ClaimView, resolve_field


def claims_for(values, *, count, field="resident_population_value", groups=6, sources=12):
    """`count` claims spread over `values`, as a rich site's pages would give."""
    return [
        ClaimView(
            claim_id=f"C{i:04d}", field_name=field, value=str(values[i % len(values)]),
            source_id=f"S{i % sources:02d}", source_class="S4",
            independence_group=f"G{i % groups}", confidence=0.5,
        )
        for i in range(count)
    ]


POPULATION_VALUES = [100, 150, 170, 200, 220, 240, 250, 280, 300, 320, 350, 400, 450, 500]


# ---------------------------------------------------------------------------
# the reported explosion
# ---------------------------------------------------------------------------
def test_conflicts_scale_with_distinct_values_not_with_claims():
    resolution = resolve_field("resident_population_value",
                               claims_for(POPULATION_VALUES, count=400), numeric=True)
    assert len(resolution.conflicts) == len(POPULATION_VALUES) - 1, (
        "one row per competing value: 14 figures is 13 disagreements with the best, "
        "however many pages repeated them")


@pytest.mark.parametrize("count", [20, 200, 2000, 5000])
def test_the_row_count_is_flat_however_often_the_community_repeats_itself(count):
    resolution = resolve_field("resident_population_value",
                               claims_for(POPULATION_VALUES, count=count), numeric=True)
    assert len(resolution.conflicts) == 13, (
        f"{count} claims produced {len(resolution.conflicts)} rows; it must stay 13")


def test_five_thousand_claims_do_not_take_meaningful_time():
    """The old shape was O(claims); 5569 rows is what that costs."""
    import time

    started = time.monotonic()
    resolution = resolve_field("resident_population_value",
                               claims_for(POPULATION_VALUES, count=5000), numeric=True)
    assert (time.monotonic() - started) < 2.0
    assert len(resolution.conflicts) == 13


# ---------------------------------------------------------------------------
# summarising must not thin the record
# ---------------------------------------------------------------------------
def test_each_row_says_how_much_stands_behind_each_side():
    resolution = resolve_field("resident_population_value",
                               claims_for(POPULATION_VALUES, count=400), numeric=True)
    for conflict in resolution.conflicts:
        assert conflict["claims_a"] > 1
        assert conflict["claims_b"] > 1
        assert conflict["groups_a"] >= 1
        assert conflict["groups_b"] >= 1
        assert conflict["distinct_values"] == 14


def test_the_summary_reads_the_way_the_brief_asks():
    resolution = resolve_field("resident_population_value",
                               claims_for(POPULATION_VALUES, count=400), numeric=True)
    summary = resolution.conflicts[0]["summary"]
    assert "14 distinct reported value" in summary
    assert "independence group" in summary
    assert "400 claim" in summary


def test_every_competing_value_is_still_represented():
    """Summarising must lose no distinct figure."""
    resolution = resolve_field("resident_population_value",
                               claims_for(POPULATION_VALUES, count=400), numeric=True)
    reported = {str(c["value_b"]) for c in resolution.conflicts}
    reported.add(str(resolution.conflicts[0]["value_a"]))
    assert reported == {str(v) for v in POPULATION_VALUES}


def test_the_strongest_claim_represents_its_value():
    """The row must point at the best claim for that figure, not an arbitrary one."""
    claims = [
        # 200 wins: it has the strongest source class behind it.
        ClaimView(claim_id="C1", field_name="f", value="200", source_id="S1",
                  source_class="S1", independence_group="G1", confidence=0.9),
        # 350 loses, and is carried by two claims of unequal weight.
        ClaimView(claim_id="C2", field_name="f", value="350", source_id="S2",
                  source_class="S4", independence_group="G2", confidence=0.1),
        ClaimView(claim_id="C3", field_name="f", value="350", source_id="S3",
                  source_class="S4", independence_group="G3", confidence=0.8),
    ]
    resolution = resolve_field("f", claims, numeric=True)
    row = next(c for c in resolution.conflicts if str(c["value_b"]) == "350")
    assert row["claim_b"] == "C3", "the strongest claim for 350 should represent it"
    assert row["claims_b"] == 2
    assert row["groups_b"] == 2, "both independence groups behind 350 must be counted"


# ---------------------------------------------------------------------------
# the behaviour that must NOT change
# ---------------------------------------------------------------------------
def test_agreement_is_still_agreement():
    claims = claims_for([200], count=50)
    resolution = resolve_field("resident_population_value", claims, numeric=True)
    assert resolution.status == "coded"
    assert resolution.conflicts == []


def test_a_single_real_disagreement_is_still_one_row():
    claims = [
        ClaimView(claim_id="C1", field_name="f", value="200", source_id="S1",
                  source_class="S1", independence_group="G1"),
        ClaimView(claim_id="C2", field_name="f", value="350", source_id="S2",
                  source_class="S1", independence_group="G2"),
    ]
    resolution = resolve_field("f", claims, numeric=True)
    assert len(resolution.conflicts) == 1
    assert resolution.status == "review_required", (
        "equal strength across independence groups still goes to a human")


def test_growth_over_time_is_still_not_a_conflict():
    """A community that grew is not a community contradicting itself."""
    claims = [
        ClaimView(claim_id="C1", field_name="f", value="80", source_id="S1",
                  source_class="S1", independence_group="G1", reference_year=2005),
        ClaimView(claim_id="C2", field_name="f", value="200", source_id="S2",
                  source_class="S1", independence_group="G2", reference_year=2020),
    ]
    resolution = resolve_field("f", claims, numeric=True)
    assert resolution.method == "time_series"
    assert resolution.status == "coded"
