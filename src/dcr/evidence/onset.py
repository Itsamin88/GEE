"""Onset dating — the priority block.

Four candidate dates are all retained. Only ``date_intervention_onset`` is the
study's onset: the year the FIRST deliberate action to alter vegetation, soil,
water or land cover for ecological purposes is documented. A community founded
in 1985 that began ecological work in 1992 has an onset of 1992.

Evidence rank drives everything; recency and confidence of tone drive nothing
(register 9.2). Rank 5 is a directory founding year used as a proxy: it is not
an onset and forces ``onset_proxy_flag = yes``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from .practices import fold

CURRENT_YEAR_CEILING = 2035


@dataclass
class DateCandidate:
    """One dated statement, with everything the rank scale needs."""

    field_name: str                    # date_formal_founding | ... | date_intervention_onset
    year: int
    sentence: str
    source_id: str | None
    source_class: str
    evidence_rank: int
    rank_reason: str
    marker: str = ""
    domain: str | None = None          # water | soil | vegetation | land_cover
    document_id: str | None = None
    page_id: str | None = None
    independence_group: str | None = None
    is_archive_snapshot: bool = False
    archive_timestamp: str | None = None
    already_under_way: bool = False
    retrospective: bool = False
    locator: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    confidence: float = 0.5


# Rank 1 comes from a dated independent record. Almost every one is academic or
# grey literature (register: "that is why Stages 5 and 6 exist").
RANK_1_CLASSES = {"S1", "S2"}
# Wording that shows the work was ALREADY under way at the snapshot date — the
# condition rank 2 requires.
UNDER_WAY_MARKERS = (
    r"\bhave (been )?(planted|restored|built|dug|created|established)",
    r"\bhas (been )?(planted|restored|built|dug|created|established)",
    r"\b(we|they) (are|were) (planting|restoring|building|digging|creating)",
    r"\bsince \d{4}", r"\bover the (past|last) \w+ years",
    r"\bavons (plante|restaure|construit|creuse|cree)", r"\bdepuis \d{4}",
    r"\bhebben (geplant|hersteld|aangelegd|gegraven)", r"\bsinds \d{4}",
    r"\bseit \d{4}", r"\bdesde \d{4}", r"\bongoing", r"\ben cours",
    r"\bis now established", r"\bmature", r"\bwell established",
)
RETROSPECTIVE_MARKERS = (
    r"\b\d{1,3} years ago", r"\bin the (early|late|mid)[- ]?\d{4}s",
    r"\btwenty years of", r"\bthirty years of", r"\bour \d{1,3}(st|nd|rd|th) anniversary",
    r"\bil y a \d{1,3} ans", r"\bdepuis \d{1,3} ans", r"\banniversaire",
    r"\bjaar geleden", r"\bjubileum", r"\bJahren", r"\banos atras", r"\bhace \d{1,3} anos",
    r"\blooking back", r"\bretrospective", r"\bhistorique",
)


def rank_for(
    *,
    source_class: str,
    is_archive_snapshot: bool,
    already_under_way: bool,
    has_explicit_year: bool,
    retrospective: bool,
    is_directory_founding: bool,
) -> tuple[int, str]:
    """The register's five-point scale, applied by rule."""
    if is_directory_founding:
        return 5, "a directory founding year used as a proxy — not an onset"
    if source_class in RANK_1_CLASSES and has_explicit_year:
        return 1, ("a dated independent record (academic, grant, permit or registry) "
                   "stating the year")
    if is_archive_snapshot and already_under_way:
        return 2, ("a dated archived snapshot describing the work as already under way; "
                   "gives a firm upper bound")
    if retrospective and has_explicit_year:
        return 3, "the community's own dated retrospective statement"
    if has_explicit_year:
        return 3, "a dated statement in the community's own material"
    return 4, "an undated statement; the year is inferred from context"


# Reference_Codes: rank 1 is 0 to +/-1 year, rank 2 is +/-1 to +/-3 with a firm
# upper bound, rank 3 is +/-2 to +/-5, rank 4 is +/-5 or wider, rank 5 is not an
# onset at all. A single unambiguous rank-1 record is precise; disagreement
# between sources is what widens the band from there.
BAND_BY_RANK = {1: 0, 2: 3, 3: 5, 4: 8, 5: 10}


def detect_markers(sentence: str) -> tuple[bool, bool]:
    folded = fold(sentence).lower()
    under_way = any(re.search(p, folded) for p in UNDER_WAY_MARKERS)
    retrospective = any(re.search(p, folded) for p in RETROSPECTIVE_MARKERS)
    return under_way, retrospective


def domain_for(practice: str, domains: Mapping[str, Sequence[str]]) -> str | None:
    for domain, practices in domains.items():
        if practice in practices:
            return domain
    return None


