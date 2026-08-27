"""The resilient fetch layer.

The web is assumed unreliable (brief §36). Every failure is caught, classified
and recorded as a structured error; nothing here may abort a run. Retries are
exponential with jitter for transient failures only, and permanent failures are
recorded once and never retried.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import urlsplit

import httpx

from .. import profiling
from ..logging_setup import get_logger
from .mime import sniff
from .ratelimit import RateLimiter
from .robots import RobotsPolicy, parse_robots

log = get_logger("net")


@dataclass
class FetchResult:
    """Everything a single fetch attempt learned, success or failure."""

    url: str
    final_url: str | None = None
    status: int | None = None
    ok: bool = False
    content: bytes | None = None
    text: str | None = None
    encoding: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    mime: str | None = None
    extension: str | None = None
    bytes_len: int = 0
    elapsed_s: float = 0.0
    attempts: int = 0
    error_type: str | None = None
    error_detail: str | None = None
    access_status: str = "not_attempted"
    truncated: bool = False
    from_cache: bool = False
    fetched_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    redirect_chain: list[str] = field(default_factory=list)

    @property
    def is_permanent_failure(self) -> bool:
        return self.access_status in {"blocked", "dead", "login_required", "robots_denied", "too_large"}


# HTTP status -> access status recorded on the source.
_STATUS_ACCESS = {
    401: "login_required",
    402: "blocked",
    403: "blocked",
    404: "dead",
    410: "dead",
    451: "blocked",
}


class Fetcher:
    """One shared HTTP client with robots, politeness and retry built in."""

    def __init__(
        self,
        *,
        user_agent: str,
        config: Mapping[str, Any],
        error_sink: Any = None,
        supervisor: Any = None,
        host_broker: Any = None,
    ):
        net = config.get("network", {})
        self.retry_cfg = config.get("retry", {})
        self.robots_cfg = config.get("robots", {})
        self.user_agent = user_agent
        self.error_sink = error_sink
        # Told about every result, so it can tell the difference between one
        # dead server and a laptop with no network (brief §14).
        self.supervisor = supervisor
        #: Per-host politeness ACROSS communities. Only consulted for the
        #: handful of hosts every community reaches — the web archive, the
        #: academic indexes, the search endpoints — because paying an
        #: inter-process round trip for a host nobody else is touching would be
        #: pure overhead. None when this is a single-community run, and every
        #: path below works without it (brief §4, §40).
        self.host_broker = host_broker
        self.max_page_bytes = int(net.get("max_page_bytes", 12_000_000))
        self.max_document_bytes = int(net.get("max_document_bytes", 120_000_000))
        self.max_image_bytes = int(net.get("max_image_bytes", 25_000_000))
        self.limiter = RateLimiter(
            default_delay=float(net.get("default_delay_per_host_s", 1.5)),
            max_delay=float(net.get("max_delay_per_host_s", 30.0)),
            per_host_concurrency=int(net.get("max_concurrency_per_host", 2)),
            global_concurrency=int(net.get("max_concurrency_global", 8)),
        )
        timeout = httpx.Timeout(
            connect=float(net.get("timeout_connect_s", 15)),
            read=float(net.get("timeout_read_s", 45)),
            write=float(net.get("timeout_read_s", 45)),
            pool=float(net.get("timeout_total_s", 120)),
        )
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            max_redirects=int(net.get("max_redirects", 8)),
            verify=bool(net.get("verify_tls", True)),
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                          "application/pdf;q=0.9,*/*;q=0.7",
                "Accept-Language": "en;q=0.9,*;q=0.5",
            },
            limits=httpx.Limits(
                max_connections=int(net.get("max_concurrency_global", 8)) * 2,
                max_keepalive_connections=int(net.get("max_concurrency_global", 8)),
            ),
        )
        # Once a host has refused connection several times in a row there is no
        # point probing forty well-known paths on it: the run stalls and the
        # errors all say the same thing. The breaker records the fact once and
        # short-circuits the rest.
        self.circuit_threshold = int(self.retry_cfg.get("host_failure_threshold", 5))
        self._host_failures: dict[str, int] = {}
        self._open_circuits: dict[str, str] = {}
        self._robots: dict[str, RobotsPolicy] = {}
        self._robots_locks: dict[str, asyncio.Lock] = {}
        self._registry_lock = asyncio.Lock()
        self.stats = {"requests": 0, "ok": 0, "failed": 0, "robots_denied": 0, "bytes": 0,
                      "short_circuited": 0}

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "Fetcher":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # -- robots ------------------------------------------------------------
    async def robots_for(self, url: str) -> RobotsPolicy:
        host = (urlsplit(url).hostname or "").lower()
        if host in self._robots:
            return self._robots[host]
        async with self._registry_lock:
            lock = self._robots_locks.setdefault(host, asyncio.Lock())
        async with lock:
            if host in self._robots:
                return self._robots[host]
            scheme = urlsplit(url).scheme or "https"
            robots_url = f"{scheme}://{urlsplit(url).netloc}/robots.txt"
            policy = RobotsPolicy(host=host)
            try:
                async with self.limiter.slot(host):
                    response = await self._client.get(robots_url)
                if response.status_code == 200 and response.text.strip():
                    policy = parse_robots(response.text, host, (self.user_agent.split("/")[0],))
                elif response.status_code in (401, 403):
                    # A protected robots.txt is not a licence, but it is also not
                    # a rule we can read. Record it and stay polite.
                    policy.status = "unreachable"
                else:
                    policy.status = "missing"
            except Exception as exc:  # network failure reading robots
                policy.status = "unreachable"
                policy.raw = f"{type(exc).__name__}: {exc}"
            if policy.crawl_delay:
                self.limiter.set_delay(host, policy.crawl_delay)
            self._robots[host] = policy
            return policy

    # -- fetching ----------------------------------------------------------
    async def fetch(self, url: str, **kwargs: Any) -> FetchResult:
        """Fetch one URL, and tell the supervisor how it went.

        Every network request in the program comes through here, so this is the
        one place that has to notice the difference between "that server said
        no" and "this machine is not on the internet".
        """
        started = time.monotonic()
        try:
            result = await self._fetch(url, **kwargs)
        finally:
            profiling.add("http", time.monotonic() - started)
        supervisor = self.supervisor
        if supervisor is not None:
            if result.ok:
                supervisor.note_success()
            else:
                supervisor.note_failure(result.error_type)
        return result

    async def _fetch(
        self,
        url: str,
        *,
        kind: str = "page",
        method: str = "GET",
        headers: Mapping[str, str] | None = None,
        obey_robots: bool | None = None,
        max_bytes: int | None = None,
        community_id: str | None = None,
        source_id: str | None = None,
        stage: int | None = None,
    ) -> FetchResult:
        """Fetch one URL. Never raises: a failure comes back as a FetchResult."""
        result = FetchResult(url=url)
        host = (urlsplit(url).hostname or "").lower()
        if not host:
            result.error_type = "malformed_url"
            result.error_detail = "no host in URL"
            result.access_status = "dead"
            self._record_error(result, community_id, source_id, stage)
            return result

        circuit_reason = self._open_circuits.get(host)
        if circuit_reason:
            self.stats["short_circuited"] += 1
            result.error_type = "host_unreachable"
            result.error_detail = circuit_reason
            result.access_status = "unreachable"
            self._record_error(result, community_id, source_id, stage,
                               unresolved=True, resolution="skipped")
            return result

        obey = self.robots_cfg.get("obey", True) if obey_robots is None else obey_robots
        if obey:
            policy = await self.robots_for(url)
            allowed, reason = policy.can_fetch(
                url, always_allowed=tuple(self.robots_cfg.get("always_allowed_paths", []))
            )
            if not allowed:
                self.stats["robots_denied"] += 1
                result.error_type = "robots_denied"
                result.error_detail = reason
                result.access_status = "robots_denied"
                self._record_error(result, community_id, source_id, stage, unresolved=False,
                                   resolution="skipped")
                return result

        cap = max_bytes or {
            "page": self.max_page_bytes,
            "document": self.max_document_bytes,
            "image": self.max_image_bytes,
        }.get(kind, self.max_page_bytes)

        attempts_allowed = int(self.retry_cfg.get("max_attempts", 4))
        retryable = set(self.retry_cfg.get("retryable_statuses", []))
        permanent = set(self.retry_cfg.get("permanent_statuses", []))

        # A host every community reaches is spaced out across the whole run, not
        # just within this community. Refused means the queue for that host is
        # too long to be worth holding a worker for: the URL is deferred and
        # this community gets on with its other work (brief §40).
        if not await self._enter_shared_host(host):
            result.error_type = "host_deferred"
            result.error_detail = (
                f"{host} is busy with other communities in this run; deferred "
                "rather than queued behind them")
            result.access_status = "deferred"
            self._record_error(result, community_id, source_id, stage,
                               unresolved=True, resolution="deferred")
            return result

        try:
            for attempt in range(1, attempts_allowed + 1):
              result.attempts = attempt
              started = asyncio.get_event_loop().time()
              try:
                  async with self.limiter.slot(host):
                      self.stats["requests"] += 1
                      request = self._client.build_request(
                          method, url, headers=dict(headers or {})
                      )
                      response = await self._client.send(request, stream=True)
                      try:
                          result.status = response.status_code
                          result.final_url = str(response.url)
                          result.headers = {k.lower(): v for k, v in response.headers.items()}
                          result.redirect_chain = [str(r.url) for r in response.history]

                          declared_length = result.headers.get("content-length")
                          if declared_length and declared_length.isdigit() and int(declared_length) > cap:
                              result.error_type = "too_large"
                              result.error_detail = f"{declared_length} bytes exceeds the {cap} byte cap"
                              result.access_status = "too_large"
                              await response.aclose()
                              self._record_error(result, community_id, source_id, stage,
                                                 unresolved=False, resolution="skipped")
                              return result

                          chunks: list[bytes] = []
                          total = 0
                          async for chunk in response.aiter_bytes():
                              chunks.append(chunk)
                              total += len(chunk)
                              if total > cap:
                                  result.truncated = True
                                  break
                          body = b"".join(chunks)[:cap]
                      finally:
                          await response.aclose()

                  result.elapsed_s = asyncio.get_event_loop().time() - started
                  result.content = body
                  result.bytes_len = len(body)
                  self.stats["bytes"] += len(body)

                  if response.status_code == 429:
                      count = self.limiter.note_429(host)
                      delay = self._retry_after(result.headers) or self._backoff(attempt)
                      cap_s = float(self.retry_cfg.get("respect_retry_after_max_s", 300))
                      self.limiter.defer(host, min(delay, cap_s))
                      if attempt >= attempts_allowed or count >= 3:
                          result.error_type = "rate_limited"
                          result.error_detail = f"429 after {attempt} attempts; host deferred"
                          result.access_status = "blocked"
                          self._record_error(result, community_id, source_id, stage)
                          return result
                      continue

                  if response.status_code in permanent:
                      result.error_type = f"http_{response.status_code}"
                      result.error_detail = self._detect_wall(body, response.status_code)
                      result.access_status = _STATUS_ACCESS.get(response.status_code, "blocked")
                      self.stats["failed"] += 1
                      self._record_error(result, community_id, source_id, stage,
                                         unresolved=False, resolution="permanent")
                      return result

                  if response.status_code in retryable and attempt < attempts_allowed:
                      await asyncio.sleep(self._backoff(attempt))
                      continue

                  if response.status_code >= 400:
                      result.error_type = f"http_{response.status_code}"
                      result.error_detail = f"HTTP {response.status_code} after {attempt} attempts"
                      result.access_status = "blocked" if response.status_code < 500 else "unreachable"
                      self.stats["failed"] += 1
                      self._record_error(result, community_id, source_id, stage)
                      return result

                  # Success.
                  self._host_failures.pop(host, None)
                  self.limiter.note_ok(host)
                  self.stats["ok"] += 1
                  result.ok = True
                  result.access_status = "ok"
                  mime, ext = sniff(body, result.headers.get("content-type"), url.rsplit("/", 1)[-1])
                  result.mime = mime
                  result.extension = ext
                  if mime.startswith("text/") or mime in {
                      "application/xml", "application/json", "application/rss+xml",
                      "application/atom+xml", "application/xhtml+xml", "image/svg+xml",
                  }:
                      result.encoding = response.encoding or "utf-8"
                      result.text = _decode(body, result.encoding)
                  return result

              except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as exc:
                  result.error_type = "timeout"
                  result.error_detail = f"{type(exc).__name__}: {exc}"
              except httpx.TooManyRedirects as exc:
                  result.error_type = "redirect_loop"
                  result.error_detail = str(exc)
                  result.access_status = "dead"
                  self._record_error(result, community_id, source_id, stage,
                                     unresolved=False, resolution="permanent")
                  return result
              except httpx.ProxyError as exc:
                  self._note_host_failure(host, "the outbound proxy refused the connection")
                  # An outbound proxy refusing CONNECT is an environment policy
                  # decision, not a property of the target. Retrying cannot help
                  # and would hide the real cause behind four timeouts.
                  result.error_type = "proxy_denied"
                  result.error_detail = f"{type(exc).__name__}: {exc}"
                  result.access_status = "unreachable"
                  self._record_error(result, community_id, source_id, stage,
                                     unresolved=True, resolution="permanent")
                  self.stats["failed"] += 1
                  return result
              except (httpx.ConnectError, httpx.NetworkError) as exc:
                  text = str(exc).lower()
                  if any(marker in text for marker in (
                      "name or service not known", "nodename nor servname",
                      "temporary failure in name resolution", "getaddrinfo",
                      "no address associated", "name does not resolve",
                  )):
                      result.error_type = "dns_error"
                      result.access_status = "dead"
                  else:
                      result.error_type = "connection_error"
                  result.error_detail = f"{type(exc).__name__}: {exc}"
                  self._note_host_failure(host, f"{result.error_type}: {exc}")
              except (httpx.ProtocolError, httpx.RemoteProtocolError) as exc:
                  result.error_type = "protocol_error"
                  result.error_detail = f"{type(exc).__name__}: {exc}"
              except Exception as exc:  # anything else, including TLS problems
                  name = type(exc).__name__
                  result.error_type = ("tls_error" if "SSL" in name or "Certificate" in name
                                       else "unknown_error")
                  result.error_detail = f"{name}: {exc}"
                  self._note_host_failure(host, f"{result.error_type}: {exc}")

              if result.error_type == "dns_error" or attempt >= attempts_allowed:
                  break
              await asyncio.sleep(self._backoff(attempt))
        finally:
            self._leave_shared_host(host, result)

        self.stats["failed"] += 1
        if result.access_status == "not_attempted":
            result.access_status = "unreachable"
        self._record_error(result, community_id, source_id, stage)
        return result

    # -- run-wide host politeness ------------------------------------------
    async def _enter_shared_host(self, host: str) -> bool:
        """Ask the run for permission to touch a host every community wants.

        The broker call is synchronous — it crosses a process boundary — so it
        goes to a thread rather than blocking this community's event loop while
        it waits. False means defer: the queue for that host is long enough that
        holding a worker for it costs more than the request is worth.
        """
        broker = self.host_broker
        if broker is None or not host:
            return True
        try:
            if not broker.shared(host):
                return True
            return bool(await asyncio.to_thread(broker.acquire, host))
        except Exception:
            # A coordinator that has gone away must not stop the research: fall
            # back to this community's own politeness, which is what a single
            # run would have done anyway.
            return True

    def _leave_shared_host(self, host: str, result: Any) -> None:
        broker = self.host_broker
        if broker is None or not host:
            return
        try:
            if not broker.shared(host):
                return
            broker.release(host, latency_s=getattr(result, "elapsed_s", 0.0) or 0.0,
                           status=getattr(result, "status", None),
                           error=getattr(result, "error_type", "") or "")
        except Exception:
            pass

    # -- helpers -----------------------------------------------------------
    def _note_host_failure(self, host: str, reason: str) -> None:
        if self.offline:
            # The machine has no network. Every host looks dead from here, and
            # recording them as unreachable would turn an outage into a page of
            # research findings (brief §13). The failure is not counted at all:
            # when the connection returns, these hosts get a fair attempt.
            return
        count = self._host_failures.get(host, 0) + 1
        self._host_failures[host] = count
        if count >= self.circuit_threshold and host not in self._open_circuits:
            self._open_circuits[host] = (
                f"{host} failed {count} times in a row ({reason}); further requests to this "
                "host are recorded as unreachable without being attempted"
            )
            log.info("[UNREACHABLE] %s", self._open_circuits[host],
                     extra={"dcr_tag": "UNREACHABLE", "dcr_host": host})

    def unreachable_hosts(self) -> dict[str, str]:
        return dict(self._open_circuits)

    @property
    def offline(self) -> bool:
        """Is the machine, rather than one server, the thing that is unreachable?"""
        supervisor = self.supervisor
        if supervisor is None:
            return False
        control = getattr(supervisor, "control", None)
        if control is None:
            return False
        return getattr(control, "connectivity", "") == "OFFLINE" or bool(
            getattr(supervisor, "suspended", False))

    def reset_host_failures(self, host: str | None = None) -> int:
        """Give hosts another chance after the network comes back.

        A circuit opened during an outage says nothing about the host, so it
        must not outlive the outage (brief §16.6).
        """
        if host is not None:
            self._host_failures.pop(host, None)
            return int(self._open_circuits.pop(host, None) is not None)
        cleared = len(self._open_circuits)
        self._host_failures.clear()
        self._open_circuits.clear()
        return cleared

    def _backoff(self, attempt: int) -> float:
        base = float(self.retry_cfg.get("backoff_base_s", 2.0))
        factor = float(self.retry_cfg.get("backoff_factor", 2.0))
        jitter = float(self.retry_cfg.get("backoff_jitter_s", 1.0))
        ceiling = float(self.retry_cfg.get("backoff_max_s", 60.0))
        return min(base * (factor ** (attempt - 1)) + random.uniform(0, jitter), ceiling)

    @staticmethod
    def _retry_after(headers: Mapping[str, str]) -> float | None:
        raw = headers.get("retry-after")
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    @staticmethod
    def _detect_wall(body: bytes, status: int) -> str:
        """Name the wall so 'blocked' is auditable rather than a bare code."""
        sample = body[:8000].decode("utf-8", "ignore").lower()
        markers = (
            ("cloudflare", "Cloudflare bot protection"),
            ("just a moment", "Cloudflare interstitial"),
            ("captcha", "CAPTCHA challenge"),
            ("log in to continue", "login wall"),
            ("sign up to see", "login wall"),
            ("please log in", "login wall"),
            ("access denied", "access denied page"),
            ("subscribe to read", "paywall"),
            ("this content isn't available", "platform restriction"),
        )
        for needle, label in markers:
            if needle in sample:
                return f"HTTP {status}: {label}"
        return f"HTTP {status}"

    def _record_error(
        self,
        result: FetchResult,
        community_id: str | None,
        source_id: str | None,
        stage: int | None,
        *,
        unresolved: bool = True,
        resolution: str | None = None,
    ) -> None:
        log.debug(
            "fetch failed: %s (%s)", result.url, result.error_type,
            extra={"dcr_tag": "FETCH", "dcr_url": result.url, "dcr_error": result.error_type},
        )
        if self.error_sink is None:
            return
        try:
            self.error_sink(
                community_id=community_id,
                source_id=source_id,
                stage=stage,
                url=result.url,
                error_type=result.error_type or "unknown_error",
                http_status=result.status,
                retry_count=result.attempts,
                detail=result.error_detail,
                unresolved=unresolved,
                resolution=resolution,
            )
        except Exception:  # an error while recording an error must not propagate
            log.debug("error sink failed for %s", result.url, exc_info=True)


def _decode(body: bytes, encoding: str | None) -> str:
    for candidate in (encoding, "utf-8", "latin-1"):
        if not candidate:
            continue
        try:
            return body.decode(candidate)
        except (UnicodeDecodeError, LookupError):
            continue
    return body.decode("utf-8", "replace")
