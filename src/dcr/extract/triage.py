"""Deciding which documents deserve the expensive work.

Opening documents is where the best evidence is: a dated project report is worth
more than the rest of a website put together. It is also where the time goes. A
rich community site carries dozens of PDFs — annual reports, a thesis, and forty
event flyers, several of them in three languages — and parsing all of them
deeply, extracting every embedded image from each, is how half an hour becomes
half a day (brief §10, §14).

Two separations do most of the work.

**Discovery before parsing.** What a document is can usually be told from its
address, its link text, its declared type and its size, before a byte of it is
downloaded. That judgement costs nothing and decides whether the rest is worth
paying for.

**One text per document family.** A report published in English, German and
Portuguese is one report. Deep-extracting all three spends three times the
budget to learn the same facts, and then produces three claims that the
reconciler has to work out are not corroboration. One is chosen for extraction;
the others are kept as provenance mirrors, which is what they are.

Nothing here decides what a document *means* — only how much attention it earns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

# -- the priority bands ----------------------------------------------------
VERY_HIGH = "VERY_HIGH"
HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"
DUPLICATE = "DUPLICATE"

BAND_ORDER = {VERY_HIGH: 0, HIGH: 1, MEDIUM: 2, LOW: 3, DUPLICATE: 4}

#: What a document has to look like to earn deep extraction. Matched against the
#: URL path, the file name and the link text together, accent-folded, in the
#: languages the study covers.
_VERY_HIGH_PATTERNS: tuple[tuple[str, str], ...] = (
    ("thesis", r"thes[ei]s|these\b|dissertat|proefschrift|tesi\b|tese\b|masterarbeit|"
               r"diplomarbeit|memoire|mestrado|doutorado"),
    ("academic paper", r"\bpaper\b|journal|article|preprint|proceedings|conference-paper"),
    ("grant or funding report", r"grant|funding|subsid|foerder|förder|leader|interreg|"
                                r"erasmus|horizon|cordis|financement|subvencion"),
    ("project report", r"project.?report|rapport.?de.?projet|projektbericht|"
                       r"relatorio.?de.?projeto|eindrapport|final.?report"),
    ("annual report", r"annual.?report|rapport.?annuel|jaarverslag|jahresbericht|"
                      r"relatorio.?anual|informe.?anual|\bbilan\b"),
    ("site or master plan", r"site.?plan|master.?plan|masterplan|plan.?de.?masse|"
                            r"inrichtingsplan|bebauungsplan|plano.?diretor|land.?use.?plan"),
    ("environmental or restoration report", r"environment|restorat|renatur|okolog|ökolog|"
                                            r"ecolog|habitat|biodivers|impact.?assessment|"
                                            r"milieu|umwelt|ambiental"),
    ("government or municipal record", r"municipal|prefeitura|gemeente|commune\b|"
                                       r"cadastr|kadaster|permit|licenc|licens|planning.?"
                                       r"application|zoning"),
    ("land or water document", r"land.?use|landgebruik|water.?retention|hydrolog|"
                               r"watershed|aquifer|terrain|parcel|hectare"),
)

_MEDIUM_PATTERNS: tuple[tuple[str, str], ...] = (
    ("newsletter", r"newsletter|bulletin|nieuwsbrief|rundbrief|boletim|circular"),
    ("brochure", r"brochure|folder|prospekt|depliant|leaflet"),
    ("community report", r"report|rapport|bericht|verslag|relatorio|informe|memoria"),
    ("conference material", r"conference|congres|tagung|symposium|workshop|seminar"),
    ("project description", r"project|projet|projekt|projeto|proyecto|programme|program"),
)

_LOW_PATTERNS: tuple[tuple[str, str], ...] = (
    ("event flyer", r"flyer|poster|einladung|invitation|invite|programme?-?\d{4}|"
                    r"festival|concert|workshop-?\d{4}|retreat|camp\b"),
    ("promotional", r"promo|advert|werbung|publicit|press.?kit|media.?kit|sponsor"),
    ("form or admin", r"\bform\b|formulaire|formular|anmeldung|booking|reservation|"
                      r"invoice|rechnung|facture|price|tarif|preisliste|menu"),
    ("legal boilerplate", r"privacy|datenschutz|impressum|terms|conditions|agb\b|"
                          r"disclaimer|cookie"),
)

#: Language markers in a file name or path. Used only to spot translations of
#: one document, never to decide what language a document is in — that is the
#: language detector's job, on the text itself.
_LANGUAGE_MARKERS = re.compile(
    r"(?:^|[-_./])(en|eng|english|de|deu|ger|german|deutsch|fr|fra|fre|french|francais|"
    r"pt|por|portuguese|portugues|es|spa|spanish|espanol|nl|nld|dut|dutch|nederlands|"
    r"it|ita|italian|italiano)(?:[-_./]|$)",
    re.IGNORECASE,
)

_YEAR = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")

#: Bytes above which a document is treated as expensive enough to need a reason.
LARGE_DOCUMENT_BYTES = 20 * 1024 * 1024


@dataclass
class DocumentVerdict:
    """How much attention one document has earned, and why."""

    band: str = MEDIUM
    score: float = 0.0
    kind: str = ""
    reason: str = ""
    year: str | None = None
    family: str = ""
    language_marker: str = ""
    deep_extract: bool = True
    extract_images: bool = True
    max_images: int = 12
    estimated_seconds: float = 4.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "priority": self.band, "score": round(self.score, 2), "kind": self.kind,
            "reason": self.reason, "year": self.year, "family": self.family,
            "deep_extract": self.deep_extract, "extract_images": self.extract_images,
            "max_images": self.max_images,
        }


def _fold(text: str) -> str:
    import unicodedata

    stripped = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in stripped if not unicodedata.combining(c)).lower()


def classify_document(
    *,
    url: str,
    link_text: str = "",
    title: str = "",
    mime: str = "",
    content_length: int | None = None,
    page_context: str = "",
    source_class: str = "",
) -> DocumentVerdict:
    """Judge a document from what is known before downloading it (brief §11)."""
    path = urlsplit(url).path or ""
    filename = path.rsplit("/", 1)[-1]
    haystack = _fold(" ".join(part for part in
                              (path, filename, link_text, title, page_context) if part))

    verdict = DocumentVerdict()
    year_match = _YEAR.search(haystack)
    verdict.year = year_match.group(1) if year_match else None
    marker = _LANGUAGE_MARKERS.search(filename)
    verdict.language_marker = (marker.group(1).lower() if marker else "")
    verdict.family = document_family(url, link_text=link_text, title=title)

    score = 0.0
    kind = ""
    for label, pattern in _VERY_HIGH_PATTERNS:
        if re.search(pattern, haystack):
            score += 6.0
            kind = label
            break
    if not kind:
        for label, pattern in _MEDIUM_PATTERNS:
            if re.search(pattern, haystack):
                score += 2.5
                kind = label
                break
    penalty = ""
    for label, pattern in _LOW_PATTERNS:
        if re.search(pattern, haystack):
            score -= 4.0
            penalty = label
            break

    # A dated document is worth more: the study is about when things happened.
    if verdict.year:
        score += 1.5
    # An academic or official source raises everything it publishes.
    if source_class in ("S1", "S2"):
        score += 2.0
    if content_length is not None:
        if content_length < 20_000:
            score -= 1.0          # a two-page flyer
        elif content_length > 400_000:
            score += 1.0          # a substantial document
        if content_length > LARGE_DOCUMENT_BYTES:
            score -= 1.5          # must earn its download

    verdict.score = score
    verdict.kind = kind or (penalty or "unclassified document")

    if score >= 7.0:
        verdict.band = VERY_HIGH
    elif score >= 4.0:
        verdict.band = HIGH
    elif score >= 1.0:
        verdict.band = MEDIUM
    else:
        verdict.band = LOW

    if penalty and not kind:
        verdict.reason = f"looks like a {penalty}"
    elif kind:
        verdict.reason = f"looks like a {kind}" + (f" from {verdict.year}" if verdict.year else "")
    else:
        verdict.reason = "nothing in its address, name or link text marks it as research material"

    # What that band buys.
    verdict.deep_extract = verdict.band in (VERY_HIGH, HIGH, MEDIUM)
    verdict.extract_images = verdict.band in (VERY_HIGH, HIGH)
    verdict.max_images = {VERY_HIGH: 20, HIGH: 12, MEDIUM: 4, LOW: 0,
                          DUPLICATE: 0}[verdict.band]
    verdict.estimated_seconds = {VERY_HIGH: 9.0, HIGH: 7.0, MEDIUM: 4.0, LOW: 1.5,
                                 DUPLICATE: 0.5}[verdict.band]
    return verdict


def document_family(url: str, *, link_text: str = "", title: str = "") -> str:
    """A key shared by translations and reprints of one underlying document.

    Built from the file name with language markers, years and separators
    removed, so `annual-report-2019-en.pdf` and `jahresbericht-2019-de.pdf`
    collide only if their stems really match. It is deliberately conservative:
    grouping two different documents would lose evidence, while failing to group
    two translations only costs time.
    """
    filename = (urlsplit(url).path or "").rsplit("/", 1)[-1]
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    folded = _fold(stem)
    folded = _LANGUAGE_MARKERS.sub("-", folded)
    # The YEAR IS KEPT. Stripping it would make the 2019 and 2020 annual
    # reports one family, and the second would be skipped as a translation of
    # the first — losing a whole year of evidence to save four seconds.
    folded = re.sub(r"[^a-z0-9]+", "-", folded).strip("-")
    folded = re.sub(r"-(v|version|rev|final|draft|copy)\d*$", "", folded)
    return folded or _fold(link_text or title)[:60]


class DocumentTriage:
    """Tracks families across a run, so one text per family is deep-extracted."""

    def __init__(self, *, max_family_deep_extractions: int = 1):
        self.max_family_deep_extractions = max(1, int(max_family_deep_extractions))
        self._family_deep: dict[str, int] = {}
        self._family_primary: dict[str, str] = {}
        #: (kind, year) -> the language marker of the document already read, so
        #: a SECOND language of the same report is recognised as a translation.
        self._translation_primary: dict[tuple[str, str], tuple[str, str]] = {}
        self.mirrors: dict[str, str] = {}
        self.counts: dict[str, int] = {}

    def _translation_of(self, verdict: DocumentVerdict) -> str | None:
        """The document this one appears to be a translation of, if any.

        Deliberately narrow. Three signals must all agree: the same document
        kind, the same year, and a DIFFERENT language marker in the file name.
        Without the language marker two annual reports from one year are simply
        two documents, and merging them would lose evidence — which is a worse
        error than spending a few seconds reading both.
        """
        if not (verdict.kind and verdict.year and verdict.language_marker):
            return None
        key = (verdict.kind, verdict.year)
        primary = self._translation_primary.get(key)
        if primary is None:
            return None
        primary_url, primary_marker = primary
        if primary_marker == verdict.language_marker:
            return None
        return primary_url

    def judge(self, *, url: str, link_text: str = "", title: str = "", mime: str = "",
              content_length: int | None = None, page_context: str = "",
              source_class: str = "") -> DocumentVerdict:
        verdict = classify_document(
            url=url, link_text=link_text, title=title, mime=mime,
            content_length=content_length, page_context=page_context,
            source_class=source_class)
        family = verdict.family
        translation_of = self._translation_of(verdict)
        if translation_of and verdict.deep_extract:
            verdict.band = DUPLICATE
            verdict.deep_extract = False
            verdict.extract_images = False
            verdict.max_images = 0
            verdict.reason = (
                f"appears to be the {verdict.language_marker} translation of "
                f"{translation_of.rsplit('/', 1)[-1]}, which has already been read in "
                "full; kept as a provenance mirror")
            self.mirrors[url] = translation_of
        elif family and verdict.deep_extract:
            already = self._family_deep.get(family, 0)
            if already >= self.max_family_deep_extractions:
                # A translation or reprint of something already read in full.
                verdict.band = DUPLICATE
                verdict.deep_extract = False
                verdict.extract_images = False
                verdict.max_images = 0
                primary = self._family_primary.get(family, "")
                verdict.reason = (
                    "another document in the same family has already been read in full"
                    + (f" ({primary})" if primary else "")
                    + "; this one is kept as a provenance mirror")
                self.mirrors[url] = primary
        # Claim the family slot HERE, not after the document has been parsed.
        # A batch of documents is fetched concurrently, so all three languages
        # of one report are judged before any of them has been read — and a
        # claim registered afterwards would come too late for every one of them.
        if verdict.deep_extract:
            self._claim(url, verdict)
        self.counts[verdict.band] = self.counts.get(verdict.band, 0) + 1
        return verdict

    def _claim(self, url: str, verdict: DocumentVerdict) -> None:
        """Record that this document is the one being read in full."""
        if verdict.kind and verdict.year and verdict.language_marker:
            self._translation_primary.setdefault(
                (verdict.kind, verdict.year), (url, verdict.language_marker))
        if verdict.family:
            self._family_deep[verdict.family] = (
                self._family_deep.get(verdict.family, 0) + 1)
            self._family_primary.setdefault(verdict.family, url)

    def note_deep_extraction(self, url: str, verdict: DocumentVerdict) -> None:
        """Confirm the extraction happened. The slot was claimed at judge time."""
        self._claim(url, verdict)

    def summary(self) -> dict[str, Any]:
        return {"by_priority": dict(self.counts),
                "families": len(self._family_deep),
                "mirrors": len(self.mirrors)}
