#!/usr/bin/env python3
"""
Parse the researcher's Paper 2 KML (Ecovillages + Selected Controls) and pull
out, per settlement, the ecovillage placemark and the "Conventional Village"
control placemark.

The join key is NOT the KML's own "EVnnn:" folder numbering - that numbering
was found to diverge from quartet_id starting at #50 (EV051 in the KML is
quartet_id 50, "Green Commune Belica", not quartet_id 51; the KML runs EV1-
EV213 with EV050 absent, ours runs 1-212 with none absent). The reliable key
is "Ecovillage ID (quartet): N" embedded in every ecovillage placemark's own
description, which is the researcher's own quartet_id and matches ours exactly
(verified: 212 values, one each, covering 1-212 with no gaps or duplicates).

The control placemark is identified by its leading "\U0001F3D8" (house emoji)
marker rather than by matching text after it, because seven of the 212 read
"Conventional Village" without the trailing word "Control".

Usage:
  python3 scripts/05_parse_existing_kml.py <Paper2.kml> [outdir]

Writes data/existing_selected_controls.json: {quartet_id: {...}}
"""
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

NS = {'k': 'http://www.opengis.net/kml/2.2'}
QID_RE = re.compile(r'Ecovillage ID \(quartet\):</b>\s*(\d+)')


def text(el, tag):
    e = el.find(f'k:{tag}', NS)
    return e.text if e is not None else None


def point_coords(pm):
    pt = pm.find('k:Point', NS)
    if pt is None:
        return None
    raw = pt.find('k:coordinates', NS).text.strip()
    lon, lat = raw.split(',')[:2]
    return float(lat), float(lon)


def style_ref(pm):
    e = pm.find('k:styleUrl', NS)
    return e.text.lstrip('#') if e is not None else None


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    kml_path = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), os.pardir, 'data')
    outdir = os.path.abspath(outdir)
    os.makedirs(outdir, exist_ok=True)

    tree = ET.parse(kml_path)
    doc = tree.getroot().find('k:Document', NS)
    folders = doc.findall('k:Folder', NS)
    print('top-level folders:', len(folders))

    out = {}
    problems = []
    for fld in folders:
        placemarks = fld.findall('k:Placemark', NS)
        qid = None
        ev_pm = None
        for pm in placemarks:
            desc = text(pm, 'description') or ''
            m = QID_RE.search(desc)
            if m:
                qid = int(m.group(1))
                ev_pm = pm
                break
        if qid is None:
            problems.append('folder %r has no quartet id' % text(fld, 'name'))
            continue

        ctrl_pm = None
        for pm in placemarks:
            name = text(pm, 'name') or ''
            if name.startswith('\U0001F3D8'):   # house-with-garden emoji
                ctrl_pm = pm
                break
        if ctrl_pm is None:
            problems.append('quartet %d: no control placemark found' % qid)
            continue

        ev_latlon = point_coords(ev_pm)
        ctrl_latlon = point_coords(ctrl_pm)
        if ctrl_latlon is None:
            problems.append('quartet %d: control placemark has no point' % qid)
            continue

        out[qid] = {
            'quartet_id': qid,
            'kml_folder_name': text(fld, 'name'),
            'ecovillage_name': (text(ev_pm, 'name') or '')
                .replace('\U0001F3E1 ECOVILLAGE: ', '').strip(),
            'ev_lat': ev_latlon[0] if ev_latlon else None,
            'ev_lon': ev_latlon[1] if ev_latlon else None,
            'ctrl_name': text(ctrl_pm, 'name'),
            'ctrl_lat': ctrl_latlon[0],
            'ctrl_lon': ctrl_latlon[1],
            'ctrl_description_html': text(ctrl_pm, 'description'),
            'ctrl_style': style_ref(ctrl_pm),
        }

    print('parsed: %d settlements' % len(out))
    if problems:
        print('problems:')
        for p in problems:
            print('  -', p)

    missing = sorted(set(range(1, 213)) - set(out))
    print('quartets 1-212 not found in KML:', missing or 'none')

    out_path = os.path.join(outdir, 'existing_selected_controls.json')
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print('wrote', out_path)


if __name__ == '__main__':
    main()
