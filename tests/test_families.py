"""Translations and re-issues of one report are one report (brief §20, §28).

Two things go wrong when they are not recognised. The obvious one is cost: three
copies of a forty-page annual report is three deep parses for one report's worth
of evidence. The one that matters more is that three copies of one document
would count as three independent sources, which would breach the corroboration
rule the whole protocol rests on.
"""

from __future__ import annotations

import pytest

from dcr.evidence.families import (CERTAIN, DocumentRef, choose_primary, group,
                                   language_tag, normalised_stem, parse_plan,
                                   relate, review_cases, savings, stated_year)


def doc(document_id, url, **kwargs):
    return DocumentRef(document_id=document_id, url=url,
                       filename=kwargs.pop("filename", url.rsplit("/", 1)[-1]),
                       **kwargs)


# ---------------------------------------------------------------------------
# reading a filename
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name,expected", [
    ("rapport_annuel_2019_DE.pdf", "German"),
    ("annual-report-2019-en.pdf", "English"),
    ("relatorio_2019_PT.pdf", "Portuguese"),
    ("https://x.org/en/reports/annual-2019.pdf", "English"),
    ("jahresbericht_2019_deutsch.pdf", "German"),
    ("report-2019.pdf", None),
])
def test_a_declared_language_is_recognised(name, expected):
    assert language_tag(name) == expected


def test_de_luxe_is_not_german():
    """Bounded by separators, or every French filename becomes German."""
    assert language_tag("report_deluxe_2019.pdf") is None


@pytest.mark.parametrize("name,expected", [
    ("rapport_annuel_2019_DE_v2.pdf", "rapport annuel"),
    ("rapport-annuel-2019-en.pdf", "rapport annuel"),
    ("Annual Report 2019 (final).pdf", "annual report"),
    ("annual_report_2019_web_lowres.pdf", "annual report"),
])
def test_versions_and_tags_are_stripped_from_the_stem(name, expected):
    assert normalised_stem(name) == expected


def test_the_year_is_kept_separately():
    assert stated_year("rapport_annuel_2019_DE.pdf") == 2019
    assert stated_year("report.pdf", "Annual Report 2016") == 2016


# ---------------------------------------------------------------------------
# what makes two documents one
# ---------------------------------------------------------------------------
def test_the_same_bytes_are_certainly_the_same_document():
    score, reasons = relate(
        doc("D1", "https://a.org/report.pdf", content_hash="abc"),
        doc("D2", "https://b.org/mirror/report.pdf", content_hash="abc"))
    assert score == 1.0
    assert "identical content hash" in reasons[0]


def test_three_translations_of_one_report_are_one_family():
    documents = [
        doc("D1", "https://x.org/rapport_annuel_2019_FR.pdf", bytes_len=1_020_000, pages=42),
        doc("D2", "https://x.org/rapport_annuel_2019_EN.pdf", bytes_len=1_010_000, pages=42),
        doc("D3", "https://x.org/rapport_annuel_2019_DE.pdf", bytes_len=1_050_000, pages=42),
    ]
    families = group(documents)
    assert len(families) == 1
    assert families[0].size == 3


def test_two_different_years_are_never_one_family():
    documents = [
        doc("D1", "https://x.org/annual_report_2018.pdf", bytes_len=900_000, pages=40),
        doc("D2", "https://x.org/annual_report_2019.pdf", bytes_len=910_000, pages=40),
    ]
    families = group(documents)
    assert len(families) == 2, (
        "the 2018 report and the 2019 report are two documents however alike "
        "their filenames")


def test_unrelated_documents_are_left_alone():
    documents = [
        doc("D1", "https://x.org/water-management-plan.pdf", bytes_len=300_000),
        doc("D2", "https://x.org/newsletter-spring.pdf", bytes_len=120_000),
        doc("D3", "https://x.org/land-use-map.pdf", bytes_len=2_400_000),
    ]
    families = group(documents)
    assert len(families) == 3
    assert all(family.size == 1 for family in families)


# ---------------------------------------------------------------------------
# what a family is for
# ---------------------------------------------------------------------------
def test_only_one_copy_is_deep_parsed():
    documents = [
        doc("D1", "https://x.org/rapport_2019_PT.pdf", bytes_len=1_000_000, pages=42),
        doc("D2", "https://x.org/rapport_2019_EN.pdf", bytes_len=1_010_000, pages=42),
        doc("D3", "https://x.org/rapport_2019_DE.pdf", bytes_len=1_005_000, pages=42),
    ]
    plan = parse_plan(group(documents))
    assert sorted(plan.values()) == ["deep", "metadata", "metadata"]


def test_the_language_the_crawler_reads_best_becomes_the_primary():
    members = [
        doc("D1", "https://x.org/r_2019_pt.pdf", bytes_len=1_000_000),
        doc("D2", "https://x.org/r_2019_en.pdf", bytes_len=900_000),
    ]
    assert choose_primary(members).document_id == "D2"


def test_a_copy_with_a_different_page_count_is_still_opened():
    """It is not a translation; it is another document named like one."""
    documents = [
        doc("D1", "https://x.org/rapport_2019_EN.pdf", bytes_len=1_000_000, pages=42),
        doc("D2", "https://x.org/rapport_2019_DE.pdf", bytes_len=1_400_000, pages=96),
    ]
    plan = parse_plan(group(documents))
    assert "deep-differs" in plan.values() or list(plan.values()).count("deep") == 2


def test_a_family_grouped_on_weak_evidence_is_flagged_for_a_human():
    documents = [
        doc("D1", "https://x.org/report.pdf", bytes_len=500_000),
        doc("D2", "https://x.org/report-de.pdf", bytes_len=505_000),
    ]
    families = group(documents)
    if families[0].size > 1 and families[0].uncertain:
        cases = review_cases(families)
        assert cases and cases[0]["category"] == "document_family"
        assert "cannot corroborate each other" in cases[0]["detail"]


def test_the_saving_is_reported():
    documents = [
        doc("D1", "https://x.org/rapport_2019_PT.pdf", bytes_len=1_000_000, pages=42),
        doc("D2", "https://x.org/rapport_2019_EN.pdf", bytes_len=1_010_000, pages=42),
        doc("D3", "https://x.org/water-plan.pdf", bytes_len=300_000, pages=8),
    ]
    numbers = savings(group(documents))
    assert numbers["documents"] == 3
    assert numbers["deep_parsed"] == 2
    assert numbers["recorded_from_metadata"] == 1


def test_grouping_four_hundred_documents_is_cheap():
    """O(n²) on metadata only. If this ever gets slow it is doing real work,
    which would defeat the point of deciding BEFORE parsing."""
    import time

    documents = [doc(f"D{i}", f"https://x.org/paper-{i}-2019.pdf",
                     bytes_len=100_000 + i, pages=10 + (i % 30))
                 for i in range(400)]
    started = time.monotonic()
    families = group(documents)
    assert time.monotonic() - started < 5.0
    assert families
