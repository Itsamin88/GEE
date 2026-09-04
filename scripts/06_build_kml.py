#!/usr/bin/env python3
"""
Build the review KML: 212 communities, each in its own folder holding

  - the community's own placemark (measured context in the description)
  - the EXISTING selected control (moved from the researcher's Paper 2 KML,
    given a distinct marker), directly in the community folder
  - a nested "Rural Control Candidates" folder holding this run's matched
    candidates (up to 15), ranked, colour-coded by tier, for manual review

Inputs:
  - the Stage 2 merged CSV (scripts/03_merge_and_qc.py output)
  - data/existing_selected_controls.json (scripts/05_parse_existing_kml.py output)

Usage:
  python3 scripts/06_build_kml.py <merged_final.csv> <existing_selected.json> \
          [-o OUTPUT.kml] [--title "Study1_Rural Control Candidates"]
"""
import argparse
import csv
import html
import json
import re
import sys
from collections import defaultdict

TIER_STYLE = {'1': 'tier1Candidate', '2': 'tier2Candidate',
             '3': 'tier3Candidate', '': 'tier3Candidate'}
TIER_WORD = {'1': 'Tier 1 - close', '2': 'Tier 2 - adequate',
            '3': 'Tier 3 - best available'}


def xesc(s):
    """Escape plain text for use inside an XML element (not CDATA)."""
    if s is None:
        return ''
    return (str(s).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;'))


def clean_name(s):
    """Undo double/triple HTML-entity-escaping and a known mojibake dash
    found in three of the 212 source names (see scripts/06_build_kml.py
    module docstring history / the merge review). Anything not matching
    those two patterns is left exactly as the CSV has it."""
    if s is None:
        return ''
    for _ in range(3):
        s2 = html.unescape(s)
        if s2 == s:
            break
        s = s2
    s = re.sub(r'â€[\x80-\x9f"\'‘-‟]?', ' - ', s)
    return re.sub(r'\s+', ' ', s).strip()


def cdata(html_text):
    safe = (html_text or '').replace(']]>', ']] >')
    return '<![CDATA[%s]]>' % safe


def fnum(row, key, nd=1):
    v = (row.get(key) or '').strip()
    if not v or v.startswith('n/a'):
        return None
    try:
        x = float(v)
        return round(x, nd)
    except ValueError:
        return None


def placemark(name, lat, lon, style_id, desc_html):
    return (
        '<Placemark>\n'
        '<name>%s</name>\n'
        '<styleUrl>#%s</styleUrl>\n'
        '<description>%s</description>\n'
        '<Point><coordinates>%.6f,%.6f,0</coordinates></Point>\n'
        '</Placemark>\n'
    ) % (xesc(name), style_id, cdata(desc_html), lon, lat)


def community_description(com):
    def row(label, key, unit='', nd=1):
        v = fnum(com, key, nd)
        return '<b>%s:</b> %s%s<br/>' % (label, v, unit) if v is not None else ''

    wb_dist = fnum(com, 'workbook_ctrl_patch_dist_m', 0)
    wb_ok = com.get('workbook_ctrl_eligible')
    wb_d = fnum(com, 'workbook_ctrl_d_value', 3)
    wb_tier = com.get('workbook_ctrl_match_tier')

    parts = [
        '<b>Quartet ID:</b> %s<br/>' % xesc(com['quartet_id']),
        '<b>Coordinates:</b> %.6f, %.6f<br/><br/>' % (
            float(com['latitude']), float(com['longitude'])),
        '<u>Measured context (this settlement)</u><br/>',
        '<b>Köppen group:</b> %s<br/>' % xesc(com.get('koppen_group', '')),
        '<b>Biome:</b> %s<br/>' % xesc(com.get('biome_name', '')),
    ]
    parts.append(row('Elevation', 'elevation_m', ' m'))
    parts.append('<b>Terrain class:</b> %s (slope %s°)<br/>' % (
        xesc(com.get('terrain_class', '')), fnum(com, 'slope_deg')))
    parts.append(row('Tree cover', 'tree_cover_pct', ' %'))
    parts.append(row('Distance to permanent water', 'water_dist_m', ' m', 0))
    pop = fnum(com, 'parent_population', 0)
    parts.append('<b>Population:</b> %s (%s)<br/>' % (
        pop, xesc(com.get('parent_population_basis', ''))))
    parts.append('<b>Rural classification:</b> %s<br/>' % xesc(com.get('smod_label', '')))
    parts.append(row('Protected-area overlap', 'protected_any_pct', ' %'))
    parts.append('<br/><u>Search summary</u><br/>')
    parts.append('<b>Built-up patches in ring:</b> %s<br/>' % com.get('n_patches_found', ''))
    parts.append('<b>Carried into scoring:</b> %s<br/>' % com.get('n_patches_pooled', ''))
    parts.append('<b>Candidates selected:</b> %s (Tier1 %s / Tier2 %s / Tier3 %s)<br/>' % (
        com.get('n_controls_selected', ''), com.get('n_tier1_controls', ''),
        com.get('n_tier2_controls', ''), com.get('n_tier3_controls', '')))
    parts.append('<b>Block grade:</b> %s<br/>' % xesc(com.get('quartet_grade', '')))
    parts.append('<br/><u>Independent re-check of your existing control</u><br/>')
    if wb_dist is not None and wb_dist >= 0:
        parts.append('<b>Nearest detected village patch:</b> %s m away<br/>' % wb_dist)
        parts.append('<b>Would this method accept it:</b> %s<br/>' % xesc(wb_ok))
        parts.append('<b>Its D value / tier:</b> %s / Tier %s<br/>' % (wb_d, xesc(wb_tier)))
    else:
        parts.append('No patch reached the scoring stage for comparison.<br/>')
    return ''.join(parts)


def build_candidate_desc(row):
    tier = row.get('match_tier', '') or ''
    d = fnum(row, 'd_value', 3)
    dist = fnum(row, 'control_distance_km')
    failed = (row.get('criteria_failed') or '').strip() or 'none'
    parts = [
        '<b>Rank:</b> %s of %s<br/>' % (row.get('control_rank'), row.get('n_controls_selected')),
        '<b>Tier:</b> %s<br/>' % xesc(row.get('tier_label')),
        '<b>D value:</b> %s &nbsp; <b>Stars:</b> %s<br/>' % (d, xesc(row.get('star_rating'))),
        '<b>Distance from settlement:</b> %s km<br/>' % dist,
        '<b>Criteria missed:</b> %s<br/><br/>' % xesc(failed),
        '<u>Key covariates (control / settlement)</u><br/>',
        '<b>Köppen:</b> %s / %s &nbsp; <b>Biome match:</b> %s<br/>' % (
            xesc(row.get('koppen_group')), xesc(row.get('parent_koppen_group')),
            xesc(row.get('C2_biome_match'))),
        '<b>Elevation:</b> %s m (parent %s m, diff %s m)<br/>' % (
            fnum(row, 'elevation_m'), fnum(row, 'parent_elevation_m'),
            fnum(row, 'elevation_diff_m')),
        '<b>Terrain:</b> %s (parent %s) &nbsp; C4 tolerant match: %s<br/>' % (
            xesc(row.get('terrain_class')), xesc(row.get('parent_terrain_class')),
            xesc(row.get('C4_terrain_class_tolerant'))),
        '<b>Water distance:</b> %s m (parent %s m, tol %s m)<br/>' % (
            fnum(row, 'water_dist_m', 0), fnum(row, 'parent_water_dist_m', 0),
            fnum(row, 'water_dist_tol_m', 0)),
        '<b>Tree cover:</b> %s%% (parent %s%%, diff %s pp)<br/>' % (
            fnum(row, 'tree_cover_pct'), fnum(row, 'parent_tree_cover_pct'),
            fnum(row, 'tree_cover_diff_pp')),
        '<b>Travel time:</b> %s min (parent %s min)<br/>' % (
            fnum(row, 'travel_time_min'), fnum(row, 'parent_travel_time_min')),
        '<b>Population ratio to settlement:</b> %sx<br/>' % fnum(row, 'population_ratio', 2),
        '<b>Village tests passed:</b> %s/8 (%s)<br/>' % (
            row.get('village_tests_passed'), xesc(row.get('village_class'))),
    ]
    if row.get('is_existing_workbook_control') == 'TRUE':
        parts.append('<br/><b>★ This candidate is within 500 m of your existing '
                     'selected control.</b><br/>')
    return ''.join(parts)


STYLES = '''
<Style id="ecovillagePin"><IconStyle><scale>1.3</scale><Icon>
<href>http://maps.google.com/mapfiles/kml/shapes/homegardenbusiness.png</href>
</Icon></IconStyle><LabelStyle><scale>0.9</scale></LabelStyle></Style>

<Style id="existingControlPin"><IconStyle><color>ffff00ff</color><scale>1.5</scale>
<Icon><href>http://maps.google.com/mapfiles/kml/shapes/target.png</href></Icon>
</IconStyle><LabelStyle><scale>1.0</scale></LabelStyle></Style>

<Style id="tier1Candidate"><IconStyle><scale>1.0</scale>
<Icon><href>http://maps.google.com/mapfiles/kml/paddle/grn-circle.png</href></Icon>
</IconStyle><LabelStyle><scale>0.7</scale></LabelStyle></Style>

<Style id="tier2Candidate"><IconStyle><scale>1.0</scale>
<Icon><href>http://maps.google.com/mapfiles/kml/paddle/ylw-circle.png</href></Icon>
</IconStyle><LabelStyle><scale>0.7</scale></LabelStyle></Style>

<Style id="tier3Candidate"><IconStyle><scale>1.0</scale>
<Icon><href>http://maps.google.com/mapfiles/kml/paddle/red-circle.png</href></Icon>
</IconStyle><LabelStyle><scale>0.7</scale></LabelStyle></Style>
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('csv_path')
    ap.add_argument('existing_json')
    ap.add_argument('-o', '--out', default='Study1_Rural Control Candidates.kml')
    ap.add_argument('--title', default='Study1_Rural Control Candidates')
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.csv_path, encoding='utf-8-sig')))
    existing = json.load(open(args.existing_json, encoding='utf-8'))

    communities = {}
    controls = defaultdict(list)
    for r in rows:
        qid = r['quartet_id']
        if r['row_type'] == 'COMMUNITY':
            communities[qid] = r
        else:
            controls[qid].append(r)

    missing_com = sorted(set(str(q) for q in range(1, 213)) - set(communities), key=int)
    missing_existing = sorted(set(str(q) for q in range(1, 213)) - set(existing.keys()), key=int)
    if missing_com:
        sys.exit('FATAL: CSV missing communities: %s' % missing_com)
    if missing_existing:
        print('WARNING: no existing-control match for quartets: %s' % missing_existing)

    out = []
    out.append('<?xml version="1.0" encoding="UTF-8"?>\n')
    out.append('<kml xmlns="http://www.opengis.net/kml/2.2">\n<Document>\n')
    out.append('<name>%s</name>\n' % xesc(args.title))
    out.append('<description>%s</description>\n' % cdata(
        'Stage 2 conventional-rural control candidates for the 212 settlements. '
        'Each community folder holds the settlement itself, its existing '
        'selected control (target-marker pin, moved from Paper 2), and a '
        'nested "Rural Control Candidates" folder of this run\'s matches, '
        'colour-coded green/yellow/red by Tier 1/2/3. Move the control you '
        'keep up into the community\'s main folder.'))
    out.append(STYLES)

    n_com, n_existing, n_cand = 0, 0, 0
    for qid in sorted(communities, key=int):
        com = communities[qid]
        name = clean_name(com['ecovillage_name'])
        lat, lon = float(com['latitude']), float(com['longitude'])
        cands = sorted(controls.get(qid, []), key=lambda r: int(r['control_rank']))

        out.append('<Folder>\n<name>EV%03d · %s</name>\n' % (int(qid), xesc(name)))

        out.append(placemark('\U0001F3E1 ECOVILLAGE: %s' % name, lat, lon,
                             'ecovillagePin', community_description(com)))
        n_com += 1

        ex = existing.get(qid)
        if ex:
            ex_name = ('⭐ EXISTING SELECTED CONTROL (Paper 2) — '
                      + re.sub(r'^\U0001F3D8️?\s*', '', ex['ctrl_name']))
            ex_desc = (ex['ctrl_description_html'] or '') + (
                '<br/><br/><u>Independent re-check (this run)</u><br/>'
                '<b>Nearest detected patch:</b> %s m<br/>'
                '<b>Would this method accept it:</b> %s<br/>'
                '<b>Its D / tier here:</b> %s / Tier %s<br/>' % (
                    fnum(com, 'workbook_ctrl_patch_dist_m', 0),
                    xesc(com.get('workbook_ctrl_eligible')),
                    fnum(com, 'workbook_ctrl_d_value', 3),
                    xesc(com.get('workbook_ctrl_match_tier'))))
            out.append(placemark(ex_name, ex['ctrl_lat'], ex['ctrl_lon'],
                                 'existingControlPin', ex_desc))
            n_existing += 1

        out.append('<Folder>\n<name>Rural Control Candidates (%d)</name>\n' % len(cands))
        note = ('%s built-up patches found in the search ring; %s carried into scoring; '
               '%s selected.' % (com.get('n_patches_found', '?'),
                                 com.get('n_patches_pooled', '?'), len(cands)))
        if not cands:
            note += (' No candidate passed every hard gate for this settlement '
                     '- see the community placemark for the measured context '
                     '(a Koppen or biome read of "unknown" at the settlement '
                     'itself, common right on a coastline, makes a match '
                     'impossible by construction).')
        out.append('<description>%s</description>\n' % cdata(note))
        for c in cands:
            tier = c.get('match_tier', '')
            style = TIER_STYLE.get(tier, 'tier3Candidate')
            d = fnum(c, 'd_value', 3)
            dist = fnum(c, 'control_distance_km')
            pname = 'CR%02d · %s · D=%s · %s · %s km' % (
                int(c['control_rank']), xesc(c.get('star_rating')), d,
                TIER_WORD.get(tier, xesc(c.get('tier_label'))).split(' - ')[0], dist)
            out.append(placemark(pname, float(c['latitude']), float(c['longitude']),
                                 style, build_candidate_desc(c)))
            n_cand += 1
        out.append('</Folder>\n')
        out.append('</Folder>\n')

    out.append('</Document>\n</kml>\n')

    with open(args.out, 'w', encoding='utf-8') as fh:
        fh.write(''.join(out))

    print('wrote %s' % args.out)
    print('communities: %d   existing-control pins moved: %d   candidate pins: %d'
          % (n_com, n_existing, n_cand))


if __name__ == '__main__':
    main()