@dataclass
class OnsetResult:
    """The resolved onset block, with the disagreements preserved."""

    values: dict[str, Any] = field(default_factory=dict)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    review_items: list[dict[str, str]] = field(default_factory=list)
    used_candidates: list[DateCandidate] = field(default_factory=list)


def resolve_onset(
    candidates: Iterable[DateCandidate],
    *,
    cohort_windows: Mapping[str, Sequence[int]],
    domains: Mapping[str, Sequence[str]] | None = None,
) -> OnsetResult:
    """Resolve the fourteen Block C fields from the dated evidence found."""
    result = OnsetResult()
    by_field: dict[str, list[DateCandidate]] = {}
    for candidate in candidates:
        if not (1800 <= candidate.year <= CURRENT_YEAR_CEILING):
            continue
        by_field.setdefault(candidate.field_name, []).append(candidate)

    # The three context dates: earliest well-evidenced year for each.
    for field_name in ("date_formal_founding", "date_land_acquisition", "date_first_residence"):
        chosen = _best_year(by_field.get(field_name, []))
        if chosen:
            result.values[field_name] = chosen.year
            result.used_candidates.append(chosen)

    onset_candidates = by_field.get("date_intervention_onset", [])
    if not onset_candidates:
        result.values.update({
            "date_intervention_onset": "NOT FOUND",
            "onset_evidence_rank": "",
            "onset_evidence_description": "no dated statement of a deliberate environmental "
                                          "action was found in any retrieved source",
            "onset_conflicting_sources": "none",
            "onset_proxy_flag": "no",
            "onset_confidence_tier": "C",
            "onset_first_or_major": "unclear",
            "cohort_candidate": "uncertain",
            "domain_onsets": "NOT FOUND",
        })
        result.review_items.append({
            "category": "onset",
            "subject": "No onset evidence found",
            "detail": "No source retrieved in this run states a dated deliberate action on "
                      "vegetation, soil, water or land cover. This may be a true absence or an "
                      "unreached source; check crawl_truncated and the search log before coding.",
            "severity": "blocking",
        })
        return result

    # The study's onset is the EARLIEST documented deliberate action, not the
    # best-evidenced one: the workbook's own example records water 1998 and
    # vegetation 1992 and sets the onset to 1992. Evidence rank decides
    # DISAGREEMENTS about a year (register 9.2), and sets the uncertainty band.
    usable = [c for c in onset_candidates if c.evidence_rank < 5] or onset_candidates
    earliest_year = min(c.year for c in usable)
    supporting = [c for c in usable if c.year == earliest_year]
    best_rank = min(c.evidence_rank for c in supporting)
    chosen = sorted(supporting, key=lambda c: c.evidence_rank)[0]
    point = earliest_year

    # Anything asserting the same earliest year at the same rank corroborates it;
    # anything asserting a different year is a disagreement to be preserved.
    at_best = [c for c in usable if c.evidence_rank == best_rank]
    equal_rank_years = sorted({c.year for c in at_best})

    band = BAND_BY_RANK.get(best_rank, 8)
    lower = point - band
    upper = point + band
    if best_rank == 2:
        # A dated snapshot describing work as already under way bounds it ABOVE.
        upper = point
        lower = point - band

    method = f"earliest documented action, at rank {best_rank}"
    if len(equal_rank_years) > 1:
        # Equal rank disagreeing on a year: earliest is the value, gap is the band.
        lower = min(lower, equal_rank_years[0])
        upper = max(upper, equal_rank_years[-1]) if best_rank != 2 else upper
        method = (f"equal rank {best_rank}: the earliest year is the point estimate and the "
                  f"{equal_rank_years[0]}-{equal_rank_years[-1]} gap becomes the band")

    # A better-ranked source asserting a LATER year does not move the onset —
    # it may simply be dating a different, later intervention — but the tension
    # is recorded and the band is not narrowed past it.
    better_but_later = [c for c in usable
                        if c.evidence_rank < best_rank and c.year > point]
    if better_but_later:
        upper = max(upper, min(c.year for c in better_but_later))

    lower_ranked = [c for c in onset_candidates if c.evidence_rank > best_rank]
    conflicting_text = "none"
    disagreeing = [c for c in onset_candidates if c.year != point]
    if disagreeing:
        parts = []
        seen_pairs: set[tuple[int, int, str]] = set()
        deduped: list[DateCandidate] = []
        for candidate in sorted(disagreeing, key=lambda c: (c.evidence_rank, c.year)):
            key = (candidate.year, candidate.evidence_rank, candidate.source_id or "")
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            deduped.append(candidate)
        disagreeing = deduped
        for candidate in disagreeing[:8]:
            parts.append(
                f"{candidate.year} (rank {candidate.evidence_rank}, "
                f"{candidate.source_class}, {candidate.source_id or 'unattributed'})"
            )
        conflicting_text = (
            f"selected {point} (rank {best_rank}, {chosen.source_class}) as the earliest "
            f"documented action; also stated: " + "; ".join(parts)
        )
        for candidate in disagreeing:
            result.conflicts.append({
                "field_name": "date_intervention_onset",
                "value_a": str(point), "source_a": chosen.source_id,
                "group_a": chosen.independence_group, "rank_a": best_rank,
                "date_a": chosen.sentence[:400],
                "value_b": str(candidate.year), "source_b": candidate.source_id,
                "group_b": candidate.independence_group, "rank_b": candidate.evidence_rank,
                "date_b": candidate.sentence[:400],
                "rule_invoked": (
                    "Onset is the EARLIEST documented deliberate action; evidence rank resolves "
                    "disagreement about a year and sets the band (register 9.2)."
                ),
                "resolution_type": "rule applied",
                "final_value": str(point),
                "residual_uncertainty": f"band {lower}-{upper}",
            })

    proxy = "yes" if best_rank == 5 else "no"
    if proxy == "yes":
        result.review_items.append({
            "category": "onset",
            "subject": "Onset rests on a directory founding year",
            "detail": f"The only dated evidence is a rank-5 directory founding year ({point}). "
                      "That is a proxy, not an onset; the register excludes it from the primary "
                      "age analysis.",
            "severity": "blocking",
        })

    # Reference_Codes: A = a precise year on rank 1 or 2 evidence; B = plus or
    # minus one year; C = uncertain beyond one year.
    width = upper - lower
    if width == 0 and best_rank <= 2:
        tier = "A"
    elif width <= 2:
        tier = "B"
    else:
        tier = "C"

    cohort = _cohort(point, lower, upper, cohort_windows)

    domain_onsets = _domain_onsets(onset_candidates)
    first_or_major = _first_or_major(chosen, onset_candidates)

    result.values.update({
        "date_intervention_onset": point,
        "onset_lower_bound": lower,
        "onset_upper_bound": upper,
        "onset_evidence_rank": str(best_rank),
        "onset_evidence_description": f"{method}; {chosen.rank_reason}: "
                                      f"\"{chosen.sentence[:200]}\"",
        "onset_conflicting_sources": conflicting_text,
        "onset_proxy_flag": proxy,
        "onset_confidence_tier": tier,
        "onset_first_or_major": first_or_major,
        "cohort_candidate": cohort,
        "domain_onsets": domain_onsets or "NOT FOUND",
    })
    result.used_candidates.extend(at_best)

    if lower_ranked and tier == "C":
        result.review_items.append({
            "category": "onset",
            "subject": "Onset band is wider than one year",
            "detail": f"Best evidence is rank {best_rank}; the band is {lower}-{upper}. "
                      f"{len(lower_ranked)} weaker statements were retained but not used. "
                      "A Stage 5/6 pass may find a rank-1 record and narrow this.",
            "severity": "normal",
        })
    return result


