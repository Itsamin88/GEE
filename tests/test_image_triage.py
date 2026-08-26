"""Image triage: what gets downloaded, what does not, and what it may evidence.

Brief §40. Two things are being defended here, and they pull in different
directions. The crawl must not spend an afternoon downloading a photo gallery,
and it must not throw away the site plan that was sitting in the middle of it.

The third, which matters more than either: a photograph is never a practice code
(register v2.4 rule 12). Priority decides what is fetched; it says nothing about
what an image proves.
"""

from __future__ import annotations

import pytest

from dcr.images.classify import DECORATIVE, LIKELY, POSSIBLE, classify_image
from dcr.images.triage import (DUPLICATE, HIGH, LOW, MEDIUM, ImageCandidate,
                               TriageLedger, priority_of, rank_of)


@pytest.fixture()
def ledger(db, community):
    return TriageLedger(db, community, run_id="IC001-RUN001")


def candidate(url: str, **kwargs) -> ImageCandidate:
    return ImageCandidate(original_url=url, page_url="https://example.org/page", **kwargs)


def triage_one(ledger, lexicon, cand: ImageCandidate) -> ImageCandidate:
    return ledger.triage([cand], lexicon=lexicon)[0]


# ---------------------------------------------------------------------------
# §40 — the images that must be selected
# ---------------------------------------------------------------------------
def test_a_research_map_is_selected(ledger, lexicon):
    result = triage_one(ledger, lexicon, candidate(
        "https://example.org/img/carte-des-parcelles.jpg",
        alt_text="Carte des parcelles cultivées",
        caption="Carte du site montrant les parcelles",
        width=1400, height=900))
    assert result.priority == HIGH
    assert result.classification.image_type == "map"


def test_a_site_plan_is_selected(ledger, lexicon):
    result = triage_one(ledger, lexicon, candidate(
        "https://example.org/uploads/master-plan-2016.png",
        alt_text="Site plan", caption="Master plan of the ecovillage, 2016",
        width=2000, height=1400))
    assert result.priority == HIGH
    assert result.classification.image_type == "site plan"
    assert result.classification.image_date == "2016"


def test_a_dated_intervention_image_is_selected(ledger, lexicon):
    result = triage_one(ledger, lexicon, candidate(
        "https://example.org/photos/DSC_0891.jpg",
        caption="In 2014 we planted 400 trees along the northern hedge.",
        surrounding_text="In 2014 we planted 400 trees along the northern hedge.",
        width=1200, height=800))
    assert result.priority in (HIGH, MEDIUM)
    assert result.classification.image_date == "2014"
    assert result.classification.documentary_text_support != "NOT FOUND"


def test_a_caption_bearing_image_outranks_a_bare_one(ledger, lexicon):
    described = triage_one(ledger, lexicon, candidate(
        "https://example.org/a/swale-construction.jpg",
        caption="Digging the swales on the eastern slope, spring 2015",
        width=1600, height=1000))
    bare = triage_one(ledger, lexicon, candidate(
        "https://example.org/a/IMG_2231.jpg", width=1600, height=1000))
    assert rank_of(described) > rank_of(bare)


def test_a_figure_in_a_document_is_high_priority(ledger, lexicon):
    result = triage_one(ledger, lexicon, candidate(
        "https://example.org/report.pdf#image3",
        origin="document", filename="fig3.png",
        caption="Figure 3. Land-use map of the holding",
        document_title="Annual report 2019",
        page_number=12, figure_number="3",
        width=1400, height=1000))
    assert result.priority == HIGH
    assert result.figure_number == "3"


# ---------------------------------------------------------------------------
# §40 — the images that must not be downloaded
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("url,alt", [
    ("https://example.org/logo.svg", "logo"),
    ("https://example.org/img/icon-facebook.png", "facebook icon"),
    ("https://example.org/team/portrait-marie.jpg", "portrait of Marie"),
])
def test_decorative_images_are_rejected(ledger, lexicon, url, alt):
    result = triage_one(ledger, lexicon, candidate(url, alt_text=alt,
                                                   width=200, height=200))
    assert result.priority == LOW


def test_a_generic_landscape_without_context_is_not_high_priority(ledger, lexicon):
    result = triage_one(ledger, lexicon, candidate(
        "https://example.org/gallery/sunset-over-the-valley.jpg",
        alt_text="sunset over the valley", width=1600, height=900))
    assert result.priority != HIGH


