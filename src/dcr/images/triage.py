"""Image triage: decide what is worth downloading before downloading it.

The old instruction to a crawler was "save the pictures". For a community with
a photo gallery that means several hundred megabytes of accommodation shots and
sunsets, and one site plan buried among them. The pipeline here is the other way
round (brief §5):

    discover candidates -> lightweight metadata -> classify -> prioritise
        -> download the high-value ones -> provenance -> link to evidence

Two things follow from that, and both matter to the research rather than only to
the bandwidth bill.

**Every candidate is recorded, including the ones passed over.** The register
notes that gallery captions and file names often carry dates that no text on the
site provides, so a candidate's metadata is research material even when its
pixels are not worth fetching. Recording it also makes the triage auditable: a
reader can see what was set aside and why, instead of having to trust that
nothing was missed.

**Priority is not evidence.** A HIGH priority means "fetch this first"; it says
nothing about what the image proves. What an image may evidence is decided
separately, in `classify.py`, and a photograph never becomes a practice code
(register rule 12).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from ..ids import sha1_key
from .classify import DECORATIVE, LIKELY, POSSIBLE, UNCERTAIN, ImageClassification

# -- the four priority bands (brief §7) ------------------------------------
HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"
DUPLICATE = "DUPLICATE"

PRIORITY_ORDER = {HIGH: 0, MEDIUM: 1, LOW: 2, DUPLICATE: 3}

#: Image types that carry documentary weight in their own right: a published
#: plan or map is an artefact of the project, not a picture of it.
_PLAN_TYPES = ("site plan", "map", "diagram", "before_after")

#: What a candidate is worth fetching, before the tie-breakers below.
_BASE_RANK = {HIGH: 100.0, MEDIUM: 50.0, LOW: 10.0, DUPLICATE: 0.0}


@dataclass
class ImageCandidate:
    """One image the crawl has seen, with everything known before fetching it.

    Every field here is obtainable without downloading the image (brief §6);
    ``width``/``height``/``bytes`` are filled from the markup where the page
    declares them, and corrected after a download when it happens.
    """

    original_url: str
    page_url: str = ""
    source_id: str | None = None
    document_id: str | None = None
    page_id: str | None = None
    archive_url: str | None = None
    origin: str = "html"                 # html | document | standalone
    filename: str = ""
    alt_text: str = ""
    title_text: str = ""
    caption: str = ""
    surrounding_text: str = ""
    page_heading: str = ""
    document_title: str = ""
    page_number: int | None = None
    figure_number: str | None = None
    extraction_method: str = ""
    width: int | None = None
    height: int | None = None
    bytes: int | None = None
    mime_type: str = ""
    publication_date: str | None = None
    source_class: str = ""
    independence_group: str | None = None
    stage: int | None = None
    data: bytes | None = None            # already in hand, for embedded figures

    # filled in by triage
    classification: ImageClassification | None = None
    priority: str = LOW
    priority_rank: float = 0.0
    decision: str = ""
    decision_reason: str = ""
    candidate_id: str = ""
    url_key: str = ""

    def __post_init__(self) -> None:
        if not self.filename and self.original_url:
            self.filename = self.original_url.rsplit("/", 1)[-1].split("?")[0]
        if not self.url_key:
            self.url_key = sha1_key(self.original_url or self.filename)


def priority_of(classification: ImageClassification) -> str:
    """Map a research classification onto a retrieval priority band.

    HIGH   a published plan, map or diagram; a figure in a document; a
           before/after pair; anything whose caption names a dated intervention.
    MEDIUM described well enough to be worth a look — a captioned field
           photograph, a dated project photograph.
    LOW    decorative, or described in a way that marks it as decoration.
    """
    if classification is None:
        return LOW
    relevance = classification.relevance_class
    if relevance == DECORATIVE:
        return LOW
    if relevance == LIKELY:
        return HIGH
    if relevance == POSSIBLE:
        # A caption that states a deliberate action, or a stated date, is what
        # separates a useful field photograph from a pretty one.
        if classification.image_type in _PLAN_TYPES:
            return HIGH
        if classification.documentary_text_support != "NOT FOUND":
            return MEDIUM
        if classification.image_date:
            return MEDIUM
        return MEDIUM
    # UNCERTAIN: keep only where the type itself is documentary.
    if classification.image_type in _PLAN_TYPES:
        return MEDIUM
    return LOW


def rank_of(candidate: ImageCandidate) -> float:
    """A sortable score, so the best candidates are fetched first (brief §5)."""
    classification = candidate.classification
    rank = _BASE_RANK.get(candidate.priority, 0.0)
    if classification is None:
        return rank
    rank += classification.score * 20.0
    if classification.image_type in _PLAN_TYPES:
        rank += 12.0
    if classification.image_date:
        rank += 6.0                       # a dated image can support onset work
    if classification.documentary_text_support != "NOT FOUND":
        rank += 5.0
    if candidate.origin == "document":
        rank += 4.0                       # a figure in a report outranks a web image
    if candidate.caption:
        rank += 3.0
    if candidate.width and candidate.height:
        pixels = candidate.width * candidate.height
        if pixels >= 1_000_000:
            rank += 2.0
        elif pixels < 40_000:
            rank -= 8.0
    return round(rank, 3)


class TriageLedger:
    """Records every candidate and the decision taken about it.

    The ledger is also the duplicate check. A gallery image linked from thirty
    pages is one candidate: recognising that before fetching is what stops the
    crawl downloading it thirty times (brief §27).
    """

    def __init__(self, db: Any, community_id: str, *, run_id: str | None = None):
        self.db = db
        self.community_id = community_id
        self.run_id = run_id
        self._seen_urls: dict[str, str] = {}       # url_key -> candidate_id
        self._seen_hashes: dict[str, str] = {}     # sha256  -> candidate_id
        #: url_key -> the decision already recorded for it.
        self._decided: dict[str, str] = {}
        #: url_key -> how many pages linked it.
        self._times_seen: dict[str, int] = {}
        self.counts: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        """Restore what earlier runs already decided, so a resume is idempotent."""
        try:
            rows = self.db.query(
                "SELECT candidate_id, url_key, sha256, decision FROM image_candidates "
                "WHERE community_id = ?", (self.community_id,))
        except Exception:
            return
        for row in rows:
            if row["url_key"]:
                self._seen_urls[row["url_key"]] = row["candidate_id"]
                self._decided[row["url_key"]] = row["decision"] or ""
            if row["sha256"]:
                self._seen_hashes[row["sha256"]] = row["candidate_id"]

    # -- triage ------------------------------------------------------------
    def triage(self, candidates: Sequence[ImageCandidate], *,
               lexicon: Mapping[str, Any] | None = None,
               classify: Any = None,
               min_width: int = 320, min_height: int = 240) -> list[ImageCandidate]:
        """Classify, deduplicate and order a page's worth of candidates.

        Returns them best-first. Nothing has been fetched at this point.
        """
        from .classify import classify_image

        classifier = classify or classify_image
        triaged: list[ImageCandidate] = []
        within_batch: set[str] = set()
        for candidate in candidates:
            if candidate.classification is None:
                candidate.classification = classifier(
                    url=candidate.original_url or candidate.filename,
                    alt=candidate.alt_text,
                    title=candidate.title_text,
                    caption=candidate.caption,
                    surrounding=candidate.surrounding_text,
                    page_title=candidate.page_heading,
                    document_title=candidate.document_title,
                    width=candidate.width,
                    height=candidate.height,
                    bytes_len=candidate.bytes,
                    lexicon=lexicon,
                    min_width=min_width,
                    min_height=min_height,
                )
            candidate.priority = priority_of(candidate.classification)
            if candidate.url_key in self._seen_urls or candidate.url_key in within_batch:
                candidate.priority = DUPLICATE
                candidate.decision_reason = (
                    "the same image address has already been triaged for this community")
            within_batch.add(candidate.url_key)
            candidate.priority_rank = rank_of(candidate)
            triaged.append(candidate)

        triaged.sort(key=lambda c: (PRIORITY_ORDER.get(c.priority, 9), -c.priority_rank))
        return triaged

    def is_duplicate_hash(self, digest: str) -> str | None:
        return self._seen_hashes.get(digest)

    # -- recording ---------------------------------------------------------
    def record(self, candidate: ImageCandidate, *, decision: str,
               reason: str = "", image_id: str | None = None,
               sha256: str | None = None) -> str:
        """Write the candidate and its outcome to the ledger.

        A candidate already decided is not re-decided. Meeting the same gallery
        photo on a ninth page says something about the page, not about the
        image: overwriting the first row's real reason ("LOW priority: nothing
        in its description marks it as research-relevant") with the far less
        informative "duplicate" would destroy exactly the audit trail this
        ledger exists to keep.
        """
        self._times_seen[candidate.url_key] = self._times_seen.get(
            candidate.url_key, 0) + 1
        previous = self._decided.get(candidate.url_key)
        if previous and decision == "skipped_duplicate":
            candidate.candidate_id = self._seen_urls.get(candidate.url_key,
                                                         candidate.candidate_id)
            candidate.decision = previous
            self.counts["seen_again"] = self.counts.get("seen_again", 0) + 1
            try:
                self.db.execute(
                    "UPDATE image_candidates SET times_seen = ? WHERE candidate_id = ?",
                    (self._times_seen[candidate.url_key], candidate.candidate_id))
            except Exception:
                pass
            return candidate.candidate_id
        candidate.decision = decision
        if reason:
            candidate.decision_reason = reason
        if not candidate.candidate_id:
            existing = self._seen_urls.get(candidate.url_key)
            candidate.candidate_id = existing or self.db.next_id(
                "image_candidates", "candidate_id", self.community_id, "IMGC")
        classification = candidate.classification
        from .db_values import candidate_row          # local import keeps this file readable

        row = candidate_row(candidate, community_id=self.community_id, run_id=self.run_id,
                            image_id=image_id, sha256=sha256,
                            times_seen=self._times_seen.get(candidate.url_key, 1))
        self.db.insert("image_candidates", row, replace=True)
        self._seen_urls[candidate.url_key] = candidate.candidate_id
        self._decided[candidate.url_key] = decision
        if sha256:
            self._seen_hashes.setdefault(sha256, candidate.candidate_id)
        self.counts[decision] = self.counts.get(decision, 0) + 1
        return candidate.candidate_id

    def summary(self) -> dict[str, int]:
        return dict(self.counts)
