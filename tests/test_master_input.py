"""The 212-community master input file, checked as data and as crawler input.

Two questions, and the file is only finished when both answer yes.

**Is it faithful?** Every community in the researcher's original export is still
here, every coordinate that export gave is still recoverable, every address is
byte-identical to the one discovery found, and nothing claims a verification
that was not performed.

**Can the crawler eat it?** Not "does it look like a CSV" but: does
`read_community_file`, the function the run actually calls, return 212
communities with their addresses intact and nothing spurious in the queue.

The original export is a fixture here, not an input to be trusted: the tests
read it to prove the master file preserved it.
"""

from __future__ import annotations

import collections
import csv
import io
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from dcr.orchestrator.session import read_community_file

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / "master_input" / "Paper1_Final_Only Ecovillages.csv"
MASTER = ROOT / "master_input" / "Paper1_Final_Only_Ecovillages_Master_Input.csv"
FINAL_COORDINATES = ROOT / "master_input" / "pipeline" / "final_coordinates.csv"

GEN_GLOBAL_URL = "https://ecovillage.org"
URL_DELIMITER = " | "
EXPECTED_COMMUNITIES = 212
EXPECTED_SOURCE_ROWS = 314

#: register v2.4 / workbook v6 Reference_Codes
SOURCE_CLASSES = {"S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"}
PLATFORM_TYPES = {
    "own website", "secondary or former website", "Facebook", "Instagram",
    "YouTube", "Vimeo", "blog platform", "directory listing", "crowdfunding",
    "LinkedIn", "booking or hosting", "news outlet", "other",
}
GEN_STATUSES = {
    "NOT_FOUND", "NOT_SEARCHED", "VERIFIED_COMMUNITY_SOURCE",
    "VERIFIED_COMMUNITY_SOURCE_LEGACY_HOST",
    "VERIFIED_COMMUNITY_SOURCE_SUBPAGE_ONLY",
    "VERIFIED_COMMUNITY_SOURCE_PARENT_ONLY",
    "VERIFIED_COMMUNITY_SOURCE_IDENTITY_UNCERTAIN",
}


@pytest.fixture(scope="module")
def rows() -> list[dict[str, str]]:
    text = MASTER.read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(text)))


@pytest.fixture(scope="module")
def original() -> list[dict[str, str]]:
    text = ORIGINAL.read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(text)))


# ---------------------------------------------------------------------------
# The file as a file
# ---------------------------------------------------------------------------
def test_utf8_round_trip_without_a_bom():
    raw = MASTER.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "a BOM breaks some CSV readers"
    text = raw.decode("utf-8")
    assert text.encode("utf-8") == raw


def test_every_row_has_the_same_number_of_fields(rows):
    header = next(csv.reader(io.StringIO(MASTER.read_text(encoding="utf-8"))))
    widths = {len(record) for record in
              csv.reader(io.StringIO(MASTER.read_text(encoding="utf-8")))}
    assert widths == {len(header)}, f"ragged rows: widths {sorted(widths)}"
    assert len(rows) == EXPECTED_COMMUNITIES


def test_no_column_name_would_be_swallowed_as_an_address(rows):
    """A column called `url_count` must not put its value in the crawl queue.

    The reader treats `urls`, `url` and `url<digits>` as addresses. Any other
    column whose name begins with "url" is a trap for a future editor, so the
    schema simply does not contain one.
    """
    from dcr.orchestrator.session import _is_url_column

    address_columns = [c for c in rows[0] if _is_url_column(c)]
    assert address_columns == ["urls"]
    lookalikes = [c for c in rows[0] if c.startswith("url") and c != "urls"]
    assert lookalikes == [], f"columns that invite the old bug back: {lookalikes}"


def test_pandas_reads_it_with_the_same_shape(rows):
    pd = pytest.importorskip("pandas")
    frame = pd.read_csv(MASTER, dtype=str, keep_default_na=False)
    assert len(frame) == EXPECTED_COMMUNITIES
    assert list(frame.columns) == list(rows[0].keys())


# ---------------------------------------------------------------------------
# Faithfulness to the original export
# ---------------------------------------------------------------------------
def test_every_original_community_survived(rows, original):
    originals = {r["Ecovillage_Name"] for r in original}
    kept = {r["community_name_original"] for r in rows}
    assert len(originals) == EXPECTED_COMMUNITIES
    assert kept == originals, f"lost or invented: {originals ^ kept}"


