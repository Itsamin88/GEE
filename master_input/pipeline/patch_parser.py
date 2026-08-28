"""Hardening the community-file parser against three faults the master input found.

Run once; it rewrites `src/dcr/orchestrator/session.py` in place. Each change is
a fault a real input file triggers, not a hypothetical:

1. **Any column starting with "url" became URLs.** `url_count`, `url_notes`,
   `url_quality_score` — a QC column named the obvious way put its own value
   into the crawl queue, so the frontier would try to fetch `7`. Only `urls`,
   `url`, and `url` followed by digits or a separator now count.

2. **The delimiter sniffer could choose the wrong character.** A `urls` cell
   holding a `;`-separated list can contain more semicolons than the header
   row has commas, and `csv.Sniffer` then reads the whole file as
   semicolon-delimited: one column, no `name`, zero communities, no error.
   The sniffed dialect is now checked against the header and discarded if it
   does not produce a usable one.

3. **A lone URL containing a comma was split into two.** Query strings carry
   commas (`?bbox=1,2,3`), and the comma branch fired whenever no `;` or `|`
   was present. Splitting now only happens where the pieces still look like
   URLs.

Also: a header may name the community column `name`, `community_name`,
`community_name_normalized`, or `ecovillage_name`. The last is what the
researcher's own spreadsheet uses, and rejecting it silently produced an empty
queue — the failure this file exists to prevent.
"""
from __future__ import annotations

from pathlib import Path

TARGET = Path("src/dcr/orchestrator/session.py")

OLD_DOC = '''    CSV wants a header row with at least `name`. URLs may be one column
    separated by `;`, `|` or whitespace, or several columns named `url`,
    `url1`, `url2` and so on — because that is how the two shapes of
    spreadsheet a researcher already has actually look.
    """'''

NEW_DOC = '''    CSV wants a header row with a name column — `name`, or one of the aliases
    in `NAME_COLUMNS`, because the researcher's own sheet calls it
    `Ecovillage_Name` and a file that reads as zero communities with no error
    is the worst failure this function has. URLs may be one column separated
    by `;`, `|` or whitespace, or several columns named `url`, `url1`, `url2`
    and so on — because that is how the two shapes of spreadsheet a researcher
    already has actually look. Columns that merely *begin* with "url", such as
    `url_count`, are not addresses and are left alone.
    """'''

OLD_READ = '''    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\\t")
        except csv.Error:
            dialect = csv.excel
        for raw in csv.DictReader(handle, dialect=dialect):
            entry = {str(k or "").strip().lower(): (v or "").strip()
                     for k, v in raw.items() if k}
            if not entry.get("name"):
                continue
            urls: list[str] = []
            for key, value in entry.items():
                if key == "urls" or key.startswith("url"):
                    urls.extend(_split_urls(value))
            entry["urls"] = urls
            rows.append(_normalise_entry(entry))
    return rows'''

NEW_READ = '''    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(8192)
        handle.seek(0)
        for raw in csv.DictReader(handle, dialect=_dialect_for(sample)):
            entry = {str(k or "").strip().lower(): (v or "").strip()
                     for k, v in raw.items() if k}
            name = next((entry[key] for key in NAME_COLUMNS
                         if entry.get(key)), "")
            if not name:
                continue
            entry["name"] = name
            urls: list[str] = []
            for key, value in entry.items():
                if _is_url_column(key):
                    urls.extend(_split_urls(value))
            entry["urls"] = _dedupe(urls)
            rows.append(_normalise_entry(entry))
    return rows


#: Header names that mean "the community's name", most specific first. The
#: researcher's own cohort file uses `Ecovillage_Name`; accepting it here is
#: what stops that file loading as zero communities.
NAME_COLUMNS = ("name", "community_name_normalized", "community_name",
                "ecovillage_name", "community")


def _dialect_for(sample: str) -> type[csv.Dialect] | csv.Dialect:
    """Choose a dialect, then check it actually produced a usable header.

    `csv.Sniffer` counts candidate delimiters, so a file whose URL column holds
    a `;`-separated list can out-vote its own commas. The sniffed answer is
    therefore treated as a proposal: if reading the header with it does not
    yield a name column, it is discarded for plain comma-separated Excel.
    """
    candidates: list[type[csv.Dialect] | csv.Dialect] = []
    try:
        candidates.append(csv.Sniffer().sniff(sample, delimiters=",;\\t"))
    except csv.Error:
        pass
    candidates.append(csv.excel)
    for dialect in candidates:
        try:
            header = next(csv.reader(sample.splitlines()[:1], dialect=dialect), [])
        except csv.Error:
            continue
        keys = {str(cell or "").strip().lower() for cell in header}
        if keys & set(NAME_COLUMNS):
            return dialect
    return csv.excel


def _is_url_column(key: str) -> bool:
    """Is this header an address column, rather than one that merely starts 'url'?

    `urls`, `url`, `url1`, `url_2`, `url-10` are addresses. `url_count`,
    `url_notes`, `urls_verified_count` are not, and feeding their values to the
    frontier would queue `7` as a page to fetch.
    """
    if key in {"url", "urls"}:
        return True
    if not key.startswith("url"):
        return False
    rest = key[3:].lstrip("_- ")
    return rest.isdigit()


def _dedupe(urls: list[str]) -> list[str]:
    """Keep first occurrence order; the same address twice is one address."""
    seen: set[str] = set()
    out: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out'''

OLD_SPLIT = '''    for separator in (";", "|", ","):
        if separator in text:
            return [part.strip() for part in text.split(separator) if part.strip()]
    return [part for part in text.split() if part]'''

NEW_SPLIT = '''    for separator in (";", "|", "\\n"):
        if separator in text:
            return [part.strip() for part in text.split(separator) if part.strip()]
    # Comma last, and only when every piece still looks like an address: query
    # strings carry commas (`?bbox=1,2,3`), and splitting one URL into two
    # fragments is worse than leaving a rare comma-separated pair joined.
    if "," in text:
        parts = [part.strip() for part in text.split(",") if part.strip()]
        if len(parts) > 1 and all(_looks_like_url(part) for part in parts):
            return parts
    return [part for part in text.split() if part]


def _looks_like_url(text: str) -> bool:
    return text.startswith(("http://", "https://", "www.")) or (
        "." in text.split("/")[0] and " " not in text)'''


def main() -> None:
    source = TARGET.read_text(encoding="utf-8")
    for old, new, label in ((OLD_DOC, NEW_DOC, "docstring"),
                            (OLD_READ, NEW_READ, "reader"),
                            (OLD_SPLIT, NEW_SPLIT, "splitter")):
        if new.split("\n")[0] in source and old not in source:
            print(f"  {label}: already applied")
            continue
        if old not in source:
            raise SystemExit(f"anchor not found for {label}")
        source = source.replace(old, new, 1)
        print(f"  {label}: patched")
    TARGET.write_text(source, encoding="utf-8")


if __name__ == "__main__":
    main()
