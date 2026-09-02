# Stage 2 — conventional-rural control matching: method

This is the method the Earth Engine script in `scripts/02_stage2_control_matching.js`
implements. It follows Stage 2 of *THE SIMPLIFIED PLAN v4.0*, with three
deliberate extensions, each flagged below: up to **15** controls per settlement
rather than three, an explicit **village test** the plan leaves to the eye, and
a stated position on the two criteria that are documentary rather than
observable.

---

## 1. What a control has to be

The plan's Stage 2 says to match on

> identical Köppen main group; same biome; elevation within 300 m; same terrain
> class; distance to permanent surface water within a declared tolerance; 5–50 km
> distant; same country; classified rural; tree cover within 15 percentage
> points; population within a factor of three; NOT inside a protected area; NO
> documented external restoration programme.

Every one of those is a column in the output, with its own TRUE/FALSE status.
Two more are carried because the Study 1 workbook already scored them
(`C4b`/`C4c` ruggedness, `C7` travel time) and because accessibility is an
adjust-for variable in the plan's own causal diagram.

### The criteria, their datasets and their thresholds

| # | Criterion | Layer | Threshold | Role |
|---|---|---|---|---|
| C1 | Köppen main group | WorldClim v1 monthly climatology, Beck et al. (2018) classification logic, ~1 km. Override with your own raster via `CFG.KOPPEN_ASSET`. | identical group (A/B/C/D/E) | **hard** |
| C2 | Biome | `RESOLVE/ECOREGIONS/2017`, `BIOME_NUM` | identical | **hard** |
| C3 | Elevation | `USGS/SRTMGL1_003`, filled above 60 °N with `USGS/GMTED2010_FULL` | ≤ 300 m | soft |
| C4 | Terrain class | slope from the same DEM | same class: flat < 2°, undulating 2–8°, hilly 8–15°, steep ≥ 15° | soft |
| C4b/c | Slope, ruggedness | as above; TRI = SD of elevation in a 3×3 window | ≤ 10°; within 50 % | reported |
| C5 | Distance | great circle | 5–50 km for Tier 1; 5–100 km is a **hard** bound | hard/soft |
| C6 | Distance to permanent water | `JRC/GSW1_4/GlobalSurfaceWater`, occurrence ≥ 80 %, distance transform on a local equidistant grid | within 50 % of the settlement's own value, never stricter than 500 m | soft |
| C7 | Travel time to a city | `Oxford/MAP/accessibility_to_cities_2015_v1_0` | within 50 %, floored at 15 min | soft |
| C8 | Tree cover | `ESA/WorldCover/v200` class 10 (or Dynamic World, configurable) | ≤ 15 percentage points | soft, heaviest weight in *D* |
| C9 | Protected area | `WCMC/WDPA/current/polygons` | ≤ 5 % of the footprint inside | **hard** |
| C10 | External programme | your own polygons; Hansen gain as a separate signal | not inside a supplied polygon | **hard** (see §5) |
| C11 | Country | `FAO/GAUL_SIMPLIFIED_500m/2015/level0` | identical `ADM0_CODE` | **hard** |
| C12 | Rural | `JRC/GHSL/P2023A/GHS_SMOD_V2-0` | class 11–13, < 10 % of footprint urban, < 1500 people/km² | **hard** |
| C13 | Population | `JRC/GHSL/P2023A/GHS_POP` 2020, or the Stage 1 documentary figure | within a factor of 3 | soft |

**Hard** means a candidate that fails is never selected. **Soft** means it is
counted: a Tier-1 control misses none, a Tier-2 control at most one.

**How to read the status columns.** A hard-gate column reads `TRUE` on every
selected control, by construction — everything that failed it was dropped
before selection. That is not a broken column; it is the record that the test
was applied, and it is what lets a reader confirm the gate rather than take it
on trust. The columns that vary between selected controls are the soft ones
(C3, C4, C6, C7, C8, C13) and the reported-only ones (C4b, C4c, C5). Read
`criteria_failed` first: it lists every failure in one cell.

