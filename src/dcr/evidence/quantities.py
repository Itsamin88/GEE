"""Quantity extraction: areas, populations and dates, with the sentence intact.

Rule 8 of the register is absolute: do not convert, round or harmonise. Both
forms are kept — ``original_value`` exactly as the source states it, and
``normalized_value`` for comparison — and the sentence that carried them is
stored alongside (brief §31, rule 8 and rule 9).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

# "4 ha", "4,5 hectares", "about 15 hectares", "1 200 m²", "10 acres"
_NUMBER = r"(?:\d{1,3}(?:[   .,]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
_APPROX = r"(?:about|around|roughly|approx\.?|approximately|some|nearly|over|more than|under|less than|" \
          r"environ|pr[eè]s de|quelque|plus de|moins de|ongeveer|circa|ca\.|rond|meer dan|minder dan|" \
          r"etwa|ungef[aä]hr|rund|mehr als|unos|alrededor de|cerca de|m[aá]s de|" \
          r"aproximadamente|quase|mais de)"
_RANGE_JOIN = r"(?:-|–|—|to|and|[àa]|et|tot|en|bis|und|hasta|a|até|e)"


@dataclass
class AreaMention:
    value_ha: float
    original: str
    unit: str
    sentence: str
    char_start: int
    char_end: int
    approximate: bool = False
    lower_ha: float | None = None
    upper_ha: float | None = None
    kind: str = "unclassified"        # managed | total_holding | unclassified
    kind_reason: str = ""
    reference_year: int | None = None


@dataclass
class PopulationMention:
    value: int
    original: str
    sentence: str
    char_start: int
    char_end: int
    lower: int | None = None
    upper: int | None = None
    kind: str = "unclassified"        # permanent | visitors | unclassified
    kind_reason: str = ""
    reference_year: int | None = None


def _to_float(text: str) -> float | None:
    cleaned = text.strip().replace(" ", "").replace(" ", "").replace(" ", "")
    # Decide which separator is decimal: "1.234,5" vs "1,234.5" vs "4,5" vs "4.5"
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        parts = cleaned.split(",")
        cleaned = cleaned.replace(",", "." if len(parts[-1]) != 3 else "")
    elif cleaned.count(".") == 1 and len(cleaned.split(".")[-1]) == 3 and len(cleaned.split(".")[0]) <= 3:
        # "1.200" is one thousand two hundred in most European writing
        cleaned = cleaned.replace(".", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def find_areas(text: str, units: Mapping[str, float], sentence_spans: Iterable[tuple[int, int, str]],
               *, markers: Mapping[str, list[str]] | None = None) -> list[AreaMention]:
    """Every area figure in the text, with the sentence that stated it."""
    unit_alternatives = sorted(units.keys(), key=len, reverse=True)
    unit_pattern = "|".join(re.escape(u) for u in unit_alternatives)
    pattern = re.compile(
        rf"(?P<approx>{_APPROX}\s+)?"
        rf"(?P<low>{_NUMBER})"
        rf"(?:\s*{_RANGE_JOIN}\s*(?P<high>{_NUMBER}))?"
        rf"\s*(?P<unit>{unit_pattern})\b",
        re.IGNORECASE,
    )
    spans = list(sentence_spans)
    mentions: list[AreaMention] = []
    for match in pattern.finditer(text):
        unit = match.group("unit").lower()
        factor = units.get(unit) or units.get(unit.rstrip("s")) or None
        if factor is None:
            continue
        low = _to_float(match.group("low"))
        if low is None:
            continue
        high = _to_float(match.group("high")) if match.group("high") else None
        sentence, s_start, s_end = _sentence_for(match.start(), spans, text)
        value = low * factor
        mention = AreaMention(
            value_ha=round(value, 4),
            original=match.group().strip(),
            unit=unit,
            sentence=sentence,
            char_start=s_start,
            char_end=s_end,
            approximate=bool(match.group("approx")),
            lower_ha=round(low * factor, 4) if high else None,
            upper_ha=round(high * factor, 4) if high else None,
            reference_year=_reference_year(sentence),
        )
        if high:
            mention.value_ha = round(low * factor, 4)
        mention.kind, mention.kind_reason = classify_area(sentence, markers or {})
        mentions.append(mention)
    return mentions


def classify_area(sentence: str, markers: Mapping[str, list[str]]) -> tuple[str, str]:
    """Worked land or the whole holding? Confusing them moves a community two size classes."""
    lowered = sentence.lower()
    managed = _first_marker(lowered, markers.get("managed_area_markers", {}))
    total = _first_marker(lowered, markers.get("total_holding_markers", {}))
    if managed and not total:
        return "managed", f"the sentence says {managed!r}"
    if total and not managed:
        return "total_holding", f"the sentence says {total!r}"
    if managed and total:
        # Both present: prefer the marker nearer the number.
        return "unclassified", (
            f"the sentence carries both a worked-land marker ({managed!r}) and a "
            f"holding marker ({total!r}); needs a human reading"
        )
    return "unclassified", "no marker distinguishing worked land from the whole holding"


# Nouns that actually denote people living somewhere. A pronoun ("nous", "we")
# is not one: matching on those made "En 2017 nous avons creusé" read as a
# population of 2017, which is exactly the kind of silent fabrication the
# register's rule 1 forbids.
RESIDENT_NOUNS = (
    "residents", "resident", "inhabitants", "inhabitant", "people", "adults", "adult",
    "children", "members", "member", "households", "dwellers", "villagers",
    "habitants", "habitant", "residents", "personnes", "adultes", "enfants", "foyers",
    "bewoners", "inwoners", "mensen", "volwassenen", "kinderen", "huishoudens", "leden",
    "bewohner", "einwohner", "menschen", "erwachsene", "kinder", "haushalte", "mitglieder",
    "habitantes", "residentes", "personas", "adultos", "pessoas", "moradores",
    "abitanti", "persone", "adulti", "invanare", "beboere", "indbyggere",
)

# "we are 40", "nous sommes 28", "wij zijn met 12": the count follows the phrase.
_WE_ARE = re.compile(
    r"\b(?:we are|we're|nous sommes|on est|wij zijn met|wij zijn|wir sind|somos|siamo|somos)\s+"
    r"(?P<count>\d{1,4})\b",
    re.IGNORECASE,
)

_YEAR_LIKE = re.compile(r"^(1[89]\d{2}|20\d{2})$")


def find_populations(text: str, sentence_spans: Iterable[tuple[int, int, str]],
                     *, markers: Mapping[str, Any] | None = None) -> list[PopulationMention]:
    """Population figures, with the visitor/resident distinction preserved.

    A figure is only taken when a RESIDENT NOUN follows it, or when a
    "we are N" phrase carries it. Four-digit year-shaped numbers are refused
    unless the noun makes them unambiguous.
    """
    spans = list(sentence_spans)
    marker_map = dict(markers or {})
    visitor_words = _flatten(marker_map.get("visitor_markers", {}))
    mentions: list[PopulationMention] = []
    seen: set[tuple[int, int]] = set()

    noun_alternatives = "|".join(sorted(set(RESIDENT_NOUNS), key=len, reverse=True))
    pattern = re.compile(
        rf"(?P<approx>{_APPROX}\s+)?(?P<low>\d{{1,4}})"
        rf"(?:\s*{_RANGE_JOIN}\s*(?P<high>\d{{1,4}}))?"
        rf"\s+(?:\w+\s+){{0,2}}(?P<noun>{noun_alternatives})\b",
        re.IGNORECASE,
    )

    def add(value_text: str, high_text: str | None, position: int,
            approximate: bool, noun: str) -> None:
        if _YEAR_LIKE.match(value_text) and noun.lower() not in RESIDENT_NOUNS:
            return
        try:
            value = int(value_text)
        except ValueError:
            return
        if value <= 0 or value > 5000:
            return
        sentence, start, end = _sentence_for(position, spans, text)
        if (start, value) in seen:
            return
        seen.add((start, value))
        lowered = sentence.lower()
        visitor_hit = _first_marker(lowered, {"x": visitor_words})
        if visitor_hit:
            kind, reason = "visitors", (
                f"the sentence says {visitor_hit!r}, so this is not a permanent-resident count"
            )
        else:
            kind, reason = "permanent", (
                f"counted as {noun!r} with no visitor or volunteer marker in the sentence"
            )
        mentions.append(
            PopulationMention(
                value=value,
                original=text[max(0, position - 2): position + 40].strip(),
                sentence=sentence,
                char_start=start,
                char_end=end,
                lower=value if high_text else None,
                upper=int(high_text) if high_text and high_text.isdigit() else None,
                kind=kind,
                kind_reason=reason,
                reference_year=_reference_year(sentence),
            )
        )

    for match in pattern.finditer(text):
        add(match.group("low"), match.group("high"), match.start(),
            bool(match.group("approx")), match.group("noun"))

    for match in _WE_ARE.finditer(text):
        add(match.group("count"), None, match.start(), False, "residents")

    return mentions


def _flatten(mapping: Any) -> list[str]:
    if isinstance(mapping, dict):
        out: list[str] = []
        for value in mapping.values():
            out.extend(value if isinstance(value, list) else [value])
        return [str(v).lower() for v in out]
    if isinstance(mapping, list):
        return [str(v).lower() for v in mapping]
    return []


def _first_marker(lowered: str, markers: Any) -> str | None:
    """Return the WORDS that matched, not the pattern that matched them.

    These reasons are read by the researcher in documentary_area_note. A raw
    alternation like '(we|community|they) (farm|work|cultivate)s?\\b' tells them
    nothing about what the source actually said.
    """
    for marker in _flatten(markers):
        cleaned = marker.strip()
        if not cleaned:
            continue
        try:
            match = re.search(cleaned, lowered)
            if match:
                return match.group().strip()
        except re.error:
            if cleaned in lowered:
                return cleaned
    return None


def _sentence_for(position: int, spans: list[tuple[int, int, str]], text: str) -> tuple[str, int, int]:
    for start, end, chunk in spans:
        if start <= position <= end:
            return chunk, start, end
    lo = max(0, position - 160)
    hi = min(len(text), position + 160)
    return text[lo:hi].strip(), lo, hi


def _reference_year(sentence: str) -> int | None:
    """The year a figure REFERS TO, where the sentence states one.

    Distinct from publication date and from retrieval date (brief §52); this is
    what stops growth over time being recorded as a disagreement (DCR-D008).
    """
    match = re.search(
        r"\b(?:in|en|im|nel|em|sinds|since|depuis|as of|au|à partir de|vanaf|seit|desde)\s+"
        r"(19[5-9]\d|20[0-4]\d)\b",
        sentence, re.IGNORECASE,
    )
    if match:
        return int(match.group(1))
    match = re.search(r"\((19[5-9]\d|20[0-4]\d)\)", sentence)
    if match:
        return int(match.group(1))
    return None
