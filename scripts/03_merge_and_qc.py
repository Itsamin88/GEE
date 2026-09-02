#!/usr/bin/env python3
"""
Stage 2 control matching - merge the Earth Engine batch exports into the single
deliverable CSV, and check it.

The Earth Engine script writes one CSV per batch of settlements. This script
concatenates them in settlement order, applies the one rule Earth Engine cannot
express cheaply (a minimum separation between the controls chosen for the same
settlement, so that two halves of one village are never counted as two
controls), re-ranks what survives, and reports what the run produced.

Usage:
  python3 scripts/03_merge_and_qc.py <dir_with_batch_csvs> [-o OUT.csv]
                                     [--min-separation-km 2.0]
                                     [--keep-all]

  --keep-all           do not apply the minimum-separation rule, only report it
  --min-separation-km  how far apart two controls of the same settlement must
                       be to count as two different villages (default 2.0)

Exit code is 1 if a structural check fails (a missing settlement, a control
with no parent, a duplicated control_id).
"""

import argparse
import csv
import glob
import math
import os
import sys
from collections import Counter, defaultdict

EARTH_R_KM = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(min(1.0, math.sqrt(a)))


def fnum(row, key, default=None):
    v = (row.get(key) or "").strip()
    if v in ("", "n/a - settlement row"):
        return default
    try:
        return float(v)
    except ValueError:
        return default


def read_batches(directory):
    paths = sorted(glob.glob(os.path.join(directory, "*.csv")))
    if not paths:
        sys.exit("No CSV files found in %s" % directory)
    header, rows = None, []
    for p in paths:
        with open(p, newline="", encoding="utf-8-sig") as fh:
            rd = csv.DictReader(fh)
            if header is None:
                header = rd.fieldnames
            elif rd.fieldnames != header:
                extra = set(rd.fieldnames or []) ^ set(header)
                sys.exit("Column mismatch in %s: %s" % (p, sorted(extra)))
            rows.extend(rd)
        print("  read %-50s %d rows" % (os.path.basename(p), len(rows)))
    return header, rows