### Measured the same way at both ends

Every covariate is measured over a **circle of 500 m radius** centred on the
site — the settlement point, or the control village centre — from the same
layers, at the same scale, in the same run. This is the point of the design: a
difference between the two arms then cannot be an artefact of how each was
measured. It is also why the script measures the settlement first and the
candidates second, rather than joining pre-computed values from two sources.

The 500 m footprint is a *matching* geometry only. It is not the measurement
geometry of Stage 4, which is the hand-drawn polygon of §7.1 — that is drawn
later, at the settlement, and translated onto whichever controls this script
selects.

---

## 2. Finding villages, not built pixels

The task this script exists to solve is not "find a pixel with a building on
it". It is "find another **village**" — a settlement with a spatial unit of its
own, which is not a bridge, a factory, an airport or any other non-rural use.
Built-up masks alone will happily hand you all four.

**Detection.** Candidates are contiguous patches of `GHS_BUILT_S` built surface
(≥ 3 % of a 100 m cell) that fall in rural `GHS_SMOD` cells, carry some
`GHS_POP` population, and are not standing on permanent water. Before the
patches are cut, a morphological **closing** at 150 m merges the scattered
buildings of one village into one object while leaving genuinely separate
villages apart. Everything runs on a **local azimuthal-equidistant grid**
centred on the settlement, so that 100 m is 100 m and the shape tests below
mean what they say at 64 °N as well as at the equator.

**The eight tests.** Each patch then faces these, and each lands in its own
column:

| Test | What it asks | What it rejects |
|---|---|---|
| **V1** | Is the patch village-sized? 0.5–400 ha holding 0.2–60 ha of built surface | isolated barns; towns |
| **V2** | Is it a *place*, not a *line*? Bounding-box elongation ≤ 4, fill ≥ 0.25, longest side ≤ 2500 m | **bridges, runways**, pipelines, quarry conveyors, roadside ribbon development |
| **V3** | Is the built space **residential**? ≤ 40 % non-residential built surface (`GHS_BUILT_S` nres band) and ≥ 55 % of 10 m built pixels residential (`GHS_BUILT_C` classes 11–15 against 21–25) | **factories**, works, depots, warehouse parks, glasshouse complexes |
| **V4** | Do people actually live there per unit of building? ≥ 3 residents per hectare of built surface, ≤ 25 % bare road surface | **airports**, industrial estates, terminals, motorway interchanges |
| **V5** | Is it on dry ground? ≤ 10 % permanent water under the patch | bridges, piers, dams, stilt platforms |
| **V6** | Is it in open rural land? ≤ 35 % sealed, ≥ 40 % tree/crop/grass/shrub | suburban fringe, sealed sites |
| **V7** | Does it have residents, in village numbers? 10–10 000 | empty structures |
| **V8** | Is it not one of the 212? > 3 km from every study settlement | another intentional community |

V1, V2, V7 and V8 are **mandatory**. Of the eight, at least
`CFG.MIN_VILLAGE_TESTS` (default 7) must pass.

`GHS_BUILT_C` is what makes V3 and V4 possible: it labels 10 m built pixels
*residential* or *non-residential* by building height, and labels bare road
surface separately. An airport is mostly road surface and non-residential
building with no residents; a factory is non-residential building with no
residents; a bridge is a line. Each falls to a different test, which is why
there are eight and not one.

**Candidates are pooled across the whole ring, not nearest-first.** The pool has
to be capped — a settled countryside holds thousands of patches — but capping
it nearest-first collapses a 50 km search into a disc a third that wide. The
first live run picked all 15 controls within 17 km and never considered the
researcher's own existing control at 25.7 km. Controls drawn from a tight disc
are also the ones most spatially autocorrelated with the settlement, which is
the opposite of what the comparison wants. The ring is therefore split into
equal-width distance bands, each capped separately. `n_patches_found`,
`n_patches_pooled` and `patch_pool_capped` report whether the cap bound at all.

