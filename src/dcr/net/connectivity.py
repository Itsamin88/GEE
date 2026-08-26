"""Connectivity detection: is the machine offline, or is one server down?

The distinction is the whole point (brief §14). A single refusing server is an
ordinary research fact — that source is unreachable, and the report says so. A
laptop with no network is an operational state, and treating it as a research
fact would write NOT FOUND across pages nobody ever opened (brief §13).

The test is therefore never "did this request fail". It is "can I still reach
several independent, unrelated places". Probes go to more than one operator, so
one provider's outage cannot be mistaken for the machine being offline.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable, Mapping, Sequence

import httpx

from ..logging_setup import event, get_logger

log = get_logger("connectivity")

FULL = "FULL"
PARTIAL = "PARTIAL"
OFFLINE = "OFFLINE"
UNKNOWN = "UNKNOWN"

#: Endpoints run by different operators, chosen because they are small,
#: designed to be polled, and unlikely to disappear together. If they are ALL
#: unreachable the machine, not the web, is the thing that is broken.
DEFAULT_PROBES: tuple[str, ...] = (
    "https://www.cloudflare.com/cdn-cgi/trace",
    "https://www.google.com/generate_204",
    "https://duckduckgo.com/",
    "https://www.wikipedia.org/",
)

#: Errors that mean "this machine could not get onto the network at all",
#: as opposed to "that server said no".
_NETWORK_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.NetworkError,
)


@dataclass
class ConnectivityReport:
    status: str = UNKNOWN
    reachable: tuple[str, ...] = ()
    unreachable: tuple[str, ...] = ()
    detail: str = ""
    checked_utc: float = 0.0

    @property
    def online(self) -> bool:
        return self.status in (FULL, PARTIAL)

    @property
    def offline(self) -> bool:
        return self.status == OFFLINE


class ConnectivityMonitor:
    """Answers one question: can this machine reach the open web right now?

    ``probe`` may be replaced in tests with a function that simulates an
    outage; nothing else in the class knows the difference.
    """

    def __init__(
        self,
        *,
        probes: Sequence[str] | None = None,
        timeout_s: float = 8.0,
        min_reachable: int = 1,
        check_interval_s: float = 30.0,
        offline_retry_s: float = 15.0,
        offline_retry_max_s: float = 300.0,
        verify_tls: bool = True,
        user_agent: str = "",
        prober: Callable[[str], Awaitable[bool]] | None = None,
    ):
        self.probes = tuple(probes or DEFAULT_PROBES)
        self.timeout_s = float(timeout_s)
        #: How many probes must answer before the machine counts as online. One
        #: is deliberate: a single reachable endpoint proves the network works.
        self.min_reachable = max(1, int(min_reachable))
        self.check_interval_s = float(check_interval_s)
        self.offline_retry_s = float(offline_retry_s)
        self.offline_retry_max_s = float(offline_retry_max_s)
        self.verify_tls = bool(verify_tls)
        self.user_agent = user_agent
        self._prober = prober
        self._last: ConnectivityReport = ConnectivityReport()
        self._last_check = 0.0
        self.checks = 0

    # -- probing -----------------------------------------------------------
    async def _probe_one(self, url: str) -> bool:
        if self._prober is not None:
            return await self._prober(url)
        headers = {"User-Agent": self.user_agent} if self.user_agent else {}
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_s, verify=self.verify_tls,
                follow_redirects=True, headers=headers,
            ) as client:
                response = await client.get(url)
            # Any answer at all proves the network works, including a 403: the
            # question is whether packets reach a server, not whether that
            # server likes us.
            return response.status_code < 600
        except _NETWORK_ERRORS:
            return False
        except Exception:
            # A TLS or protocol error still means something answered.
            return True

    async def check(self, *, force: bool = False) -> ConnectivityReport:
        """Probe the endpoints and classify the result."""
        now = time.monotonic()
        if not force and self._last.status != UNKNOWN and \
                (now - self._last_check) < self.check_interval_s:
            return self._last
        self._last_check = now
        self.checks += 1

        results = await asyncio.gather(
            *(self._probe_one(url) for url in self.probes), return_exceptions=True
        )
        reachable = tuple(
            url for url, ok in zip(self.probes, results) if ok is True
        )
        unreachable = tuple(url for url in self.probes if url not in reachable)

        if len(reachable) >= self.min_reachable and not unreachable:
            status, detail = FULL, "all connectivity probes answered"
        elif len(reachable) >= self.min_reachable:
            status = PARTIAL
            detail = (f"{len(reachable)} of {len(self.probes)} probes answered; "
                      "the machine is online but some services are not")
        else:
            status = OFFLINE
            detail = (f"none of {len(self.probes)} independent endpoints answered; "
                      "the machine appears to have no internet connection")

        report = ConnectivityReport(
            status=status, reachable=reachable, unreachable=unreachable,
            detail=detail, checked_utc=time.time(),
        )
        if report.status != self._last.status and self._last.status != UNKNOWN:
            log.info("[NETWORK] %s -> %s (%s)", self._last.status, report.status, detail)
        self._last = report
        return report

    @property
    def last(self) -> ConnectivityReport:
        return self._last

    def invalidate(self) -> None:
        """Force the next check to actually probe."""
        self._last_check = 0.0

    # -- waiting -----------------------------------------------------------
    async def wait_for_restoration(
        self,
        *,
        should_stop: Callable[[], bool] | None = None,
        on_attempt: Callable[[int, ConnectivityReport, float], None] | None = None,
        max_wait_s: float | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> ConnectivityReport:
        """Recheck until the network comes back, or until told to stop.

        Backs off gently so a long outage does not spend the battery on probes,
        and never gives up on its own: an outage is not a reason to declare the
        research finished.
        """
        sleeper = sleep or asyncio.sleep
        delay = self.offline_retry_s
        attempt = 0
        started = time.monotonic()
        while True:
            if should_stop is not None and should_stop():
                return self._last
            if max_wait_s is not None and (time.monotonic() - started) >= max_wait_s:
                return self._last
            attempt += 1
            if on_attempt is not None:
                on_attempt(attempt, self._last, delay)
            await sleeper(delay)
            if should_stop is not None and should_stop():
                return self._last
            report = await self.check(force=True)
            if report.online:
                return report
            delay = min(delay * 1.6, self.offline_retry_max_s)

    async def verify_usable(self, *, attempts: int = 2) -> ConnectivityReport:
        """Confirm a restored connection really works before resuming.

        A network interface can come up moments before name resolution does; a
        crawler that trusts the first success burns a batch of URLs on failures
        that look like dead sources (brief §16.2).
        """
        report = await self.check(force=True)
        for _ in range(max(0, attempts - 1)):
            if not report.online:
                return report
            await asyncio.sleep(0)
            report = await self.check(force=True)
        return report


def classify_failures(error_types: Iterable[str], *, minimum: int = 3) -> str:
    """A first opinion on connectivity, drawn from failures already seen.

    Cheap: it costs no requests. Used to decide whether an active probe is
    worth making at all, never to declare the machine offline on its own —
    that decision always costs a real probe.

    ``minimum`` is how many consecutive network-shaped failures count as a
    suspicion. It comes from `run_control.failures_before_probe`, and must be
    honoured rather than second-guessed here: a caller that lowers the
    threshold means it.
    """
    types = [t for t in error_types if t]
    if not types:
        return UNKNOWN
    networkish = {"connection_error", "timeout", "dns_error", "host_unreachable"}
    hits = sum(1 for t in types if t in networkish)
    if hits == len(types) and hits >= max(1, minimum):
        return OFFLINE
    if hits:
        return PARTIAL
    return FULL
