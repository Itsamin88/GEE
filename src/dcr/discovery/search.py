"""Search-engine adapters.

Search engines are how you reach pages that are linked from nowhere
(register 2e, 5, 6, 7). Every engine here is optional: one that is not
configured, or that refuses automated reading, is recorded as a consultation
with result ``unreachable`` — never as zero results (brief §73).
"""

from __future__ import annotations

import html as html_module
import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit

from bs4 import BeautifulSoup

from ..soup import soup as make_soup

from ..crawl.normalize import normalize


@dataclass
class SearchHit:
    url: str
    title: str = ""
    snippet: str = ""
    engine: str = ""


@dataclass
class EngineOutcome:
    engine_id: str
    engine_name: str
    query: str
    result: str                       # hits found | none found | unreachable | not_configured
    hits: list[SearchHit] = field(default_factory=list)
    http_status: int | None = None
    detail: str = ""


def build_request(engine: dict[str, Any], query: str, *, api_key: str | None,
                  extra_key: str | None, count: int = 20,
                  language: str | None = None) -> tuple[str, dict[str, str]] | None:
    """Return (url, headers) for one engine, or None if it cannot be automated."""
    engine_id = engine.get("id")
    endpoint = engine.get("endpoint")
    if not endpoint:
        return None
    if engine.get("needs_key") and not api_key:
        return None
    headers: dict[str, str] = {}

    if engine_id == "duckduckgo_html":
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        return f"{endpoint}?{urlencode({'q': query})}", headers
    if engine_id == "brave":
        headers.update({"X-Subscription-Token": api_key or "", "Accept": "application/json"})
        params = {"q": query, "count": str(count)}
        if language:
            params["search_lang"] = language
        return f"{endpoint}?{urlencode(params)}", headers
    if engine_id == "serpapi":
        params = {"q": query, "num": str(count), "api_key": api_key or "", "engine": "google"}
        return f"{endpoint}?{urlencode(params)}", {"Accept": "application/json"}
    if engine_id == "google_cse":
        if not extra_key:
            return None
        params = {"q": query, "key": api_key or "", "cx": extra_key, "num": str(min(count, 10))}
        return f"{endpoint}?{urlencode(params)}", {"Accept": "application/json"}
    if engine_id == "bing":
        headers.update({"Ocp-Apim-Subscription-Key": api_key or "", "Accept": "application/json"})
        return f"{endpoint}?{urlencode({'q': query, 'count': str(count)})}", headers
    if engine_id in ("mojeek", "marginalia"):
        return f"{endpoint}?{urlencode({'q': query})}", headers
    return None


def parse_results(engine_id: str, body: str) -> list[SearchHit]:
    if engine_id in ("brave", "serpapi", "google_cse", "bing"):
        return _parse_json(engine_id, body)
    return _parse_html(engine_id, body)


def _parse_json(engine_id: str, body: str) -> list[SearchHit]:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return []
    hits: list[SearchHit] = []
    if engine_id == "brave":
        items = (data.get("web") or {}).get("results") or []
        for item in items:
            hits.append(SearchHit(url=item.get("url", ""), title=item.get("title", ""),
                                  snippet=item.get("description", ""), engine=engine_id))
    elif engine_id == "serpapi":
        for item in data.get("organic_results") or []:
            hits.append(SearchHit(url=item.get("link", ""), title=item.get("title", ""),
                                  snippet=item.get("snippet", ""), engine=engine_id))
    elif engine_id == "google_cse":
        for item in data.get("items") or []:
            hits.append(SearchHit(url=item.get("link", ""), title=item.get("title", ""),
                                  snippet=item.get("snippet", ""), engine=engine_id))
    elif engine_id == "bing":
        for item in (data.get("webPages") or {}).get("value") or []:
            hits.append(SearchHit(url=item.get("url", ""), title=item.get("name", ""),
                                  snippet=item.get("snippet", ""), engine=engine_id))
    return [h for h in hits if h.url]


def _parse_html(engine_id: str, body: str) -> list[SearchHit]:
    soup = make_soup(body)
    hits: list[SearchHit] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        url = _unwrap_redirect(href)
        candidate = normalize(url)
        if not candidate or candidate in seen:
            continue
        host = (urlsplit(candidate).hostname or "").lower()
        if any(marker in host for marker in ("duckduckgo.com", "mojeek.com", "marginalia.nu",
                                             "google.", "bing.com")):
            continue
        title = anchor.get_text(" ", strip=True)
        if len(title) < 3:
            continue
        snippet = ""
        container = anchor.find_parent(["div", "li", "article", "tr"])
        if container is not None:
            snippet = container.get_text(" ", strip=True)[:400]
        seen.add(candidate)
        hits.append(SearchHit(url=candidate, title=html_module.unescape(title)[:400],
                              snippet=snippet, engine=engine_id))
    return hits


def _unwrap_redirect(href: str) -> str:
    """DuckDuckGo and friends wrap results in a redirect; unwrap to the target."""
    if href.startswith("//"):
        href = "https:" + href
    parts = urlsplit(href)
    if "duckduckgo.com" in (parts.hostname or "") and parts.path.startswith("/l/"):
        target = parse_qs(parts.query).get("uddg")
        if target:
            return unquote(target[0])
    if parts.path in ("/url", "/l/") and parts.query:
        for key in ("q", "url", "u"):
            target = parse_qs(parts.query).get(key)
            if target:
                return unquote(target[0])
    return href


def filetype_queries(name: str, extensions: list[str], *, extra_terms: list[str] | None = None) -> list[str]:
    """`"<name>" filetype:pdf` and its friends (register 6.3)."""
    queries = [f'"{name}" filetype:{ext}' for ext in extensions]
    for term in extra_terms or []:
        queries.append(f'"{name}" {term} filetype:pdf')
    return queries


def site_queries(domain: str, *, years: list[int] | None = None) -> list[str]:
    """`site:<domain>` enumeration, which catches pages linked from nowhere."""
    queries = [f"site:{domain}"]
    for year in years or []:
        queries.append(f"site:{domain} {year}")
    return queries


def domain_guesses(slug: str, country_code: str | None) -> list[str]:
    """Candidate domains for a community with no supplied address (register Stage 1)."""
    tlds = ["org", "com", "net", "eu", "info"]
    if country_code:
        tlds.insert(0, country_code.lower())
    return [f"https://{slug}.{tld}" for tld in tlds]