def test_a_tiny_image_with_a_promising_name_is_still_decoration(ledger, lexicon):
    result = triage_one(ledger, lexicon, candidate(
        "https://example.org/icons/map-pin.png", alt_text="map", width=24, height=24))
    assert result.priority == LOW


# ---------------------------------------------------------------------------
# §40 — duplicates
# ---------------------------------------------------------------------------
def test_the_same_address_twice_in_one_page_is_a_duplicate(ledger, lexicon):
    url = "https://example.org/img/site-plan.jpg"
    first, second = ledger.triage(
        [candidate(url, caption="Site plan", width=1200, height=900),
         candidate(url, caption="Site plan", width=1200, height=900)],
        lexicon=lexicon)
    assert first.priority == HIGH
    assert second.priority == DUPLICATE


def test_an_image_already_triaged_is_not_triaged_again(ledger, lexicon, db, community):
    url = "https://example.org/img/gallery-1.jpg"
    first = triage_one(ledger, lexicon, candidate(url, caption="Planting day 2015",
                                                  width=1200, height=800))
    ledger.record(first, decision="downloaded", sha256="abc123", image_id="IC001-IMG0001")

    # A second page links the same gallery image.
    again = triage_one(ledger, lexicon, candidate(url, caption="Planting day 2015",
                                                  width=1200, height=800))
    assert again.priority == DUPLICATE


def test_a_duplicate_is_recognised_across_processes(db, community, lexicon):
    """A resumed run must not re-download what the first run already took."""
    url = "https://example.org/img/plan.jpg"
    first = TriageLedger(db, community)
    result = first.triage([candidate(url, caption="Site plan", width=1200, height=900)],
                          lexicon=lexicon)[0]
    first.record(result, decision="downloaded", sha256="deadbeef",
                 image_id="IC001-IMG0001")

    resumed = TriageLedger(db, community)          # a fresh object, as after a restart
    again = resumed.triage([candidate(url, caption="Site plan", width=1200, height=900)],
                           lexicon=lexicon)[0]
    assert again.priority == DUPLICATE
    # The ledger maps content hash -> candidate, which is what the crawler
    # needs in order to skip the download entirely.
    assert resumed.is_duplicate_hash("deadbeef") == result.candidate_id


# ---------------------------------------------------------------------------
# ordering: the best candidates are fetched first (§5)
# ---------------------------------------------------------------------------
def test_candidates_come_back_best_first(ledger, lexicon):
    triaged = ledger.triage([
        candidate("https://example.org/logo.png", alt_text="logo", width=100, height=40),
        candidate("https://example.org/sunset.jpg", alt_text="sunset",
                  width=1200, height=800),
        candidate("https://example.org/plan-de-masse.jpg",
                  caption="Plan de masse du site, 2017", width=1800, height=1200),
        candidate("https://example.org/planting.jpg",
                  caption="We planted the food forest in 2016", width=1200, height=800),
    ], lexicon=lexicon)
    priorities = [c.priority for c in triaged]
    assert priorities == sorted(priorities, key=lambda p: {HIGH: 0, MEDIUM: 1,
                                                           LOW: 2, DUPLICATE: 3}[p])
    # The published plan and the dated planting caption are both worth fetching;
    # the logo and the untitled sunset are not.
    kept = {c.original_url for c in triaged if c.priority in (HIGH, MEDIUM)}
    assert any("plan-de-masse" in url for url in kept)
    assert any("planting" in url for url in kept)
    assert triaged[-1].priority == LOW
    assert "logo" in triaged[-1].original_url or "sunset" in triaged[-1].original_url


# ---------------------------------------------------------------------------
# §40 — provenance is preserved for everything seen, kept or not
# ---------------------------------------------------------------------------
def test_a_skipped_candidate_keeps_its_metadata(ledger, lexicon, db, community):
    """A gallery caption can carry a date the page text never gives (register §3)."""
    result = triage_one(ledger, lexicon, candidate(
        "https://example.org/gallery/party.jpg",
        alt_text="summer party", caption="Summer party, 2011",
        page_heading="Gallery", width=900, height=600))
    ledger.record(result, decision="skipped_low_priority", reason="decorative")

    row = db.query_one("SELECT * FROM image_candidates WHERE community_id=?", (community,))
    assert row["decision"] == "skipped_low_priority"
    assert row["caption"] == "Summer party, 2011"
    assert row["page_url"] == "https://example.org/page"
    assert row["image_date"] == "2011"
    assert row["decision_reason"] == "decorative"


