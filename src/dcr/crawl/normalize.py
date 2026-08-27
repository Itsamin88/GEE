"""URL normalisation, scope rules and crawler-trap detection.

Two URLs that fetch the same bytes must normalise to the same key, or the crawl
counts one page many times and a duplicate masquerades as a new source
(brief §8, §36).
"""

from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

# Parameters that never change what a page says.
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    "gclid", "fbclid", "msclkid", "mc_cid", "mc_eid", "igshid", "ref", "ref_src",
    "_ga", "_gl", "yclid", "wickedid", "hsa_acc", "hsa_cam", "hsCtaTracking",
    "sessionid", "phpsessid", "jsessionid", "sid", "PHPSESSID",
    "share", "replytocom", "print", "amp", "output", "nocache", "_",
}

# Parameters that DO change the page and must be preserved.
MEANINGFUL_PARAMS = {
    "p", "page", "paged", "id", "post", "page_id", "cat", "tag", "q", "s", "search",
    "year", "m", "month", "start", "offset", "lang", "l", "hl", "v", "list",
    "file", "download", "attachment_id", "doc", "view", "url",
}

DEFAULT_PORTS = {"http": 80, "https": 443}

# Extensions we never queue as pages.
BINARY_SKIP = {
    ".css", ".js", ".mjs", ".map", ".ico", ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp3", ".wav", ".ogg", ".m4a", ".flac", ".mp4", ".mkv", ".mov", ".avi", ".webm",
    ".exe", ".dmg", ".msi", ".apk", ".deb", ".rpm", ".iso", ".bin", ".dll", ".so",
}

DOCUMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".odt", ".rtf", ".xls", ".xlsx", ".xlsm", ".ods",
    ".csv", ".tsv", ".ppt", ".pptx", ".odp", ".txt", ".xml", ".json",
    ".kml", ".kmz", ".geojson", ".gpx", ".zip",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".tif", ".tiff", ".bmp", ".svg"}

_DEFAULT_TRAPS = (
    r"/calendar/",
    r"/events?/\d{4}/\d{2}/\d{2}",
    r"[?&](replytocom|share|print|add-to-cart|orderby|filter_)=",
    r"/page/\d{3,}",
    r"(/[^/]{2,})\1{2,}",
    r"/(feed|rss)/(feed|rss)",
    r"[?&]s=[^&]*&s=",
)


def normalize(url: str, base: str | None = None) -> str | None:
    """Return a canonical form of ``url``, or None if it is not fetchable."""
    if not url:
        return None
    raw = url.strip().strip("<>\"'")
    if not raw or raw.startswith(("javascript:", "mailto:", "tel:", "data:", "#", "about:")):
        return None
    if base:
        raw = urljoin(base, raw)
    try:
        parts = urlsplit(raw)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https"):
        return None
    if not parts.hostname:
        return None

    host = parts.hostname.lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    port = parts.port
    netloc = host
    if port and port != DEFAULT_PORTS.get(parts.scheme):
        netloc = f"{host}:{port}"

    # Collapse duplicate slashes, but never inside an embedded URL: a Wayback
    # snapshot path is /web/20160901000000id_/http://example.org/page, and
    # flattening that "//" turns a valid archive URL into a 404.
    path = _collapse_slashes(parts.path or "/")
    # "/x" and "/x/" are the same page on every server this study meets, and
    # treating them as two costs a duplicate fetch and a duplicate page row.
    # An archive path carries a whole second URL, whose own trailing slash is
    # part of that URL: stripping it turns a valid snapshot into a 404.
    if len(path) > 1 and not _EMBEDDED_SCHEME.search(path):
        path = path.rstrip("/") or "/"
    if not path:
        path = "/"

    query_pairs = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in {p.lower() for p in TRACKING_PARAMS}
    ]
    query = urlencode(sorted(query_pairs))
    return urlunsplit((parts.scheme, netloc, path, query, ""))


_EMBEDDED_SCHEME = re.compile(r"(https?:/{1,2})", re.IGNORECASE)


