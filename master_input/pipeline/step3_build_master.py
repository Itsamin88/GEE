"""Step 3 - assemble the master input CSV.

One row per community, 212 of them, carrying five things that used to live in
five places: what the crawler needs to start, who the community is, where it
is and how confident we are of that, its Global Ecovillage Network status, and
the quality control that lets a reader tell a thin record from a thorough one.

Three decisions shape the file and are worth stating plainly.

**The URL list is one column, not ten.** `URL_1 ... URL_10` cannot say what a
URL *is*, and the crawler's own reader already accepts a single delimited
`urls` column. Per-address facts - source class, platform type, independence
group, confidence, the evidence that identified it - go in one JSON column
beside it, so the addresses stay exactly reconstructable and the metadata
stays attached to the address it describes rather than to a column number.

**The delimiter is " | ", not ";" or ",".** `csv.Sniffer` weighs `,` `;` and
tab; a pipe is invisible to it, so a URL list can never be mistaken for the
file's own delimiter. Commas inside query strings survive for the same reason.

**Nothing from the original file is overwritten.** Repaired names sit beside
the originals, every coordinate the source gave is preserved even where a
community has four of them, and a country the gazetteer and the web disagree
about is flagged rather than silently resolved.
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pycountry

SCHEMA_VERSION = "1.0.0"
GEN_GLOBAL_URL = "https://ecovillage.org"
URL_DELIMITER = " | "
LIST_DELIMITER = "; "
OUT = Path("master_input/Paper1_Final_Only_Ecovillages_Master_Input.csv")

COLUMNS = [
    # --- what the crawler reads (orchestrator/session.py read_community_file)
    "community_id", "name", "latitude", "longitude", "country", "mode",
    "coder_id", "urls",
    # --- identity, with the original preserved
    "community_name_original", "community_name_normalized",
    "name_repair_applied", "alternative_names", "register_mode",
    # --- coordinates, with every candidate the source gave
    "source_rows", "coordinate_primary_rule", "coordinate_candidate_count",
    "coordinate_candidate_spread_km", "coordinate_candidates",
    "coordinate_status",
    # --- country, and how it was established
    "country_iso2", "country_iso3", "admin_region", "country_confidence",
    "country_verification_method", "country_verification_source",
    "country_gazetteer_code", "country_gazetteer_signal",
    "country_gazetteer_nearest",
    # --- the Global Ecovillage Network, global source vs community profile
    "gen_global_url", "gen_global_status", "gen_community_url",
    "gen_community_status", "gen_verification_method", "gen_evidence_note",
    "gen_independence_group",
    # --- the seed source set
    "seed_url_count", "independence_group_count", "source_classes",
    "strongest_source_class", "seed_sources_json",
    # --- address validation; the live pass writes the last four
    "seed_url_verification_method", "seed_url_validated_count",
    "seed_url_dead_count", "seed_url_blocked_count",
    "seed_url_duplicate_count",
    # --- quality control and provenance
    "discovery_status", "community_identity_confidence", "review_required",
    "review_reasons", "qc_notes", "verification_date", "schema_version",
]

#: Gazetteer country codes whose geonamescache name differs from the ISO 3166
#: English short name this file standardises on (rule §29: one representation).
CANONICAL_NAME_FIXES = {
    "US": "United States", "GB": "United Kingdom", "RU": "Russia",
    "KR": "South Korea", "KP": "North Korea", "IR": "Iran", "SY": "Syria",
    "VE": "Venezuela", "BO": "Bolivia", "TZ": "Tanzania", "MD": "Moldova",
    "LA": "Laos", "VN": "Vietnam", "BN": "Brunei", "CD": "Democratic Republic of the Congo",
    "CG": "Republic of the Congo", "CZ": "Czechia", "MK": "North Macedonia",
    "SZ": "Eswatini", "TR": "Turkey", "CI": "Ivory Coast", "CV": "Cabo Verde",
    "PS": "Palestine", "TW": "Taiwan", "MM": "Myanmar", "BS": "Bahamas",
    "GM": "Gambia", "NL": "Netherlands", "PH": "Philippines",
}


def canonical_country(code: str) -> str:
    """ISO alpha-2 -> the one English name this dataset uses for that country."""
    if not code:
        return ""
    if code in CANONICAL_NAME_FIXES:
        return CANONICAL_NAME_FIXES[code]
    record = pycountry.countries.get(alpha_2=code)
    if record is None:
        return ""
    return getattr(record, "common_name", None) or record.name


def iso3_for(code: str) -> str:
    record = pycountry.countries.get(alpha_2=code) if code else None
    return record.alpha_3 if record else ""


def ranked_urls(sources: list[dict]) -> list[str]:
    """Addresses in descending research usefulness, GEN's global page last.

    The global GEN page is mandatory on every row (brief §5) but is a standard
    network route rather than a finding about this community, so it never
    displaces a thesis or an official site from the top of the list (brief §38).
    """
    community_specific = sorted(
        (s for s in sources if s["url"] != GEN_GLOBAL_URL),
        key=lambda s: -float(s.get("score", 0.0)),
    )
    out: list[str] = []
    for source in community_specific:
        if source["url"] not in out:
            out.append(source["url"])
    out.append(GEN_GLOBAL_URL)
    return out


def build_row(community: dict, discovery: dict | None) -> dict[str, str]:
    points = community["coordinate_candidates"]
    primary = points[0]
    gaz = primary["geocode"]
    reviews: list[str] = []
    notes: list[str] = []

    # ---- identity -------------------------------------------------------
    original = community["community_name_original"]
    normalized = community["community_name_normalized"]
    if community["text_repaired"]:
        notes.append("name repaired from a mis-encoded export; original preserved")

    # ---- coordinates ----------------------------------------------------
    candidates = URL_DELIMITER.join(
        f"{p['latitude']:.6f},{p['longitude']:.6f}" for p in points)
    if len(points) > 1:
        coordinate_status = "MULTIPLE_CANDIDATES_UNRESOLVED"
        reviews.append("multiple_coordinate_candidates")
        notes.append(
            f"the source file gave {len(points)} coordinates for this one name, "
            f"up to {community['candidate_spread_km']:.0f} km apart, so at most one "
            "can be the site; all are preserved and none is asserted")
    else:
        coordinate_status = "SINGLE"

    # ---- country --------------------------------------------------------
    gaz_code = gaz["country_code"]
    gaz_name = canonical_country(gaz_code)
    if discovery:
        iso2 = discovery["country_iso2"]
        country = canonical_country(iso2) or discovery["country"]
        method = discovery["country_method"]
        source = discovery["country_source"]
        admin = discovery["admin_region"]
        if iso2 == gaz_code:
            confidence = "HIGH"
        else:
            confidence = "MEDIUM"
            reviews.append("country_corrected_from_gazetteer")
            notes.append(
                f"country corrected from the gazetteer's {gaz_name or gaz_code} to "
                f"{country} on published evidence; the nearest large town lies across "
                "a border, a coast or a lake")
    else:
        iso2 = gaz_code
        country = gaz_name
        method = "coordinate_gazetteer_only"
        source = "geonamescache k-nearest populated places (offline)"
        admin = ""
        confidence = {"UNANIMOUS": "MEDIUM", "MAJORITY": "LOW"}.get(
            gaz["signal"], "LOW")
        reviews.append("country_not_web_verified")
    if gaz["signal"] in {"SPLIT", "REMOTE", "NO_CITY_IN_RANGE"}:
        reviews.append(f"gazetteer_{gaz['signal'].lower()}")

    # ---- GEN ------------------------------------------------------------
    if discovery:
        gen_url = discovery["gen_community_url"]
        gen_status_raw = discovery["gen_status"]
        gen_evidence = discovery["gen_evidence"]
        gen_method = "search_index" if gen_url else "search_index_negative"
        if gen_status_raw.startswith("NOT_SEARCHED"):
            # A community researched for its other sources but never actually
            # queried against ecovillage.org must not be reported as NOT_FOUND.
            # Register v2.4 I12: absence of effort is not absence of evidence.
            gen_url, gen_status, gen_method = "", "NOT_SEARCHED", "none"
            reviews.append("gen_not_searched")
        elif gen_url:
            gen_status = "VERIFIED_COMMUNITY_SOURCE"
            if gen_status_raw != "VERIFIED_SEARCH_INDEX":
                gen_status = f"VERIFIED_COMMUNITY_SOURCE_{gen_status_raw.replace('VERIFIED_SEARCH_INDEX_', '')}"
                reviews.append("gen_page_qualified")
        else:
            gen_status = "NOT_FOUND"
    else:
        gen_url, gen_status, gen_evidence = "", "NOT_SEARCHED", (
            "no Global Ecovillage Network search was run for this community in "
            "this pass; absence here is absence of effort, not absence of a page")
        gen_method = "none"
        reviews.append("gen_not_searched")

    # ---- the source set --------------------------------------------------
    sources = discovery["sources"] if discovery else []
    urls = ranked_urls(sources)
    groups = sorted({s["independence_group"] for s in sources})
    classes = sorted({s["source_class"] for s in sources})
    payload = [
        {"url": s["url"], "rank": urls.index(s["url"]) + 1,
         "source_class": s["source_class"], "platform_type": s["platform_type"],
         "independence_group": s["independence_group"],
         "confidence": s["confidence"], "quality_score": s["score"],
         "verification": "search_index", "evidence": s["evidence"]}
        for s in sources
    ]
    payload.append({
        "url": GEN_GLOBAL_URL, "rank": len(urls),
        "source_class": "S3", "platform_type": "directory listing",
        "independence_group": "G1", "confidence": "HIGH", "quality_score": 0.10,
        "verification": "fixed_global_source",
        "evidence": "Mandatory Global Ecovillage Network network-level seed, "
                    "present on every row; not evidence that this community is "
                    "GEN-registered - see gen_community_status",
    })

    if discovery:
        discovery_status = "COMPLETE"
        identity = discovery["identity_confidence"]
        if discovery.get("notes"):
            notes.append(discovery["notes"])
        if len(sources) < 2:
            reviews.append("thin_source_set")
        if len(groups) < 2:
            reviews.append("single_independence_group")
        if identity != "HIGH":
            reviews.append("identity_confidence_below_high")
    else:
        discovery_status = "PENDING"
        identity = "NOT_ASSESSED"
        reviews.append("discovery_pending")
        notes.append(
            "source discovery was not run for this community: the session's web "
            "search budget was exhausted after 99 communities. The mandatory GEN "
            "global seed is present, every original field is preserved, and "
            "master_input/pipeline/step4_resume_discovery.py completes this row in place")

    return {
        "community_id": f"IC{community['seq']:03d}",
        "name": normalized,
        "latitude": f"{primary['latitude']:.6f}",
        "longitude": f"{primary['longitude']:.6f}",
        "country": country,
        "mode": "FULL",
        "coder_id": "",
        "urls": URL_DELIMITER.join(urls),
        "community_name_original": original,
        "community_name_normalized": normalized,
        "name_repair_applied": "yes" if community["text_repaired"] else "no",
        "alternative_names": (discovery or {}).get("alternative_names", ""),
        "register_mode": "SETTLEMENT",
        "source_rows": LIST_DELIMITER.join(str(r) for r in community["source_rows"]),
        "coordinate_primary_rule": "first_source_row",
        "coordinate_candidate_count": str(community["candidate_count"]),
        "coordinate_candidate_spread_km": f"{community['candidate_spread_km']:.3f}",
        "coordinate_candidates": candidates,
        "coordinate_status": coordinate_status,
        "country_iso2": iso2,
        "country_iso3": iso3_for(iso2),
        "admin_region": admin,
        "country_confidence": confidence,
        "country_verification_method": method,
        "country_verification_source": source,
        "country_gazetteer_code": gaz_code,
        "country_gazetteer_signal": gaz["signal"],
        "country_gazetteer_nearest": (
            f"{gaz['nearest_place']} ({gaz['nearest_km']} km)"
            if gaz["nearest_place"] else ""),
        "gen_global_url": GEN_GLOBAL_URL,
        "gen_global_status": "FIXED_GLOBAL_SOURCE",
        "gen_community_url": gen_url,
        "gen_community_status": gen_status,
        "gen_verification_method": gen_method,
        "gen_evidence_note": gen_evidence,
        "gen_independence_group": "G1",
        "seed_url_count": str(len(urls)),
        "independence_group_count": str(len(groups) or 1),
        "source_classes": LIST_DELIMITER.join(classes or ["S3"]),
        "strongest_source_class": (classes or ["S3"])[0],
        "seed_sources_json": json.dumps(payload, ensure_ascii=False,
                                        separators=(",", ":")),
        "seed_url_verification_method": (
            "search_index" if discovery else "none"),
        "seed_url_validated_count": "", "seed_url_dead_count": "",
        "seed_url_blocked_count": "", "seed_url_duplicate_count": "",
        "discovery_status": discovery_status,
        "community_identity_confidence": identity,
        "review_required": "yes" if reviews else "no",
        "review_reasons": LIST_DELIMITER.join(dict.fromkeys(reviews)),
        "qc_notes": " | ".join(notes),
        "verification_date": date.today().isoformat(),
        "schema_version": SCHEMA_VERSION,
    }


def main() -> None:
    communities = json.loads(
        Path("master_input/pipeline/communities_geocoded.json").read_text(encoding="utf-8"))
    discovery = json.loads(Path("master_input/pipeline/discovery.json").read_text(encoding="utf-8"))

    rows = [build_row(c, discovery.get(str(c["seq"]))) for c in communities]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\r\n",
                                quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)

    complete = sum(1 for r in rows if r["discovery_status"] == "COMPLETE")
    print(f"wrote {OUT}")
    print(f"  rows            : {len(rows)}")
    print(f"  columns         : {len(COLUMNS)}")
    print(f"  discovery done  : {complete}")
    print(f"  discovery pending: {len(rows) - complete}")
    print(f"  bytes           : {OUT.stat().st_size}")


if __name__ == "__main__":
    main()
