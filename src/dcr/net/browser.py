"""Optional browser rendering for JavaScript-only pages.

A browser is expensive, so it is used only where static HTML demonstrably does
not carry the content (brief §10). If Playwright is not installed the crawler
records ``js_required`` on the page and carries on with HTTP extraction — it
never pretends to have read a page it could not render (brief §78).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from ..logging_setup import get_logger

log = get_logger("browser")

# Markers that a static response is a shell waiting for JavaScript.
JS_SHELL_MARKERS = (
    "you need to enable javascript",
    "please enable javascript",
    "<noscript>",
    "id=\"root\"></div>",
    "id=\"app\"></div>",
    "__next_data__",
    "window.__nuxt__",
    "ng-version",
    "data-reactroot",
)


@dataclass
class RenderResult:
    ok: bool
    html: str | None = None
    final_url: str | None = None
    status: int | None = None
    error: str | None = None
    reason: str = ""


def looks_javascript_rendered(html: str | None, min_text_chars: int) -> tuple[bool, str]:
    """Decide whether a page is worth escalating to a browser."""
    if html is None:
        return False, "no html"
    lowered = html.lower()
    text_only = _strip_tags(lowered)
    if len(text_only) < min_text_chars:
        for marker in JS_SHELL_MARKERS:
            if marker in lowered:
                return True, f"thin body plus {marker!r}"
        if len(text_only) < min_text_chars // 3 and "<script" in lowered:
            return True, f"only {len(text_only)} characters of text with scripts present"
    return False, "static html carries the content"


def _strip_tags(html: str) -> str:
    out: list[str] = []
    depth = 0
    skip = False
    i = 0
    while i < len(html):
        if html.startswith(("<script", "<style"), i):
            skip = True
        if html[i] == "<":
            depth += 1
        elif html[i] == ">":
            if depth:
                depth -= 1
            if skip and html[max(0, i - 9):i + 1].endswith(("/script>", "/style>")):
                skip = False
        elif depth == 0 and not skip:
            out.append(html[i])
        i += 1
    return "".join(out).strip()


class BrowserPool:
    """A small pool of browser pages. Absent Playwright, it reports unavailable."""

    def __init__(self, *, enabled: bool = True, pool_size: int = 2, timeout_s: float = 45.0,
                 user_agent: str | None = None, channel: str | None = None):
        self.requested = enabled
        #: Force a particular installed browser, e.g. "chrome" or "msedge".
        #: Empty means: try Playwright's own build first, then what is installed.
        self.channel = (channel or "").strip()
        self.pool_size = max(1, pool_size)
        self.timeout_ms = int(timeout_s * 1000)
        self.user_agent = user_agent
        self.available = False
        self.unavailable_reason = "not started"
        self._playwright: Any = None
        self._browser: Any = None
        self._semaphore: asyncio.Semaphore | None = None
        self.pages_rendered = 0

    async def start(self) -> None:
        if not self.requested:
            self.unavailable_reason = "disabled in configuration"
            return
        try:
            from playwright.async_api import async_playwright  # type: ignore
        except ImportError:
            self.unavailable_reason = "playwright is not installed"
            log.info("[BROWSER] unavailable: %s — HTTP-only extraction", self.unavailable_reason)
            return
        args = ["--no-sandbox", "--disable-dev-shm-usage"]
        # `playwright install` downloads a private Chromium from a Google CDN
        # that refuses connections from some countries outright - a researcher in
        # Iran gets "this service is not available in your location". That is a
        # geography problem, not a configuration one, and it should not cost the
        # whole browser feature when the machine already has Chrome or Edge.
        #
        # So: the downloaded build first, then the browsers Windows and macOS
        # ship with anyway. `channel` tells Playwright to drive an installed
        # browser rather than its own.
        attempts: list[tuple[str, dict]] = [
            ("bundled chromium", {}),
            ("installed Chrome", {"channel": "chrome"}),
            ("installed Edge", {"channel": "msedge"}),
        ]
        configured = self.channel
        if configured:
            attempts.insert(0, (f"configured channel {configured!r}",
                                {"channel": configured}))

        failures: list[str] = []
        try:
            self._playwright = await async_playwright().start()
        except Exception as exc:
            self.unavailable_reason = f"{type(exc).__name__}: {exc}"
            log.info("[BROWSER] unavailable: %s — HTTP-only extraction",
                     self.unavailable_reason)
            return

        for label, options in attempts:
            try:
                self._browser = await self._playwright.chromium.launch(
                    args=args, **options)
            except Exception as exc:
                failures.append(f"{label}: {type(exc).__name__}")
                continue
            self._semaphore = asyncio.Semaphore(self.pool_size)
            self.available = True
            self.unavailable_reason = ""
            log.info("[BROWSER] %s ready (pool of %d)", label, self.pool_size)
            if label != "bundled chromium":
                log.warning(
                    "[BROWSER] using %s because Playwright's own build is not "
                    "present. This is fine. If you want the bundled one, "
                    "`playwright install` must be able to reach "
                    "cdn.playwright.dev.", label)
            return

        self.unavailable_reason = (
            "no usable Chromium: " + "; ".join(failures)
            + ". Install one with `playwright install`, or install Google Chrome "
              "or Microsoft Edge and it will be used automatically")
        log.info("[BROWSER] unavailable: %s — HTTP-only extraction",
                 self.unavailable_reason)

    async def close(self) -> None:
        try:
            if self._browser is not None:
                await self._browser.close()
            if self._playwright is not None:
                await self._playwright.stop()
        except Exception:  # pragma: no cover
            log.debug("browser shutdown failed", exc_info=True)
        finally:
            self.available = False

    async def render(self, url: str, *, wait_selector: str | None = None) -> RenderResult:
        if not self.available or self._browser is None or self._semaphore is None:
            return RenderResult(False, error=self.unavailable_reason or "browser unavailable",
                                reason="unavailable")
        async with self._semaphore:
            context = None
            try:
                context = await self._browser.new_context(
                    user_agent=self.user_agent,
                    ignore_https_errors=False,
                    java_script_enabled=True,
                )
                page = await context.new_page()
                response = await page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded")
                if wait_selector:
                    try:
                        await page.wait_for_selector(wait_selector, timeout=8000)
                    except Exception:
                        pass
                try:
                    await page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                html = await page.content()
                self.pages_rendered += 1
                return RenderResult(
                    True, html=html, final_url=page.url,
                    status=response.status if response else None, reason="rendered",
                )
            except Exception as exc:
                return RenderResult(False, error=f"{type(exc).__name__}: {exc}", reason="render failed")
            finally:
                if context is not None:
                    try:
                        await context.close()
                    except Exception:
                        pass
