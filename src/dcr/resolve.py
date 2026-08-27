"""Stage 9 — cross-source reconciliation.

Every value carries its sources. Where sources disagree, both are reported and
the protocol's rule is applied; where no rule exists the case goes to a human.
Corroboration counts independence GROUPS, never URLs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .db import Database, utcnow
from .evidence.conflict import ClaimView, ReviewQueue, resolve_field
from .evidence.extractors import haversine_km
from .evidence.independence import IndependenceResolver
from .evidence.model import claim_dedupe_key, evidence_dedupe_key
from .evidence.onset import DateCandidate, resolve_onset
from .evidence.practices import code_practices
from .logging_setup import event, get_logger

log = get_logger("resolve")

NOT_FOUND = "NOT FOUND"

# Free-text fields that ACCUMULATE rather than conflict. Two different notes
# about the same landholding are two observations, not a disagreement, and
# turning them into a conflict buries the real disagreements in noise.
ACCUMULATING_TEXT_FIELDS = {
    "documentary_area_note", "notable_context", "e2_evidence_note", "status_evidence",
    "practice_evidence_notes", "external_funding_or_programme", "alternative_names",
    "e1_network_listing",
}

# One published phrase is wanted, not a disagreement between three of them.
BEST_QUOTE_FIELDS = {"e1_self_identification"}

NUMERIC_FIELDS = {
    "managed_area_ha", "managed_area_lower_ha", "managed_area_upper_ha", "total_holding_ha",
    "population_value", "population_lower", "population_upper", "e3_population_value",
    "population_source_date", "first_listing_year", "last_listing_year", "dissolution_year",
    "founding_decade", "pages_opened_count", "independence_groups",
}

# Fields resolved by their own engines rather than the generic resolver.
SPECIAL_FIELDS = {
    "date_formal_founding", "date_land_acquisition", "date_first_residence",
    "date_intervention_onset", "onset_lower_bound", "onset_upper_bound",
    "onset_band_width_years", "onset_evidence_rank", "onset_evidence_description",
    "onset_conflicting_sources", "resolution_rule", "onset_proxy_flag",
    "onset_confidence_tier", "onset_first_or_major", "cohort_candidate", "domain_onsets",
    "v1_self_documentation", "v2_external_documentation", "v3_substantive_affiliation",
    "v4_visual_documentation", "v5_continuity_evidence", "channel_count", "activity_tier",
    "activity_tier_note", "coordinate_agreement", "polygon_area_ha", "latitude", "longitude",
    "pages_opened_count", "documents_opened", "source_classes_found", "search_languages",
    "negative_consultations", "independence_groups", "stages_completed", "crawl_truncated",
    "e1_network_listing", "e1_pathway", "founding_decade", "area_type", "site_plan_published",
    "population_source_date",
    "external_funding_or_programme", "practice_evidence_notes",
}


class FieldResolver:
    """Turns stored claims into one resolved value per field."""

    def __init__(self, *, db: Database, settings: Any, community_id: str,
                 review: ReviewQueue, independence: IndependenceResolver):
        self.db = db
        self.settings = settings
        self.community_id = community_id
        self.review = review
        self.independence = independence
        self.schema = settings.schema
        self.conflict_counter = 0
        self._conflict_signatures: set[tuple[str, ...]] = set()
        #: Fields already announced in the log, so one field prints one line.
        self._conflict_fields_logged: set[str] = set()

    # -- entry -------------------------------------------------------------
    def resolve(
        self,
        *,
        community: Any,
        date_candidates: Sequence[DateCandidate],
        practice_hits: Sequence[Any],
        published_coordinates: Sequence[tuple[float, float, str]],
        names: Iterable[str],
        networks: Iterable[str],
        certifiers: Iterable[str],
        stages: Mapping[int, Any],
        truncation_reasons: Sequence[str],
        languages: Iterable[str],
    ) -> dict[str, int]:
        counts = {"coded": 0, "not_found": 0, "review": 0, "conflicts": 0}

        self._resolve_generic(counts)
        self._resolve_onset(date_candidates, counts)
        self._resolve_practices(practice_hits, certifiers, counts)
        self._align_population_date(counts)
        self._derive_area_band(counts)
        self._resolve_activity(counts)
        self._resolve_identity(community, names, networks, published_coordinates, counts)
        self._resolve_provenance(stages, truncation_reasons, languages, counts)
        self._flag_priority_gaps(counts)
        self._store_review_queue()
        return counts

    # -- generic fields ----------------------------------------------------
    def _resolve_generic(self, counts: dict[str, int]) -> None:
        rows = self.db.query(
            "SELECT DISTINCT field_name FROM claims WHERE community_id = ?", (self.community_id,))
        for row in rows:
            field_name = row["field_name"]
            if field_name in SPECIAL_FIELDS:
                continue
            claims = self._claims_for(field_name)
            if field_name in ACCUMULATING_TEXT_FIELDS:
                self._accumulate_text(field_name, claims, counts)
                continue
            if field_name in BEST_QUOTE_FIELDS:
                self._best_quote(field_name, claims, counts)
                continue
            resolution = resolve_field(
                field_name, claims,
                numeric=field_name in NUMERIC_FIELDS,
                growth_gap_years=int(_decision_parameter(
                    self.settings.decisions, "DCR-D008", "growth_gap_years", 3)),
            )
            self._write(resolution.field_name, resolution.value, resolution.status,
                        method=resolution.method, rationale=resolution.rationale,
                        claim_ids=resolution.claim_ids, source_ids=resolution.source_ids,
                        groups=resolution.groups,
                        residual=resolution.residual_uncertainty, counts=counts)
            for conflict in resolution.conflicts:
                self._store_conflict(conflict)
                counts["conflicts"] += 1
            if resolution.review:
                self.review.add(**{k: v for k, v in resolution.review.items()})

    def _best_quote(self, field_name: str, claims: Sequence[ClaimView],
                    counts: dict[str, int]) -> None:
        """Choose one published phrase; keep the rest as residual, not as a conflict.

        The register wants a phrase under 25 words that states ecological aims.
        Several candidates is an embarrassment of riches, not a disagreement.
        """
        aim_words = ("regener", "restor", "ecolog", "sustainab", "biodivers", "soil",
                     "agroecolog", "duurzaam", "natuurherstel", "permacultur")

        def score(claim: ClaimView) -> tuple[int, int, int]:
            value = str(claim.value)
            words = len(value.split())
            on_topic = sum(1 for w in aim_words if w in value.lower())
            fits = 1 if words <= 25 else 0
            return (fits, on_topic, -abs(words - 18))

        best = max(claims, key=score)
        others = [str(c.value)[:200] for c in claims if c.claim_id != best.claim_id]
        self._write(
            field_name, str(best.value)[:400], "coded", method="best_quote",
            rationale=f"chosen from {len(claims)} published phrase(s) as the one that states "
                      "ecological aims within the 25-word limit",
            claim_ids=[best.claim_id],
            source_ids=sorted({c.source_id for c in claims if c.source_id}),
            groups=sorted({c.independence_group for c in claims if c.independence_group}),
            residual=("other candidate phrases: " + " | ".join(others[:4]))[:1500] if others else "",
            counts=counts,
        )

    def _accumulate_text(self, field_name: str, claims: Sequence[ClaimView],
                         counts: dict[str, int]) -> None:
        """Keep every distinct observation, in source-strength order."""
        seen: set[str] = set()
        pieces: list[str] = []
        for claim in sorted(claims, key=lambda c: (-c.strength, -c.confidence)):
            value = str(claim.value).strip()
            key = value.lower()[:160]
            if not value or key in seen:
                continue
            seen.add(key)
            pieces.append(value)
        if not pieces:
            return
        self._write(
            field_name, " | ".join(pieces)[:3000], "coded",
            method="accumulated",
            rationale=f"{len(pieces)} distinct observation(s) kept in source-strength order; "
                      "differing notes about the same subject are observations, not a conflict",
            claim_ids=[c.claim_id for c in claims],
            source_ids=sorted({c.source_id for c in claims if c.source_id}),
            groups=sorted({c.independence_group for c in claims if c.independence_group}),
            residual="", counts=counts,
        )

    # -- onset -------------------------------------------------------------
    def _resolve_onset(self, candidates: Sequence[DateCandidate], counts: dict[str, int]) -> None:
        outcome = resolve_onset(
            candidates,
            cohort_windows=self.schema.get("cohort_windows", {}),
            domains=self.settings.lexicon.get("onset", {}).get("domains", {}),
        )
        source_ids = sorted({c.source_id for c in outcome.used_candidates if c.source_id})
        groups = sorted({c.independence_group for c in outcome.used_candidates
                         if c.independence_group})
        for field_name, value in outcome.values.items():
            status = "not_found" if value == NOT_FOUND else "coded"
            self._write(field_name, None if status == "not_found" else str(value), status,
                        method="onset_engine",
                        rationale="resolved by the onset rank rules (register 9.2)",
                        claim_ids=[], source_ids=source_ids, groups=groups,
                        residual="", counts=counts)
        for conflict in outcome.conflicts:
            self._store_conflict(conflict)
            counts["conflicts"] += 1
        self.review.extend(outcome.review_items)

        founding = outcome.values.get("date_formal_founding")
        if isinstance(founding, int):
            decade = (founding // 10) * 10
            self._write("founding_decade", str(decade), "coded", method="derived",
                        rationale=f"derived from date_formal_founding ({founding}) per "
                                  "decision DCR-D014",
                        claim_ids=[], source_ids=source_ids, groups=groups,
                        residual="", counts=counts)

    def stored_date_candidates(self) -> list[DateCandidate]:
        """Rebuild date candidates from stored claims, so a RECONCILE or AUDIT
        run works offline from the database alone (brief §67)."""
        rows = self.db.query(
            "SELECT c.*, e.quote FROM claims c LEFT JOIN evidence e ON c.evidence_id = e.evidence_id "
            "WHERE c.community_id = ? AND c.field_name LIKE 'date_%'",
            (self.community_id,))
        out: list[DateCandidate] = []
        for row in rows:
            try:
                year = int(str(row["value"])[:4])
            except (TypeError, ValueError):
                continue
            out.append(
                DateCandidate(
                    field_name=row["field_name"],
                    year=year,
                    sentence=(row["exact_wording"] or row["quote"] or "")[:1200],
                    source_id=row["source_id"],
                    source_class=row["source_class"] or "S4",
                    evidence_rank=int(row["evidence_rank"] or 3),
                    rank_reason=row["rationale"] or "stored claim",
                    independence_group=row["independence_group"],
                    document_id=row["document_id"],
                )
            )
        return out

    # -- practices ---------------------------------------------------------
    def _resolve_practices(self, hits: Sequence[Any], certifiers: Iterable[str],
                           counts: dict[str, int]) -> None:
        codes = [f["name"] for f in self.schema["blocks"]["F"]["fields"]
                 if f["name"].startswith("pc")]
        codings = code_practices(hits, all_practices=codes)
        notes: list[str] = []
        for code in codes:
            coding = codings[code]
            source_ids = sorted({h.source_id for h in coding.hits if h.source_id})
            groups = sorted({h.independence_group for h in coding.hits if h.independence_group})
            self._write(code, coding.level, "coded", method="practice_rules",
                        rationale=coding.rationale, claim_ids=[], source_ids=source_ids,
                        groups=groups, residual=coding.note, counts=counts)
            if coding.level != "not mentioned":
                best = coding.hits[0] if coding.hits else None
                notes.append(
                    f"{code}={coding.level}: {coding.rationale}"
                    + (f" [{', '.join(source_ids[:3])}]" if source_ids else "")
                )
                self._store_practice_evidence(code, coding)
            if coding.note == "contradictory statements":
                self.review.add(
                    "practice", f"Contradictory statements about {code}",
                    f"Both a positive statement and a denial were found for {code}. "
                    "Both are preserved in O2b_Practice_Evidence; a human must decide.",
                    severity="normal",
                )
        certifier_list = sorted(set(certifiers))
        if certifier_list:
            notes.append("pc12_organic certifier(s) named: " + "; ".join(certifier_list))
        self._write("practice_evidence_notes", "\n".join(notes) or NOT_FOUND,
                    "coded" if notes else "not_found", method="practice_rules",
                    rationale="one line per coded practice", claim_ids=[], source_ids=[],
                    groups=[], residual="", counts=counts)

    def _store_practice_evidence(self, code: str, coding: Any) -> None:
        """One O2b row per coded practice, with the supporting passage.

        Reconciliation runs again on every resume, so this has to reach the
        rows it wrote last time rather than making new ones (brief §27).
        """
        for hit in coding.hits[:6]:
            key = evidence_dedupe_key(
                self.community_id, source_id=hit.source_id, document_id=hit.document_id,
                page_id=hit.page_id, evidence_type="passage", locator=hit.locator,
                quote=hit.sentence[:4000])
            existing = self.db.query_one(
                "SELECT evidence_id FROM evidence WHERE community_id=? AND dedupe_key=?",
                (self.community_id, key))
            if existing is not None:
                # Never re-insert a passage that is already stored. SQLite's
                # INSERT OR REPLACE deletes the old row first, and
                # claims.evidence_id is ON DELETE SET NULL — so "replacing" a
                # passage silently cuts every claim already resting on it loose
                # from the evidence that supports it.
                self._store_practice_claim(code, coding, hit, existing["evidence_id"])
                continue

            evidence_id = self.db.next_id(
                "evidence", "evidence_id", self.community_id, "E")
            self.db.insert(
                "evidence",
                {
                    "evidence_id": evidence_id,
                    "dedupe_key": key,
                    "community_id": self.community_id,
                    "source_id": hit.source_id,
                    "document_id": hit.document_id,
                    "page_id": hit.page_id,
                    "evidence_type": "passage",
                    "locator": hit.locator,
                    "quote": hit.sentence[:4000],
                    "source_class": hit.source_class,
                    "publication_date": hit.publication_date,
                    "created_utc": utcnow(),
                },
            )
            self._store_practice_claim(code, coding, hit, evidence_id)

    def _store_practice_claim(self, code: str, coding: Any, hit: Any,
                              evidence_id: str) -> None:
        """The claim this passage supports, written once however often it is read."""
        claim_key = claim_dedupe_key(self.community_id, code, coding.level,
                                     evidence_id, "rule:practices/1.0.0")
        if self.db.query_one(
                "SELECT claim_id FROM claims WHERE community_id=? AND dedupe_key=?",
                (self.community_id, claim_key)) is not None:
            return
        self.db.insert(
            "claims",
            {
                "claim_id": self.db.next_id("claims", "claim_id", self.community_id, "C"),
                "dedupe_key": claim_key,
                "community_id": self.community_id,
                "field_name": code,
                "value": coding.level,
                "value_type": "enum",
                "original_value": hit.matched_term,
                "exact_wording": hit.sentence[:4000],
                "source_id": hit.source_id,
                "document_id": hit.document_id,
                "evidence_id": evidence_id,
                "locator": hit.locator,
                "publication_date": hit.publication_date,
                "reference_year": hit.reference_year,
                "source_class": hit.source_class,
                "independence_group": hit.independence_group,
                "coding_level": coding.level,
                "confidence": 0.7 if hit.specific else 0.5,
                "conflict_status": "conflicting" if hit.denial else "none",
                "rationale": coding.rationale,
                "extractor": "rule:practices/1.0.0",
                "extracted_utc": utcnow(),
                "verified_passage": 1,
            },
        )

    def _derive_area_band(self, counts: dict[str, int]) -> None:
        """Give the documentary area a band where the sources support one.

        The register is explicit that the band is what makes the check against
        the drawn polygon meaningful: "about 15 hectares" and a polygon of 11 ha
        are not in conflict, "15.4 hectares under cultivation" and the same
        polygon are. Recording only a point estimate throws that away.
        """
        point_row = self.db.query_one(
            "SELECT value FROM field_values WHERE community_id=? AND field_name='managed_area_ha' "
            "AND status='coded'", (self.community_id,))
        if point_row is None or not point_row["value"]:
            return
        try:
            point = float(str(point_row["value"]).replace(",", "."))
        except ValueError:
            return

        claims = self._claims_for("managed_area_ha")
        values: list[tuple[float, ClaimView]] = []
        for claim in claims:
            try:
                values.append((float(str(claim.value).replace(",", ".")), claim))
            except (TypeError, ValueError):
                continue
        if not values:
            return

        # Only figures describing roughly the same period belong in one band; an
        # older, smaller figure is growth, not uncertainty (register 9.4).
        reference_years = [c.reference_year for _, c in values if c.reference_year]
        latest = max(reference_years) if reference_years else None
        window = int(_decision_parameter(self.settings.decisions, "DCR-D008",
                                         "growth_gap_years", 3))
        if latest is not None:
            # Undated figures are excluded once dated ones exist: an undated
            # "2 hectares" from an abandoned site would otherwise widen a band
            # that the current figures define perfectly well.
            in_period = [(value, claim) for value, claim in values
                         if claim.reference_year
                         and abs(claim.reference_year - latest) <= window]
        else:
            in_period = list(values)
        if not in_period:
            in_period = list(values)
        numbers = sorted(v for v, _ in in_period) or [point]
        low, high = min(numbers + [point]), max(numbers + [point])

        existing_low = self.db.query_one(
            "SELECT value FROM field_values WHERE community_id=? "
            "AND field_name='managed_area_lower_ha' AND status='coded'", (self.community_id,))
        if existing_low:
            return   # a source stated an explicit range; do not overwrite it

        if low == high:
            # One figure only. An approximate figure still carries a band.
            approximate = any("environ" in (c.exact_wording or "").lower()
                              or "about" in (c.exact_wording or "").lower()
                              or "around" in (c.exact_wording or "").lower()
                              or "ongeveer" in (c.exact_wording or "").lower()
                              for _, c in in_period)
            if not approximate:
                return
            low, high = round(point * 0.8, 3), round(point * 1.2, 3)
            note = "the source qualifies the figure as approximate, so a +/-20% band is recorded"
        else:
            note = (f"{len(in_period)} figure(s) describing the same period span "
                    f"{low:g}-{high:g} ha")

        source_ids = sorted({c.source_id for _, c in in_period if c.source_id})
        groups = sorted({c.independence_group for _, c in in_period if c.independence_group})
        for field_name, value in (("managed_area_lower_ha", low), ("managed_area_upper_ha", high)):
            self._write(field_name, f"{value:g}", "coded", method="derived_band",
                        rationale=note, claim_ids=[c.claim_id for _, c in in_period],
                        source_ids=source_ids, groups=groups, residual="", counts=counts)

    def _align_population_date(self, counts: dict[str, int]) -> None:
        """The year the POPULATION figure refers to, not the newest year seen.

        Resolving this field on its own picks whichever year is best attested,
        which can belong to a different figure entirely (register 9.4).
        """
        row = self.db.query_one(
            "SELECT value, claim_ids FROM field_values WHERE community_id=? "
            "AND field_name='population_value' AND status='coded'", (self.community_id,))
        if row is None or not row["claim_ids"]:
            return
        claim_ids = [c.strip() for c in str(row["claim_ids"]).split(";") if c.strip()]
        if not claim_ids:
            return
        placeholders = ",".join("?" for _ in claim_ids)
        chosen = self.db.query_one(
            f"SELECT reference_year, source_id, independence_group FROM claims "
            f"WHERE claim_id IN ({placeholders}) AND reference_year IS NOT NULL "
            f"ORDER BY reference_year DESC LIMIT 1", claim_ids)
        if chosen is None or not chosen["reference_year"]:
            return
        self._write(
            "population_source_date", str(chosen["reference_year"]), "coded",
            method="follows_population_value",
            rationale=f"the year the coded population figure ({row['value']}) refers to, taken "
                      "from the same statement rather than resolved independently",
            claim_ids=claim_ids,
            source_ids=[chosen["source_id"]] if chosen["source_id"] else [],
            groups=[chosen["independence_group"]] if chosen["independence_group"] else [],
            residual="", counts=counts,
        )

    # -- activity verification --------------------------------------------
    def _resolve_activity(self, counts: dict[str, int]) -> None:
        """Block D counts independence GROUPS, never addresses (register Block D)."""
        groups_by_class: dict[str, set[str]] = {}
        for row in self.db.query(
            "SELECT source_class, independence_group FROM sources WHERE community_id = ? "
            "AND independence_group IS NOT NULL", (self.community_id,)
        ):
            groups_by_class.setdefault(row["source_class"] or "S4", set()).add(
                row["independence_group"])

        specific_own = self.db.scalar(
            "SELECT COUNT(*) FROM claims WHERE community_id=? AND coding_level IN "
            "('documented','evidenced') AND source_class IN ('S4','S5','S7')",
            (self.community_id,)) or 0
        external_docs = self.db.scalar(
            "SELECT COUNT(*) FROM claims WHERE community_id=? AND source_class IN ('S1','S2','S6')",
            (self.community_id,)) or 0
        verified_academic = self.db.scalar(
            "SELECT COUNT(*) FROM academic_records WHERE community_id=? AND verified_resolves='yes'",
            (self.community_id,)) or 0
        affiliations = self.db.scalar(
            "SELECT COUNT(*) FROM claims WHERE community_id=? AND field_name='pc12_organic' "
            "AND value IN ('evidenced','documented')", (self.community_id,)) or 0
        visual = self.db.scalar(
            "SELECT COUNT(*) FROM images WHERE community_id=? AND relevance_class='likely_relevant'",
            (self.community_id,)) or 0
        continuity_years = self.db.query(
            "SELECT DISTINCT reference_year FROM claims WHERE community_id=? "
            "AND reference_year IS NOT NULL", (self.community_id,))
        years = sorted(int(r["reference_year"]) for r in continuity_years if r["reference_year"])

        channels = {
            "v1_self_documentation": ("yes" if specific_own else "no",
                                      f"{specific_own} specific documented statements in the "
                                      "community's own material"),
            "v2_external_documentation": ("yes" if (external_docs or verified_academic) else "no",
                                          f"{external_docs} external-class claims, "
                                          f"{verified_academic} verified academic records"),
            "v3_substantive_affiliation": ("yes" if affiliations else "no",
                                           "membership of a body that assesses practice "
                                           "(certification) " +
                                           ("found" if affiliations else "not found")),
            "v4_visual_documentation": ("yes" if visual else "no",
                                        f"{visual} research-relevant images with provenance"),
            "v5_continuity_evidence": (
                "yes" if len(years) >= 2 and (years[-1] - years[0]) >= 2 else "no",
                f"dated statements span {years[0]}-{years[-1]}" if len(years) >= 2
                else "fewer than two distinct dated years"),
        }
        satisfied = 0
        for field_name, (value, rationale) in channels.items():
            if value == "yes":
                satisfied += 1
            self._write(field_name, value, "coded", method="activity_rules",
                        rationale=rationale, claim_ids=[], source_ids=[],
                        groups=sorted({g for gs in groups_by_class.values() for g in gs}),
                        residual="", counts=counts)

        external_satisfied = channels["v2_external_documentation"][0] == "yes"
        visual_or_continuity = (channels["v4_visual_documentation"][0] == "yes"
                                or channels["v5_continuity_evidence"][0] == "yes")
        if satisfied >= 3 and external_satisfied:
            tier = "A"
        elif satisfied == 2 and visual_or_continuity:
            tier = "B"
        elif satisfied == 2:
            tier = "C"
        else:
            tier = "Fail"
        note = (f"{satisfied} of 5 channels satisfied"
                + (", including an external channel" if external_satisfied else
                   ", none of them external")
                + f"; counted across {self.independence.group_count()} independence groups, "
                  "not addresses")
        self._write("activity_tier", tier, "coded", method="activity_rules", rationale=note,
                    claim_ids=[], source_ids=[], groups=[], residual="", counts=counts)
        self._write("activity_tier_note", note, "coded", method="activity_rules",
                    rationale="derived from the channel flags", claim_ids=[], source_ids=[],
                    groups=[], residual="", counts=counts)

    # -- identity, networks, coordinates -----------------------------------
    def _resolve_identity(self, community: Any, names: Iterable[str], networks: Iterable[str],
                          coordinates: Sequence[tuple[float, float, str]],
                          counts: dict[str, int]) -> None:
        self._write("community_name_official", community.name, "coded",
                    method="researcher_input",
                    rationale="the name the researcher supplied; alternatives are recorded "
                              "separately",
                    claim_ids=[], source_ids=[], groups=[], residual="", counts=counts)
        alternatives = sorted({n for n in names if n and n != community.name})
        self._write("alternative_names", "; ".join(alternatives) or NOT_FOUND,
                    "coded" if alternatives else "not_found", method="extraction",
                    rationale="name variants found in retrieved sources; each is a separate "
                              "academic search string",
                    claim_ids=[], source_ids=[], groups=[], residual="", counts=counts)
        if community.country:
            self._write("country", community.country, "coded", method="researcher_input",
                        rationale="supplied by the researcher", claim_ids=[], source_ids=[],
                        groups=[], residual="", counts=counts)

        network_list = sorted(set(networks))
        self._write("e1_network_listing", "; ".join(network_list) or NOT_FOUND,
                    "coded" if network_list else "not_found", method="extraction",
                    rationale="networks and directories naming this community in retrieved sources",
                    claim_ids=[], source_ids=[], groups=[], residual="", counts=counts)
        self_id = self.db.query_one(
            "SELECT value FROM field_values WHERE community_id=? AND field_name='e1_self_identification'",
            (self.community_id,))
        has_self_id = bool(self_id and self_id["value"])
        if network_list and has_self_id:
            pathway = "both"
        elif network_list:
            pathway = "network/directory listing"
        elif has_self_id:
            pathway = "independent self-identification"
        else:
            pathway = None
        if pathway:
            self._write("e1_pathway", pathway, "coded", method="rule",
                        rationale=f"{len(network_list)} listings and "
                                  f"{'a' if has_self_id else 'no'} published self-identification",
                        claim_ids=[], source_ids=[], groups=[], residual="", counts=counts)

        # coordinate_agreement — never guessed when the researcher gave no
        # coordinates (decision DCR-D005).
        radius = float(_decision_parameter(self.settings.decisions, "DCR-D005",
                                           "agreement_radius_km", 2.0))
        if community.latitude is None or community.longitude is None:
            self._write("coordinate_agreement", None, "review_required", method="rule",
                        rationale="no researcher coordinates were supplied, so agreement cannot "
                                  "be assessed. Writing 'no published location' would misreport "
                                  "a missing input as a documentary finding (DCR-D005).",
                        claim_ids=[], source_ids=[], groups=[], residual="", counts=counts)
            self.review.add(
                "coordinates", "Coordinate agreement not assessable",
                "No latitude/longitude was supplied, so coordinate_agreement is left blank "
                "rather than guessed. Supply the researcher's coordinates and re-run AUDIT.",
                severity="normal",
            )
        elif not coordinates:
            self._write("coordinate_agreement", "no published location", "coded", method="rule",
                        rationale="no retrieved source publishes a coordinate for this community",
                        claim_ids=[], source_ids=[], groups=[], residual="", counts=counts)
        else:
            distances = [
                (haversine_km(community.latitude, community.longitude, lat, lon), lat, lon, note)
                for lat, lon, note in coordinates
            ]
            nearest = min(distances, key=lambda d: d[0])
            agrees = nearest[0] <= radius
            self._write("coordinate_agreement", "agrees" if agrees else "differs", "coded",
                        method="rule",
                        rationale=f"nearest published location is {nearest[0]:.2f} km from the "
                                  f"researcher's coordinates (threshold {radius} km): "
                                  f"{nearest[3][:120]}",
                        claim_ids=[], source_ids=[], groups=[], residual="", counts=counts)
            if not agrees:
                self.review.add(
                    "coordinates", "Published location differs from the researcher's",
                    f"The nearest published coordinate is {nearest[0]:.2f} km away. Geocoded "
                    "directory coordinates are frequently a postal address in a neighbouring "
                    "village; check which is right before coding.",
                    severity="normal",
                )

    # -- provenance block --------------------------------------------------
    def _resolve_provenance(self, stages: Mapping[int, Any], truncation_reasons: Sequence[str],
                            languages: Iterable[str], counts: dict[str, int]) -> None:
        pages = self.db.scalar(
            "SELECT COUNT(DISTINCT normalized_url) FROM pages WHERE community_id=?",
            (self.community_id,)) or 0
        self._write("pages_opened_count", str(pages), "coded", method="crawl_audit",
                    rationale="distinct normalised URLs for which a response body was received, "
                              "including those that yielded nothing (DCR-D017)",
                    claim_ids=[], source_ids=[], groups=[], residual="", counts=counts)

        documents = self.db.query(
            "SELECT title, filename, extension FROM documents WHERE community_id=? "
            "ORDER BY document_id", (self.community_id,))
        titles = [f"{(r['title'] or r['filename'])} ({r['extension']})" for r in documents]
        self._write("documents_opened", "; ".join(titles[:80]) or NOT_FOUND,
                    "coded" if titles else "not_found", method="crawl_audit",
                    rationale=f"{len(titles)} files opened and parsed",
                    claim_ids=[], source_ids=[], groups=[], residual="", counts=counts)

        classes = sorted({r["source_class"] for r in self.db.query(
            "SELECT DISTINCT source_class FROM sources WHERE community_id=? "
            "AND source_class IS NOT NULL", (self.community_id,))})
        academic_found = self.db.scalar(
            "SELECT COUNT(*) FROM academic_records WHERE community_id=? AND verified_resolves='yes'",
            (self.community_id,)) or 0
        if academic_found and "S1" not in classes:
            classes.append("S1")
        self._write("source_classes_found", ";".join(sorted(classes)) or NOT_FOUND,
                    "coded" if classes else "not_found", method="crawl_audit",
                    rationale="source classes actually located in this run",
                    claim_ids=[], source_ids=[], groups=[], residual="", counts=counts)

        language_list = sorted({lang for lang in languages if lang})
        self._write("search_languages", "; ".join(language_list) or "en", "coded",
                    method="crawl_audit",
                    rationale="languages the searches were run in",
                    claim_ids=[], source_ids=[], groups=[], residual="", counts=counts)

        # negative_consultations is GENERATED from the search log, so the two
        # can never diverge (decision DCR-D016).
        negatives = self.db.query(
            "SELECT database_name, database_type, result FROM searches WHERE community_id=? "
            "AND result IN ('none found','unreachable') ORDER BY database_type, database_name",
            (self.community_id,))
        by_result: dict[str, list[str]] = {}
        for row in negatives:
            by_result.setdefault(row["result"], []).append(row["database_name"])
        parts = []
        for label, key in (("none found", "none found"), ("unreachable", "unreachable")):
            names = sorted(set(by_result.get(key, [])))
            if names:
                parts.append(f"{label}: " + ", ".join(names[:40]))
        self._write("negative_consultations", " | ".join(parts) or "none recorded",
                    "coded" if parts else "not_found", method="search_log",
                    rationale="generated from O7_Search_Log; 'unreachable' is kept distinct "
                              "from 'none found'",
                    claim_ids=[], source_ids=[], groups=[], residual="", counts=counts)

        groups = {r["independence_group"] for r in self.db.query(
            "SELECT DISTINCT independence_group FROM sources WHERE community_id=? "
            "AND independence_group IS NOT NULL", (self.community_id,))}
        # A verified thesis or a dated grant record is an independent voice even
        # when it is not a crawled web address. It is only counted separately if
        # no source row already represents it — otherwise it would be counted twice.
        verified_academic = self.db.scalar(
            "SELECT COUNT(*) FROM academic_records WHERE community_id=? AND verified_resolves='yes'",
            (self.community_id,)) or 0
        academic_sources = self.db.scalar(
            "SELECT COUNT(*) FROM sources WHERE community_id=? AND source_class='S1'",
            (self.community_id,)) or 0
        if verified_academic and not academic_sources:
            groups.add("G-ACAD")
        institutional_claims = self.db.scalar(
            "SELECT COUNT(*) FROM claims WHERE community_id=? AND source_class='S2' "
            "AND source_id IS NULL", (self.community_id,)) or 0
        if institutional_claims:
            groups.add("G-INST")
        group_count = len(groups)
        self._write("independence_groups", str(group_count), "coded", method="independence",
                    rationale="distinct independence groups across all sources; this is the "
                              "number Block D counts, not the number of URLs",
                    claim_ids=[], source_ids=[], groups=[], residual="", counts=counts)

        complete = [str(n) for n, s in sorted(stages.items()) if s.status == "complete"]
        partial = [f"{n} ({s.detail[:60]})" for n, s in sorted(stages.items())
                   if s.status == "partial"]
        blocked = [f"{n} ({s.detail[:60]})" for n, s in sorted(stages.items())
                   if s.status in ("blocked", "failed")]
        never = [str(n) for n, s in sorted(stages.items()) if s.status == "not_reached"]
        summary_parts = []
        if complete:
            summary_parts.append("complete: " + ", ".join(complete))
        if partial:
            summary_parts.append("cut short: " + "; ".join(partial))
        if blocked:
            summary_parts.append("blocked: " + "; ".join(blocked))
        if never:
            summary_parts.append("not reached: " + ", ".join(never))
        self._write("stages_completed", " | ".join(summary_parts), "coded", method="run_state",
                    rationale="generated from the recorded status of each stage, never asserted",
                    claim_ids=[], source_ids=[], groups=[], residual="", counts=counts)

        truncated = "yes" if truncation_reasons else "no"
        self._write("crawl_truncated", truncated, "coded", method="run_state",
                    rationale=("; ".join(truncation_reasons)[:900] if truncation_reasons
                               else "every stage in this run mode completed and no budget was "
                                    "exhausted with URLs still queued"),
                    claim_ids=[], source_ids=[], groups=[], residual="", counts=counts)

        # site_plan_published, from images actually retrieved.
        plan = self.db.query_one(
            "SELECT original_url, caption FROM images WHERE community_id=? "
            "AND image_type IN ('site plan','map') AND relevance_class='likely_relevant' "
            "ORDER BY relevance_score DESC LIMIT 1", (self.community_id,))
        if plan:
            self._write("site_plan_published", f"yes — {plan['original_url']}", "coded",
                        method="image_evidence",
                        rationale=f"a published plan or map was retrieved: "
                                  f"{(plan['caption'] or '')[:120]}",
                        claim_ids=[], source_ids=[], groups=[], residual="", counts=counts)
        else:
            self._write("site_plan_published", "no", "coded", method="image_evidence",
                        rationale="no published site plan or map was found in this run",
                        claim_ids=[], source_ids=[], groups=[], residual="", counts=counts)

        # area_type follows from which area figures were actually coded.
        managed = self._value("managed_area_ha")
        holding = self._value("total_holding_ha")
        if managed and holding:
            area_type = "both recorded"
        elif managed:
            area_type = "actively managed"
        elif holding:
            area_type = "total holding only"
        else:
            area_type = "not stated"
        self._write("area_type", area_type, "coded", method="rule",
                    rationale="follows from which area figures the sources actually stated",
                    claim_ids=[], source_ids=[], groups=[], residual="", counts=counts)
        if not managed:
            self._write("managed_area_basis", "not found", "coded", method="rule",
                        rationale="no source states a worked area; a complete and correct answer, "
                                  "and the researcher's polygon still gives the site its geometry",
                        claim_ids=[], source_ids=[], groups=[], residual="", counts=counts)

        funding = self.db.query(
            "SELECT DISTINCT value FROM claims WHERE community_id=? "
            "AND field_name='external_funding_or_programme'", (self.community_id,))
        values = [r["value"] for r in funding if r["value"]]
        self._write("external_funding_or_programme", "; ".join(values[:6]) or "none found",
                    "coded", method="grey_literature",
                    rationale="grant and programme records naming this community, from Stage 6",
                    claim_ids=[], source_ids=[], groups=[], residual="", counts=counts)

    # -- gaps --------------------------------------------------------------
    def _flag_priority_gaps(self, counts: dict[str, int]) -> None:
        priority = []
        for block in self.schema["blocks"].values():
            for field in block["fields"]:
                if field.get("priority"):
                    priority.append(field["name"])
        for field_name in priority:
            row = self.db.query_one(
                "SELECT value, status, group_count FROM field_values WHERE community_id=? "
                "AND field_name=?", (self.community_id, field_name))
            if row is None or row["status"] != "coded":
                self.review.add(
                    "priority_field", f"{field_name} is not coded",
                    f"{field_name} is a priority field for this study and no retrieved source "
                    "supports a value. Check crawl_truncated and the search log: an absence of "
                    "evidence and an absence of effort look identical in the data.",
                    severity="normal",
                )
            elif (row["group_count"] or 0) < 2:
                self.review.add(
                    "priority_field", f"{field_name} rests on one independence group",
                    f"{field_name} = {row['value']!r} is supported by a single independence "
                    "group. It is recorded, but it is not corroborated.",
                    severity="advisory",
                )

    # -- storage -----------------------------------------------------------
    def _write(self, field_name: str, value: str | None, status: str, *, method: str,
               rationale: str, claim_ids: Sequence[str], source_ids: Sequence[str],
               groups: Sequence[str], residual: str, counts: dict[str, int]) -> None:
        previous = self.db.query_one(
            "SELECT value FROM field_values WHERE community_id=? AND field_name=?",
            (self.community_id, field_name))
        self.db.upsert(
            "field_values",
            {
                "community_id": self.community_id,
                "field_name": field_name,
                "value": value,
                "status": status,
                "method": method,
                "claim_ids": "; ".join(claim_ids),
                "source_ids": "; ".join(source_ids),
                "independence_groups": "; ".join(groups),
                "group_count": len(set(groups)),
                "residual_uncertainty": residual[:2000],
                "rationale": rationale[:2000],
                "updated_utc": utcnow(),
            },
            ["community_id", "field_name"],
        )
        if previous and previous["value"] != value:
            change_id = self.db.next_id("field_change_log", "change_id", self.community_id, "CHG")
            self.db.insert(
                "field_change_log",
                {"change_id": change_id, "community_id": self.community_id,
                 "field_name": field_name, "old_value": previous["value"], "new_value": value,
                 "reason": method, "ts_utc": utcnow()},
                replace=True,
            )
        if status == "coded":
            counts["coded"] += 1
        elif status == "not_found":
            counts["not_found"] += 1
        elif status == "review_required":
            counts["review"] += 1

    def _value(self, field_name: str) -> str | None:
        row = self.db.query_one(
            "SELECT value FROM field_values WHERE community_id=? AND field_name=? "
            "AND status='coded'", (self.community_id, field_name))
        return row["value"] if row else None

    def _claims_for(self, field_name: str) -> list[ClaimView]:
        rows = self.db.query(
            "SELECT * FROM claims WHERE community_id=? AND field_name=?",
            (self.community_id, field_name))
        return [
            ClaimView(
                claim_id=row["claim_id"], field_name=field_name, value=str(row["value"]),
                source_id=row["source_id"], source_class=row["source_class"],
                independence_group=row["independence_group"],
                reference_year=row["reference_year"],
                publication_date=row["publication_date"],
                evidence_rank=row["evidence_rank"],
                confidence=float(row["confidence"] or 0.5),
                original_value=row["original_value"],
                exact_wording=row["exact_wording"],
                value_type=row["value_type"] or "text",
            )
            for row in rows
        ]

    def _store_conflict(self, conflict: Mapping[str, Any]) -> None:
        signature = (
            str(conflict.get("field_name")), str(conflict.get("value_a")),
            str(conflict.get("value_b")), str(conflict.get("source_a")),
            str(conflict.get("source_b")),
        )
        if signature in self._conflict_signatures:
            return
        self._conflict_signatures.add(signature)
        self.conflict_counter += 1
        conflict_id = f"{self.community_id}-X{self.conflict_counter:03d}"
        payload = {k: v for k, v in conflict.items()
                   if k in {
                       "field_name", "value_a", "claim_a", "source_a", "group_a", "rank_a",
                       "date_a", "value_b", "claim_b", "source_b", "group_b", "rank_b", "date_b",
                       "rule_invoked", "resolution_type", "final_value", "residual_uncertainty",
                       "human_review", "claims_a", "claims_b", "groups_a", "groups_b",
                       "distinct_values", "summary",
                   }}
        payload.update({"conflict_id": conflict_id, "community_id": self.community_id,
                        "created_utc": utcnow()})
        self.db.insert("conflicts", payload, replace=True)
        # One line per FIELD, not per disagreeing value. A field with fourteen
        # competing figures used to print fourteen near-identical lines, and a
        # run could end with thousands of them scrolling past.
        field_name = str(conflict.get("field_name") or "")
        if field_name not in self._conflict_fields_logged:
            self._conflict_fields_logged.add(field_name)
            event(log, "CONFLICT",
                  conflict.get("summary")
                  or f"{field_name}: {conflict.get('value_a')} vs {conflict.get('value_b')}")

    def _store_review_queue(self) -> None:
        for index, item in enumerate(self.review.items, start=1):
            self.db.insert(
                "review_queue",
                {
                    "item_id": f"{self.community_id}-RQ{index:03d}",
                    "community_id": self.community_id,
                    "category": item.category,
                    "subject": item.subject[:400],
                    "detail": item.detail[:4000],
                    "severity": item.severity,
                    "related_ids": item.related_ids,
                    "suggested_action": item.suggested_action,
                    "created_utc": utcnow(),
                },
                replace=True,
            )


def _decision_parameter(decisions: Mapping[str, Any], decision_id: str, key: str,
                        default: Any) -> Any:
    for entry in decisions.get("decisions", []):
        if entry.get("id") == decision_id:
            return (entry.get("parameters") or {}).get(key, default)
    return default
