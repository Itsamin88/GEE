"""Fetching, robots, retries and the failure paths."""

from __future__ import annotations

import asyncio

import pytest

from dcr.net.fetcher import Fetcher
from dcr.net.mime import is_html, is_image, sniff
from dcr.net.robots import parse_robots


# -- robots -----------------------------------------------------------------
ROBOTS = """
User-agent: *
Disallow: /wp-admin/
Allow: /wp-admin/admin-ajax.php
Crawl-delay: 4
Sitemap: https://x.org/sitemap.xml

User-agent: DocumentaryResearchCrawler
Disallow: /private/
"""


def test_the_most_specific_group_applies():
    policy = parse_robots(ROBOTS, "x.org", ("documentaryresearchcrawler",))
    assert policy.can_fetch("https://x.org/private/a")[0] is False
    # The wildcard group's rules do not apply once our own group matched.
    assert policy.can_fetch("https://x.org/wp-admin/x")[0] is True
    assert policy.sitemaps == ["https://x.org/sitemap.xml"]


def test_wildcard_group_applies_to_an_unnamed_agent():
    policy = parse_robots(ROBOTS, "x.org", ("someotherbot",))
    assert policy.can_fetch("https://x.org/wp-admin/x")[0] is False
    assert policy.can_fetch("https://x.org/wp-admin/admin-ajax.php")[0] is True
    assert policy.crawl_delay == 4


def test_an_unreachable_robots_file_is_neither_a_ban_nor_a_licence():
    from dcr.net.robots import RobotsPolicy

    policy = RobotsPolicy(host="x.org", status="unreachable")
    allowed, reason = policy.can_fetch("https://x.org/a")
    assert allowed and "unreachable" in reason


def test_robots_and_sitemap_are_always_readable():
    policy = parse_robots("User-agent: *\nDisallow: /", "x.org", ("dcr",))
    assert policy.can_fetch("https://x.org/a")[0] is False
    assert policy.can_fetch("https://x.org/robots.txt",
                            always_allowed=("/robots.txt", "/sitemap.xml"))[0] is True


def test_wildcards_and_end_anchors_are_honoured():
    policy = parse_robots("User-agent: *\nDisallow: /*.pdf$\nDisallow: /tmp/*/x",
                          "x.org", ("dcr",))
    assert policy.can_fetch("https://x.org/a.pdf")[0] is False
    assert policy.can_fetch("https://x.org/a.pdf.html")[0] is True
    assert policy.can_fetch("https://x.org/tmp/1/x")[0] is False


def test_malformed_robots_does_not_raise():
    policy = parse_robots("!!!! not robots\n\n:::", "x.org", ("dcr",))
    assert policy.can_fetch("https://x.org/a")[0] is True


# -- mime -------------------------------------------------------------------
def test_mime_helpers():
    assert is_html("text/html; charset=utf-8")
    assert is_image("image/png")
    assert not is_image("application/pdf")
    assert sniff(b"%PDF-1.7 x") == ("application/pdf", "pdf")


# -- fetching ---------------------------------------------------------------
def _fetch(settings, url, **kwargs):
    async def run():
        async with Fetcher(user_agent=settings.user_agent, config=settings.app) as fetcher:
            return await fetcher.fetch(url, **kwargs)

    return asyncio.run(run())


def test_a_malformed_url_is_recorded_not_raised(settings):
    result = _fetch(settings, "not a url")
    assert not result.ok
    assert result.error_type == "malformed_url"
    assert result.access_status == "dead"


def test_an_unreachable_host_never_raises(settings):
    result = _fetch(settings, "https://this-host-does-not-exist-xyzzy-12345.invalid/")
    assert not result.ok
    assert result.error_type in {"dns_error", "connection_error", "proxy_denied",
                                 "timeout", "unknown_error"}
    assert result.access_status in {"dead", "unreachable"}
    assert result.error_detail


def test_errors_reach_the_sink(settings):
    captured: list[dict] = []

    async def run():
        async with Fetcher(user_agent=settings.user_agent, config=settings.app,
                           error_sink=lambda **kw: captured.append(kw)) as fetcher:
            await fetcher.fetch("https://this-host-does-not-exist-xyzzy-12345.invalid/",
                                community_id="IC001", stage=2)

    asyncio.run(run())
    assert captured and captured[0]["community_id"] == "IC001"
    assert captured[0]["error_type"]


def test_a_dead_host_is_short_circuited_after_repeated_failures(settings):
    """A dead domain must cost a handful of requests, not forty."""
    async def run():
        async with Fetcher(user_agent=settings.user_agent, config=settings.app) as fetcher:
            fetcher.circuit_threshold = 2
            host = "https://this-host-does-not-exist-xyzzy-98765.invalid"
            outcomes = [await fetcher.fetch(f"{host}/p{i}", obey_robots=False) for i in range(5)]
            return outcomes, fetcher

    outcomes, fetcher = asyncio.run(run())
    assert any(o.error_type == "host_unreachable" for o in outcomes)
    assert fetcher.stats["short_circuited"] >= 1
    assert fetcher.unreachable_hosts()


def test_backoff_is_bounded_and_jittered(settings):
    async def run():
        async with Fetcher(user_agent=settings.user_agent, config=settings.app) as fetcher:
            return [fetcher._backoff(n) for n in range(1, 8)]

    delays = asyncio.run(run())
    ceiling = float(settings.app["retry"]["backoff_max_s"])
    assert all(0 < d <= ceiling for d in delays)
    assert delays[0] < delays[3]
