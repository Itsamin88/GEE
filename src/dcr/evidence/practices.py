"""Practice detection and coding.

A keyword match is a CANDIDATE, never a code. The level comes from who said it,
how specific the statement is, and whether it recurs across years
(decision DCR-D019):

  evidenced         an external class (S1, S2, S6) or dated visual source, WITH specificity
  documented        the community's own material, specific AND continuous across years
  claimed           the community's own material, without specificity or continuity
  explicitly absent a denial in the same sentence as the practice term
  not mentioned     no hit at all — never read as absence (register Block F)
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

LEVELS = ("evidenced", "documented", "claimed", "explicitly absent", "not mentioned")
EXTERNAL_CLASSES = {"S1", "S2", "S6"}
COMMUNITY_CLASSES = {"S3", "S4", "S5", "S7", "S8"}

# Community websites and extracted PDF text drop accents often enough that
# accent-sensitive matching silently loses French, Portuguese and Spanish
# evidence. Folding is one-to-one so character offsets stay valid.
def _build_fold_table() -> dict[int, str]:
    """Map each accented Latin letter to its base letter, one character to one.

    Built with unicodedata so the table covers every Latin accent the study's
    languages use, and length-preserving so character offsets stay valid.
    """
    table: dict[int, str] = {}
    for code in range(0x00C0, 0x0250):
        char = chr(code)
        decomposed = unicodedata.normalize("NFKD", char)
        base = "".join(c for c in decomposed if not unicodedata.combining(c))
        if len(base) == 1 and base != char and base.isascii() and base.isalpha():
            table[code] = base
    return table


_FOLD = _build_fold_table()


def fold(text: str) -> str:
    """Accent-fold, preserving length so character offsets remain valid."""
    return (text or "").translate(_FOLD)


# Practices whose vocabulary is itself a negation ("no-till", "sans labour").
# Marking a denial beside such a term would double-negate it into nonsense.
NEGATIVE_PHRASING_PRACTICES = {"pc04_no_till", "pc12_organic"}


@dataclass
class PracticeHit:
    """One sentence that mentions one practice, with everything needed to code it."""

    practice: str
    sentence: str
    matched_term: str
    language: str
    char_start: int
    char_end: int
    specific: bool = False
    specificity_marker: str = ""
    denial: bool = False
    denial_marker: str = ""
    year: int | None = None
    source_class: str = "S4"
    source_id: str | None = None
    document_id: str | None = None
    page_id: str | None = None
    image_id: str | None = None
    locator: str | None = None
    publication_date: str | None = None
    reference_year: int | None = None
    independence_group: str | None = None


@dataclass
class PracticeCoding:
    practice: str
    level: str
    rationale: str
    hits: list[PracticeHit] = field(default_factory=list)
    supporting_years: list[int] = field(default_factory=list)
    external_support: bool = False
    note: str = ""


class PracticeDetector:
    """Compiles the lexicon once and scans text with it."""

    def __init__(self, lexicon: Mapping[str, Any]):
        self.lexicon = lexicon
        self._patterns: dict[str, list[tuple[str, re.Pattern[str]]]] = {}
        self._excludes: dict[str, list[re.Pattern[str]]] = {}
        self._denials: list[tuple[str, re.Pattern[str]]] = []
        self._specificity: list[re.Pattern[str]] = []
        self._compile()

    def _compile(self) -> None:
        for practice, spec in self.lexicon.get("practices", {}).items():
            compiled: list[tuple[str, re.Pattern[str]]] = []
            for language, terms in (spec.get("include") or {}).items():
                for term in terms:
                    folded = fold(term)
                    try:
                        compiled.append((language, re.compile(folded, re.IGNORECASE | re.UNICODE)))
                    except re.error:
                        compiled.append((language, re.compile(re.escape(folded), re.IGNORECASE)))
            self._patterns[practice] = compiled
            excludes = []
            for term in spec.get("exclude") or []:
                folded = fold(term)
                try:
                    excludes.append(re.compile(folded, re.IGNORECASE | re.UNICODE))
                except re.error:
                    excludes.append(re.compile(re.escape(folded), re.IGNORECASE))
            self._excludes[practice] = excludes

        for language, markers in (self.lexicon.get("denial_markers") or {}).items():
            for marker in markers:
                try:
                    self._denials.append(
                        (language, re.compile(fold(marker), re.IGNORECASE | re.UNICODE))
                    )
                except re.error:
                    continue
        for marker in self.lexicon.get("specificity_markers") or []:
            try:
                self._specificity.append(re.compile(fold(marker), re.IGNORECASE | re.UNICODE))
            except re.error:
                continue

    def scan(
        self,
        sentence_spans: Iterable[tuple[int, int, str]],
        *,
        source_class: str = "S4",
        source_id: str | None = None,
        document_id: str | None = None,
        page_id: str | None = None,
        locator: str | None = None,
        publication_date: str | None = None,
        independence_group: str | None = None,
    ) -> list[PracticeHit]:
        hits: list[PracticeHit] = []
        for start, end, sentence in sentence_spans:
            if len(sentence) < 12:
                continue
            folded = fold(sentence)
            for practice, patterns in self._patterns.items():
                if any(pattern.search(folded) for pattern in self._excludes.get(practice, [])):
                    continue
                for language, pattern in patterns:
                    match = pattern.search(folded)
                    if not match:
                        continue
                    specific, marker = self._is_specific(folded)
                    if practice in NEGATIVE_PHRASING_PRACTICES:
                        denial, denial_marker = False, ""
                    else:
                        denial, denial_marker = self._is_denial(folded, match.start())
                    hits.append(
                        PracticeHit(
                            practice=practice,
                            sentence=sentence[:2000],
                            matched_term=sentence[match.start():match.end()][:120],
                            language=language,
                            char_start=start,
                            char_end=end,
                            specific=specific,
                            specificity_marker=marker,
                            denial=denial,
                            denial_marker=denial_marker,
                            year=_year_in(sentence),
                            source_class=source_class,
                            source_id=source_id,
                            document_id=document_id,
                            page_id=page_id,
                            locator=locator,
                            publication_date=publication_date,
                            reference_year=_year_in(sentence),
                            independence_group=independence_group,
                        )
                    )
                    break   # one hit per practice per sentence
        return hits

    def _is_specific(self, sentence: str) -> tuple[bool, str]:
        for pattern in self._specificity:
            match = pattern.search(sentence)
            if match:
                return True, match.group()[:80]
        return False, ""

    def _is_denial(self, sentence: str, term_position: int) -> tuple[bool, str]:
        """A denial only counts in the same sentence as the practice term."""
        for _, pattern in self._denials:
            match = pattern.search(sentence)
            if match and abs(match.start() - term_position) <= 160:
                return True, match.group()[:80]
        return False, ""

    def certifiers_in(self, text: str) -> list[str]:
        names = (self.lexicon.get("practices", {})
                 .get("pc12_organic", {})
                 .get("certifier_names", []))
        folded = fold(text or "")
        return [name for name in names
                if re.search(re.escape(fold(name)), folded, re.IGNORECASE)]


def code_practices(
    hits: Iterable[PracticeHit],
    *,
    all_practices: Iterable[str],
    continuity_gap_years: int = 2,
) -> dict[str, PracticeCoding]:
    """Turn candidate hits into coding levels, by rule."""
    by_practice: dict[str, list[PracticeHit]] = defaultdict(list)
    for hit in hits:
        by_practice[hit.practice].append(hit)

    codings: dict[str, PracticeCoding] = {}
    for practice in all_practices:
        practice_hits = by_practice.get(practice, [])
        if not practice_hits:
            codings[practice] = PracticeCoding(
                practice=practice,
                level="not mentioned",
                rationale="no source states anything either way. This is NOT evidence of absence.",
            )
            continue

        denials = [h for h in practice_hits if h.denial]
        positives = [h for h in practice_hits if not h.denial]

        if denials and not positives:
            best = denials[0]
            codings[practice] = PracticeCoding(
                practice=practice,
                level="explicitly absent",
                rationale=f"a source states it does not do this: {best.denial_marker!r} in the "
                          f"same sentence as {best.matched_term!r}",
                hits=denials,
            )
            continue

        external = [h for h in positives if h.source_class in EXTERNAL_CLASSES]
        specific = [h for h in positives if h.specific]
        specific_external = [h for h in external if h.specific]
        years = sorted({y for y in (h.reference_year or _date_year(h.publication_date)
                                    for h in positives) if y})

        if specific_external:
            best = specific_external[0]
            level = "evidenced"
            rationale = (
                f"an external source ({best.source_class}) states it specifically: "
                f"{best.specificity_marker!r} in {best.matched_term!r}"
            )
        elif specific and len(years) >= 2 and (max(years) - min(years)) >= continuity_gap_years:
            level = "documented"
            rationale = (
                f"the community describes it specifically and consistently across "
                f"{min(years)}-{max(years)}"
            )
        elif specific:
            level = "documented" if len(positives) >= 2 else "claimed"
            rationale = (
                f"specific statement ({specific[0].specificity_marker!r}) but "
                + ("repeated in the community's own material without independent corroboration"
                   if len(positives) >= 2
                   else "stated once, without corroboration or continuity")
            )
        elif external:
            level = "claimed"
            rationale = (
                f"an external source ({external[0].source_class}) mentions it, but without "
                "the specificity that would make it evidenced"
            )
        else:
            level = "claimed"
            rationale = "asserted without specificity or corroboration"

        if denials and positives:
            rationale += (
                f"; a denial also appears ({denials[0].denial_marker!r}) — the contradiction is "
                "preserved and flagged for review"
            )

        codings[practice] = PracticeCoding(
            practice=practice,
            level=level,
            rationale=rationale,
            hits=positives + denials,
            supporting_years=years,
            external_support=bool(external),
            note="contradictory statements" if (denials and positives) else "",
        )
    return codings


def _year_in(text: str) -> int | None:
    match = re.search(r"\b(19[5-9]\d|20[0-4]\d)\b", text or "")
    return int(match.group(1)) if match else None


def _date_year(value: str | None) -> int | None:
    return _year_in(value or "")