def _best_year(candidates: list[DateCandidate]) -> DateCandidate | None:
    if not candidates:
        return None
    return sorted(candidates, key=lambda c: (c.evidence_rank, c.year))[0]


def _cohort(point: int, lower: int, upper: int,
            windows: Mapping[str, Sequence[int]]) -> str:
    core = windows.get("core", [2020, 2021])
    extension = windows.get("extension", [2019, 2019])
    if lower < core[0] <= point <= core[1] < upper:
        return "uncertain"
    if core[0] <= point <= core[1]:
        return "core (2020-2021)" if lower >= core[0] and upper <= core[1] else "uncertain"
    if extension[0] <= point <= extension[1]:
        return "extension (2019)" if lower >= extension[0] and upper <= extension[1] else "uncertain"
    if lower <= core[1] and upper >= extension[0]:
        return "uncertain"
    return "no"


def _domain_onsets(candidates: list[DateCandidate]) -> str:
    earliest: dict[str, int] = {}
    for candidate in candidates:
        if not candidate.domain:
            continue
        current = earliest.get(candidate.domain)
        if current is None or candidate.year < current:
            earliest[candidate.domain] = candidate.year
    if not earliest:
        return ""
    order = ["water", "soil", "vegetation", "land_cover"]
    parts = [f"{d.replace('_', ' ')} {earliest[d]}" for d in order if d in earliest]
    parts += [f"{d} {y}" for d, y in earliest.items() if d not in order]
    return "; ".join(parts)


def _first_or_major(chosen: DateCandidate, candidates: list[DateCandidate]) -> str:
    """Is this the first intervention or a later major project?"""
    earlier = [c for c in candidates if c.year < chosen.year]
    if earlier:
        return "major new project"
    markers = ("first", "began", "started", "premier", "premiere", "debut", "commence",
               "eerste", "begonnen", "erste", "primer", "primeiro", "iniziato")
    folded = fold(chosen.sentence).lower()
    if any(marker in folded for marker in markers):
        return "first intervention"
    return "unclear"
