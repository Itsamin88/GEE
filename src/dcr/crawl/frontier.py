"""The crawl frontier: a persistent, prioritised, budget-aware URL queue.

Persistence is what makes a run resumable (brief §40): if PyCharm is closed
half way through, the queue, the budgets and the per-source spend are all still
in the database and the next RUN continues from there.

Priority is *retrieval priority* — how much crawl effort a URL earns. It is a
separate concept from the study's evidence rank (brief §54) and never touches it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urlsplit

from ..db import Database
from ..ids import sha1_key
from .normalize import classify_url, normalize

# Path fragments that mark a page as worth reaching first. History and land
# pages carry the dating evidence; documents and reports carry the best of it.
HIGH_VALUE_PATH_TERMS = {
    3.0: ("history", "histoire", "geschiedenis", "geschichte", "historia", "storia",
          "our-story", "timeline", "chronologie", "tijdlijn", "anniversaire", "jubileum"),
    2.6: ("report", "rapport", "verslag", "bericht", "informe", "relatorio", "relatório",
          "publication", "publicatie", "document", "download", "library", "bibliotheque",
          "bibliothek", "resources", "ressources", "dossier"),
    2.4: ("land", "terrain", "terrein", "grond", "farm", "ferme", "boerderij", "finca",
          "quinta", "hectare", "parcel", "domaine", "landgoed", "le-lieu", "lieu",
          "het-terrein", "la-terre", "unser-land"),
    2.2: ("restoration", "restauration", "herstel", "renaturier", "reforest", "reboisement",
          "herbebossing", "regeneration", "regeneratie", "permaculture", "permacultuur",
          "agroforest", "voedselbos", "food-forest", "foret-jardin", "water", "eau",
          "swale", "keyline",
          # Ecology and the water-retention vocabulary a research-rich site
          # uses for exactly the pages this study needs (brief §19).
          "ecolog", "ecologie", "okolog", "ökolog", "ecologia", "biodivers",
          "rewilding", "retention", "aquifer", "watershed", "hydrolog",
          "soil", "sol-vivant", "bodem", "boden", "erosion"),
    2.0: ("about", "a-propos", "apropos", "over-ons", "ueber-uns", "sobre", "chi-siamo",
          "who-we-are", "quienes", "quem-somos", "wie-zijn-wij"),
    1.8: ("project", "projet", "projecten", "projekte", "proyecto", "projeto",
          "garden", "jardin", "tuin", "huerta", "agriculture", "landbouw", "landwirtschaft"),
    1.4: ("blog", "news", "nieuws", "actualites", "aktuelles", "noticias", "journal",
          "updates", "archive", "archief", "archiv"),
    1.2: ("gallery", "galerie", "galeria", "photos", "fotos", "media", "plan", "map",
          "carte", "kaart"),
}

LOW_VALUE_PATH_TERMS = (
    "cart", "checkout", "basket", "login", "signin", "register", "account", "wishlist",
    "privacy", "cookie", "terms", "impressum", "disclaimer", "sitemap.html",
    "tag/", "author/", "comment", "share", "subscribe", "newsletter-signup",
)

_YEAR_IN_URL = re.compile(r"/(19[89]\d|20[0-2]\d)(/|$|-)")


@dataclass
class FrontierItem:
    url: str
    normalized_url: str
    url_key: str
    source_id: str | None
    depth: int
    priority: float
    kind: str
    stage: int | None
    discovered_by: str | None


def score_url(url: str, *, depth: int, kind: str, source_priority: str = "B",
              discovery_method: str = "link", prefer_oldest: bool = True) -> float:
    """Retrieval priority for one URL. Higher is fetched sooner."""
    score = 5.0
    path = (urlsplit(url).path or "/").lower()

    for weight, terms in HIGH_VALUE_PATH_TERMS.items():
        if any(term in path for term in terms):
            score += weight
            break
    if any(term in path for term in LOW_VALUE_PATH_TERMS):
        score -= 3.5

    if kind == "document":
        score += 3.5          # a dated PDF outweighs the rest of a website
    elif kind == "image":
        score -= 1.0

    score -= 0.8 * max(0, depth)

    if prefer_oldest:
        match = _YEAR_IN_URL.search(path)
        if match:
            year = int(match.group(1))
            # The older the dated material, the more it is worth for onset.
            score += max(0.0, (2016 - year) * 0.22)

    score += {"A": 2.0, "B": 0.8, "C": 0.0}.get(source_priority, 0.0)
    score += {
        "sitemap": 1.2, "feed": 1.4, "cdx": 1.6, "footer": 0.9, "nav": 0.6,
        "search": 0.5, "link": 0.0, "seed": 6.0, "pagination": 0.3,
        "oembed": 0.5, "api": 0.5,
        # A guessed path is a guess: it must never be fetched ahead of a URL the
        # site itself published in its sitemap or feed.
        "path_probe": -1.5,
    }.get(discovery_method, 0.0)
    return round(score, 3)


class Frontier:
    """A database-backed queue, so nothing is lost when a run stops."""

    def __init__(self, db: Database, community_id: str):
        self.db = db
        self.community_id = community_id
        self._seen: set[str] = set()
        self._load_seen()

    def _load_seen(self) -> None:
        rows = self.db.query(
            "SELECT url_key FROM frontier WHERE community_id = ?", (self.community_id,)
        )
        self._seen = {row["url_key"] for row in rows}

    # -- adding ------------------------------------------------------------
    def add(
        self,
        url: str,
        *,
        source_id: str | None = None,
        depth: int = 0,
        kind: str | None = None,
        stage: int | None = None,
        discovered_by: str | None = None,
        discovery_method: str = "link",
        source_priority: str = "B",
        base: str | None = None,
        priority: float | None = None,
        prefer_oldest: bool = True,
    ) -> str | None:
        """Queue a URL. Returns the normalised URL if newly added, else None."""
        normalized = normalize(url, base)
        if not normalized:
            return None
        key = sha1_key(normalized)
        if key in self._seen:
            return None
        resolved_kind = kind or classify_url(normalized)
        if resolved_kind == "skip":
            return None
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        score = priority if priority is not None else score_url(
            normalized, depth=depth, kind=resolved_kind,
            source_priority=source_priority, discovery_method=discovery_method,
            prefer_oldest=prefer_oldest,
        )
        self.db.insert(
            "frontier",
            {
                "url_key": key,
                "community_id": self.community_id,
                "source_id": source_id,
                "url": url,
                "normalized_url": normalized,
                "depth": depth,
                "priority": score,
                "kind": resolved_kind,
                "stage": stage,
                "discovered_by": discovered_by or discovery_method,
                "status": "queued",
                "added_utc": now,
                "updated_utc": now,
            },
            replace=True,
        )
        self._seen.add(key)
        return normalized

    def add_many(self, urls: Iterable[str], **kwargs: object) -> int:
        added = 0
        for url in urls:
            if self.add(url, **kwargs):  # type: ignore[arg-type]
                added += 1
        return added

    # -- taking work -------------------------------------------------------
    def next_batch(self, limit: int, *, kinds: tuple[str, ...] | None = None) -> list[FrontierItem]:
        clause = ""
        params: list[object] = [self.community_id]
        if kinds:
            clause = f" AND kind IN ({','.join('?' for _ in kinds)})"
            params.extend(kinds)
        params.append(limit)
        rows = self.db.query(
            "SELECT * FROM frontier WHERE community_id = ? AND status = 'queued'"
            + clause
            + " ORDER BY priority DESC, added_utc ASC LIMIT ?",
            params,
        )
        items: list[FrontierItem] = []
        for row in rows:
            self.db.update(
                "frontier",
                {"status": "in_flight",
                 "updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                {"community_id": self.community_id, "url_key": row["url_key"]},
            )
            items.append(
                FrontierItem(
                    url=row["url"],
                    normalized_url=row["normalized_url"],
                    url_key=row["url_key"],
                    source_id=row["source_id"],
                    depth=row["depth"],
                    priority=row["priority"],
                    kind=row["kind"],
                    stage=row["stage"],
                    discovered_by=row["discovered_by"],
                )
            )
        return items

    def complete(self, url_key: str, status: str = "done", error: str | None = None) -> None:
        values: dict[str, object] = {
            "status": status,
            "updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        if error:
            values["last_error"] = error[:2000]
        self.db.update("frontier", values, {"community_id": self.community_id, "url_key": url_key})

    def retry_later(self, url_key: str, error: str) -> None:
        self.db.execute(
            "UPDATE frontier SET status='queued', attempts=attempts+1, last_error=?, updated_utc=? "
            "WHERE community_id=? AND url_key=?",
            (error[:2000], datetime.now(timezone.utc).isoformat(timespec="seconds"),
             self.community_id, url_key),
        )

    def pending_count(self) -> int:
        """How much work is left. Used for progress and for the time estimate."""
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM frontier WHERE community_id = ? "
            "AND status IN ('queued', 'in_flight')", (self.community_id,)) or 0)

    def counts_by_status(self) -> dict[str, int]:
        """The queue broken down by state, for the completion report (brief §26)."""
        rows = self.db.query(
            "SELECT status, COUNT(*) AS n FROM frontier WHERE community_id = ? "
            "GROUP BY status", (self.community_id,))
        return {row["status"]: int(row["n"]) for row in rows}

    def reclaim_in_flight(self) -> int:
        """After an interrupted run, put anything left mid-flight back in the queue."""
        cursor = self.db.execute(
            "UPDATE frontier SET status='queued', updated_utc=? "
            "WHERE community_id=? AND status='in_flight'",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), self.community_id),
        )
        return cursor.rowcount or 0

    def requeue_failed(self) -> int:
        cursor = self.db.execute(
            "UPDATE frontier SET status='queued', updated_utc=? "
            "WHERE community_id=? AND status IN ('failed','deferred')",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), self.community_id),
        )
        return cursor.rowcount or 0

    # -- state -------------------------------------------------------------
    def counts(self) -> dict[str, int]:
        rows = self.db.query(
            "SELECT status, COUNT(*) AS n FROM frontier WHERE community_id = ? GROUP BY status",
            (self.community_id,),
        )
        return {row["status"]: row["n"] for row in rows}

    def pending(self) -> int:
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM frontier WHERE community_id = ? AND status = 'queued'",
            (self.community_id,),
        ) or 0)

    def pending_for_source(self, source_id: str) -> int:
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM frontier WHERE community_id=? AND source_id=? AND status='queued'",
            (self.community_id, source_id),
        ) or 0)

    def has_seen(self, url: str) -> bool:
        normalized = normalize(url)
        return bool(normalized) and sha1_key(normalized) in self._seen


class SourceBudget:
    """Adaptive crawl budget (brief §39).

    A source starts with a base allowance and earns more while it keeps yielding
    evidence. When its recent pages stop yielding anything new, it is declared
    exhausted and the effort moves to a source class that is still thin.
    """

    def __init__(self, source_id: str, *, base: int, maximum: int,
                 yield_window: int = 10, yield_threshold: float = 0.15,
                 increment: int = 25, exhaustion_window: int = 20):
        self.source_id = source_id
        self.limit = base
        self.maximum = maximum
        self.spent = 0
        self.yield_window = yield_window
        self.yield_threshold = yield_threshold
        self.increment = increment
        self.exhaustion_window = exhaustion_window
        self.recent: list[bool] = []
        self.barren_streak = 0
        self.failure_streak = 0
        # A source is only declared dead when nothing responds for a long run of
        # attempts, well beyond the number of speculative probes the protocol makes.
        self.dead_source_window = max(exhaustion_window * 4, 60)
        self.exhausted_reason: str | None = None
        #: What this source produced that earned it extra effort.
        self.high_value_finds: list[str] = []

    @property
    def exhausted(self) -> bool:
        return self.exhausted_reason is not None

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.spent)

    def record_failure(self) -> None:
        """A speculative probe that 404s costs effort but is not a page opened.

        It must not count towards exhaustion either: the register asks for forty
        well-known paths to be tried, most of which do not exist on any given
        site, and letting those 404s exhaust the source abandons it before its
        sitemap pages are read. Only a genuinely dead source — one where nothing
        at all responds — stops on failures alone.
        """
        self.failure_streak += 1
        if self.failure_streak >= self.dead_source_window:
            self.exhausted_reason = (
                f"{self.failure_streak} consecutive requests failed; the source appears dead"
            )

    def reward_high_value_find(self, what: str, *, pages: int = 20) -> None:
        """A source that just produced a thesis or a site plan has earned more.

        The register's best evidence is concentrated: a single dated project
        report outweighs the rest of a website. A source that has just yielded
        one is exactly where the next minute should be spent, so it gets a
        larger allowance and any earlier exhaustion is lifted (brief §9).
        """
        self.limit = min(self.maximum, self.limit + pages)
        self.barren_streak = 0
        self.failure_streak = 0
        if self.exhausted_reason and "dead" not in self.exhausted_reason:
            self.exhausted_reason = None
        self.high_value_finds.append(what)

    def record(self, *, yielded_evidence: bool, new_urls: int) -> None:
        self.spent += 1
        self.recent.append(yielded_evidence)
        if len(self.recent) > self.yield_window:
            self.recent.pop(0)
        self.failure_streak = 0
        if yielded_evidence or new_urls:
            self.barren_streak = 0
        else:
            self.barren_streak += 1

        if self.barren_streak >= self.exhaustion_window:
            self.exhausted_reason = (
                f"no evidence and no new URLs in {self.barren_streak} consecutive pages"
            )
            return
        if self.spent >= self.limit:
            rate = sum(self.recent) / len(self.recent) if self.recent else 0.0
            if rate >= self.yield_threshold and self.limit < self.maximum:
                self.limit = min(self.maximum, self.limit + self.increment)
            else:
                self.exhausted_reason = (
                    f"budget of {self.limit} pages spent at a {rate:.0%} yield rate"
                    if self.limit < self.maximum
                    else f"reached the {self.maximum}-page ceiling for one source"
                )

    def state(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "limit": self.limit,
            "spent": self.spent,
            "exhausted": self.exhausted,
            "reason": self.exhausted_reason,
            "recent_yield_rate": (sum(self.recent) / len(self.recent)) if self.recent else 0.0,
            "high_value_finds": list(self.high_value_finds),
        }
