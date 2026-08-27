"""Conflict resolution and the human review queue.

Where sources disagree the program does not pick quietly and does not average
(register 9.2). It records both values with their sources, applies the
protocol's rule where one exists, and flags the case for a human where none
does (brief §45, §46).

It also distinguishes a value that CHANGED from a value that CONFLICTS: a 2012
page saying four hectares and a 2024 page saying fifteen are not in
disagreement — the community grew (register 9.4, decision DCR-D008).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from . import roles

# Class strength for resolving ordinary (non-onset) disagreements: an
# independent record outranks a self-description.
CLASS_STRENGTH = {"S1": 6, "S2": 6, "S8": 4, "S6": 3, "S5": 3, "S3": 2, "S4": 2, "S7": 1}


@dataclass
class ClaimView:
    """A claim as the resolver sees it."""

    claim_id: str
    field_name: str
    value: str
    source_id: str | None
    source_class: str | None
    independence_group: str | None
    reference_year: int | None = None
    publication_date: str | None = None
    evidence_rank: int | None = None
    confidence: float = 0.5
    original_value: str | None = None
    exact_wording: str | None = None
    value_type: str = "text"
    #: What this value is a value OF (see `evidence/roles.py`). Claims with
    #: different roles are never compared.
    semantic_role: str | None = None
    role_reason: str | None = None

    @property
    def strength(self) -> int:
        return CLASS_STRENGTH.get(self.source_class or "S4", 2)

    @property
    def year(self) -> int | None:
        if self.reference_year:
            return self.reference_year
        match = re.search(r"\b(19\d{2}|20\d{2})\b", self.publication_date or "")
        return int(match.group(1)) if match else None


@dataclass
class Resolution:
    field_name: str
    value: str | None
    status: str                       # coded | not_found | review_required | time_series
    method: str
    rationale: str
    claim_ids: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    residual_uncertainty: str = ""
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    review: dict[str, str] | None = None
    series: list[tuple[int | None, str]] = field(default_factory=list)
    #: Claims that bore on this field but are about something else — visitor
    #: counts beside a resident count, the whole property beside the managed
    #: land. Kept so the report can say what else the sources said.
    other_roles: dict[str, list[str]] = field(default_factory=dict)


def resolve_field(
    field_name: str,
    claims: Sequence[ClaimView],
    *,
    numeric: bool = False,
    growth_gap_years: int = 3,
    prefer: str = "strongest",
    respect_roles: bool = True,
) -> Resolution:
    """Resolve one field from all the claims that bear on it.

    **Claims about different things are not competing claims.** Before anything
    is compared, the claims are partitioned by semantic role, and only those
    carrying the role the field is actually about are considered. "200 visitors
    a year", "12 permanent residents" and "60 people at the summer gathering"
    are three facts, not three candidate populations, and reporting them as a
    disagreement is most of what made the previous run produce five and a half
    thousand conflicts (brief §21, §22, §23, §24).

    The claims set aside are not discarded: they are recorded on the resolution
    as `other_roles`, so the report can say what else the sources said and a
    coder can see it.
    """
    if not claims:
        return Resolution(
            field_name=field_name, value=None, status="not_found",
            method="no claim", rationale="no retrieved source states a value for this field",
        )

    other_roles: dict[str, list[str]] = {}
    if respect_roles:
        expected = roles.role_for_field(field_name)
        if expected is not None:
            _family, wanted = expected
            considered = [c for c in claims if c.semantic_role == wanted]
            for claim in claims:
                if claim.semantic_role != wanted:
                    other_roles.setdefault(
                        claim.semantic_role or roles.UNCLASSIFIED, []
                    ).append(claim.claim_id)
            if not considered:
                unresolved = len(other_roles.get(roles.UNCLASSIFIED, ()))
                described = ", ".join(
                    f"{len(ids)} {role}" for role, ids in sorted(other_roles.items()))
                return Resolution(
                    field_name=field_name, value=None,
                    status="review_required" if unresolved else "not_found",
                    method="no claim of the right kind",
                    rationale=(
                        f"{len(claims)} figure(s) were found but none of them is a "
                        f"{wanted!r} figure ({described}). "
                        + ("Some could not be classified from their sentences and need "
                           "a human reading." if unresolved else
                           "They are recorded as their own facts rather than "
                           "substituted for this field.")),
                    source_ids=sorted({c.source_id for c in claims if c.source_id}),
                    other_roles=other_roles,
                    review={
                        "category": "semantic_role",
                        "subject": f"No {wanted} figure for {field_name}",
                        "detail": (
                            f"{described}. Substituting one of these would put the "
                            "wrong kind of number in the workbook."),
                        "severity": "blocking" if unresolved else "normal",
                    } if unresolved else None,
                )
            claims = considered

    groups = sorted({c.independence_group for c in claims if c.independence_group})
    source_ids = sorted({c.source_id for c in claims if c.source_id})
    distinct = _distinct_values(claims, numeric=numeric)

    if len(distinct) == 1:
        value = next(iter(distinct))
        supporting = [c for c in claims if _key(c, numeric) == value]
        best = _strongest(supporting)
        return Resolution(
            field_name=field_name,
            value=best.value,
            status="coded",
            method="single value" if len(claims) == 1 else "corroborated",
            rationale=(
                f"{len(supporting)} claim(s) across {len(groups) or 1} independence group(s) "
                f"agree; strongest is {best.source_class} ({best.source_id or 'unattributed'})"
            ),
            claim_ids=[c.claim_id for c in supporting],
            source_ids=source_ids,
            groups=groups,
            other_roles=other_roles,
        )

    # Values differ. First: did the value CHANGE rather than conflict?
    if numeric:
        series = _time_series(claims, growth_gap_years)
        if series is not None:
            latest_year, latest_claims = series
            best = _strongest(latest_claims)
            history = "; ".join(
                f"{c.year or 'undated'}: {c.original_value or c.value}"
                for c in sorted(claims, key=lambda c: (c.year or 0))
            )
            return Resolution(
                field_name=field_name,
                value=best.value,
                status="coded",
                method="time_series",
                rationale=(
                    f"the figures move consistently over time rather than contradicting each "
                    f"other; the {latest_year} figure is recorded. Full series: {history}"
                ),
                claim_ids=[c.claim_id for c in latest_claims],
                source_ids=source_ids,
                groups=groups,
                residual_uncertainty=f"earlier figures retained: {history}",
                series=[(c.year, c.original_value or c.value) for c in claims],
                other_roles=other_roles,
            )

    # A genuine disagreement.
    #
    # One row per competing VALUE, not per competing claim. A community whose
    # population is mentioned on two hundred pages with fourteen different
    # figures is fourteen disagreements, not two hundred — and emitting the
    # latter buries the real ones under near-identical repetitions of the same
    # two numbers (brief §31, §32). Every individual claim is still in the
    # claims table with its own wording and source; what is summarised here is
    # the disagreement, not the evidence.
    ranked = sorted(claims, key=lambda c: (-(c.strength), -(c.confidence)))
    best = ranked[0]
    best_key = _key(best, numeric)
    by_value = _group_by_value(claims, numeric)
    runner_up = next((c for c in ranked[1:] if _key(c, numeric) != best_key), None)

    supporting_best = by_value.get(best_key, [best])
    groups_a = len({c.independence_group for c in supporting_best if c.independence_group})
    summary = (
        f"{len(by_value)} distinct reported value(s) for {field_name} across "
        f"{len(groups) or 1} independence group(s), from {len(claims)} claim(s)"
    )

    conflicts: list[dict[str, Any]] = []
    for key, group_claims in by_value.items():
        if key == best_key:
            continue
        other = _strongest(group_claims)
        conflicts.append({
            "field_name": field_name,
            "value_a": best.value, "claim_a": best.claim_id, "source_a": best.source_id,
            "group_a": best.independence_group, "rank_a": best.evidence_rank,
            "date_a": best.publication_date,
            "value_b": other.value, "claim_b": other.claim_id, "source_b": other.source_id,
            "group_b": other.independence_group, "rank_b": other.evidence_rank,
            "date_b": other.publication_date,
            # How much stands behind each side, so a summarised row is not a
            # thinner record than the pile of pairwise ones it replaces.
            "claims_a": len(supporting_best),
            "claims_b": len(group_claims),
            "groups_a": groups_a,
            "groups_b": len({c.independence_group for c in group_claims
                             if c.independence_group}),
            "distinct_values": len(by_value),
            "semantic_role": best.semantic_role,
            "summary": summary,
        })

    same_strength = runner_up is not None and runner_up.strength == best.strength
    cross_group = runner_up is not None and (
        best.independence_group != runner_up.independence_group
    )

    if same_strength and cross_group:
        # Two independent sources of equal standing disagree. There is no
        # protocol rule for this outside onset dating, so a human decides.
        for conflict in conflicts:
            conflict["rule_invoked"] = "no deterministic rule for equal-strength cross-group disagreement"
            conflict["resolution_type"] = "unresolved"
            conflict["final_value"] = ""
            conflict["residual_uncertainty"] = f"{best.value} vs {runner_up.value}"
            conflict["human_review"] = 1
        return Resolution(
            field_name=field_name,
            value=None,
            status="review_required",
            method="unresolved",
            rationale=(
                f"{best.source_class} ({best.source_id}) says {best.value!r}; "
                f"{runner_up.source_class} ({runner_up.source_id}) says {runner_up.value!r}. "
                "Equal source strength, different independence groups, and no protocol rule "
                f"covers this field — left for a human coder. {summary}."
            ),
            claim_ids=[c.claim_id for c in claims],
            source_ids=source_ids,
            groups=groups,
            residual_uncertainty=f"{best.value} vs {runner_up.value}",
            conflicts=conflicts,
            review={
                "category": "conflict",
                "subject": f"Contradictory values for {field_name}",
                "detail": (
                    f"{best.value!r} from {best.source_id} ({best.source_class}, "
                    f"group {best.independence_group}) versus {runner_up.value!r} from "
                    f"{runner_up.source_id} ({runner_up.source_class}, group "
                    f"{runner_up.independence_group}). Both preserved; neither written."
                ),
                "severity": "blocking",
            },
            other_roles=other_roles,
        )

    for conflict in conflicts:
        conflict["rule_invoked"] = (
            f"stronger source class wins: {best.source_class} over "
            f"{conflict['value_b'] and (runner_up.source_class if runner_up else '?')}"
        )
        conflict["resolution_type"] = "rule applied"
        conflict["final_value"] = best.value
        conflict["residual_uncertainty"] = "; ".join(
            f"{c.value} ({c.source_class}, {c.source_id})" for c in ranked[1:4]
        )
        conflict["human_review"] = 0

    return Resolution(
        field_name=field_name,
        value=best.value,
        status="coded",
        method="source_class_precedence",
        rationale=(
            f"selected {best.value!r} from {best.source_class} "
            f"({best.source_id or 'unattributed'}); weaker statements preserved: "
            + "; ".join(f"{c.value!r} ({c.source_class})" for c in ranked[1:4])
        ),
        claim_ids=[c.claim_id for c in claims],
        source_ids=source_ids,
        groups=groups,
        residual_uncertainty="; ".join(
            f"{c.value} ({c.source_class}, {c.source_id})" for c in ranked[1:4]
        ),
        conflicts=conflicts,
        other_roles=other_roles,
    )


def _key(claim: ClaimView, numeric: bool) -> str:
    if numeric:
        try:
            return f"{float(str(claim.value).replace(',', '.')):.4f}"
        except (TypeError, ValueError):
            return str(claim.value).strip().lower()
    return str(claim.value).strip().lower()


def _distinct_values(claims: Sequence[ClaimView], *, numeric: bool) -> set[str]:
    return {_key(c, numeric) for c in claims}


def _group_by_value(claims: Sequence[ClaimView],
                    numeric: bool) -> dict[str, list[ClaimView]]:
    """Claims collected under the normalised value each one asserts.

    Two hundred claims of "about 200 residents" are one reported value. Keeping
    them grouped is what stops the disagreement record scaling with how often a
    community repeats itself.
    """
    grouped: dict[str, list[ClaimView]] = {}
    for claim in claims:
        grouped.setdefault(_key(claim, numeric), []).append(claim)
    return grouped


def _strongest(claims: Sequence[ClaimView]) -> ClaimView:
    return sorted(claims, key=lambda c: (-(c.strength), -(c.confidence)))[0]


def _time_series(claims: Sequence[ClaimView],
                 gap_years: int) -> tuple[int, list[ClaimView]] | None:
    """Is this growth over time rather than a contradiction?"""
    dated = [c for c in claims if c.year]
    if len(dated) < 2:
        return None
    years = sorted({c.year for c in dated if c.year})
    if len(years) < 2 or (years[-1] - years[0]) < gap_years:
        return None
    try:
        pairs = sorted(
            ((c.year, float(str(c.value).replace(",", "."))) for c in dated if c.year),
            key=lambda pair: pair[0],
        )
    except (TypeError, ValueError):
        return None
    values = [v for _, v in pairs]
    monotonic = all(b >= a for a, b in zip(values, values[1:])) or \
                all(b <= a for a, b in zip(values, values[1:]))
    if not monotonic:
        return None
    latest_year = pairs[-1][0]
    latest = [c for c in dated if c.year == latest_year]
    return latest_year, latest


@dataclass
class ReviewItem:
    category: str
    subject: str
    detail: str
    severity: str = "normal"
    related_ids: str = ""
    suggested_action: str = ""


class ReviewQueue:
    """Cases where a machine decision would be a bad decision (brief §46)."""

    def __init__(self) -> None:
        self.items: list[ReviewItem] = []
        self._seen: set[tuple[str, str]] = set()

    def add(self, category: str, subject: str, detail: str, *, severity: str = "normal",
            related_ids: str = "", suggested_action: str = "") -> None:
        key = (category, subject)
        if key in self._seen:
            return
        self._seen.add(key)
        self.items.append(
            ReviewItem(category=category, subject=subject, detail=detail, severity=severity,
                       related_ids=related_ids, suggested_action=suggested_action)
        )

    def extend(self, entries: Iterable[Mapping[str, str]]) -> None:
        for entry in entries:
            self.add(
                entry.get("category", "general"),
                entry.get("subject", ""),
                entry.get("detail", ""),
                severity=entry.get("severity", "normal"),
                related_ids=entry.get("related_ids", ""),
                suggested_action=entry.get("suggested_action", ""),
            )

    @property
    def blocking(self) -> list[ReviewItem]:
        return [item for item in self.items if item.severity == "blocking"]

    def __len__(self) -> int:
        return len(self.items)
