"""Evidence, claims, practices, onset dating and conflict resolution."""

from __future__ import annotations

import pytest

from dcr.evidence.conflict import ClaimView, ReviewQueue, resolve_field
from dcr.evidence.model import ClaimItem, EvidenceItem, EvidenceRecorder, sentences
from dcr.evidence.onset import DateCandidate, rank_for, resolve_onset
from dcr.evidence.practices import PracticeDetector, code_practices, fold
from dcr.evidence.quantities import find_areas, find_populations


# -- the anti-fabrication gate ---------------------------------------------
def test_satellite_only_field_is_refused(db, community, schema):
    recorder = EvidenceRecorder(db, community, schema)
    evidence_id = recorder.add_evidence(
        EvidenceItem(evidence_type="passage", quote="the site covers 13 hectares"))
    assert recorder.add_claim(ClaimItem(field_name="polygon_area_ha", value="13"),
                              evidence_id, {}) is None
    assert any("satellite" in reason for _, reason in recorder.rejected)


def test_unknown_field_is_refused(db, community, schema):
    recorder = EvidenceRecorder(db, community, schema)
    evidence_id = recorder.add_evidence(EvidenceItem(evidence_type="passage", quote="x"))
    assert recorder.add_claim(ClaimItem(field_name="invented_field", value="7"),
                              evidence_id, {}) is None


def test_claim_requires_a_value(db, community, schema):
    recorder = EvidenceRecorder(db, community, schema)
    evidence_id = recorder.add_evidence(EvidenceItem(evidence_type="passage", quote="x"))
    assert recorder.add_claim(ClaimItem(field_name="managed_area_ha", value="  "),
                              evidence_id, {}) is None


def test_passage_verification_rejects_an_invented_quote(db, community, schema):
    recorder = EvidenceRecorder(db, community, schema)
    stored = "Sur le lieu, nous cultivons 4 hectares."
    assert recorder.verify_passage("nous  cultivons 4 HECTARES", stored)
    assert not recorder.verify_passage("nous cultivons 40 hectares", stored)


def test_evidence_and_claim_are_linked(db, community, schema):
    recorder = EvidenceRecorder(db, community, schema)
    evidence_id, claim_ids = recorder.record(
        EvidenceItem(evidence_type="passage", quote="Nous cultivons 4 hectares.",
                     source_class="S4"),
        [ClaimItem(field_name="managed_area_ha", value="4", original_value="4 hectares",
                   extractor="rule:test")],
        {"source_id": None},
    )
    row = db.query_one("SELECT * FROM claims WHERE claim_id=?", (claim_ids[0],))
    assert row["evidence_id"] == evidence_id
    assert row["original_value"] == "4 hectares"


# -- quantities -------------------------------------------------------------
def test_managed_area_is_distinguished_from_the_whole_holding(lexicon):
    text = ("Le domaine de 200 hectares est notre propriete. "
            "Nous cultivons 15 hectares en maraichage.")
    found = find_areas(text, lexicon["quantities"]["area_units"], sentences(text),
                       markers=lexicon["quantities"])
    kinds = {round(a.value_ha): a.kind for a in found}
    assert kinds[15] == "managed"
    assert kinds[200] == "total_holding"


def test_units_are_converted_but_the_original_wording_survives(lexicon):
    text = "The market garden covers 10 acres."
    found = find_areas(text, lexicon["quantities"]["area_units"], sentences(text),
                       markers=lexicon["quantities"])
    assert found[0].original == "10 acres"
    assert found[0].value_ha == pytest.approx(4.047, abs=0.01)


def test_a_stated_range_is_kept_as_a_range(lexicon):
    text = "The community works between 10 and 12 hectares."
    found = find_areas(text, lexicon["quantities"]["area_units"], sentences(text),
                       markers=lexicon["quantities"])
    assert (found[0].lower_ha, found[0].upper_ha) == (10.0, 12.0)


def test_reference_year_is_read_from_the_same_sentence(lexicon):
    text = "Nous cultivons 4 hectares depuis 2018."
    found = find_areas(text, lexicon["quantities"]["area_units"], sentences(text),
                       markers=lexicon["quantities"])
    assert found[0].reference_year == 2018


