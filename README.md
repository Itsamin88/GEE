# Stage 2 — conventional-rural control matching

Earth Engine tooling that finds, for each of the **212 intentional sustainable
communities** of Study 1, up to **15 matched conventional-rural controls**, and
writes them to a single CSV in which every control names the community it
belongs to and carries a TRUE/FALSE status for every matching and exclusion
criterion.

Implements Stage 2 of *THE SIMPLIFIED PLAN v4.0*, from the settlement register
in `Study_1_Final_Ecovillages.xlsx`.

---

## What you get

`stage2_rural_controls_FINAL.csv` — 122 columns, one row per settlement
(`row_type = COMMUNITY`) followed by one row per control belonging to it
(`row_type = CONTROL`):

```
row_type   quartet_id  control_id     control_rank  d_value  tier_label       C1  C2  C3 …
COMMUNITY  3           EV003          0                      Tier 1 - close
CONTROL    3           EV003_CR01     1             0.31     Tier 1 - close   TRUE TRUE TRUE
CONTROL    3           EV003_CR02     2             0.44     Tier 1 - close   TRUE TRUE TRUE
…
```

All 212 settlements appear, including any that found nothing — the plan says a
settlement is never dropped, and that has to be visible in the output rather
than only in the method.

Every criterion is a column:

- **C1–C13** — Köppen group, biome, elevation, terrain class, distance, distance
  to permanent water, travel time, tree cover, protected area, external
  programme, country, rural classification, population.
- **V1–V8** — the village tests, which is how the script keeps bridges,
  factories, airports, industrial estates, dams and road interchanges out of the
  control pool.
- Both the control's value **and** the settlement's value for each covariate, so
  every row can be checked without a lookup.

A hard-gate column (C1, C2, C9, C10, C11, C12, V1–V8) reads `TRUE` on every
selected control by construction — everything failing it was dropped before
selection. The columns that vary are the soft criteria (C3, C4, C6, C7, C8,
C13). `criteria_failed` lists every failure of a row in one cell.

`docs/COLUMN_DICTIONARY.md` documents all 122. `docs/METHODS.md` gives the
thresholds, the datasets, the ranking, and an honest account of the two criteria
a satellite cannot settle.

---

## How to run it

**1 — Regenerate the inputs** (optional; the committed files are current)

```bash
pip install openpyxl
python3 scripts/01_prepare_inputs.py Study_1_Final_Ecovillages.xlsx
```

Writes `data/ecovillages_212.csv`, `data/existing_conventional_rural_controls.csv`
and `data/ecovillages_212_inline.js` — the last of which is already embedded in
the Earth Engine script, so there is nothing to upload.

**2 — Preflight (seconds)**