def test_a_downloaded_candidate_records_the_full_provenance(ledger, lexicon, db, community):
    result = triage_one(ledger, lexicon, candidate(
        "https://example.org/report.pdf#image1",
        origin="document", filename="figure1.png",
        caption="Figure 1. Restoration plan for the eastern parcel",
        document_title="Restoration report 2018", page_number=4,
        figure_number="1", extraction_method="pypdf:embedded",
        source_id="IC001-02", document_id="IC001-D001",
        source_class="S1", independence_group="G1",
        width=1600, height=1200))
    ledger.record(result, decision="downloaded", image_id="IC001-IMG0007",
                  sha256="feed0001")

    row = db.query_one("SELECT * FROM image_candidates WHERE image_id='IC001-IMG0007'")
    for column, expected in [
        ("source_id", "IC001-02"), ("document_id", "IC001-D001"),
        ("page_number", 4), ("figure_number", "1"),
        ("extraction_method", "pypdf:embedded"), ("source_class", "S1"),
        ("independence_group", "G1"), ("sha256", "feed0001"),
        ("origin", "document"), ("priority", HIGH), ("decision", "downloaded"),
    ]:
        assert row[column] == expected, column
    assert row["possible_fields"]
    assert row["relevance_reason"]


# ---------------------------------------------------------------------------
# rule 12: a photograph is never a practice code
# ---------------------------------------------------------------------------
def test_a_photograph_of_green_rows_evidences_no_practice(ledger, lexicon):
    """Register rule 12, stated as a test."""
    result = triage_one(ledger, lexicon, candidate(
        "https://example.org/photos/rows.jpg",
        alt_text="green rows of vegetables", width=1600, height=1000))
    classification = result.classification
    assert classification.documentary_text_support == "NOT FOUND"
    assert "practice" not in classification.visual_evidence_allowed.lower()


def test_a_caption_that_states_the_practice_is_what_licenses_a_claim(ledger, lexicon):
    result = triage_one(ledger, lexicon, candidate(
        "https://example.org/photos/rows.jpg",
        caption="We planted the alley crops between the fruit trees in 2015.",
        surrounding_text="We planted the alley crops between the fruit trees in 2015.",
        width=1600, height=1000))
    assert result.classification.documentary_text_support != "NOT FOUND"
    assert "planted" in result.classification.documentary_text_support


def test_priority_never_claims_the_image_proves_anything(ledger, lexicon):
    """HIGH means 'fetch first', not 'evidenced'."""
    result = triage_one(ledger, lexicon, candidate(
        "https://example.org/img/aerial-2019.jpg",
        alt_text="aerial view", caption="Aerial view of the site, 2019",
        width=2400, height=1600))
    assert result.priority == HIGH
    allowed = result.classification.visual_evidence_allowed
    assert "V4 visual documentation" in allowed
    assert result.classification.documentary_text_support == "NOT FOUND"


# ---------------------------------------------------------------------------
# regression: a lexicon pattern must not be broken by how the YAML is wrapped
# ---------------------------------------------------------------------------
def test_no_lexicon_pattern_is_folded_across_lines(lexicon):
    """YAML folds a wrapped quoted scalar into a space.

    That silently turned `|plan.?de.?masse|` into `| plan.?de.?masse|`, so a
    French caption *beginning* "Plan de masse" scored nothing and the site plan
    behind it was never downloaded. The alternation must stay on one line.
    """
    for group, patterns in lexicon.get("image_relevance", {}).items():
        for pattern in patterns:
            assert "\n" not in pattern, f"{group}: {pattern!r} is wrapped across lines"
            assert "| " not in pattern, f"{group}: {pattern!r} has a space after a pipe"
            assert " |" not in pattern, f"{group}: {pattern!r} has a space before a pipe"


def test_a_french_site_plan_caption_is_matched_from_its_first_word(ledger, lexicon):
    result = triage_one(ledger, lexicon, candidate(
        "https://example.org/media/pdm.jpg",
        caption="Plan de masse du site, 2017", width=1800, height=1200))
    assert result.priority == HIGH
    assert result.classification.relevance_class == LIKELY


def test_a_folded_pattern_would_still_match_if_one_slipped_through(ledger):
    """The compiler tolerates the mistake even where the lexicon does not."""
    folded = {"image_relevance": {"strong": ["site.?plan|\n       plan.?de.?masse"],
                                  "moderate": [], "decorative": []}}
    result = classify_image(url="https://example.org/x.jpg",
                            caption="Plan de masse du site", width=1200, height=900,
                            lexicon=folded)
    assert result.relevance_class == LIKELY
