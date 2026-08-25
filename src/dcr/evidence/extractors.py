"""Deterministic field extraction from one page or document.

Rules do the work that rules do well — dates, numbers, named vocabularies,
provenance — and nothing here ever fills a field from a guess. Where a statement
is ambiguous the extractor records the passage and leaves the field alone, so
the ambiguity reaches the review queue instead of the workbook (brief §66).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from .model import ClaimItem, EvidenceItem, sentences, window
from .onset import DateCandidate, detect_markers, domain_for, rank_for
from .practices import PracticeDetector, PracticeHit, fold
from .quantities import AreaMention, PopulationMention, find_areas, find_populations

EXTRACTOR_VERSION = "1.0.0"


@dataclass
class MinedText:
    """Everything one page or document yielded, before resolution."""

    evidence: list[tuple[EvidenceItem, list[ClaimItem]]] = field(default_factory=list)
    date_candidates: list[DateCandidate] = field(default_factory=list)
    practice_hits: list[PracticeHit] = field(default_factory=list)
    area_mentions: list[AreaMention] = field(default_factory=list)
    population_mentions: list[PopulationMention] = field(default_factory=list)
    languages: set[str] = field(default_factory=set)
    networks: set[str] = field(default_factory=set)
    founders: set[str] = field(default_factory=set)
    legal_entities: set[str] = field(default_factory=set)
    certifiers: set[str] = field(default_factory=set)
    published_coordinates: list[tuple[float, float, str]] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.evidence)


# --- controlled vocabularies, matched on folded text -----------------------
SETTLEMENT_TYPE_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("retreat centre", ("retreat centre", "retreat center", "centre de retraite", "retraite",
                        "seminarhaus", "retiro", "meditation centre")),
    ("campus", ("campus", "school of", "training centre", "ecole", "academy", "institute")),
    ("business", ("company", "sarl", "gmbh", "ltd", "bv ", "enterprise", "consultancy")),
    ("single household", ("our family", "my partner and i", "single household", "one family",
                          "notre famille", "ons gezin")),
    ("urban co-housing", ("co-housing", "cohousing", "urban", "in the city centre",
                          "centraal in de stad", "habitat participatif urbain")),
    ("village-scale permanent residence",
     ("we live here", "permanent residents", "our community lives", "habitants permanents",
      "vaste bewoners", "wij wonen hier", "residents live on site", "intentional community",
      "ecovillage", "ecodorp", "ecovillage", "ecoaldea", "ecoaldeia", "okodorf")),
)

TENURE_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("commons or trust", ("land trust", "community land trust", "held in trust", "stichting bezit",
                          "fondation propri", "foncier solidaire", "terre de liens", "commons")),
    ("freehold collective", ("collectively owned", "owned by the association", "cooperative owns",
                             "propriete collective", "gezamenlijk eigendom", "cooperative fonciere",
                             "sci ", "societe civile immobiliere", "owned by the community")),
    ("freehold individual", ("privately owned", "owned by one", "individual ownership",
                             "propriete privee", "prive eigendom")),
    ("leasehold", ("lease", "leased", "bail", "erfpacht", "pacht", "arrendamiento", "emphyteotic")),
    ("informal", ("squat", "occupied without", "informal tenure", "sans titre")),
)

STATUS_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("dissolved", ("has dissolved", "was dissolved", "closed down", "no longer exists",
                   "a ferme ses portes", "opgeheven", "aufgelost", "disuelta", "ceased operations")),
    ("relocated", ("relocated to", "moved to a new site", "demenage", "verhuisd naar")),
    ("transformed", ("became a", "now operates as", "transformed into", "est devenu",
                     "omgevormd tot")),
    ("dormant", ("on hold", "paused", "currently inactive", "en pause", "tijdelijk gestopt")),
)

MOVEMENT_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("permaculture", ("permaculture", "permacultuur", "permakultur", "permacultura")),
    ("ecovillage network", ("global ecovillage network", "gen europe", "gen-europe", "ecovillage network",
                            "rie", "ecovillage.org")),
    ("Camphill", ("camphill",)),
    ("kibbutz", ("kibbutz", "kibbuts")),
    ("Buddhist or spiritual", ("buddhist", "dharma", "sangha", "ashram", "spiritual community",
                               "meditation community", "communaute spirituelle")),
    ("Transition", ("transition town", "transition network", "ville en transition")),
    ("agroecology", ("agroecology", "agroecologie", "agroecologia", "agrarokologie")),
)

AGRICULTURAL_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("market", ("we sell", "market garden", "csa", "farm shop", "our produce is sold",
                "vente directe", "marche", "verkoop", "boerenmarkt", "amap")),
    ("subsistence", ("self-sufficient", "for our own", "subsistence", "autosuffisance",
                     "zelfvoorzienend", "eigen gebruik", "autoconsumo")),
)

EDUCATION_MARKERS = ("wwoof", "workaway", "volunteer", "internship", "course", "workshop",
                     "training", "benevole", "stage", "formation", "vrijwilliger", "cursus",
                     "seminar", "praktikum", "voluntario", "curso")

PROTECTED_AREA_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("inside", ("within the national park", "inside the nature reserve", "in the natura 2000 site",
                "dans le parc national", "in het natuurgebied", "im naturschutzgebiet")),
    ("adjacent", ("adjacent to the", "bordering the national park", "next to the nature reserve",
                  "en bordure du parc", "grenst aan het natuurgebied", "borders the reserve")),
)

NOTABLE_CONTEXT_MARKERS = (
    ("fire", ("wildfire", "forest fire", "incendie", "bosbrand", "waldbrand", "incendio")),
    ("drought", ("drought", "secheresse", "droogte", "durre", "sequia", "seca")),
    ("flood", ("flood", "inondation", "overstroming", "hochwasser", "inundacion")),
    ("land dispute", ("land dispute", "legal dispute", "court case", "litige", "rechtszaak",
                      "eviction", "expulsion")),
    ("relocation", ("we relocated", "moved the project", "demenagement", "verhuizing")),
    ("war", ("war", "conflict zone", "guerre", "oorlog", "krieg")),
)

NETWORK_NAMES = (
    "Global Ecovillage Network", "GEN Europe", "GEN-Europe", "Foundation for Intentional Community",
    "NuMundo", "WWOOF", "Workaway", "Ecolise", "Colibris", "Terre de Liens", "Diggers and Dreamers",
    "Eurotopia", "Permaculture Association", "Transition Network", "RIE", "Réseau Français des Écolieux",
    "Gemeinschaften", "Ecobasa", "Habitat Participatif", "Kraaijeveld", "Ecodorpen Nederland",
    "Global Ecovillage Network Europe", "Permacultura", "La Via Campesina",
)

_LEGAL_FORMS = (
    r"association|asbl|vzw|stichting|vereniging|foundation|fondation|fundacion|"
    r"cooperative|cooperatief|genossenschaft|gmbh|e\.?v\.?|sci|scop|scic|sarl|sa|bv|nv|"
    r"ltd|llc|trust|societa|associazione|cooperativa|lda|crl|coop"
)
# Legal names appear both ways round: "Pourgues Association" and
# "L'association Pourgues". Grant and registry records use the legal name, so
# missing one costs a whole Stage 6 route.
# The capitalised-word parts stay case-SENSITIVE (scoped (?-i:...)) so a legal
# form followed by ordinary lowercase prose is not swallowed as a name.
LEGAL_FORM_PATTERNS = (
    re.compile(rf"\b((?-i:(?:[A-ZÀ-Þ][\w'’\-\.]+\s+){{1,5}})(?:{_LEGAL_FORMS}))\b",
               re.UNICODE | re.IGNORECASE),
    re.compile(rf"\b((?:{_LEGAL_FORMS})\s+(?-i:(?:[A-ZÀ-Þ][\w'’\-\.]+\s*){{1,4}}))",
               re.UNICODE | re.IGNORECASE),
)

_PERSON = r"([A-ZÀ-Þ][\w'’\-]+(?:\s+(?:de|van|von|del|da|di)\s+)?(?:\s*[A-ZÀ-Þ][\w'’\-]+){0,2})"
# "founded in 2015 by X" and "fondé par X" both matter: the founder's name is a
# separate academic and registry search string (register 5.2).
FOUNDER_PATTERN = re.compile(
    rf"\b(?:founded|co-?founded|established|created|started)(?:\s+in\s+\d{{4}})?\s+by\s+{_PERSON}"
    rf"|\bfond[ée]\w*(?:\s+en\s+\d{{4}})?\s+par\s+{_PERSON}"
    rf"|\bcr[ée]{{2}}\w*(?:\s+en\s+\d{{4}})?\s+par\s+{_PERSON}"
    rf"|\bopgericht(?:\s+in\s+\d{{4}})?\s+door\s+{_PERSON}"
    rf"|\bgegr[üu]ndet(?:\s+\d{{4}})?\s+von\s+{_PERSON}"
    rf"|\bfundad[oa](?:\s+en\s+\d{{4}})?\s+por\s+{_PERSON}",
    re.UNICODE,
)

COORDINATE_PATTERN = re.compile(
    r"(-?\d{1,2}[.,]\d{3,8})\s*[,;/]\s*(-?\d{1,3}[.,]\d{3,8})"
)

# A community's own published context figures. Recorded as context only, never
# substituted for the satellite pipeline value (register A.0 exception).
CONTEXT_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("context_elevation_m",
     re.compile(r"(\d{2,4})\s*(?:m|metres|meters|meter|mètres)\s*(?:above sea level|asl|a\.s\.l\.|"
                r"d.altitude|altitude|boven zeeniveau|uber dem meeresspiegel|sobre el nivel del mar)",
                re.IGNORECASE), "m"),
    ("context_annual_rainfall_mm",
     re.compile(r"(\d{3,4})\s*mm\s*(?:of\s*)?(?:rain|rainfall|precipitation|de pluie|"
                r"neerslag|niederschlag|lluvia|chuva|precipitazioni)", re.IGNORECASE), "mm"),
)


class TextMiner:
    """Extracts every field this text can support, with the passage attached."""

    def __init__(self, lexicon: Mapping[str, Any], schema: Mapping[str, Any]):
        self.lexicon = lexicon
        self.schema = schema
        self.practice_detector = PracticeDetector(lexicon)
        self.quantity_markers = lexicon.get("quantities", {})
        self.area_units = self.quantity_markers.get("area_units", {})
        self.onset_lexicon = lexicon.get("onset", {})
        self.domains = self.onset_lexicon.get("domains", {})

    # -- main entry --------------------------------------------------------
    def mine(
        self,
        text: str,
        *,
        source_id: str | None,
        source_class: str,
        page_id: str | None = None,
        document_id: str | None = None,
        locator: str | None = None,
        publication_date: str | None = None,
        retrieval_date: str | None = None,
        language: str | None = None,
        independence_group: str | None = None,
        is_archive_snapshot: bool = False,
        archive_timestamp: str | None = None,
        title: str = "",
    ) -> MinedText:
        mined = MinedText()
        if not text or len(text) < 40:
            return mined

        spans = sentences(text)
        common = {
            "source_id": source_id,
            "source_class": source_class,
            "page_id": page_id,
            "document_id": document_id,
            "locator": locator,
            "publication_date": publication_date,
            "retrieval_date": retrieval_date,
            "language": language,
            "independence_group": independence_group,
        }

        self._mine_practices(mined, spans, common)
        self._mine_dates(mined, spans, text, common,
                         is_archive_snapshot=is_archive_snapshot,
                         archive_timestamp=archive_timestamp)
        self._mine_areas(mined, spans, text, common)
        self._mine_population(mined, spans, text, common)
        self._mine_vocabularies(mined, spans, text, common, title=title)
        self._mine_context(mined, spans, text, common)
        self._mine_entities(mined, text)
        if language:
            mined.languages.add(language)
        return mined

    # -- practices ---------------------------------------------------------
    def _mine_practices(self, mined: MinedText, spans: list[tuple[int, int, str]],
                        common: dict[str, Any]) -> None:
        hits = self.practice_detector.scan(
            spans,
            source_class=common["source_class"],
            source_id=common["source_id"],
            document_id=common["document_id"],
            page_id=common["page_id"],
            locator=common["locator"],
            publication_date=common["publication_date"],
            independence_group=common["independence_group"],
        )
        mined.practice_hits.extend(hits)

    # -- dates -------------------------------------------------------------
    def _mine_dates(self, mined: MinedText, spans: list[tuple[int, int, str]], text: str,
                    common: dict[str, Any], *, is_archive_snapshot: bool,
                    archive_timestamp: str | None) -> None:
        markers = {
            "date_formal_founding": self.onset_lexicon.get("founding_markers", {}),
            "date_land_acquisition": self.onset_lexicon.get("land_acquisition_markers", {}),
            "date_first_residence": self.onset_lexicon.get("first_residence_markers", {}),
        }
        seen_dates: set[tuple[str, int, int]] = set()
        for field_name, marker_map in markers.items():
            for language, patterns in marker_map.items():
                for pattern in patterns:
                    for start, end, sentence in spans:
                        folded = fold(sentence)
                        if not re.search(fold(pattern), folded, re.IGNORECASE):
                            continue
                        year = _year_in(sentence)
                        if not year:
                            continue
                        if (field_name, year, start) in seen_dates:
                            continue
                        seen_dates.add((field_name, year, start))
                        under_way, retrospective = detect_markers(sentence)
                        rank, reason = rank_for(
                            source_class=common["source_class"],
                            is_archive_snapshot=is_archive_snapshot,
                            already_under_way=under_way,
                            has_explicit_year=True,
                            retrospective=retrospective,
                            is_directory_founding=(
                                common["source_class"] == "S3" and field_name == "date_formal_founding"
                            ),
                        )
                        mined.date_candidates.append(
                            DateCandidate(
                                field_name=field_name, year=year, sentence=sentence[:1200],
                                source_id=common["source_id"], source_class=common["source_class"],
                                evidence_rank=rank, rank_reason=reason, marker=pattern,
                                document_id=common["document_id"], page_id=common["page_id"],
                                independence_group=common["independence_group"],
                                is_archive_snapshot=is_archive_snapshot,
                                archive_timestamp=archive_timestamp,
                                already_under_way=under_way, retrospective=retrospective,
                                locator=common["locator"], char_start=start, char_end=end,
                            )
                        )
                        self._record(
                            mined, text, start, end, sentence, common,
                            evidence_type="passage",
                            claims=[ClaimItem(
                                field_name=field_name, value=str(year), value_type="year",
                                original_value=sentence[:300], exact_wording=sentence[:600],
                                evidence_rank=rank, reference_year=year, confidence=0.6,
                                rationale=reason, extractor=f"rule:dates/{EXTRACTOR_VERSION}",
                            )],
                        )
                        break

        # The onset itself: a deliberate action on vegetation, soil, water or
        # land cover, with a year in the SAME sentence.
        for hit in mined.practice_hits:
            if hit.denial:
                continue
            year = hit.reference_year or _year_in(hit.sentence)
            if not year:
                continue
            under_way, retrospective = detect_markers(hit.sentence)
            if not self._is_action_sentence(hit.sentence):
                continue
            rank, reason = rank_for(
                source_class=hit.source_class,
                is_archive_snapshot=is_archive_snapshot,
                already_under_way=under_way,
                has_explicit_year=True,
                retrospective=retrospective,
                is_directory_founding=False,
            )
            mined.date_candidates.append(
                DateCandidate(
                    field_name="date_intervention_onset", year=year, sentence=hit.sentence[:1200],
                    source_id=hit.source_id, source_class=hit.source_class,
                    evidence_rank=rank, rank_reason=reason, marker=hit.matched_term,
                    domain=domain_for(hit.practice, self.domains),
                    document_id=hit.document_id, page_id=hit.page_id,
                    independence_group=hit.independence_group,
                    is_archive_snapshot=is_archive_snapshot, archive_timestamp=archive_timestamp,
                    already_under_way=under_way, retrospective=retrospective,
                    locator=hit.locator, char_start=hit.char_start, char_end=hit.char_end,
                    confidence=0.6,
                )
            )

    def _is_action_sentence(self, sentence: str) -> bool:
        """Did something actually HAPPEN, or is this an aim?"""
        folded = fold(sentence).lower()
        for verbs in (self.onset_lexicon.get("action_verbs") or {}).values():
            for verb in verbs:
                if re.search(fold(verb), folded, re.IGNORECASE):
                    return True
        return False

    # -- areas -------------------------------------------------------------
    def _mine_areas(self, mined: MinedText, spans: list[tuple[int, int, str]], text: str,
                    common: dict[str, Any]) -> None:
        mentions = find_areas(text, self.area_units, spans, markers=self.quantity_markers)
        mined.area_mentions.extend(mentions)
        for mention in mentions:
            claims: list[ClaimItem] = []
            basis = "measured" if common["source_class"] in ("S1", "S2") else "stated"
            note = (
                f"{mention.kind_reason}. Stated as {mention.original!r}"
                + (f", referring to {mention.reference_year}" if mention.reference_year else "")
                + ("; the source qualifies it as approximate" if mention.approximate else "")
            )
            if mention.kind == "managed":
                claims.append(ClaimItem(
                    field_name="managed_area_ha", value=f"{mention.value_ha:g}",
                    value_type="float", original_value=mention.original,
                    normalized_value=f"{mention.value_ha:g}",
                    normalization_note=f"converted from {mention.unit} to hectares"
                    if mention.unit not in ("ha", "hectare", "hectares") else None,
                    exact_wording=mention.sentence[:600], reference_year=mention.reference_year,
                    confidence=0.65, rationale=note,
                    extractor=f"rule:area/{EXTRACTOR_VERSION}",
                ))
                claims.append(ClaimItem(
                    field_name="managed_area_basis", value=basis, value_type="enum",
                    original_value=mention.original, exact_wording=mention.sentence[:600],
                    confidence=0.6,
                    rationale=f"basis {basis} because the figure comes from a "
                              f"{common['source_class']} source",
                    extractor=f"rule:area/{EXTRACTOR_VERSION}",
                ))
                claims.append(ClaimItem(
                    field_name="managed_area_source_class", value=common["source_class"],
                    value_type="enum", exact_wording=mention.sentence[:600], confidence=0.9,
                    rationale="the class of the source that supplied the figure",
                    extractor=f"rule:area/{EXTRACTOR_VERSION}",
                ))
                claims.append(ClaimItem(
                    field_name="documentary_area_note", value=note[:900], value_type="text",
                    exact_wording=mention.sentence[:600], confidence=0.6,
                    rationale="qualification of the documentary figure",
                    extractor=f"rule:area/{EXTRACTOR_VERSION}",
                ))
                if mention.lower_ha is not None:
                    claims.append(ClaimItem(
                        field_name="managed_area_lower_ha", value=f"{mention.lower_ha:g}",
                        value_type="float", original_value=mention.original,
                        exact_wording=mention.sentence[:600], confidence=0.6,
                        rationale="lower end of a range the source states",
                        extractor=f"rule:area/{EXTRACTOR_VERSION}",
                    ))
                if mention.upper_ha is not None:
                    claims.append(ClaimItem(
                        field_name="managed_area_upper_ha", value=f"{mention.upper_ha:g}",
                        value_type="float", original_value=mention.original,
                        exact_wording=mention.sentence[:600], confidence=0.6,
                        rationale="upper end of a range the source states",
                        extractor=f"rule:area/{EXTRACTOR_VERSION}",
                    ))
            elif mention.kind == "total_holding":
                claims.append(ClaimItem(
                    field_name="total_holding_ha", value=f"{mention.value_ha:g}",
                    value_type="float", original_value=mention.original,
                    normalized_value=f"{mention.value_ha:g}",
                    exact_wording=mention.sentence[:600], reference_year=mention.reference_year,
                    confidence=0.6, rationale=note,
                    extractor=f"rule:area/{EXTRACTOR_VERSION}",
                ))
            if claims:
                self._record(mined, text, mention.char_start, mention.char_end,
                             mention.sentence, common, evidence_type="passage", claims=claims)

    # -- population --------------------------------------------------------
    def _mine_population(self, mined: MinedText, spans: list[tuple[int, int, str]], text: str,
                         common: dict[str, Any]) -> None:
        mentions = find_populations(text, spans, markers=self.quantity_markers)
        mined.population_mentions.extend(mentions)
        for mention in mentions:
            if mention.kind != "permanent":
                continue
            claims = [
                ClaimItem(
                    field_name="population_value", value=str(mention.value), value_type="integer",
                    original_value=mention.original, exact_wording=mention.sentence[:600],
                    reference_year=mention.reference_year, confidence=0.6,
                    rationale=mention.kind_reason,
                    extractor=f"rule:population/{EXTRACTOR_VERSION}",
                ),
                # The workbook holds the same quantity twice (decision DCR-D003).
                ClaimItem(
                    field_name="e3_population_value", value=str(mention.value),
                    value_type="integer", original_value=mention.original,
                    exact_wording=mention.sentence[:600], reference_year=mention.reference_year,
                    confidence=0.6, rationale=mention.kind_reason,
                    extractor=f"rule:population/{EXTRACTOR_VERSION}",
                ),
            ]
            if mention.reference_year:
                claims.append(ClaimItem(
                    field_name="population_source_date", value=str(mention.reference_year),
                    value_type="year", exact_wording=mention.sentence[:600], confidence=0.7,
                    rationale="the year the figure refers to, as stated in the same sentence",
                    extractor=f"rule:population/{EXTRACTOR_VERSION}",
                ))
            if mention.lower is not None:
                claims.append(ClaimItem(
                    field_name="population_lower", value=str(mention.lower), value_type="integer",
                    exact_wording=mention.sentence[:600], confidence=0.6,
                    rationale="lower end of a stated range",
                    extractor=f"rule:population/{EXTRACTOR_VERSION}",
                ))
            if mention.upper is not None:
                claims.append(ClaimItem(
                    field_name="population_upper", value=str(mention.upper), value_type="integer",
                    exact_wording=mention.sentence[:600], confidence=0.6,
                    rationale="upper end of a stated range",
                    extractor=f"rule:population/{EXTRACTOR_VERSION}",
                ))
            self._record(mined, text, mention.char_start, mention.char_end, mention.sentence,
                         common, evidence_type="passage", claims=claims)

    # -- controlled vocabularies -------------------------------------------
    def _mine_vocabularies(self, mined: MinedText, spans: list[tuple[int, int, str]], text: str,
                           common: dict[str, Any], *, title: str = "") -> None:
        folded_all = fold(text).lower()

        def scan(markers: Sequence[tuple[str, Sequence[str]]], field_name: str,
                 confidence: float, note: str) -> None:
            for value, needles in markers:
                for needle in needles:
                    folded_needle = fold(needle).lower()
                    position = folded_all.find(folded_needle)
                    if position < 0:
                        continue
                    start, end, sentence = _sentence_at(position, spans, text)
                    self._record(
                        mined, text, start, end, sentence, common,
                        evidence_type="passage",
                        claims=[ClaimItem(
                            field_name=field_name, value=value, value_type="enum",
                            original_value=needle, exact_wording=sentence[:600],
                            confidence=confidence,
                            rationale=f"{note}: the source says {needle!r}",
                            extractor=f"rule:vocabulary/{EXTRACTOR_VERSION}",
                        )],
                    )
                    return

        scan(SETTLEMENT_TYPE_MARKERS, "e2_settlement_type", 0.55, "settlement type")
        scan(TENURE_MARKERS, "tenure_type", 0.6, "tenure")
        scan(STATUS_MARKERS, "status_current", 0.6, "status")
        scan(MOVEMENT_MARKERS, "movement_tradition", 0.6, "movement tradition")
        scan(AGRICULTURAL_MARKERS, "agricultural_orientation", 0.5, "agricultural orientation")
        scan(PROTECTED_AREA_MARKERS, "protected_area_status", 0.55, "protected area")

        for label, needles in NOTABLE_CONTEXT_MARKERS:
            for needle in needles:
                position = folded_all.find(fold(needle).lower())
                if position < 0:
                    continue
                start, end, sentence = _sentence_at(position, spans, text)
                self._record(
                    mined, text, start, end, sentence, common, evidence_type="passage",
                    claims=[ClaimItem(
                        field_name="notable_context", value=f"{label}: {sentence[:220]}",
                        value_type="text", exact_wording=sentence[:600], confidence=0.5,
                        rationale=f"the source mentions {needle!r}",
                        extractor=f"rule:vocabulary/{EXTRACTOR_VERSION}",
                    )],
                )
                break

        for needle in EDUCATION_MARKERS:
            position = folded_all.find(fold(needle).lower())
            if position < 0:
                continue
            start, end, sentence = _sentence_at(position, spans, text)
            self._record(
                mined, text, start, end, sentence, common, evidence_type="passage",
                claims=[ClaimItem(
                    field_name="education_volunteer_program", value="yes", value_type="enum",
                    original_value=needle, exact_wording=sentence[:600], confidence=0.6,
                    rationale=f"the source mentions {needle!r}",
                    extractor=f"rule:vocabulary/{EXTRACTOR_VERSION}",
                )],
            )
            break

        for network in NETWORK_NAMES:
            if fold(network).lower() in folded_all:
                mined.networks.add(network)

        # A published self-identification of ecological aims (register B3).
        for start, end, sentence in spans:
            folded = fold(sentence).lower()
            if len(sentence.split()) > 30 or len(sentence) < 20:
                continue
            aim_markers = ("regenerat", "restor", "ecolog", "sustainab", "permaculture",
                           "biodiversity", "agroecolog", "soil health", "reforest",
                           "ecologi", "duurzaam", "natuurherstel", "regener")
            if any(marker in folded for marker in aim_markers):
                self._record(
                    mined, text, start, end, sentence, common, evidence_type="passage",
                    claims=[ClaimItem(
                        field_name="e1_self_identification", value=sentence[:200],
                        value_type="text", original_value=sentence[:200],
                        exact_wording=sentence[:600], confidence=0.5,
                        rationale="a published phrase stating ecological aims, quoted verbatim",
                        extractor=f"rule:vocabulary/{EXTRACTOR_VERSION}",
                    )],
                )
                break

        certifiers = self.practice_detector.certifiers_in(text)
        mined.certifiers.update(certifiers)

    # -- context figures and coordinates -----------------------------------
    def _mine_context(self, mined: MinedText, spans: list[tuple[int, int, str]], text: str,
                      common: dict[str, Any]) -> None:
        for field_name, pattern, unit in CONTEXT_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            start, end, sentence = _sentence_at(match.start(), spans, text)
            self._record(
                mined, text, start, end, sentence, common, evidence_type="passage",
                claims=[ClaimItem(
                    field_name=field_name, value=f"{match.group(1)} {unit}", value_type="text",
                    original_value=match.group(), exact_wording=sentence[:600], confidence=0.6,
                    rationale="the community's own published figure, recorded as CONTEXT only. "
                              "It must never replace the satellite pipeline value.",
                    extractor=f"rule:context/{EXTRACTOR_VERSION}",
                )],
            )

        for match in COORDINATE_PATTERN.finditer(text[:200000]):
            try:
                lat = float(match.group(1).replace(",", "."))
                lon = float(match.group(2).replace(",", "."))
            except ValueError:
                continue
            if -90 <= lat <= 90 and -180 <= lon <= 180 and (abs(lat) > 0.01 or abs(lon) > 0.01):
                _, _, sentence = _sentence_at(match.start(), spans, text)
                mined.published_coordinates.append((lat, lon, sentence[:300]))

    def _mine_entities(self, mined: MinedText, text: str) -> None:
        for match in FOUNDER_PATTERN.finditer(text[:200000]):
            name = next((g for g in match.groups() if g), None)
            if name and 3 < len(name) < 60:
                mined.founders.add(name.strip())
        for pattern in LEGAL_FORM_PATTERNS:
            for match in pattern.finditer(text[:200000]):
                entity = re.sub(r"\s+", " ", match.group(1)).strip(" .,'’")
                if 6 < len(entity) < 90 and any(ch.isupper() for ch in entity):
                    mined.legal_entities.add(entity)

    # -- helper ------------------------------------------------------------
    def _record(self, mined: MinedText, text: str, start: int, end: int, sentence: str,
                common: dict[str, Any], *, evidence_type: str,
                claims: list[ClaimItem]) -> None:
        evidence = EvidenceItem(
            evidence_type=evidence_type,
            quote=sentence[:2000],
            source_id=common["source_id"],
            document_id=common["document_id"],
            page_id=common["page_id"],
            locator=common["locator"],
            context=window(text, start, end),
            language=common["language"],
            source_class=common["source_class"],
            publication_date=common["publication_date"],
            retrieval_date=common["retrieval_date"],
            char_start=start,
            char_end=end,
        )
        mined.evidence.append((evidence, claims))


def _year_in(text: str) -> int | None:
    match = re.search(r"\b(19[5-9]\d|20[0-4]\d)\b", text or "")
    return int(match.group(1)) if match else None


def _sentence_at(position: int, spans: list[tuple[int, int, str]],
                 text: str) -> tuple[int, int, str]:
    for start, end, sentence in spans:
        if start <= position <= end:
            return start, end, sentence
    lo = max(0, position - 150)
    hi = min(len(text), position + 150)
    return lo, hi, text[lo:hi].strip()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance between two points, for the coordinate-agreement check."""
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))
