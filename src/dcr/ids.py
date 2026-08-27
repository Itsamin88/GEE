"""Stable identifiers and safe filesystem names.

Every artefact the crawler keeps must be uniquely traceable back to a source
(brief §62), so identifiers are minted once and never reused.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
_REPEATS = re.compile(r"[_-]{2,}")

# Reserved on Windows; a researcher may open the output folder anywhere.
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_name(text: str, *, max_length: int = 64, fallback: str = "unnamed") -> str:
    """A filesystem-safe, ASCII, traversal-proof form of an arbitrary string."""
    if not text:
        return fallback
    normalised = unicodedata.normalize("NFKD", str(text))
    ascii_text = normalised.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.replace(" ", "_")
    cleaned = _UNSAFE.sub("_", ascii_text)
    cleaned = _REPEATS.sub("_", cleaned).strip("._-")
    if not cleaned:
        # Nothing survived transliteration (e.g. an all-CJK name): keep a stable
        # hash rather than collapsing every such name onto "unnamed".
        return f"{fallback}_{hashlib.sha1(text.encode('utf-8')).hexdigest()[:10]}"
    if cleaned.upper().split(".")[0] in _RESERVED:
        cleaned = f"_{cleaned}"
    if len(cleaned) > max_length:
        digest = hashlib.sha1(cleaned.encode("utf-8")).hexdigest()[:8]
        cleaned = f"{cleaned[: max_length - 9].rstrip('._-')}_{digest}"
    return cleaned


def community_id(index: int, *, fixture: bool = False) -> str:
    """IC001 ... IC999, prefixed TEST- for fixture runs (decision DCR-D022)."""
    base = f"IC{index:03d}"
    return f"TEST-{base}" if fixture else base


def address_id(community: str, index: int) -> str:
    """The register's own address numbering: IC001-01, IC001-02 ..."""
    return f"{community}-{index:02d}"


def source_id(community: str, index: int) -> str:
    return f"{community}-S{index:03d}"


def sha1_key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "surrogatepass")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def image_filename(
    *,
    image_id: str,
    topic: str | None,
    year: str | int | None,
    source: str,
    page_number: int | None,
    extension: str,
) -> str:
    """A traceable image name, e.g. IC027-IMG0042_site_plan_food_forest_2017_S018_p12.jpg.

    The name is a convenience; the manifest and the database carry the full
    provenance. Nothing is ever identified by filename alone.
    """
    parts = [image_id]
    if topic:
        parts.append(safe_name(topic, max_length=48))
    if year:
        parts.append(str(year))
    parts.append(safe_name(source, max_length=24))
    if page_number:
        parts.append(f"p{page_number}")
    ext = extension.lower().lstrip(".") or "bin"
    return f"{'_'.join(p for p in parts if p)}.{safe_name(ext, max_length=8)}"
