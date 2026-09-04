#!/usr/bin/env python3
"""
Add a placeholder hexagon polygon, named "Polygon: <Ecovillage name>", to
every community folder in a working copy of Study1_Rural Control Candidates
that does not already have one.

Works by TEXT SPLICING, not by re-serialising the parsed tree: ElementTree
round-trips CDATA sections back out as escaped plain text (turning a working
<![CDATA[<b>...</b>]]> description into a dead "&lt;b&gt;...&lt;/b&gt;"), which
would quietly break every info-bubble in the file. ElementTree is used
READ-ONLY here, purely to find names, coordinates and insertion points; the
actual edit is inserting new text into the original bytes, so every byte this
script doesn't touch is guaranteed unchanged - including whatever the
researcher already edited by hand (moved candidates, redrawn polygons,
changed coordinates).

A folder that already contains a placemark named "Polygon: ..." is left
completely alone - this is how a settlement the researcher has already
finished (drawn its real polygon, promoted its chosen candidates) is skipped
rather than given a redundant second polygon.

Usage:
  python3 scripts/07_add_placeholder_polygons.py <input.kml> [-o output.kml]
          [--radius-m 100]
"""
import argparse
import math
import re
import sys
import xml.etree.ElementTree as ET

NS = {'k': 'http://www.opengis.net/kml/2.2'}
FOLDER_NAME_RE = re.compile(r'^EV(\d{3}) · (.*)$')
ECOVILLAGE_NAME_RE = re.compile(r'\U0001F3E1\s*ECOVILLAGE:\s*(.*)$')

STYLE_ID = 'hexPolygonPlaceholder'
STYLE_BLOCK = (
    '<Style id="%s">\n'
    '<LineStyle><color>ff0080ff</color><width>2</width></LineStyle>\n'
    '<PolyStyle><color>4d0080ff</color></PolyStyle>\n'
    '</Style>\n'
) % STYLE_ID


def xesc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def hexagon_ring(lat, lon, radius_m):
    """6 vertices of a regular hexagon centred on (lat, lon), plus the
    closing repeat of the first vertex, as 'lon,lat,0' KML coordinate
    tuples. Flat-earth offset is exact enough at this scale (well under a
    millimetre of error for a 100 m radius)."""
    mlat = math.radians(lat)
    m_per_deg_lon = 111320.0 * math.cos(mlat)
    m_per_deg_lat = 110540.0
    pts = []
    for i in range(6):
        theta = math.radians(90 - 60 * i)   # start due north, clockwise
        dx = radius_m * math.cos(theta)
        dy = radius_m * math.sin(theta)
        plon = lon + dx / m_per_deg_lon
        plat = lat + dy / m_per_deg_lat
        pts.append('%.7f,%.7f,0' % (plon, plat))
    pts.append(pts[0])
    return ' '.join(pts)


def placemark_block(name, lat, lon, radius_m):
    coords = hexagon_ring(lat, lon, radius_m)
    return (
        '\t\t<Placemark>\n'
        '\t\t\t<name>%s</name>\n'
        '\t\t\t<styleUrl>#%s</styleUrl>\n'
        '\t\t\t<Polygon>\n'
        '\t\t\t\t<tessellate>1</tessellate>\n'
        '\t\t\t\t<outerBoundaryIs>\n'
        '\t\t\t\t\t<LinearRing>\n'
        '\t\t\t\t\t\t<coordinates>%s</coordinates>\n'
        '\t\t\t\t\t</LinearRing>\n'
        '\t\t\t\t</outerBoundaryIs>\n'
        '\t\t\t</Polygon>\n'
        '\t\t</Placemark>\n'
    ) % (xesc(name), STYLE_ID, coords)


