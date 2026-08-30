"""One place that builds a BeautifulSoup, so a missing parser degrades.

`BeautifulSoup(html, "lxml")` raises `FeatureNotFound` when lxml is not
installed. Scattered across four call sites, that turned one missing package
into a run that fetched pages, failed to parse every single one of them, and
finished reporting zero evidence, zero documents and zero images — while the
startup banner said the program "still runs and records what it could not do".

It did not record it. A researcher watching that run had no way to tell an
empty internet from an empty `pip install`.

So parser choice is made here, once, with a fallback to the `html.parser` that
ships with Python. It is slower and slightly more forgiving of broken markup,
which for this work is a fair trade against extracting nothing at all. The
substitution is announced once per process, at WARNING, naming the fix.
"""
from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup

from .logging_setup import get_logger

log = get_logger("soup")

#: Preferred first, then the standard library. lxml is faster and handles
#: real-world malformed HTML better; html.parser needs no C extension and is
#: always present, which is what makes it a usable floor.
_PARSERS = ("lxml", "html.parser")

#: Resolved once, then reused: probing the parser on every page would cost more
#: than the parse.
_chosen: str | None = None
_announced = False


def parser_name() -> str:
    """The best available parser, resolved once per process."""
    global _chosen, _announced
    if _chosen is not None:
        return _chosen
    for candidate in _PARSERS:
        try:
            BeautifulSoup("<html></html>", candidate)
        except Exception:                       # FeatureNotFound, and anything else
            continue
        _chosen = candidate
        if candidate != _PARSERS[0] and not _announced:
            _announced = True
            log.warning(
                "[PARSER] lxml is not installed, so HTML is being parsed with "
                "Python's built-in %s. This works, but it is slower and less "
                "tolerant of broken markup. Install it with: "
                "pip install -r requirements.txt", candidate)
        return _chosen
    # Cannot happen: html.parser is part of the standard library. If it somehow
    # does, failing loudly here is far better than failing silently on every page.
    raise RuntimeError(
        "no usable HTML parser: neither lxml nor Python's html.parser could be "
        "loaded. Run: pip install -r requirements.txt")


def soup(markup: str | bytes, **kwargs: Any) -> BeautifulSoup:
    """Parse markup with the best parser this installation actually has."""
    return BeautifulSoup(markup, parser_name(), **kwargs)


def xml_soup(markup: str | bytes, **kwargs: Any) -> BeautifulSoup:
    """Parse XML - a sitemap or a feed.

    lxml-xml keeps namespaced tags intact, which matters for sitemap indexes.
    Without lxml there is no XML parser, so this falls back to the HTML one:
    sitemap tags are simple enough that it still finds the <loc> elements.
    """
    for candidate in ("lxml-xml", "xml"):
        try:
            return BeautifulSoup(markup, candidate, **kwargs)
        except Exception:
            continue
    return soup(markup, **kwargs)
