"""The same report in three languages is one report.

A community that publishes its annual report in English, German and Portuguese
gives the crawler three PDFs, three content hashes and three sets of extracted
text. Nothing so far has any way of knowing they are the same document, so it
parses all three, mines all three, and produces three copies of every figure in
them — from three "different" documents, which then look like three
corroborating sources.

That is expensive twice over. It wastes the parse (brief §20), and it inflates
the evidence: three copies of one report are one source, not three, and counting
them as three would breach the independence rule the whole protocol rests on
(register v2.4 §9, brief §28).

## What makes two documents one document

Cheap signals first, and nothing expensive unless the cheap ones are suggestive.

1. **The same bytes.** Identical content hash: the same file, reached twice.
2. **The same file, differently named.** `report-2019.pdf` and
   `report-2019-v2.pdf`; `rapport_2019_DE.pdf` and `rapport_2019_EN.pdf`. The
   language tag, the version suffix and the separator style are stripped and
   what remains is compared.
3. **The same document, different language.** Same normalised stem, same year,
   different language tag — or the same page linking to both under labels that
   are themselves language names.
4. **The same size and structure.** Same page count and a byte size within a few
   per cent: a translation of a laid-out report is very nearly the same length.

None of these is conclusive alone. A family is formed when two of them agree,
and a family formed on weak evidence is flagged for a human rather than acted on
silently (brief §80, §81).

## What a family is for

**One primary, deep-parsed.** The primary is chosen by usefulness to the study:
the language the crawler can mine best, then the largest, then the earliest
reached. The others are recorded, hashed and stored, but not deep-parsed unless
they turn out to say something different.

**One independence group.** Every member inherits the primary's group, so the
three translations cannot corroborate one another.

**A member is still opened if it might differ.** A version with a materially
different page count, or one from a different publisher, is not a translation —
it is another document, and it is parsed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import unquote, urlsplit

# ---------------------------------------------------------------------------
# Recognising the parts of a filename that vary between versions
# ---------------------------------------------------------------------------
#: Language tags as they appear in filenames and URL segments. Deliberately
#: bounded by separators so `report_de_luxe` is not read as German.
LANGUAGE_TAGS: dict[str, str] = {
    "en": "English", "eng": "English", "english": "English",
    "de": "German", "ger": "German", "deu": "German", "deutsch": "German",
    "fr": "French", "fra": "French", "fre": "French", "francais": "French",
    "pt": "Portuguese", "por": "Portuguese", "portugues": "Portuguese",
    "es": "Spanish", "spa": "Spanish", "espanol": "Spanish", "castellano": "Spanish",
    "nl": "Dutch", "nld": "Dutch", "dut": "Dutch", "nederlands": "Dutch",
    "it": "Italian", "ita": "Italian", "italiano": "Italian",
    "da": "Danish", "sv": "Swedish", "no": "Norwegian", "nb": "Norwegian",
    "fi": "Finnish", "pl": "Polish", "cs": "Czech", "hu": "Hungarian",
    "ro": "Romanian", "el": "Greek", "tr": "Turkish", "ru": "Russian",
    "ca": "Catalan", "eu": "Basque", "gl": "Galician",
}

#: Version and copy suffixes that do not make a different document.
_VERSION = re.compile(
    r"[-_\s]*[(\[]?(?:v|ver|version|rev|revision|copy|final|draft|def)"
    r"[-_\s.]*\d{0,3}[)\]]?$", re.IGNORECASE)

_YEAR = re.compile(r"(?<!\d)(1[89]\d{2}|20\d{2})(?!\d)")
_SEPARATORS = re.compile(r"[-_.\s+]+")
_NOISE = re.compile(r"\b(?:final|draft|web|print|lowres|hires|small|large|compressed|"
                    r"screen|online|opt|optimised|optimized)\b", re.IGNORECASE)


def _stem_of(url_or_name: str) -> str:
    text = unquote(url_or_name or "")
    if "//" in text or text.startswith("/"):
        text = urlsplit(text).path
    return PurePosixPath(text).stem


def language_tag(url_or_name: str) -> str | None:
    """The language a filename or URL declares, if it declares one."""
    stem = _stem_of(url_or_name).lower()
    parts = [part for part in _SEPARATORS.split(stem) if part]
    for part in parts:
        if part in LANGUAGE_TAGS:
            return LANGUAGE_TAGS[part]
    # /en/reports/annual-2019.pdf — the tag can be a path segment instead.
    path = urlsplit(unquote(url_or_name or "")).path.lower()
    for segment in path.split("/"):
        if segment in LANGUAGE_TAGS:
            return LANGUAGE_TAGS[segment]
    return None


def normalised_stem(url_or_name: str) -> str:
    """The filename with everything that varies between versions removed.

    `rapport_annuel_2019_DE_v2.pdf` and `rapport-annuel-2019-en.pdf` both
    reduce to `rapport annuel`, with the year kept separately so two different
    years are never one family.
    """
    stem = _stem_of(url_or_name).lower()
    stem = _VERSION.sub("", stem)
    parts = [part for part in _SEPARATORS.split(stem) if part]
    kept = [part for part in parts
            if part not in LANGUAGE_TAGS
            and not _YEAR.fullmatch(part)
            and not _NOISE.fullmatch(part)
            and not part.isdigit()]
    return " ".join(kept).strip()


def stated_year(url_or_name: str, title: str = "") -> int | None:
    for candidate in (_stem_of(url_or_name), title or ""):
        match = _YEAR.search(candidate)
        if match:
            return int(match.group(1))
    return None


@dataclass
class DocumentRef:
    """What is known about one document cheaply, before it is parsed."""

    document_id: str
    url: str
    filename: str = ""
    title: str = ""
    content_hash: str = ""
    bytes_len: int = 0
    pages: int | None = None
    language: str = ""
    mime: str = ""
    source_id: str = ""
    independence_group: str = ""
    #: Where it sits in the crawl's own ordering, used only to break ties.
    discovered_index: int = 0

    @property
    def stem(self) -> str:
        return normalised_stem(self.filename or self.url)

    @property
    def declared_language(self) -> str:
        return self.language or (language_tag(self.filename or self.url) or "")

    @property
    def year(self) -> int | None:
        return stated_year(self.filename or self.url, self.title)


@dataclass
class Family:
    """Documents judged to be versions of one document."""

    family_id: str
    members: list[DocumentRef] = field(default_factory=list)
    primary_id: str = ""
    reasons: list[str] = field(default_factory=list)
    #: True when the evidence for grouping was weak enough that a coder should
    #: confirm it. The crawler still acts on it; it does not hide it.
    uncertain: bool = False

    @property
    def size(self) -> int:
        return len(self.members)

    def primary(self) -> DocumentRef | None:
        for member in self.members:
            if member.document_id == self.primary_id:
                return member
        return self.members[0] if self.members else None

    def others(self) -> list[DocumentRef]:
        return [m for m in self.members if m.document_id != self.primary_id]

    def as_dict(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "primary": self.primary_id,
            "members": [m.document_id for m in self.members],
            "languages": sorted({m.declared_language for m in self.members
                                 if m.declared_language}),
            "reasons": list(self.reasons),
            "needs_human_review": self.uncertain,
        }


#: How well the crawler can mine each language, best first. A report it can read
#: properly is worth more as the primary than one it can only skim.
_LANGUAGE_PREFERENCE = ("English", "German", "French", "Spanish", "Portuguese",
                        "Dutch", "Italian")


def _preference(language: str) -> int:
    try:
        return _LANGUAGE_PREFERENCE.index(language)
    except ValueError:
        return len(_LANGUAGE_PREFERENCE)


def _similar_size(a: DocumentRef, b: DocumentRef, tolerance: float = 0.35) -> bool:
    if not a.bytes_len or not b.bytes_len:
        return False
    larger = max(a.bytes_len, b.bytes_len)
    return abs(a.bytes_len - b.bytes_len) / larger <= tolerance


def _same_pages(a: DocumentRef, b: DocumentRef) -> bool:
    if a.pages is None or b.pages is None:
        return False
    if a.pages == 0 or b.pages == 0:
        return False
    return abs(a.pages - b.pages) <= max(1, round(0.05 * max(a.pages, b.pages)))


def relate(a: DocumentRef, b: DocumentRef) -> tuple[float, list[str]]:
    """How strongly do these two look like one document? Score and reasons.

    Cheap comparisons only: filenames, sizes, page counts and declared
    languages. Nothing here opens a file, which is the point — the decision has
    to be made BEFORE paying to parse the second copy (brief §19, §20).
    """
    reasons: list[str] = []
    score = 0.0

    if a.content_hash and a.content_hash == b.content_hash:
        return 1.0, ["identical content hash: the same file reached twice"]

    stem_a, stem_b = a.stem, b.stem
    if stem_a and stem_a == stem_b:
        score += 0.5
        reasons.append(f"the same filename once versions and language tags are "
                       f"removed ({stem_a!r})")
    elif stem_a and stem_b and (stem_a in stem_b or stem_b in stem_a):
        score += 0.25
        reasons.append(f"one filename contains the other ({stem_a!r} / {stem_b!r})")

    year_a, year_b = a.year, b.year
    if year_a and year_b:
        if year_a == year_b:
            score += 0.2
            reasons.append(f"both state {year_a}")
        else:
            # Different years is decisive against: the 2018 report and the 2019
            # report are two documents however alike their filenames.
            return 0.0, [f"different years ({year_a} and {year_b}): two documents"]

    language_a, language_b = a.declared_language, b.declared_language
    if language_a and language_b and language_a != language_b:
        score += 0.3
        reasons.append(f"declared as {language_a} and {language_b}")

    if _same_pages(a, b):
        score += 0.2
        reasons.append(f"the same page count ({a.pages})")
    if _similar_size(a, b):
        score += 0.1
        reasons.append("within a third of each other in size")

    return min(1.0, score), reasons


#: Below this a pair is not a family; between this and `CERTAIN` it is a family
#: flagged for a human.
LIKELY = 0.5
CERTAIN = 0.75


def group(documents: Sequence[DocumentRef], *, prefix: str = "FAM") -> list[Family]:
    """Sort documents into families. O(n²) on purpose, and cheap enough.

    Every comparison is string and integer work on metadata already in hand, so
    even a community with four hundred documents costs a fraction of a second —
    against the minutes that deep-parsing one duplicate report would cost.
    """
    families: list[Family] = []
    assigned: dict[str, Family] = {}

    for index, document in enumerate(documents):
        best: tuple[float, Family, list[str]] | None = None
        for family in families:
            for member in family.members:
                score, reasons = relate(document, member)
                if score >= LIKELY and (best is None or score > best[0]):
                    best = (score, family, reasons)
        if best is not None:
            score, family, reasons = best
            family.members.append(document)
            family.reasons.extend(reasons)
            if score < CERTAIN:
                family.uncertain = True
            assigned[document.document_id] = family
            continue
        family = Family(family_id=f"{prefix}{len(families) + 1:03d}",
                        members=[document])
        families.append(family)
        assigned[document.document_id] = family

    for family in families:
        family.primary_id = choose_primary(family.members).document_id
        # A family of one is not a family; it just did not match anything.
        if family.size == 1:
            family.uncertain = False
            family.reasons = []
    return families


def choose_primary(members: Sequence[DocumentRef]) -> DocumentRef:
    """Which copy to deep-parse.

    The language the crawler mines best first, because a report it can read
    properly yields more than one it can only skim; then the largest, because a
    fuller version of a report is the one with the figures in it; then whichever
    was reached first, so the choice is stable across runs.
    """
    return sorted(
        members,
        key=lambda m: (_preference(m.declared_language), -m.bytes_len,
                       m.discovered_index, m.document_id),
    )[0]


def parse_plan(families: Sequence[Family]) -> dict[str, str]:
    """What to do with each document: `deep`, `metadata`, or `deep-differs`.

    A member is normally recorded from its metadata alone. It is still parsed
    when its page count differs materially from the primary's, because that is
    not a translation — it is a different document that happens to be named
    like one, and treating it as a duplicate would lose whatever it adds.
    """
    plan: dict[str, str] = {}
    for family in families:
        primary = family.primary()
        if primary is None:
            continue
        plan[primary.document_id] = "deep"
        for member in family.others():
            if primary.pages and member.pages and not _same_pages(primary, member):
                plan[member.document_id] = "deep-differs"
            else:
                plan[member.document_id] = "metadata"
    return plan


def review_cases(families: Sequence[Family]) -> list[dict[str, str]]:
    """Families a coder should confirm (brief §81)."""
    cases: list[dict[str, str]] = []
    for family in families:
        if not family.uncertain or family.size < 2:
            continue
        names = ", ".join(m.filename or m.url for m in family.members)
        cases.append({
            "category": "document_family",
            "subject": f"{family.size} documents grouped as one ({family.family_id})",
            "detail": (
                f"{names}. Grouped because: {'; '.join(family.reasons[:4])}. "
                f"Only {family.primary_id} was parsed in full, and all of them share "
                "one independence group, so they cannot corroborate each other. "
                "If these are in fact different documents, the others should be "
                "parsed and separated."),
            "severity": "normal",
            "suggested_action": "confirm the grouping, or split the family",
        })
    return cases


def savings(families: Sequence[Family]) -> dict[str, int]:
    """What grouping saved, for the report."""
    total = sum(family.size for family in families)
    plan = parse_plan(families)
    deep = sum(1 for state in plan.values() if state.startswith("deep"))
    return {
        "documents": total,
        "families": len(families),
        "deep_parsed": deep,
        "recorded_from_metadata": total - deep,
        "grouped": sum(family.size for family in families if family.size > 1),
    }


__all__ = [
    "CERTAIN", "DocumentRef", "Family", "LANGUAGE_TAGS", "LIKELY", "choose_primary",
    "group", "language_tag", "normalised_stem", "parse_plan", "relate",
    "review_cases", "savings", "stated_year",
]
