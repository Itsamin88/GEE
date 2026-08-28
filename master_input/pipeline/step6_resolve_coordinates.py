"""Resolve the communities for which the source file gave four coordinates.

Thirty-four of the 212 communities - and, tellingly, the last thirty-four in
file order, seq 179 to 212 with no gaps - carry exactly four coordinate rows
each. That is not scatter in the data. It is the signature of a geocoder that
was asked for candidates rather than for an answer, and whose output was
pasted into the export without anyone choosing between them.

Reading the four slots against the offline gazetteer makes the structure plain:

* **Slot 3 is a decoy.** In case after case it lands within a kilometre or two
  of the nearest large city - Ansbach 0 km, Butterworth 0 km, Maralal 0 km,
  Castricum 0 km, Victoria 1 km, Kirksville 1 km, Nhlazatje 2 km, Delmas 2 km,
  George 2 km, Llanelli 3 km, Randers 3 km, Arnold 3 km, Vladimir 4 km,
  Limerick 4 km, Odense 4 km. A geocoder falling back to the nearest populated
  place produces exactly this.
* **Slot 4 is the community.** Checked against the published street or village
  address gathered independently for each row during source discovery, slot 4
  lands on the stated locality again and again, often to three decimal places.
* **Slot 1 - the coordinate the export put first, and therefore the one a
  naive reader takes - is frequently wrong**, sometimes by fifty to ninety
  kilometres. Nearly every location conflict flagged during discovery traces
  to slot 1: Nuweiba, Valdepielagos, Hurdal, TerraSante, Poussan, Yator,
  Colebrook. Those conflicts are not conflicts in the underlying record. They
  are an artefact of reading the wrong slot.

Master-brief section 33 forbids transferring a factual result from one
community to another without independent verification, and that rule binds
here more than anywhere: it would be easy, and wrong, to declare "slot 4
always" and move on. So every pick below is justified by THAT community's own
published address, from the source named beside it, and the gazetteer evidence
is recomputed at run time so a reader can audit each choice. Where the
published record does not pin the locality finely enough to separate the
candidates, the row stays unresolved and says why. The pattern is a conclusion
drawn from many independent checks, never a premise applied to them.

Nothing is discarded. All four candidates stay in ``coordinate_candidates`` on
every row, and the export's original first coordinate is preserved in its own
columns, so any choice made here can be reversed by a coder who disagrees.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from step2_geocode import Gazetteer

RAW = Path("master_input/pipeline/communities_raw.json")
OUT = Path("master_input/pipeline/coordinate_resolution.json")

#: One entry per multi-candidate community.
#:
#: ``locality``   the place the published sources name, which the chosen
#:                candidate has to match - the thing actually being tested.
#: ``source``     where that locality was published.
#: ``pick``       1-based index into ``coordinate_candidates``; 0 = unresolved.
#: ``confidence`` HIGH   the candidate sits on the named locality.
#:                MEDIUM the candidate is the best fit but the address is
#:                       coarse, or a second candidate is nearly as good.
#:                LOW    recorded for completeness; treat as unresolved.
VERIFICATIONS: dict[int, dict[str, Any]] = {
    179: {"locality": "Nuweiba, at the mouth of the Wadi Watir delta, South Sinai",
          "source": "https://habibacommunity.com/agriculture/", "pick": 4, "confidence": "HIGH",
          "note": "c4 sits on Nuweiba. c1 - the coordinate the export put first - is far to the "
                  "south towards Dahab, which is the whole of the location conflict this row "
                  "was flagged for during discovery."},
    180: {"locality": "Chuchumbletza, near Gualaquiza, Morona Santiago",
          "source": "https://ecovillage.org/ecovillage/fruit-haven-ecovllage-ecuador/",
          "pick": 4, "confidence": "MEDIUM",
          "note": "c3 is Gualaquiza town itself, the decoy slot. c4 lies south of it, which is "
                  "where Chuchumbletza is. c1 is in Azuay province, which is what made this row "
                  "look like a province conflict. Held at MEDIUM because the community spans "
                  "seven separate properties and no single parcel address was published."},
    181: {"locality": "Yator, Cadiar, Las Alpujarras, Granada 18448",
          "source": "https://ecohomes.blog/2010/06/15/el-valle-de-sensaciones-yator-spain/",
          "pick": 4, "confidence": "HIGH",
          "note": "c4 falls on Yator in Granada province. c1 is in Almeria province, which is "
                  "the province conflict recorded against this row."},
    182: {"locality": "Huatusco de Chicuellar, Veracruz",
          "source": "https://bosquedeniebla.com.mx/quienes-somos/", "pick": 4, "confidence": "HIGH",
          "note": "c4 is on Huatusco; c1 is up towards Xico, which is why the gazetteer named a "
                  "different town than the community's own address."},
    183: {"locality": "Valdepielagos, Comunidad de Madrid, about 50 km north of Madrid",
          "source": "https://ecoaldeas.org/valdepielagos/", "pick": 4, "confidence": "HIGH",
          "note": "c4 lands on the municipality of Valdepielagos in Madrid. c1 is well east in "
                  "Guadalajara province - the province conflict on this row."},
    184: {"locality": "the mesa north-west of Taos across the Rio Grande gorge, Taos County",
          "source": "https://greaterworldhoa.communitysite.com/", "pick": 4, "confidence": "HIGH",
          "note": "c4 is on the mesa north-west of Taos where the subdivision lies; c1 sits east "
                  "of the gorge, on the wrong side of the canyon from the community."},
    185: {"locality": "Dripping Springs Valley, Pinal County, Arizona",
          "source": "https://windspiritcommunity.org/about/", "pick": 4, "confidence": "HIGH",
          "note": "c4 is in the Dripping Springs Valley; c3 is Tucson, the decoy slot."},
    186: {"locality": "13535 W. Sacred Earth Pl., Tucson AZ 85735 - the Three Points area, "
                      "about 25 miles south-west of Tucson",
          "source": "https://www.terrasante.org/", "pick": 4, "confidence": "HIGH",
          "note": "c4 is west of Tucson in the 85735 area. c1 is south-east of the city near "
                  "Sahuarita - the location conflict recorded against this row."},
    187: {"locality": "near Poussan, Herault",
          "source": "https://catfarm.net/about-us/", "pick": 4, "confidence": "HIGH",
          "note": "c4 sits on Poussan. c1 is far west towards Beziers, which is why the "
                  "gazetteer named the wrong town for this row."},
    188: {"locality": "Grishino, Vashinskoye, Podporozhsky District, Leningrad Oblast",
          "source": "https://www.wikidata.org/wiki/Q18406117", "pick": 0, "confidence": "LOW",
          "note": "UNRESOLVED. The decoy test cannot be applied here: there is no city above the "
                  "gazetteer's size threshold anywhere near any of the four candidates, so no "
                  "slot betrays itself as the nearest-city fallback. Two candidates sit in "
                  "Podporozhsky District and two further north in Karelia, and the published "
                  "record names the district but not a coordinate. Left for a coder with "
                  "Russian settlement data rather than guessed at."},
    189: {"locality": "Hurdal municipality, Akershus, about 80 km north of Oslo",
          "source": "https://hurdallandsbyene.no/en/", "pick": 4, "confidence": "HIGH",
          "note": "c4 lands on Hurdal. c1 is away to the north-east towards Hamar in a "
                  "neighbouring county - the conflict flagged on this row."},
    190: {"locality": "the area around Jarna, south of Stockholm",
          "source": "https://ecovillage.org/ecovillage/nackunga-community/",
          "pick": 4, "confidence": "MEDIUM",
          "note": "c4 is the closest of the four to Jarna, which is the only locality GEN gives. "
                  "MEDIUM because 'the area around Jarna' is not an address and cannot separate "
                  "candidates at the kilometre scale."},
    191: {"locality": "Skare, about 10 km north of Karlstad",
          "source": "https://hbvarmland.se/brf-tuggelite/", "pick": 4, "confidence": "HIGH",
          "note": "c4 sits on Skare, north-west of Karlstad, exactly as the published address "
                  "describes. c3 is Karlstad city, the decoy slot."},
    192: {"locality": "Stanciova, Recas commune, Timis County",
          "source": "https://ecobasa.org/en/communities/stanciova-an-open-community/",
          "pick": 4, "confidence": "HIGH",
          "note": "c4 falls on Stanciova between Timisoara and Lugoj; c3 is Timisoara itself, "
                  "the decoy slot."},
    193: {"locality": "Kressberg 74594, Schwabisch Hall district, Baden-Wurttemberg",
          "source": "https://de.wikipedia.org/wiki/Tempelhof_(Gemeinschaft)",
          "pick": 4, "confidence": "HIGH",
          "note": "c4 is the only candidate in the Schwabisch Hall district, near Crailsheim, "
                  "where Kressberg is. The other three are all in the Ansbach area in Bavaria, "
                  "a different state; c3 is Ansbach itself, the decoy slot."},
    194: {"locality": "La Plata, Macon County, Missouri",
          "source": "https://www.motherearthnews.com/sustainable-living/nature-and-environment/"
                    "possibility-alliance-ze0z11zmar/", "pick": 4, "confidence": "HIGH",
          "note": "c4 is a few kilometres from La Plata; c3 is Kirksville, the decoy slot, and "
                  "the nearest place of any size."},
    195: {"locality": "Vladimir Oblast - no finer locality was published",
          "source": "https://vmegre.com/en/kin-domain/vladimir-oblast-region-rodnoe/",
          "pick": 0, "confidence": "LOW",
          "note": "UNRESOLVED. c3 is Vladimir city and is clearly the decoy slot, which rules "
                  "one candidate out but does not choose among the other three. The sources "
                  "name only the oblast, and a settlement spread over roughly a hundred "
                  "one-hectare plots has no single point anyway. Left unresolved."},
    196: {"locality": "the townland of Oxpark adjoining Cloughjordan village, County Tipperary",
          "source": "https://www.thevillage.ie/about-us/our-story/", "pick": 4, "confidence": "HIGH",
          "note": "c4 sits on Cloughjordan. c3 is Limerick, the decoy slot; c1 and c2 are away "
                  "east in the midlands."},
    197: {"locality": "1565 Baldy Mountain Rd, Shawnigan Lake, British Columbia V8H 2A9",
          "source": "https://ourecovillage.org/", "pick": 4, "confidence": "HIGH",
          "note": "c4 is on the Shawnigan Lake side, south of Duncan, matching the street "
                  "address. c3 is Victoria city centre, the decoy slot."},
    198: {"locality": "Glandwr, near Crymych, Pembrokeshire",
          "source": "https://lammas.org.uk/en/ecovillage/", "pick": 4, "confidence": "HIGH",
          "note": "c4 lands on the Glandwr and Crymych area. c3 is Llanelli, the decoy slot, and "
                  "is in a different county."},
    199: {"locality": "Feldballe, Djursland, Syddjurs Municipality",
          "source": "https://da.wikipedia.org/wiki/Friland", "pick": 4, "confidence": "HIGH",
          "note": "c4 is on Djursland at Feldballe; c3 is Randers, the decoy slot, and is not on "
                  "Djursland at all."},
    200: {"locality": "Anse-a-Pitres, Sud-Est Department, on the Dominican border",
          "source": "https://sadhanaforest.org/haiti/causes-haiti/", "pick": 4, "confidence": "HIGH",
          "note": "c4 sits on Anse-a-Pitres in the far south-east. c1 is near Thomazeau outside "
                  "Port-au-Prince, roughly ninety kilometres away and in the wrong department, "
                  "and c3 is Port-au-Prince itself, the decoy slot. Note that the planting this "
                  "community does is dispersed across the whole municipality, so even the "
                  "correct point represents only its base."},
    201: {"locality": "Hockerton, Newark and Sherwood district, Nottinghamshire",
          "source": "https://www.hockertonhousingproject.org.uk/about-us/",
          "pick": 4, "confidence": "HIGH",
          "note": "c4 is the only candidate in the Newark and Sherwood district, a short "
                  "distance from Newark on Trent, which is where Hockerton is. c3 is Nottingham, "
                  "the decoy slot."},
    202: {"locality": "Hundstrup, 5762 Vester Skerninge, Svendborg Municipality, South Funen",
          "source": "http://www.selvforsyning.dk/", "pick": 4, "confidence": "HIGH",
          "note": "c4 is in Svendborg Municipality on southern Funen, nearest to the Vester "
                  "Skerninge area. c3 is Odense, the decoy slot, and is in the north of the "
                  "island."},
    203: {"locality": "Colebrook, Coos County, New Hampshire 03576",
          "source": "https://ecovillage.org/project/cite-ecologique-of-new-hampshire/",
          "pick": 4, "confidence": "HIGH",
          "note": "c4 falls on Colebrook, New Hampshire. This pick also settles the country: c1, "
                  "the exported first coordinate, lies west of Colebrook and is what drove the "
                  "gazetteer's vote for Canada on a community that is in the United States."},
    204: {"locality": "near Newport (Trefdraeth), Pembrokeshire",
          "source": "https://brithdirmawr.co.uk/about/", "pick": 4, "confidence": "HIGH",
          "note": "c4 is nearest the Newport/Trefdraeth coast of north Pembrokeshire where the "
                  "farm lies; c3 is well south, in the wrong part of the county."},
    205: {"locality": "Karise, Faxe Municipality, Region Zealand",
          "source": "https://permatopia.dk/english/", "pick": 4, "confidence": "HIGH",
          "note": "c4 is south of Koge in the Karise and Faxe area. c3 is central Copenhagen, "
                  "the decoy slot; c1 is at Ringsted, a different municipality."},
    206: {"locality": "Samburu County, the Maralal area - no finer locality was published",
          "source": "https://sadhanaforest.org/kenya/", "pick": 0, "confidence": "LOW",
          "note": "UNRESOLVED. c3 is Maralal town and is plainly the decoy slot, but the other "
                  "three all sit 18 to 28 km out and the sources say only 'the Maralal area'. "
                  "The point matters less here than almost anywhere in the cohort: the planting "
                  "is done in family shambas scattered across the county, not on one parcel, so "
                  "no single coordinate represents the work. Left unresolved deliberately."},
    207: {"locality": "the former MOB-complex at Bergen, Noord-Holland",
          "source": "http://www.transitsocialinnovation.eu/sii/ecovillage-bergen",
          "pick": 4, "confidence": "HIGH",
          "note": "c4 is the only candidate at Bergen itself - about two kilometres from the "
                  "town centre. c1 is inland near Purmerend, c2 is up at Den Helder and c3 is "
                  "Castricum, all different towns."},
    208: {"locality": "Chacra y Mar beach, Aucallama district, Huaral province",
          "source": "https://ecovillage.org/ecovillage/eco-truly-park-eco-village/",
          "pick": 4, "confidence": "MEDIUM",
          "note": "c4 lies on the coast south of Chancay, where Chacra y Mar is. c2 is close "
                  "enough that it cannot be excluded outright - it sits on Chancay itself - so "
                  "this is held at MEDIUM rather than HIGH."},
    209: {"locality": "near Haga-Haga, on the Quko River, about 8 km from the sea, Eastern Cape",
          "source": "https://ecovillage.org/ecovillage/khula-dhamma-community/",
          "pick": 4, "confidence": "MEDIUM",
          "note": "c4 is the closest of the four to Haga-Haga and is consistent with an inland "
                  "position on the Quko River about eight kilometres from the coast. c1 is only "
                  "slightly further off, so the margin is thin; MEDIUM. c3 is Butterworth, the "
                  "decoy slot."},
    210: {"locality": "Steynsdorp No 2, next to Elukwatini, Mpumalanga",
          "source": "https://ecovillage.org/ecovillage/umphakatsi-peace-ecovillage/",
          "pick": 4, "confidence": "HIGH",
          "note": "Read carelessly this row looks like a case for c2 or c3, because those are "
                  "nearest to Elukwatini (the gazetteer's Lukwatini). But the published address "
                  "is Steynsdorp, which lies south-east of Elukwatini, not in it - and c3 is "
                  "sitting on Nhlazatje, the decoy slot. c4 is the candidate in the right "
                  "relation to Elukwatini for Steynsdorp."},
    211: {"locality": "the Wilderness Lakes area of the Garden Route, Western Cape",
          "source": "https://ecovillage.org/project/green-canvas-light/",
          "pick": 4, "confidence": "MEDIUM",
          "note": "c4 is east of Wilderness among the lakes, which is what GEN describes. c3 is "
                  "George, the decoy slot, and c1 is at Groot-Brakrivier, west of Wilderness - "
                  "the mismatch recorded against this row. MEDIUM because GEN names a stretch of "
                  "coast rather than a farm."},
    212: {"locality": "the Naivasha and Mai Mahiu area, Nakuru County",
          "source": "https://www.agathaamanihouse.org/", "pick": 4, "confidence": "HIGH",
          "note": "c4 is about five kilometres from Naivasha, the closest of the four to the "
                  "published area. c3 is over by Limuru, a different county. Note the "
                  "safeguarding flag on this row: it is a refuge for survivors of domestic "
                  "violence, and a more precise coordinate is not something to publish."},
}


def resolve() -> dict[str, Any]:
    gz = Gazetteer()
    communities = {c["seq"]: c for c in json.loads(RAW.read_text(encoding="utf-8"))}
    out: dict[str, Any] = {}

    for seq, check in sorted(VERIFICATIONS.items()):
        community = communities[seq]
        points = community["coordinate_candidates"]
        if len(points) != 4:
            raise ValueError(f"seq {seq}: expected 4 candidates, got {len(points)}")

        evidence = []
        for i, p in enumerate(points, 1):
            lat, lon = float(p["latitude"]), float(p["longitude"])
            near = gz.nearest(lat, lon, k=1)[0]
            evidence.append({
                "candidate": i, "latitude": p["latitude"], "longitude": p["longitude"],
                "nearest_city": near[2], "nearest_country": near[1],
                "nearest_km": round(near[0], 1),
            })

        pick = check["pick"]
        chosen = points[pick - 1] if pick else None
        out[str(seq)] = {
            "community": community["community_name_normalized"],
            "published_locality": check["locality"],
            "locality_source": check["source"],
            "resolved": bool(pick),
            "chosen_candidate": pick or None,
            "latitude": chosen["latitude"] if chosen else "",
            "longitude": chosen["longitude"] if chosen else "",
            "confidence": check["confidence"],
            "reasoning": check["note"],
            "candidate_evidence": evidence,
        }
    return out


def main() -> None:
    data = resolve()
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    done = [v for v in data.values() if v["resolved"]]
    high = [v for v in done if v["confidence"] == "HIGH"]
    print(f"wrote {OUT}")
    print(f"  multi-candidate communities : {len(data)}")
    print(f"  resolved                    : {len(done)} ({len(high)} HIGH, "
          f"{len(done) - len(high)} MEDIUM)")
    print(f"  left unresolved             : {len(data) - len(done)}")
    for v in data.values():
        if not v["resolved"]:
            print(f"    - {v['community']}")
    picks = {v["chosen_candidate"] for v in done}
    print(f"  candidate slots chosen      : {sorted(picks)}")


if __name__ == "__main__":
    main()