def test_a_year_is_never_read_as_a_population(lexicon):
    text = "En 2017 nous avons creuse des baissieres sur les pentes."
    assert find_populations(text, sentences(text), markers=lexicon["quantities"]) == []


def test_visitors_are_not_permanent_residents(lexicon):
    text = "Nous accueillons 800 visiteurs par an."
    found = find_populations(text, sentences(text), markers=lexicon["quantities"])
    assert all(m.kind != "permanent" for m in found)


def test_permanent_residents_are_counted(lexicon):
    text = "Nous sommes 40 habitants permanents en 2023."
    found = find_populations(text, sentences(text), markers=lexicon["quantities"])
    assert found[0].value == 40 and found[0].kind == "permanent"
    assert found[0].reference_year == 2023


# -- practices --------------------------------------------------------------
def test_accent_folding_preserves_length():
    assert len(fold("forêt-jardin çà où")) == len("forêt-jardin çà où")
    assert fold("forêt") == "foret"


def test_silence_is_never_absence(lexicon):
    detector = PracticeDetector(lexicon)
    coding = code_practices(detector.scan(sentences("We grow vegetables.")),
                            all_practices=["pc01_rainwater"])
    assert coding["pc01_rainwater"].level == "not mentioned"
    assert "NOT evidence of absence" in coding["pc01_rainwater"].rationale


def test_an_actual_denial_is_explicitly_absent(lexicon):
    detector = PracticeDetector(lexicon)
    hits = detector.scan(sentences("Nous n'irriguons pas les prairies."), source_class="S4")
    coding = code_practices(hits, all_practices=["pc03_irrigation"])
    assert coding["pc03_irrigation"].level == "explicitly absent"


def test_an_external_specific_source_upgrades_to_evidenced(lexicon):
    detector = PracticeDetector(lexicon)
    hits = detector.scan(
        sentences("The author observed no-till cultivation across the cropped area in 2019."),
        source_class="S1", publication_date="2019-01-01")
    coding = code_practices(hits, all_practices=["pc04_no_till"])
    assert coding["pc04_no_till"].level == "evidenced"


def test_community_continuity_across_years_is_documented(lexicon):
    detector = PracticeDetector(lexicon)
    hits = detector.scan(sentences("Nous avons plante 3000 arbres en 2015."),
                         source_class="S4", publication_date="2015-06-01")
    hits += detector.scan(sentences("In 2019 werden 1200 bomen geplant."),
                          source_class="S4", publication_date="2019-06-01")
    coding = code_practices(hits, all_practices=["pc07_tree_planting"])
    assert coding["pc07_tree_planting"].level == "documented"


def test_building_restoration_does_not_evidence_land_restoration(lexicon):
    detector = PracticeDetector(lexicon)
    hits = detector.scan(sentences("La restauration du batiment principal s'est achevee en 2019."))
    assert not [h for h in hits if h.practice == "pc13_restoration"]


# -- onset ------------------------------------------------------------------
def test_rank_scale():
    assert rank_for(source_class="S1", is_archive_snapshot=False, already_under_way=False,
                    has_explicit_year=True, retrospective=False,
                    is_directory_founding=False)[0] == 1
    assert rank_for(source_class="S5", is_archive_snapshot=True, already_under_way=True,
                    has_explicit_year=True, retrospective=False,
                    is_directory_founding=False)[0] == 2
    assert rank_for(source_class="S3", is_archive_snapshot=False, already_under_way=False,
                    has_explicit_year=True, retrospective=False,
                    is_directory_founding=True)[0] == 5


def test_onset_is_the_earliest_documented_action_not_the_founding_year(schema):
    outcome = resolve_onset([
        DateCandidate("date_formal_founding", 1985, "Founded in 1985", "S1", "S4", 3, "own"),
        DateCandidate("date_intervention_onset", 1992, "We began planting in 1992", "S1", "S4",
                      3, "own", domain="vegetation"),
    ], cohort_windows=schema["cohort_windows"])
    assert outcome.values["date_formal_founding"] == 1985
    assert outcome.values["date_intervention_onset"] == 1992