def test_the_coordinates_are_the_researchers_verified_ones(rows):
    """The file ships exactly the latitude and longitude the researcher returned.

    The export gave four geocoder candidates for the last 34 communities and
    chose none. The researcher checked those by hand and sent back one pair per
    community; those are authoritative, and this build may not alter, round or
    second-guess them. Compared against the researcher's own file, not against
    anything this pipeline derived.
    """
    verified = {r["community_id"]: (r["latitude"], r["longitude"])
                for r in csv.DictReader(
                    FINAL_COORDINATES.open(encoding="utf-8-sig", newline=""))}
    assert len(verified) == EXPECTED_COMMUNITIES
    for row in rows:
        assert row["community_id"] in verified, row["community_id"]
        lat, lon = verified[row["community_id"]]
        assert row["latitude"] == lat, row["community_id"]
        assert row["longitude"] == lon, row["community_id"]


def test_one_coordinate_pair_per_community_and_no_candidate_columns(rows):
    """The multi-candidate machinery is gone, not merely unused.

    Nine columns existed only to carry the export's unresolved geocoder
    candidates. With verified coordinates in hand they are noise in a crawler
    input file, and leaving them in place invites a reader to trust a stale
    `coordinate_status` that no longer describes anything.
    """
    retired = {"coordinate_primary_rule", "coordinate_candidate_count",
               "coordinate_candidate_spread_km", "coordinate_candidates",
               "coordinate_status", "latitude_as_exported",
               "longitude_as_exported", "coordinate_confidence",
               "coordinate_evidence"}
    present = set(rows[0])
    assert not (retired & present), sorted(retired & present)
    for row in rows:
        assert row["coordinate_source"] in {
            "researcher_verified", "source_export_single_row"}, row["community_id"]


def test_the_communities_whose_coordinates_were_checked_say_so(rows):
    """Provenance survives the cleanup: 34 rows record a human verification."""
    verified = [r for r in rows if r["coordinate_source"] == "researcher_verified"]
    assert len(verified) == 34
    # They are the tail of the file - the block the export mis-geocoded.
    assert {r["community_id"] for r in verified} == {
        f"IC{n:03d}" for n in range(179, 213)}


def test_coordinates_parse_and_are_on_the_planet(rows):
    for row in rows:
        latitude, longitude = float(row["latitude"]), float(row["longitude"])
        assert -90 <= latitude <= 90 and -180 <= longitude <= 180, row["community_id"]


def test_repaired_names_are_flagged_and_the_original_kept(rows):
    for row in rows:
        repaired = row["community_name_original"] != row["community_name_normalized"]
        assert row["name_repair_applied"] == ("yes" if repaired else "no")
        assert row["community_name_normalized"] == row["name"]
    assert sum(1 for r in rows if r["name_repair_applied"] == "yes") == 10


def test_community_ids_are_unique_and_sequential(rows):
    ids = [r["community_id"] for r in rows]
    assert ids == [f"IC{n:03d}" for n in range(1, EXPECTED_COMMUNITIES + 1)]


# ---------------------------------------------------------------------------
# The Global Ecovillage Network requirement
# ---------------------------------------------------------------------------
def test_the_fixed_gen_global_url_is_on_every_single_row(rows):
    for row in rows:
        assert row["gen_global_url"] == GEN_GLOBAL_URL
        assert row["gen_global_status"] == "FIXED_GLOBAL_SOURCE"
        assert GEN_GLOBAL_URL in row["urls"].split(URL_DELIMITER)


def test_gen_global_is_distinguishable_from_a_community_profile(rows):
    for row in rows:
        assert row["gen_community_status"] in GEN_STATUSES, row["community_id"]
        if row["gen_community_status"].startswith("VERIFIED"):
            assert row["gen_community_url"], row["community_id"]
            assert row["gen_community_url"] != GEN_GLOBAL_URL
        else:
            assert row["gen_community_url"] == "", row["community_id"]


def test_no_community_gen_url_was_invented(rows):
    """Every GEN community URL must be a real path found by search, and each
    must carry the evidence line that found it (brief §36)."""
    for row in rows:
        url = row["gen_community_url"]
        if not url:
            continue
        host = urlsplit(url).hostname or ""
        assert host == "ecovillage.org" or host.endswith(".ecovillage.org"), \
            f"{row['community_id']}: not a GEN host: {url}"
        assert url.rstrip("/") != GEN_GLOBAL_URL
        assert len(row["gen_evidence_note"]) > 30, row["community_id"]


