"""Step 5 - open every address and write what happened back into the master file.

This pass is deliberately separate from discovery, because it needs something
discovery does not: an open network. The session that built this file reached
the web only through a search API; the egress proxy refused a direct connection
to every research host, so no address in it has been fetched. The file says so
rather than implying otherwise - `seed_url_verification_method` is
`search_index`, and the four count columns are empty.

Run this where the network is open and the file stops being a promise:

    python3 master_input/pipeline/step5_validate_urls.py                # check everything
    python3 master_input/pipeline/step5_validate_urls.py --only IC001   # or one community

For each address it records, in `seed_sources_json` beside the address itself:

* `http_status`   - what the server actually said
* `final_url`     - after redirects, so a moved site is visible as moved
* `content_type`
* `crawl_status`  - the workbook's O11 vocabulary: `crawled`, `blocked`,
                    `dead link`, `not attempted`
* `checked_at`

and rolls the four totals up into `seed_url_validated_count`,
`seed_url_dead_count`, `seed_url_blocked_count` and
`seed_url_duplicate_count`. A 401, 403 or 429 is recorded as `blocked`, never
as empty: the register is explicit that a reported block is data and a guess
about the content behind it is fabrication.

Politeness: one request at a time per host, a real user agent, HEAD first and
GET only if HEAD is refused. The crawler's own fetcher does this properly with
robots.txt and rate limits; this is a lighter check whose only job is to fill
in the columns above.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import requests

MASTER = Path("master_input/Paper1_Final_Only_Ecovillages_Master_Input.csv")
TIMEOUT = 25
PER_HOST_DELAY = 2.0
USER_AGENT = ("DocumentaryResearchCrawler/1.0 (+academic research; "
              "ecovillage cohort source validation)")

#: HTTP status -> O11_Source_Set crawl_status. Anything that answers with a
#: page is `crawled`; a refusal is `blocked` and stays visible as a refusal.
BLOCKED = {401, 402, 403, 405, 406, 429, 451}


def classify(status: int | None, error: str) -> str:
    if status is None:
        return "dead link" if error else "not attempted"
    if 200 <= status < 400:
        return "crawled"
    if status in BLOCKED:
        return "blocked"
    if status in (404, 410):
        return "dead link"
    if status >= 500:
        return "blocked"
    return "dead link"


def check(session: requests.Session, url: str) -> dict:
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        response = session.head(url, timeout=TIMEOUT, allow_redirects=True)
        if response.status_code in BLOCKED or response.status_code >= 400:
            response = session.get(url, timeout=TIMEOUT, allow_redirects=True,
                                   stream=True)
            response.close()
        return {
            "http_status": response.status_code,
            "final_url": response.url,
            "content_type": response.headers.get("content-type", "").split(";")[0],
            "crawl_status": classify(response.status_code, ""),
            "checked_at": started,
        }
    except requests.RequestException as exc:
        return {
            "http_status": None, "final_url": "", "content_type": "",
            "crawl_status": classify(None, str(exc)),
            "error": type(exc).__name__, "checked_at": started,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", action="append", default=[],
                        help="community_id to check; repeatable")
    parser.add_argument("--recheck", action="store_true",
                        help="re-check addresses that already have a status")
    args = parser.parse_args()

    text = MASTER.read_text(encoding="utf-8")
    rows = list(csv.DictReader(io.StringIO(text)))
    fieldnames = list(rows[0].keys())

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    last_seen: dict[str, float] = defaultdict(float)
    seen_urls: set[str] = set()

    for row in rows:
        if args.only and row["community_id"] not in args.only:
            continue
        sources = json.loads(row["seed_sources_json"])
        for source in sources:
            if "http_status" in source and not args.recheck:
                continue
            host = urlsplit(source["url"]).hostname or ""
            wait = PER_HOST_DELAY - (time.monotonic() - last_seen[host])
            if wait > 0:
                time.sleep(wait)
            source.update(check(session, source["url"]))
            last_seen[host] = time.monotonic()
            print(f"  {row['community_id']}  {source['crawl_status']:<13} "
                  f"{source.get('http_status') or '-':>4}  {source['url'][:88]}")

        statuses = [s.get("crawl_status") for s in sources]
        duplicates = sum(1 for s in sources
                         if (s.get("final_url") or s["url"]) in seen_urls)
        seen_urls.update((s.get("final_url") or s["url"]) for s in sources)

        row["seed_sources_json"] = json.dumps(sources, ensure_ascii=False,
                                              separators=(",", ":"))
        row["seed_url_validated_count"] = str(statuses.count("crawled"))
        row["seed_url_dead_count"] = str(statuses.count("dead link"))
        row["seed_url_blocked_count"] = str(statuses.count("blocked"))
        row["seed_url_duplicate_count"] = str(duplicates)
        row["seed_url_verification_method"] = "search_index+http"

    with MASTER.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames,
                                lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nwrote {MASTER}")


if __name__ == "__main__":
    main()
