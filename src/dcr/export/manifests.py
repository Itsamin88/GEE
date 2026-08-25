"""CSV and JSONL manifests written beside the workbook.

These are the machine-readable twin of the workbook's supplementary sheets, so
the evidence can be re-read without opening Excel (brief §72).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ..db import Database


def write_csv(path: Path, headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(["" if v is None else v for v in row])
            count += 1
    return count


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(dict(record), ensure_ascii=False, default=str) + "\n")
            count += 1
    return count


def export_all(db: Database, community_id: str, final_dir: Path) -> dict[str, int]:
    """Write every manifest for one community."""
    counts: dict[str, int] = {}

    counts["source_manifest.csv"] = write_csv(
        final_dir / "source_manifest.csv",
        ["source_id", "address_id", "url", "canonical_url", "domain", "platform_type",
         "source_class", "supplied_or_discovered", "discovery_method", "independence_group",
         "independence_reason", "language", "http_status", "access_status", "crawl_status",
         "first_discovered", "last_crawled", "archive_checked", "archive_earliest_snapshot",
         "pages_opened", "documents_found", "images_found", "evidence_count", "notes"],
        (
            [r["source_id"], r["address_id"], r["url"], r["canonical_url"], r["domain"],
             r["platform_type"], r["source_class"], r["supplied_or_discovered"],
             r["discovery_method"], r["independence_group"], r["independence_reason"],
             r["language"], r["http_status"], r["access_status"], r["crawl_status"],
             r["first_discovered_utc"], r["last_crawled_utc"], r["archive_checked"],
             r["archive_earliest_snapshot"], r["pages_opened"], r["documents_found"],
             r["images_found"], r["evidence_count"], r["notes"]]
            for r in db.query("SELECT * FROM sources WHERE community_id=? ORDER BY source_id",
                              (community_id,))
        ),
    )

    counts["evidence_manifest.csv"] = write_csv(
        final_dir / "evidence_manifest.csv",
        ["evidence_id", "source_id", "document_id", "page_id", "image_id", "evidence_type",
         "locator", "page_number", "source_class", "publication_date", "retrieval_date",
         "language", "quote"],
        (
            [r["evidence_id"], r["source_id"], r["document_id"], r["page_id"], r["image_id"],
             r["evidence_type"], r["locator"], r["page_number"], r["source_class"],
             r["publication_date"], r["retrieval_date"], r["language"], (r["quote"] or "")[:4000]]
            for r in db.query("SELECT * FROM evidence WHERE community_id=? ORDER BY evidence_id",
                              (community_id,))
        ),
    )

    counts["image_manifest.csv"] = write_csv(
        final_dir / "image_manifest.csv",
        ["image_id", "community_id", "source_id", "document_id", "filename", "local_path",
         "original_url", "page_number", "source_title", "publication_date", "image_type",
         "research_topic", "caption", "surrounding_text_summary", "evidence_subject",
         "possible_relevant_fields", "visual_evidence_allowed", "documentary_text_support",
         "image_date_if_known", "image_date_confidence", "OCR_text_if_used", "relevance_class",
         "relevance_reason", "confidence", "width", "height", "bytes", "sha256", "notes"],
        (
            [r["image_id"], community_id, r["source_id"], r["document_id"], r["filename"],
             r["local_path"], r["original_url"], r["page_number"], r["source_title"],
             r["publication_date"], r["image_type"], r["research_topic"],
             (r["caption"] or "")[:1000], r["surrounding_summary"], r["evidence_subject"],
             r["possible_fields"], r["visual_evidence_allowed"], r["documentary_text_support"],
             r["image_date"], r["image_date_confidence"], (r["ocr_text"] or "")[:1000],
             r["relevance_class"], r["relevance_reason"], r["confidence"], r["width"],
             r["height"], r["bytes"], r["sha256"], r["notes"]]
            for r in db.query("SELECT * FROM images WHERE community_id=? ORDER BY image_id",
                              (community_id,))
        ),
    )

    counts["document_manifest.csv"] = write_csv(
        final_dir / "document_manifest.csv",
        ["document_id", "title", "filename", "extension", "mime_sniffed", "bytes", "sha256",
         "storage_path", "page_count", "publication_date", "doc_kind", "parser_status",
         "text_status", "table_status", "image_status", "source_ids", "original_urls"],
        (
            [r["document_id"], r["title"], r["filename"], r["extension"], r["mime_sniffed"],
             r["bytes"], r["sha256"], r["storage_path"], r["page_count"], r["publication_date"],
             r["doc_kind"], r["parser_status"], r["text_status"], r["table_status"],
             r["image_status"],
             "; ".join(str(l["source_id"]) for l in db.query(
                 "SELECT source_id FROM document_sources WHERE document_id=?",
                 (r["document_id"],))),
             "; ".join(str(l["original_url"]) for l in db.query(
                 "SELECT original_url FROM document_sources WHERE document_id=?",
                 (r["document_id"],)))[:2000]]
            for r in db.query("SELECT * FROM documents WHERE community_id=? ORDER BY document_id",
                              (community_id,))
        ),
    )

    counts["search_log.csv"] = write_csv(
        final_dir / "search_log.csv",
        ["search_id", "stage", "database_name", "database_type", "query", "language",
         "hits_returned", "full_text_opened", "abstract_only", "result", "http_status",
         "detail", "searched"],
        (
            [r["search_id"], r["stage"], r["database_name"], r["database_type"], r["query"],
             r["language"], r["hits_returned"], r["full_text_opened"], r["abstract_only"],
             r["result"], r["http_status"], r["detail"], r["searched_utc"]]
            for r in db.query("SELECT * FROM searches WHERE community_id=? ORDER BY searched_utc",
                              (community_id,))
        ),
    )

    counts["claims.jsonl"] = write_jsonl(
        final_dir / "claims.jsonl",
        (dict(r) for r in db.query(
            "SELECT * FROM claims WHERE community_id=? ORDER BY claim_id", (community_id,))),
    )

    counts["errors.jsonl"] = write_jsonl(
        final_dir / "errors.jsonl",
        (dict(r) for r in db.query(
            "SELECT * FROM errors WHERE community_id=? ORDER BY ts_utc", (community_id,))),
    )

    counts["review_queue.jsonl"] = write_jsonl(
        final_dir / "review_queue.jsonl",
        (dict(r) for r in db.query(
            "SELECT * FROM review_queue WHERE community_id=? ORDER BY item_id", (community_id,))),
    )

    counts["conflicts.jsonl"] = write_jsonl(
        final_dir / "conflicts.jsonl",
        (dict(r) for r in db.query(
            "SELECT * FROM conflicts WHERE community_id=? ORDER BY conflict_id", (community_id,))),
    )

    counts["field_values.csv"] = write_csv(
        final_dir / "field_values.csv",
        ["field_name", "value", "status", "method", "independence_groups", "group_count",
         "source_ids", "claim_ids", "residual_uncertainty", "rationale"],
        (
            [r["field_name"], r["value"], r["status"], r["method"], r["independence_groups"],
             r["group_count"], r["source_ids"], r["claim_ids"], r["residual_uncertainty"],
             r["rationale"]]
            for r in db.query(
                "SELECT * FROM field_values WHERE community_id=? ORDER BY field_name",
                (community_id,))
        ),
    )
    return counts
