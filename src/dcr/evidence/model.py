"""The evidence model: Source -> Document -> Evidence -> Claim -> Field.

One source yields many evidence items; one evidence item can support several
claims; one claim can contribute to several fields; one field can be supported
by several independent sources (brief §26).

Nothing reaches a workbook cell without an evidence row carrying the exact
wording behind it.
"""

from __future__ import annotations

import hashlib

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from ..db import Database, utcnow
from ..logging_setup import get_logger

log = get_logger("evidence")

# Fields whose values come from the satellite pipeline or the researcher's own
# drawing. A documentary claim on any of these is a hard validation failure.
FORBIDDEN_CLAIM_FIELDS: set[str] = set()


@dataclass
class EvidenceItem:
    evidence_type: str
    quote: str
    source_id: str | None = None
    document_id: str | None = None
    page_id: str | None = None
    image_id: str | None = None
    table_id: str | None = None
    locator: str | None = None
    section: str | None = None
    page_number: int | None = None
    context: str | None = None
    language: str | None = None
    source_class: str | None = None
    publication_date: str | None = None
    retrieval_date: str | None = None
    char_start: int | None = None
    char_end: int | None = None


@dataclass
class ClaimItem:
    field_name: str
    value: str
    value_type: str = "text"
    original_value: str | None = None
    normalized_value: str | None = None
    normalization_note: str | None = None
    exact_wording: str | None = None
    reference_year: int | None = None
    evidence_rank: int | None = None
    coding_level: str | None = None
    confidence: float = 0.5
    rationale: str | None = None
    extractor: str = "rule:unknown"
    model_name: str | None = None
    prompt_version: str | None = None
    locator: str | None = None
    notes: str | None = None
    verified_passage: bool = True



def evidence_dedupe_key(
    community_id: str,
    *,
    source_id: str | None = None,
    document_id: str | None = None,
    page_id: str | None = None,
    image_id: str | None = None,
    table_id: str | None = None,
    evidence_type: str = "",
    locator: str | None = None,
    quote: str = "",
) -> str:
    """What makes two evidence rows the same piece of evidence.

    One sentence, in one place, in one artefact. Character offsets are
    deliberately NOT part of the key: the same passage is often recorded once
    by a pass that knows where it sits and once by a pass that does not, and
    those are one piece of evidence, not two.
    """
    parts = (community_id, source_id or "", document_id or "", page_id or "",
             image_id or "", table_id or "", evidence_type or "", locator or "",
             " ".join((quote or "").split()))
    return hashlib.sha1("\u241f".join(parts).encode("utf-8")).hexdigest()


def claim_dedupe_key(community_id: str, field_name: str, value: Any,
                     evidence_id: str | None, extractor: str | None) -> str:
    """The same value, from the same passage, by the same extractor, is one claim."""
    parts = (community_id, field_name, str(value)[:4000],
             evidence_id or "", extractor or "")
    return hashlib.sha1("\u241f".join(parts).encode("utf-8")).hexdigest()


