"""Stage 6 — grey literature, funding records and official registers.

Grey literature is where dated, independent records live and almost nobody
searches it. A LEADER or LIFE record naming the community and dating a planting
or water project is often the best onset evidence that exists anywhere
(register 6.1). Every consultation is logged by type, including the empty ones.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib.parse import urlencode

# The fourteen-plus grey types the register asks to be logged (field I7).
GREY_TYPE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("thesis", ("thesis", "dissertation", "master", "phd", "doctoral", "mémoire", "memoire",
                "proefschrift", "scriptie", "tese", "tesis", "dissertação", "abschlussarbeit")),
    ("conference paper", ("conference", "proceedings", "symposium", "colloque", "congress",
                          "poster", "abstract book")),
    ("NGO report", ("ngo", "foundation report", "association report", "stichting", "vereniging",
                    "charity", "fondation", "rapport d'activité", "jaarverslag")),
    ("government report", ("ministry", "ministère", "municipal", "commune", "gemeente",
                           "prefecture", "government", "conseil", "provincie", "county",
                           "environment agency", "rapport public")),
    ("environmental assessment", ("environmental impact", "impact assessment", "étude d'impact",
                                  "milieueffect", "mer-rapport", "eia")),
    ("grant application", ("grant application", "demande de subvention", "subsidieaanvraag",
                           "funding application", "call proposal")),
    ("grant record", ("grant", "subvention", "subsidie", "funding", "financement", "beneficiary",
                      "bénéficiaire", "leader", "life programme", "interreg", "erasmus",
                      "horizon", "cordis", "fonds")),
    ("project deliverable", ("deliverable", "livrable", "work package", "project report",
                             "rapport de projet", "projectverslag")),
    ("certification audit", ("certification", "certified", "audit", "inspection", "demeter",
                             "ecocert", "skal", "bioland", "naturland", "organic control",
                             "participatory guarantee")),
    ("network report", ("network report", "federation", "member survey", "gen europe",
                        "réseau", "netwerk", "annual gathering")),
    ("working paper", ("working paper", "preprint", "discussion paper", "document de travail")),
    ("consultancy report", ("consultancy", "evaluation report", "programme evaluation",
                            "étude", "onderzoeksrapport")),
    ("newsletter", ("newsletter", "bulletin", "lettre d'information", "nieuwsbrief", "rundbrief")),
    ("extension publication", ("extension service", "chambre d'agriculture", "advisory service",
                               "voorlichting", "landbouwvoorlichting")),
    ("land trust document", ("land trust", "conservation easement", "covenant", "servitude",
                             "erfdienstbaarheid", "bail emphytéotique")),
    ("planning permit", ("planning application", "building permit", "permis de construire",
                         "omgevingsvergunning", "bestemmingsplan", "bouwvergunning",
                         "land use permit", "certificat d'urbanisme", "déclaration préalable")),
    ("registry entry", ("registre", "register", "kvk", "siren", "siret", "rna", "handelsregister",
                        "company register", "association register", "charity number", "cadastre",
                        "kadaster", "land registry")),
)


@dataclass
class GreyRecord:
    title: str
    url: str
    database_id: str
    database_name: str
    grey_type: str = "other"
    year: int | None = None
    identifier: str = ""
    summary: str = ""
    organisation: str = ""
    amount: str = ""
    start_date: str = ""
    end_date: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


def classify_grey_type(*texts: str) -> str:
    """Name the grey type from the record's own words, for field I7."""
    haystack = " ".join(t.lower() for t in texts if t)
    if not haystack.strip():
        return "other"
    # Weight by needle length: "omgevingsvergunning" identifies a permit far more
    # specifically than "gemeente" identifies a government report, and counting
    # bare hits lets the vaguer word win.
    best = "other"
    best_score = 0.0
    for label, needles in GREY_TYPE_PATTERNS:
        score = sum(len(needle) for needle in needles if needle in haystack)
        if score > best_score:
            best, best_score = label, score
    return best


def build_queries(
    *,
    names: Iterable[str],
    entity_names: Iterable[str],
    locality: str | None,
    country: str | None,
    templates: Iterable[str],
) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()
    name_list = [n for n in dict.fromkeys(n for n in names if n)]
    entity_list = [n for n in dict.fromkeys(n for n in entity_names if n)]

    for template in templates:
        subjects = entity_list if "{entity}" in template else name_list
        for subject in subjects or name_list:
            query = (
                template.replace("{name}", subject)
                .replace("{entity}", subject)
                .replace("{place}", locality or "")
                .replace("{country}", country or "")
            )
            cleaned = " ".join(query.split())
            if cleaned and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                queries.append(cleaned)
    return queries


#: Grey databases that page, and the parameter that moves the window.
#: Registries and gazetteers are deliberately absent: a company register returns
#: one match for one name and paging it is noise, not coverage.
PAGING = {
    "openaire_projects": ("page", "page", 1),
    "opencorporates": ("page", "page", 1),
    "fr_rna_associations": ("page", "page", 1),
    "fr_annuaire_entreprises": ("page", "page", 1),
}


def supports_paging(database: dict[str, Any]) -> bool:
    return database.get("id") in PAGING


