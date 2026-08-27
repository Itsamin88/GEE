"""What a number is a number OF, and what a date is the date OF.

The reported run produced 5 569 conflicts. Half of that was arithmetic — one row
per PAIR of disagreeing claims, so fourteen values across two hundred claims
became nineteen thousand pairs — and that half was already fixed by emitting one
row per distinct VALUE.

The other half is not arithmetic. It is that the values being compared were
never the same kind of thing.

    "around 200 visitors a year"          200
    "12 permanent residents"               12    ─┐  three "competing"
    "60 people came to the summer gathering" 60   ─┘  values for population
    "we employ 4 people"                    4

    "the property is 134 hectares"        134
    "we cultivate 4 hectares"               4    ─┐  four "competing"
    "22 hectares under restoration"        22    ─┘  values for area
    "the leased parcel is 8 hectares"       8

None of those eight pairs is a disagreement. They are eight facts about
different things, and calling them contradictions does three kinds of damage:
it buries the real disagreements, it puts a visitor count where a resident count
belongs, and it can move a community two size classes by coding the whole
property as the managed area (brief §22, §23, §24).

So a claim carries a **semantic role** as well as a value, and:

* claims with different roles are never compared;
* only the role a field is actually about may be written to that field;
* a claim whose role could not be determined goes to a human, not to a cell.

## The three role families

**Population** — who is being counted. Only `resident` belongs in
`e3_population_value`. `visitor`, `guest`, `volunteer`, `event_attendance`,
`employee` and `member` are recorded as their own facts and never substituted.

**Area** — what land is being measured. `managed` and `total_holding` are
separate workbook fields already, and the plan's measurement zones depend on the
difference. `cultivated`, `restoration`, `forest`, `leased` and `project` are
recorded distinctly rather than folded into either.

**Date** — what happened. `founding`, `land_acquisition`, `first_residence` and
`intervention_onset` are four different questions the onset register asks
separately; `publication`, `event` and `archive_snapshot` are properties of the
SOURCE and must never be read as properties of the community. Treating a
publication date as an intervention date is named in §108 as a thing the final
audit must confirm has not happened.

## Deliberately cautious

Where the marker words are absent or contradictory the role is `unclassified`,
and an unclassified claim is not written to a field — it goes to the review
queue. Guessing would produce exactly the silent errors the register's
anti-fabrication rules exist to prevent, and a coder can settle in a minute what
no amount of pattern matching will.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# The vocabularies
# ---------------------------------------------------------------------------
UNCLASSIFIED = "unclassified"

#: Population roles, and the words that mark each. Ordered: the first family
#: whose marker appears wins, so "volunteers and visitors" reads as volunteers
#: rather than as either at random.
POPULATION_ROLES: dict[str, tuple[str, ...]] = {
    "event_attendance": (
        "attended", "attendees", "attendance", "gathering", "festival", "conference",
        "summer camp", "camp", "took part", "participants", "participated",
        "teilnehmer", "besucherzahl", "participants", "participantes",
        "participanti", "deelnemers",
    ),
    "volunteer": (
        "volunteer", "volunteers", "wwoof", "wwoofer", "woofer", "helper", "helpers",
        "work exchange", "workaway", "intern", "interns", "apprentice", "apprentices",
        "bénévole", "bénévoles", "volontaire", "freiwillige", "helfer",
        "voluntario", "voluntarios", "voluntário", "vrijwilliger", "vrijwilligers",
    ),
    "guest": (
        "guest", "guests", "overnight", "bed", "beds", "accommodation", "hostel",
        "campsite", "retreat participants", "hôte", "hôtes", "gäste", "gast",
        "huésped", "huéspedes", "hóspedes", "gasten", "ospiti",
    ),
    "visitor": (
        "visitor", "visitors", "visiting", "tourists", "day visitors", "footfall",
        "per year", "annually", "each year", "a year",
        "visiteur", "visiteurs", "besucher", "visitante", "visitantes",
        "bezoekers", "visitatori",
    ),
    "employee": (
        "employee", "employees", "employ", "employs", "staff", "salaried", "paid staff",
        "workforce", "employé", "employés", "salarié", "mitarbeiter", "angestellte",
        "empleado", "empleados", "funcionários", "medewerkers", "dipendenti",
    ),
    "member": (
        "member", "members", "association members", "cooperative members",
        "shareholders", "mitglieder", "membres", "socios", "sócios", "leden", "soci",
    ),
    "resident": (
        "resident", "residents", "live here", "living here", "lives here",
        "permanent", "inhabitant", "inhabitants", "we are", "population of",
        "adults and children", "households", "full-time",
        "habitant", "habitants", "résident", "résidents", "nous sommes",
        "bewohner", "einwohner", "wir sind", "bewoners", "inwoners",
        "residente", "residentes", "moradores", "abitanti",
    ),
}

#: Only this role may be written to the workbook's population field.
POPULATION_FIELD_ROLE = "resident"

#: Area roles. `managed` and `total_holding` already have their own workbook
#: columns; the rest are recorded as their own facts rather than folded in.
AREA_ROLES: dict[str, tuple[str, ...]] = {
    "restoration": (
        "restor", "rehabilitat", "reforest", "afforest", "regenerat", "rewild",
        "renaturier", "wiederaufforst", "restaur", "herstel", "rimboschimento",
    ),
    "forest": (
        "forest", "woodland", "food forest", "agroforest", "trees planted on",
        "wald", "forêt", "bosque", "floresta", "bos", "bosco",
    ),
    "cultivated": (
        "cultivat", "under cultivation", "market garden", "vegetable", "arable",
        "cropland", "orchard", "vineyard", "in production", "productive land",
        "growing area", "planted area", "sown", "huerta", "potager", "gemüse",
        "moestuin", "orto",
    ),
    "leased": (
        "lease", "leased", "rented", "tenancy", "on loan from", "pacht", "arrend",
        "louée", "en fermage", "affitto",
    ),
    "project": (
        "project area", "project site", "the project covers", "intervention area",
        "study area", "demonstration", "pilot area", "projektfläche",
    ),
    "managed": (
        "manage", "managed", "we work", "worked land", "actively managed",
        "we farm", "farmed", "we tend", "under management", "stewarded",
        "bewirtschaftet", "gérée", "gestita", "beheerd",
    ),
    "total_holding": (
        # Single words as well as phrases: "The 134-hectare property includes…"
        # never contains the phrase "the property", and a community's whole
        # holding being read as its managed land is the error that moves it two
        # size classes.
        "total", "in total", "altogether", "property", "estate", "domain",
        "the whole", "the land is", "we own", "owns", "purchased", "bought",
        "landholding", "holding", "title to", "hectares of land", "site of",
        "grundstück", "insgesamt", "anwesen",
        "propriété", "domaine", "au total", "propiedad", "finca",
        "propriedade", "het terrein", "landgoed", "la proprietà", "tenuta",
    ),
}

#: Date roles. The first four are questions about the COMMUNITY; the last three
#: are properties of the SOURCE and must never be read as the first four.
DATE_ROLES: dict[str, tuple[str, ...]] = {
    "publication": (
        "published", "publication", "posted on", "issue", "issued", "printed",
        "this article", "veröffentlicht", "publié", "publicado", "gepubliceerd",
    ),
    "archive_snapshot": (
        "archived", "snapshot", "wayback", "captured on", "as of",
    ),
    "event": (
        "workshop", "festival", "conference", "gathering", "open day", "course",
        "the event", "took place on", "will take place", "veranstaltung",
    ),
    "land_acquisition": (
        "bought", "purchase", "purchased", "acquired", "acquisition", "we bought",
        "the land was bought", "erworben", "gekauft", "acheté", "comprad",
        "adquirid", "gekocht",
    ),
    "first_residence": (
        "moved in", "first residents", "first lived", "settled here", "moved here",
        "began living", "eingezogen", "emménagé", "se instalaron", "ingetrokken",
    ),
    "intervention_onset": (
        "first planted", "began planting", "started planting", "first swale",
        "began restoring", "started restoring", "work began", "began work",
        "we started", "started the", "first harvest", "began terracing",
        "planting began", "restoration began", "erste pflanzung", "begonnen mit",
    ),
    "founding": (
        "founded", "founding", "established", "was formed", "we began in",
        "since", "started in", "creation of", "inception",
        "gegründet", "fondé", "fondée", "fundad", "opgericht", "fondat",
    ),
}

#: Which role each workbook field is actually about. A claim whose role is not
#: the field's role is never written to it (brief §22, §23, §24).
FIELD_ROLES: dict[str, tuple[str, str]] = {
    "e3_population_value": ("population", "resident"),
    "population_value": ("population", "resident"),
    "population_lower": ("population", "resident"),
    "population_upper": ("population", "resident"),
    "managed_area_ha": ("area", "managed"),
    "managed_area_lower_ha": ("area", "managed"),
    "managed_area_upper_ha": ("area", "managed"),
    "total_holding_ha": ("area", "total_holding"),
    "date_formal_founding": ("date", "founding"),
    "date_land_acquisition": ("date", "land_acquisition"),
    "date_first_residence": ("date", "first_residence"),
    "date_intervention_onset": ("date", "intervention_onset"),
}

#: Roles that describe the SOURCE, not the community. A claim carrying one of
#: these must never reach a community field, whatever the extractor thought.
SOURCE_ROLES = frozenset({"publication", "archive_snapshot"})

_WORD_BOUNDARY_CACHE: dict[str, re.Pattern] = {}


@dataclass
class RoleVerdict:
    """What a value is about, why, and how sure that is."""

    family: str
    role: str = UNCLASSIFIED
    reason: str = ""
    #: Markers found for OTHER roles. A sentence carrying two families' markers
    #: is ambiguous, and saying so is more useful than picking.
    competing: tuple[str, ...] = ()
    confidence: float = 0.0

    @property
    def resolved(self) -> bool:
        return self.role != UNCLASSIFIED

    @property
    def describes_the_source(self) -> bool:
        return self.role in SOURCE_ROLES

    def as_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "semantic_role": self.role,
            "role_reason": self.reason,
            "competing_roles": list(self.competing),
            "role_confidence": round(self.confidence, 2),
        }


def _pattern(marker: str) -> re.Pattern:
    """A word-boundary matcher, cached: this runs on every sentence."""
    compiled = _WORD_BOUNDARY_CACHE.get(marker)
    if compiled is None:
        # Markers are literal phrases, not expressions: a stray "(" in a
        # vocabulary must not become a syntax error in the middle of a crawl.
        compiled = re.compile(r"(?<!\w)" + re.escape(marker), re.IGNORECASE)
        _WORD_BOUNDARY_CACHE[marker] = compiled
    return compiled


def _hits(text: str, vocabulary: Mapping[str, Sequence[str]]) -> dict[str, tuple[str, int]]:
    """Which roles the text carries a marker for, and where the nearest is."""
    found: dict[str, tuple[str, int]] = {}
    for role, markers in vocabulary.items():
        for marker in markers:
            match = _pattern(marker).search(text)
            if match is not None:
                previous = found.get(role)
                if previous is None or match.start() < previous[1]:
                    found[role] = (marker, match.start())
    return found


def classify(family: str, sentence: str, *, position: int | None = None,
             vocabulary: Mapping[str, Sequence[str]] | None = None,
             extra: Mapping[str, Sequence[str]] | None = None) -> RoleVerdict:
    """What is this number, or this date, about?

    `position` is where in the sentence the value sits. When two roles both have
    markers the NEARER one wins, because "the 134-hectare property includes 4
    hectares of market garden" has both and the reader has no difficulty: each
    number sits next to the words that describe it.
    """
    vocabularies = {
        "population": POPULATION_ROLES,
        "area": AREA_ROLES,
        "date": DATE_ROLES,
    }
    words = dict(vocabulary or vocabularies.get(family) or {})
    for role, markers in (extra or {}).items():
        words[role] = tuple(words.get(role, ())) + tuple(markers)
    if not words:
        return RoleVerdict(family=family, reason=f"no vocabulary for {family!r}")

    text = sentence or ""
    found = _hits(text, words)
    if not found:
        return RoleVerdict(
            family=family,
            reason="the sentence carries no word distinguishing what this is about")

    if len(found) == 1:
        role, (marker, _at) = next(iter(found.items()))
        return RoleVerdict(family=family, role=role,
                           reason=f"the sentence says {marker!r}", confidence=0.8)

    # Several roles have markers. Which one describes THIS figure?
    #
    # Distance alone is not enough. "The 134-hectare property includes 4
    # hectares of market garden" carries both, and a reader has no difficulty
    # with either number — because a quantity is qualified by what FOLLOWS it.
    # That holds across the languages in scope: "4 hectares of market garden",
    # "4 hectares de maraîchage", "4 Hektar Gemüsegarten". So a marker after the
    # figure outranks one before it, and only among equals does distance decide.
    anchor = position if position is not None else len(text) // 2
    following = {role: hit for role, hit in found.items() if hit[1] >= anchor}
    preferred = following or found

    ranked = sorted(preferred.items(), key=lambda item: abs(item[1][1] - anchor))
    best_role, (best_marker, best_at) = ranked[0]
    if len(ranked) == 1:
        note = ""
        if len(found) > 1:
            others = ", ".join(sorted(role for role in found if role != best_role))
            note = f" (the sentence also carries {others} before the figure)"
        return RoleVerdict(
            family=family, role=best_role,
            reason=f"the figure is qualified by {best_marker!r}{note}",
            competing=tuple(role for role in found if role != best_role),
            confidence=0.7)

    runner_role, (runner_marker, runner_at) = ranked[1]
    distance = abs(best_at - anchor)
    rival = abs(runner_at - anchor)

    # "Nearest" only means something when it is clearly nearer. Two markers the
    # same distance from the figure is genuinely ambiguous, and a coder settles
    # it in a minute where no amount of pattern matching will.
    if rival - distance < 8:
        return RoleVerdict(
            family=family, role=UNCLASSIFIED,
            reason=(f"the sentence carries {best_marker!r} and {runner_marker!r} "
                    "at similar distance from the figure; a human should read it"),
            competing=tuple(role for role, _ in ranked[:3]),
            confidence=0.0)

    return RoleVerdict(
        family=family, role=best_role,
        reason=(f"the sentence says {best_marker!r} nearest the figure "
                f"(also carries {runner_marker!r})"),
        competing=tuple(role for role, _ in ranked[1:3]),
        confidence=0.6)


def classify_population(sentence: str, *, position: int | None = None,
                        extra: Mapping[str, Sequence[str]] | None = None) -> RoleVerdict:
    """Who is being counted? Only `resident` belongs in the population field."""
    return classify("population", sentence, position=position, extra=extra)


def classify_area(sentence: str, *, position: int | None = None,
                  extra: Mapping[str, Sequence[str]] | None = None) -> RoleVerdict:
    """What land is being measured? Confusing these moves a community two size
    classes (brief §23)."""
    return classify("area", sentence, position=position, extra=extra)


def classify_date(sentence: str, *, position: int | None = None,
                  extra: Mapping[str, Sequence[str]] | None = None) -> RoleVerdict:
    """What happened? A publication date is not an intervention date (brief §24)."""
    return classify("date", sentence, position=position, extra=extra)


def role_for_field(field_name: str) -> tuple[str, str] | None:
    """The (family, role) a workbook field is about, or None if it has no role."""
    return FIELD_ROLES.get(field_name)


def may_write(field_name: str, role: str | None) -> tuple[bool, str]:
    """May a claim with this role be written to this field?

    The check the whole module exists for. A visitor count in the population
    field, or a property area in the managed-area field, is not a disagreement
    to be resolved later — it is a wrong value, and this is where it is stopped
    (brief §22, §23, §108).
    """
    expected = FIELD_ROLES.get(field_name)
    if expected is None:
        return True, ""                       # the field is not role-bearing
    _family, wanted = expected
    if not role or role == UNCLASSIFIED:
        return False, (
            f"{field_name} needs a {wanted!r} figure and the source does not say "
            "which kind this is; sent for human reading rather than guessed")
    if role in SOURCE_ROLES:
        return False, (
            f"{role!r} is a property of the source, not of the community; it must "
            f"never be written to {field_name}")
    if role != wanted:
        return False, (
            f"{field_name} is the {wanted!r} figure; this is a {role!r} figure and "
            "is recorded as its own fact instead")
    return True, ""


def conflict_key(field_name: str, role: str | None) -> str:
    """The bucket a claim competes in.

    Claims in different buckets are never compared, which is what stops eight
    facts about different things being reported as eight contradictions
    (brief §21, §22).
    """
    return f"{field_name}::{role or UNCLASSIFIED}"


def summarise(field_name: str, verdicts: Iterable[RoleVerdict]) -> dict[str, int]:
    """How many claims of each role a field attracted, for the report."""
    counts: dict[str, int] = {}
    for verdict in verdicts:
        counts[verdict.role] = counts.get(verdict.role, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: -item[1]))


__all__ = [
    "AREA_ROLES", "DATE_ROLES", "FIELD_ROLES", "POPULATION_ROLES",
    "POPULATION_FIELD_ROLE", "RoleVerdict", "SOURCE_ROLES", "UNCLASSIFIED",
    "classify", "classify_area", "classify_date", "classify_population",
    "conflict_key", "may_write", "role_for_field", "summarise",
]
