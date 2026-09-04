# Building the review KML: what the merge found

`scripts/05_parse_existing_kml.py` and `scripts/06_build_kml.py` turn the 212
per-settlement batch exports plus the researcher's own Paper 2 KML into one
review file: **`Study1_Rural Control Candidates.kml`**. This note records what
the merge surfaced, so it isn't rediscovered by accident later.

## The Paper 2 KML's own numbering doesn't match `quartet_id`

The Paper 2 KML labels each folder `EVnnn: <name>`, and that numbering looks
at first glance like it should equal `quartet_id`. It doesn't, past #49:
`EV051` in that file is quartet 50 ("Green Commune Belica"), and the sequence
runs `EV1`–`EV213` with `EV050` absent — one slot was dropped somewhere in the
researcher's own numbering history, shifting everything after it by one.

The reliable join key is different: every ecovillage placemark's own
description embeds `Ecovillage ID (quartet): N`, and that field matches our
`quartet_id` exactly for all 212, verified with no gaps and no duplicates.
`05_parse_existing_kml.py` joins on that field, not on the folder number.
The control placemark itself is found by its leading 🏘️ marker rather than by
matching the text after it, because seven of the 212 read "Conventional
Village" without the trailing word "Control".

As a second, independent check: every extracted control coordinate was
compared against `data/existing_conventional_rural_controls.csv` (pulled
straight from the original workbook, untouched by any of this). All 212
matched to within 50 m.

## Three ecovillage names carried corrupted text in the source workbook

Not introduced by this pipeline — present in the original `.xlsx` cells, and
inconsistent even within the workbook (one cell reads `&amp;`, another for the
same settlement reads `&amp;amp;`):

| quartet | as stored in the workbook | shown in the KML |
|---|---|---|
| 23 | `Sat Yoga Ashram &amp;amp; Wisdom School` | Sat Yoga Ashram & Wisdom School |
| 91 | `Avalon Organic Gardens &amp;amp; EcoVillage` | Avalon Organic Gardens & EcoVillage |
| 127 | `Eco Aldeia do Vale â€&amp;quot; Instituto Permacultura` | Eco Aldeia do Vale - Instituto Permacultura |

The first two are repeated HTML-entity escaping and unescape cleanly. The
third is a UTF-8 dash mis-decoded as Windows-1252 and then further mangled by
a smart-quote-to-straight-quote pass somewhere upstream — not recoverable to
the exact original character, so `clean_name()` in `06_build_kml.py` collapses
the corrupted run to a plain " - " rather than guess which dash or quote was
intended. All 212 names were checked after cleaning; nothing else was flagged.

## Two settlements found zero candidates, and it's explainable

Quartet 51 (Findhorn, Scotland) and quartet 120 (Assalam, Zanzibar) both sit
close enough to the coast that their own biome or Köppen classification reads
as `unknown` (`biome_num = 0`, or `koppen_group` unmapped) — RESOLVE
Ecoregions and the WorldClim-derived Köppen layer both have small coastal
gaps. C1 and C2 are hard gates requiring an *exact* match to the settlement's
own class, so if the settlement's own class is unknown, no candidate can ever
satisfy it — not a bug, a direct and correctly-predictable consequence of the
hard-gate logic. Both settlements still got their `COMMUNITY` row (with
`n_controls_selected = 0`, per the plan's "never drop the settlement") and
their existing Paper-2 control, moved into their folder as normal; only the
nested candidates folder is empty, with the reason stated in its own
`<description>`.

Quartet 110 (Gulpa Creek) came in at 1 control rather than the target 15 —
a real result of a genuinely sparse rural neighbourhood (rural Victoria,
Australia), not a data problem.

## What went into the review KML

- **3,399 placemarks**: 212 ecovillages, 212 existing controls (moved from
  Paper 2, target-marker pin), 2,975 ranked candidates.
- **212 community folders**, each holding the ecovillage placemark and the
  existing-control placemark directly, and one nested "Rural Control
  Candidates" folder for this run's matches — exactly the layout requested,
  so the existing control is never mistaken for one of the new candidates.
- Candidates are colour-coded green/yellow/red by Tier 1/2/3, named with
  rank, star rating, D value, tier and distance, and their description gives
  every covariate compared against the settlement plus which criteria (if
  any) were missed.
- Every placemark validated: well-formed XML, every coordinate in range,
  every `styleUrl` resolved, zero unescaped `&` outside CDATA content.

## Adding placeholder polygons for manual drawing (scripts/07)

`scripts/07_add_placeholder_polygons.py` takes a *working copy* of the review
KML — one the researcher has already started editing in Google Earth Pro —
and adds a 6-vertex placeholder hexagon, named `Polygon: <Ecovillage name>`,
directly in every community folder that doesn't already have one.

**It edits by text splicing, not by re-parsing and re-writing the tree.**
`xml.etree.ElementTree` reads a `<![CDATA[...]]>` description back out as
plain text, and writing that text back out re-escapes it — silently turning
every working info-bubble (`<b>...</b>`) into dead, literal text
(`&lt;b&gt;...&lt;/b&gt;`). ElementTree is used here only to *read* — folder
names, each settlement's current coordinates, whether a folder already has a
`Polygon:` placemark. The edit itself inserts new text into the original
bytes, so every byte the script doesn't touch is byte-for-byte guaranteed
unchanged, including whatever the researcher has already hand-edited.

A folder already containing a `Polygon: ...` placemark is left completely
alone — that's how a settlement the researcher has already finished (its real
polygon drawn, its chosen controls promoted to the main folder) is recognised
and skipped rather than given a redundant second polygon.

Verified on the first working round-trip (EV001 already carried a real,
hand-drawn 18-vertex polygon and had its coordinates changed and three
candidates promoted to its main folder): the output re-parses as well-formed
XML; EV001 is byte-for-byte identical before and after; every other folder's
original content is byte-for-byte identical with exactly one new hexagon
placemark appended, its nested "Rural Control Candidates" folder completely
untouched; total placemark count matches the input count plus exactly the
number of hexagons added; every new hexagon has exactly 6 vertices at the
configured radius (default 100 m, `--radius-m` to change) from that folder's
*current* ecovillage coordinate — not a value re-derived from the original
CSV, so a settlement whose point has been manually moved gets its hexagon
centred on the moved point.
