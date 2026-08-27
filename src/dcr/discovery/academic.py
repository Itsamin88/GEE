"""Stage 5 — academic literature.

For a community that HAS been studied, a thesis or a paper is usually the best
source in existence: dated, independent, written by someone who visited. This is
where rank-1 onset evidence lives.

Two rules govern everything here:

* Most communities have NO academic literature. Finding none is the expected
  result and is recorded as a negative consultation (register rule 11).
* A record may support a workbook value only after it has been verified to
  exist — the DOI or repository record retrieved in this run, with a matching
  title (decision DCR-D013). Nothing is ever reconstructed from memory.
"""

from __future__ import annotations

import html as html_module
import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib.parse import quote, urlencode

from ..logging_setup import get_logger

log = get_logger("academic")

# Terms that make a hit plausibly about an intentional community rather than a
# coincidental name match.
TOPIC_TERMS = {
    "ecovillage", "eco-village", "ecovillages", "intentional community",
    "intentional communities", "permaculture", "agroecology", "agroecological",
    "ecological restoration", "land use", "land-use", "communal living", "commune",
    "sustainable community", "cohousing", "co-housing", "agroforestry", "reforestation",
    "écovillage", "écolieu", "communauté intentionnelle", "agroécologie",
    "ecodorp", "permacultuur", "ökodorf", "ecoaldea", "ecoaldeia", "ecovillaggio",
    "rural settlement", "back-to-the-land", "alternative community",
}


@dataclass
class AcademicRecord:
    """One bibliographic record, as retrieved. Never as remembered."""

    title: str
    database_id: str
    authors: str = ""
    year: int | None = None
    venue: str = ""
    doi: str = ""
    url: str = ""
    pdf_url: str = ""
    repository: str = ""
    record_type: str = "paper"
    abstract: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    relevance_score: float = 0.0
    relevance_reason: str = ""
    full_text_status: str = "record only"
    verified_resolves: str = "no"
    verification_detail: str = ""
    source_id: str | None = None

    @property
    def identity_key(self) -> str:
        if self.doi:
            return f"doi:{self.doi.lower()}"
        return "title:" + re.sub(r"[^a-z0-9]+", "", self.title.lower())[:120]


@dataclass
class SearchOutcome:
    """What one consultation of one database actually produced."""

    database_id: str
    database_name: str
    database_type: str
    query: str
    language: str
    result: str                        # hits found | none found | unreachable | paywalled
    hits: int = 0
    records: list[AcademicRecord] = field(default_factory=list)
    http_status: int | None = None
    detail: str = ""


# ---------------------------------------------------------------------------
# Query construction (register 5.2 — "one query is not a search")
# ---------------------------------------------------------------------------
def build_queries(
    *,
    names: Iterable[str],
    locality: str | None,
    region: str | None,
    country: str | None,
    founders: Iterable[str],
    networks: Iterable[str],
    terms_by_language: dict[str, list[str]],
    languages: Iterable[str],
) -> list[tuple[str, str]]:
    """Return (query, language) pairs covering the register's ten routes."""
    name_list = [n for n in dict.fromkeys(n.strip() for n in names if n and n.strip())]
    queries: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(query: str, language: str) -> None:
        cleaned = " ".join(query.split())
        key = (cleaned.lower(), language)
        if cleaned and key not in seen:
            seen.add(key)
            queries.append((cleaned, language))

    langs = [lang for lang in dict.fromkeys(languages) if lang]
    if "en" not in langs:
        langs.append("en")

    for name in name_list:
        add(f'"{name}"', "en")
        for lang in langs:
            for term in terms_by_language.get(lang, [])[:6]:
                add(f'"{name}" {term}', lang)

    for place in (locality, region):
        if not place:
            continue
        for lang in langs:
            for term in terms_by_language.get(lang, [])[:4]:
                add(f'"{place}" {term}', lang)

    for founder in list(founders)[:4]:
        for name in name_list[:2]:
            add(f'"{founder}" "{name}"', "en")

    for network in list(networks)[:4]:
        for name in name_list[:2]:
            add(f'"{network}" "{name}"', "en")

    if country:
        for name in name_list[:2]:
            add(f'"{name}" {country}', "en")
    return queries


