"""Step 1 — read the original CSV, repair text damage, group into 212 communities.

Nothing here invents data. Every repair is a decoding fix whose input and output
are both recorded, so the original string survives in the master file.
"""
from __future__ import annotations
import csv, io, json, math, sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).parent))
from collections import defaultdict
from pathlib import Path

SRC = Path("master_input/Paper1_Final_Only Ecovillages.csv")

from repair_text import repair


def haversine_km(a, b):
    (la1, lo1), (la2, lo2) = a, b
    R = 6371.0088
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = p2 - p1, math.radians(lo2 - lo1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def main() -> None:
    rows = list(csv.DictReader(io.StringIO(SRC.read_text(encoding="utf-8"))))
    groups: dict[str, list[dict]] = defaultdict(list)
    order: list[str] = []
    for line_no, row in enumerate(rows, start=2):
        name = row["Ecovillage_Name"]
        if name not in groups:
            order.append(name)
        groups[name].append({
            "source_line": line_no,
            "latitude": float(row["Latitude"]),
            "longitude": float(row["Longitude"]),
        })

    communities = []
    for index, original_name in enumerate(order, start=1):
        pts = groups[original_name]
        coords = [(p["latitude"], p["longitude"]) for p in pts]
        spread = max((haversine_km(a, b) for a in coords for b in coords), default=0.0)
        repaired = repair(original_name)
        communities.append({
            "seq": index,
            "community_name_original": original_name,
            "community_name_normalized": repaired,
            "text_repaired": repaired != original_name,
            "source_rows": [p["source_line"] for p in pts],
            "coordinate_candidates": pts,
            "candidate_count": len(pts),
            "candidate_spread_km": round(spread, 3),
        })

    Path("master_input/pipeline/communities_raw.json").write_text(
        json.dumps(communities, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"communities: {len(communities)}")
    print(f"source rows: {sum(c['candidate_count'] for c in communities)}")
    print(f"repaired names: {sum(1 for c in communities if c['text_repaired'])}")
    print(f"multi-candidate: {sum(1 for c in communities if c['candidate_count'] > 1)}")
    print("\n--- every repaired name ---")
    for c in communities:
        if c["text_repaired"]:
            print(f"  {c['community_name_original']!r}\n    -> {c['community_name_normalized']!r}")


if __name__ == "__main__":
    main()
