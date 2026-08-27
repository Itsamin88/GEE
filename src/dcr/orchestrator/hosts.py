"""Politeness that survives running sixteen communities at once.

Inside one community, `net/ratelimit.py` already keeps requests to one host
spaced out. That is no longer enough. The brief is explicit about why (§4, §40):
sixteen communities is not sixteen requests, and the point of running them in
parallel is to overlap *independent* waiting — not to arrive at one server from
sixteen directions at once.

Most hosts are not shared: each community has its own website, and sixteen
workers on sixteen different domains interfere with nobody. The problem is the
handful of hosts that every community needs.

    web.archive.org        stage 4, every community
    scholar / crossref     stage 5, every community
    doi.org, repositories  stage 5
    search endpoints       stages 0, 2, 5, 6

Left alone, a 212-community run would send those hosts sixteen concurrent
streams and be rate-limited into uselessness within minutes — and rightly so.

## The design

The parent process owns one broker. Workers hold a proxy to it and ask before
each request to a **shared** host. Community-specific hosts are not brokered at
all: paying an inter-process round trip for a request nobody else is making
would be pure overhead.

    worker ──ask──> broker ──> wait 1.4s ──> go
                       │
                       └─ another worker asking for the same host waits behind it

A lease is granted, used and released. The broker enforces two things per host:
a **concurrency limit** (how many requests may be in flight) and a **delay**
(how long since the last one). Both tighten automatically when a host says it is
unhappy — a 429, a 503, a Retry-After — and relax slowly when it is not.

## Why not a shared token bucket in the database

Because the SQLite file would then be written on every request from every
worker, which reintroduces exactly the writer-lock contention that one database
per community exists to remove. The broker is in memory in the parent, and the
database only records what it observed, once every few seconds.

## Failure

If the broker is unreachable — the parent is shutting down, the proxy is gone —
the worker proceeds using its own local limiter. Politeness degrades to what one
community would have done alone, which is the correct failure direction: never
stop researching because a coordinator went away.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

from ..logging_setup import get_logger

log = get_logger("orchestrator.hosts")

#: Hosts every community reaches, so a run of two hundred hits them two hundred
#: times over. These are the only ones worth an inter-process round trip.
SHARED_HOST_PATTERNS: tuple[str, ...] = (
    "web.archive.org", "archive.org", "timetravel.mementoweb.org",
    "scholar.google.com", "api.crossref.org", "doi.org", "dx.doi.org",
    "api.openalex.org", "openalex.org", "api.semanticscholar.org",
    "core.ac.uk", "arxiv.org", "export.arxiv.org", "zenodo.org",
    "base-search.net", "openaire.eu", "explore.openaire.eu",
    "duckduckgo.com", "html.duckduckgo.com", "lite.duckduckgo.com",
    "search.marcia.eu", "www.bing.com", "bing.com", "search.brave.com",
    "www.google.com", "google.com", "startpage.com", "mojeek.com",
    "ec.europa.eu", "cordis.europa.eu", "webgate.ec.europa.eu",
    "api.openaire.eu", "pub.orcid.org", "orcid.org",
    "en.wikipedia.org", "wikipedia.org", "wikidata.org", "query.wikidata.org",
    "nominatim.openstreetmap.org", "overpass-api.de",
)

#: Default politeness for a shared host: how many requests may be in flight, and
#: the minimum gap between two of them.
DEFAULT_SHARED_CONCURRENCY = 2
DEFAULT_SHARED_DELAY_S = 1.5

#: The archive is slow and heavily used; it gets the strictest treatment.
HOST_OVERRIDES: dict[str, tuple[int, float]] = {
    "web.archive.org": (2, 2.5),
    "archive.org": (2, 2.5),
    "scholar.google.com": (1, 6.0),
    "www.google.com": (1, 5.0),
    "google.com": (1, 5.0),
    "api.crossref.org": (3, 0.6),
    "api.openalex.org": (3, 0.6),
    "doi.org": (3, 0.8),
}

#: Never wait longer than this for a lease. A jammed host must not hold a worker
#: for ever; the crawl records the deferral and moves on (brief §63).
MAX_LEASE_WAIT_S = 90.0

#: How far a host's delay may be pushed by repeated rate limiting.
MAX_DELAY_S = 60.0


def host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def is_shared_host(host: str, patterns: Iterable[str] = SHARED_HOST_PATTERNS) -> bool:
    """Is this a host every community will reach?

    Matched on the registrable tail so `web.archive.org` also catches
    `web.archive.org.` and a regional mirror under the same suffix, without
    catching an unrelated host that merely contains the string.
    """
    name = (host or "").lower().strip(".")
    if not name:
        return False
    for pattern in patterns:
        pattern = pattern.lower().strip(".")
        if name == pattern or name.endswith("." + pattern):
            return True
    return False


@dataclass
class HostState:
    """What one host is currently being allowed, and what it has done."""

    host: str
    concurrency: int = DEFAULT_SHARED_CONCURRENCY
    delay_s: float = DEFAULT_SHARED_DELAY_S
    in_flight: int = 0
    last_started: float = 0.0
    requests: int = 0
    failures: int = 0
    rate_limited: int = 0
    blocked: int = 0
    total_latency_s: float = 0.0
    deferred: int = 0
    #: Communities that have asked for this host, so the report can show which
    #: hosts are genuinely shared and which only looked it.
    communities: set = field(default_factory=set)

    @property
    def mean_latency_s(self) -> float:
        return self.total_latency_s / self.requests if self.requests else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "requests": self.requests,
            "failures": self.failures,
            "rate_limited": self.rate_limited,
            "blocked": self.blocked,
            "deferred": self.deferred,
            "concurrency": self.concurrency,
            "delay_s": round(self.delay_s, 2),
            "mean_latency_s": round(self.mean_latency_s, 3),
            "communities": len(self.communities),
        }


class HostBroker:
    """Per-host politeness across every community in the run.

    Lives in the parent process. Workers reach it through a
    `multiprocessing.Manager` proxy, which works identically on Windows and on
    POSIX — there is no `fork`-shared memory here, and nothing assumes one.
    """

    def __init__(self, *, config: Mapping[str, Any] | None = None):
        config = dict(config or {})
        self._lock = threading.Condition()
        self._hosts: dict[str, HostState] = {}
        self.default_concurrency = int(
            config.get("shared_host_concurrency", DEFAULT_SHARED_CONCURRENCY))
        self.default_delay_s = float(
            config.get("shared_host_delay_s", DEFAULT_SHARED_DELAY_S))
        self.max_wait_s = float(config.get("max_lease_wait_s", MAX_LEASE_WAIT_S))
        self.overrides = {**HOST_OVERRIDES, **dict(config.get("host_overrides") or {})}
        extra = tuple(config.get("shared_hosts") or ())
        self.patterns = SHARED_HOST_PATTERNS + tuple(str(p) for p in extra)
        self.grants = 0
        self.waits = 0
        self.total_wait_s = 0.0

    # -- state -------------------------------------------------------------
    def _state(self, host: str) -> HostState:
        state = self._hosts.get(host)
        if state is None:
            concurrency, delay = self.overrides.get(
                host, (self.default_concurrency, self.default_delay_s))
            state = HostState(host=host, concurrency=int(concurrency),
                              delay_s=float(delay))
            self._hosts[host] = state
        return state

    def shared(self, host: str) -> bool:
        return is_shared_host(host, self.patterns)

    # -- leases ------------------------------------------------------------
    def acquire(self, host: str, *, community: str = "",
                timeout_s: float | None = None) -> float:
        """Wait until a request to this host may start. Returns seconds waited.

        A negative return means the lease was refused because the wait would
        have been unreasonable; the caller should defer the URL rather than make
        the request. Refusing is better than holding a worker hostage to one
        jammed host while its other fifteen communities have work to do.
        """
        if not host:
            return 0.0
        limit = self.max_wait_s if timeout_s is None else float(timeout_s)
        deadline = time.monotonic() + limit
        waited_from = time.monotonic()
        with self._lock:
            state = self._state(host)
            if community:
                state.communities.add(community)
            while True:
                now = time.monotonic()
                since = now - state.last_started
                free = state.in_flight < state.concurrency
                spaced = since >= state.delay_s
                if free and spaced:
                    state.in_flight += 1
                    state.last_started = now
                    state.requests += 1
                    self.grants += 1
                    waited = now - waited_from
                    if waited > 0.001:
                        self.waits += 1
                        self.total_wait_s += waited
                    return waited
                if now >= deadline:
                    state.deferred += 1
                    return -1.0
                # Wait for whichever comes first: a slot, or the delay expiring.
                wait_for = max(0.01, min(state.delay_s - since if not spaced else 0.05,
                                         deadline - now))
                self._lock.wait(wait_for)

    def release(self, host: str, *, latency_s: float = 0.0, status: int | None = None,
                error: str = "") -> None:
        """Give the slot back, and let the host's own behaviour set the pace."""
        if not host:
            return
        with self._lock:
            state = self._state(host)
            state.in_flight = max(0, state.in_flight - 1)
            state.total_latency_s += max(0.0, float(latency_s))
            if error:
                state.failures += 1
            if status in (429, 503):
                state.rate_limited += 1
                self._tighten(state, "the host asked us to slow down")
            elif status in (403, 401, 451):
                state.blocked += 1
            elif status and 200 <= status < 400 and not error:
                self._relax(state)
            self._lock.notify_all()

    def defer(self, host: str, seconds: float, *, reason: str = "") -> None:
        """A host said Retry-After. Nobody touches it until then (brief §84)."""
        if not host:
            return
        with self._lock:
            state = self._state(host)
            state.last_started = time.monotonic() + max(0.0, float(seconds))
            state.rate_limited += 1
            log.info("[HOST] %s deferred %.0fs — %s", host, seconds,
                     reason or "Retry-After")
            self._lock.notify_all()

    def _tighten(self, state: HostState, why: str) -> None:
        before = (state.concurrency, state.delay_s)
        state.concurrency = max(1, state.concurrency - 1)
        state.delay_s = min(MAX_DELAY_S, max(state.delay_s * 2.0, 2.0))
        if (state.concurrency, state.delay_s) != before:
            log.info("[HOST] %s: %s — now %d in flight, %.1fs apart",
                     state.host, why, state.concurrency, state.delay_s)

    def _relax(self, state: HostState) -> None:
        """Recover slowly. Fast recovery is how a host gets hammered twice."""
        if state.rate_limited == 0:
            return
        if state.requests % 40:
            return
        base_concurrency, base_delay = self.overrides.get(
            state.host, (self.default_concurrency, self.default_delay_s))
        if state.delay_s > base_delay:
            state.delay_s = max(float(base_delay), state.delay_s * 0.8)
        elif state.concurrency < int(base_concurrency):
            state.concurrency += 1

    # -- reporting ---------------------------------------------------------
    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [state.as_dict() for state in
                    sorted(self._hosts.values(), key=lambda s: -s.requests)]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "hosts": len(self._hosts),
                "grants": self.grants,
                "waits": self.waits,
                "mean_wait_s": round(self.total_wait_s / self.waits, 3)
                if self.waits else 0.0,
                "total_wait_s": round(self.total_wait_s, 1),
                "deferred": sum(s.deferred for s in self._hosts.values()),
                "rate_limited": sum(s.rate_limited for s in self._hosts.values()),
                "blocked": sum(s.blocked for s in self._hosts.values()),
            }