def test_absence_of_a_gen_page_is_never_dressed_up_as_a_search(rows):
    """A community nobody searched for must not read like one with no page."""
    for row in rows:
        if row["discovery_status"] == "PENDING":
            assert row["gen_community_status"] == "NOT_SEARCHED"
            assert row["gen_verification_method"] == "none"
            assert "gen_not_searched" in row["review_reasons"]
        else:
            assert row["gen_community_status"] != "NOT_SEARCHED"


def test_gen_never_counts_as_an_independent_second_voice(rows):
    """The global page and any community profile share one independence group."""
    for row in rows:
        assert row["gen_independence_group"] == "G1"
        for source in json.loads(row["seed_sources_json"]):
            if "ecovillage.org" in source["url"]:
                assert source["independence_group"] == "G1", row["community_id"]


# ---------------------------------------------------------------------------
# The seed source set
# ---------------------------------------------------------------------------
def test_url_list_reconstructs_exactly_from_the_structured_column(rows):
    for row in rows:
        listed = row["urls"].split(URL_DELIMITER)
        structured = [s["url"] for s in json.loads(row["seed_sources_json"])]
        assert sorted(listed) == sorted(structured), row["community_id"]
        assert len(listed) == len(set(listed)), f"duplicate address in {row['community_id']}"
        assert int(row["seed_url_count"]) == len(listed)


def test_every_address_is_absolute_and_unmangled(rows):
    for row in rows:
        for url in row["urls"].split(URL_DELIMITER):
            assert url == url.strip()
            assert url.startswith(("http://", "https://")), url
            assert " " not in url, f"a space would split this address: {url!r}"


def test_addresses_with_commas_and_query_strings_survive(rows):
    """The delimiter must not be something URLs contain."""
    tricky = [u for r in rows for u in r["urls"].split(URL_DELIMITER)
              if "," in u or "?" in u]
    assert tricky, "no comma/query-string address in the file to prove the point"
    for url in tricky:
        assert URL_DELIMITER not in url


def test_every_address_carries_a_class_a_platform_and_a_group(rows):
    for row in rows:
        for source in json.loads(row["seed_sources_json"]):
            assert source["source_class"] in SOURCE_CLASSES, source
            assert source["platform_type"] in PLATFORM_TYPES, source
            assert source["independence_group"].startswith("G"), source
            assert source["confidence"] in {"HIGH", "MEDIUM", "LOW"}, source
            assert source["verification"] in {"search_index", "fixed_global_source"}
            assert 0.0 <= float(source["quality_score"]) <= 1.0


def test_ranking_is_descending_by_quality_with_gen_global_last(rows):
    for row in rows:
        urls = row["urls"].split(URL_DELIMITER)
        assert urls[-1] == GEN_GLOBAL_URL, row["community_id"]
        by_url = {s["url"]: float(s["quality_score"])
                  for s in json.loads(row["seed_sources_json"])}
        scores = [by_url[u] for u in urls[:-1]]
        assert scores == sorted(scores, reverse=True), row["community_id"]


def test_independence_groups_are_counted_not_urls(rows):
    for row in rows:
        sources = json.loads(row["seed_sources_json"])
        groups = {s["independence_group"] for s in sources
                  if s["url"] != GEN_GLOBAL_URL}
        assert int(row["independence_group_count"]) == len(groups or {"G1"})
        assert int(row["independence_group_count"]) <= int(row["seed_url_count"])


# ---------------------------------------------------------------------------
# Quality control, and honesty about what was not done
# ---------------------------------------------------------------------------
def test_country_is_present_or_the_row_says_why_not(rows):
    for row in rows:
        assert row["country"], row["community_id"]
        assert len(row["country_iso2"]) == 2 and len(row["country_iso3"]) == 3
        assert row["country_confidence"] in {"HIGH", "MEDIUM", "LOW"}
        if row["country_confidence"] != "HIGH":
            assert row["review_required"] == "yes", row["community_id"]


def test_country_is_written_one_way_only(rows):
    by_code: dict[str, set[str]] = {}
    for row in rows:
        by_code.setdefault(row["country_iso2"], set()).add(row["country"])
    mixed = {code: names for code, names in by_code.items() if len(names) > 1}
    assert not mixed, f"one country spelled several ways: {mixed}"


def test_ambiguous_rows_are_flagged_rather_than_quietly_resolved(rows):
    for row in rows:
        reasons = row["review_reasons"]
        assert (row["review_required"] == "yes") == bool(reasons), row["community_id"]
        if row["discovery_status"] == "PENDING":
            assert "discovery_pending" in reasons
        # The coordinates are settled, so no row may still be asking about them.
        assert "multiple_coordinate_candidates" not in reasons, row["community_id"]
        assert "coordinate_resolved_below_high" not in reasons, row["community_id"]


