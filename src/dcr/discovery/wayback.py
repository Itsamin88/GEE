"""Stage 4 — the web archive, treated as a first-class source.

The CDX index answers "every URL this archive holds under this domain" in one
request, including pages that were deleted years ago and are linked from
nowhere. That is the single largest yield increase in the protocol (register
v2.4). If the endpoint is unreachable the stage is recorded as blocked; it is
never silently marked complete (brief §14).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable
from urllib.parse import quote, urlencode, urlsplit

from ..crawl.normalize import classify_url, normalize


@dataclass
class ArchivedUrl:
    original: str
    timestamp: str                 # YYYYMMDDhhmmss
    mimetype: str = ""
    status: str = ""
    digest: str = ""
    kind: str = "page"

    @property
    def iso_date(self) -> str:
        try:
            return datetime.strptime(self.timestamp[:8], "%Y%m%d").date().isoformat()
        except ValueError:
            return self.timestamp[:4]

    @property
    def year(self) -> int | None:
        try:
            return int(self.timestamp[:4])
        except (ValueError, TypeError):
            return None

    def snapshot_url(self, template: str, *, raw: bool = True) -> str:
        # The `id_` suffix asks the archive for the original bytes rather than
        # its rewritten page, which keeps document hashes meaningful.
        return template.format(timestamp=self.timestamp + ("id_" if raw and "id_" not in template else ""),
                               url=self.original).replace("id_id_", "id_")


_SNAPSHOT_URL = re.compile(
    r"/(?:web|wayback)/(\d{4,14})(?:id_|im_|cs_|js_|if_)?/(https?://.+)$", re.IGNORECASE
)


def parse_archive_url(url: str) -> tuple[str, str] | None:
    """Recover (timestamp, original URL) from an archive snapshot URL.

    Doing it from the URL rather than from how the URL was queued means an
    archived page is marked as archived however it was reached — including when
    a live page links to one.
    """
    match = _SNAPSHOT_URL.search(url or "")
    if not match:
        return None
    return match.group(1), match.group(2)


@dataclass
class CdxResult:
    ok: bool
    entries: list[ArchivedUrl] = field(default_factory=list)
    status: str = "not_attempted"     # ok | unreachable | empty | error
    detail: str = ""
    query_url: str = ""


def build_cdx_query(endpoint: str, domain: str, params: dict[str, Any],
                    *, from_year: int | None = None, to_year: int | None = None) -> str:
    query = dict(params)
    query["url"] = f"{domain}*"
    query["output"] = "json"
    if from_year:
        query["from"] = str(from_year)
    if to_year:
        query["to"] = str(to_year)
    return f"{endpoint}?{urlencode(query, quote_via=quote)}"


def parse_cdx(payload: str | bytes) -> CdxResult:
    """Parse a CDX response in either the JSON-array or the space-separated form."""
    text = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else payload
    text = text.strip()
    if not text:
        return CdxResult(ok=True, status="empty", detail="archive holds no records for this domain")

    entries: list[ArchivedUrl] = []
    if text.startswith("["):
        try:
            rows = json.loads(text)
        except json.JSONDecodeError as exc:
            return CdxResult(ok=False, status="error", detail=f"malformed CDX JSON: {exc}")
        if not rows:
            return CdxResult(ok=True, status="empty")
        header = [str(h) for h in rows[0]]
        for row in rows[1:]:
            record = dict(zip(header, [str(v) for v in row]))
            entry = _entry_from(record)
            if entry:
                entries.append(entry)
    else:
        for line in text.splitlines():
            fields = line.split()
            if len(fields) < 2:
                continue
            record = {"original": fields[0], "timestamp": fields[1]}
            if len(fields) > 2:
                record["mimetype"] = fields[2]
            if len(fields) > 3:
                record["statuscode"] = fields[3]
            if len(fields) > 4:
                record["digest"] = fields[4]
            entry = _entry_from(record)
            if entry:
                entries.append(entry)

    if not entries:
        return CdxResult(ok=True, status="empty")
    return CdxResult(ok=True, entries=entries, status="ok")


def _entry_from(record: dict[str, str]) -> ArchivedUrl | None:
    original = record.get("original") or record.get("url")
    timestamp = record.get("timestamp")
    if not original or not timestamp:
        return None
    normalised = normalize(original)
    if not normalised:
        return None
    return ArchivedUrl(
        original=original,
        timestamp=timestamp,
        mimetype=record.get("mimetype", ""),
        status=record.get("statuscode", ""),
        digest=record.get("digest", ""),
        kind=classify_url(normalised),
    )


def select_snapshots(
    entries: Iterable[ArchivedUrl],
    *,
    priority_paths: Iterable[str],
    max_per_url: int = 20,
    max_total: int = 60,
) -> list[ArchivedUrl]:
    """Choose which snapshots to actually retrieve.

    Priorities, in order: the earliest snapshot of anything (it bounds the
    dating); every snapshot of a page whose path matters for onset; then roughly
    annual samples of everything else. Documents always win over pages, because
    a deleted PDF is unrecoverable anywhere else.
    """
    by_url: dict[str, list[ArchivedUrl]] = {}
    for entry in entries:
        by_url.setdefault(entry.original, []).append(entry)
    for values in by_url.values():
        values.sort(key=lambda e: e.timestamp)

    wanted = {p.rstrip("/").lower() for p in priority_paths}
    scored: list[tuple[float, ArchivedUrl]] = []

    for url, snapshots in by_url.items():
        path = (urlsplit(url).path or "/").rstrip("/").lower() or "/"
        is_priority = path in wanted or any(path.startswith(w) for w in wanted if w != "/")
        is_document = snapshots[0].kind == "document"

        chosen: list[ArchivedUrl] = [snapshots[0]]           # earliest, always
        if len(snapshots) > 1:
            chosen.append(snapshots[-1])                     # latest, always
        if is_priority or is_document:
            # roughly annual sampling across the record
            seen_years: set[int] = {s.year for s in chosen if s.year}
            for snapshot in snapshots:
                if snapshot.year and snapshot.year not in seen_years:
                    seen_years.add(snapshot.year)
                    chosen.append(snapshot)
        for snapshot in chosen[:max_per_url]:
            score = 0.0
            score += 4.0 if is_document else 0.0
            score += 3.0 if is_priority else 0.0
            score += 2.0 if snapshot is snapshots[0] else 0.0
            # older material is worth more for dating
            if snapshot.year:
                score += max(0.0, (2015 - snapshot.year) * 0.15)
            scored.append((score, snapshot))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    out: list[ArchivedUrl] = []
    seen: set[tuple[str, str]] = set()
    for _, snapshot in scored:
        key = (snapshot.original, snapshot.timestamp)
        if key in seen:
            continue
        seen.add(key)
        out.append(snapshot)
        if len(out) >= max_total:
            break
    return out