class BrokerClient:
    """A worker's view of the broker. Safe when there is no broker at all.

    Everything here is written so that a missing, dead or slow broker degrades
    to "behave as a single community would" rather than to an exception in the
    middle of a crawl.
    """

    def __init__(self, broker: Any = None, *, community: str = "",
                 patterns: Iterable[str] = SHARED_HOST_PATTERNS):
        self._broker = broker
        self.community = community
        self.patterns = tuple(patterns)
        self.leases = 0
        self.waited_s = 0.0
        self.deferrals = 0
        self.broker_failures = 0

    @property
    def available(self) -> bool:
        return self._broker is not None

    def shared(self, host: str) -> bool:
        return is_shared_host(host, self.patterns)

    def acquire(self, url_or_host: str, *, timeout_s: float | None = None) -> bool:
        """True if the request may go ahead; False if it should be deferred."""
        host = url_or_host if "/" not in url_or_host else host_of(url_or_host)
        if not self._broker or not self.shared(host):
            return True
        try:
            waited = self._broker.acquire(host, community=self.community,
                                          timeout_s=timeout_s)
        except Exception as exc:
            # The parent may be shutting down. Proceed politely on our own.
            self.broker_failures += 1
            log.debug("host broker unavailable for %s: %s", host, exc)
            return True
        if waited is None:
            return True
        if waited < 0:
            self.deferrals += 1
            return False
        self.leases += 1
        self.waited_s += float(waited)
        return True

    def release(self, url_or_host: str, *, latency_s: float = 0.0,
                status: int | None = None, error: str = "") -> None:
        host = url_or_host if "/" not in url_or_host else host_of(url_or_host)
        if not self._broker or not self.shared(host):
            return
        try:
            self._broker.release(host, latency_s=latency_s, status=status, error=error)
        except Exception:
            self.broker_failures += 1

    def defer(self, url_or_host: str, seconds: float, *, reason: str = "") -> None:
        host = url_or_host if "/" not in url_or_host else host_of(url_or_host)
        if not self._broker or not self.shared(host):
            return
        try:
            self._broker.defer(host, seconds, reason=reason)
        except Exception:
            self.broker_failures += 1

    def stats(self) -> dict[str, Any]:
        return {
            "broker_available": self.available,
            "leases": self.leases,
            "waited_s": round(self.waited_s, 1),
            "deferrals": self.deferrals,
            "broker_failures": self.broker_failures,
        }


__all__ = ["BrokerClient", "HostBroker", "HostState", "SHARED_HOST_PATTERNS",
           "host_of", "is_shared_host"]
