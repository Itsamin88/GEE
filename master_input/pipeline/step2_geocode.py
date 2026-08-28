"""Step 2 - what country does each coordinate actually fall in?

Register field A3 is `country`, and the master prompt is explicit that it must
not be read off the community's name. This step therefore never looks at the
name. It takes the coordinate on its own and asks a gazetteer where it is.

The gazetteer is `geonamescache`, a bundled offline extract of GeoNames
(cities above 15 000 inhabitants, plus the country table). Offline matters
twice over: the run is reproducible from the repository alone, and no
coordinate leaves the machine.

**The method, and why it is the k-nearest form rather than the nearest.**
The nearest city to a point is a single draw and says nothing about its own
reliability. Taking the five nearest and asking whether they agree turns the
same data into a signal with an error bar attached: five cities in one country
around a point 40 km inland is a different kind of answer from three in Malawi
and two in Mozambique around a point on the border, and only the k-nearest
form can tell them apart. Agreement and distance are both carried forward, so
the confidence in the master file is derived from evidence rather than
asserted.

A coordinate in an empty quarter - desert, jungle, small island - has no city
within any useful radius, and the honest output there is a low-confidence
answer flagged for the verification pass, not a confident guess.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import geonamescache

EARTH_RADIUS_KM = 6371.0088

#: How many neighbours vote. Five is enough for the vote to be informative
#: without reaching so far that it crosses two borders in dense regions.
K = 5

#: Beyond this the nearest city says little about which side of a border a
#: point is on, and the answer is marked for verification whatever it says.
FAR_KM = 120.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


class Gazetteer:
    def __init__(self) -> None:
        gc = geonamescache.GeonamesCache()
        self.cities = [
            (float(c["latitude"]), float(c["longitude"]), c["countrycode"], c["name"])
            for c in gc.get_cities().values()
        ]
        self.countries = {
            code: info["name"] for code, info in gc.get_countries().items()
        }
        print(f"gazetteer: {len(self.cities)} cities, {len(self.countries)} countries",
              file=sys.stderr)

    def nearest(self, lat: float, lon: float, k: int = K) -> list[tuple[float, str, str]]:
        """The k nearest cities as (distance_km, country_code, city_name).

        A cheap latitude/longitude window prunes the list before the haversine
        runs; it widens until it holds enough candidates, so a point in an
        empty region still gets an answer rather than an exception.
        """
        window = 2.0
        while True:
            lon_window = window / max(0.15, math.cos(math.radians(lat)))
            near = [
                c for c in self.cities
                if abs(c[0] - lat) <= window and abs(c[1] - lon) <= lon_window
            ]
            if len(near) >= k or window >= 40.0:
                break
            window *= 2.0
        scored = sorted(
            ((haversine_km(lat, lon, c[0], c[1]), c[2], c[3]) for c in near),
            key=lambda t: t[0],
        )
        return scored[:k]


def classify(neighbours: list[tuple[float, str, str]]) -> dict:
    """Turn the k nearest cities into a country, a vote and a confidence."""
    if not neighbours:
        return {
            "country_code": "", "votes": 0, "k": 0, "nearest_km": None,
            "nearest_place": "", "agreement": 0.0, "signal": "NO_CITY_IN_RANGE",
        }
    counts: dict[str, int] = {}
    for _, code, _name in neighbours:
        counts[code] = counts.get(code, 0) + 1
    winner = max(counts, key=lambda c: (counts[c], -min(
        d for d, code, _ in neighbours if code == c)))
    nearest_km, nearest_code, nearest_place = neighbours[0]
    agreement = counts[winner] / len(neighbours)

    if agreement == 1.0 and nearest_km <= FAR_KM:
        signal = "UNANIMOUS"
    elif nearest_code == winner and agreement >= 0.6 and nearest_km <= FAR_KM:
        signal = "MAJORITY"
    elif nearest_km > FAR_KM:
        signal = "REMOTE"
    else:
        signal = "SPLIT"
    return {
        "country_code": winner,
        "votes": counts[winner],
        "k": len(neighbours),
        "nearest_km": round(nearest_km, 1),
        "nearest_place": nearest_place,
        "nearest_country_code": nearest_code,
        "agreement": round(agreement, 2),
        "signal": signal,
        "vote_detail": counts,
    }


def main() -> None:
    communities = json.loads(Path("master_input/pipeline/communities_raw.json").read_text(encoding="utf-8"))
    gaz = Gazetteer()

    for community in communities:
        for point in community["coordinate_candidates"]:
            neighbours = gaz.nearest(point["latitude"], point["longitude"])
            point["geocode"] = classify(neighbours)
            point["geocode"]["country_name"] = gaz.countries.get(
                point["geocode"]["country_code"], "")

    Path("master_input/pipeline/communities_geocoded.json").write_text(
        json.dumps(communities, ensure_ascii=False, indent=1), encoding="utf-8")

    from collections import Counter
    signals = Counter(p["geocode"]["signal"]
                      for c in communities for p in c["coordinate_candidates"])
    print("\n--- geocode signal over all 314 coordinates ---")
    for signal, count in signals.most_common():
        print(f"  {signal:<18} {count}")

    print("\n--- coordinates needing a look (REMOTE / SPLIT / none) ---")
    for community in communities:
        for point in community["coordinate_candidates"]:
            g = point["geocode"]
            if g["signal"] in {"REMOTE", "SPLIT", "NO_CITY_IN_RANGE"}:
                print(f"  line {point['source_line']:>3} "
                      f"{community['community_name_normalized'][:38]:<38} "
                      f"{point['latitude']:>10.5f},{point['longitude']:>11.5f} "
                      f"-> {g['country_code'] or '??'} {g['signal']:<16} "
                      f"{g['nearest_km']}km {g['nearest_place'][:22]} {g['vote_detail']}")

    print("\n--- multi-candidate groups whose candidates disagree on country ---")
    for community in communities:
        codes = {p["geocode"]["country_code"] for p in community["coordinate_candidates"]}
        if len(codes) > 1:
            print(f"  {community['community_name_normalized'][:44]:<44} {sorted(codes)}")


if __name__ == "__main__":
    main()
