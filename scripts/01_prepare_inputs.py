#!/usr/bin/env python3
"""
Stage 2 control matching - input preparation.

Reads the researcher's Study 1 workbook ("Ecovillages & Controls" sheet, one
quartet per Quartet_ID: 1 Ecovillage row + 3 Site Control rows) and writes:

  data/ecovillages_212.csv                  one row per settlement (the 212)
  data/existing_conventional_rural_controls.csv
                                            the single conventional-rural control
                                            already held for each settlement
  data/ecovillages_212_inline.js            the same 212 settlements as a
                                            JavaScript array, ready to paste into
                                            the Earth Engine script's DATA BLOCK

Usage:
  python3 scripts/01_prepare_inputs.py <Study_1_Final_Ecovillages.xlsx> [outdir]
"""

import csv
import os
import sys

import openpyxl

SHEET = "Ecovillages & Controls"


def clean(v):
    """Text with newlines, tabs and stray control characters collapsed to
    single spaces, so that a cell containing a line break cannot break the
    generated JavaScript DATA BLOCK."""
    if v is None:
        return ""
    s = " ".join(str(v).split())
    return "" if s in {"—", "-", "N/A", "nan", "None"} else s


def to_float(v):
    s = clean(v)
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    xlsx = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), os.pardir, "data")
    outdir = os.path.abspath(outdir)
    os.makedirs(outdir, exist_ok=True)

    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    rows = list(wb[SHEET].values)
    hdr = [clean(h) for h in rows[0]]
    ix = {h: i for i, h in enumerate(hdr)}

    settlements, controls = {}, {}
    for r in rows[1:]:
        qid = r[ix["Quartet_ID"]]
        if qid is None:
            continue
        qid = int(qid)
        row_type = clean(r[ix["Row_Type"]])
        ctl_type = clean(r[ix["Control_Type"]])
        lat, lon = to_float(r[ix["Latitude"]]), to_float(r[ix["Longitude"]])
        if row_type == "Ecovillage":
            koppen = clean(r[ix["C1_Koppen_Match"]])
            # Ecovillage rows carry their OWN Koppen main group, e.g.
            # "B (own classification -- reference for its controls)".
            koppen_group = koppen.split(" ")[0] if koppen[:1] in "ABCDE" else ""
            settlements[qid] = {
                "quartet_id": qid,
                "ecovillage_name": clean(r[ix["Ecovillage_Name"]]),
                "latitude": lat,
                "longitude": lon,
                "population_documentary": clean(r[ix["Population"]]),
                "founding_year": clean(r[ix["E4_Founding_Year"]]).replace(".0", ""),
                "koppen_group_workbook": koppen_group,
                "e8_not_urban_at_founding": clean(r[ix["E8_Not_Urban_at_Founding"]]),
                "e10_no_exogenous_shocks": clean(r[ix["E10_No_Exogenous_Shocks"]]),
                "website": clean(r[ix["Website(s)"]]),
            }
        elif row_type == "Site Control" and ctl_type == "Conventional Rural":
            controls[qid] = {
                "quartet_id": qid,
                "latitude": lat,
                "longitude": lon,
                "d_value_workbook": clean(r[ix["D_Value"]]),
                "star_rating_workbook": clean(r[ix["Star_Rating"]]),
                "all_tier1_pass_workbook": clean(r[ix["All_Tier1_Pass"]]),
                "kept_despite_failing_tier1": clean(r[ix["Kept_Despite_Failing_Tier1"]]),
                "selection_source": clean(r[ix["Selection_Source"]]),
            }

    qids = sorted(settlements)
    print("settlements: %d   existing conventional-rural controls: %d"
          % (len(qids), len(controls)))

    ev_path = os.path.join(outdir, "ecovillages_212.csv")
    ev_cols = ["quartet_id", "ecovillage_name", "latitude", "longitude",
               "population_documentary", "founding_year", "koppen_group_workbook",
               "e8_not_urban_at_founding", "e10_no_exogenous_shocks", "website",
               "existing_control_lat", "existing_control_lon"]
    with open(ev_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=ev_cols)
        w.writeheader()
        for q in qids:
            row = dict(settlements[q])
            c = controls.get(q, {})
            row["existing_control_lat"] = c.get("latitude", "")
            row["existing_control_lon"] = c.get("longitude", "")
            w.writerow(row)

    ctl_path = os.path.join(outdir, "existing_conventional_rural_controls.csv")
    ctl_cols = ["quartet_id", "latitude", "longitude", "d_value_workbook",
                "star_rating_workbook", "all_tier1_pass_workbook",
                "kept_despite_failing_tier1", "selection_source"]
    with open(ctl_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=ctl_cols)
        w.writeheader()
        for q in qids:
            if q in controls:
                w.writerow(controls[q])

    # ---- the inline JavaScript DATA BLOCK -----------------------------------
    js_path = os.path.join(outdir, "ecovillages_212_inline.js")
    with open(js_path, "w", encoding="utf-8") as fh:
        fh.write("// ===== DATA BLOCK - generated by scripts/01_prepare_inputs.py =====\n")
        fh.write("// [quartet_id, name, latitude, longitude, documentary_population,\n")
        fh.write("//  existing_control_lat, existing_control_lon]\n")
        fh.write("// documentary_population < 0 means 'not found' in Stage 1 coding.\n")
        fh.write("var EV_TABLE = [\n")
        for q in qids:
            s, c = settlements[q], controls.get(q, {})
            pop = s["population_documentary"]
            try:
                pop = float(pop)
            except ValueError:
                pop = -1
            name = s["ecovillage_name"].replace("\\", " ").replace("'", "’")
            name = " ".join(name.split())
            clat = c.get("latitude")
            clon = c.get("longitude")
            fh.write("  [%d, '%s', %.6f, %.6f, %g, %s, %s],\n" % (
                q, name, s["latitude"], s["longitude"], pop,
                "%.6f" % clat if clat is not None else "null",
                "%.6f" % clon if clon is not None else "null"))
        fh.write("];\n")

    print("wrote %s\n      %s\n      %s" % (ev_path, ctl_path, js_path))


if __name__ == "__main__":
    main()
