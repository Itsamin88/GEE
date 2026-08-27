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
def _pop(cid, value, role, group="G1", source_class="S4",
         field_name="e3_population_value"):
    return ClaimView(claim_id=cid, field_name=field_name, value=str(value),
                     source_id=cid, source_class=source_class,
                     independence_group=group, semantic_role=role)


def _claim(cid, value, source_class, group, year=None, role="managed"):
    # Every claim on a role-bearing field carries its semantic role: what the
    # figure is a figure OF. Without one it is not a candidate for the field at
    # all, which is the point of `evidence/roles.py`.
    return ClaimView(claim_id=cid, field_name="managed_area_ha", value=str(value),
                     source_id=cid, source_class=source_class, independence_group=group,
                     reference_year=year, semantic_role=role)


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
                               [_pop("C1", 28, "resident", "G2", "S1",
                                     field_name="population_value"),
                                _pop("C2", 45, "resident", "G3", "S2",
                                     field_name="population_value")],
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


# ---------------------------------------------------------------------------
# Idempotent reprocessing (brief §27)
#
# A pause, a retry and a resumed run all reach the same passage again. Each
# time, the answer must be the same row: duplicate evidence would inflate every
# count in the completion report and fill the evidence manifest with the same
# sentence over and over.
# ---------------------------------------------------------------------------
@pytest.fixture()
def crawled(db, community):
    """One source and two pages, so evidence has something real to point at."""
    from dcr.db import utcnow

    db.insert("sources", {
        "source_id": "IC001-S001", "community_id": community,
        "address_id": "IC001-01", "url": "https://example.org/",
        "source_class": "S1", "supplied_or_discovered": "supplied",
    })
    for page_id, url in (("IC001-P0001", "https://example.org/histoire"),
                         ("IC001-P0002", "https://example.org/about")):
        db.insert("pages", {
            "page_id": page_id, "community_id": community, "source_id": "IC001-S001",
            "url": url, "normalized_url": url, "fetched_utc": utcnow(),
        })
    return community


def _passage(**kwargs) -> EvidenceItem:
    kwargs.setdefault("evidence_type", "passage")
    kwargs.setdefault("quote", "En 2017 nous avons creuse des baissieres.")
    kwargs.setdefault("source_id", "IC001-S001")
    kwargs.setdefault("page_id", "IC001-P0001")
    kwargs.setdefault("locator", "https://example.org/histoire")
    return EvidenceItem(**kwargs)


def test_the_same_passage_recorded_twice_is_one_row(db, crawled, community, schema):
    recorder = EvidenceRecorder(db, community, schema)
    first = recorder.add_evidence(_passage())
    second = recorder.add_evidence(_passage())
    assert first == second
    rows = db.query("SELECT * FROM evidence WHERE community_id=?", (community,))
    assert len(rows) == 1


def test_whitespace_alone_does_not_make_a_second_piece_of_evidence(db, crawled, community, schema):
    recorder = EvidenceRecorder(db, community, schema)
    first = recorder.add_evidence(_passage(quote="Nous cultivons 4 hectares."))
    second = recorder.add_evidence(_passage(quote="Nous  cultivons\n4 hectares."))
    assert first == second


def test_the_same_sentence_on_a_different_page_is_different_evidence(db, crawled, community, schema):
    """Two sources saying the same thing is corroboration, not duplication."""
    recorder = EvidenceRecorder(db, community, schema)
    first = recorder.add_evidence(_passage(page_id="IC001-P0001"))
    second = recorder.add_evidence(_passage(page_id="IC001-P0002",
                                            locator="https://example.org/about"))
    assert first != second


def test_a_later_pass_fills_in_offsets_the_first_one_lacked(db, crawled, community, schema):
    recorder = EvidenceRecorder(db, community, schema)
    first = recorder.add_evidence(_passage())
    recorder.add_evidence(_passage(char_start=153, char_end=201))
    row = db.query_one("SELECT * FROM evidence WHERE evidence_id=?", (first,))
    assert row["char_start"] == 153
    assert row["char_end"] == 201


def test_an_offset_already_recorded_is_not_overwritten(db, crawled, community, schema):
    recorder = EvidenceRecorder(db, community, schema)
    first = recorder.add_evidence(_passage(char_start=153, char_end=201))
    recorder.add_evidence(_passage())            # a pass that does not know where it sits
    row = db.query_one("SELECT * FROM evidence WHERE evidence_id=?", (first,))
    assert row["char_start"] == 153