class EvidenceRecorder:
    """Writes evidence and claims, enforcing the anti-fabrication rules."""

    def __init__(self, db: Database, community_id: str, schema: dict[str, Any]):
        self.db = db
        self.community_id = community_id
        self.schema = schema
        self.forbidden = {str(q).lower() for q in schema.get("satellite_only_quantities", [])}
        self.known_fields = self._known_fields(schema)
        self.rejected: list[tuple[str, str]] = []

    @staticmethod
    def _known_fields(schema: dict[str, Any]) -> set[str]:
        names: set[str] = set()
        for block in schema.get("blocks", {}).values():
            for fld in block.get("fields", []):
                names.add(str(fld["name"]))
        return names

    # -- writing -----------------------------------------------------------
    @staticmethod
    def evidence_key(item: EvidenceItem, community_id: str) -> str:
        return evidence_dedupe_key(
            community_id, source_id=item.source_id, document_id=item.document_id,
            page_id=item.page_id, image_id=item.image_id, table_id=item.table_id,
            evidence_type=item.evidence_type, locator=item.locator, quote=item.quote)

    def add_evidence(self, item: EvidenceItem) -> str:
        """Record one piece of evidence, once.

        Reprocessing the same page must not double the record (brief §27): a
        resumed run, a retried task and a second pass over a document all reach
        the same passage again, and each time the answer must be the same row.
        """
        key = self.evidence_key(item, self.community_id)
        existing = self.db.query_one(
            "SELECT evidence_id, char_start, char_end, context FROM evidence "
            "WHERE community_id = ? AND dedupe_key = ?", (self.community_id, key))
        if existing is not None:
            self._enrich_evidence(existing, item)
            return existing["evidence_id"]

        evidence_id = self.db.next_id("evidence", "evidence_id", self.community_id, "E")
        self.db.insert(
            "evidence",
            {
                "evidence_id": evidence_id,
                "dedupe_key": key,
                "community_id": self.community_id,
                "source_id": item.source_id,
                "document_id": item.document_id,
                "page_id": item.page_id,
                "image_id": item.image_id,
                "table_id": item.table_id,
                "evidence_type": item.evidence_type,
                "locator": item.locator,
                "section": item.section,
                "page_number": item.page_number,
                "quote": item.quote[:8000],
                "context": (item.context or "")[:8000] or None,
                "language": item.language,
                "source_class": item.source_class,
                "publication_date": item.publication_date,
                "retrieval_date": item.retrieval_date,
                "char_start": item.char_start,
                "char_end": item.char_end,
                "created_utc": utcnow(),
            },
        )
        if item.source_id:
            self.db.bump("sources", "evidence_count", {"source_id": item.source_id})
        return evidence_id

    def _enrich_evidence(self, existing: Any, item: EvidenceItem) -> None:
        """Fill in what the first recording of this passage did not know.

        A later pass may have found the character offsets the first one lacked.
        Nothing already recorded is overwritten — only gaps are filled.
        """
        updates: dict[str, Any] = {}
        if existing["char_start"] is None and item.char_start is not None:
            updates["char_start"] = item.char_start
            updates["char_end"] = item.char_end
        if not existing["context"] and item.context:
            updates["context"] = item.context[:8000]
        if updates:
            self.db.update("evidence", updates,
                           {"evidence_id": existing["evidence_id"]})

    def add_claim(self, claim: ClaimItem, evidence_id: str, context: dict[str, Any]) -> str | None:
        """Record a claim. Returns None when the claim is refused."""
        field_name = claim.field_name
        if field_name.lower() in self.forbidden:
            self.rejected.append((field_name, "satellite-only quantity; documentary coding forbidden"))
            log.warning("[REFUSED] claim on satellite-only field %s", field_name)
            return None
        if not field_name.startswith("context_") and field_name not in self.known_fields:
            self.rejected.append((field_name, "not a field in the canonical schema"))
            log.warning("[REFUSED] claim on unknown field %s", field_name)
            return None
        if claim.value is None or str(claim.value).strip() == "":
            self.rejected.append((field_name, "empty value"))
            return None

        # The same value, drawn from the same passage by the same extractor, is
        # one claim however many times the passage is read (brief §27).
        key = claim_dedupe_key(self.community_id, field_name, claim.value,
                               evidence_id, claim.extractor)
        existing = self.db.query_one(
            "SELECT claim_id FROM claims WHERE community_id = ? AND dedupe_key = ?",
            (self.community_id, key))
        if existing is not None:
            return existing["claim_id"]

        claim_id = self.db.next_id("claims", "claim_id", self.community_id, "C")
        self.db.insert(
            "claims",
            {
                "claim_id": claim_id,
                "dedupe_key": key,
                "community_id": self.community_id,
                "field_name": field_name,
                "value": str(claim.value)[:4000],
                "value_type": claim.value_type,
                "original_value": (claim.original_value or str(claim.value))[:2000],
                "normalized_value": claim.normalized_value,
                "normalization_note": claim.normalization_note,
                "exact_wording": (claim.exact_wording or "")[:4000] or None,
                "source_id": context.get("source_id"),
                "document_id": context.get("document_id"),
                "evidence_id": evidence_id,
                "image_id": context.get("image_id"),
                "locator": claim.locator or context.get("locator"),
                "publication_date": context.get("publication_date"),
                "reference_year": claim.reference_year,
                "retrieval_date": context.get("retrieval_date"),
                "source_class": context.get("source_class"),
                "independence_group": context.get("independence_group"),
                "evidence_rank": claim.evidence_rank,
                "coding_level": claim.coding_level,
                "confidence": claim.confidence,
                "conflict_status": "none",
                "rationale": claim.rationale,
                "extractor": claim.extractor,
                "model_name": claim.model_name,
                "prompt_version": claim.prompt_version,
                "extracted_utc": utcnow(),
                "verified_passage": int(claim.verified_passage),
                "notes": claim.notes,
            },
        )
        return claim_id

    def record(self, evidence: EvidenceItem, claims: Sequence[ClaimItem],
               context: dict[str, Any]) -> tuple[str, list[str]]:
        """The usual path: one passage, one or more claims drawn from it."""
        evidence_id = self.add_evidence(evidence)
        claim_ids: list[str] = []
        merged = dict(context)
        merged.setdefault("source_class", evidence.source_class)
        merged.setdefault("publication_date", evidence.publication_date)
        merged.setdefault("retrieval_date", evidence.retrieval_date)
        merged.setdefault("document_id", evidence.document_id)
        merged.setdefault("locator", evidence.locator)
        for claim in claims:
            claim_id = self.add_claim(claim, evidence_id, merged)
            if claim_id:
                claim_ids.append(claim_id)
        return evidence_id, claim_ids

    # -- verification ------------------------------------------------------
    def verify_passage(self, quote: str, haystack: str) -> bool:
        """Confirm a quoted passage really occurs in the stored text.

        This is what stops an LLM (or a buggy rule) inventing a supporting
        sentence: the passage must be present, character for character, modulo
        whitespace (decision DCR-D015).
        """
        if not quote or not haystack:
            return False
        needle = _squash(quote)
        return needle in _squash(haystack)


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def sentences(text: str) -> list[tuple[int, int, str]]:
    """Split into sentences, keeping character offsets so a quote is locatable."""
    if not text:
        return []
    out: list[tuple[int, int, str]] = []
    start = 0
    for match in re.finditer(r"(?<=[.!?;:])\s+|\n+", text):
        end = match.start()
        chunk = text[start:end].strip()
        if chunk:
            out.append((start, end, chunk))
        start = match.end()
    tail = text[start:].strip()
    if tail:
        out.append((start, len(text), tail))
    return [(s, e, c) for s, e, c in out if len(c) > 2]


def window(text: str, start: int, end: int, *, before: int = 200, after: int = 200) -> str:
    """The surrounding context of a passage, for the evidence row."""
    return text[max(0, start - before): min(len(text), end + after)].strip()