**The one rule the script cannot express cheaply** is a minimum separation
*between the controls chosen for one settlement*. Connected components are
already distinct objects, but a large village occasionally splits into two.
`scripts/03_merge_and_qc.py` applies a 2 km minimum separation greedily in rank
order and reports every control it drops. The Earth Engine script selects
`CONTROLS_PER_SETTLEMENT + SELECTION_HEADROOM` so that a block which loses a
duplicate is backfilled rather than left short, and the merge step trims back
to the target afterwards.

---

## 3. Ranking, and the distance ladder

Surviving candidates are ranked on a **weighted standardised distance** *D*.
Each residual is divided by its own declared tolerance, so *D* = 1 means the
covariates use up exactly their allowance on average, and the value is readable
without knowing the sample:

```
D = sqrt( Σ wₖ · (residualₖ / toleranceₖ)² / Σ wₖ )
```

with weights: tree cover 1.50, elevation 1.00, water distance 1.00,
population 1.00, slope 0.75, built fraction 0.75, travel time 0.50. Tree cover
carries the most because the plan names it "the strongest single predictor of
most metrics".

The star bands reproduce the Study 1 workbook: ★★★ *D* < 0.5, ★★ 0.5 ≤ *D* < 1.5,
★ *D* ≥ 1.5.

**Terrain class is judged by a declared rule, not by the bin edge alone.**
`terrain_class` is a hard-binned category, so a settlement near a bin edge
fails C4 against almost every neighbour. Lost Valley sits at 6.6°, 1.4° below
the 8° cut: 12 of its 15 controls "failed" C4 while every one was within 10° of
its slope, and that single brittle test kept the whole block out of Tier 1.
`CFG.C4_MODE` therefore declares which rule counts — `CLASS` (the plan's
literal wording), `CLASS_TOLERANT` (identical, or one class apart with slopes
within 5°; the default), or `SLOPE_TRI` (the Study 1 workbook's own C4: slope
within 10° and ruggedness within 50%). All three land in the CSV whichever is
chosen, so the file can be re-filtered under a different rule without
re-running anything.

**The ladder**, from Stage 2, expressed as a single sort key:

1. **Tier 1** — every soft criterion within tolerance, within 50 km, *D* ≤ 1.0.
   Ordered by *D*.
2. **Tier 2** — at most one soft criterion missed, **or** 50–100 km, *D* ≤ 1.5.
   Ordered by **distance**, because the plan says that once the search is
   extended you take the *closest* qualifying candidates, not the best-scoring
   ones.
3. **Tier 3** — best available. No ceiling on *D*, because the plan is explicit
   that a settlement is never dropped for want of a good comparator. How bad
   "best available" was is visible in `d_value` and
   `d_within_declared_threshold`.

Distance orders the candidates that are genuinely **distance-extended** — the
plan's reasoning ("take the CLOSEST qualifying candidates rather than the
best-scoring ones") is about candidates reached by widening the search. A
control inside the first rung that is Tier 2 only because it missed a tolerance
is not one of those, so match quality orders it instead; otherwise a poor near
match would outrank a good one.

**A block is graded on its best three controls**, not on all fifteen. The
plan's three tiers grade a *quartet* — one settlement against three controls —
and "at most one covariate outside tolerance" is a statement about that trio.
Applied to fifteen it becomes a statement about the fifteenth-best match, so
every block on earth grades Tier 3 and the grade carries no information; the
first live run showed exactly that. `n_tier1_controls`, `n_tier2_controls` and
`n_tier3_controls` describe the rest of the block.

Controls are taken in that order until 15 are found or the eligible pool is
exhausted. **No settlement is ever dropped**: all 212 appear in the output as
`COMMUNITY` rows, including any with `n_controls_selected = 0`.

