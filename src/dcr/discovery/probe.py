"""Lightweight discovery: enough requests to size the job, and no more.

Estimating must not become the crawl (brief §35). This asks each address three
cheap questions — what does robots.txt say, how many URLs do the sitemaps it
names contain, and what does the home page look like — and then stops. It
stores nothing as evidence and queues nothing: the real run does that.

Typically fewer than five requests per address.
"""

from __future__ import annotations

import time
from typing import Any, Iterable, Sequence
from urllib.parse import urljoin, urlsplit

from ..crawl.normalize import classify_url, normalize
from ..estimate import DiscoveryProbe
from ..extract.html import parse_html
from ..images.classify import classify_image
from ..images.triage import priority_of, HIGH, MEDIUM
from ..logging_setup import get_logger
from ..net.browser import looks_javascript_rendered
from ..net.mime import is_html
from .sitemap import maybe_gunzip, parse_sitemap

log = get_logger("probe")

#: Sitemaps read per address while estimating. One is usually an index naming
#: the rest, and its own entry count is enough to size the site.
MAX_SITEMAPS_PER_SOURCE = 2

#: A site that publishes more URLs than this is treated as "large"; the crawl
#: budget will cap it long before the estimate needs to be exact.
SITEMAP_URL_CEILING = 5000


async def probe_workload(
    urls: Sequence[str],
    *,
    fetcher: Any,
    lexicon: Any = None,
    community_id: str | None = None,
    min_static_chars: int = 600,
    max_sources: int = 12,
    should_stop: Any = None,
) -> DiscoveryProbe:
    """Look briefly at each supplied address and report how big the job is."""
    started = time.monotonic()
    probe = DiscoveryProbe()
    seen_domains: set[str] = set()
    pages_total = 0
    image_samples = 0
    image_pages = 0
    kept_samples = 0

    candidates = [u for u in (normalize(u) for u in urls) if u][:max_sources]
    probe.sources = len(candidates)
    if not candidates:
        probe.notes.append("no addresses to probe; the estimate rests on assumptions alone")
        probe.elapsed_s = time.monotonic() - started
        return probe

    for url in candidates:
        if should_stop is not None and should_stop():
            probe.notes.append("discovery stopped early on request; the estimate is partial")
            break
        host = (urlsplit(url).hostname or "").lower()
        seen_domains.add(host)
        base = f"{urlsplit(url).scheme}://{host}"

        # 1. robots.txt — cheap, and it names the sitemaps.
        sitemap_urls: list[str] = []
        try:
            policy = await fetcher.robots_for(url)
            probe.requests_made += 1
            sitemap_urls = list(getattr(policy, "sitemaps", []) or [])
        except Exception as exc:                      # never let sizing break the run
            log.debug("robots probe failed for %s: %s", url, exc)
        if not sitemap_urls:
            sitemap_urls = [urljoin(base + "/", "sitemap.xml")]

        # 2. the sitemaps it named — the site's own statement of its size.
        site_pages = 0
        site_documents = 0
        for sitemap_url in sitemap_urls[:MAX_SITEMAPS_PER_SOURCE]:
            if should_stop is not None and should_stop():
                break
            result = await fetcher.fetch(sitemap_url, kind="page",
                                         community_id=community_id)
            probe.requests_made += 1
            if not result.ok or not result.content:
                continue
            probe.sitemaps_found += 1
            try:
                text = maybe_gunzip(result.content).decode("utf-8", "replace")
                entries, nested = parse_sitemap(text, sitemap_url)
            except Exception:
                continue
            for entry in entries:
                if entry.kind == "document" or classify_url(entry.url) == "document":
                    site_documents += 1
                else:
                    site_pages += 1
            # A sitemap index: each nested map holds roughly as many entries
            # again. Counting them all would be a crawl, so scale instead and
            # say so.
            if nested:
                per_map = max(len(entries), 50)
                site_pages += per_map * max(0, len(nested) - 1)
                probe.notes.append(
                    f"{host} publishes a sitemap index naming {len(nested)} sitemaps; "
                    "its page count is scaled from the first, not enumerated")
            if site_pages >= SITEMAP_URL_CEILING:
                probe.notes.append(
                    f"{host} lists more than {SITEMAP_URL_CEILING} URLs; the crawl "
                    "budget will cap the run well below its full size")
                site_pages = SITEMAP_URL_CEILING
                break

        # 3. the home page — link density where there is no sitemap, plus the
        #    two things that change the cost most: JavaScript and images.
        result = await fetcher.fetch(url, kind="page", community_id=community_id)
        probe.requests_made += 1
        if result.ok and result.text and is_html(result.mime or ""):
            needs_browser, why = looks_javascript_rendered(result.text, min_static_chars)
            if needs_browser:
                probe.javascript_sources += 1
                probe.notes.append(f"{host} renders through JavaScript ({why}); "
                                   "its pages need a browser and cost several times more")
            try:
                parsed = parse_html(result.text, url)
            except Exception:
                parsed = None
            if parsed is not None:
                internal = {
                    n for n in (normalize(link, url) for link, _ in parsed.links)
                    if n and (urlsplit(n).hostname or "").lower() == host
                }
                if not site_pages:
                    # No sitemap: the home page's own link count is the only
                    # evidence of size there is. Sites are deeper than their
                    # front page, so allow for pages it does not link to.
                    site_pages = max(len(internal) * 3, 10)
                    probe.notes.append(
                        f"{host} publishes no readable sitemap; its size is estimated "
                        f"from {len(internal)} links on the home page")
                site_documents = max(site_documents, len(parsed.document_links))

                if parsed.images:
                    image_pages += 1
                    image_samples += len(parsed.images)
                    for ref in parsed.images:
                        classification = classify_image(
                            url=ref.url, alt=ref.alt, title=ref.title,
                            caption=ref.caption, surrounding=ref.surrounding,
                            page_title=parsed.title, width=ref.width, height=ref.height,
                            lexicon=lexicon,
                        )
                        if priority_of(classification) in (HIGH, MEDIUM):
                            kept_samples += 1
        elif not result.ok:
            probe.unreachable_sources += 1
            probe.notes.append(
                f"{host} did not answer during discovery ({result.error_type or 'no reason given'}); "
                "it is still counted, because unreachable now is not unreachable later")

        pages_total += site_pages
        probe.documents_seen += site_documents

    probe.domains = len(seen_domains)
    probe.estimated_pages = pages_total
    if image_pages:
        probe.images_per_page = round(image_samples / image_pages, 2)
    if image_samples:
        probe.image_keep_rate = round(kept_samples / image_samples, 3)
        probe.notes.append(
            f"image triage kept {kept_samples} of {image_samples} candidates on the "
            f"pages sampled ({probe.image_keep_rate:.0%}); the rest are not downloaded")
    # The archive is enumerated per domain and is often the largest single cost.
    probe.archive_snapshots = probe.domains * 12
    probe.elapsed_s = time.monotonic() - started
    return probe
