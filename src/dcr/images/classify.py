"""Image relevance classification.

The system must save maps, site plans, restoration diagrams and dated field
photographs, and must NOT save every decorative image (brief §22, §23).

The hard rule (brief §47, register rule 12): a photograph is never a practice
code. Visual appearance alone can evidence the existence of a physical
structure and can date it, but only a caption or surrounding text that STATES a
practice may support a practice claim. Every classification therefore records
both what the image alone may evidence and what documentary text supports.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

LIKELY = "likely_relevant"
POSSIBLE = "possibly_relevant"
DECORATIVE = "decorative"
UNCERTAIN = "uncertain"

# What an image of each type may evidence on its own.
VISUAL_EVIDENCE_BY_TYPE = {
    "site plan": "V4 visual documentation; the existence and layout of a published plan",
    "map": "V4 visual documentation; the existence of a published map",
    "diagram": "V4 visual documentation; the existence of a design drawing",
    "aerial": "V4 visual documentation; the visible state of the ground at the image date",
    "before_after": "V4 visual documentation; a change between two stated dates",
    "photograph": "V4 visual documentation ONLY where the photograph is dated and shows a "
                  "physical structure (a swale, a pond, a planted block)",
    "unknown": "nothing on its own",
}

_TYPE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("site plan", ("site.?plan", "master.?plan", "masterplan", "plan.?de.?masse", "plattegrond",
                   "terreinplan", "inrichtingsplan", "lageplan", "permaculture.?design",
                   "design.?plan", "ontwerp", "plano.?del.?sitio", "farm.?plan", "zone.?plan")),
    ("map", ("\\bmap\\b", "\\bcarte\\b", "\\bkaart\\b", "\\bkarte\\b", "\\bmapa\\b", "\\bmappa\\b",
             "land.?use", "landgebruik", "zoning", "bestemmingsplan", "cadastr", "kadaster",
             "topograph", "parcel")),
    ("aerial", ("aerial", "luchtfoto", "vue.?a[eé]rienne", "luftbild", "orthophoto", "drone",
                "satellite", "birds.?eye")),
    ("before_after", ("before.?(and.?)?after", "avant.?apr[eè]s", "voor.?en.?na", "vorher.?nachher",
                      "antes.?y.?despu", "\\b(19|20)\\d{2}\\s*(vs|versus|-|→)\\s*(19|20)\\d{2}")),
    ("diagram", ("diagram", "schema", "sch[ée]ma", "schets", "skizze", "cross.?section",
                 "profil", "doorsnede", "layout", "keyline", "contour")),
)

_YEAR = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")


@dataclass
class ImageClassification:
    relevance_class: str
    score: float
    reason: str
    image_type: str = "unknown"
    research_topic: str = ""
    possible_fields: list[str] = field(default_factory=list)
    visual_evidence_allowed: str = "nothing on its own"
    documentary_text_support: str = "NOT FOUND"
    image_date: str | None = None
    image_date_confidence: str = "none"
    confidence: float = 0.0


# Which workbook fields an image MAY bear on. "May" is the operative word: the
# field is only ever coded from text, never from the picture.
_TOPIC_FIELDS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("site plan", ("site.?plan", "master.?plan", "plan.?de.?masse", "inrichtingsplan",
                   "permaculture.?design", "plattegrond"),
     ("site_plan_published", "v4_visual_documentation", "managed_area_ha")),
    ("land use", ("land.?use", "landgebruik", "zoning", "bestemmingsplan", "parcel", "cadastr"),
     ("site_plan_published", "parcel_structure", "total_holding_ha", "v4_visual_documentation")),
    ("water works", ("swale", "keyline", "pond", "mare", "vijver", "wetland", "zone.?humide",
                     "waterplan", "irrigation", "drainage", "bassin", "citerne", "rainwater"),
     ("pc01_rainwater", "pc02_swales", "pc03_irrigation", "pc13_restoration", "v4_visual_documentation")),
    ("tree planting", ("plantation", "planting", "reforest", "reboisement", "herbebossing",
                       "tree.?plant", "boomaanplant", "verger", "orchard", "boomgaard",
                       "\\barbres?\\b", "\\bbomen\\b", "\\bb[aä]ume\\b", "\\b[aá]rbol",
                       "\\b[aá]rvore", "\\balberi\\b", "plant[ée]s?\\b", "geplant\\b"),
     ("pc07_tree_planting", "date_intervention_onset", "v4_visual_documentation")),
    ("agroforestry", ("food.?forest", "voedselbos", "for[eê]t.?jardin", "agrofor", "waldgarten",
                      "syntropic", "agrofloresta"),
     ("pc08_agroforestry", "pc09_polyculture", "v4_visual_documentation")),
    ("restoration", ("restoration", "restaurati", "herstel", "renaturier", "erosion", "gully",
                     "revegetat", "meadow", "prairie", "grassland"),
     ("pc13_restoration", "date_intervention_onset", "v4_visual_documentation")),
    ("cultivation", ("garden", "jardin", "tuin", "huerta", "horta", "market.?garden",
                     "mara[iî]chage", "moestuin", "bed", "planche", "terrace", "terras"),
     ("pc11_small_parcel", "pc05_mulching", "v4_visual_documentation")),
    ("hedgerow", ("hedge", "haie", "haag", "houtwal", "hecke", "windbreak", "brise.?vent",
                  "shelterbelt", "seto"),
     ("pc10_hedgerows", "v4_visual_documentation")),
)


def classify_image(
    *,
    url: str,
    alt: str = "",
    title: str = "",
    caption: str = "",
    surrounding: str = "",
    page_title: str = "",
    document_title: str = "",
    ocr_text: str = "",
    width: int | None = None,
    height: int | None = None,
    bytes_len: int | None = None,
    lexicon: Mapping[str, Any] | None = None,
    min_width: int = 320,
    min_height: int = 240,
) -> ImageClassification:
    """Decide whether an image is worth keeping, and say why."""
    patterns = dict((lexicon or {}).get("image_relevance", {}))
    strong = _compile(patterns.get("strong", []))
    moderate = _compile(patterns.get("moderate", []))
    decorative = _compile(patterns.get("decorative", []))

    filename = url.rsplit("/", 1)[-1]
    # Weight the fields by how much a match in each is worth: a caption that
    # names a site plan is far stronger evidence than a filename that does.
    signals: list[tuple[str, str, float]] = [
        ("caption", caption, 1.0),
        ("alt text", alt, 0.9),
        ("title attribute", title, 0.8),
        ("filename", filename, 0.7),
        ("surrounding text", surrounding, 0.6),
        ("document title", document_title, 0.6),
        ("page title", page_title, 0.4),
        ("OCR text", ocr_text, 0.5),
    ]
    haystack = " ".join(value for _, value, _ in signals if value)

    if not haystack.strip():
        # Nothing said about it at all. Keep it as uncertain if it is large
        # enough to be substantive; a picture with no context is not evidence,
        # but discarding it silently loses a possible map.
        big_enough = _big_enough(width, height, bytes_len, min_width, min_height)
        return ImageClassification(
            relevance_class=UNCERTAIN if big_enough else DECORATIVE,
            score=0.2 if big_enough else 0.0,
            reason="no caption, alt text or surrounding text; classified on size alone",
            confidence=0.2,
        )

    decorative_hits = [p.pattern for p in decorative if p.search(filename) or p.search(alt)]
    strong_hits: list[tuple[str, str]] = []
    moderate_hits: list[tuple[str, str]] = []
    score = 0.0
    for field_name, value, weight in signals:
        if not value:
            continue
        for pattern in strong:
            if pattern.search(value):
                strong_hits.append((field_name, pattern.pattern))
                score += 0.55 * weight
                break
        for pattern in moderate:
            if pattern.search(value):
                moderate_hits.append((field_name, pattern.pattern))
                score += 0.18 * weight
                break

    if decorative_hits and not strong_hits:
        return ImageClassification(
            relevance_class=DECORATIVE,
            score=0.0,
            reason=f"decorative marker in filename or alt text ({decorative_hits[0]})",
            confidence=0.75,
        )

    if _is_icon(width, height):
        # A strong keyword normally outweighs the size floor — a thumbnail of a
        # site plan is still a site plan. An icon is different: nothing at
        # icon size is a readable plan or map, whatever it is named, and
        # "map-pin.png" with alt="map" would otherwise score as research
        # material and be downloaded.
        return ImageClassification(
            relevance_class=DECORATIVE,
            score=0.0,
            reason=f"icon-sized ({width}x{height}); too small to be a readable "
                   "plan, map or photograph whatever its description says",
            confidence=0.85,
        )

    if not _big_enough(width, height, bytes_len, min_width, min_height) and not strong_hits:
        return ImageClassification(
            relevance_class=DECORATIVE,
            score=max(0.0, score - 0.3),
            reason=f"below the size floor ({width}x{height}) with no strong caption signal",
            confidence=0.6,
        )

    image_type = _image_type(haystack)
    topic, fields = _topic_and_fields(haystack)
    image_date, date_confidence = _image_date(caption, alt, surrounding, filename)
    text_support = _documentary_support(caption, alt, surrounding)

    if strong_hits:
        relevance = LIKELY
        reason = f"strong match in {strong_hits[0][0]}: {strong_hits[0][1]}"
    elif text_support != "NOT FOUND":
        # A caption that STATES a deliberate action is what licenses a claim
        # later, so the artefact is worth keeping even without a plan keyword.
        relevance = POSSIBLE
        reason = "caption states a deliberate action, which may support a documentary claim"
    elif moderate_hits and score >= 0.3:
        relevance = POSSIBLE
        reason = f"moderate match in {moderate_hits[0][0]}: {moderate_hits[0][1]}"
    elif moderate_hits:
        relevance = UNCERTAIN
        reason = f"weak match in {moderate_hits[0][0]}"
    else:
        relevance = UNCERTAIN
        reason = "described, but nothing in the description marks it as research-relevant"

    return ImageClassification(
        relevance_class=relevance,
        score=round(min(score, 1.0), 3),
        reason=reason,
        image_type=image_type,
        research_topic=topic,
        possible_fields=list(fields),
        visual_evidence_allowed=VISUAL_EVIDENCE_BY_TYPE.get(image_type, "nothing on its own"),
        documentary_text_support=text_support,
        image_date=image_date,
        image_date_confidence=date_confidence,
        confidence=round(min(0.4 + score * 0.6, 0.95), 3),
    )


#: Below this, on both sides, an image cannot carry documentary content: it is
#: a logo, a bullet, a social icon or a map pin.
ICON_MAX_EDGE = 96


def _compile(patterns: Iterable[str]) -> list[re.Pattern[str]]:
    """Compile lexicon patterns, tolerating a YAML scalar wrapped across lines.

    A quoted YAML scalar that wraps folds its newline into a space, which turns
    `...|plan.?de.?masse|...` into `...| plan.?de.?masse|...` and stops it
    matching a caption that starts with those words. The lexicon keeps each
    alternation on one line; this makes a slip there harmless rather than
    silent.
    """
    compiled: list[re.Pattern[str]] = []
    for pattern in patterns:
        cleaned = re.sub(r"\s*\|\s*", "|", str(pattern).strip())
        try:
            compiled.append(re.compile(cleaned, re.I))
        except re.error:
            continue
    return compiled


def _is_icon(width: int | None, height: int | None) -> bool:
    """Known to be too small to carry any documentary content."""
    if not width or not height:
        return False
    return width <= ICON_MAX_EDGE and height <= ICON_MAX_EDGE


def _big_enough(width: int | None, height: int | None, bytes_len: int | None,
                min_width: int, min_height: int) -> bool:
    if width and height:
        return width >= min_width and height >= min_height
    if bytes_len is not None:
        return bytes_len >= 12000
    return True   # unknown dimensions: do not discard on a guess


def _image_type(haystack: str) -> str:
    for label, patterns in _TYPE_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, haystack, re.I):
                return label
    return "photograph"


def _topic_and_fields(haystack: str) -> tuple[str, tuple[str, ...]]:
    for topic, patterns, fields in _TOPIC_FIELDS:
        for pattern in patterns:
            if re.search(pattern, haystack, re.I):
                return topic, fields
    return "", ()


def _image_date(*texts: str) -> tuple[str | None, str]:
    """A date for the image, only where the text actually states one."""
    for text in texts:
        if not text:
            continue
        match = _YEAR.search(text)
        if match:
            return match.group(1), "stated in caption or filename"
    return None, "none"


def _documentary_support(caption: str, alt: str, surrounding: str) -> str:
    """The exact wording that would license a claim — or NOT FOUND.

    A practice code needs a STATEMENT. This returns the sentence that makes one,
    so a coder can see at a glance whether the image is evidence or decoration.
    """
    combined = " ".join(t for t in (caption, alt, surrounding) if t)
    if not combined.strip():
        return "NOT FOUND"
    action = re.compile(
        r"[^.!?]*\b(plant\w*|sow\w*|dug|dig|excavat\w*|built|construct\w*|creat\w*|"
        r"restor\w*|establish\w*|plant[ée]s?|sem[ée]s?|creus[ée]s?|aangelegd|geplant|"
        r"gepflanzt|angelegt|plantad\w*|piantat\w*)\b[^.!?]*[.!?]?",
        re.I,
    )
    match = action.search(combined)
    if match:
        return match.group().strip()[:600]
    return "NOT FOUND"


def summarise_surrounding(text: str, *, limit: int = 400) -> str:
    """A short, faithful summary for the manifest — a trim, never a paraphrase."""
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    cut = cleaned[:limit]
    boundary = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    if boundary > limit // 2:
        return cut[: boundary + 1]
    return cut.rsplit(" ", 1)[0] + "…"
