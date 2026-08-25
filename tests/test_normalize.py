"""URL normalisation, scope and trap detection."""

from __future__ import annotations

import pytest

from dcr.crawl.normalize import (
    TrapDetector, classify_url, normalize, registrable_domain, same_site,
)


@pytest.mark.parametrize("raw, expected", [
    ("HTTP://WWW.Example.COM:80/a//b/?utm_source=x&page=2#frag", "http://example.com/a/b?page=2"),
    ("https://example.com/", "https://example.com/"),
    ("https://example.com/path/", "https://example.com/path"),
    ("https://example.com/file.html/", "https://example.com/file.html"),
    ("https://Example.com:443/x", "https://example.com/x"),
    ("https://example.com:8443/x", "https://example.com:8443/x"),
])
def test_normalize_canonical_forms(raw, expected):
    assert normalize(raw) == expected


@pytest.mark.parametrize("raw", [
    "", "  ", "mailto:a@b.c", "javascript:void(0)", "tel:+33", "#anchor",
    "data:text/html,x", "ftp://example.com/x", "not a url",
])
def test_normalize_rejects_unfetchable(raw):
    assert normalize(raw) is None


def test_normalize_resolves_relative_against_base():
    assert normalize("/about", "https://x.org/blog/post") == "https://x.org/about"
    assert normalize("../a", "https://x.org/b/c/d") == "https://x.org/b/a"


@pytest.mark.parametrize("raw", [
    "https://web.archive.org/web/20160901000000id_/http://pourgues.org/histoire",
    "https://web.archive.org/web/20160901000000id_/http://pourgues.org/",
    "http://archive.test:8080/web/20161201000000/http://x.test/docs/a.pdf",
])
def test_normalize_preserves_embedded_archive_url(raw):
    """A Wayback URL contains a whole second URL; altering it yields a 404."""
    assert normalize(raw) == raw


def test_normalize_strips_tracking_but_keeps_meaning():
    assert normalize("https://x.org/a?utm_medium=e&id=7&fbclid=z") == "https://x.org/a?id=7"


def test_normalize_is_idempotent():
    once = normalize("HTTP://WWW.X.ORG:80/a//b/?b=2&a=1")
    assert normalize(once) == once


@pytest.mark.parametrize("host, expected", [
    ("https://blog.news.co.uk/x", "news.co.uk"),
    ("https://a.b.pourgues.org", "pourgues.org"),
    ("example.com", "example.com"),
    ("https://www.example.com", "example.com"),
])
def test_registrable_domain(host, expected):
    assert registrable_domain(host) == expected


def test_same_site():
    assert same_site("https://a.x.org/1", "https://b.x.org/2")
    assert not same_site("https://x.org", "https://y.org")


@pytest.mark.parametrize("url, kind", [
    ("https://x.org/report.PDF", "document"),
    ("https://x.org/a.jpg", "image"),
    ("https://x.org/a.css", "skip"),
    ("https://x.org/about", "page"),
    ("https://x.org/data.xlsx", "document"),
])
def test_classify_url(url, kind):
    assert classify_url(url) == kind


def test_trap_detector_catches_infinite_shapes():
    detector = TrapDetector()
    assert detector.check("https://x.org/calendar/2020/01/01")
    assert detector.check("https://x.org/a/b/c/d/e/f/g/h/i/j/k/l/m/n")
    assert detector.check("https://x.org/x?a=1&b=2&c=3&d=4&e=5&f=6&g=7")
    assert detector.check("https://x.org/about") is None


def test_trap_detector_limits_query_variants_of_one_path():
    detector = TrapDetector(max_same_path_variants=3)
    results = [detector.check(f"https://x.org/search?q={i}") for i in range(6)]
    assert results[-1] is not None