def test_pending_rows_still_carry_the_mandatory_seed_and_nothing_invented(rows):
    for row in (r for r in rows if r["discovery_status"] == "PENDING"):
        assert row["urls"] == GEN_GLOBAL_URL
        assert row["seed_url_count"] == "1"
        assert row["alternative_names"] == ""
        assert row["seed_url_verification_method"] == "none"


def test_completed_rows_record_how_their_addresses_were_verified(rows):
    for row in (r for r in rows if r["discovery_status"] == "COMPLETE"):
        assert row["seed_url_verification_method"] == "search_index"
        assert int(row["seed_url_count"]) >= 2
        assert row["community_identity_confidence"] in {"HIGH", "MEDIUM", "LOW"}


# ---------------------------------------------------------------------------
# The crawler's own reader — the compatibility that actually matters
# ---------------------------------------------------------------------------
def test_the_crawler_reads_all_212_communities(rows):
    entries = read_community_file(MASTER)
    assert len(entries) == EXPECTED_COMMUNITIES
    assert all(entry["name"] for entry in entries)
    assert {e["name"] for e in entries} == {r["name"] for r in rows}


def test_the_crawler_gets_every_address_and_only_addresses(rows):
    entries = {e["name"]: e for e in read_community_file(MASTER)}
    for row in rows:
        expected = row["urls"].split(URL_DELIMITER)
        assert entries[row["name"]]["urls"] == expected, row["community_id"]


def test_the_crawler_gets_coordinates_and_a_country_it_can_use(rows):
    from dcr.runner import _country_code

    entries = read_community_file(MASTER)
    for entry in entries:
        assert entry["latitude"] is not None and entry["longitude"] is not None
        assert entry["country"]
        assert _country_code(entry["country"]), \
            f"no ccTLD for {entry['country']!r}: the local-language sweep would skip it"


def test_the_run_mode_is_one_the_runner_understands(rows):
    from dcr.runner import MODE_STAGES

    entries = read_community_file(MASTER)
    assert {e["mode"] for e in entries} <= set(MODE_STAGES)


def test_the_plan_builder_sizes_and_orders_the_whole_cohort():
    from dcr.orchestrator.plan import build_plan

    entries = read_community_file(MASTER)
    plan = build_plan(entries, run_id="RTEST", output_root=Path("/tmp/dcr-test"),
                      mode="FULL")
    assert len(plan.jobs) == EXPECTED_COMMUNITIES
    assert len({job.site_id for job in plan.jobs}) == EXPECTED_COMMUNITIES
    assert all(job.urls for job in plan.jobs), "every community starts with an address"


def test_gen_addresses_are_classified_as_directories_not_websites():
    from dcr.orchestrator.plan import classify_address

    assert classify_address(GEN_GLOBAL_URL) == "directory"
    assert classify_address("https://ecovillage.org/project/tamera-0/") == "directory"


def test_the_original_export_would_now_load_too():
    """The researcher's own file names the column `Ecovillage_Name`.

    Before the alias existed this returned zero communities and said nothing,
    which is the failure mode most likely to waste a day.
    """
    entries = read_community_file(ORIGINAL)
    assert len(entries) == EXPECTED_SOURCE_ROWS
    assert entries[0]["name"] == "Soheili Village_Hara"


# ---------------------------------------------------------------------------
# The crawl policy: what the file tells the crawler to DO
# ---------------------------------------------------------------------------
def test_every_deep_crawl_target_is_a_bare_site_root(rows):
    """A whole-site walk has to start at the front door.

    Discovery recorded the single most useful page on each site, because that is
    what a ranked seed list wants - Tamera's water-retention-landscape page, not
    tamera.org. A crawler told to walk the whole site and handed that page
    starts three levels down and reaches the archive only by luck. So the deep
    targets are origins, and the specific pages stay in `urls`.
    """
    seen = 0
    for row in rows:
        for url in row["deep_crawl_urls"].split(URL_DELIMITER):
            if not url:
                continue
            seen += 1
            parts = urlsplit(url)
            assert parts.scheme in {"http", "https"}, url
            assert parts.netloc, url
            assert parts.path == "/", f"{url} is a page, not a site root"
            assert not parts.query and not parts.fragment, url
    assert seen >= 150, "almost every community has a site of its own"


