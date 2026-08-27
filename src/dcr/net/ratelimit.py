"""Per-host politeness: bounded concurrency, a delay between requests, and
deferral when a server says it has had enough."""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field


@dataclass
class HostState:
    delay: float
    last_request: float = 0.0
    deferred_until: float = 0.0
    consecutive_429: int = 0
    semaphore: asyncio.Semaphore | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class RateLimiter:
    """Politeness governor shared by every fetch."""

    def __init__(
        self,
        *,
        default_delay: float = 1.5,
        max_delay: float = 30.0,
        per_host_concurrency: int = 2,
        global_concurrency: int = 8,
    ):
        self.default_delay = default_delay
        self.max_delay = max_delay
        self.per_host_concurrency = per_host_concurrency
        self._global = asyncio.Semaphore(global_concurrency)
        self._hosts: dict[str, HostState] = {}
        self._registry_lock = asyncio.Lock()

    async def _state(self, host: str) -> HostState:
        async with self._registry_lock:
            state = self._hosts.get(host)
            if state is None:
                state = HostState(delay=self.default_delay,
                                  semaphore=asyncio.Semaphore(self.per_host_concurrency))
                self._hosts[host] = state
            return state

    def set_delay(self, host: str, delay: float) -> None:
        """Apply a robots crawl-delay. It may slow us down, never speed us up."""
        state = self._hosts.get(host)
        target = min(max(delay, self.default_delay), self.max_delay)
        if state is None:
            self._hosts[host] = HostState(delay=target,
                                          semaphore=asyncio.Semaphore(self.per_host_concurrency))
        else:
            state.delay = max(state.delay, target)

    def defer(self, host: str, seconds: float) -> None:
        state = self._hosts.get(host)
        if state is None:
            state = HostState(delay=self.default_delay,
                              semaphore=asyncio.Semaphore(self.per_host_concurrency))
            self._hosts[host] = state
        state.deferred_until = max(state.deferred_until, time.monotonic() + seconds)

    def deferral_remaining(self, host: str) -> float:
        state = self._hosts.get(host)
        if not state:
            return 0.0
        return max(0.0, state.deferred_until - time.monotonic())

    def note_429(self, host: str) -> int:
        state = self._hosts.get(host)
        if state is None:
            return 1
        state.consecutive_429 += 1
        # Back off this host for everyone, not just this request.
        state.delay = min(state.delay * 2, self.max_delay)
        return state.consecutive_429

    def note_ok(self, host: str) -> None:
        state = self._hosts.get(host)
        if state:
            state.consecutive_429 = 0

    class _Slot:
        def __init__(self, limiter: "RateLimiter", host: str):
            self.limiter = limiter
            self.host = host
            self.state: HostState | None = None

        async def __aenter__(self) -> None:
            self.state = await self.limiter._state(self.host)
            await self.limiter._global.acquire()
            assert self.state.semaphore is not None
            await self.state.semaphore.acquire()
            async with self.state.lock:
                wait = self.state.deferred_until - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                gap = self.state.delay - (time.monotonic() - self.state.last_request)
                if gap > 0:
                    await asyncio.sleep(gap + random.uniform(0, 0.3))
                self.state.last_request = time.monotonic()

        async def __aexit__(self, *exc: object) -> None:
            assert self.state is not None and self.state.semaphore is not None
            self.state.semaphore.release()
            self.limiter._global.release()

    def slot(self, host: str) -> "_Slot":
        return RateLimiter._Slot(self, host)