def test_equal_rank_disagreement_takes_the_earlier_year_and_widens_the_band(schema):
    outcome = resolve_onset([
        DateCandidate("date_intervention_onset", 1992, "planting 1992", "S1", "S4", 3, "own",
                      domain="vegetation"),
        DateCandidate("date_intervention_onset", 1990, "planting 1990", "S2", "S4", 3, "own",
                      domain="vegetation"),
    ], cohort_windows=schema["cohort_windows"])
    assert outcome.values["date_intervention_onset"] == 1990
    assert outcome.values["onset_lower_bound"] <= 1990
    assert outcome.values["onset_upper_bound"] >= 1992
    assert outcome.conflicts


def test_a_directory_founding_year_sets_the_proxy_flag(schema):
    outcome = resolve_onset([
        DateCandidate("date_intervention_onset", 2009, "Directory says founded 2009", "S9",
                      "S3", 5, "directory proxy"),
    ], cohort_windows=schema["cohort_windows"])
    assert outcome.values["onset_proxy_flag"] == "yes"
    assert any(item["severity"] == "blocking" for item in outcome.review_items)


def test_no_onset_evidence_is_not_found_not_a_guess(schema):
    outcome = resolve_onset([], cohort_windows=schema["cohort_windows"])
    assert outcome.values["date_intervention_onset"] == "NOT FOUND"
    assert outcome.values["onset_confidence_tier"] == "C"
    assert outcome.review_items


def test_a_precise_rank_one_record_reaches_tier_a_and_the_cohort(schema):
    outcome = resolve_onset([
        DateCandidate("date_intervention_onset", 2020, "The LIFE grant funded planting in 2020",
                      "S1", "S2", 1, "dated grant record", domain="vegetation"),
    ], cohort_windows=schema["cohort_windows"])
    assert outcome.values["onset_confidence_tier"] == "A"
    assert outcome.values["cohort_candidate"] == "core (2020-2021)"


def test_domain_onsets_record_the_earliest_year_per_domain(schema):
    outcome = resolve_onset([
        DateCandidate("date_intervention_onset", 1998, "water works 1998", "S1", "S4", 3, "own",
                      domain="water"),
        DateCandidate("date_intervention_onset", 1992, "planting 1992", "S1", "S4", 3, "own",
                      domain="vegetation"),
    ], cohort_windows=schema["cohort_windows"])
    assert "vegetation 1992" in outcome.values["domain_onsets"]
    assert "water 1998" in outcome.values["domain_onsets"]


# -- conflicts --------------------------------------------------------------
def _claim(cid, value, source_class, group, year=None):
    return ClaimView(claim_id=cid, field_name="managed_area_ha", value=str(value),
                     source_id=cid, source_class=source_class, independence_group=group,
                     reference_year=year)


def test_agreement_across_groups_is_corroboration():
    resolution = resolve_field("managed_area_ha",
                               [_claim("C1", 15, "S4", "G1"), _claim("C2", 15, "S1", "G2")],
                               numeric=True)
    assert resolution.status == "coded" and resolution.value == "15"
    assert len(resolution.groups) == 2


def test_growth_over_time_is_not_a_conflict():
    resolution = resolve_field("managed_area_ha",
                               [_claim("C1", 4, "S5", "G1", 2012),
                                _claim("C2", 15, "S4", "G1", 2024)],
                               numeric=True)
    assert resolution.method == "time_series"
    assert resolution.value == "15"
    assert "2012" in resolution.residual_uncertainty


def test_a_stronger_class_wins_but_the_weaker_value_survives():
    resolution = resolve_field("managed_area_ha",
                               [_claim("C1", 200, "S4", "G1"), _claim("C2", 15, "S1", "G2")],
                               numeric=True)
    assert resolution.value == "15"
    assert "200" in resolution.residual_uncertainty
    assert resolution.conflicts


def test_equal_strength_across_groups_goes_to_a_human():
    resolution = resolve_field("population_value",
                               [_claim("C1", 28, "S1", "G2"), _claim("C2", 45, "S2", "G3")],
                               numeric=True)
    assert resolution.status == "review_required"
    assert resolution.value is None
    assert resolution.review["severity"] == "blocking"


def test_no_claims_is_not_found():
    resolution = resolve_field("tenure_type", [])
    assert resolution.status == "not_found"


def test_review_queue_deduplicates():
    queue = ReviewQueue()
    queue.add("conflict", "same", "detail", severity="blocking")
    queue.add("conflict", "same", "detail")
    assert len(queue) == 1 and len(queue.blocking) == 1