def request_for(database: dict[str, Any], query: str, *, rows: int,
                api_key: str | None, page: int = 0
                ) -> tuple[str, dict[str, str]] | None:
    """Build a request for a grey/funding/registry API, or None if not automatable.

    `page` is 0-based; a database absent from `PAGING` ignores it.
    """
    built = _build_request(database, query, rows=rows, api_key=api_key)
    if built is None or not page:
        return built
    url, headers = built
    entry = PAGING.get(str(database.get("id")))
    if not entry:
        return built
    name, _style, base = entry
    joiner = "&" if "?" in url else "?"
    return f"{url}{joiner}{urlencode({name: str(base + page)})}", headers


def _build_request(database: dict[str, Any], query: str, *, rows: int,
                   api_key: str | None) -> tuple[str, dict[str, str]] | None:
    db_id = database.get("id")
    endpoint = database.get("endpoint")
    if database.get("access") != "api" or not endpoint:
        return None
    headers = {"Accept": "application/json"}

    if db_id == "openaire_projects":
        return f"{endpoint}?{urlencode({'keywords': query, 'size': str(rows), 'format': 'json'})}", headers
    if db_id == "opencorporates":
        if not api_key:
            return None
        return f"{endpoint}?{urlencode({'q': query, 'api_token': api_key, 'per_page': str(rows)})}", headers
    if db_id == "fr_rna_associations":
        return f"{endpoint}{query.replace(' ', '%20')}?{urlencode({'per_page': str(min(rows, 20))})}", headers
    if db_id == "fr_annuaire_entreprises":
        return f"{endpoint}?{urlencode({'q': query, 'per_page': str(min(rows, 20))})}", headers
    if db_id == "openstreetmap_nominatim":
        return (f"{endpoint}?{urlencode({'q': query, 'format': 'jsonv2', 'limit': str(min(rows, 10))})}",
                headers)
    return None


def parse_response(database: dict[str, Any], payload: str) -> list[GreyRecord]:
    db_id = str(database.get("id"))
    name = str(database.get("name", db_id))
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []

    records: list[GreyRecord] = []
    if db_id == "openaire_projects":
        results = (((data.get("response") or {}).get("results") or {}).get("result") or [])
        if isinstance(results, dict):
            results = [results]
        for entry in results:
            meta = (((entry.get("metadata") or {}).get("oaf:entity") or {}).get("oaf:project") or {})
            if not meta:
                continue
            title = _text(meta.get("title"))
            records.append(
                GreyRecord(
                    title=title,
                    url=_text(meta.get("websiteurl")),
                    database_id=db_id,
                    database_name=name,
                    grey_type="grant record",
                    identifier=_text(meta.get("code")),
                    year=_year(meta.get("startdate")),
                    start_date=_text(meta.get("startdate")),
                    end_date=_text(meta.get("enddate")),
                    organisation=_text(meta.get("legalname")),
                    amount=_text(meta.get("fundedamount")),
                    summary=_text(meta.get("summary"))[:4000],
                    raw=meta,
                )
            )
    elif db_id == "opencorporates":
        for item in ((data.get("results") or {}).get("companies") or []):
            company = item.get("company") or {}
            records.append(
                GreyRecord(
                    title=_text(company.get("name")),
                    url=_text(company.get("opencorporates_url")),
                    database_id=db_id,
                    database_name=name,
                    grey_type="registry entry",
                    identifier=_text(company.get("company_number")),
                    year=_year(company.get("incorporation_date")),
                    start_date=_text(company.get("incorporation_date")),
                    organisation=_text(company.get("jurisdiction_code")),
                    raw=company,
                )
            )
    elif db_id in ("fr_rna_associations", "fr_annuaire_entreprises"):
        items = data.get("association") or data.get("results") or []
        if isinstance(items, dict):
            items = [items]
        for item in items:
            records.append(
                GreyRecord(
                    title=_text(item.get("titre") or item.get("nom_complet") or item.get("nom_raison_sociale")),
                    url=_text(item.get("site_web") or ""),
                    database_id=db_id,
                    database_name=name,
                    grey_type="registry entry",
                    identifier=_text(item.get("id_association") or item.get("siren")),
                    year=_year(item.get("date_creation") or item.get("date_declaration")),
                    start_date=_text(item.get("date_creation") or item.get("date_declaration")),
                    organisation=_text(item.get("objet") or item.get("activite_principale"))[:600],
                    raw=item,
                )
            )
    elif db_id == "openstreetmap_nominatim":
        for item in data if isinstance(data, list) else []:
            records.append(
                GreyRecord(
                    title=_text(item.get("display_name")),
                    url=f"https://www.openstreetmap.org/{_text(item.get('osm_type'))}/{_text(item.get('osm_id'))}",
                    database_id=db_id,
                    database_name=name,
                    grey_type="registry entry",
                    identifier=f"{_text(item.get('lat'))},{_text(item.get('lon'))}",
                    summary=_text(item.get("category")) + " " + _text(item.get("type")),
                    raw=item,
                )
            )
    return records


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("$", "content", "value", "name"):
            if key in value:
                return _text(value[key])
        return ""
    if isinstance(value, list):
        return "; ".join(_text(v) for v in value if v)
    return str(value).strip()


def _year(value: Any) -> int | None:
    match = re.search(r"\b(1[89]\d{2}|20\d{2})\b", str(value or ""))
    return int(match.group(1)) if match else None
