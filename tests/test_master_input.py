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


def test_every_original_coordinate_is_still_recoverable(rows, original):
    """All 314 source coordinates, not just the 212 that became primary."""
    wanted = {(r["Ecovillage_Name"],
               f"{float(r['Latitude']):.6f},{float(r['Longitude']):.6f}")
              for r in original}
    have: set[tuple[str, str]] = set()
    for row in rows:
        for pair in row["coordinate_candidates"].split(URL_DELIMITER):
            have.add((row["community_name_original"], pair.strip()))
    assert wanted <= have, f"coordinates dropped: {sorted(wanted - have)[:5]}"
    assert sum(int(r["coordinate_candidate_count"]) for r in rows) == EXPECTED_SOURCE_ROWS


def test_the_exported_coordinate_is_never_lost(rows, original):
    """Whatever the crawler is given, the export's own first coordinate survives.

    The primary coordinate moves for the 31 rows where the export listed four
    geocoder candidates and step6 established which one matches the community's
    published address. Nothing may be discarded in the process: the coordinate
    the export put first has to remain byte-for-byte recoverable, or the
    original data has been silently rewritten.
    """
    first_seen: dict[str, tuple[str, str]] = {}
    for record in original:
        first_seen.setdefault(record["Ecovillage_Name"],
                              (record["Latitude"], record["Longitude"]))
    for row in rows:
        lat, lon = first_seen[row["community_name_original"]]
        assert row["latitude_as_exported"] == f"{float(lat):.6f}", row["community_id"]
        assert row["longitude_as_exported"] == f"{float(lon):.6f}", row["community_id"]
        # and it is still among the candidate list too
        assert f"{float(lat):.6f},{float(lon):.6f}" in row["coordinate_candidates"]


def test_a_single_coordinate_row_is_never_second_guessed(rows, original):
    """Rows the export gave one coordinate for keep it, untouched."""
    for row in (r for r in rows if r["coordinate_status"] == "SINGLE"):
        assert row["latitude"] == row["latitude_as_exported"], row["community_id"]
        assert row["longitude"] == row["longitude_as_exported"], row["community_id"]
        assert row["coordinate_primary_rule"] == "single_source_row"


def test_a_moved_coordinate_is_one_of_the_exported_candidates(rows):
    """A resolved coordinate is a CHOICE among the four given, never a new point.

    This is the guard against the resolution step quietly inventing a location:
    the promoted latitude/longitude must appear verbatim in the candidate list
    the export supplied.
    """
    moved = [r for r in rows if r["latitude"] != r["latitude_as_exported"]
             or r["longitude"] != r["longitude_as_exported"]]
    assert moved, "expected the resolution step to have moved some coordinates"
    for row in moved:
        assert row["coordinate_status"] == "MULTIPLE_CANDIDATES_RESOLVED", row["community_id"]
        pair = f"{float(row['latitude']):.6f},{float(row['longitude']):.6f}"
        assert pair in row["coordinate_candidates"].split(URL_DELIMITER), row["community_id"]


def test_every_moved_coordinate_cites_the_address_that_justifies_it(rows):
    """No coordinate may be reassigned on a hunch - each carries its evidence."""
    for row in (r for r in rows
                if r["coordinate_status"] == "MULTIPLE_CANDIDATES_RESOLVED"):
        evidence = row["coordinate_evidence"]
        assert "published locality:" in evidence, row["community_id"]
        assert "http" in evidence, row["community_id"]
        assert len(evidence) > 120, row["community_id"]
        assert row["coordinate_confidence"] in {"HIGH", "MEDIUM"}, row["community_id"]
        assert row["coordinate_primary_rule"].startswith(
            "verified_against_published_address_candidate_"), row["community_id"]


def test_an_unresolved_coordinate_is_still_flagged_and_still_the_exported_one(rows):
    """Where the address could not separate the candidates, nothing was chosen."""
    unresolved = [r for r in rows
                  if r["coordinate_status"] == "MULTIPLE_CANDIDATES_UNRESOLVED"]
    assert unresolved, "the honest outcome for some rows is no answer"
    for row in unresolved:
        assert row["latitude"] == row["latitude_as_exported"], row["community_id"]
        assert row["longitude"] == row["longitude_as_exported"], row["community_id"]
        assert row["coordinate_confidence"] == "LOW", row["community_id"]
        assert "multiple_coordinate_candidates" in row["review_reasons"]


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
        if row["coordinate_status"] == "MULTIPLE_CANDIDATES_UNRESOLVED":
            assert "multiple_coordinate_candidates" in reasons
        if row["discovery_status"] == "PENDING":
            assert "discovery_pending" in reasons
    # The export shipped four geocoder candidates for 34 communities and chose
    # none. 31 were settled against their own published addresses; the 3 whose
    # sources name only a district or a region are left open on purpose.
    statuses = collections.Counter(r["coordinate_status"] for r in rows)
    assert statuses["MULTIPLE_CANDIDATES_RESOLVED"] == 31
    assert statuses["MULTIPLE_CANDIDATES_UNRESOLVED"] == 3
    assert statuses["SINGLE"] == 178


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