def _collapse_slashes(path: str) -> str:
    pieces = _EMBEDDED_SCHEME.split(path)
    out: list[str] = []
    for piece in pieces:
        if _EMBEDDED_SCHEME.fullmatch(piece):
            # Normalise the embedded scheme to its canonical double slash.
            out.append(piece.rstrip("/") + "//")
        else:
            out.append(re.sub(r"/{2,}", "/", piece))
    return "".join(out)


def registrable_domain(url_or_host: str) -> str:
    """A pragmatic eTLD+1: enough to tell one organisation's domain from another.

    This deliberately avoids a public-suffix dependency; where the guess is
    wrong the effect is a slightly wider or narrower crawl scope, never a
    provenance error, because scope is recorded per URL.
    """
    host = url_or_host
    if "://" in url_or_host:
        parsed = urlsplit(url_or_host)
        host = parsed.hostname or ""
    host = host.lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    two_part_suffixes = {
        "co.uk", "org.uk", "ac.uk", "gov.uk", "me.uk", "net.uk", "sch.uk",
        "com.au", "net.au", "org.au", "edu.au", "gov.au",
        "co.nz", "org.nz", "com.br", "org.br", "net.br", "gov.br", "edu.br",
        "co.za", "org.za", "co.jp", "or.jp", "ne.jp", "ac.jp", "go.jp",
        "com.mx", "org.mx", "com.ar", "org.ar", "com.tr", "org.tr",
        "co.in", "org.in", "net.in", "gov.in", "ac.in",
        "com.pt", "org.pt", "com.es", "org.es", "com.pl", "org.pl",
        "co.il", "org.il", "com.cn", "org.cn", "net.cn", "gov.cn",
        "com.sg", "com.hk", "co.kr", "or.kr",
    }
    if ".".join(labels[-2:]) in two_part_suffixes and len(labels) >= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def same_site(a: str, b: str) -> bool:
    return registrable_domain(a) == registrable_domain(b)


def path_extension(url: str) -> str:
    path = urlsplit(url).path
    _, _, last = path.rpartition("/")
    if "." not in last:
        return ""
    return "." + last.rsplit(".", 1)[-1].lower()


def classify_url(url: str) -> str:
    """page | document | image | skip — decided from the URL alone."""
    ext = path_extension(url)
    if ext in DOCUMENT_EXTENSIONS:
        return "document"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in BINARY_SKIP:
        return "skip"
    return "page"


class TrapDetector:
    """Recognises the URL shapes that generate infinite crawls."""

    def __init__(
        self,
        patterns: Iterable[str] | None = None,
        *,
        max_query_params: int = 6,
        max_path_segments: int = 12,
        max_same_path_variants: int = 40,
    ):
        source = list(patterns) if patterns else list(_DEFAULT_TRAPS)
        self.patterns = [re.compile(p, re.IGNORECASE) for p in source]
        self.max_query_params = max_query_params
        self.max_path_segments = max_path_segments
        self.max_same_path_variants = max_same_path_variants
        self._path_counts: dict[str, int] = {}

    def check(self, url: str) -> str | None:
        """Return a reason string when ``url`` looks like a trap, else None."""
        for pattern in self.patterns:
            if pattern.search(url):
                return f"matches trap pattern {pattern.pattern!r}"
        parts = urlsplit(url)
        params = parse_qsl(parts.query, keep_blank_values=True)
        if len(params) > self.max_query_params:
            return f"{len(params)} query parameters"
        segments = [s for s in parts.path.split("/") if s]
        if len(segments) > self.max_path_segments:
            return f"{len(segments)} path segments"
        if len(segments) != len(set(segments)) and len(segments) > 4:
            counts: dict[str, int] = {}
            for seg in segments:
                counts[seg] = counts.get(seg, 0) + 1
            if max(counts.values()) >= 3:
                return "repeating path segment"
        key = f"{parts.netloc}{parts.path}"
        self._path_counts[key] = self._path_counts.get(key, 0) + 1
        if self._path_counts[key] > self.max_same_path_variants:
            return f"more than {self.max_same_path_variants} query variants of one path"
        return None
