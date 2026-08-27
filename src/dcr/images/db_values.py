"""Turning an image candidate into the row the ledger stores.

Kept apart from the triage logic so that adding a provenance column is a change
in one obvious place, and so the triage module reads as decisions rather than
as column names.
"""

from __future__ import annotations

from typing import Any

from ..db import utcnow


def candidate_row(candidate: Any, *, community_id: str, run_id: str | None,
                  image_id: str | None = None, sha256: str | None = None,
                  times_seen: int = 1) -> dict[str, Any]:
    """Every field of §6 and §10 that is known without opening the image."""
    classification = candidate.classification
    return {
        "candidate_id": candidate.candidate_id,
        "community_id": community_id,
        "run_id": run_id,
        "source_id": candidate.source_id,
        "document_id": candidate.document_id,
        "page_id": candidate.page_id,
        "image_id": image_id,
        "url_key": candidate.url_key,
        "original_url": candidate.original_url,
        "page_url": candidate.page_url,
        "archive_url": candidate.archive_url,
        "origin": candidate.origin,
        "filename": candidate.filename,
        "alt_text": _trim(candidate.alt_text, 1000),
        "title_text": _trim(candidate.title_text, 1000),
        "caption": _trim(candidate.caption, 2000),
        "surrounding_text": _trim(candidate.surrounding_text, 4000),
        "page_heading": _trim(candidate.page_heading, 500),
        "document_title": _trim(candidate.document_title, 500),
        "page_number": candidate.page_number,
        "figure_number": candidate.figure_number,
        "extraction_method": candidate.extraction_method,
        "width": candidate.width,
        "height": candidate.height,
        "bytes": candidate.bytes,
        "mime_type": candidate.mime_type,
        "publication_date": candidate.publication_date,
        "image_date": getattr(classification, "image_date", None),
        "source_class": candidate.source_class,
        "independence_group": candidate.independence_group,
        "image_type": getattr(classification, "image_type", None),
        "research_topic": getattr(classification, "research_topic", None),
        "relevance_class": getattr(classification, "relevance_class", None),
        "priority": candidate.priority,
        "priority_rank": candidate.priority_rank,
        "relevance_score": getattr(classification, "score", None),
        "relevance_reason": _trim(getattr(classification, "reason", ""), 1000),
        "possible_fields": "; ".join(getattr(classification, "possible_fields", []) or []),
        "documentary_text_support": _trim(
            getattr(classification, "documentary_text_support", ""), 1000),
        "decision": candidate.decision,
        "decision_reason": _trim(candidate.decision_reason, 1000),
        "sha256": sha256,
        "stage": candidate.stage,
        "times_seen": times_seen,
        "seen_utc": utcnow(),
        "decided_utc": utcnow(),
    }


def _trim(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    return text[:limit] if text else None