Paste `scripts/02_stage2_control_matching.js` into the
[Earth Engine Code Editor](https://code.earthengine.google.com/). It opens on
`RUN_MODE: 'PREFLIGHT'`. Run it.

This samples every base layer at one point in a single call. If a dictionary
prints, every asset id, every asset **type** (`ee.Image` against
`ee.ImageCollection`) and every band name is good. Do this first: an asset
mistake otherwise stays invisible until an export task fails, an hour after you
queued it.

**3 — Preview one settlement (a minute)**

```js
RUN_MODE:           'PREVIEW',
PREVIEW_QUARTET_ID: 3,
```

You get the search ring, every built-up patch found, the candidates that were
measured, the eligible ones and the selected ones as separate map layers, plus
the printed table. Do this on two or three settlements in contrasting
landscapes — a dense European countryside, a sparse arid one — and satisfy
yourself the village detector is behaving. It is much cheaper to adjust a
threshold now than after 27 export tasks.

**4 — Export, a few batches at a time**

```js
RUN_MODE:        'EXPORT',
FIRST_BATCH:     0,
BATCHES_PER_RUN: 6,
```

Each run queues 6 tasks (48 settlements) to Google Drive folder
`GEE_Stage2_Controls`, and prints the `FIRST_BATCH` to set next. Five runs
cover all 27 batches: 0, 6, 12, 18, 24.

Both layers of chunking are deliberate. A single export task covering all 212
settlements at a 100 km search radius will time out on the server; and the Code
Editor builds every settlement's expression graph **in the browser** before
anything is sent, so queueing all 27 tasks at once is what makes the page hang.
If your machine handles it comfortably, raise `BATCHES_PER_RUN`; if the page
still labours, lower it.

**5 — Merge and check**

```bash
python3 scripts/03_merge_and_qc.py ~/Drive/GEE_Stage2_Controls \
        -o stage2_rural_controls_FINAL.csv
```

Concatenates the batches in settlement order, applies the 2 km minimum
separation between the controls of one settlement (so two halves of one village
are never counted twice), re-ranks what survives, and reports: controls per
settlement, tier distribution, per-criterion pass rates, the *D* and distance
distributions, how often the search reproduced the workbook's existing control,
and any settlement that found nothing. It exits non-zero if a settlement is
missing, a control is orphaned, or an id is duplicated.

---

## Tuning

Everything lives in the `CFG` block at the top of the Earth Engine script. The
knobs that matter most:

| Setting | Default | Effect |
|---|---|---|
| `CONTROLS_PER_SETTLEMENT` | 15 | How many controls to keep. A three-control analysis needs no re-run — filter `control_rank <= 3`. |
| `SEARCH_MAX_KM` | 100 | The dominant cost. 50 km runs roughly four times faster and still satisfies the plan's first ladder step. |
| `BATCH_SIZE` | 8 | Settlements per export task. Lower it if tasks time out on the server. |
| `BATCHES_PER_RUN` | 6 | Tasks queued per script run. Lower it if the Code Editor page is slow to respond; this is browser-side, not server-side. |
| `LANDCOVER_SOURCE` | `ESA_WORLDCOVER` | `DYNAMIC_WORLD` for exact conformance with the plan's §4.1, at a materially longer run. |
| `KOPPEN_ASSET` | *(empty)* | Point at your uploaded Beck et al. raster to replace the WorldClim-derived main groups. |
| `PA_EXCLUSION_MODE` | `IUCN_I_II` | `ANY` for the stricter reading of "not inside a protected area". Both are reported regardless. |
| `EXTERNAL_PROGRAMME_ASSET` | *(empty)* | Your own polygons of funded restoration programmes; this is the only way C10 becomes a real check. |
| `MIN_VILLAGE_TESTS` | 7 of 8 | How strict the village test is. V1, V2, V7 and V8 are mandatory whatever this is set to. |

If a settlement comes back with too few controls, `n_patches_found` and
`n_candidates_screened` on its `COMMUNITY` row say whether the detector found
nothing or the criteria rejected everything — which are different problems with
different fixes.

---

## Repository layout

```
scripts/01_prepare_inputs.py          workbook  ->  CSV + the script's data block
scripts/02_stage2_control_matching.js the Earth Engine script (paste and run)
scripts/03_merge_and_qc.py            batch CSVs -> the single deliverable, checked
scripts/gen_column_dictionary.py      regenerates docs/COLUMN_DICTIONARY.md
data/ecovillages_212.csv              the 212 settlements
data/existing_conventional_rural_controls.csv
                                      the one control per settlement already held
data/ecovillages_212_inline.js        the same 212, as the script's DATA BLOCK
docs/METHODS.md                       criteria, thresholds, datasets, limits
docs/COLUMN_DICTIONARY.md             all 122 output columns
```

---

## Two things to read before trusting the output

**`external_funding_or_programme` cannot be verified from orbit.** No global
dataset of funded restoration programmes exists. The script hard-excludes sites
inside polygons you supply, and separately reports a Hansen tree-cover-gain
*signal* as a prompt for documentary follow-up. It does not pretend to have
checked the paperwork. See `docs/METHODS.md` §5.

**183 of the 212 settlements have no documentary population.** Those quartets
are matched on a GHSL population estimate measured identically at both arms, and
every row states which basis it used in `parent_population_basis` — which is
what the plan's field E1 asks for.
