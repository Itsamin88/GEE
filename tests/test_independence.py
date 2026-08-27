"""The independence rule: ten copied pages are not ten sources."""

from __future__ import annotations

from dcr.evidence.independence import (
    IndependenceResolver, compare, containment, editorial_signals_present, hamming,
    jaccard, shingles, simhash, tokenize,
)

SITE = ("We are an ecovillage founded in 1998. "
        "We planted a food forest of four hectares and restored the meadow. " * 20)
NEAR_COPY = ("We are an ecovillage founded in 1998. "
             "We planted a food forest of four hectares and restored the meadow. " * 18)
THESIS = ("This dissertation examines agroecological transition at a French intentional "
          "community using participant observation across two field seasons. " * 20)


def test_simhash_distance_tracks_similarity():
    a, b, c = (simhash(tokenize(t)) for t in (SITE, NEAR_COPY, THESIS))
    assert hamming(a, b) < hamming(a, c)


def test_jaccard_and_containment():
    a, b = shingles(tokenize(SITE)), shingles(tokenize(NEAR_COPY))
    assert jaccard(a, b) > 0.8
    assert containment(a, b) > 0.8
    assert jaccard(a, shingles(tokenize(THESIS))) < 0.1


def test_compare_identifies_a_copy():
    resolver = IndependenceResolver()
    verdict = compare(resolver.profile("P1", "S1", SITE), resolver.profile("P2", "S2", NEAR_COPY))
    assert verdict.is_copy
    assert verdict.detail


def test_four_addresses_of_one_community_are_one_group():
    resolver = IndependenceResolver()
    for source_id, platform in (("S1", "own website"), ("S2", "Facebook"),
                                ("S3", "Instagram"), ("S4", "YouTube")):
        resolver.assign(source_id=source_id, platform_type=platform, source_class="S4",
                        registrable="x.org", profile=None, community_domains={"x.org"})
    assert resolver.group_count() == 1


def test_directory_copy_shares_the_website_group_but_a_thesis_does_not():
    resolver = IndependenceResolver()
    resolver.assign(source_id="S1", platform_type="own website", source_class="S4",
                    registrable="x.org", profile=resolver.profile("P1", "S1", SITE),
                    community_domains={"x.org"})
    listing = resolver.assign(
        source_id="S2", platform_type="directory listing", source_class="S3",
        registrable="ecovillage.org", profile=resolver.profile("P2", "S2", NEAR_COPY),
        community_domains={"x.org"}, text=NEAR_COPY)
    thesis = resolver.assign(
        source_id="S3", platform_type="other", source_class="S1",
        registrable="theses.fr", profile=resolver.profile("P3", "S3", THESIS),
        community_domains={"x.org"}, text=THESIS)
    assert listing.group == "G1"
    assert thesis.group != "G1"
    assert resolver.group_count() == 2


def test_press_release_reprint_is_not_independent():
    resolver = IndependenceResolver({"press_release_markers": ["press release"]})
    resolver.assign(source_id="S1", platform_type="own website", source_class="S4",
                    registrable="x.org", profile=resolver.profile("P1", "S1", SITE),
                    community_domains={"x.org"})
    reprint = resolver.assign(
        source_id="S2", platform_type="news outlet", source_class="S6",
        registrable="news.org", profile=resolver.profile("P2", "S2", "press release " + SITE),
        community_domains={"x.org"}, text="press release " + SITE)
    assert reprint.group == "G1"


def test_editorial_signals_detected():
    assert editorial_signals_present("Our reviewer visited the site in 2019.")
    assert not editorial_signals_present("We are a community in the mountains.")
