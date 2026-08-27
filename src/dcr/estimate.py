"""How long will this take?

The researcher is about to start something that may run for two hours, and
deserves to know that before it starts rather than after (brief §30). Two
figures are produced, and they are not the same thing:

* **active processing time** — what the machine actually spends fetching,
  parsing and coding;
* **wall-clock duration** — what the clock in the room will say, which also
  includes politeness delays, a server that rate-limits, an archive that is
  slow today, retries, and any time spent paused.

Neither is a promise, and the report says so. The estimate is built from
observable workload, never from a hard-coded duration, and it is recalculated
once lightweight discovery has shown how big the sites really are (brief §32).
Where previous runs exist, their recorded actuals calibrate it (brief §34).
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

from .db import Database, utcnow
from .logging_setup import get_logger

log = get_logger("estimate")

#: Seconds of active processing per unit of work, before calibration. These are
#: starting points, not constants of nature: every one can be overridden in
#: config.yaml, and history from real runs moves the whole model (brief §45).
DEFAULT_COSTS: dict[str, float] = {
    "page_s": 1.6,              # fetch, parse, extract text, mine evidence
    "document_s": 7.0,          # download and parse a PDF or Office file
    "image_candidate_s": 0.05,  # classify a candidate from its metadata
    "image_download_s": 1.1,    # fetch and hash one kept image
    "browser_page_s": 6.5,      # a JavaScript page rendered in Chromium
    "sitemap_s": 1.2,
    "archive_query_s": 4.0,     # one CDX enumeration
    "archive_snapshot_s": 3.2,  # one retrieved snapshot
    "academic_query_s": 5.0,
    "academic_verify_s": 4.0,
    "grey_query_s": 4.5,
    "search_query_s": 3.5,
    "source_overhead_s": 8.0,   # robots, home page, scope confirmation
    "resolve_s": 25.0,          # stage 9 reconciliation, once per run
    "export_s": 20.0,           # workbook, manifests, quality checks
}

#: Multipliers turning active time into wall-clock time. The low end assumes
#: everything answers first time; the high end assumes politeness delays and a
#: normal share of retries.
DEFAULT_WALL_FACTORS = (1.15, 2.1)

#: How wide the band is around the central estimate.
DEFAULT_SPREAD = (0.7, 1.45)

#: Pages a site of unknown size is assumed to have, per supplied address,
#: before discovery has looked. Deliberately modest: the updated estimate
#: after discovery is the one that matters.
ASSUMED_PAGES_PER_SOURCE = 25
ASSUMED_DOCUMENTS_PER_SOURCE = 4
ASSUMED_IMAGE_CANDIDATES_PER_PAGE = 6


@dataclass
class Workload:
    """The countable work a run is expected to do."""

    sources: int = 0
    domains: int = 0
    pages: int = 0
    documents: int = 0
    image_candidates: int = 0
    image_downloads: int = 0
    browser_pages: int = 0
    sitemaps: int = 0
    archive_queries: int = 0
    archive_snapshots: int = 0
    academic_queries: int = 0
    academic_verifications: int = 0
    grey_queries: int = 0
    search_queries: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if k != "notes"}

    @property
    def units(self) -> int:
        """A single number for "how much work", used to compare estimates."""
        return (self.pages + self.documents + self.archive_snapshots
                + self.academic_queries + self.grey_queries + self.search_queries
                + self.image_downloads)


@dataclass
class Estimate:
    """A band, never a single number, and never a guarantee."""

    phase: str
    active_low_s: float
    active_high_s: float
    wall_low_s: float
    wall_high_s: float
    workload: Workload
    basis: dict[str, float] = field(default_factory=dict)
    reason: str = ""
    calibrated: bool = False
    calibration_factor: float = 1.0

    # -- presentation ------------------------------------------------------
    @staticmethod
    def _band(low_s: float, high_s: float) -> str:
        return f"{_minutes(low_s)}–{_minutes(high_s)} min"

    @property
    def active_band(self) -> str:
        return self._band(self.active_low_s, self.active_high_s)

    @property
    def wall_band(self) -> str:
        return self._band(self.wall_low_s, self.wall_high_s)

    def lines(self) -> list[str]:
        out = [
            f"Estimated active processing time: {self.active_band}",
            f"Estimated wall-clock duration:    {self.wall_band}",
        ]
        if self.calibrated:
            out.append(f"  calibrated against previous runs (x{self.calibration_factor:.2f})")
        if self.reason:
            out.append(f"  {self.reason}")
        return out

    def as_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "active_low_s": round(self.active_low_s, 1),
            "active_high_s": round(self.active_high_s, 1),
            "wall_low_s": round(self.wall_low_s, 1),
            "wall_high_s": round(self.wall_high_s, 1),
            "active_band": self.active_band,
            "wall_band": self.wall_band,
            "workload": self.workload.as_dict(),
            "notes": list(self.workload.notes),
            "basis": {k: round(v, 2) for k, v in self.basis.items()},
            "reason": self.reason,
            "calibrated": self.calibrated,
            "calibration_factor": round(self.calibration_factor, 3),
        }


def _minutes(seconds: float) -> int:
    return max(1, int(round(seconds / 60.0)))


class Estimator:
    """Builds workload estimates and records what actually happened."""

    def __init__(self, settings: Any = None, db: Database | None = None):
        self.db = db
        config: Mapping[str, Any] = {}
        if settings is not None:
            config = dict(settings.get("estimation", default={}) or {})
        self.costs = dict(DEFAULT_COSTS)
        for key, value in (config.get("costs") or {}).items():
            if key in self.costs:
                self.costs[key] = float(value)
        spread = config.get("spread") or DEFAULT_SPREAD
        self.spread = (float(spread[0]), float(spread[1]))
        wall = config.get("wall_factors") or DEFAULT_WALL_FACTORS
        self.wall_factors = (float(wall[0]), float(wall[1]))
        self.use_history = bool(config.get("use_history", True))
        self.min_history_runs = int(config.get("min_history_runs", 2))
        self.settings = settings

    # -- the two estimates -------------------------------------------------
    def initial(self, community: Any, *, mode: str = "FULL") -> Estimate:
        """Before any network request: what the researcher's input alone implies."""
        urls = [u for u in getattr(community, "urls", []) or [] if u]
        domains = {_registrable(u) for u in urls}
        domains.discard("")
        stages = _stages_for(mode)

        work = Workload(sources=max(len(urls), 1), domains=max(len(domains), 1))
        if not urls:
            # Nobody supplied an address, so stage 0 has to find them first.
            work.search_queries += 8
            work.notes.append(
                "no addresses supplied: the run must discover them first, which is "
                "the least predictable part of the estimate")
            work.sources = 3

        if 2 in stages:
            work.sitemaps = work.domains
            work.pages = work.sources * ASSUMED_PAGES_PER_SOURCE
            work.browser_pages = max(0, work.pages // 12)
        if 3 in stages:
            work.documents = work.sources * ASSUMED_DOCUMENTS_PER_SOURCE
        if 4 in stages:
            work.archive_queries = work.domains
            work.archive_snapshots = work.domains * 12
        if 5 in stages:
            work.academic_queries = 9
            work.academic_verifications = 4
        if 6 in stages:
            work.grey_queries = 10
        if 7 in stages:
            work.search_queries += 6
        if 8 in stages:
            work.search_queries += 5
            if not getattr(community, "country", None):
                work.notes.append(
                    "no country supplied: the local-language sweep has to guess a "
                    "language, which usually costs more queries and finds less")

        if 2 in stages:
            work.image_candidates = work.pages * ASSUMED_IMAGE_CANDIDATES_PER_PAGE
            work.image_downloads = max(1, work.image_candidates // 10)

        reason = ("built from the addresses supplied, before anything has been fetched; "
                  "site sizes are assumed, not known")
        return self._build("initial", work, reason)

    def after_discovery(self, discovery: "DiscoveryProbe", previous: Estimate | None = None,
                        *, mode: str = "FULL") -> Estimate:
        """After lightweight discovery: what the sites themselves say they hold."""
        stages = _stages_for(mode)
        work = Workload(
            sources=max(discovery.sources, 1),
            domains=max(discovery.domains, 1),
            notes=list(discovery.notes),
        )

        if 2 in stages:
            work.sitemaps = max(discovery.sitemaps_found, work.domains)
            work.pages = discovery.estimated_pages or (
                work.sources * ASSUMED_PAGES_PER_SOURCE)
            work.browser_pages = (discovery.javascript_sources
                                  * max(4, work.pages // max(1, work.sources) // 3))
        if 3 in stages:
            work.documents = discovery.documents_seen or (
                work.sources * ASSUMED_DOCUMENTS_PER_SOURCE)
        if 4 in stages:
            work.archive_queries = work.domains
            work.archive_snapshots = discovery.archive_snapshots or work.domains * 12
        if 5 in stages:
            work.academic_queries = 9
            work.academic_verifications = 4
        if 6 in stages:
            work.grey_queries = 10
        if 7 in stages:
            work.search_queries += 6
        if 8 in stages:
            work.search_queries += 5

        if 2 in stages:
            per_page = discovery.images_per_page or ASSUMED_IMAGE_CANDIDATES_PER_PAGE
            work.image_candidates = int(work.pages * per_page)
            keep_rate = discovery.image_keep_rate or 0.1
            work.image_downloads = max(1, int(work.image_candidates * keep_rate))

        reason = _explain_change(previous, work)
        return self._build("after_discovery", work, reason)

    # -- the arithmetic ----------------------------------------------------
    def _build(self, phase: str, work: Workload, reason: str) -> Estimate:
        c = self.costs
        basis = {
            "pages": work.pages * c["page_s"],
            "documents": work.documents * c["document_s"],
            "image_candidates": work.image_candidates * c["image_candidate_s"],
            "image_downloads": work.image_downloads * c["image_download_s"],
            "browser_pages": work.browser_pages * c["browser_page_s"],
            "sitemaps": work.sitemaps * c["sitemap_s"],
            "archive_queries": work.archive_queries * c["archive_query_s"],
            "archive_snapshots": work.archive_snapshots * c["archive_snapshot_s"],
            "academic_queries": work.academic_queries * c["academic_query_s"],
            "academic_verifications": work.academic_verifications * c["academic_verify_s"],
            "grey_queries": work.grey_queries * c["grey_query_s"],
            "search_queries": work.search_queries * c["search_query_s"],
            "source_overhead": work.sources * c["source_overhead_s"],
            "reconciliation": c["resolve_s"],
            "export": c["export_s"],
        }
        central = sum(basis.values())
        factor, calibrated = self._calibration()
        central *= factor

        active_low = central * self.spread[0]
        active_high = central * self.spread[1]
        return Estimate(
            phase=phase,
            active_low_s=active_low,
            active_high_s=active_high,
            wall_low_s=active_low * self.wall_factors[0],
            wall_high_s=active_high * self.wall_factors[1],
            workload=work,
            basis=basis,
            reason=reason,
            calibrated=calibrated,
            calibration_factor=factor,
        )

    def _calibration(self) -> tuple[float, bool]:
        """How wrong were we last time?

        Used gently (brief §34): the factor is the median of previous
        actual/estimated ratios, clamped, so one pathological run cannot make
        every future estimate absurd.
        """
        if not (self.use_history and self.db is not None):
            return 1.0, False
        try:
            rows = self.db.query(
                "SELECT estimated_active_s, actual_active_s FROM run_history "
                "WHERE estimated_active_s > 0 AND actual_active_s > 0 "
                "ORDER BY ts_utc DESC LIMIT 20")
        except Exception:
            return 1.0, False
        ratios = [float(r["actual_active_s"]) / float(r["estimated_active_s"])
                  for r in rows if r["estimated_active_s"]]
        if len(ratios) < self.min_history_runs:
            return 1.0, False
        factor = statistics.median(ratios)
        return max(0.4, min(factor, 3.0)), True

    # -- recording ---------------------------------------------------------
    def record(self, estimate: Estimate, *, run_id: str | None,
               community_id: str) -> None:
        if self.db is None:
            return
        self.db.insert("run_estimates", {
            "run_id": run_id,
            "community_id": community_id,
            "phase": estimate.phase,
            "active_low_s": estimate.active_low_s,
            "active_high_s": estimate.active_high_s,
            "wall_low_s": estimate.wall_low_s,
            "wall_high_s": estimate.wall_high_s,
            "unit_count": estimate.workload.units,
            "basis": json.dumps(estimate.as_dict()["basis"], ensure_ascii=False),
            "reason": estimate.reason,
            "calibrated": int(estimate.calibrated),
            "ts_utc": utcnow(),
        })

    def record_actual(self, *, run_id: str, community_id: str, mode: str,
                      estimated_active_s: float, actual_active_s: float,
                      wall_clock_s: float, offline_s: float = 0.0,
                      paused_manual_s: float = 0.0, stats: Mapping[str, Any] | None = None,
                      final_state: str = "") -> None:
        """Write what actually happened, so the next estimate can be better."""
        if self.db is None:
            return
        stats = stats or {}
        self.db.upsert("run_history", {
            "run_id": run_id,
            "community_id": community_id,
            "mode": mode,
            "estimated_active_s": estimated_active_s,
            "actual_active_s": actual_active_s,
            "wall_clock_s": wall_clock_s,
            "offline_s": offline_s,
            "paused_manual_s": paused_manual_s,
            "pages_processed": int(stats.get("pages_opened", 0) or 0),
            "documents": int(stats.get("documents", 0) or 0),
            "images_kept": int(stats.get("images_kept", 0) or 0),
            "image_candidates": int(stats.get("image_candidates", 0) or 0),
            "retries": int(stats.get("retries", 0) or 0),
            "errors": int(stats.get("errors", 0) or 0),
            "pauses_manual": int(stats.get("pauses_manual", 0) or 0),
            "pauses_network": int(stats.get("pauses_network", 0) or 0),
            "final_state": final_state,
            "ts_utc": utcnow(),
        }, ["run_id"])


# ===========================================================================
# Lightweight discovery — enough to size the job, not enough to be the job
# ===========================================================================
@dataclass
class DiscoveryProbe:
    """What a few cheap requests revealed about the size of the work ahead.

    The estimation phase must stay lightweight (brief §35): this looks at
    robots.txt, the sitemaps it names, and the home page of each address. It
    never crawls, and it never stores evidence.
    """

    sources: int = 0
    domains: int = 0
    sitemaps_found: int = 0
    sitemap_urls: int = 0
    estimated_pages: int = 0
    documents_seen: int = 0
    images_per_page: float = 0.0
    image_keep_rate: float = 0.0
    javascript_sources: int = 0
    archive_snapshots: int = 0
    unreachable_sources: int = 0
    requests_made: int = 0
    elapsed_s: float = 0.0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if k != "notes"} | {
            "notes": list(self.notes)}


def _registrable(url: str) -> str:
    host = (urlsplit(url if "//" in url else f"//{url}").hostname or "").lower()
    parts = [p for p in host.split(".") if p]
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _stages_for(mode: str) -> set[int]:
    from .runner import MODE_STAGES
    return set(MODE_STAGES.get(mode, MODE_STAGES["FULL"]))


def _explain_change(previous: Estimate | None, work: Workload) -> str:
    """Say, in one sentence, why the number moved (brief §32)."""
    if previous is None:
        return "built from what lightweight discovery found"
    before, after = previous.workload, work
    reasons: list[str] = []
    if after.pages > before.pages * 1.25:
        reasons.append(f"the sitemaps list {after.pages} pages "
                       f"where {before.pages} were assumed")
    elif after.pages < before.pages * 0.75:
        reasons.append(f"the sites are smaller than assumed "
                       f"({after.pages} pages, not {before.pages})")
    if after.documents > before.documents * 1.3:
        reasons.append(f"{after.documents} documents were seen, not {before.documents}")
    if after.sources > before.sources:
        reasons.append(f"{after.sources} addresses are in scope, not {before.sources}")
    if after.browser_pages > before.browser_pages * 1.3:
        reasons.append("some pages need a browser, which is several times slower")
    if not reasons:
        return "lightweight discovery broadly confirmed the initial assumptions"
    return "; ".join(reasons)
