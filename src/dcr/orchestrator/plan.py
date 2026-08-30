"""What the researcher entered, sized and ordered before anything is fetched.

Three jobs, in this order:

**Sizing.** How much work is each community likely to be? Before any request is
made this can only come from what was typed — how many addresses, what kind they
are, whether coordinates and a country were given. That is a weak signal and the
estimate says so, in a range rather than a number (brief §45).

**Ordering.** The scheduler needs to know which community to start first. Two
things drive it: expected value (a community with six addresses including an
academic page is worth more than one with a Facebook link) and expected size.
Large jobs start early so they are not left running alone at the end while
fifteen workers idle — the classic longest-processing-time-first result — but
never so aggressively that the small ones starve, which is what the ageing rule
in the store is for (brief §5, §47).

**Identity.** Each community is given its queue position (`C001`) and its
workbook site id (`IC001`) here, once, so both the parent and the worker agree
on where its output goes before the worker starts.

The estimate is refined after lightweight discovery, in `Estimator`; this module
is what exists before there is anything to refine.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

from ..ids import safe_name

# ---------------------------------------------------------------------------
# What different kinds of address are worth, and cost
# ---------------------------------------------------------------------------
#: Workload units per address, by what the address appears to be. A unit is
#: roughly "one minute of active work on a typical machine"; the mapping is
#: recalibrated from observed runs by `Estimator`, so these are only the
#: starting point for a run with no history (brief §48).
ADDRESS_COST: dict[str, float] = {
    "website": 14.0,        # sitemaps, deep crawl, documents: the bulk of the work
    "archive": 8.0,         # an old domain: usually smaller, often richer
    "academic": 4.0,        # a repository page, a DOI: cheap and valuable
    "directory": 2.0,       # a network listing: one page, quickly read
    "social": 3.0,          # public content only, often login-walled
    "video": 2.5,           # metadata and captions, never the video
    "document": 2.0,        # a PDF linked directly
    "unknown": 6.0,
}

#: What each address kind suggests about the community's research value. Used
#: for ordering, never for deciding what to crawl: every supplied address is
#: crawled whatever this says (brief §27).
ADDRESS_VALUE: dict[str, float] = {
    "website": 3.0, "archive": 3.5, "academic": 5.0, "directory": 1.5,
    "social": 1.5, "video": 1.0, "document": 2.5, "unknown": 2.0,
}

#: Stages that run whatever was supplied — search, academic, grey, language.
#: A community with no addresses at all still costs this much.
BASELINE_UNITS = 12.0

#: The share of a community's work that cannot overlap with another community's:
#: per-host politeness, the parent's own bookkeeping, one SQLite writer each.
DEFAULT_CONTENTION = 0.05

#: Interference BETWEEN workers — the shared hosts, the disk, the memory bus.
#: It grows with the square of the worker count, which is why sixteen workers
#: can be slower than twelve and why the governor measures rather than assumes.
DEFAULT_COHERENCY = 0.0008

#: The spread on an estimate made from nothing but typed addresses. Wide on
#: purpose: pretending to a tighter number would be dishonest (brief §45).
ESTIMATE_LOW_FACTOR = 0.55
ESTIMATE_HIGH_FACTOR = 2.1

_SOCIAL = re.compile(
    r"(facebook|instagram|twitter|x\.com|linkedin|tiktok|mastodon|threads|bsky)",
    re.IGNORECASE)
_VIDEO = re.compile(r"(youtube|youtu\.be|vimeo|dailymotion)", re.IGNORECASE)
_ACADEMIC = re.compile(
    r"(scholar\.google|researchgate|academia\.edu|jstor|doi\.org|arxiv|"
    r"repositor|\.edu|\.ac\.|dspace|zenodo|hal\.science|core\.ac\.uk|orcid)",
    re.IGNORECASE)
_DIRECTORY = re.compile(
    r"(ecovillage\.org|gen-europe|ic\.org|numundo|wwoof|permaculture(global|news)|"
    r"fellowship|directory|network)", re.IGNORECASE)
_ARCHIVE = re.compile(r"(web\.archive\.org|archive\.(org|today)|wayback)", re.IGNORECASE)
_DOCUMENT = re.compile(r"\.(pdf|docx?|xlsx?|pptx?|odt|ods|csv)(\?|$)", re.IGNORECASE)


def classify_address(url: str) -> str:
    """What kind of thing is this address? Cheap, and only ever a hint."""
    text = (url or "").strip()
    if not text:
        return "unknown"
    if _DOCUMENT.search(text):
        return "document"
    if _ARCHIVE.search(text):
        return "archive"
    if _ACADEMIC.search(text):
        return "academic"
    if _SOCIAL.search(text):
        return "social"
    if _VIDEO.search(text):
        return "video"
    if _DIRECTORY.search(text):
        return "directory"
    host = (urlsplit(text if "//" in text else f"//{text}").hostname or "").lower()
    return "website" if host else "unknown"


def scalability(workers: int, *, contention: float = DEFAULT_CONTENTION,
                coherency: float = DEFAULT_COHERENCY) -> float:
    """Speed-up from N workers under the Universal Scalability Law.

    `scalability(1)` is exactly 1.0, and the curve rises, flattens and can fall
    — which is the honest shape. A model that could only rise would never let
    the software say "twelve was better than sixteen".
    """
    count = max(1, int(workers))
    if count == 1:
        return 1.0
    denominator = (1.0 + contention * (count - 1)
                   + coherency * count * (count - 1))
    return count / max(1e-9, denominator)


def best_worker_count(maximum: int = 32, *, contention: float = DEFAULT_CONTENTION,
                      coherency: float = DEFAULT_COHERENCY) -> int:
    """Where the curve above peaks — the point past which more workers cost."""
    return max(range(1, max(2, int(maximum)) + 1),
               key=lambda n: scalability(n, contention=contention,
                                         coherency=coherency))


@dataclass
class CommunityJob:
    """One community, as it enters the queue."""

    job_id: str                       # C001 — its position in the queue
    site_id: str                      # IC001 — its identity in the workbook
    name: str
    urls: list[str] = field(default_factory=list)
    latitude: float | None = None
    longitude: float | None = None
    country: str | None = None
    coder_id: str = ""
    mode: str = "FULL"
    fixture: bool = False
    #: Sites to walk in full rather than sample - the community's own domains.
    deep_crawl_urls: list[str] = field(default_factory=list)
    #: Exact query strings for the exhaustive academic harvest.
    academic_search_terms: list[str] = field(default_factory=list)
    crawl_policy: str | None = None

    workload_units: float = 0.0
    estimate_low_s: float = 0.0
    estimate_high_s: float = 0.0
    estimate_basis: str = ""
    priority: float = 0.0

    output_dir: str = ""
    database_path: str = ""

    @property
    def directory_name(self) -> str:
        return f"{self.site_id}_{safe_name(self.name)}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id, "site_id": self.site_id, "name": self.name,
            "urls": list(self.urls), "latitude": self.latitude,
            "longitude": self.longitude, "country": self.country,
            "coder_id": self.coder_id, "mode": self.mode, "fixture": self.fixture,
            "deep_crawl_urls": list(self.deep_crawl_urls),
            "academic_search_terms": list(self.academic_search_terms),
            "crawl_policy": self.crawl_policy,
            "workload_units": self.workload_units,
            "estimate_low_s": self.estimate_low_s,
            "estimate_high_s": self.estimate_high_s,
            "estimate_basis": self.estimate_basis, "priority": self.priority,
            "output_dir": self.output_dir, "database_path": self.database_path,
        }

    def estimate_text(self) -> str:
        low = self.estimate_low_s / 60.0
        high = self.estimate_high_s / 60.0
        if high >= 90:
            return f"{low / 60:.1f}–{high / 60:.1f} h"
        return f"{low:.0f}–{high:.0f} min"


def estimate_workload(urls: Sequence[str], *, country: str | None = None,
                      has_coordinates: bool = False,
                      unit_seconds: float = 60.0,
                      calibration: Mapping[str, float] | None = None,
                      ) -> tuple[float, float, float, str]:
    """Size one community from what was typed. Returns (units, low_s, high_s, why).

    Deliberately crude. It has nothing to work from but the addresses, and a
    confident number here would be a lie — so it produces a wide range and says
    what it was based on, and the scheduler treats it as an ordering hint rather
    than a promise (brief §45, §46).
    """
    costs = {**ADDRESS_COST, **dict(calibration or {})}
    kinds: dict[str, int] = {}
    units = BASELINE_UNITS
    for url in urls:
        kind = classify_address(url)
        kinds[kind] = kinds.get(kind, 0) + 1
        units += costs.get(kind, costs["unknown"])

    # A country makes the local-language sweep and the registry searches
    # worthwhile; without one they are guesswork and mostly skipped.
    if country:
        units += 4.0
    # Coordinates cost nothing but make several checks possible.
    if has_coordinates:
        units += 1.0
    # Diminishing returns: the sixth address on one community shares most of its
    # crawl with the first five, because they usually overlap.
    if len(urls) > 4:
        units -= (len(urls) - 4) * 1.5

    units = max(BASELINE_UNITS, units)
    described = ", ".join(f"{count} {kind}" for kind, count in sorted(kinds.items()))
    basis = (f"{len(urls)} supplied address(es)"
             + (f" ({described})" if described else "")
             + (f"; country {country}" if country else "; no country given"))
    return (round(units, 1),
            round(units * unit_seconds * ESTIMATE_LOW_FACTOR, 1),
            round(units * unit_seconds * ESTIMATE_HIGH_FACTOR, 1),
            basis)


def value_score(urls: Sequence[str], *, country: str | None = None) -> float:
    """How much research value this community's addresses suggest.

    Used only for ordering. It never decides what to crawl: every supplied
    address is crawled whatever this says (brief §27).
    """
    score = 1.0
    seen_hosts: set[str] = set()
    for url in urls:
        kind = classify_address(url)
        host = (urlsplit(url if "//" in url else f"//{url}").hostname or "").lower()
        # Five pages of one site are one address's worth of value.
        weight = 1.0 if host not in seen_hosts else 0.3
        seen_hosts.add(host)
        score += ADDRESS_VALUE.get(kind, 2.0) * weight
    if country:
        score += 1.0
    # Independent hosts are the thing the protocol actually wants (register
    # v2.4 §9): three different domains beat three pages of one.
    score += min(4.0, len(seen_hosts) * 0.8)
    return round(score, 2)


@dataclass
class RunPlan:
    """The whole queue, sized and ordered, before anything is fetched."""

    run_id: str
    jobs: list[CommunityJob] = field(default_factory=list)
    mode: str = "FULL"

    @property
    def total_units(self) -> float:
        return sum(job.workload_units for job in self.jobs)

    @property
    def active_low_s(self) -> float:
        return sum(job.estimate_low_s for job in self.jobs)

    @property
    def active_high_s(self) -> float:
        return sum(job.estimate_high_s for job in self.jobs)

    def wall_clock_estimate_s(self, *, workers_low: int, workers_high: int,
                              contention: float = DEFAULT_CONTENTION,
                              coherency: float = DEFAULT_COHERENCY,
                              ) -> tuple[float, float]:
        """Wall-clock, given a number of workers. Not active time divided by N.

        Parallel speed-up is never linear, and an estimate that pretends it is
        would be exactly the overstatement the brief forbids in §96. Three
        things take the difference, and each has its own term:

        **Serial work** — per-host politeness delays, the parent writing the
        queue, the one SQLite writer per community. `contention` is the share of
        a community's work that cannot overlap with another's.

        **Cross-worker interference** — the shared hosts every community reaches,
        the disk, the memory bus. `coherency` grows with the SQUARE of the worker
        count, because interference is between pairs, and it is why sixteen
        workers can be slower than twelve.

        **The tail** — the last communities cannot be spread over more workers
        than there are of them, and no arrangement finishes sooner than the
        single longest community.

            speed-up(N) = N / (1 + σ(N-1) + κN(N-1))

        This is the Universal Scalability Law, and the defaults below are a
        starting point only: `tools/benchmark.py` measures σ and κ on the actual
        machine and writes them into configuration, after which this reports
        what that machine really does rather than what a model assumed.
        """
        workers_low = max(1, int(workers_low))
        workers_high = max(workers_low, int(workers_high))

        def spread(active_s: float, workers: int) -> float:
            if not self.jobs:
                return 0.0
            effective = min(workers, len(self.jobs))
            speedup = scalability(effective, contention=contention,
                                  coherency=coherency)
            longest = max((job.estimate_high_s for job in self.jobs), default=0.0)
            return max(longest, active_s / speedup)

        return (round(spread(self.active_low_s, workers_high), 1),
                round(spread(self.active_high_s, workers_low), 1))

    def order(self) -> "RunPlan":
        """Decide the starting priority of every community, on a 0–100 scale.

        Long jobs first, so the run does not end with one enormous community
        holding fifteen idle workers; value second, so the communities most
        likely to repay the effort are not left until last.

        Both are normalised across the queue rather than used raw, and that
        matters more than it looks. A raw workload number is unbounded — one
        community with nine addresses scores five times another with two — so
        the ageing bonus in the store would be a rounding error beside it and
        the small communities would never rise however long they waited. On a
        bounded scale, "has waited an hour" is worth a comparable amount to "is
        twice the size", which is what makes the fairness rule bite (brief §5,
        §47).
        """
        if not self.jobs:
            return self
        sizes = [job.workload_units for job in self.jobs]
        values = [value_score(job.urls, country=job.country) for job in self.jobs]
        low_size, high_size = min(sizes), max(sizes)
        low_value, high_value = min(values), max(values)

        def normalise(value: float, low: float, high: float) -> float:
            if high - low < 1e-9:
                return 0.5
            return (value - low) / (high - low)

        for job, size, value in zip(self.jobs, sizes, values):
            job.priority = round(
                60.0 * normalise(size, low_size, high_size)
                + 40.0 * normalise(value, low_value, high_value), 2)
        self.jobs.sort(key=lambda j: (-j.priority, j.job_id))
        return self

    def table(self, *, limit: int = 0) -> str:
        """The queue as the researcher sees it before pressing START (brief §6)."""
        rows = self.jobs if not limit else self.jobs[:limit]
        width = max((len(job.name) for job in rows), default=9)
        width = min(max(width, 9), 42)
        lines = [
            f"{'ID':<5} {'Community':<{width}} {'URLs':>4}  "
            f"{'Estimated workload':<20} {'Status':<8}",
            f"{'-' * 5} {'-' * width} {'-' * 4}  {'-' * 20} {'-' * 8}",
        ]
        for job in rows:
            name = job.name if len(job.name) <= width else job.name[: width - 1] + "…"
            lines.append(
                f"{job.job_id:<5} {name:<{width}} {len(job.urls):>4}  "
                f"{job.estimate_text():<20} {'QUEUED':<8}")
        if limit and len(self.jobs) > limit:
            lines.append(f"...   and {len(self.jobs) - limit} more")
        return "\n".join(lines)


def build_plan(
    entries: Iterable[Mapping[str, Any]],
    *,
    run_id: str,
    output_root: Path,
    mode: str = "FULL",
    database_filename: str = "research.sqlite3",
    unit_seconds: float = 60.0,
    calibration: Mapping[str, float] | None = None,
    start_index: int = 1,
    fixture: bool = False,
) -> RunPlan:
    """Turn what the researcher typed into a sized, ordered, identified queue.

    The number of communities is whatever was supplied — one, twenty, two
    hundred and twelve. Nothing here has an upper bound (brief §2).
    """
    plan = RunPlan(run_id=run_id, mode=mode)
    for offset, entry in enumerate(entries):
        index = start_index + offset
        site_id = f"{'TEST-' if fixture or entry.get('fixture') else ''}IC{index:03d}"
        urls = [str(u).strip() for u in (entry.get("urls") or []) if str(u).strip()]
        units, low, high, basis = estimate_workload(
            urls, country=entry.get("country"),
            has_coordinates=entry.get("latitude") is not None
            and entry.get("longitude") is not None,
            unit_seconds=unit_seconds, calibration=calibration)
        name = str(entry.get("name") or "").strip()
        directory = Path(output_root) / f"{site_id}_{safe_name(name)}"
        plan.jobs.append(CommunityJob(
            job_id=f"C{index:03d}",
            site_id=site_id,
            name=name,
            urls=urls,
            latitude=entry.get("latitude"),
            longitude=entry.get("longitude"),
            country=entry.get("country"),
            coder_id=str(entry.get("coder_id") or ""),
            mode=str(entry.get("mode") or mode),
            fixture=bool(entry.get("fixture", fixture)),
            deep_crawl_urls=[str(u).strip() for u in (entry.get("deep_crawl_urls") or [])
                             if str(u).strip()],
            academic_search_terms=[str(t).strip() for t in
                                   (entry.get("academic_search_terms") or []) if str(t).strip()],
            crawl_policy=entry.get("crawl_policy"),
            workload_units=units,
            estimate_low_s=low,
            estimate_high_s=high,
            estimate_basis=basis,
            output_dir=str(directory),
            database_path=str(directory / database_filename),
        ))
    return plan.order()


__all__ = [
    "ADDRESS_COST", "ADDRESS_VALUE", "DEFAULT_COHERENCY", "DEFAULT_CONTENTION",
    "CommunityJob", "RunPlan", "best_worker_count", "build_plan",
    "classify_address", "estimate_workload", "scalability", "value_score",
]
