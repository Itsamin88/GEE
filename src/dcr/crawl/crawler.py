"""The crawl engine.

Adaptive, platform-aware and evidence-first. It fetches what the frontier
offers, stores every artefact with its provenance, extracts documents and
images, feeds new URLs back into the frontier, and stops spending on a source
when that source stops paying (brief §9-§13, §39).

One failure never stops the run: every error is caught, classified and recorded.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from ..db import Database, utcnow
from ..discovery.wayback import parse_archive_url
from ..extract.dispatch import Extraction, extract as extract_file
from ..extract.html import ParsedPage, parse_html
from ..ids import image_filename, safe_name
from ..images.classify import classify_image, summarise_surrounding
from ..logging_setup import event, get_logger
from ..net.browser import BrowserPool, looks_javascript_rendered
from ..net.fetcher import FetchResult, Fetcher
from ..net.mime import is_html
from ..storage import CommunityStorage
from .frontier import Frontier, SourceBudget
from .normalize import TrapDetector, classify_url, normalize, registrable_domain, same_site
from .platform import detect_platform, is_website_like

log = get_logger("crawl")

DECORATIVE = "decorative"


@dataclass
class CrawlStats:
    pages_opened: int = 0
    pages_yielding: int = 0
    documents: int = 0
    images_kept: int = 0
    images_rejected: int = 0
    urls_discovered: int = 0
    external_candidates: int = 0
    blocked: int = 0
    failed: int = 0
    browser_renders: int = 0
    traps_avoided: int = 0
    robots_denied: int = 0

    def as_dict(self) -> dict[str, int]:
        return dict(self.__dict__)


@dataclass
class SourceContext:
    """Everything the crawler needs to know about one address it is working on."""

    source_id: str
    url: str
    platform_type: str
    source_class: str
    retrieval_priority: str
    independence_group: str | None
    login_walled: bool
    budget: SourceBudget
    scope_domains: set[str] = field(default_factory=set)
    language: str | None = None


class Crawler:
    """Fetch, store, extract, discover. One instance per community run."""

    def __init__(
        self,
        *,
        db: Database,
        storage: CommunityStorage,
        fetcher: Fetcher,
        frontier: Frontier,
        community_id: str,
        config: Mapping[str, Any],
        lexicon: Mapping[str, Any],
        browser: BrowserPool | None = None,
        on_page: Callable[[str, ParsedPage, dict[str, Any]], int] | None = None,
        on_document: Callable[[str, Extraction, dict[str, Any]], int] | None = None,
    ):
        self.db = db
        self.storage = storage
        self.fetcher = fetcher
        self.frontier = frontier
        self.community_id = community_id
        self.config = config
        self.lexicon = lexicon
        self.browser = browser
        self.on_page = on_page
        self.on_document = on_document

        crawl_cfg = dict(config.get("crawl", {}))
        self.max_depth = int(crawl_cfg.get("max_depth", 6))
        self.min_depth = int(crawl_cfg.get("min_depth", 3))
        self.max_pages_per_run = int(crawl_cfg.get("max_pages_per_run", 4000))
        self.prefer_oldest = bool(crawl_cfg.get("prefer_oldest_first", True))
        self.trap = TrapDetector(
            crawl_cfg.get("trap_patterns"),
            max_query_params=int(crawl_cfg.get("max_query_params", 6)),
            max_path_segments=int(crawl_cfg.get("max_path_segments", 12)),
            max_same_path_variants=int(crawl_cfg.get("max_same_path_variants", 40)),
        )
        browser_cfg = dict(config.get("browser", {}))
        self.min_static_chars = int(browser_cfg.get("min_text_chars_for_static", 400))
        self.max_browser_pages = int(browser_cfg.get("max_browser_pages_per_source", 40))
        image_cfg = dict(config.get("images", {}))
        self.image_enabled = bool(image_cfg.get("enabled", True))
        self.image_min_bytes = int(image_cfg.get("min_bytes", 12000))
        self.image_min_width = int(image_cfg.get("min_width", 320))
        self.image_min_height = int(image_cfg.get("min_height", 240))
        self.image_keep = set(image_cfg.get("keep_classes",
                                            ["likely_relevant", "possibly_relevant", "uncertain"]))
        self.max_images_per_source = int(image_cfg.get("max_images_per_source", 400))
        self.max_images_per_community = int(image_cfg.get("max_images_per_community", 1500))

        self.stats = CrawlStats()
        self.sources: dict[str, SourceContext] = {}
        self.external_candidates: dict[str, dict[str, Any]] = {}
        self._image_hashes: set[str] = set()
        self._document_hashes: dict[str, str] = {}
        self._browser_renders: dict[str, int] = {}
        self._announced_exhausted: set[str] = set()
        self._unregistered: dict[str, SourceContext] = {}
        self._archive_template: str | None = None
        self._platform_patterns: dict[str, list[str]] = {}
        self._load_existing_hashes()

    # -- setup -------------------------------------------------------------
    def _load_existing_hashes(self) -> None:
        """Resume-safe: know what is already stored before fetching anything."""
        for row in self.db.query(
            "SELECT sha256, document_id FROM documents WHERE community_id = ?", (self.community_id,)
        ):
            self._document_hashes[row["sha256"]] = row["document_id"]
        for row in self.db.query(
            "SELECT sha256 FROM images WHERE community_id = ?", (self.community_id,)
        ):
            self._image_hashes.add(row["sha256"])

    def register_source(self, context: SourceContext) -> None:
        self.sources[context.source_id] = context

    def source_for(self, source_id: str | None) -> SourceContext | None:
        """The registered context, or a read-only one rebuilt from the database.

        Stages 5 and 6 queue individual documents against sources that were
        never registered for page crawling. Without this fallback their class
        defaults to the community's own, and a thesis coded as S4 can never
        upgrade a practice to `evidenced`.
        """
        if not source_id:
            return None
        context = self.sources.get(source_id)
        if context is not None:
            return context
        if source_id in self._unregistered:
            return self._unregistered[source_id]
        row = self.db.query_one(
            "SELECT * FROM sources WHERE source_id = ?", (source_id,))
        if row is None:
            return None
        context = SourceContext(
            source_id=source_id,
            url=row["url"],
            platform_type=row["platform_type"] or "other",
            source_class=row["source_class"] or "S4",
            retrieval_priority=row["retrieval_priority"] or "C",
            independence_group=row["independence_group"],
            login_walled=False,
            budget=SourceBudget(source_id, base=10 ** 6, maximum=10 ** 6),
            scope_domains={registrable_domain(row["url"])},
            language=row["language"],
        )
        self._unregistered[source_id] = context
        return context

    # -- the loop ----------------------------------------------------------
    async def run(self, *, stage: int, batch_size: int = 6,
                  page_limit: int | None = None) -> CrawlStats:
        """Work the frontier until it is empty, budgets are spent, or the cap is hit."""
        opened = 0
        cap = page_limit if page_limit is not None else self.max_pages_per_run
        while opened < cap:
            batch = self.frontier.next_batch(min(batch_size, cap - opened))
            if not batch:
                break
            tasks = [self._handle(item, stage) for item in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for item, outcome in zip(batch, results):
                if isinstance(outcome, Exception):
                    # A bug in one handler must not end the crawl.
                    log.error("handler failed for %s: %s", item.url, outcome, exc_info=outcome)
                    self.frontier.complete(item.url_key, "failed", str(outcome))
                    self._record_error(url=item.url, source_id=item.source_id, stage=stage,
                                       error_type="handler_exception", detail=str(outcome))
            opened += len(batch)
        return self.stats

    async def _handle(self, item: Any, stage: int) -> None:
        context = self.source_for(item.source_id)
        # Stages 4-8 queue individually chosen, high-value targets: an archived
        # snapshot, a verified thesis, a grant record. They must not be refused
        # because the live site's page budget happens to be spent.
        budget_governed = (item.stage or stage) in (2, 3, 7)
        if context and context.budget.exhausted and budget_governed:
            self.frontier.complete(item.url_key, "skipped", context.budget.exhausted_reason)
            return

        reason = self.trap.check(item.normalized_url)
        if reason:
            self.stats.traps_avoided += 1
            self.frontier.complete(item.url_key, "skipped", f"crawler trap: {reason}")
            self._log_discovery(stage, "trap", item.normalized_url, "out_of_scope", reason)
            return

        kind = item.kind or classify_url(item.normalized_url)
        if kind == "document":
            await self._fetch_document(item, context, stage)
        elif kind == "image":
            await self._fetch_standalone_image(item, context, stage)
        else:
            await self._fetch_page(item, context, stage)

    # -- pages -------------------------------------------------------------
    async def _fetch_page(self, item: Any, context: SourceContext | None, stage: int) -> None:
        result = await self.fetcher.fetch(
            item.normalized_url, kind="page", community_id=self.community_id,
            source_id=item.source_id, stage=stage,
        )
        if not result.ok:
            self._after_failed_fetch(item, context, result, stage)
            return

        render_mode = "http"
        html_text = result.text or ""
        if is_html(result.mime or "") and self.browser is not None:
            needs_browser, why = looks_javascript_rendered(html_text, self.min_static_chars)
            budget_key = item.source_id or "global"
            if needs_browser and self._browser_renders.get(budget_key, 0) < self.max_browser_pages:
                rendered = await self.browser.render(item.normalized_url)
                if rendered.ok and rendered.html:
                    html_text = rendered.html
                    render_mode = "browser"
                    self._browser_renders[budget_key] = self._browser_renders.get(budget_key, 0) + 1
                    self.stats.browser_renders += 1
                    event(log, "RENDER", f"browser used for {item.normalized_url} ({why})")
                else:
                    self._record_error(
                        url=item.normalized_url, source_id=item.source_id, stage=stage,
                        error_type="js_required",
                        detail=f"{why}; browser unavailable or failed: {rendered.error}",
                        unresolved=True, human_review=False,
                    )
            elif needs_browser:
                self._record_error(
                    url=item.normalized_url, source_id=item.source_id, stage=stage,
                    error_type="js_required",
                    detail=f"{why}; browser budget for this source is spent",
                )

        if not is_html(result.mime or ""):
            # The URL looked like a page but the bytes are a file. Treat it as one.
            archived = parse_archive_url(item.normalized_url)
            await self._store_document_bytes(item.normalized_url, result, context, stage,
                                             url_key=item.url_key,
                                             archive_timestamp=archived[0] if archived else None)
            return

        page_id = self.db.next_id("pages", "page_id", self.community_id, "P")
        archived_here = parse_archive_url(item.normalized_url)
        # An archived page's relative links point at the site as it was, not at
        # the archive. Resolving them against the archive host would invent
        # addresses like archive.org/about and attribute them to the community.
        link_base = archived_here[1] if archived_here else (
            result.final_url or item.normalized_url)
        parsed = parse_html(html_text, link_base)

        raw_path = self.storage.write_text(
            self.storage.raw, self.storage.raw_page_path(page_id, "html"), html_text
        )
        text_path = self.storage.write_text(
            self.storage.text, self.storage.text_path(page_id), parsed.text
        )

        archived = archived_here
        archive_timestamp = archived[0] if archived else None
        self.db.insert(
            "pages",
            {
                "page_id": page_id,
                "community_id": self.community_id,
                "source_id": item.source_id,
                "url": item.url,
                "normalized_url": item.normalized_url,
                "final_url": result.final_url,
                "http_status": result.status,
                "content_type": result.mime,
                "bytes": result.bytes_len,
                "sha256": self.storage.content_hash(result.content or b""),
                "title": parsed.title[:500],
                "language": parsed.html_lang or (context.language if context else None),
                "published_date": parsed.published_date,
                "archive_timestamp": archive_timestamp,
                "archived_original": archived[1] if archived else None,
                "depth": item.depth,
                "discovery_method": item.discovered_by,
                "render_mode": render_mode,
                "text_path": self.storage.relative(text_path),
                "text_chars": len(parsed.text),
                "stage": stage,
                "fetched_utc": result.fetched_utc,
                "notes": self.storage.relative(raw_path),
            },
            replace=True,
        )
        self.stats.pages_opened += 1

        if context and parsed.platform_engine:
            self.db.upsert("domains",
                           {"domain": registrable_domain(item.normalized_url),
                            "platform_engine": parsed.platform_engine,
                            "checked_utc": utcnow()}, ["domain"])

        evidence_count = 0
        if self.on_page is not None:
            try:
                evidence_count = self.on_page(page_id, parsed, {
                    "source_id": item.source_id,
                    "url": item.normalized_url,
                    "final_url": result.final_url,
                    "stage": stage,
                    "source_class": context.source_class if context else "S4",
                    "independence_group": context.independence_group if context else None,
                    "published_date": parsed.published_date,
                    "retrieval_date": result.fetched_utc[:10],
                    "archive_timestamp": archive_timestamp,
                })
            except Exception as exc:
                log.error("evidence extraction failed for %s: %s", page_id, exc, exc_info=True)
                self._record_error(url=item.normalized_url, source_id=item.source_id, stage=stage,
                                   error_type="evidence_extraction_failed", detail=str(exc))

        if evidence_count:
            self.db.update("pages", {"yielded_evidence": 1}, {"page_id": page_id})
            self.stats.pages_yielding += 1

        new_urls = self._queue_links(parsed, item, context, stage,
                                     archive_timestamp=archive_timestamp)
        if self.image_enabled:
            await self._harvest_page_images(parsed, page_id, item, context, stage)

        if context:
            context.budget.record(yielded_evidence=bool(evidence_count), new_urls=new_urls)
            self.db.bump("sources", "pages_opened", {"source_id": context.source_id})
            self.db.update("sources", {"last_crawled_utc": utcnow(),
                                       "budget_spent": context.budget.spent},
                           {"source_id": context.source_id})
            if context.budget.exhausted and context.source_id not in self._announced_exhausted:
                self._announced_exhausted.add(context.source_id)
                event(log, "BUDGET",
                      f"{context.source_id} exhausted — {context.budget.exhausted_reason}")
        self.frontier.complete(item.url_key, "done")

    def _after_failed_fetch(self, item: Any, context: SourceContext | None,
                            result: FetchResult, stage: int) -> None:
        if result.access_status in ("blocked", "login_required"):
            self.stats.blocked += 1
            platform = context.platform_type if context else "page"
            event(log, "BLOCKED", f"{platform}: {item.normalized_url} — {result.error_detail}")
            if context:
                self.db.update("sources",
                               {"access_status": result.access_status,
                                "crawl_status": "blocked",
                                "http_status": result.status,
                                "notes": (result.error_detail or "")[:500],
                                "last_crawled_utc": utcnow()},
                               {"source_id": context.source_id})
        else:
            self.stats.failed += 1
        if result.error_type == "robots_denied":
            self.stats.robots_denied += 1
        status = "skipped" if result.is_permanent_failure else "failed"
        self.frontier.complete(item.url_key, status, result.error_detail)
        if context:
            context.budget.record_failure()

    # -- link discovery ----------------------------------------------------
    def _queue_links(self, parsed: ParsedPage, item: Any,
                     context: SourceContext | None, stage: int,
                     *, archive_timestamp: str | None = None) -> int:
        """Queue in-scope links; record out-of-scope ones as candidate sources."""
        added = 0
        depth = item.depth + 1
        scope = context.scope_domains if context else set()
        if not scope:
            scope = {registrable_domain(item.normalized_url)}
        priority = context.retrieval_priority if context else "B"
        archive_template = self._archive_template if archive_timestamp else None

        def queue(url: str, method: str, *, kind: str | None = None) -> None:
            nonlocal added
            normalized = normalize(url, item.normalized_url)
            if not normalized:
                return
            resolved_kind = kind or classify_url(normalized)
            in_scope = registrable_domain(normalized) in scope
            if not in_scope:
                # Never wander onto an unrelated site (brief §12). Record it as a
                # candidate source instead, for Stage 0 to decide on.
                self._note_external(normalized, item, method)
                return
            if resolved_kind == "page" and depth > self.max_depth:
                return
            if archive_template and archive_timestamp:
                # Keep following the site as it was on that date.
                normalized = archive_template.format(timestamp=archive_timestamp,
                                                     url=normalized)
                normalized = normalize(normalized) or normalized
            if self.frontier.add(normalized, source_id=item.source_id, depth=depth,
                                 kind=resolved_kind, stage=stage,
                                 discovery_method=method, source_priority=priority,
                                 prefer_oldest=self.prefer_oldest):
                added += 1
                self.stats.urls_discovered += 1
                self._log_discovery(stage, method, normalized, "new_url", item.normalized_url)

        for url in parsed.nav_links:
            queue(url, "nav")
        for url in parsed.footer_links:
            queue(url, "footer")
        for url in parsed.pagination_links:
            queue(url, "pagination")
        for url, _ in parsed.document_links:
            queue(url, "link", kind="document")
        for url in parsed.feeds:
            queue(url, "feed", kind="page")
        for url, _ in parsed.links:
            queue(url, "link")
        for url in parsed.social_links:
            self._note_external(url, item, "footer")
        return added

    def _note_external(self, url: str, item: Any, method: str) -> None:
        normalized = normalize(url)
        if not normalized:
            return
        domain = registrable_domain(normalized)
        entry = self.external_candidates.setdefault(
            domain,
            {"domain": domain, "urls": [], "count": 0, "first_seen_on": item.normalized_url,
             "methods": set()},
        )
        entry["count"] += 1
        entry["methods"].add(method)
        entry.setdefault("platforms", set()).add(
            detect_platform(normalized, self._platform_patterns))
        if normalized not in entry["urls"] and len(entry["urls"]) < 8:
            entry["urls"].append(normalized)
        self.stats.external_candidates += 1

    # -- documents ---------------------------------------------------------
    async def _fetch_document(self, item: Any, context: SourceContext | None, stage: int) -> None:
        result = await self.fetcher.fetch(
            item.normalized_url, kind="document", community_id=self.community_id,
            source_id=item.source_id, stage=stage,
        )
        if not result.ok:
            self._after_failed_fetch(item, context, result, stage)
            return
        archived = parse_archive_url(item.normalized_url)
        await self._store_document_bytes(item.normalized_url, result, context, stage,
                                         url_key=item.url_key,
                                         archive_timestamp=archived[0] if archived else None,
                                         discovery_method=item.discovered_by or "link")

    async def _store_document_bytes(
        self,
        url: str,
        result: FetchResult,
        context: SourceContext | None,
        stage: int,
        *,
        url_key: str | None = None,
        archive_timestamp: str | None = None,
        discovery_method: str = "link",
    ) -> str | None:
        data = result.content or b""
        if not data:
            if url_key:
                self.frontier.complete(url_key, "failed", "empty body")
            return None

        digest = self.storage.content_hash(data)
        filename = safe_name(url.rsplit("/", 1)[-1].split("?")[0] or "document", max_length=100)
        source_id = context.source_id if context else None

        existing = self._document_hashes.get(digest)
        if existing:
            # Same bytes, different address: one file, two provenances (DCR-D018).
            if source_id:
                self.db.insert(
                    "document_sources",
                    {"document_id": existing, "source_id": source_id, "original_url": url,
                     "final_url": result.final_url, "archive_timestamp": archive_timestamp,
                     "discovery_stage": stage, "discovery_method": discovery_method,
                     "retrieved_utc": result.fetched_utc},
                    replace=True,
                )
            event(log, "DOC", f"duplicate content, provenance added: {filename} -> {existing}")
            if url_key:
                self.frontier.complete(url_key, "done")
            return existing

        document_id = self.db.next_id("documents", "document_id", self.community_id, "D", width=3)
        extraction = extract_file(data, declared_mime=result.mime, filename=filename,
                                  config=self.config)

        stored_name = f"{document_id}_{filename}"
        if not stored_name.lower().endswith(f".{extraction.extension}"):
            stored_name = f"{stored_name}.{extraction.extension}"
        target_dir = self.storage.archives if archive_timestamp else self.storage.documents
        stored = self.storage.write_bytes(target_dir, stored_name, data)

        text_rel = None
        if extraction.text:
            text_path = self.storage.write_text(
                self.storage.text, self.storage.text_path(document_id), extraction.text
            )
            text_rel = self.storage.relative(text_path)

        from ..extract.pdf import detect_document_kind

        title = (extraction.metadata.get("title") or extraction.metadata.get("Title")
                 or (extraction.headings[0] if extraction.headings else "") or filename)
        publication_date = _document_date(extraction.metadata)

        self.db.insert(
            "documents",
            {
                "document_id": document_id,
                "community_id": self.community_id,
                "sha256": digest,
                "filename": filename,
                "title": str(title)[:500],
                "mime_declared": result.headers.get("content-type"),
                "mime_sniffed": extraction.mime,
                "extension": extraction.extension,
                "bytes": len(data),
                "storage_path": self.storage.relative(stored),
                "page_count": extraction.page_count,
                "publication_date": publication_date,
                "parser": extraction.parser,
                "parser_status": extraction.parser_status,
                "text_status": extraction.text_status,
                "table_status": extraction.table_status,
                "image_status": extraction.image_status,
                "text_path": text_rel,
                "text_chars": len(extraction.text),
                "doc_kind": detect_document_kind(str(title), extraction.text, extraction.metadata),
                "notes": extraction.detail,
                "created_utc": utcnow(),
            },
            replace=True,
        )
        self._document_hashes[digest] = document_id
        if source_id:
            self.db.insert(
                "document_sources",
                {"document_id": document_id, "source_id": source_id, "original_url": url,
                 "final_url": result.final_url, "archive_timestamp": archive_timestamp,
                 "discovery_stage": stage, "discovery_method": discovery_method,
                 "retrieved_utc": result.fetched_utc},
                replace=True,
            )
            self.db.bump("sources", "documents_found", {"source_id": source_id})
        self.stats.documents += 1
        event(log, "DOC",
              f"{extraction.extension.upper()} stored: {filename} "
              f"({extraction.parser_status}/{extraction.text_status}, {len(data)} bytes)",
              document_id=document_id, url=url)

        self._store_tables(document_id, extraction)

        evidence_count = 0
        if self.on_document is not None:
            try:
                evidence_count = self.on_document(document_id, extraction, {
                    "source_id": source_id,
                    "url": url,
                    "stage": stage,
                    "source_class": context.source_class if context else "S4",
                    "independence_group": context.independence_group if context else None,
                    "publication_date": publication_date,
                    "retrieval_date": result.fetched_utc[:10],
                    "archive_timestamp": archive_timestamp,
                    "title": str(title),
                })
            except Exception as exc:
                log.error("document evidence extraction failed for %s: %s", document_id, exc,
                          exc_info=True)
                self._record_error(url=url, source_id=source_id, stage=stage,
                                   error_type="evidence_extraction_failed", detail=str(exc))

        if self.image_enabled and extraction.images:
            self._store_document_images(document_id, extraction, context, str(title), url)

        # A zip's members are parsed as documents in their own right.
        for member_name, blob in extraction.contained_files[:50]:
            member_digest = self.storage.content_hash(blob)
            if member_digest in self._document_hashes:
                continue
            member_result = FetchResult(
                url=f"{url}#{member_name}", final_url=f"{url}#{member_name}", status=result.status,
                ok=True, content=blob, headers=result.headers, bytes_len=len(blob),
                fetched_utc=result.fetched_utc,
            )
            await self._store_document_bytes(f"{url}#{member_name}", member_result, context, stage,
                                             archive_timestamp=archive_timestamp,
                                             discovery_method="archive_member")

        if context:
            context.budget.record(yielded_evidence=bool(evidence_count), new_urls=0)
        if url_key:
            self.frontier.complete(url_key, "done")
        return document_id

    def _store_tables(self, document_id: str, extraction: Extraction) -> None:
        for table in extraction.tables[:200]:
            table_id = self.db.next_id("document_tables", "table_id", self.community_id, "T", width=3)
            rows = table.rows
            csv_name = f"{table_id}.csv"
            content = "\n".join(
                ",".join('"' + str(cell).replace('"', '""') + '"' for cell in row) for row in rows
            )
            csv_path = self.storage.write_text(self.storage.tables, csv_name, content)
            self.db.insert(
                "document_tables",
                {
                    "table_id": table_id,
                    "document_id": document_id,
                    "community_id": self.community_id,
                    "sheet_name": table.sheet_name,
                    "page_number": table.page_number,
                    "cell_range": table.cell_range,
                    "n_rows": len(rows),
                    "n_cols": max((len(r) for r in rows), default=0),
                    "header_json": json.dumps(table.header, ensure_ascii=False),
                    "csv_path": self.storage.relative(csv_path),
                    "created_utc": utcnow(),
                },
                replace=True,
            )

    # -- images ------------------------------------------------------------
    async def _harvest_page_images(self, parsed: ParsedPage, page_id: str, item: Any,
                                   context: SourceContext | None, stage: int) -> None:
        if self.stats.images_kept >= self.max_images_per_community:
            return
        source_id = context.source_id if context else None
        kept_for_source = 0
        for ref in parsed.images[: self.max_images_per_source]:
            if self.stats.images_kept >= self.max_images_per_community:
                return
            if kept_for_source >= self.max_images_per_source:
                return
            classification = classify_image(
                url=ref.url, alt=ref.alt, title=ref.title, caption=ref.caption,
                surrounding=ref.surrounding, page_title=parsed.title,
                width=ref.width, height=ref.height, lexicon=self.lexicon,
                min_width=self.image_min_width, min_height=self.image_min_height,
            )
            if classification.relevance_class not in self.image_keep:
                self.stats.images_rejected += 1
                continue

            result = await self.fetcher.fetch(
                ref.url, kind="image", community_id=self.community_id,
                source_id=source_id, stage=stage,
            )
            if not result.ok or not result.content:
                self.stats.images_rejected += 1
                continue
            if len(result.content) < self.image_min_bytes and classification.relevance_class != "likely_relevant":
                self.stats.images_rejected += 1
                continue

            width, height = _image_dimensions(result.content)
            if width and height:
                # Re-classify now that the true dimensions are known: a tiny
                # image dressed up in a promising filename is still decoration.
                classification = classify_image(
                    url=ref.url, alt=ref.alt, title=ref.title, caption=ref.caption,
                    surrounding=ref.surrounding, page_title=parsed.title,
                    width=width, height=height, bytes_len=len(result.content),
                    lexicon=self.lexicon, min_width=self.image_min_width,
                    min_height=self.image_min_height,
                )
                if classification.relevance_class not in self.image_keep:
                    self.stats.images_rejected += 1
                    continue

            self._persist_image(
                data=result.content,
                classification=classification,
                source_id=source_id,
                page_id=page_id,
                document_id=None,
                original_url=ref.url,
                caption=ref.caption,
                alt=ref.alt,
                surrounding=ref.surrounding,
                source_title=parsed.title,
                publication_date=parsed.published_date,
                page_number=None,
                extension=result.extension or "jpg",
                width=width,
                height=height,
            )
            kept_for_source += 1

    async def _fetch_standalone_image(self, item: Any, context: SourceContext | None,
                                      stage: int) -> None:
        if not self.image_enabled:
            self.frontier.complete(item.url_key, "skipped", "image harvesting disabled")
            return
        result = await self.fetcher.fetch(
            item.normalized_url, kind="image", community_id=self.community_id,
            source_id=item.source_id, stage=stage,
        )
        if not result.ok or not result.content:
            self._after_failed_fetch(item, context, result, stage)
            return
        width, height = _image_dimensions(result.content)
        classification = classify_image(
            url=item.normalized_url, width=width, height=height,
            bytes_len=len(result.content), lexicon=self.lexicon,
            min_width=self.image_min_width, min_height=self.image_min_height,
        )
        if classification.relevance_class in self.image_keep:
            self._persist_image(
                data=result.content, classification=classification,
                source_id=item.source_id, page_id=None, document_id=None,
                original_url=item.normalized_url, caption="", alt="", surrounding="",
                source_title="", publication_date=None, page_number=None,
                extension=result.extension or "jpg", width=width, height=height,
            )
        else:
            self.stats.images_rejected += 1
        self.frontier.complete(item.url_key, "done")

    def _store_document_images(self, document_id: str, extraction: Extraction,
                               context: SourceContext | None, title: str, url: str) -> None:
        source_id = context.source_id if context else None
        for image in extraction.images[:200]:
            if self.stats.images_kept >= self.max_images_per_community:
                return
            classification = classify_image(
                url=image.name, caption=image.nearby_text[:600],
                surrounding=image.nearby_text, document_title=title,
                width=image.width, height=image.height, bytes_len=len(image.data),
                lexicon=self.lexicon, min_width=self.image_min_width,
                min_height=self.image_min_height,
            )
            if classification.relevance_class not in self.image_keep:
                self.stats.images_rejected += 1
                continue
            self._persist_image(
                data=image.data, classification=classification, source_id=source_id,
                page_id=None, document_id=document_id, original_url=url,
                caption=image.nearby_text[:600], alt="", surrounding=image.nearby_text,
                source_title=title, publication_date=None, page_number=image.page_number,
                extension=image.extension, width=image.width, height=image.height,
            )

    def _persist_image(self, *, data: bytes, classification: Any, source_id: str | None,
                       page_id: str | None, document_id: str | None, original_url: str,
                       caption: str, alt: str, surrounding: str, source_title: str,
                       publication_date: str | None, page_number: int | None,
                       extension: str, width: int, height: int) -> str | None:
        digest = self.storage.content_hash(data)
        if (digest, source_id) in {(h, source_id) for h in self._image_hashes}:
            return None
        image_id = self.db.next_id("images", "image_id", self.community_id, "IMG")
        filename = image_filename(
            image_id=image_id,
            topic=classification.research_topic or classification.image_type,
            year=classification.image_date,
            source=source_id or "unsourced",
            page_number=page_number,
            extension=extension,
        )
        try:
            path = self.storage.write_bytes(self.storage.images, filename, data)
        except ValueError as exc:
            self._record_error(url=original_url, source_id=source_id, stage=None,
                               error_type="unsafe_filename", detail=str(exc))
            return None

        self.db.insert(
            "images",
            {
                "image_id": image_id,
                "community_id": self.community_id,
                "source_id": source_id,
                "document_id": document_id,
                "page_id": page_id,
                "sha256": digest,
                "filename": filename,
                "local_path": self.storage.relative(path),
                "original_url": original_url,
                "page_number": page_number,
                "width": width or None,
                "height": height or None,
                "bytes": len(data),
                "format": extension,
                "source_title": source_title[:400],
                "publication_date": publication_date,
                "image_type": classification.image_type,
                "research_topic": classification.research_topic,
                "caption": caption[:2000],
                "alt_text": alt[:1000],
                "surrounding_text": surrounding[:4000],
                "surrounding_summary": summarise_surrounding(surrounding),
                "evidence_subject": classification.research_topic or classification.image_type,
                "possible_fields": "; ".join(classification.possible_fields),
                "visual_evidence_allowed": classification.visual_evidence_allowed,
                "documentary_text_support": classification.documentary_text_support,
                "image_date": classification.image_date,
                "image_date_confidence": classification.image_date_confidence,
                "relevance_class": classification.relevance_class,
                "relevance_score": classification.score,
                "relevance_reason": classification.reason,
                "confidence": classification.confidence,
                "classifier": "rule:image_lexicon/1.0.0",
                "created_utc": utcnow(),
            },
            replace=True,
        )
        self._image_hashes.add(digest)
        self.stats.images_kept += 1
        if source_id:
            self.db.bump("sources", "images_found", {"source_id": source_id})
        if classification.relevance_class == "likely_relevant":
            event(log, "IMG",
                  f"research-relevant {classification.image_type} kept: {filename}",
                  image_id=image_id, url=original_url)
        return image_id

    # -- bookkeeping -------------------------------------------------------
    def _record_error(self, *, url: str | None, source_id: str | None, stage: int | None,
                      error_type: str, detail: str | None, http_status: int | None = None,
                      unresolved: bool = True, human_review: bool = False,
                      resolution: str | None = None) -> None:
        error_id = self.db.next_id("errors", "error_id", self.community_id, "ERR")
        self.db.insert(
            "errors",
            {
                "error_id": error_id,
                "community_id": self.community_id,
                "stage": stage,
                "source_id": source_id,
                "url": url,
                "error_type": error_type,
                "http_status": http_status,
                "detail": (detail or "")[:4000],
                "unresolved": int(unresolved),
                "human_review": int(human_review),
                "resolution": resolution,
                "ts_utc": utcnow(),
            },
            replace=True,
        )

    def _log_discovery(self, stage: int, method: str, url: str, outcome: str,
                       detail: str | None = None) -> None:
        discovery_id = self.db.next_id("discovery_log", "discovery_id", self.community_id, "DSC")
        self.db.insert(
            "discovery_log",
            {
                "discovery_id": discovery_id,
                "community_id": self.community_id,
                "stage": stage,
                "method": method,
                "found_url": url,
                "outcome": outcome,
                "detail": (detail or "")[:1000],
                "ts_utc": utcnow(),
            },
            replace=True,
        )


def _image_dimensions(data: bytes) -> tuple[int, int]:
    try:
        import io

        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            return image.width, image.height
    except Exception:
        return 0, 0


def _document_date(metadata: Mapping[str, str]) -> str | None:
    from ..extract.html import parse_date_string

    for key in ("CreationDate", "creationdate", "created", "date", "ModDate", "modified",
                "Created", "Date"):
        value = metadata.get(key)
        if value:
            parsed = parse_date_string(str(value).replace("D:", "")[:30])
            if parsed:
                return parsed
    return None