def test_the_same_claim_from_the_same_passage_is_one_claim(db, crawled, community, schema):
    recorder = EvidenceRecorder(db, community, schema)
    evidence_id = recorder.add_evidence(_passage())
    claim = ClaimItem(field_name="date_intervention_onset", value="2017",
                      extractor="rule:onset/1.0.0")
    first = recorder.add_claim(claim, evidence_id, {})
    second = recorder.add_claim(claim, evidence_id, {})
    assert first == second
    rows = db.query("SELECT * FROM claims WHERE community_id=?", (community,))
    assert len(rows) == 1


def test_a_different_extractor_reaching_the_same_value_is_a_separate_claim(
        db, crawled, community, schema):
    """Two independent extractors agreeing is worth recording as two claims."""
    recorder = EvidenceRecorder(db, community, schema)
    evidence_id = recorder.add_evidence(_passage())
    first = recorder.add_claim(
        ClaimItem(field_name="date_intervention_onset", value="2017",
                  extractor="rule:onset/1.0.0"), evidence_id, {})
    second = recorder.add_claim(
        ClaimItem(field_name="date_intervention_onset", value="2017",
                  extractor="llm:semantic/1.0.0"), evidence_id, {})
    assert first != second


def test_reprocessing_never_orphans_a_claim_from_its_evidence(db, crawled, community, schema):
    """Regression: INSERT OR REPLACE deletes the row before re-inserting it.

    `claims.evidence_id` is ON DELETE SET NULL, so re-writing a passage that
    already existed silently cut every claim resting on it loose from the
    sentence that supported it — leaving a coded value with no traceable
    evidence, which is the one thing this whole design exists to prevent.
    """
    recorder = EvidenceRecorder(db, community, schema)
    evidence_id = recorder.add_evidence(_passage())
    recorder.add_claim(ClaimItem(field_name="date_intervention_onset", value="2017",
                                 extractor="rule:onset/1.0.0"), evidence_id, {})
    # Whatever else runs afterwards, the link must survive.
    recorder.add_evidence(_passage())
    recorder.add_evidence(_passage(char_start=10, char_end=40))

    claims = db.query("SELECT * FROM claims WHERE community_id=?", (community,))
    assert claims
    for claim in claims:
        assert claim["evidence_id"], "a claim was cut loose from its evidence"
        assert db.query_one("SELECT 1 FROM evidence WHERE evidence_id=?",
                            (claim["evidence_id"],)) is not None


# ===========================================================================
# §21-§24 — claims about different things are not competing claims
#
# The previous run produced 5 569 conflicts. Emitting one row per distinct
# VALUE rather than per PAIR removed the arithmetic half of that. This is the
# other half: the values being compared were never the same kind of thing.
# ===========================================================================
from dcr.evidence import roles


def test_visitors_and_residents_are_not_a_disagreement():
    """The single most common false conflict in the reported run."""
    resolution = resolve_field("e3_population_value", [
        _pop("C1", 12, "resident", "G1"),
        _pop("C2", 200, "visitor", "G2"),
        _pop("C3", 60, "event_attendance", "G2"),
        _pop("C4", 4, "employee", "G1"),
    ], numeric=True)
    assert resolution.value == "12", "the resident count must be the population"
    assert resolution.conflicts == [], (
        "four facts about four different groups of people were reported as "
        "contradictions")
    assert set(resolution.other_roles) == {"visitor", "event_attendance", "employee"}


def test_the_other_counts_are_kept_not_discarded():
    resolution = resolve_field("e3_population_value", [
        _pop("C1", 12, "resident"), _pop("C2", 200, "visitor"),
    ], numeric=True)
    assert resolution.other_roles["visitor"] == ["C2"]


def test_two_resident_counts_that_really_do_disagree_still_conflict():
    resolution = resolve_field("e3_population_value", [
        _pop("C1", 12, "resident", "G1", "S1"),
        _pop("C2", 40, "resident", "G2", "S1"),
    ], numeric=True)
    assert resolution.status == "review_required"
    assert resolution.conflicts, "a real disagreement was suppressed"


def test_a_field_with_no_figure_of_the_right_kind_is_not_coded():
    resolution = resolve_field("e3_population_value", [
        _pop("C1", 200, "visitor"), _pop("C2", 60, "event_attendance"),
    ], numeric=True)
    assert resolution.value is None
    assert resolution.status == "not_found"
    assert "none of them is a 'resident' figure" in resolution.rationale


def test_an_unclassifiable_figure_goes_to_a_human_not_to_a_cell():
    """Guessing here is what puts a visitor count in the population column."""
    resolution = resolve_field("e3_population_value", [
        _pop("C1", 34, roles.UNCLASSIFIED),
    ], numeric=True)
    assert resolution.value is None
    assert resolution.status == "review_required"
    assert resolution.review["severity"] == "blocking"


