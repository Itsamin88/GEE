"""HTML parsing: text, links, images, dates and platform fingerprints.

Everything here is deterministic. Nothing infers a fact; it only reports what
the markup actually contains, with enough context that a later claim can quote
the exact sentence (brief §66).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from ..soup import soup as make_soup

BOILERPLATE_TAGS = ("script", "style", "noscript", "template", "svg", "iframe")

_WS = re.compile(r"[ \t ]+")
_BLANK_LINES = re.compile(r"\n{3,}")

# ISO, European and written dates in the languages this study touches.
_DATE_PATTERNS = (
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
    re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b"),
)
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
    "decembre": 12,
    "januari": 1, "februari": 2, "maart": 3, "mei": 5, "juni": 6, "juli": 7, "augustus": 8,
    "oktober": 10, "december": 12,
    "januar": 1, "februar": 2, "märz": 3, "marz": 3, "juni ": 6, "dezember": 12,
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "maio": 5, "junho": 6, "julho": 7,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
    "gennaio": 1, "febbraio": 2, "aprile": 4, "maggio": 5, "giugno": 6, "luglio": 7,
    "settembre": 9, "ottobre": 10, "dicembre": 12,
}
_WRITTEN_DATE = re.compile(
    r"\b(\d{1,2})\s+([a-zàâäéèêëîïôöùûüçñ]+)\s+(\d{4})\b|"
    r"\b([a-zàâäéèêëîïôöùûüçñ]+)\s+(\d{1,2}),?\s+(\d{4})\b",
    re.IGNORECASE,
)

PLATFORM_FINGERPRINTS = (
    ("wordpress", ("wp-content", "wp-includes", "wp-json", 'name="generator" content="wordpress')),
    ("blogspot", ("blogspot.com", "blogger.com/static")),
    ("ghost", ('name="generator" content="ghost',)),
    ("medium", ("cdn-client.medium.com", "medium.com/_/")),
    ("substack", ("substackcdn.com", "substack.com/api")),
    ("wix", ("static.wixstatic.com", "wix.com/website")),
    ("squarespace", ("squarespace.com", "static1.squarespace.com")),
    ("joomla", ('name="generator" content="joomla',)),
    ("drupal", ("/sites/default/files", "drupal.js")),
    ("webflow", ("assets.website-files.com", "webflow.js")),
    ("shopify", ("cdn.shopify.com",)),
    ("weebly", ("weebly.com",)),
    ("typo3", ("typo3temp", "typo3conf")),
    ("jimdo", ("jimdo.com", "jimcdn.com")),
)


@dataclass
class ImageRef:
    url: str
    alt: str = ""
    title: str = ""
    caption: str = ""
    surrounding: str = ""
    width: int | None = None
    height: int | None = None
    in_figure: bool = False
    from_link: bool = False


@dataclass
class ParsedPage:
    title: str = ""
    text: str = ""
    html_lang: str | None = None
    meta: dict[str, str] = field(default_factory=dict)
    links: list[tuple[str, str]] = field(default_factory=list)      # (url, anchor text)
    nav_links: list[str] = field(default_factory=list)
    footer_links: list[str] = field(default_factory=list)
    document_links: list[tuple[str, str]] = field(default_factory=list)
    images: list[ImageRef] = field(default_factory=list)
    feeds: list[str] = field(default_factory=list)
    canonical: str | None = None
    published_date: str | None = None
    platform_engine: str | None = None
    headings: list[tuple[int, str]] = field(default_factory=list)
    pagination_links: list[str] = field(default_factory=list)
    social_links: list[str] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    jsonld: list[str] = field(default_factory=list)


def parse_html(html: str, base_url: str) -> ParsedPage:
    soup = make_soup(html)
    page = ParsedPage()

    html_tag = soup.find("html")
    if isinstance(html_tag, Tag):
        lang = html_tag.get("lang")
        if isinstance(lang, str):
            page.html_lang = lang.split("-")[0].lower()

    if soup.title and soup.title.string:
        page.title = soup.title.string.strip()

    for meta in soup.find_all("meta"):
        key = meta.get("name") or meta.get("property") or meta.get("itemprop")
        content = meta.get("content")
        if isinstance(key, str) and isinstance(content, str):
            page.meta[key.lower().strip()] = content.strip()

    link_canonical = soup.find("link", rel=lambda v: bool(v) and "canonical" in str(v).lower())
    if isinstance(link_canonical, Tag):
        href = link_canonical.get("href")
        if isinstance(href, str):
            page.canonical = urljoin(base_url, href)

    for link in soup.find_all("link", type=re.compile(r"(rss|atom)\+xml")):
        href = link.get("href")
        if isinstance(href, str):
            page.feeds.append(urljoin(base_url, href))

    page.published_date = _extract_published_date(soup, page.meta)

    lowered_html = html.lower()
    for engine, markers in PLATFORM_FINGERPRINTS:
        if any(marker in lowered_html for marker in markers):
            page.platform_engine = engine
            break

    for script in soup.find_all("script", type="application/ld+json"):
        payload = script.string or script.get_text()
        if payload and len(payload) < 200000:
            page.jsonld.append(payload.strip())

    page.images = _collect_images(soup, base_url)
    _collect_links(soup, base_url, page)

    for level in range(1, 5):
        for heading in soup.find_all(f"h{level}"):
            text = heading.get_text(" ", strip=True)
            if text:
                page.headings.append((level, text[:300]))

    for table in soup.find_all("table"):
        rows: list[list[str]] = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            if cells:
                rows.append(cells)
        if rows and len(rows) > 1:
            page.tables.append(rows[:200])

    for tag in soup(BOILERPLATE_TAGS):
        tag.decompose()
    raw_text = soup.get_text("\n", strip=True)
    page.text = _BLANK_LINES.sub("\n\n", _WS.sub(" ", raw_text))
    return page


def _collect_images(soup: BeautifulSoup, base_url: str) -> list[ImageRef]:
    images: list[ImageRef] = []
    seen: set[str] = set()

    def add(url_value: Any, node: Tag, *, from_link: bool = False) -> None:
        if not isinstance(url_value, str) or not url_value.strip():
            return
        candidate = url_value.strip().split()[0]  # srcset "url 2x"
        absolute = urljoin(base_url, candidate)
        if absolute in seen:
            return
        seen.add(absolute)
        figure = node.find_parent("figure")
        caption = ""
        if figure is not None:
            figcaption = figure.find("figcaption")
            if figcaption:
                caption = figcaption.get_text(" ", strip=True)
        images.append(
            ImageRef(
                url=absolute,
                alt=str(node.get("alt") or "")[:500],
                title=str(node.get("title") or "")[:300],
                caption=caption[:1000],
                surrounding=_surrounding_text(node),
                width=_int_or_none(node.get("width")),
                height=_int_or_none(node.get("height")),
                in_figure=figure is not None,
                from_link=from_link,
            )
        )

    for img in soup.find_all("img"):
        add(img.get("src") or img.get("data-src") or img.get("data-lazy-src")
            or img.get("data-original"), img)
        srcset = img.get("srcset") or img.get("data-srcset")
        if isinstance(srcset, str):
            candidates = [c.strip() for c in srcset.split(",") if c.strip()]
            if candidates:
                add(candidates[-1], img)  # the largest rendition

    for source in soup.find_all("source"):
        srcset = source.get("srcset")
        if isinstance(srcset, str) and srcset.strip():
            add(srcset.split(",")[-1].strip(), source)

    # <a href="photo.jpg"> — gallery thumbnails linking the full-size original.
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if isinstance(href, str) and re.search(r"\.(jpe?g|png|gif|webp|tiff?)($|\?)", href, re.I):
            add(href, anchor, from_link=True)

    for meta_key in ("og:image", "twitter:image"):
        tag = soup.find("meta", attrs={"property": meta_key}) or soup.find("meta", attrs={"name": meta_key})
        if isinstance(tag, Tag):
            add(tag.get("content"), tag)
    return images


def _collect_links(soup: BeautifulSoup, base_url: str, page: ParsedPage) -> None:
    nav_scopes = soup.find_all(["nav", "header"]) + soup.find_all(
        attrs={"class": re.compile(r"\b(nav|menu|topbar)\b", re.I)}
    )
    footer_scopes = soup.find_all("footer") + soup.find_all(
        attrs={"class": re.compile(r"\bfooter\b", re.I)}
    )
    nav_nodes = {id(a) for scope in nav_scopes for a in scope.find_all("a", href=True)}
    footer_nodes = {id(a) for scope in footer_scopes for a in scope.find_all("a", href=True)}

    social_hosts = ("facebook.com", "instagram.com", "youtube.com", "youtu.be", "vimeo.com",
                    "linkedin.com", "twitter.com", "x.com", "tiktok.com", "mastodon",
                    "flickr.com", "pinterest.")
    document_ext = re.compile(
        r"\.(pdf|docx?|odt|rtf|xlsx?|xlsm|ods|csv|tsv|pptx?|odp|txt|kml|kmz|geojson|gpx|zip)($|\?)",
        re.I,
    )
    pagination_words = re.compile(
        r"^\s*(older|previous|next|suivant|précédent|precedent|vorige|volgende|"
        r"älter|zurück|weiter|anterior|siguiente|próxima|proxima|«|»|\d{1,4})\s*$",
        re.I,
    )

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if not isinstance(href, str):
            continue
        text = anchor.get_text(" ", strip=True)[:300]
        absolute = urljoin(base_url, href.strip())
        if not absolute.lower().startswith(("http://", "https://")):
            continue
        page.links.append((absolute, text))
        if id(anchor) in nav_nodes:
            page.nav_links.append(absolute)
        if id(anchor) in footer_nodes:
            page.footer_links.append(absolute)
        if document_ext.search(absolute):
            page.document_links.append((absolute, text or anchor.get("title", "") or ""))
        host = (urlsplit(absolute).hostname or "").lower()
        if any(social in host for social in social_hosts):
            page.social_links.append(absolute)
        rel = anchor.get("rel") or []
        if isinstance(rel, str):
            rel = [rel]
        if any(r.lower() in ("next", "prev") for r in rel) or pagination_words.match(text):
            page.pagination_links.append(absolute)


def _surrounding_text(node: Tag, *, window: int = 400) -> str:
    """The prose immediately around an image, for the manifest's context."""
    parts: list[str] = []
    parent = node.find_parent(["figure", "div", "section", "article", "li", "p", "td"])
    if parent is not None:
        parts.append(parent.get_text(" ", strip=True))
    else:
        for sibling in list(node.next_siblings)[:3]:
            if isinstance(sibling, Tag):
                parts.append(sibling.get_text(" ", strip=True))
    text = " ".join(p for p in parts if p)
    return _WS.sub(" ", text)[:window]