def apply_min_separation(controls_by_qid, min_km, keep_all):
    """Greedy, in rank order: keep a control only if it is at least min_km from
    every control already kept for the same settlement. Two patches that close
    together are the same village seen twice."""
    dropped = []
    for qid, ctls in controls_by_qid.items():
        ctls.sort(key=lambda r: (fnum(r, "control_rank", 1e9),
                                 fnum(r, "d_value", 1e9)))
        kept = []
        for c in ctls:
            lat, lon = fnum(c, "latitude"), fnum(c, "longitude")
            if lat is None or lon is None:
                dropped.append((qid, c, "no coordinates"))
                continue
            clash = None
            for k in kept:
                dkm = haversine_km(lat, lon, fnum(k, "latitude"),
                                   fnum(k, "longitude"))
                if dkm < min_km:
                    clash = (k, dkm)
                    break
            if clash is None:
                kept.append(c)
            else:
                dropped.append((qid, c, "%.2f km from %s"
                                % (clash[1], clash[0].get("control_id"))))
        if not keep_all:
            controls_by_qid[qid] = kept
    return dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("directory")
    ap.add_argument("-o", "--out", default="stage2_rural_controls_FINAL.csv")
    ap.add_argument("--min-separation-km", type=float, default=2.0)
    ap.add_argument("--keep-all", action="store_true")
    ap.add_argument("--rescue-below", type=int, default=3,
                    help="report settlements with fewer than this many "
                         "controls, as a ready-to-paste ONLY_QUARTET_IDS list")
    args = ap.parse_args()

    print("Reading batch exports from %s" % args.directory)
    header, rows = read_batches(args.directory)
    print("Total rows read: %d" % len(rows))

    communities = {}
    controls_by_qid = defaultdict(list)
    for r in rows:
        qid = (r.get("quartet_id") or "").strip()
        if not qid:
            continue
        qid = int(float(qid))
        if r.get("row_type") == "COMMUNITY":
            if qid in communities:
                print("  WARNING duplicate COMMUNITY row for quartet %d" % qid)
            communities[qid] = r
        else:
            controls_by_qid[qid].append(r)

    print("\nSettlements present : %d" % len(communities))
    print("Controls present    : %d"
          % sum(len(v) for v in controls_by_qid.values()))

    problems = []
    missing = sorted(set(range(1, 213)) - set(communities))
    if missing:
        problems.append("settlements missing from the output: %s" % missing)
    orphans = sorted(set(controls_by_qid) - set(communities))
    if orphans:
        problems.append("controls whose settlement row is absent: %s" % orphans)

    # ---- minimum separation between the controls of one settlement ----------
    dropped = apply_min_separation(controls_by_qid, args.min_separation_km,
                                   args.keep_all)
    if dropped:
        verb = "would be dropped" if args.keep_all else "dropped"
        print("\n%d controls %s by the %.1f km minimum-separation rule:"
              % (len(dropped), verb, args.min_separation_km))
        for qid, c, why in dropped[:20]:
            print("   quartet %-4s %-14s  %s"
                  % (qid, c.get("control_id"), why))
        if len(dropped) > 20:
            print("   ... and %d more" % (len(dropped) - 20))

    # ---- re-rank and write ---------------------------------------------------
    out_rows = []
    for qid in sorted(communities):
        com = communities[qid]
        kept = controls_by_qid.get(qid, [])
        com["n_controls_selected"] = len(kept)
        com["n_controls_within_50km"] = sum(
            1 for c in kept
            if (fnum(c, "control_distance_km", 1e9) or 1e9) <= 50)
        out_rows.append(com)
        for i, c in enumerate(kept, start=1):
            c["control_rank"] = i
            c["control_id"] = "EV%03d_CR%02d" % (qid, i)
            c["n_controls_selected"] = len(kept)
            c["n_controls_within_50km"] = com["n_controls_within_50km"]
            out_rows.append(c)

    ids = [r.get("control_id") for r in out_rows]
    dupe_ids = [i for i, n in Counter(ids).items() if n > 1]
    if dupe_ids:
        problems.append("duplicated control_id values: %s" % dupe_ids[:10])

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        w.writerows(out_rows)
    print("\nWrote %s  (%d rows: %d communities + %d controls)"
          % (args.out, len(out_rows), len(communities),
             len(out_rows) - len(communities)))

    # ---- report --------------------------------------------------------------
    counts = Counter(len(controls_by_qid.get(q, [])) for q in communities)
    print("\nControls per settlement")
    for k in sorted(counts):
        print("   %2d controls : %3d settlements" % (k, counts[k]))
    zero = sorted(q for q in communities if not controls_by_qid.get(q))
    if zero:
        print("   settlements with NO eligible control: %s" % zero)
        print("   -> the plan says never to drop these. They stay in the CSV")
        print("      as COMMUNITY rows with n_controls_selected = 0.")

    # The distance ladder, applied where it is actually needed. Re-running all
    # 212 at a wider radius costs four times as much to help a handful; this
    # names the handful.
    short = sorted(q for q in communities
                   if len(controls_by_qid.get(q, [])) < args.rescue_below)
    if short:
        print("\nSettlements with fewer than %d controls: %d"
              % (args.rescue_below, len(short)))
        print("To extend the search for JUST these, per the plan's distance")
        print("ladder, set in the Earth Engine script:")
        print("    SEARCH_MAX_KM:    100,")
        print("    ONLY_QUARTET_IDS: %s," % short)
        print("then merge the extra CSV in with the rest and re-run this.")

    all_ctl = [c for v in controls_by_qid.values() for c in v]
    if all_ctl:
        print("\nMatch tier of the selected controls")
        for t, n in sorted(Counter(c.get("tier_label") for c in all_ctl).items()):
            print("   %-26s %4d" % (t, n))
        print("\nCriterion pass rate across %d selected controls" % len(all_ctl))
        crit = [c for c in header
                if (c.startswith("C") and "_" in c) or c.startswith("V")]
        crit = [c for c in crit if c[0] in "CV" and c[1].isdigit()]
        for c in crit:
            n_true = sum(1 for r in all_ctl if r.get(c) == "TRUE")
            n_eval = sum(1 for r in all_ctl if r.get(c) in ("TRUE", "FALSE"))
            if n_eval:
                print("   %-30s %5.1f%%  (%d/%d)"
                      % (c, 100.0 * n_true / n_eval, n_true, n_eval))
        d = [fnum(r, "d_value") for r in all_ctl]
        d = sorted(x for x in d if x is not None)
        if d:
            print("\nD value: median %.3f   90th pct %.3f   max %.3f"
                  % (d[len(d) // 2], d[int(0.9 * (len(d) - 1))], d[-1]))
        dist = sorted(x for x in (fnum(r, "control_distance_km")
                                  for r in all_ctl) if x is not None)
        if dist:
            print("Distance km: median %.1f   90th pct %.1f   max %.1f"
                  % (dist[len(dist) // 2], dist[int(0.9 * (len(dist) - 1))],
                     dist[-1]))
        n_exist = sum(1 for r in all_ctl
                      if r.get("is_existing_workbook_control") == "TRUE")
        print("Controls that reproduce the workbook's existing "
              "conventional-rural control: %d" % n_exist)

    if problems:
        print("\nCHECKS FAILED:")
        for p in problems:
            print("   - %s" % p)
        sys.exit(1)
    print("\nAll structural checks passed.")


if __name__ == "__main__":
    main()
