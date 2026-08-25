"""Sitemap and feed enumeration.

A sitemap or an RSS feed returns the whole dated page list for one request,
which makes them the cheapest high-value action in the protocol (register
Stage 2A/2B). The sitemap is never assumed complete: its URLs are merged with
navigation, internal crawling and archive listings.
"""

from __future__ import annotations

import gzip
import io
import re
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from ..crawl.normalize import classify_url, normalize
from ..extract.html import parse_date_string


@dataclass
class SitemapEntry:
    url: str
    lastmod: str | None = None
    kind: str = "page"           # page | document | image | sitemap
    source_sitemap: str | None = None
    language: str | None = None
    images: list[str] = field(default_factory=list)


@dataclass
class FeedEntry:
    url: str
    title: str = ""
    published: str | None = None
    summary: str = ""
    content: str = ""
    enclosures: list[str] = field(default_factory=list)


def parse_sitemap(xml_text: str, base_url: str) -> tuple[list[SitemapEntry], list[str]]:
    """Return (entries, nested sitemap URLs)."""
    entries: list[SitemapEntry] = []
    nested: list[str] = []
    try:
        soup = BeautifulSoup(xml_text, "xml")
    except Exception:
        soup = BeautifulSoup(xml_text, "lxml")

    for node in soup.find_all("sitemap"):
        loc = node.find("loc")
        if loc and loc.get_text(strip=True):
            candidate = normalize(loc.get_text(strip=True), base_url)
            if candidate:
                nested.append(candidate)

    for node in soup.find_all("url"):
        loc = node.find("loc")
        if not loc or not loc.get_text(strip=True):
            continue
        candidate = normalize(loc.get_text(strip=True), base_url)
        if not candidate:
            continue
        lastmod_node = node.find("lastmod")
        lastmod = parse_date_string(lastmod_node.get_text(strip=True)) if lastmod_node else None
        images = []
        for image in node.find_all(re.compile(r"(^|:)loc$")):
            parent_name = image.parent.name.lower() if image.parent else ""
            if "image" in parent_name:
                value = normalize(image.get_text(strip=True), base_url)
                if value:
                    images.append(value)
        language = None
        for link in node.find_all(re.compile(r"(^|:)link$")):
            hreflang = link.get("hreflang")
            if hreflang:
                language = str(hreflang).split("-")[0].lower()
                alt = normalize(str(link.get("href") or ""), base_url)
                if alt and alt != candidate:
                    entries.append(SitemapEntry(url=alt, lastmod=lastmod, kind=classify_url(alt),
                                                source_sitemap=base_url, language=language))
        entries.append(
            SitemapEntry(url=candidate, lastmod=lastmod, kind=classify_url(candidate),
                         source_sitemap=base_url, language=language, images=images)
        )

    # A plain-text sitemap (one URL per line) is also legal.
    if not entries and not nested and "\n" in xml_text and "<" not in xml_text[:200]:
        for line in xml_text.splitlines():
            candidate = normalize(line.strip(), base_url)
            if candidate:
                entries.append(SitemapEntry(url=candidate, kind=classify_url(candidate),
                                            source_sitemap=base_url))
    return entries, nested


def maybe_gunzip(data: bytes) -> bytes:
    if data[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(data)
        except OSError:
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as fh:  # pragma: no cover
                return fh.read()
    return data


def parse_feed(xml_text: str, base_url: str) -> list[FeedEntry]:
    """Parse RSS or Atom. Feed dates are publication dates, never event dates."""
    entries: list[FeedEntry] = []
    try:
        soup = BeautifulSoup(xml_text, "xml")
    except Exception:
        soup = BeautifulSoup(xml_text, "lxml")

    for item in soup.find_all(["item", "entry"]):
        link = ""
        link_node = item.find("link")
        if link_node is not None:
            link = (link_node.get("href") or link_node.get_text(strip=True) or "").strip()
        if not link:
            guid = item.find("guid")
            if guid and guid.get_text(strip=True).startswith("http"):
                link = guid.get_text(strip=True)
        candidate = normalize(link, base_url) if link else None
        if not candidate:
            continue
        published = None
        for tag in ("pubDate", "published", "updated", "dc:date", "date"):
            node = item.find(tag)
            if node is not None:
                published = parse_date_string(node.get_text(strip=True))
                if published:
                    break
        title_node = item.find("title")
        summary_node = item.find(["description", "summary"])
        content_node = item.find(["content", "content:encoded"])
        enclosures = []
        for enclosure in item.find_all(["enclosure", "media:content"]):
            href = enclosure.get("url") or enclosure.get("href")
            if href:
                value = normalize(str(href), base_url)
                if value:
                    enclosures.append(value)
        entries.append(
            FeedEntry(
                url=candidate,
                title=title_node.get_text(" ", strip=True)[:400] if title_node else "",
                published=published,
                summary=summary_node.get_text(" ", strip=True)[:4000] if summary_node else "",
                content=content_node.get_text(" ", strip=True)[:40000] if content_node else "",
                enclosures=enclosures,
            )
        )
    return entries


def candidate_sitemap_urls(base: str, paths: Iterable[str], robots_sitemaps: Iterable[str]) -> list[str]:
    parts = urlsplit(base)
    root = f"{parts.scheme}://{parts.netloc}"
    urls: list[str] = []
    for sitemap in robots_sitemaps:
        candidate = normalize(sitemap, root)
        if candidate:
            urls.append(candidate)
    for path in paths:
        candidate = normalize(urljoin(root + "/", path.lstrip("/")), root)
        if candidate and candidate not in urls:
            urls.append(candidate)
    return urls


def archive_paths_for_blog(base: str, years: Iterable[int]) -> list[str]:
    """Chronological archive URLs for the common blog engines."""
    parts = urlsplit(base)
    root = f"{parts.scheme}://{parts.netloc}"
    out: list[str] = []
    for year in years:
        out.append(f"{root}/{year}/")
        for month in range(1, 13):
            out.append(f"{root}/{year}/{month:02d}/")
        out.append(f"{root}/{year}_01_01_archive.html")   # Blogspot
    return out
