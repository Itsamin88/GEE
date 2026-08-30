"""Append newly-found addresses to an existing community's discovery record.

The first pass aimed at a small, ranked set of the best addresses per community
- three to ten, per the original brief. That ceiling is now lifted: the crawler
takes an address's SCOPE from the master file, so a third-party page costs
exactly one fetch and a direct document link costs one download. Breadth is
therefore cheap, and the limit on how many addresses a community may carry is
no longer a cost question.

What is NOT cheap, and what this helper refuses to do, is invent addresses. A
URL is added here only because a search returned it.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from discovery_store import CONFIDENCE, PLATFORM_TYPES, SOURCE_CLASSES, load, save


def add(seq: int, sources: list[dict[str, Any]], *, note: str = "") -> int:
    """Add addresses to one community, skipping any URL it already has."""
    data = load()
    entry = data[str(seq)]
    have = {s["url"] for s in entry["sources"]}
    added = 0
    for source in sources:
        if source["source_class"] not in SOURCE_CLASSES:
            raise ValueError(f"seq {seq}: bad source_class {source['source_class']}")
        if source["platform_type"] not in PLATFORM_TYPES:
            raise ValueError(f"seq {seq}: bad platform_type {source['platform_type']}")
        if source["confidence"] not in CONFIDENCE:
            raise ValueError(f"seq {seq}: bad confidence {source['confidence']}")
        if not source["url"].startswith(("http://", "https://")):
            raise ValueError(f"seq {seq}: not a URL: {source['url']}")
        if source["url"] in have:
            continue
        entry["sources"].append(source)
        have.add(source["url"])
        added += 1
    if note:
        entry["notes"] = f"{entry['notes']} {note}".strip()
    save(data)
    return added


def add_many(batch: list[dict[str, Any]]) -> None:
    total = 0
    for item in batch:
        total += add(item["seq"], item["sources"], note=item.get("note", ""))
    data = load()
    urls = sum(len(v["sources"]) for v in data.values())
    print(f"added {total} addresses; {urls} across {len(data)} communities")