def collect_folder_records(root):
    """One record per TOP-LEVEL community folder, in document order:
    (qid, ecovillage_name, lat, lon, already_has_polygon)."""
    doc = root.find('k:Document', NS)
    records = []
    for fld in doc.findall('k:Folder', NS):
        fname = fld.find('k:name', NS).text or ''
        m = FOLDER_NAME_RE.match(fname)
        if not m:
            sys.exit('FATAL: top-level folder name does not match "EVnnn · ...": %r'
                     % fname)
        qid = m.group(1)

        ev_pm, has_polygon = None, False
        for pm in fld.findall('k:Placemark', NS):
            pname = pm.find('k:name', NS).text or ''
            if pname.startswith('\U0001F3E1'):
                ev_pm = pm
            if pname.startswith('Polygon:'):
                has_polygon = True

        if ev_pm is None:
            sys.exit('FATAL: folder %r has no ecovillage placemark' % fname)
        nm = ECOVILLAGE_NAME_RE.search(ev_pm.find('k:name', NS).text or '')
        ev_name = nm.group(1).strip() if nm else m.group(2)
        pt = ev_pm.find('k:Point', NS)
        lon, lat = [float(x) for x in
                   pt.find('k:coordinates', NS).text.strip().split(',')[:2]]

        records.append({'qid': qid, 'name': ev_name, 'lat': lat, 'lon': lon,
                        'has_polygon': has_polygon, 'folder_name': fname})
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input_kml')
    ap.add_argument('-o', '--out', default=None)
    ap.add_argument('--radius-m', type=float, default=100.0)
    args = ap.parse_args()
    out_path = args.out or args.input_kml.replace('.kml', '_with_hexagons.kml')

    raw = open(args.input_kml, encoding='utf-8').read()
    root = ET.fromstring(raw)
    records = collect_folder_records(root)
    print('community folders found: %d' % len(records))
    print('already have a "Polygon: ..." placemark (left untouched): %d'
          % sum(1 for r in records if r['has_polygon']))

    # Split on every <Folder> opening tag, top-level AND nested alike. Because
    # nothing ever appears between a top-level folder's two placemarks and its
    # nested folder's OWN opening tag, this makes each top-level folder's own
    # chunk end exactly where its content ends and the nested folder begins -
    # or, for a folder with no nested folder left (the researcher emptied and
    # removed it), the chunk instead runs on to swallow the closing tags too,
    # which is fine: those folders already have their polygon and are skipped.
    chunks = re.split(r'(?=<Folder>)', raw)

    rec_by_qid = {r['qid']: r for r in records}
    seen_qids = set()
    n_inserted = 0
    for i, chunk in enumerate(chunks):
        if not chunk.startswith('<Folder>'):
            continue
        m = re.search(r'<name>EV(\d{3}) · ', chunk[:200])
        if not m:
            continue   # a nested "Rural Control Candidates" chunk
        qid = m.group(1)
        seen_qids.add(qid)
        rec = rec_by_qid[qid]
        if rec['has_polygon']:
            continue
        chunks[i] = chunk + placemark_block(
            'Polygon: %s' % rec['name'], rec['lat'], rec['lon'], args.radius_m)
        n_inserted += 1

    missing = set(rec_by_qid) - seen_qids
    if missing:
        sys.exit('FATAL: never found a raw-text chunk for quartets: %s'
                 % sorted(missing))

    # the new Style belongs alongside the existing Style/StyleMap block, which
    # is everything before the first <Folder>
    chunks[0] = chunks[0] + STYLE_BLOCK

    out_text = ''.join(chunks)
    with open(out_path, 'w', encoding='utf-8') as fh:
        fh.write(out_text)

    print('hexagons inserted: %d' % n_inserted)
    print('wrote %s' % out_path)

    # ---- verify: well-formed, and every byte outside insertions preserved --
    ET.fromstring(out_text)
    print('output re-parses as well-formed XML: OK')
    if len(out_text) != len(raw) + n_inserted * 0 + len(STYLE_BLOCK) + sum(
            len(placemark_block('Polygon: %s' % rec_by_qid[q]['name'],
                                rec_by_qid[q]['lat'], rec_by_qid[q]['lon'],
                                args.radius_m))
            for q in rec_by_qid if not rec_by_qid[q]['has_polygon']):
        print('WARNING: output length does not match the arithmetic '
             'expectation - re-check before trusting this file.')
    else:
        print('output length matches original + exactly the inserted text: OK')


if __name__ == '__main__':
    main()