def test_the_whole_property_is_never_the_managed_area():
    """Confusing these moves a community two size classes (brief §23)."""
    resolution = resolve_field("managed_area_ha", [
        _claim("C1", 4, "S4", "G1", role="managed"),
        _claim("C2", 134, "S2", "G2", role="total_holding"),
        _claim("C3", 22, "S1", "G3", role="restoration"),
        _claim("C4", 8, "S4", "G1", role="leased"),
    ], numeric=True)
    assert resolution.value == "4"
    assert resolution.conflicts == []
    assert set(resolution.other_roles) == {"total_holding", "restoration", "leased"}


def test_a_conflict_row_says_which_role_it_is_about():
    resolution = resolve_field("managed_area_ha", [
        _claim("C1", 4, "S1", "G1"), _claim("C2", 9, "S4", "G2"),
    ], numeric=True)
    assert resolution.conflicts
    assert resolution.conflicts[0]["semantic_role"] == "managed"


# ---------------------------------------------------------------------------
# classification itself
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("sentence,expected", [
    ("Twelve permanent residents live here all year.", "resident"),
    ("We welcome around 200 visitors a year.", "visitor"),
    ("Sixty people attended the summer gathering.", "event_attendance"),
    ("We host 15 volunteers each season.", "volunteer"),
    ("The association employs four staff.", "employee"),
    ("We have 30 guests in the accommodation.", "guest"),
    ("The cooperative has 45 members.", "member"),
])
def test_population_roles_are_read_from_the_sentence(sentence, expected):
    assert roles.classify_population(sentence).role == expected


@pytest.mark.parametrize("sentence,expected", [
    ("We cultivate four hectares of market garden.", "cultivated"),
    ("The property is 134 hectares in total.", "total_holding"),
    ("22 hectares are under restoration.", "restoration"),
    ("We actively manage 15 hectares.", "managed"),
    ("The leased parcel is eight hectares.", "leased"),
    ("The food forest covers three hectares.", "forest"),
])
def test_area_roles_are_read_from_the_sentence(sentence, expected):
    assert roles.classify_area(sentence).role == expected


@pytest.mark.parametrize("sentence,expected", [
    ("The community was founded in 1985.", "founding"),
    ("The land was bought in 1987.", "land_acquisition"),
    ("The first residents moved in during 1988.", "first_residence"),
    ("We first planted the terraces in 1992.", "intervention_onset"),
    ("This article was published in 2019.", "publication"),
    ("Archived snapshot captured on 2009-04-17.", "archive_snapshot"),
])
def test_date_roles_are_read_from_the_sentence(sentence, expected):
    assert roles.classify_date(sentence).role == expected


def test_a_publication_date_may_never_become_an_intervention_date():
    """Named in §108 as something the final audit must confirm never happened."""
    allowed, reason = roles.may_write("date_intervention_onset", "publication")
    assert not allowed
    assert "property of the source" in reason


def test_the_nearer_marker_wins_when_a_sentence_carries_two():
    sentence = "The 134-hectare property includes 4 hectares of market garden."
    near_total = roles.classify_area(sentence, position=sentence.index("134"))
    near_garden = roles.classify_area(sentence, position=sentence.index("4 hectares"))
    assert near_total.role == "total_holding"
    assert near_garden.role == "cultivated"


def test_a_figure_is_qualified_by_what_follows_it():
    """A quantity is described by what comes after it, in every language here:
    "4 hectares of market garden", "4 hectares de maraîchage"."""
    sentence = "The property covers 4 hectares of market garden."
    verdict = roles.classify_area(sentence, position=sentence.index("4 hectares"))
    assert verdict.role == "cultivated", (
        "'property' came earlier in the sentence, but 'market garden' is what "
        "the four hectares actually are")


def test_two_markers_at_the_same_distance_are_ambiguous_not_guessed():
    verdict = roles.classify_area("4 ha forest restored", position=0)
    assert verdict.role == roles.UNCLASSIFIED
    assert "a human should read it" in verdict.reason


def test_a_sentence_with_no_marker_is_unclassified():
    verdict = roles.classify_population("There are 40 of them.")
    assert verdict.role == roles.UNCLASSIFIED
    assert not verdict.resolved


def test_a_field_with_no_role_is_left_alone():
    allowed, _ = roles.may_write("e1_pathway", None)
    assert allowed, "only role-bearing fields may be refused on role grounds"


def test_a_marker_containing_regex_characters_does_not_explode():
    """The vocabularies are literal phrases; one stray bracket must not become a
    syntax error in the middle of a crawl."""
    verdict = roles.classify("area", "we manage 4 ha (approx.)",
                             vocabulary={"managed": ("manage", "(approx.)")})
    assert verdict.role == "managed"