def _int_or_none(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _extract_published_date(soup: BeautifulSoup, meta: dict[str, str]) -> str | None:
    """The page's OWN stated date. Never confused with retrieval date (brief §52)."""
    for key in ("article:published_time", "article:modified_time", "datepublished",
                "date", "dc.date", "dcterms.created", "og:updated_time", "pubdate"):
        value = meta.get(key)
        if value:
            parsed = parse_date_string(value)
            if parsed:
                return parsed
    time_tag = soup.find("time", attrs={"datetime": True})
    if isinstance(time_tag, Tag):
        parsed = parse_date_string(str(time_tag.get("datetime")))
        if parsed:
            return parsed
    for node in soup.find_all(attrs={"class": re.compile(r"(post|entry|published|date)", re.I)})[:12]:
        parsed = parse_date_string(node.get_text(" ", strip=True)[:120])
        if parsed:
            return parsed
    return None


def parse_date_string(value: str | None) -> str | None:
    """Return an ISO date (or year) from a human or machine date string."""
    if not value:
        return None
    text = value.strip()
    # RFC 822 / 2822, the format every RSS feed uses.
    if "," in text[:5] or re.match(r"^[A-Za-z]{3},", text):
        try:
            from email.utils import parsedate_to_datetime

            parsed = parsedate_to_datetime(text)
            if parsed is not None:
                return parsed.date().isoformat()
        except (TypeError, ValueError, IndexError):
            pass
    for pattern in _DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            groups = match.groups()
            try:
                if len(groups[0]) == 4:
                    y, m, d = int(groups[0]), int(groups[1]), int(groups[2])
                else:
                    d, m, y = int(groups[0]), int(groups[1]), int(groups[2])
                if m > 12 and d <= 12:
                    d, m = m, d
                return date(y, m, d).isoformat()
            except (ValueError, TypeError):
                continue
    match = _WRITTEN_DATE.search(text)
    if match:
        groups = [g for g in match.groups() if g]
        if len(groups) == 3:
            a, b, c = groups
            month = _MONTHS.get(str(b).lower().strip()) or _MONTHS.get(str(a).lower().strip())
            if month:
                day = int(a) if str(a).isdigit() else int(b)
                try:
                    return date(int(c), month, day).isoformat()
                except ValueError:
                    return str(int(c))
    year = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    if year:
        return year.group(1)
    return None


def iter_years(text: str, *, low: int = 1900, high: int = 2100) -> Iterable[int]:
    for match in re.finditer(r"\b(1[89]\d{2}|20\d{2})\b", text):
        year = int(match.group(1))
        if low <= year <= high:
            yield year