Extending from three controls to fifteen does not change any criterion. It
changes only how far down the ranked list the script reads. The `control_rank`
column preserves the order, so a three-control analysis is `control_rank <= 3`
and needs no re-run.

---

## 4. Population, and what is actually known

Only **29 of the 212** settlements carry a documentary population figure in the
workbook. The plan's field E1 anticipates this: *"'not found'. The quartet is
matched on the remaining criteria and flagged; report how many."*

The script does slightly better than dropping the criterion. Where a
documentary figure exists, it is compared against the control **village's own**
residents (GHS-POP summed over the built patch) — resident count against
resident count. Where it does not, both arms are estimated from GHS-POP over
the identical 500 m footprint, which is internally consistent even though it is
not the community's own membership. Which of the two applies is stated per row
in `parent_population_basis`, and the count of each is in the merge report.

---

## 5. The two criteria a satellite cannot settle

This is stated plainly because the alternative is a column that looks checked
and is not.

**`protected_area_status` (C9).** WDPA is authoritative for *designated* areas
and silent on informal protection. Two judgement calls are exposed in `CFG`:

- `PA_EXCLUSION_MODE` defaults to `IUCN_I_II`, matching the workbook's own C9.
  Set it to `ANY` for the stricter reading of "not inside a protected area".
  Both percentages are reported on every row either way, so you can re-filter
  the CSV without re-running anything.
- `PA_DESIG_EXCLUDE` defaults to removing **UNESCO-MAB Biosphere Reserves** from
  the protected definition. Their transition zones are inhabited working
  countryside covering whole regions; counting them would exclude much of rural
  Europe for a designation that does not restrict land use there. If you
  disagree, empty the list — it is one line.

**`external_funding_or_programme` (C10).** There is **no global spatial dataset
of funded restoration programmes**, so this criterion cannot be closed from
orbit. The script does two separate things and does not confuse them:

1. It hard-excludes any site inside a polygon you supply in
   `CFG.EXTERNAL_PROGRAMME_ASSET`. If you have a national programme boundary,
   put it there and the criterion becomes real for that country.
2. It reports `restoration_signal_pct` — Hansen tree-cover gain in the footprint
   — and raises `restoration_signal_flag` above 10 % **only when forest loss
   stayed below 5 %**. Gain on its own flags ordinary rotation forestry: a
   control near Lost Valley showed 13 % gain beside 10 % loss, which is a
   clearcut replanted, not a programme. Real afforestation is gain without
   matching loss. This is a **prompt for
   documentary follow-up**, not evidence. It defaults to not excluding anything;
   set `TREAT_RESTORATION_SIGNAL_AS_EXCLUSION` if you want it to.

The practical consequence: C10 turns 15 controls per settlement into a
shortlist you can check by hand, instead of a world you cannot.

---

## 6. Other things worth knowing before you trust the output

- **Köppen.** Earth Engine has no native Köppen-Geiger raster — the same reason
  the plan says "upload as an asset, or join offline". The script reproduces the
  **main groups** from WorldClim v1 monthly climatology using Beck et al.'s
  logic. WorldClim v1 is a 1960–1990 climatology; Beck et al. is 1980–2016.
  Main-group boundaries move little between them, but if you have the published
  raster, set `CFG.KOPPEN_ASSET` and the script uses it instead.
- **Tree cover.** `LANDCOVER_SOURCE` defaults to ESA WorldCover (one static 10 m
  image, cheap to reduce) rather than the Dynamic World the plan names for
  Stage 4 measurement. A matching covariate only has to be consistent across the
  two arms, and it is. Set `DYNAMIC_WORLD` for exact conformance; expect a
  materially longer run.
- **Elevation above 60 °N.** SRTM stops there, so GMTED2010 (~225 m) fills in.
  Sites in Scandinavia therefore carry coarser elevation and slope than sites
  further south. `elevation_m` is still comparable within a quartet, because
  both arms of a quartet are in the same country and so on the same source.
