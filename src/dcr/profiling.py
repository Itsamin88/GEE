"""Where the time actually goes.

The reported run took hours and nobody could say which part of it was
responsible. Guessing is how a crawler gets "optimised" by lowering a timeout
that was never the problem, so this measures instead (brief §49).

Costs are recorded per activity — HTTP, PDF parsing, table extraction, image
work, archive queries, reconciliation, export — and reported as both seconds and
a share of the whole. The overhead is one monotonic clock read per timed block,
which is nothing beside the work being timed.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

#: The activities worth telling apart. Anything else lands in "other".
ACTIVITIES = (
    "http",              # time inside network requests
    "html_parse",
    "pdf_parse",
    "office_parse",
    "table_extract",
    "image_classify",
    "image_download",
    "image_extract",     # pulling figures out of documents
    "text_mining",       # deterministic extraction of evidence and claims
    "llm",
    "archive_query",
    "sitemap",
    "search",
    "reconcile",
    "export",
    "other",
)


@dataclass
class Profile:
    """Cumulative time and call counts per activity."""

    seconds: dict[str, float] = field(default_factory=dict)
    calls: dict[str, int] = field(default_factory=dict)
    started: float = field(default_factory=time.monotonic)

    def add(self, activity: str, seconds: float) -> None:
        key = activity if activity in ACTIVITIES else "other"
        self.seconds[key] = self.seconds.get(key, 0.0) + max(0.0, seconds)
        self.calls[key] = self.calls.get(key, 0) + 1

    @contextmanager
    def timing(self, activity: str) -> Iterator[None]:
        start = time.monotonic()
        try:
            yield
        finally:
            self.add(activity, time.monotonic() - start)

    @property
    def total_s(self) -> float:
        return sum(self.seconds.values())

    def report(self) -> dict[str, Any]:
        """Seconds and percentages, biggest first."""
        total = self.total_s or 1.0
        ordered = sorted(self.seconds.items(), key=lambda kv: -kv[1])
        return {
            "measured_s": round(self.total_s, 1),
            "wall_s": round(time.monotonic() - self.started, 1),
            "by_activity_s": {k: round(v, 2) for k, v in ordered},
            "by_activity_pct": {k: round(100.0 * v / total, 1) for k, v in ordered},
            "calls": dict(self.calls),
        }

    def lines(self, *, limit: int = 8) -> list[str]:
        """The report as a person would read it."""
        report = self.report()
        out = [f"Measured {report['measured_s']:.0f}s of work:"]
        for activity, pct in list(report["by_activity_pct"].items())[:limit]:
            seconds = report["by_activity_s"][activity]
            calls = report["calls"].get(activity, 0)
            out.append(f"  {activity:<16} {pct:5.1f}%  {seconds:8.1f}s  "
                       f"{calls:6d} call(s)")
        return out


#: One profile per run. A module-level default keeps the call sites free of
#: plumbing; the runner replaces it per run so nothing leaks between them.
_current = Profile()


def current() -> Profile:
    return _current


def reset() -> Profile:
    global _current
    _current = Profile()
    return _current


@contextmanager
def timing(activity: str) -> Iterator[None]:
    with _current.timing(activity):
        yield


def add(activity: str, seconds: float) -> None:
    _current.add(activity, seconds)
