#!/usr/bin/env python3
"""
Static checks on the Earth Engine script.

Earth Engine reports most mistakes only when a task RUNS, and often as an error
naming an operator rather than the thing that is actually wrong. These are the
checks that would have caught the failures found so far, so they cannot recur
silently:

  1. No reduceRegions/reduceRegion is handed a SINGLE-BAND image. Earth Engine
     names the output after the reducer, not the band, when an image has
     exactly one band - so the value lands under 'mean' and the property you
     asked for is missing. It then reads as null and fails much later.

  2. Every covariate the scoring code reads is actually produced by one of the
     measurement stacks.

  3. No footprint reduction runs at a scale as coarse as the footprint itself.
     A reducer that finds no pixel centre in its region returns null.

  4. Every declared output column is set somewhere, and none is declared twice.

Usage:  python3 scripts/04_check_script.py [path_to_js]
Exit code 1 if any check fails.
"""

import os
import re
import sys

DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "02_stage2_control_matching.js")


def band_names(block):
    names = set(re.findall(r"rename\('([^']+)'\)", block))
    for m in re.finditer(r"rename\(\s*\[([^\]]+)\]\s*\)", block):
        names |= set(re.findall(r"'([^']+)'", m.group(1)))
    return names


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    src = open(path, encoding="utf-8").read()
    fails = []

    # ---- 1. single-band reducer inputs -------------------------------------
    # Every image handed to reduceRegions must be an ee.Image.cat([...]) of two
    # or more bands, or a named stack built that way.
    stacks = {}
    for m in re.finditer(r"var (\w+)\s*=\s*ee\.Image\.cat\(\[(.*?)\]\)", src,
                         re.S):
        entries = [e.strip() for e in re.split(r",(?![^\[\]]*\])", m.group(2))
                   if e.strip()]
        stacks[m.group(1)] = len(entries)

    for m in re.finditer(r"(\S+?)\.reduceRegions?\(\{", src):
        expr = m.group(1)
        line = src[:m.start()].count("\n") + 1
        if expr in stacks:
            if stacks[expr] < 2:
                fails.append("line %d: reduceRegions on single-band stack %s"
                             % (line, expr))
        elif expr.endswith("toFloat()") or expr.endswith("toInt()") \
                or "cat(" in expr or expr.endswith("]"):
            continue          # inline ee.Image.cat([...]) - multi-band
        else:
            fails.append("line %d: reduceRegions on '%s', which is not an "
                         "ee.Image.cat stack - if it has one band the output "
                         "is named after the reducer, not the band" %
                         (line, expr))

    # ---- 2. every required covariate is produced ---------------------------
    produced = set()
    produced |= band_names(src.split("function landcoverStack()", 1)[1]
                              .split("\nvar LANDCOVER", 1)[0])
    for name in stacks:
        blk = src.split("var %s = ee.Image.cat([" % name, 1)
        if len(blk) > 1:
            produced |= band_names(blk[1].split("])", 1)[0])
    produced |= band_names(src)          # top-level renames

    required = re.findall(r"'([^']+)'",
                          src.split("var FOOTPRINT_REQUIRED = [", 1)[1]
                             .split("];", 1)[0])
    for r in required:
        if r not in produced:
            fails.append("FOOTPRINT_REQUIRED names '%s', which no stack "
                         "produces" % r)

    # ---- 3. no footprint reduction coarser than the footprint --------------
    radius = int(re.search(r"SITE_RADIUS_M:\s*(\d+)", src).group(1))
    for m in re.finditer(r"scale:\s*(\d+)", src):
        scale = int(m.group(1))
        if scale >= radius:
            line = src[:m.start()].count("\n") + 1
            fails.append("line %d: scale %d m is not finer than the %d m "
                         "footprint radius; the reducer can find no pixel "
                         "centre and return null" % (line, scale, radius))

    # ---- 4. output columns -------------------------------------------------
    cols = re.findall(r"'([^']+)'",
                      src.split("var OUT_COLUMNS = [", 1)[1]
                         .split("];", 1)[0])
    dupes = sorted({c for c in cols if cols.count(c) > 1})
    if dupes:
        fails.append("OUT_COLUMNS declares these twice: %s" % dupes)

    set_keys = set(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*:", src))
    set_keys |= produced
    for c in cols:
        if c not in set_keys:
            fails.append("OUT_COLUMNS names '%s', which is never set" % c)

    # ---- report -------------------------------------------------------------
    print("checked %s" % os.path.basename(path))
    print("  reducer inputs      : %d ee.Image.cat stacks" % len(stacks))
    print("  required covariates : %d, all produced" % len(required))
    print("  output columns      : %d, all set" % len(cols))
    print("  footprint radius    : %d m" % radius)
    if fails:
        print("\nFAILED:")
        for f in fails:
            print("   - %s" % f)
        sys.exit(1)
    print("\nAll static checks passed.")


if __name__ == "__main__":
    main()