- **Reduction scale against footprint size.** A reducer asked to work on a grid
  as coarse as the region it is reducing over can find no pixel centre inside
  it and returns `null`, and the null surfaces later as an error naming an
  operator rather than the layer. The 500 m footprint is 1 km across, so every
  footprint reduction runs at `CFG.FOOTPRINT_SCALE_M` (100 m, ≥ 78 samples)
  even for the ~1 km accessibility and human-modification layers. Keep that
  invariant if you change `SITE_RADIUS_M`. `RUN_MODE: 'PREFLIGHT'` check 2 runs
  the real measurement path and shows every value, so a null is visible before
  any task is queued.
- **Candidate volume.** A settled countryside can hold thousands of built-up
  patches in a 100 km ring — Lost Valley, Oregon returns over 6000. Reducing
  statistics over all of them is slow enough to break the request. Only the
  nearest `MAX_PATCHES_NEAR` inside 50 km and `MAX_PATCHES_FAR` beyond it are
  carried forward, so both rungs of the distance ladder keep candidates of
  their own. `n_patches_found` in the output reports the size of that pool.
- **What `water_dist_m` actually measures.** The mask is thresholded at GSW's
  own 30 m grid and carried up to the distance-transform grid with a `max`
  reducer, so a cell counts as water if it contains *any*. Doing it the other
  way round — coarsening occurrence and thresholding the average — deletes
  every watercourse narrower than the cell, and did: Lost Valley, 1.6 km from
  the Middle Fork Willamette, first came back 7.25 km from "permanent water".
  Separately, `occurrence >= 80 %` excludes reservoirs with a large seasonal
  drawdown, so in regulated river basins this is distance to water that is
  there *all year* — a defensible reading of "permanent", applied identically
  at both arms, but a choice: lower `WATER_OCCURRENCE_PCT` if seasonal water
  should count. Distances are capped at 30 km and `water_dist_censored` marks
  any pair that hit the cap.
- **Where V3 and V4 do their work.** `GHS_BUILT_S`'s non-residential band and
  `GHS_BUILT_C`'s non-residential classes are frequently zero in small rural
  hamlets, so the residential-dominance tests pass vacuously there. They bite
  where non-residential built surface actually exists — beside works, depots,
  industrial estates and airfields — which is exactly where they are needed.
  V2 (shape) and V7 (residents) carry the load in remote countryside.
- **Asset types.** Earth Engine fails an `ee.Image('…')` on an ImageCollection
  only when the task runs, with `Asset '…' is not an Image`. The types used
  here have been checked against the catalogue: `CSP/HM/GlobalHumanModification`,
  VIIRS, WorldClim, the GHSL layers and ESA WorldCover are **ImageCollections**;
  Oxford accessibility, Hansen, GSW, SRTM and GMTED are **Images**. `RUN_MODE:
  'PREFLIGHT'` re-checks all of them in seconds. Oxford accessibility and
  Hansen are flagged *deprecated* in the catalogue — they still load, and both
  ids sit in `CFG` so a successor can be swapped in without touching the code.
- **The search radius defaults to 50 km**, which is the plan's own first ladder
  step. Extending every settlement to 100 km costs four times as much — search
  area is quadratic in the radius — to help the few that need it. The intended
  workflow is the plan's: run all 212 at 50 km, then re-run only the short ones
  at 100 km via `ONLY_QUARTET_IDS`, which `03_merge_and_qc.py` prints for you.
- **Permanent water is not in the detection seed.** It is 30 m data in a
  different projection from the GHSL layers, so seeding on it means reading and
  resampling 30 m water across the whole search ring in order to reject a
  handful of bridges. The rejection happens later instead, and more cheaply:
  V5 measures permanent water under each surviving patch, and V2 rejects linear
  structures on shape alone. Nothing is lost but the cost.
- **GHS_BUILT_C is a 2018 epoch**; the other GHSL layers are 2020. A village
  built since 2018 is detected (from `GHS_BUILT_S` 2020) but scored on 2018
  characteristics.
