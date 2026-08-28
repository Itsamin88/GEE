"""Step 4 - finish the rows discovery has not reached, and merge them in place.

The master file is built to be completed incrementally rather than rebuilt.
Rows carry `discovery_status`, so a second pass can find exactly what is left:

    python3 master_input/pipeline/step4_resume_discovery.py --list-pending

prints the communities still marked PENDING, with the coordinate and the
gazetteer's reading of it, in the order the cohort runs. Work through them with
the same two searches per community the first pass used - one general, one
`site:ecovillage.org "<name>"` - record each result with
`discovery_store.record_many(...)`, then:

    python3 master_input/pipeline/step3_build_master.py

rebuilds the master file with the new rows folded in. Nothing already recorded
is re-fetched, and a row that has been completed never returns to PENDING.

**Why the pending rows are marked rather than left blank.** Register v2.4 field
I12 exists because a community searched for four minutes and a community
searched exhaustively that genuinely has nothing look identical in the data -
both arrive as a thin record full of NOT FOUND - and they mean opposite things.
One is an absence of evidence and the other an absence of effort. So every row
here says which it is: `gen_community_status` is `NOT_SEARCHED`, never
`NOT_FOUND`, until somebody has actually looked.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

TEMPLATE = '''\
 dict(seq={seq}, country="", country_iso2="", admin_region="",
   country_method="", country_source="",
   gen_community_url="", gen_status="",
   gen_evidence="",
   alternative_names="", identity_confidence="",
   notes="",
   sources=[
     S("", "S4", "own website", "G1", "HIGH", 0.90, ""),
   ]),'''


def pending() -> list[dict]:
    communities = json.loads(
        Path("master_input/pipeline/communities_geocoded.json").read_text(encoding="utf-8"))
    done = set(json.loads(Path("master_input/pipeline/discovery.json").read_text(encoding="utf-8")))
    return [c for c in communities if str(c["seq"]) not in done]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-pending", action="store_true")
    parser.add_argument("--emit-template", action="store_true",
                        help="print a record_many() skeleton for the next N rows")
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args()

    rows = pending()
    if args.emit_template:
        print("import sys; sys.path.insert(0, 'master_input/pipeline')")
        print("from discovery_store import record_many")
        print("S = lambda u, c, p, g, cf, sc, e: dict(url=u, source_class=c, "
              "platform_type=p, independence_group=g, confidence=cf, score=sc, "
              "evidence=e)")
        print("record_many([")
        for community in rows[: args.limit]:
            print(f"# {community['community_name_normalized']}")
            print(TEMPLATE.format(seq=community["seq"]))
        print("])")
        return

    print(f"{len(rows)} communities still to research\n")
    for community in rows:
        point = community["coordinate_candidates"][0]
        gaz = point["geocode"]
        print(f"  seq {community['seq']:>3}  {community['community_name_normalized'][:46]:<46} "
              f"{point['latitude']:>10.5f},{point['longitude']:>11.5f}  "
              f"{gaz['country_code']:<3} {gaz['signal']:<10} "
              f"near {gaz['nearest_place'][:22]}")


if __name__ == "__main__":
    main()