def test_the_network_seed_is_never_walked_exhaustively(rows):
    """ecovillage.org is 212 communities' shared directory, not anyone's site.

    Walking it in full would crawl the whole Global Ecovillage Network once per
    community, and none of it would be that community's own voice.

    Matched on the host, not on a substring: `ecovillage.org.in` is an Indian
    community's own domain and has nothing to do with the network's site.
    """
    for row in rows:
        for url in row["deep_crawl_urls"].split(URL_DELIMITER):
            if not url:
                continue
            host = urlsplit(url).netloc.lower().removeprefix("www.")
            assert host != "ecovillage.org", row["community_id"]


def test_deep_targets_and_source_scopes_agree(rows):
    """`deep_crawl_urls` and the per-source `crawl_scope` cannot disagree.

    They are two views of one decision, and a crawler may read either.
    """
    for row in rows:
        deep_hosts = {urlsplit(u).netloc for u in
                      row["deep_crawl_urls"].split(URL_DELIMITER) if u}
        for source in json.loads(row["seed_sources_json"]):
            expected = "exhaustive" if urlsplit(
                source["url"]).netloc in deep_hosts else "targeted"
            assert source["crawl_scope"] == expected, (row["community_id"], source["url"])
            assert source["asset_download"] == (
                "all" if expected == "exhaustive" else "evidence_bearing")


def test_academic_terms_exist_for_every_community_and_carry_the_names(rows):
    """The harvest is driven by written-down strings, not by re-derivation.

    Writing the queries into the file is what makes the literature search
    reproducible: a community that turns up nothing can be told apart from one
    that was never asked about properly.
    """
    for row in rows:
        terms = [t for t in row["academic_search_terms"].split(URL_DELIMITER) if t]
        assert len(terms) >= 3, row["community_id"]
        assert row["name"] in terms, row["community_id"]
        assert all(t == t.strip() and t for t in terms), row["community_id"]


def test_every_alternative_name_is_actually_searched(rows):
    """A name the community is also known by is worthless if nothing queries it.

    The literature does not agree on names - Khula Dhamma is published as Khula
    Dharma, Zeleni Kruchi under Dubravushka, Raiz do Anuhmas as Anhumas. Each
    alternative name must appear in the harvest, or those papers are invisible.
    """
    for row in rows:
        terms = {t.lower() for t in row["academic_search_terms"].split(URL_DELIMITER)}
        for alt in row["alternative_names"].split("; "):
            alt = alt.split("(")[0].strip()
            if not alt:
                continue
            assert any(alt.lower() == t or t.startswith(alt.lower() + " ")
                       for t in terms), (row["community_id"], alt)


def test_search_terms_survive_the_reader_intact(rows):
    """A query is prose: commas and semicolons inside it must not split it.

    "Baireni, Udayapur" is one search string. Splitting it the way an address
    list is split would search for "Baireni" and "Udayapur" separately and
    quietly lose the disambiguation that makes the query work.
    """
    communities = {c["name"]: c for c in read_community_file(MASTER)}
    commas = 0
    for row in rows:
        parsed = communities[row["name"]]["academic_search_terms"]
        expected = [t for t in row["academic_search_terms"].split(URL_DELIMITER) if t]
        assert parsed == expected, row["community_id"]
        commas += sum(1 for t in expected if "," in t or ";" in t)
    assert commas, "the guard is worthless if no term contains a comma"


def test_the_crawler_reads_the_policy_columns(rows):
    """The reader must actually surface the policy, or the file is just decor."""
    communities = read_community_file(MASTER)
    assert len(communities) == EXPECTED_COMMUNITIES
    with_deep = [c for c in communities if c["deep_crawl_urls"]]
    assert len(with_deep) >= 150
    for community in communities:
        assert community["crawl_policy"] in {
            "EXHAUSTIVE_SITE_AND_ACADEMIC", "ACADEMIC_EXHAUSTIVE_ONLY"}
        assert community["academic_search_terms"]


def test_policy_columns_are_optional_for_a_plain_sheet(tmp_path):
    """A researcher's two-column sheet still loads; it just gets the defaults."""
    plain = tmp_path / "plain.csv"
    plain.write_text("Ecovillage_Name,Latitude,Longitude,urls\n"
                     "Somewhere,1.5,2.5,https://example.org/\n", encoding="utf-8")
    got = read_community_file(plain)
    assert len(got) == 1
    assert got[0]["deep_crawl_urls"] == []
    assert got[0]["academic_search_terms"] == []
    assert got[0]["crawl_policy"] is None