# ---------------------------------------------------------------------------
# Response adapters — one per API. Each returns records, never assumptions.
# ---------------------------------------------------------------------------
def request_for(database: dict[str, Any], query: str, *, rows: int, api_key: str | None,
                extra: dict[str, str] | None = None) -> tuple[str, dict[str, str]] | None:
    """Build the request URL and headers for a database, or None if not automatable."""
    db_id = database.get("id")
    endpoint = database.get("endpoint")
    if database.get("access") != "api" or not endpoint:
        return None
    headers: dict[str, str] = {"Accept": "application/json"}

    if db_id == "openalex":
        params = {"search": query, "per-page": str(min(rows, 50)),
                  "select": "id,doi,title,publication_year,authorships,primary_location,"
                            "type,abstract_inverted_index,open_access,locations"}
        return f"{endpoint}?{urlencode(params)}", headers
    if db_id == "crossref":
        params = {"query.bibliographic": query, "rows": str(min(rows, 50)),
                  "select": "DOI,title,author,issued,container-title,type,abstract,URL,link"}
        return f"{endpoint}?{urlencode(params)}", headers
    if db_id == "semantic_scholar":
        params = {"query": query, "limit": str(min(rows, 50)),
                  "fields": "title,abstract,year,authors,externalIds,venue,openAccessPdf,publicationTypes,url"}
        if api_key:
            headers["x-api-key"] = api_key
        return f"{endpoint}?{urlencode(params)}", headers
    if db_id == "core":
        if not api_key:
            return None
        headers["Authorization"] = f"Bearer {api_key}"
        return f"{endpoint}?{urlencode({'q': query, 'limit': str(min(rows, 50))})}", headers
    if db_id in ("openaire", "openaire_projects", "openaire_country", "narcis_worldcat",
                 "iris", "dk_openaire"):
        params = {"keywords": query, "size": str(min(rows, 50)), "format": "json"}
        return f"{endpoint}?{urlencode(params)}", headers
    if db_id == "doaj":
        return f"{endpoint}/{quote(query, safe='')}?{urlencode({'pageSize': str(min(rows, 50))})}", headers
    if db_id == "datacite":
        return f"{endpoint}?{urlencode({'query': query, 'page[size]': str(min(rows, 50))})}", headers
    if db_id == "theses_fr":
        return f"{endpoint}?{urlencode({'q': query, 'nombre': str(min(rows, 50))})}", headers
    if db_id == "hal":
        params = {"q": query, "rows": str(min(rows, 50)), "wt": "json",
                  "fl": "title_s,authFullName_s,producedDateY_i,doiId_s,uri_s,docType_s,abstract_s,fileMain_s"}
        return f"{endpoint}?{urlencode(params)}", headers
    if db_id == "dnb":
        params = {"version": "1.1", "operation": "searchRetrieve",
                  "query": query, "recordSchema": "oai_dc", "maximumRecords": str(min(rows, 50))}
        return f"{endpoint}?{urlencode(params)}", headers
    if extra:
        return f"{endpoint}?{urlencode({**extra, 'q': query})}", headers
    return None


