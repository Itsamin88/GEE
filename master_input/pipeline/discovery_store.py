"""The record of what the discovery pass actually found, per community.

One JSON file, appended to in batches, so a long discovery run survives an
interruption and every claim in the master CSV can be traced back to the
search evidence that produced it.

Independence groups follow register v2.4 "The independence rule" rather than
the looser reading that counts URLs:

* **G1** is the community's own voice - its current site, any former domain,
  its social accounts, and every self-submitted directory listing including
  its Global Ecovillage Network profile. A listing whose text the community
  submitted corroborates nothing about the community.
* **G2, G3, ...** are separate origins: an outside researcher's thesis, a
  municipal or national record, a grant award, independent journalism. Two
  works by one author on one visit share a group.

`https://ecovillage.org` is placed in G1 as well. It is not the community's
voice, but master-brief §8 requires that it never counts as independent of a
GEN community profile, and a GEN profile is G1; keeping both there is the
reading that cannot over-state corroboration.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STORE = Path("master_input/pipeline/discovery.json")

#: Source classes, register v2.4 / Reference_Codes.
SOURCE_CLASSES = {"S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"}

#: platform_type vocabulary, workbook v6 sheet O11_Source_Set.
PLATFORM_TYPES = {
    "own website", "secondary or former website", "Facebook", "Instagram",
    "YouTube", "Vimeo", "blog platform", "directory listing", "crowdfunding",
    "LinkedIn", "booking or hosting", "news outlet", "other",
}

CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}


def load() -> dict[str, Any]:
    if STORE.exists():
        return json.loads(STORE.read_text(encoding="utf-8"))
    return {}


def save(data: dict[str, Any]) -> None:
    STORE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def record(seq: int, **fields: Any) -> None:
    """Store one community's discovery result, validating the vocabularies."""
    data = load()
    for source in fields.get("sources", []):
        if source["source_class"] not in SOURCE_CLASSES:
            raise ValueError(f"seq {seq}: bad source_class {source['source_class']}")
        if source["platform_type"] not in PLATFORM_TYPES:
            raise ValueError(f"seq {seq}: bad platform_type {source['platform_type']}")
        if source["confidence"] not in CONFIDENCE:
            raise ValueError(f"seq {seq}: bad confidence {source['confidence']}")
        if not source["url"].startswith(("http://", "https://")):
            raise ValueError(f"seq {seq}: not a URL: {source['url']}")
    data[str(seq)] = fields
    save(data)


def record_many(batch: list[dict[str, Any]]) -> None:
    for entry in batch:
        seq = entry.pop("seq")
        record(seq, **entry)
    print(f"stored {len(batch)}; total {len(load())}")