def parse_response(database_id: str, payload: str) -> list[AcademicRecord]:
    """Turn one API response into records. An unparsable body yields none."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        if database_id == "dnb":
            return _parse_sru_xml(payload, database_id)
        return []

    if database_id == "openalex":
        return [_from_openalex(item, database_id) for item in data.get("results", [])]
    if database_id == "crossref":
        return [_from_crossref(item, database_id) for item in data.get("message", {}).get("items", [])]
    if database_id == "semantic_scholar":
        return [_from_semantic_scholar(item, database_id) for item in data.get("data", [])]
    if database_id == "core":
        return [_from_core(item, database_id) for item in data.get("results", [])]
    if database_id in ("openaire", "openaire_country", "narcis_worldcat", "iris", "dk_openaire"):
        return _from_openaire(data, database_id)
    if database_id == "doaj":
        return [_from_doaj(item, database_id) for item in data.get("results", [])]
    if database_id == "datacite":
        return [_from_datacite(item, database_id) for item in data.get("data", [])]
    if database_id == "theses_fr":
        return [_from_theses_fr(item, database_id) for item in
                (data.get("theses") or data.get("resultats") or [])]
    if database_id == "hal":
        return [_from_hal(item, database_id) for item in
                data.get("response", {}).get("docs", [])]
    return []


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, list):
        return "; ".join(_text(v) for v in value if v)
    if isinstance(value, dict):
        for key in ("name", "title", "value", "$", "content"):
            if key in value:
                return _text(value[key])
        return default
    return html_module.unescape(str(value)).strip()


def _year(value: Any) -> int | None:
    match = re.search(r"\b(1[89]\d{2}|20\d{2})\b", str(value or ""))
    return int(match.group(1)) if match else None


def _from_openalex(item: dict[str, Any], db: str) -> AcademicRecord:
    location = item.get("primary_location") or {}
    source = (location.get("source") or {})
    pdf = ""
    for loc in item.get("locations") or []:
        if loc.get("pdf_url"):
            pdf = loc["pdf_url"]
            break
    abstract = ""
    inverted = item.get("abstract_inverted_index")
    if isinstance(inverted, dict):
        positions: list[tuple[int, str]] = []
        for word, idxs in inverted.items():
            for idx in idxs or []:
                positions.append((idx, word))
        abstract = " ".join(w for _, w in sorted(positions))[:6000]
    return AcademicRecord(
        title=_text(item.get("title")),
        database_id=db,
        authors="; ".join(
            _text((a.get("author") or {}).get("display_name"))
            for a in item.get("authorships", [])[:12]
        ),
        year=item.get("publication_year"),
        venue=_text(source.get("display_name")),
        doi=(item.get("doi") or "").replace("https://doi.org/", ""),
        url=item.get("id", "") or (location.get("landing_page_url") or ""),
        pdf_url=pdf,
        record_type=_text(item.get("type"), "paper"),
        abstract=abstract,
        raw=item,
    )


def _from_crossref(item: dict[str, Any], db: str) -> AcademicRecord:
    issued = ((item.get("issued") or {}).get("date-parts") or [[None]])[0]
    pdf = ""
    for link in item.get("link") or []:
        if "pdf" in str(link.get("content-type", "")).lower():
            pdf = link.get("URL", "")
            break
    return AcademicRecord(
        title=_text((item.get("title") or [""])[0]),
        database_id=db,
        authors="; ".join(
            f"{_text(a.get('family'))} {_text(a.get('given'))}".strip()
            for a in item.get("author", [])[:12]
        ),
        year=issued[0] if issued and isinstance(issued[0], int) else None,
        venue=_text((item.get("container-title") or [""])[0]),
        doi=_text(item.get("DOI")),
        url=_text(item.get("URL")),
        pdf_url=pdf,
        record_type=_text(item.get("type"), "paper"),
        abstract=re.sub(r"<[^>]+>", " ", _text(item.get("abstract")))[:6000],
        raw=item,
    )


def _from_semantic_scholar(item: dict[str, Any], db: str) -> AcademicRecord:
    external = item.get("externalIds") or {}
    types = item.get("publicationTypes") or []
    return AcademicRecord(
        title=_text(item.get("title")),
        database_id=db,
        authors="; ".join(_text(a.get("name")) for a in item.get("authors", [])[:12]),
        year=item.get("year"),
        venue=_text(item.get("venue")),
        doi=_text(external.get("DOI")),
        url=_text(item.get("url")),
        pdf_url=_text((item.get("openAccessPdf") or {}).get("url")),
        record_type="thesis" if "Thesis" in types else _text(types[0] if types else "paper", "paper"),
        abstract=_text(item.get("abstract"))[:6000],
        raw=item,
    )


def _from_core(item: dict[str, Any], db: str) -> AcademicRecord:
    return AcademicRecord(
        title=_text(item.get("title")),
        database_id=db,
        authors="; ".join(_text(a.get("name")) for a in item.get("authors", [])[:12]),
        year=_year(item.get("publishedDate") or item.get("yearPublished")),
        venue=_text(item.get("publisher")),
        doi=_text(item.get("doi")),
        url=_text(item.get("downloadUrl") or item.get("sourceFulltextUrls")),
        pdf_url=_text(item.get("downloadUrl")),
        repository=_text((item.get("dataProviders") or [{}])[0].get("name") if item.get("dataProviders") else ""),
        record_type=_text(item.get("documentType"), "paper"),
        abstract=_text(item.get("abstract"))[:6000],
        raw=item,
    )


def _from_openaire(data: dict[str, Any], db: str) -> list[AcademicRecord]:
    results = (((data.get("response") or {}).get("results") or {}).get("result") or [])
    if isinstance(results, dict):
        results = [results]
    records: list[AcademicRecord] = []
    for entry in results:
        meta = (((entry.get("metadata") or {}).get("oaf:entity") or {}).get("oaf:result") or {})
        if not meta:
            continue
        creators = meta.get("creator")
        if isinstance(creators, dict):
            creators = [creators]
        pid = meta.get("pid")
        if isinstance(pid, dict):
            pid = [pid]
        doi = ""
        for identifier in pid or []:
            if str((identifier or {}).get("@classid", "")).lower() == "doi":
                doi = _text(identifier)
                break
        records.append(
            AcademicRecord(
                title=_text(meta.get("title")),
                database_id=db,
                authors="; ".join(_text(c) for c in (creators or [])[:12]),
                year=_year(meta.get("dateofacceptance")),
                venue=_text(meta.get("publisher")),
                doi=doi,
                url=_text((meta.get("children") or {}).get("instance", {}).get("webresource", {})
                          .get("url") if isinstance(meta.get("children"), dict) else ""),
                record_type=_text((meta.get("resulttype") or {}).get("@classname"), "paper"),
                abstract=_text(meta.get("description"))[:6000],
                raw=meta,
            )
        )
    return records


def _from_doaj(item: dict[str, Any], db: str) -> AcademicRecord:
    bib = item.get("bibjson") or {}
    doi = ""
    url = ""
    for identifier in bib.get("identifier") or []:
        if identifier.get("type") == "doi":
            doi = _text(identifier.get("id"))
    for link in bib.get("link") or []:
        if link.get("type") == "fulltext":
            url = _text(link.get("url"))
    return AcademicRecord(
        title=_text(bib.get("title")),
        database_id=db,
        authors="; ".join(_text(a.get("name")) for a in bib.get("author", [])[:12]),
        year=_year(bib.get("year")),
        venue=_text((bib.get("journal") or {}).get("title")),
        doi=doi,
        url=url,
        abstract=_text(bib.get("abstract"))[:6000],
        raw=item,
    )


def _from_datacite(item: dict[str, Any], db: str) -> AcademicRecord:
    attrs = item.get("attributes") or {}
    titles = attrs.get("titles") or [{}]
    return AcademicRecord(
        title=_text(titles[0].get("title") if titles else ""),
        database_id=db,
        authors="; ".join(_text(c.get("name")) for c in attrs.get("creators", [])[:12]),
        year=attrs.get("publicationYear"),
        venue=_text(attrs.get("publisher")),
        doi=_text(attrs.get("doi")),
        url=_text(attrs.get("url")),
        record_type=_text((attrs.get("types") or {}).get("resourceTypeGeneral"), "dataset"),
        abstract=_text((attrs.get("descriptions") or [{}])[0].get("description")
                       if attrs.get("descriptions") else "")[:6000],
        raw=item,
    )


def _from_theses_fr(item: dict[str, Any], db: str) -> AcademicRecord:
    return AcademicRecord(
        title=_text(item.get("titrePrincipal") or item.get("title")),
        database_id=db,
        authors=_text(item.get("auteurs") or item.get("auteur")),
        year=_year(item.get("dateSoutenance") or item.get("anneeSoutenance")),
        venue=_text(item.get("etablissementSoutenance")),
        url=f"https://theses.fr/{_text(item.get('nnt') or item.get('id'))}",
        repository="theses.fr",
        record_type="thesis",
        abstract=_text(item.get("resume"))[:6000],
        raw=item,
    )


def _from_hal(item: dict[str, Any], db: str) -> AcademicRecord:
    return AcademicRecord(
        title=_text((item.get("title_s") or [""])[0] if isinstance(item.get("title_s"), list)
                    else item.get("title_s")),
        database_id=db,
        authors="; ".join(item.get("authFullName_s") or [])[:600],
        year=item.get("producedDateY_i"),
        doi=_text((item.get("doiId_s") or "")),
        url=_text(item.get("uri_s")),
        pdf_url=_text(item.get("fileMain_s")),
        repository="HAL",
        record_type="thesis" if "THESE" in str(item.get("docType_s", "")).upper() else "paper",
        abstract=_text((item.get("abstract_s") or [""])[0] if isinstance(item.get("abstract_s"), list)
                       else item.get("abstract_s"))[:6000],
        raw=item,
    )


def _parse_sru_xml(payload: str, db: str) -> list[AcademicRecord]:
    from bs4 import BeautifulSoup

    try:
        soup = BeautifulSoup(payload, "xml")
    except Exception:
        return []
    records: list[AcademicRecord] = []
    for node in soup.find_all(re.compile(r"(^|:)dc$")):
        title = node.find(re.compile(r"(^|:)title$"))
        if not title:
            continue
        creator = node.find_all(re.compile(r"(^|:)creator$"))
        date_node = node.find(re.compile(r"(^|:)date$"))
        records.append(
            AcademicRecord(
                title=title.get_text(strip=True),
                database_id=db,
                authors="; ".join(c.get_text(strip=True) for c in creator[:12]),
                year=_year(date_node.get_text(strip=True) if date_node else ""),
                record_type="thesis",
            )
        )
    return records


# ---------------------------------------------------------------------------
# Relevance and verification
# ---------------------------------------------------------------------------
def score_relevance(record: AcademicRecord, *, names: Iterable[str], locality: str | None,
                    region: str | None, country: str | None) -> tuple[float, str]:
    """How likely is this record to be about THIS community?

    A high score is a reason to open the full text, never a reason to code a
    value. Coding still requires a passage.
    """
    haystack = " ".join(
        part.lower() for part in (record.title, record.abstract, record.venue, record.authors) if part
    )
    if not haystack.strip():
        return 0.0, "no text to score"

    score = 0.0
    reasons: list[str] = []
    name_hit = False
    for name in names:
        cleaned = name.strip().lower()
        if len(cleaned) < 3:
            continue
        if cleaned in haystack:
            score += 0.55 if not name_hit else 0.1
            name_hit = True
            reasons.append(f"names '{name}'")
    topic_hits = [t for t in TOPIC_TERMS if t in haystack]
    if topic_hits:
        score += min(0.3, 0.12 * len(topic_hits))
        reasons.append(f"topic terms: {', '.join(sorted(topic_hits)[:3])}")
    for place, weight in ((locality, 0.2), (region, 0.12), (country, 0.06)):
        if place and place.strip().lower() in haystack:
            score += weight
            reasons.append(f"mentions '{place}'")
    if record.record_type in ("thesis", "dissertation"):
        score += 0.05
        reasons.append("thesis")
    if not name_hit and not topic_hits:
        return 0.0, "neither the community name nor any topic term appears"
    return min(score, 1.0), "; ".join(reasons) or "weak match"


def verification_targets(record: AcademicRecord) -> list[tuple[str, str]]:
    """URLs that would independently confirm this record exists.

    Only identifiers the record itself carries are used. A DOI or repository URL
    is never constructed (register rule 11).
    """
    targets: list[tuple[str, str]] = []
    if record.doi:
        doi = record.doi.strip()
        if doi.lower().startswith("http"):
            targets.append(("doi", doi))
        else:
            targets.append(("doi", f"https://api.crossref.org/works/{quote(doi, safe='')}"))
    if record.url and record.url.lower().startswith("http"):
        targets.append(("landing_page", record.url))
    if record.pdf_url and record.pdf_url.lower().startswith("http"):
        targets.append(("pdf", record.pdf_url))
    return targets


def titles_match(a: str, b: str) -> bool:
    """Loose title comparison for verification."""
    def canon(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()

    left, right = canon(a), canon(b)
    if not left or not right:
        return False
    if left in right or right in left:
        return True
    left_words = set(left.split())
    right_words = set(right.split())
    if not left_words or not right_words:
        return False
    overlap = len(left_words & right_words) / max(1, min(len(left_words), len(right_words)))
    return overlap >= 0.7
