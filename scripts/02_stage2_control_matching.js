/**
 * =============================================================================
 *  STAGE 2  -  CONVENTIONAL-RURAL CONTROL MATCHING FOR 212 INTENTIONAL
 *              SUSTAINABLE COMMUNITIES
 * =============================================================================
 *
 *  Study : "A global comparison of vegetation condition and provisioning
 *           capacity in intentional sustainable settlements"
 *           THE SIMPLIFIED PLAN v4.0 - Stage 2 (control matching), with the
 *           strata of section 6.3 and the datasets of section 4.1.
 *  Input : the 212 settlements of Study_1_Final_Ecovillages.xlsx, carried in
 *          the DATA BLOCK at the bottom of this file.
 *  Output: ONE CSV holding all 212 communities and, for each, up to
 *          CFG.CONTROLS_PER_SETTLEMENT eligible conventional-rural controls.
 *          Every control names the community it belongs to and carries a
 *          TRUE/FALSE status column for every matching and exclusion criterion.
 *
 *  WHAT THE SCRIPT DOES, IN ORDER
 *  ------------------------------
 *  For each settlement, inside the 5-100 km search annulus:
 *
 *   A. FIND REAL VILLAGES, NOT JUST BUILT PIXELS.
 *      Candidates are contiguous built-up patches (GHSL built surface, 100 m)
 *      that sit in rural Degree-of-Urbanisation cells, carry resident
 *      population, and are not standing on permanent water. A morphological
 *      closing merges the scattered buildings of one village into one patch.
 *      Each patch then faces eight explicit "is this really a village" tests
 *      (V1-V8) whose job is to reject bridges, factories, industrial estates,
 *      quarries, depots, airports, road interchanges and dams.
 *
 *   B. MEASURE BOTH ARMS ON IDENTICAL GEOMETRY.
 *      Every matching covariate is measured over a circle of CFG.SITE_RADIUS_M
 *      around the settlement centre and around each candidate village centre,
 *      from the same layers, at the same scale, in the same run.
 *
 *   C. TEST EVERY CRITERION AND RECORD ITS STATUS.
 *      C1 Koppen main group   C2 biome            C3 elevation
 *      C4 terrain class       C5 distance         C6 distance to water
 *      C7 travel time         C8 tree cover       C9 protected area
 *      C10 external programme C11 country         C12 rural classification
 *      C13 population
 *
 *   D. RANK AND SELECT under the plan's distance ladder, grading every control
 *      Tier 1 / Tier 2 / Tier 3, and never dropping a settlement.
 *
 *  HOW TO RUN
 *  ----------
 *   1. Paste this whole file into the Earth Engine Code Editor
 *      (https://code.earthengine.google.com/). It is self-contained.
 *   2. Set CFG.PREVIEW_MODE = true and CFG.PREVIEW_QUARTET_ID to one
 *      settlement. Run. Inspect the map layers and the printed table until you
 *      are satisfied the village detector behaves in that landscape.
 *   3. Set CFG.PREVIEW_MODE = false and run again. One export task is queued
 *      per batch of CFG.BATCH_SIZE settlements. Start them from the Tasks tab.
 *   4. Merge the batch CSVs into the single deliverable with
 *      scripts/03_merge_and_qc.py.
 *
 *  WHAT SATELLITES CANNOT SEE - STATED PLAINLY
 *  -------------------------------------------
 *  Two Stage-2 criteria are documentary in the plan (fields G1 and G2) and are
 *  only partly observable from orbit:
 *    - protected_area_status comes from WDPA, authoritative for designated
 *      areas but silent on informal protection;
 *    - external_funding_or_programme has no global spatial dataset at all.
 *      The script excludes anything inside a project polygon you supply in
 *      CFG.EXTERNAL_PROGRAMME_ASSET, and separately reports a satellite
 *      restoration SIGNAL (Hansen tree-cover gain) as a flag for documentary
 *      follow-up. It does not pretend to have checked the paperwork.
 *  Both are reported per control so the researcher can finish the check by
 *  hand on a shortlist instead of on the whole world.
 * =============================================================================
 */

var SCRIPT_VERSION = 'stage2_control_matching v1.0';

// =============================================================================
//  1.  CONFIGURATION  -  every threshold the study declares, in one place
// =============================================================================

var CFG = {

  // ---- run control ---------------------------------------------------------
  // Work through these in order. PREFLIGHT takes seconds and proves every
  // asset id, type and band name; PREVIEW takes a minute and shows you one
  // settlement on the map; only then is EXPORT worth queueing.
  RUN_MODE:                'PREFLIGHT',   // 'PREFLIGHT' | 'PREVIEW' | 'EXPORT'
  PREVIEW_QUARTET_ID:      3,
  // ONE settlement per task. The total compute is the same however it is
  // sliced, but a task that fails, stalls or gets cancelled then costs one
  // settlement rather than four, its name says which settlement, and re-running
  // it is a one-line change. Raise this only if you would rather click fewer
  // times than lose less work.
  BATCH_SIZE:              1,      // settlements per export task
  // The Code Editor builds the whole expression graph for every settlement it
  // touches, in the browser, before anything is sent anywhere. Queueing all
  // 27 tasks in one run means building 212 settlements' graphs at once, which
  // is what makes the page hang. Queue them a few at a time instead: run,
  // raise FIRST_BATCH by BATCHES_PER_RUN, run again. The script tells you
  // exactly what to set next each time.
  FIRST_BATCH:             0,      // first batch this run queues
  BATCHES_PER_RUN:         20,     // how many tasks to queue per script run
  // Run ONLY these settlements, as a single task, ignoring the batching above.
  // Two uses: [3] queues one settlement so you can read its real runtime and
  // EECU cost before committing to all 212; and after a full run, the list of
  // settlements that came up short can be re-run here with SEARCH_MAX_KM
  // raised to 100, which is the plan's distance ladder applied where it is
  // actually needed. Leave empty for a normal run.
  ONLY_QUARTET_IDS:        [],
  DRIVE_FOLDER:            'GEE_Stage2_Controls',
  FILE_PREFIX:             'stage2_rural_controls',

  // ---- how many controls, and how far -------------------------------------
  CONTROLS_PER_SETTLEMENT: 15,
  // Selected on top of that, as headroom. Two controls of one settlement can
  // be two halves of one village; 03_merge_and_qc.py enforces a minimum
  // separation between them and trims back to CONTROLS_PER_SETTLEMENT, so the
  // final block is a full 15 rather than 13.
  SELECTION_HEADROOM:      5,
  SEARCH_MIN_KM:           5,      // plan Stage 2: controls sit 5-50 km away
  SEARCH_TIER1_KM:         50,     // ladder step 1
  // Ladder step 2 extends to 100 km, but the plan extends it only for the
  // settlements that came up short - not for all 212. Search area grows with
  // the SQUARE of this, so 100 km costs four times what 50 km costs on every
  // settlement, to help the few that need it. Run all 212 at 50, then re-run
  // just the short ones at 100 using ONLY_QUARTET_IDS below.
  SEARCH_MAX_KM:           50,

  // ---- geometry on which covariates are measured ---------------------------
  SITE_RADIUS_M:           500,    // identical footprint at both arms
  // Coarsest grid any footprint reduction may use. It MUST stay well below
  // 2 x SITE_RADIUS_M: a reducer working on a grid as coarse as the footprint
  // can find no pixel centre inside it and return null.
  FOOTPRINT_SCALE_M:       100,

  // ---- village detection ---------------------------------------------------
  GHSL_EPOCH:              2020,
  PATCH_SCALE_M:           100,    // detector grid; GHSL's own native scale
  SEED_BUILT_FRAC:         0.03,   // >= 3% of a 100 m cell is built surface
  SEED_POP_PER_CELL:       0.20,   // some resident population in the cell
  CLOSE_RADIUS_M:          150,    // morphological closing: merge one village
  MAX_SMOD_CLASS:          13,     // 11/12/13 = rural (GHS-SMOD)
  MAX_CANDIDATES:          60,     // patches carried into full evaluation
  // A settled countryside can hold thousands of built-up patches in the search
  // ring - Lost Valley, Oregon returns over 6000 at 100 km - and reducing
  // statistics over all of them is slow enough to break the request. So the
  // pool is capped. But capping it "nearest first" across the whole ring
  // collapses the search into a small disc: the first live run picked all 15
  // controls within 17 km of a 50 km ring, and never even considered the
  // researcher's own existing control at 25.7 km. Controls drawn from a tight
  // disc are also the ones most spatially autocorrelated with the settlement,
  // which is the opposite of what a comparison wants. The ring is therefore
  // divided into equal-width distance bands, each capped separately, so every
  // part of it is represented.
  PATCH_BANDS:             4,
  MAX_PATCHES_PER_BAND:    120,
  USE_LOCAL_AEQD:          true,   // local equidistant grid for water distance
  CATEGORICAL_READ_RADIUS_M: 200,  // disc around a patch centre for the
                                   // climate/biome/country read (see
                                   // screenPatches for why it is not the patch)

  // ---- the eight village tests V1-V8 --------------------------------------
  MIN_PATCH_HA:            0.5,
  MAX_PATCH_HA:            400,
  MIN_BUILT_HA:            0.20,   // built SURFACE inside the patch
  MAX_BUILT_HA:            60,
  MAX_ELONGATION:          4.0,    // long side / short side of the bbox
  MIN_BBOX_FILL:           0.25,   // patch area / bbox area
  MAX_PATCH_DIM_M:         2500,   // longest bbox side
  MAX_NRES_FRAC:           0.40,   // non-residential share of built surface
  MIN_RES_SHARE_10M:       0.55,   // residential share, GHS_BUILT_C at 10 m
  MAX_ROAD_PCT_10M:        25,     // road surface inside the footprint
  MIN_POP_PER_BUILT_HA:    3.0,    // residents per hectare of built surface
  MAX_PATCH_WATER_PCT:     10,     // permanent water under the patch
  MAX_FOOTPRINT_WATER_PCT: 40,
  MAX_BUILTUP_PCT:         35,     // sealed share of the 500 m footprint
  MIN_OPEN_LAND_PCT:       40,     // tree + crop + grass + shrub
  MIN_VILLAGE_POP:         10,     // matches the study's own E3 lower bound
  MAX_VILLAGE_POP:         10000,
  EV_EXCLUSION_M:          3000,   // a control may not be another study site
  MIN_VILLAGE_TESTS:       7,      // of 8; V1, V2, V7 and V8 are mandatory

  // ---- matching tolerances (the plan's declared values) --------------------
  TOL_ELEV_M:              300,    // "elevation within 300 m"
  TOL_SLOPE_DEG:           10,     // workbook C4
  TOL_TRI_REL:             0.50,   // workbook C4
  TOL_WATER_REL:           0.50,   // "within a declared tolerance"; workbook C6
  TOL_WATER_FLOOR_M:       500,    // but never stricter than 500 m
  TOL_TRAVEL_REL:          0.50,   // workbook C7
  TOL_TRAVEL_FLOOR_MIN:    15,
  TOL_TREE_PP:             15,     // "tree cover within 15 percentage points"
  TOL_POP_FACTOR:          3,      // "population within a factor of three"
  TOL_BUILT_PP:            10,     // built fraction, percentage points
  TERRAIN_BREAKS_DEG:      [2, 8, 15],   // flat | undulating | hilly | steep
  // Terrain class is a hard-binned category, and a settlement sitting near a
  // bin edge fails it against almost every neighbour. Lost Valley, at 6.6
  // degrees, is 1.4 degrees below the 8-degree cut: 12 of its 15 controls
  // "failed" C4 while every one of them was within 10 degrees of its slope,
  // and that one brittle test kept the whole block out of Tier 1. How C4 is
  // judged is therefore a declared choice:
  //   'CLASS'           identical class - the plan's literal wording
  //   'CLASS_TOLERANT'  identical, OR one class apart with slopes within
  //                     TOL_TERRAIN_ADJACENT_DEG  (default)
  //   'SLOPE_TRI'       the Study 1 workbook's own C4: slope within 10 degrees
  //                     AND ruggedness within 50 per cent
  // All three are reported on every row whichever is chosen, so the CSV can be
  // re-filtered under a different rule without re-running anything.
  C4_MODE:                  'CLASS_TOLERANT',
  TOL_TERRAIN_ADJACENT_DEG: 5,

  // ---- rural classification ------------------------------------------------
  MAX_URBAN_FRACTION_PCT:  10,     // share of footprint in SMOD >= 21
  MAX_RURAL_POP_DENS:      1500,   // people / km2 over the 500 m footprint

  // ---- exclusions ----------------------------------------------------------
  PA_STATUS_KEEP:          ['Designated', 'Inscribed', 'Established'],
  PA_DESIG_EXCLUDE:        ['UNESCO-MAB Biosphere Reserve'],
  PA_EXCLUSION_MODE:       'IUCN_I_II',   // 'IUCN_I_II' (workbook C9) or 'ANY'
  MAX_PA_OVERLAP_PCT:      5,      // tolerated overlap of the footprint
  EXTERNAL_PROGRAMME_ASSET: '',    // your own FeatureCollection of project areas
  // Hansen tree-cover GAIN on its own flags ordinary rotation forestry: a
  // control near Lost Valley showed 13% gain beside 10% loss, which is a
  // clearcut replanted, not a restoration programme. Real afforestation is
  // gain WITHOUT matching loss, so both bounds have to hold.
  RESTORATION_GAIN_PCT:    10,     // Hansen gain share that raises the flag
  RESTORATION_MAX_LOSS_PCT: 5,     // ...but only if loss stayed below this
  TREAT_RESTORATION_SIGNAL_AS_EXCLUSION: false,

  // ---- weights of the standardised distance D ------------------------------
  // Each residual is expressed as a fraction of its own tolerance, so D = 1
  // means "on average the covariates use up exactly their allowance".
  W_ELEV: 1.00, W_WATER: 1.00, W_TREE: 1.50, W_POP: 1.00,
  W_SLOPE: 0.75, W_TRAVEL: 0.50, W_BUILT: 0.75,
  D_MAX_TIER1: 1.0, D_MAX_TIER2: 1.5, D_MAX_TIER3: 2.5,

  // ---- data sources --------------------------------------------------------
  LANDCOVER_SOURCE:  'ESA_WORLDCOVER',   // or 'DYNAMIC_WORLD'
  DW_START:          '2021-01-01',
  DW_END:            '2023-01-01',
  KOPPEN_ASSET:      '',   // optional: your uploaded Beck et al. 1 km raster
  KOPPEN_ASSET_IS_MAIN_GROUP: false,     // true if it already holds 1..5
  // Both of these are Images, and both are flagged 'deprecated' in the Earth
  // Engine catalogue - they still load, but they are named here so you can
  // swap in a successor without hunting through the code.
  ASSET_TRAVEL:      'Oxford/MAP/accessibility_to_cities_2015_v1_0',
  ASSET_HANSEN:      'UMD/hansen/global_forest_change_2024_v1_12',
  // GSW occurrence >= 80% counts as permanent. Note what that excludes:
  // reservoirs with a large seasonal drawdown spend part of the year dry and
  // can fall below it, so in regulated river basins the measure is distance to
  // water that is there ALL year. That is a defensible reading of "permanent",
  // and it is applied identically at both arms, but it is a choice - lower it
  // if seasonal water should count.
  WATER_OCCURRENCE_PCT: 80,
  // 120 m keeps rivers sharp; 256 cells of it reach 30.7 km, which is well
  // past any distance the +/-50% tolerance can still discriminate.
  WATER_DT_SCALE_M:  120,
  WATER_DT_NEIGHBOURHOOD_PX: 256,
  WATER_DIST_MAX_M:  30000,

  // ---- misc ----------------------------------------------------------------
  GEOM_MAXERR:       10,
  MAX_PIXELS:        1e9,
  TILE_SCALE:        4
};

var RUN_DATE = ee.Date(Date.now()).format('YYYY-MM-dd');

// =============================================================================
//  2.  LOOK-UP TABLES  (indexed server-side by a computed number)
// =============================================================================

var TF            = ['FALSE', 'TRUE'];
var KOPPEN_LETTER = ['unknown', 'A', 'B', 'C', 'D', 'E'];
var TERRAIN_NAME  = ['flat', 'undulating', 'hilly', 'steep'];
var STAR_NAME     = ['1-star', '2-star', '3-star'];
var TIER_NAME     = ['not eligible', 'Tier 1 - close', 'Tier 2 - adequate',
                     'Tier 3 - best available'];
var VILLAGE_CLASS = ['C - weak', 'C - weak', 'C - weak', 'C - weak', 'C - weak',
                     'C - weak', 'B - probable', 'B - probable', 'A - strong'];
var SMOD_LABEL    = ['water', 'very low density rural', 'low density rural',
                     'rural cluster', 'suburban or peri-urban',
                     'semi-dense urban cluster', 'dense urban cluster',
                     'urban centre'];
var BIOME_NAME = ['unknown',
  'Tropical & Subtropical Moist Broadleaf Forests',
  'Tropical & Subtropical Dry Broadleaf Forests',
  'Tropical & Subtropical Coniferous Forests',
  'Temperate Broadleaf & Mixed Forests',
  'Temperate Conifer Forests',
  'Boreal Forests/Taiga',
  'Tropical & Subtropical Grasslands, Savannas & Shrublands',
  'Temperate Grasslands, Savannas & Shrublands',
  'Flooded Grasslands & Savannas',
  'Montane Grasslands & Shrublands',
  'Tundra',
  'Mediterranean Forests, Woodlands & Scrub',
  'Deserts & Xeric Shrublands',
  'Mangroves'];

function lut(list, index) {
  return ee.List(list).get(ee.Number(index).round().max(0).min(list.length - 1));
}
function tf(flag) { return lut(TF, flag); }

/** SMOD codes are sparse (10,11,12,13,21,22,23,30); map them onto 0..7. */
function smodLabel(code) {
  var c = ee.Number(code);
  var idx = c.eq(11).multiply(1).add(c.eq(12).multiply(2))
             .add(c.eq(13).multiply(3)).add(c.eq(21).multiply(4))
             .add(c.eq(22).multiply(5)).add(c.eq(23).multiply(6))
             .add(c.eq(30).multiply(7));
  return lut(SMOD_LABEL, idx);
}

/** '<name>;' when the criterion FAILED, '' when it passed. */
function failTag(name, failFlag) {
  var s = name + ';';
  return ee.String(s).slice(0, ee.Number(failFlag).multiply(s.length));
}

function num(f, key) { return ee.Number(f.get(key)); }

/**
 * The first value of a property across a collection, or a fallback when the
 * collection is empty. aggregate_* returns null on an empty collection, and a
 * null does not fail where it is made - it fails later, in whatever arithmetic
 * first touches it. Appending the fallback to the list makes that impossible.
 */
function firstOr(fc, prop, fallback) {
  return ee.Number(ee.List(fc.aggregate_array(prop)).add(fallback).get(0));
}

// Properties a candidate must actually carry before any arithmetic touches it.
// A reducer that finds no pixel in a region returns null rather than failing,
// and the null only surfaces later, as an error naming an operator rather than
// the layer. Filtering on ee.Filter.notNull turns "the whole settlement died"
// into "one odd patch was dropped".
var PATCH_REQUIRED = ['s_built_frac', 's_pop_dens', 'surface_water_pct',
  's_elev', 'g_koppen', 'g_biome', 'g_adm0'];

var FOOTPRINT_REQUIRED = ['tree_cover_pct', 'cropland_pct', 'grass_shrub_pct',
  'builtup_pct', 'bare_pct', 'residential_built_pct_10m',
  'nonres_built_pct_10m', 'road_surface_pct_10m', 'elevation_m', 'slope_deg',
  'tri', 'forest_gain_pct', 'forest_loss_pct', 'footprint_water_pct',
  'protected_any_pct', 'protected_iucn12_pct', 'study_site_pct',
  'ext_programme_pct', 'pop_density_km2', 'built_frac_pct',
  'nonresidential_built_pct', 'urban_fraction_pct', 'water_dist_m',
  'travel_time_min', 'human_modification', 'nightlight_radiance',
  'koppen_group', 'biome_num', 'adm0_code', 'smod_class'];

// =============================================================================
//  3.  BASE LAYERS  -  built once, all lazy
// =============================================================================

function ghslEpoch(id, year) {
  return ee.ImageCollection(id)
           .filterDate(year + '-01-01', year + '-12-31')
           .mosaic();
}

// --- settlement structure ----------------------------------------------------
var GHS_BUILT   = ghslEpoch('JRC/GHSL/P2023A/GHS_BUILT_S', CFG.GHSL_EPOCH);
var BUILT_TOTAL = GHS_BUILT.select('built_surface').unmask(0);      // m2 / cell
var BUILT_NRES  = GHS_BUILT.select('built_surface_nres').unmask(0);
var BUILT_FRAC  = BUILT_TOTAL.divide(10000);                        // 0..1
var NRES_FRAC   = BUILT_NRES.divide(BUILT_TOTAL.max(1));            // 0..1
var GHS_POP     = ghslEpoch('JRC/GHSL/P2023A/GHS_POP', CFG.GHSL_EPOCH)
                    .select('population_count').unmask(0);
var POP_DENS    = GHS_POP.multiply(100);                            // people/km2
var GHS_SMOD    = ghslEpoch('JRC/GHSL/P2023A/GHS_SMOD_V2-0', CFG.GHSL_EPOCH)
                    .select('smod_code').unmask(10);
var SMOD_URBAN  = GHS_SMOD.gte(21);

// GHSL P2023A is stored in World Mollweide at 100 m: an equal-area grid whose
// units are metres. Running the patch detector in it costs no reprojection at
// all, which is the single biggest saving available in this script.
var GHSL_GRID   = BUILT_TOTAL.projection();

// GHS_BUILT_C, 10 m, 2018. This is the layer that separates RESIDENTIAL built
// space from NON-RESIDENTIAL built space and from bare road surface, and it is
// what lets the script tell a village apart from a works, a depot or an
// airfield. Class codes: 5 = road surfaces, 11-15 = residential by building
// height, 21-25 = non-residential by building height.
var BUILT_C  = ee.ImageCollection('JRC/GHSL/P2023A/GHS_BUILT_C')
                 .mosaic().select('built_characteristics').unmask(0);
var BC_RES   = BUILT_C.gte(11).and(BUILT_C.lte(15));
var BC_NRES  = BUILT_C.gte(21).and(BUILT_C.lte(25));
var BC_ROAD  = BUILT_C.eq(5);

// --- terrain -----------------------------------------------------------------
// SRTM stops at 60 N / 56 S. GMTED2010 fills the high latitudes so that no
// settlement silently loses its elevation, slope and terrain class.
var SRTM  = ee.Image('USGS/SRTMGL1_003').select('elevation').toFloat();
var GMTED = ee.Image('USGS/GMTED2010_FULL').select('mea').toFloat()
              .rename('elevation');
var DEM   = ee.ImageCollection([GMTED, SRTM]).mosaic()
              .setDefaultProjection(SRTM.projection()).rename('elevation_m');
var SLOPE = ee.Terrain.slope(DEM).rename('slope_deg');
var TRI   = DEM.reduceNeighborhood(ee.Reducer.stdDev(), ee.Kernel.square(1))
               .rename('tri');

// --- water -------------------------------------------------------------------
// The threshold is applied at the layer's OWN 30 m grid, pinned with
// reproject, and only then aggregated to whatever grid a consumer asks for.
// Order matters here and it is not a detail: aggregating occurrence FIRST and
// thresholding after erases every watercourse narrower than the coarse cell,
// because a 240 m cell holding a 70 m river averages to about 30% occurrence
// and fails a ">= 80%" test. That is how Lost Valley, 1.6 km from the Middle
// Fork Willamette, came back 7.25 km from "permanent water".
var GSW_OCCURRENCE = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('occurrence');
var PERM_WATER = GSW_OCCURRENCE.unmask(0).gte(CFG.WATER_OCCURRENCE_PCT)
                   .reproject(GSW_OCCURRENCE.projection())
                   .rename('perm_water');

// --- climate: Koppen main group ----------------------------------------------
/**
 * Koppen main groups A/B/C/D/E from the WorldClim v1 monthly climatology,
 * following the classification logic of Beck et al. (2018). Earth Engine
 * carries no native Koppen-Geiger raster, which is exactly why the plan
 * (section 4.1) says "upload as an asset, or join offline from the published
 * raster". Set CFG.KOPPEN_ASSET to use your own upload; otherwise the main
 * groups are reproduced here directly, at about 1 km.
 */
function koppenMainGroupImage() {
  if (CFG.KOPPEN_ASSET) {
    var k = ee.Image(CFG.KOPPEN_ASSET).select(0);
    if (CFG.KOPPEN_ASSET_IS_MAIN_GROUP) { return k.rename('koppen_group'); }
    // Beck et al. 30-class coding: 1-3 = A, 4-7 = B, 8-16 = C, 17-28 = D,
    // 29-30 = E.
    return ee.Image(0)
      .where(k.gte(1).and(k.lte(3)),   1)
      .where(k.gte(4).and(k.lte(7)),   2)
      .where(k.gte(8).and(k.lte(16)),  3)
      .where(k.gte(17).and(k.lte(28)), 4)
      .where(k.gte(29).and(k.lte(30)), 5)
      .rename('koppen_group');
  }

  var wc   = ee.ImageCollection('WORLDCLIM/V1/MONTHLY');
  var tavg = ee.ImageCollection(wc.select('tavg').map(function (i) {
               return i.multiply(0.1).copyProperties(i, ['month']);
             }));
  var tHot = tavg.max(), tCold = tavg.min(), mat = tavg.mean();

  var pAnn    = wc.select('prec').sum();
  var pAprSep = wc.select('prec')
                  .filter(ee.Filter.and(ee.Filter.gte('month', 4),
                                        ee.Filter.lte('month', 9))).sum();
  var north   = ee.Image.pixelLonLat().select('latitude').gte(0);
  var pSummer = pAprSep.multiply(north)
                  .add(pAnn.subtract(pAprSep).multiply(north.not()));
  var denom   = pAnn.max(1);
  var fSummer = pSummer.divide(denom);
  var fWinter = pAnn.subtract(pSummer).divide(denom);

  // aridity threshold Pth of Beck et al.; arid if Pann < 10 * Pth
  var pth = mat.multiply(2)
              .add(ee.Image(28).multiply(fSummer.gte(0.7)))
              .add(ee.Image(14).multiply(fSummer.lt(0.7).and(fWinter.lt(0.7))));

  var isB  = pAnn.lt(pth.multiply(10));
  var isA  = tCold.gte(18).and(isB.not());
  var isE  = tHot.lt(10).and(isB.not()).and(isA.not());
  var rest = isB.not().and(isA.not()).and(isE.not());
  var isC  = tHot.gte(10).and(tCold.gt(0)).and(tCold.lt(18)).and(rest);
  var isD  = tHot.gte(10).and(tCold.lte(0)).and(rest);

  return ee.Image(0)
    .where(isA, 1).where(isB, 2).where(isC, 3).where(isD, 4).where(isE, 5)
    .rename('koppen_group');
}
var KOPPEN = koppenMainGroupImage().unmask(0);

// --- land cover ---------------------------------------------------------------
/**
 * Six composition bands, in per cent of whatever footprint they are reduced
 * over. Both sources are internally consistent across the two arms, which is
 * all a matching covariate has to be. ESA WorldCover is one static 10 m image
 * and is far cheaper to reduce; Dynamic World is the source the measurement
 * stage (section 4.1) itself uses, and is offered for exact conformance.
 */
function landcoverStack() {
  if (CFG.LANDCOVER_SOURCE === 'DYNAMIC_WORLD') {
    var dw = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1')
               .filterDate(CFG.DW_START, CFG.DW_END).mean();
    return ee.Image.cat([
      dw.select('trees').multiply(100).rename('tree_cover_pct'),
      dw.select('crops').multiply(100).rename('cropland_pct'),
      dw.select('grass').add(dw.select('shrub_and_scrub')).multiply(100)
        .rename('grass_shrub_pct'),
      dw.select('built').multiply(100).rename('builtup_pct'),
      dw.select('water').multiply(100).rename('lc_water_pct'),
      dw.select('bare').multiply(100).rename('bare_pct')
    ]).unmask(0).toFloat();
  }
  var m = ee.ImageCollection('ESA/WorldCover/v200').mosaic().select('Map');
  return ee.Image.cat([
    m.eq(10).multiply(100).rename('tree_cover_pct'),
    m.eq(40).multiply(100).rename('cropland_pct'),
    m.eq(20).or(m.eq(30)).multiply(100).rename('grass_shrub_pct'),
    m.eq(50).multiply(100).rename('builtup_pct'),
    m.eq(80).multiply(100).rename('lc_water_pct'),
    m.eq(60).or(m.eq(100)).multiply(100).rename('bare_pct')
  ]).unmask(0).toFloat();
}
var LANDCOVER = landcoverStack();

// --- accessibility, human pressure, disturbance ------------------------------
// Asset TYPE matters here, and the two kinds are not interchangeable:
// ee.Image() on an ImageCollection fails at task time with "Asset ... is not an
// Image", which is not visible until the export runs. Verified types:
//   Image            Oxford accessibility, Hansen, GSW, SRTM, GMTED
//   ImageCollection  CSP human modification, VIIRS, WorldClim, GHSL, WorldCover
// Run CFG.RUN_MODE = 'PREFLIGHT' to check every one of them in a few seconds
// before queueing any export.
var TRAVEL = ee.Image(CFG.ASSET_TRAVEL)
               .select('accessibility').unmask(0).rename('travel_time_min');
var GHM    = ee.ImageCollection('CSP/HM/GlobalHumanModification')
               .mosaic().select('gHM')
               .unmask(0).rename('human_modification');
var VIIRS  = ee.ImageCollection('NOAA/VIIRS/DNB/ANNUAL_V22')
               .filterDate('2021-01-01', '2022-12-31').select('average')
               .mean().unmask(0).rename('nightlight_radiance');
var HANSEN = ee.Image(CFG.ASSET_HANSEN);
var GAIN   = HANSEN.select('gain').unmask(0);
var LOSS   = HANSEN.select('loss').unmask(0);

// =============================================================================
//  4.  PER-SITE HELPERS
// =============================================================================

/** A local azimuthal-equidistant grid, so that metres are really metres. */
function localGrid(lon, lat, scaleM) {
  if (!CFG.USE_LOCAL_AEQD) {
    return ee.Projection('EPSG:4326').atScale(scaleM);
  }
  var wkt =
    'PROJCS["AEQD_local",' +
      'GEOGCS["WGS 84",' +
        'DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],' +
        'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],' +
      'PROJECTION["Azimuthal_Equidistant"],' +
      'PARAMETER["latitude_of_center",' + lat + '],' +
      'PARAMETER["longitude_of_center",' + lon + '],' +
      'PARAMETER["false_easting",0],PARAMETER["false_northing",0],' +
      'UNIT["Meter",1]]';
  return ee.Projection(wkt).atScale(scaleM);
}

/**
 * Distance to permanent surface water, in metres, on a local metric grid.
 *
 * The 30 m water mask is carried up to the transform's grid with a MAX
 * reducer, so a cell counts as water if it contains ANY permanent water. Using
 * reproject alone would re-threshold the averaged occurrence and delete every
 * river narrower than the cell.
 */
function waterDistanceImage(lon, lat) {
  var grid = localGrid(lon, lat, CFG.WATER_DT_SCALE_M);
  var water = PERM_WATER
    .reduceResolution({reducer: ee.Reducer.max(), maxPixels: 256})
    .reproject(grid);
  return water
    .fastDistanceTransform(CFG.WATER_DT_NEIGHBOURHOOD_PX, 'pixels',
                           'squared_euclidean')
    .sqrt().multiply(CFG.WATER_DT_SCALE_M)
    .min(CFG.WATER_DIST_MAX_M)
    .rename('water_dist_m').toFloat();
}

/** Protected areas, cut to the search region so nothing global is painted. */
function protectedAreaImage(region) {
  var wdpa = ee.FeatureCollection('WCMC/WDPA/current/polygons')
               .filterBounds(region)
               .filter(ee.Filter.inList('STATUS', CFG.PA_STATUS_KEEP));
  if (CFG.PA_DESIG_EXCLUDE.length) {
    wdpa = wdpa.filter(ee.Filter.inList('DESIG_ENG',
                                        CFG.PA_DESIG_EXCLUDE).not());
  }
  var iucn = wdpa.filter(ee.Filter.inList('IUCN_CAT', ['Ia', 'Ib', 'II']));
  return ee.Image.cat([
    ee.Image(0).byte().paint(wdpa, 1).multiply(100)
      .rename('protected_any_pct'),
    ee.Image(0).byte().paint(iucn, 1).multiply(100)
      .rename('protected_iucn12_pct')
  ]).toFloat();
}

/** Biome and country as rasters, cut to the search region. */
function contextImage(region) {
  var eco = ee.FeatureCollection('RESOLVE/ECOREGIONS/2017').filterBounds(region);
  var adm = ee.FeatureCollection('FAO/GAUL_SIMPLIFIED_500m/2015/level0')
              .filterBounds(region);
  return ee.Image.cat([
    ee.Image(0).int().paint(eco, 'BIOME_NUM').rename('biome_num'),
    ee.Image(0).int().paint(adm, 'ADM0_CODE').rename('adm0_code')
  ]);
}

/** The 212 study sites, buffered: a control may not be another study site. */
var _STUDY_SITE_IMG = null;
function studySiteImage() {
  if (_STUDY_SITE_IMG !== null) { return _STUDY_SITE_IMG; }
  var pts = [];
  for (var i = 0; i < EV_TABLE.length; i++) {
    pts.push(ee.Feature(ee.Geometry.Point([EV_TABLE[i][3], EV_TABLE[i][2]])
                          .buffer(CFG.EV_EXCLUSION_M)));
  }
  _STUDY_SITE_IMG = ee.Image(0).byte()
    .paint(ee.FeatureCollection(pts), 1).multiply(100)
    .rename('study_site_pct').toFloat();
  return _STUDY_SITE_IMG;
}

/** Documented restoration/funding programmes, if the researcher supplies them. */
var _EXT_PROG_IMG = null;
function externalProgrammeImage() {
  if (_EXT_PROG_IMG !== null) { return _EXT_PROG_IMG; }
  var fc = CFG.EXTERNAL_PROGRAMME_ASSET
    ? ee.FeatureCollection(CFG.EXTERNAL_PROGRAMME_ASSET)
    : ee.FeatureCollection([]);
  _EXT_PROG_IMG = ee.Image(0).byte().paint(fc, 1).multiply(100)
    .rename('ext_programme_pct').toFloat();
  return _EXT_PROG_IMG;
}

function terrainClassNumber(slopeDeg) {
  var b = CFG.TERRAIN_BREAKS_DEG, s = ee.Number(slopeDeg);
  return s.gte(b[0]).add(s.gte(b[1])).add(s.gte(b[2]));
}

/** Residents inside the measured footprint. */
function footprintPopulation(f) {
  var areaKm2 = Math.PI * CFG.SITE_RADIUS_M * CFG.SITE_RADIUS_M / 1e6;
  return num(f, 'pop_density_km2').multiply(areaKm2);
}

// =============================================================================
//  5.  STAGE A  -  FIND CANDIDATE VILLAGES AROUND ONE SETTLEMENT
// =============================================================================

/** Contiguous rural built-up patches inside the search annulus. */
function findPatches(ring) {

  // Rural, inhabited, built-up ground.
  //
  // Every layer here is GHSL P2023A, which is stored in World Mollweide at
  // 100 m - an EQUAL-AREA METRIC grid. So the detector runs in that grid
  // directly and reprojects NOTHING. The earlier version reprojected the seed
  // into a per-site azimuthal-equidistant grid, which forced Earth Engine to
  // resample every input across the whole search area, and that alone was most
  // of the cost of the run.
  //
  // Permanent water is deliberately NOT in the seed. It is a 30 m layer in a
  // different projection, so including it meant reading and resampling 30 m
  // water across tens of thousands of square kilometres to reject a handful of
  // bridges. The same rejection happens later, for free: V5 measures water
  // under each surviving patch (a few hundred of them, not a whole region) and
  // V2 rejects linear structures on shape alone.
  // setDefaultProjection, NOT reproject: it declares which grid this image
  // lives on so the focal radii below are honest metres and the vectoriser
  // knows where the pixels are, without resampling anything.
  var seed = BUILT_FRAC.gte(CFG.SEED_BUILT_FRAC)
               .and(GHS_SMOD.gte(11))
               .and(GHS_SMOD.lte(CFG.MAX_SMOD_CLASS))
               .and(GHS_POP.gte(CFG.SEED_POP_PER_CELL))
               .setDefaultProjection(GHSL_GRID);

  // Morphological closing: the scattered buildings of ONE village become ONE
  // patch, while genuinely separate villages stay separate.
  var closed = seed
    .focalMax({radius: CFG.CLOSE_RADIUS_M, kernelType: 'circle',
               units: 'meters'})
    .focalMin({radius: CFG.CLOSE_RADIUS_M, kernelType: 'circle',
               units: 'meters'});

  return closed.selfMask().rename('patch').toInt().reduceToVectors({
    geometry:       ring,
    // reduceToVectors REQUIRES a scale or crsTransform whenever a crs is
    // given - it will not take the scale from the projection object, and the
    // task fails in about a second if you leave it out.
    crs:            GHSL_GRID,
    scale:          CFG.PATCH_SCALE_M,
    geometryType:   'polygon',
    eightConnected: true,
    labelProperty:  'patch_label',
    maxPixels:      CFG.MAX_PIXELS,
    bestEffort:     false,
    tileScale:      CFG.TILE_SCALE
  });
}

/**
 * STAGE 1 of the geometry work - the cheap half. Two operations per patch: its
 * centroid, and how far that is from the settlement. Nothing else is computed
 * yet, because a settled countryside returns thousands of patches and the
 * shape maths below costs several geodesic operations each. Locate first,
 * throw most of them away on distance, and only then measure shape.
 */
function locatePatches(patches, evPoint, existingPoint) {
  return patches.map(function (f) {
    var c  = f.geometry().centroid(CFG.GEOM_MAXERR)
               .transform('EPSG:4326', CFG.GEOM_MAXERR);
    var xy = ee.List(c.coordinates());
    return f.set({
      control_lon:             xy.get(0),
      control_lat:             xy.get(1),
      control_distance_km:     c.distance(evPoint, CFG.GEOM_MAXERR)
                                .divide(1000),
      dist_to_existing_ctrl_m: c.distance(existingPoint, CFG.GEOM_MAXERR)
    });
  }).filter(ee.Filter.and(
      ee.Filter.gte('control_distance_km', CFG.SEARCH_MIN_KM),
      ee.Filter.lte('control_distance_km', CFG.SEARCH_MAX_KM)));
}

/**
 * Cap the candidate pool EVENLY ACROSS THE RING rather than nearest-first.
 * Taking the nearest N collapses a 50 km search into a disc a third that
 * wide, which both starves the far half of the ring and picks the controls
 * most spatially autocorrelated with the settlement. Equal-width bands, each
 * capped separately, keep the whole ring in play.
 */
function bandedPool(located) {
  var lo = CFG.SEARCH_MIN_KM, hi = CFG.SEARCH_MAX_KM;
  var width = (hi - lo) / CFG.PATCH_BANDS;
  var pool = null;
  for (var b = 0; b < CFG.PATCH_BANDS; b++) {
    var from = lo + b * width;
    var to   = lo + (b + 1) * width;
    var band = located
      .filter(ee.Filter.gte('control_distance_km', from))
      .filter(b === CFG.PATCH_BANDS - 1
                ? ee.Filter.lte('control_distance_km', to)
                : ee.Filter.lt('control_distance_km', to))
      .limit(CFG.MAX_PATCHES_PER_BAND, 'control_distance_km', true);
    pool = (pool === null) ? band : pool.merge(band);
  }
  return pool;
}

/**
 * STAGE 2 of the geometry work - size and shape, on the survivors only. Shape
 * alone rejects bridges, runways, pipelines, road strips and ribbon
 * development, which is why it runs before any pixel is reduced.
 *
 * findPatches vectorises in the GHSL grid, so the patches arrive with that
 * projection and their coordinates are METRES. Everything below works on the
 * WGS84 transform, which is what makes area(), length() and distance() mean
 * what they say.
 */
function describePatchShape(patches) {
  return patches.map(function (f) {
    var g      = f.geometry().transform('EPSG:4326', CFG.GEOM_MAXERR);
    var areaM2 = g.area(CFG.GEOM_MAXERR);
    var coords = ee.List(ee.Geometry(g.bounds(CFG.GEOM_MAXERR))
                           .coordinates().get(0));
    var p0 = ee.List(coords.get(0)),
        p1 = ee.List(coords.get(1)),
        p2 = ee.List(coords.get(2));
    var w = ee.Geometry.LineString([p0, p1]).length(CFG.GEOM_MAXERR).max(1);
    var h = ee.Geometry.LineString([p1, p2]).length(CFG.GEOM_MAXERR).max(1);
    var longSide = w.max(h), shortSide = w.min(h);

    var areaHa = areaM2.divide(1e4);
    var elong  = longSide.divide(shortSide);
    var fill   = areaM2.divide(w.multiply(h));

    // Village-sized, and a place rather than a line. These are the same
    // thresholds V1 and V2 report on, so a selected control always shows them
    // TRUE: everything that failed them was dropped here.
    var gate = areaHa.gte(CFG.MIN_PATCH_HA)
                .and(areaHa.lte(CFG.MAX_PATCH_HA))
                .and(elong.lte(CFG.MAX_ELONGATION))
                .and(fill.gte(CFG.MIN_BBOX_FILL))
                .and(longSide.lte(CFG.MAX_PATCH_DIM_M));

    return f.setGeometry(g).set({
      patch_area_ha:    areaHa,
      patch_elongation: elong,
      patch_bbox_fill:  fill,
      patch_max_dim_m:  longSide,
      geom_gate:        gate
    });
  }).filter(ee.Filter.gt('geom_gate', 0.5));
}

/**
 * Patch-level statistics and the three cheap hard gates (Koppen, biome,
 * country). Pruning here is what keeps the expensive footprint stage small.
 */
function screenPatches(patches, ctxImg, pKop, pBio, pAdm, pElev, pPop) {

  var contPatch = ee.Image.cat([
    BUILT_FRAC.rename('s_built_frac'),
    POP_DENS.rename('s_pop_dens'),
    PERM_WATER.multiply(100).rename('surface_water_pct'),
    DEM.rename('s_elev')
  ]).toFloat();

  var catPatch = ee.Image.cat([
    KOPPEN.rename('g_koppen'),
    ctxImg.rename(['g_biome', 'g_adm0'])
  ]).toInt();

  // The continuous statistics are read over the patch itself. The categorical
  // ones are read over a disc around its centre instead: a one-hectare patch
  // may contain no pixel CENTRE of a 100 m grid, and a reducer over a region
  // with no pixel centres returns null, which would then break every
  // comparison downstream. Every value the patch geometry supplies is already
  // stored as a property by locatePatches, so the swap costs nothing.
  var out = contPatch.reduceRegions({
    collection: patches, reducer: ee.Reducer.mean(), scale: 30,
    tileScale: CFG.TILE_SCALE});
  out = out.map(function (f) {
    return f.setGeometry(
      ee.Geometry.Point([f.get('control_lon'), f.get('control_lat')])
        .buffer(CFG.CATEGORICAL_READ_RADIUS_M));
  });
  out = catPatch.reduceRegions({
    collection: out, reducer: ee.Reducer.mode(), scale: 100,
    tileScale: CFG.TILE_SCALE});

  return out.filter(ee.Filter.notNull(PATCH_REQUIRED)).map(function (f) {
    var areaHa  = num(f, 'patch_area_ha');
    var builtHa = areaHa.multiply(num(f, 's_built_frac'));
    var popPatch = num(f, 's_pop_dens').multiply(areaHa.divide(100));

    // Cheap hard gates, applied before anything expensive is computed.
    var gate = num(f, 'g_koppen').eq(pKop).and(num(f, 'g_koppen').gte(1))
      .and(num(f, 'g_biome').eq(pBio)).and(num(f, 'g_biome').gte(1))
      .and(num(f, 'g_adm0').eq(pAdm)).and(num(f, 'g_adm0').gt(0))
      .and(builtHa.gte(CFG.MIN_BUILT_HA))
      .and(builtHa.lte(CFG.MAX_BUILT_HA))
      .and(popPatch.gte(CFG.MIN_VILLAGE_POP))
      .and(popPatch.lte(CFG.MAX_VILLAGE_POP))
      .and(num(f, 'surface_water_pct').lte(CFG.MAX_PATCH_WATER_PCT));

    // A cheap preliminary score, used only to decide which candidates are
    // worth measuring in full. The real ranking is the D value in Stage C.
    var ratio   = popPatch.max(1).divide(ee.Number(pPop).max(1));
    var ratioS  = ratio.max(ee.Number(1).divide(ratio.max(1e-6)));
    var dPrelim = num(f, 's_elev').subtract(pElev).abs()
                    .divide(CFG.TOL_ELEV_M).pow(2)
                  .add(ratioS.max(1).log().divide(Math.log(CFG.TOL_POP_FACTOR))
                    .pow(2))
                  .add(num(f, 'control_distance_km')
                    .divide(CFG.SEARCH_TIER1_KM).pow(2).multiply(0.5))
                  .sqrt();

    return f.set({
      patch_built_area_ha:  builtHa,
      population_est_patch: popPatch,
      screen_gate:          gate,
      d_prelim:             dPrelim
    });
  })
  .filter(ee.Filter.gt('screen_gate', 0.5))
  .limit(CFG.MAX_CANDIDATES, 'd_prelim', true)
  // From here on, a candidate IS its village centre.
  .map(function (f) {
    return f.setGeometry(ee.Geometry.Point([f.get('control_lon'),
                                            f.get('control_lat')]));
  });
}

// =============================================================================
//  6.  STAGE B  -  MEASURE BOTH ARMS ON IDENTICAL GEOMETRY
// =============================================================================

/**
 * Six chained reduceRegions calls, each at the native grain of its own layers,
 * so no fraction is quietly destroyed by a coarse pyramid. Every feature is
 * measured over a circle of CFG.SITE_RADIUS_M centred on its own point.
 */
function measureFootprints(points, site) {

  var footprints = points.map(function (f) {
    var xy = ee.List(f.geometry().coordinates());
    return f.set('site_centre_lon', xy.get(0), 'site_centre_lat', xy.get(1))
            .setGeometry(f.geometry().buffer(CFG.SITE_RADIUS_M));
  });

  // (a) 10 m: land-cover composition, and the residential / non-residential /
  //     road breakdown that separates a village from a works or an airfield.
  var img10 = ee.Image.cat([
    LANDCOVER,
    BC_RES.multiply(100).rename('residential_built_pct_10m'),
    BC_NRES.multiply(100).rename('nonres_built_pct_10m'),
    BC_ROAD.multiply(100).rename('road_surface_pct_10m')
  ]).toFloat();

  // (b) 30 m: terrain, protection, disturbance, exclusion masks.
  var img30 = ee.Image.cat([
    DEM, SLOPE, TRI,
    GAIN.multiply(100).rename('forest_gain_pct'),
    LOSS.multiply(100).rename('forest_loss_pct'),
    PERM_WATER.multiply(100).rename('footprint_water_pct'),
    site.pa,
    studySiteImage(),
    externalProgrammeImage()
  ]).toFloat();

  // (c) 100 m: settlement structure, population, and distance to water.
  //
  // The water-distance band belongs in THIS stack rather than in a call of its
  // own, and that is not tidiness. reduceRegions names its output after the
  // BAND when the image has several bands, but after the REDUCER when the
  // image has exactly one - so reducing the single-band water image on its own
  // wrote the value to a property called 'mean' and left 'water_dist_m'
  // missing altogether. A missing property reads as null, and the null only
  // announced itself much later, in the first arithmetic that touched it.
  // Keeping every reduceRegions input multi-band makes that impossible.
  var img100 = ee.Image.cat([
    POP_DENS.rename('pop_density_km2'),
    BUILT_FRAC.multiply(100).rename('built_frac_pct'),
    NRES_FRAC.multiply(100).rename('nonresidential_built_pct'),
    SMOD_URBAN.multiply(100).rename('urban_fraction_pct'),
    site.water
  ]).toFloat();

  var out = img10.reduceRegions({collection: footprints,
    reducer: ee.Reducer.mean(), scale: 10, tileScale: CFG.TILE_SCALE});
  out = img30.reduceRegions({collection: out,
    reducer: ee.Reducer.mean(), scale: 30, tileScale: CFG.TILE_SCALE});
  out = img100.reduceRegions({collection: out,
    reducer: ee.Reducer.mean(), scale: 100, tileScale: CFG.TILE_SCALE});
  // (d) EVERY remaining layer is reduced at CFG.FOOTPRINT_SCALE_M.
  //     This is not a detail. The site footprint is 1 km across, so a reducer
  //     asked to work at 927 m - the native grain of the accessibility and
  //     human-modification layers - can find NO pixel centre inside it and
  //     return null. A null then reaches the first arithmetic that touches it
  //     and the run dies with "Number.multiply: Parameter 'left' is required
  //     and may not be null". Reducing the coarse layers on a 100 m grid
  //     instead samples the same cell values and guarantees at least 78
  //     samples inside every footprint.
  out = ee.Image.cat([TRAVEL, GHM, VIIRS]).toFloat().reduceRegions({
    collection: out, reducer: ee.Reducer.mean(),
    scale: CFG.FOOTPRINT_SCALE_M, tileScale: CFG.TILE_SCALE});
  // Categorical layers: the modal class over the footprint, never one pixel.
  out = ee.Image.cat([KOPPEN, site.ctx,
                      GHS_SMOD.rename('smod_class')]).toInt()
          .reduceRegions({collection: out, reducer: ee.Reducer.mode(),
                          scale: CFG.FOOTPRINT_SCALE_M,
                          tileScale: CFG.TILE_SCALE});

  // Give the point geometry back; the circle was only a measuring device.
  return out.map(function (f) {
    return f.setGeometry(ee.Geometry.Point([f.get('site_centre_lon'),
                                            f.get('site_centre_lat')]));
  });
}


// =============================================================================
//  7.  STAGE C  -  EVERY CRITERION, WITH ITS STATUS
// =============================================================================

/**
 * Attaches the settlement's own measured values to every candidate, tests all
 * thirteen matching criteria and all eight village tests, and grades the
 * result. Nothing here is hidden: every test lands in its own column.
 */
function evaluateCandidates(cands, ev, parentPopDoc, hasDocPop) {

  // ---- the settlement's own values, measured on the same 500 m footprint ---
  var pKop   = num(ev, 'koppen_group');
  var pBio   = num(ev, 'biome_num');
  var pAdm   = num(ev, 'adm0_code');
  var pElev  = num(ev, 'elevation_m');
  var pSlope = num(ev, 'slope_deg');
  var pTri   = num(ev, 'tri');
  var pWater = num(ev, 'water_dist_m');
  var pTrav  = num(ev, 'travel_time_min');
  var pTree  = num(ev, 'tree_cover_pct');
  var pBuilt = num(ev, 'built_frac_pct');
  var pTerr  = terrainClassNumber(pSlope);
  var pPop   = hasDocPop ? ee.Number(parentPopDoc) : footprintPopulation(ev);

  // tolerances that are relative to the settlement's own value
  var tolWater  = pWater.multiply(CFG.TOL_WATER_REL).max(CFG.TOL_WATER_FLOOR_M);
  var tolTravel = pTrav.multiply(CFG.TOL_TRAVEL_REL)
                       .max(CFG.TOL_TRAVEL_FLOOR_MIN);
  var tolTri    = pTri.multiply(CFG.TOL_TRI_REL).max(1);

  return cands.map(function (f) {

    // -------------------------------------------------------------- values --
    var kop    = num(f, 'koppen_group');
    var bio    = num(f, 'biome_num');
    var adm    = num(f, 'adm0_code');
    var elev   = num(f, 'elevation_m');
    var slope  = num(f, 'slope_deg');
    var tri    = num(f, 'tri');
    var water  = num(f, 'water_dist_m');
    var trav   = num(f, 'travel_time_min');
    var tree   = num(f, 'tree_cover_pct');
    var built  = num(f, 'built_frac_pct');
    var smod   = num(f, 'smod_class');
    var terr   = terrainClassNumber(slope);
    var distKm = num(f, 'control_distance_km');

    var popFootprint = footprintPopulation(f);
    var popPatch     = num(f, 'population_est_patch');
    // Compare like with like. A documentary community population counts
    // RESIDENTS, so it is matched against the control village's own residents;
    // a GHSL-derived parent population is matched over the same footprint.
    var popCtl      = hasDocPop ? popPatch : popFootprint;
    var ratio       = popCtl.max(1).divide(pPop.max(1));
    var popRatioSym = ratio.max(ee.Number(1).divide(ratio.max(1e-6)));

    // ------------------------------------------- matching criteria C1 - C13 --
    var c1  = kop.eq(pKop).and(kop.gte(1));
    var c2  = bio.eq(pBio).and(bio.gte(1));
    var elevDiff = elev.subtract(pElev).abs();
    var c3  = elevDiff.lte(CFG.TOL_ELEV_M);
    var slopeDiff = slope.subtract(pSlope).abs();
    var c4  = terr.eq(pTerr);                       // the plan's literal wording
    var c4b = slopeDiff.lte(CFG.TOL_SLOPE_DEG);
    var c4c = tri.subtract(pTri).abs().lte(tolTri);
    // identical class, or one class apart with slopes close together: the
    // remedy for a settlement sitting near a class boundary
    var c4tol = c4.or(terr.subtract(pTerr).abs().eq(1)
                        .and(slopeDiff.lte(CFG.TOL_TERRAIN_ADJACENT_DEG)));
    var c4workbook = c4b.and(c4c);                  // the workbook's own C4
    // whichever of the three CFG.C4_MODE names is the one that counts
    var c4used = CFG.C4_MODE === 'CLASS' ? c4
               : CFG.C4_MODE === 'SLOPE_TRI' ? c4workbook
               : c4tol;
    var c5  = distKm.gte(CFG.SEARCH_MIN_KM)
                .and(distKm.lte(CFG.SEARCH_TIER1_KM));
    var c5b = distKm.gte(CFG.SEARCH_MIN_KM)
                .and(distKm.lte(CFG.SEARCH_MAX_KM));
    var waterDiff = water.subtract(pWater).abs();
    var c6  = waterDiff.lte(tolWater);
    var travDiff = trav.subtract(pTrav).abs();
    var c7  = travDiff.lte(tolTravel);
    var treeDiff = tree.subtract(pTree).abs();
    var c8  = treeDiff.lte(CFG.TOL_TREE_PP);

    var paPct = CFG.PA_EXCLUSION_MODE === 'ANY'
                  ? num(f, 'protected_any_pct')
                  : num(f, 'protected_iucn12_pct');
    var c9  = paPct.lte(CFG.MAX_PA_OVERLAP_PCT);

    var restoration = num(f, 'forest_gain_pct');
    // gain WITHOUT matching loss; gain beside loss is rotation forestry
    var restFlag    = restoration.gte(CFG.RESTORATION_GAIN_PCT)
                        .and(num(f, 'forest_loss_pct')
                               .lte(CFG.RESTORATION_MAX_LOSS_PCT));
    var extHit      = num(f, 'ext_programme_pct').gt(0);
    var c10 = extHit.not().and(CFG.TREAT_RESTORATION_SIGNAL_AS_EXCLUSION
                                 ? restFlag.not() : ee.Number(1));

    var c11 = adm.eq(pAdm).and(adm.gt(0));
    var c12 = smod.gte(11).and(smod.lte(CFG.MAX_SMOD_CLASS))
                .and(num(f, 'urban_fraction_pct')
                       .lte(CFG.MAX_URBAN_FRACTION_PCT))
                .and(num(f, 'pop_density_km2').lte(CFG.MAX_RURAL_POP_DENS));
    var c13 = popRatioSym.lte(CFG.TOL_POP_FACTOR);

    // ---------------------------------------------- village tests V1 - V8 --
    var areaHa   = num(f, 'patch_area_ha');
    var builtHa  = num(f, 'patch_built_area_ha');
    var res10    = num(f, 'residential_built_pct_10m');
    var nres10   = num(f, 'nonres_built_pct_10m');
    var road10   = num(f, 'road_surface_pct_10m');
    var resShare = res10.divide(res10.add(nres10).max(0.001));
    var popPerBuiltHa = popPatch.divide(builtHa.max(0.01));

    // V1 - the patch is the size of a village, not of a shed or of a town
    var v1 = areaHa.gte(CFG.MIN_PATCH_HA).and(areaHa.lte(CFG.MAX_PATCH_HA))
               .and(builtHa.gte(CFG.MIN_BUILT_HA))
               .and(builtHa.lte(CFG.MAX_BUILT_HA));
    // V2 - the patch is a PLACE, not a LINE. This is the test that rejects
    //      bridges, runways, pipelines, quarry conveyors, road strips and
    //      ribbon development, none of which are villages.
    var v2 = num(f, 'patch_elongation').lte(CFG.MAX_ELONGATION)
               .and(num(f, 'patch_bbox_fill').gte(CFG.MIN_BBOX_FILL))
               .and(num(f, 'patch_max_dim_m').lte(CFG.MAX_PATCH_DIM_M));
    // V3 - the built space is mostly RESIDENTIAL. This is the test that
    //      rejects factories, works, depots, warehouses and glasshouse
    //      complexes, which GHS_BUILT_S and GHS_BUILT_C both label
    //      non-residential.
    var v3 = num(f, 'nonresidential_built_pct').divide(100)
               .lte(CFG.MAX_NRES_FRAC)
               .and(resShare.gte(CFG.MIN_RES_SHARE_10M)
                      .or(res10.add(nres10).lt(0.05)));
    // V4 - people live there per unit of building, and it is not mostly
    //      pavement. This is the test that rejects industrial estates,
    //      airports, terminals and motorway interchanges.
    var v4 = popPerBuiltHa.gte(CFG.MIN_POP_PER_BUILT_HA)
               .and(road10.lte(CFG.MAX_ROAD_PCT_10M));
    // V5 - it is not standing on water: bridges, piers, dams, stilt platforms
    var v5 = num(f, 'surface_water_pct').lte(CFG.MAX_PATCH_WATER_PCT)
               .and(num(f, 'footprint_water_pct')
                      .lte(CFG.MAX_FOOTPRINT_WATER_PCT));
    // V6 - it sits in open rural land rather than inside a sealed surface
    var v6 = num(f, 'builtup_pct').lte(CFG.MAX_BUILTUP_PCT)
               .and(tree.add(num(f, 'cropland_pct'))
                        .add(num(f, 'grass_shrub_pct'))
                        .gte(CFG.MIN_OPEN_LAND_PCT));
    // V7 - it actually has residents, in village numbers
    var v7 = popPatch.gte(CFG.MIN_VILLAGE_POP)
               .and(popPatch.lte(CFG.MAX_VILLAGE_POP));
    // V8 - it is not one of the 212 study settlements
    var v8 = num(f, 'study_site_pct').eq(0);

    var vSum  = v1.add(v2).add(v3).add(v4).add(v5).add(v6).add(v7).add(v8);
    var vHard = v1.multiply(v2).multiply(v7).multiply(v8);
    var villageOk = vHard.and(vSum.gte(CFG.MIN_VILLAGE_TESTS));

    // -------------------------------------------- weighted standardised D --
    // Each residual is a fraction of its own tolerance, so D = 1 means the
    // covariates use up exactly their declared allowance on average.
    var rElev  = elevDiff.divide(CFG.TOL_ELEV_M);
    var rWater = waterDiff.divide(tolWater);
    var rTree  = treeDiff.divide(CFG.TOL_TREE_PP);
    var rPop   = popRatioSym.max(1).log().divide(Math.log(CFG.TOL_POP_FACTOR));
    var rSlope = slope.subtract(pSlope).abs().divide(CFG.TOL_SLOPE_DEG);
    var rTrav  = travDiff.divide(tolTravel);
    var rBuilt = built.subtract(pBuilt).abs().divide(CFG.TOL_BUILT_PP);
    var wSum = CFG.W_ELEV + CFG.W_WATER + CFG.W_TREE + CFG.W_POP +
               CFG.W_SLOPE + CFG.W_TRAVEL + CFG.W_BUILT;
    var d = rElev.pow(2).multiply(CFG.W_ELEV)
      .add(rWater.pow(2).multiply(CFG.W_WATER))
      .add(rTree.pow(2).multiply(CFG.W_TREE))
      .add(rPop.pow(2).multiply(CFG.W_POP))
      .add(rSlope.pow(2).multiply(CFG.W_SLOPE))
      .add(rTrav.pow(2).multiply(CFG.W_TRAVEL))
      .add(rBuilt.pow(2).multiply(CFG.W_BUILT))
      .divide(wSum).sqrt();

    // ------------------------------------------------------- eligibility ---
    // HARD gates: fail one and the candidate is never selected. These are the
    // criteria the plan holds constant BY MATCHING, plus the exclusions, plus
    // "it has to actually be a village".
    var hardOk = c1.multiply(c2).multiply(c9).multiply(c10).multiply(c11)
                   .multiply(c12).multiply(c5b).multiply(villageOk);
    var hardFail = ee.Number(8).subtract(
      c1.add(c2).add(c9).add(c10).add(c11).add(c12).add(c5b).add(villageOk));
    // SOFT criteria: counted; a Tier-2 control may miss at most one.
    var softFail = ee.Number(6).subtract(
      c3.add(c4used).add(c6).add(c7).add(c8).add(c13));

    var t1 = hardOk.and(softFail.eq(0)).and(c5).and(d.lte(CFG.D_MAX_TIER1));
    var t2 = hardOk.and(softFail.lte(1)).and(d.lte(CFG.D_MAX_TIER2));
    // Tier 3 has no ceiling on D. The plan is explicit: where nothing good
    // exists, take the best available and FLAG it rather than dropping the
    // settlement. d_within_declared_threshold below says how bad "best
    // available" was, so nothing is hidden by keeping it.
    var t3 = hardOk;
    var notT1 = ee.Number(1).subtract(t1);
    var tier  = t1
      .add(t2.multiply(notT1).multiply(2))
      .add(t3.multiply(notT1).multiply(ee.Number(1).subtract(t2)).multiply(3));

    // The distance ladder. The plan orders by DISTANCE once the search has
    // been EXTENDED beyond the first rung - "take the CLOSEST qualifying
    // candidates rather than the best-scoring ones". That reasoning applies to
    // candidates that are actually far away. A control inside the first rung
    // which is Tier 2 only because it missed a tolerance is not a
    // distance-extended candidate, and ordering it by distance would rank a
    // poor near match above a good one. So distance orders the far ones and
    // match quality orders the rest.
    var isFar   = distKm.gt(CFG.SEARCH_TIER1_KM);
    var primary = d.multiply(ee.Number(1).subtract(isFar))
                   .add(distKm.divide(CFG.SEARCH_MAX_KM).multiply(isFar))
                   .min(999);   // so the tier term always dominates the sort
    var sortKey = tier.multiply(1000).add(primary);

    var stars = d.lt(CFG.D_MAX_TIER2).add(d.lt(0.5));

    var one = ee.Number(1);
    var failed = ee.String('')
      .cat(failTag('C1_koppen',        one.subtract(c1)))
      .cat(failTag('C2_biome',         one.subtract(c2)))
      .cat(failTag('C3_elevation',     one.subtract(c3)))
      .cat(failTag('C4_terrain',       one.subtract(c4used)))
      .cat(failTag('C5_distance_50km', one.subtract(c5)))
      .cat(failTag('C6_water_dist',    one.subtract(c6)))
      .cat(failTag('C7_travel_time',   one.subtract(c7)))
      .cat(failTag('C8_tree_cover',    one.subtract(c8)))
      .cat(failTag('C9_protected',     one.subtract(c9)))
      .cat(failTag('C10_programme',    one.subtract(c10)))
      .cat(failTag('C11_country',      one.subtract(c11)))
      .cat(failTag('C12_rural',        one.subtract(c12)))
      .cat(failTag('C13_population',   one.subtract(c13)))
      .cat(failTag('V1_patch_size',    one.subtract(v1)))
      .cat(failTag('V2_shape_linear',  one.subtract(v2)))
      .cat(failTag('V3_residential',   one.subtract(v3)))
      .cat(failTag('V4_industrial',    one.subtract(v4)))
      .cat(failTag('V5_on_water',      one.subtract(v5)))
      .cat(failTag('V6_rural_context', one.subtract(v6)))
      .cat(failTag('V7_no_residents',  one.subtract(v7)))
      .cat(failTag('V8_study_site',    one.subtract(v8)));

    return f.set({
      // --- what this control was matched against ---------------------------
      parent_koppen_group:      lut(KOPPEN_LETTER, pKop),
      parent_biome_num:         pBio,
      parent_biome_name:        lut(BIOME_NAME, pBio),
      parent_adm0_code:         pAdm,
      parent_elevation_m:       pElev,
      parent_slope_deg:         pSlope,
      parent_terrain_class:     lut(TERRAIN_NAME, pTerr),
      parent_tri:               pTri,
      parent_water_dist_m:      pWater,
      parent_travel_time_min:   pTrav,
      parent_tree_cover_pct:    pTree,
      parent_built_frac_pct:    pBuilt,
      parent_population:        pPop,
      parent_population_basis:  hasDocPop
                                  ? 'documentary (Stage 1 coding)'
                                  : 'GHSL 2020 over the 500 m footprint',
      // --- the control's own values ----------------------------------------
      koppen_group:             lut(KOPPEN_LETTER, kop),
      biome_name:               lut(BIOME_NAME, bio),
      terrain_class:            lut(TERRAIN_NAME, terr),
      smod_label:               smodLabel(smod),
      elevation_diff_m:         elevDiff,
      tree_cover_diff_pp:       treeDiff,
      water_dist_diff_m:        waterDiff,
      water_dist_censored:      tf(water.gte(CFG.WATER_DIST_MAX_M - 1)
                                    .or(pWater.gte(CFG.WATER_DIST_MAX_M - 1))),
      water_dist_tol_m:         tolWater,
      travel_time_tol_min:      tolTravel,
      population_est_footprint: popFootprint,
      population_used_for_C13:  popCtl,
      population_ratio:         popRatioSym,
      pop_per_built_ha:         popPerBuiltHa,
      residential_share_10m:    resShare,
      restoration_signal_pct:   restoration,
      restoration_signal_flag:  tf(restFlag),
      external_programme_hit:   tf(extHit),
      // --- criterion status -------------------------------------------------
      C1_koppen_match:              tf(c1),
      C2_biome_match:               tf(c2),
      C3_elevation_within_300m:     tf(c3),
      C4_terrain_class_match:       tf(c4),
      C4_terrain_class_tolerant:    tf(c4tol),
      C4_workbook_slope_and_tri:    tf(c4workbook),
      C4_rule_applied:              CFG.C4_MODE,
      C4b_slope_within_10deg:       tf(c4b),
      C4c_tri_within_50pct:         tf(c4c),
      C5_distance_5_50km:           tf(c5),
      C5b_distance_5_100km:         tf(c5b),
      C6_water_dist_within_tol:     tf(c6),
      C7_travel_within_50pct:       tf(c7),
      C8_treecover_within_15pp:     tf(c8),
      C9_not_protected_area:        tf(c9),
      C10_no_external_programme:    tf(c10),
      C11_same_country:             tf(c11),
      C12_rural_settlement:         tf(c12),
      C13_population_within_3x:     tf(c13),
      V1_patch_size_plausible:      tf(v1),
      V2_shape_not_linear:          tf(v2),
      V3_residential_dominant:      tf(v3),
      V4_not_industrial_or_airport: tf(v4),
      V5_not_on_water:              tf(v5),
      V6_rural_open_land_context:   tf(v6),
      V7_residents_present:         tf(v7),
      V8_not_a_study_site:          tf(v8),
      village_tests_passed:         vSum,
      village_class:                lut(VILLAGE_CLASS, vSum),
      is_village_eligible:          tf(villageOk),
      is_existing_workbook_control:
        tf(num(f, 'dist_to_existing_ctrl_m').lte(500)),
      // --- score and grade --------------------------------------------------
      n_hard_failed:   hardFail,
      n_soft_failed:   softFail,
      criteria_failed: failed,
      d_value:         d,
      d_within_declared_threshold: tf(d.lte(CFG.D_MAX_TIER3)),
      star_rating:     lut(STAR_NAME, stars),
      match_tier:      tier,
      tier_label:      lut(TIER_NAME, tier),
      sort_key:        sortKey,
      eligible:        hardOk
    });
  });
}

// =============================================================================
//  8.  THE COMMUNITY ROW
// =============================================================================

var NA = 'n/a - settlement row';

/**
 * One row per community, so that all 212 appear in the CSV whether or not the
 * search found anything for them. "NEVER drop the settlement" has to be
 * visible in the output, not only in the method. The row also carries the
 * community's own measured context, which is what every control beneath it was
 * matched against, and the two exclusion criteria the plan applies to
 * settlements as well as to controls.
 */
function communityRow(qid, evName, evLon, evLat, ev, blk, hasDocPop,
                      parentPopDoc, nScreened) {

  var n        = blk.nSelected;
  var maxTier  = blk.maxTier;
  var within50 = blk.within50;

  var pTerr = terrainClassNumber(num(ev, 'slope_deg'));
  var pPop  = hasDocPop ? ee.Number(parentPopDoc) : footprintPopulation(ev);
  var paPct = CFG.PA_EXCLUSION_MODE === 'ANY'
                ? num(ev, 'protected_any_pct')
                : num(ev, 'protected_iucn12_pct');
  var smod  = num(ev, 'smod_class');
  var kop   = num(ev, 'koppen_group');
  var bio   = num(ev, 'biome_num');

  return ee.Feature(ee.Geometry.Point([evLon, evLat]), {
    row_type:            'COMMUNITY',
    quartet_id:          qid,
    ecovillage_name:     evName,
    control_id:          ee.String('EV').cat(ee.Number(qid).format('%03d')),
    control_rank:        0,
    latitude:            evLat,
    longitude:           evLon,
    parent_latitude:     evLat,
    parent_longitude:    evLon,
    control_distance_km: 0,

    // ---- the community's own measured context ---------------------------
    koppen_group:              lut(KOPPEN_LETTER, kop),
    parent_koppen_group:       lut(KOPPEN_LETTER, kop),
    biome_num:                 bio,
    parent_biome_num:          bio,
    biome_name:                lut(BIOME_NAME, bio),
    parent_biome_name:         lut(BIOME_NAME, bio),
    adm0_code:                 num(ev, 'adm0_code'),
    parent_adm0_code:          num(ev, 'adm0_code'),
    elevation_m:               num(ev, 'elevation_m'),
    parent_elevation_m:        num(ev, 'elevation_m'),
    elevation_diff_m:          0,
    slope_deg:                 num(ev, 'slope_deg'),
    parent_slope_deg:          num(ev, 'slope_deg'),
    tri:                       num(ev, 'tri'),
    parent_tri:                num(ev, 'tri'),
    terrain_class:             lut(TERRAIN_NAME, pTerr),
    parent_terrain_class:      lut(TERRAIN_NAME, pTerr),
    water_dist_m:              num(ev, 'water_dist_m'),
    parent_water_dist_m:       num(ev, 'water_dist_m'),
    water_dist_diff_m:         0,
    water_dist_censored:       tf(num(ev, 'water_dist_m')
                                    .gte(CFG.WATER_DIST_MAX_M - 1)),
    water_dist_tol_m:          num(ev, 'water_dist_m')
                                 .multiply(CFG.TOL_WATER_REL)
                                 .max(CFG.TOL_WATER_FLOOR_M),
    travel_time_min:           num(ev, 'travel_time_min'),
    parent_travel_time_min:    num(ev, 'travel_time_min'),
    travel_time_tol_min:       num(ev, 'travel_time_min')
                                 .multiply(CFG.TOL_TRAVEL_REL)
                                 .max(CFG.TOL_TRAVEL_FLOOR_MIN),
    tree_cover_pct:            num(ev, 'tree_cover_pct'),
    parent_tree_cover_pct:     num(ev, 'tree_cover_pct'),
    tree_cover_diff_pp:        0,
    cropland_pct:              num(ev, 'cropland_pct'),
    grass_shrub_pct:           num(ev, 'grass_shrub_pct'),
    builtup_pct:               num(ev, 'builtup_pct'),
    bare_pct:                  num(ev, 'bare_pct'),
    built_frac_pct:            num(ev, 'built_frac_pct'),
    parent_built_frac_pct:     num(ev, 'built_frac_pct'),
    nonresidential_built_pct:  num(ev, 'nonresidential_built_pct'),
    residential_built_pct_10m: num(ev, 'residential_built_pct_10m'),
    nonres_built_pct_10m:      num(ev, 'nonres_built_pct_10m'),
    residential_share_10m:     num(ev, 'residential_built_pct_10m').divide(
                                 num(ev, 'residential_built_pct_10m')
                                   .add(num(ev, 'nonres_built_pct_10m'))
                                   .max(0.001)),
    road_surface_pct_10m:      num(ev, 'road_surface_pct_10m'),
    surface_water_pct:         num(ev, 'footprint_water_pct'),
    footprint_water_pct:       num(ev, 'footprint_water_pct'),
    pop_density_km2:           num(ev, 'pop_density_km2'),
    population_est_patch:      footprintPopulation(ev),
    population_est_footprint:  footprintPopulation(ev),
    population_used_for_C13:   pPop,
    parent_population:         pPop,
    parent_population_basis:   hasDocPop
                                 ? 'documentary (Stage 1 coding)'
                                 : 'GHSL 2020 over the 500 m footprint',
    population_ratio:          1,
    pop_per_built_ha:          footprintPopulation(ev).divide(
                                 num(ev, 'built_frac_pct').divide(100)
                                   .multiply(Math.PI * CFG.SITE_RADIUS_M *
                                             CFG.SITE_RADIUS_M / 1e4)
                                   .max(0.01)),
    urban_fraction_pct:        num(ev, 'urban_fraction_pct'),
    smod_class:                smod,
    smod_label:                smodLabel(smod),
    protected_any_pct:         num(ev, 'protected_any_pct'),
    protected_iucn12_pct:      num(ev, 'protected_iucn12_pct'),
    human_modification:        num(ev, 'human_modification'),
    nightlight_radiance:       num(ev, 'nightlight_radiance'),
    forest_gain_pct:           num(ev, 'forest_gain_pct'),
    forest_loss_pct:           num(ev, 'forest_loss_pct'),
    restoration_signal_pct:    num(ev, 'forest_gain_pct'),
    restoration_signal_flag:   tf(num(ev, 'forest_gain_pct')
                                   .gte(CFG.RESTORATION_GAIN_PCT)),
    external_programme_hit:    tf(num(ev, 'ext_programme_pct').gt(0)),
    patch_area_ha:             '', patch_built_area_ha: '',
    patch_elongation:          '', patch_bbox_fill: '', patch_max_dim_m: '',

    // ---- criterion columns: a settlement is not matched against itself, so
    //      only the two exclusion criteria the plan applies to settlements
    //      carry a real value here ------------------------------------------
    C1_koppen_match: NA, C2_biome_match: NA, C3_elevation_within_300m: NA,
    C4_terrain_class_match: NA, C4b_slope_within_10deg: NA,
    C4c_tri_within_50pct: NA, C5_distance_5_50km: NA,
    C5b_distance_5_100km: NA, C6_water_dist_within_tol: NA,
    C7_travel_within_50pct: NA, C8_treecover_within_15pp: NA,
    C9_not_protected_area:  tf(paPct.lte(CFG.MAX_PA_OVERLAP_PCT)),
    C10_no_external_programme: tf(num(ev, 'ext_programme_pct').eq(0)),
    C11_same_country: NA,
    C12_rural_settlement: tf(smod.gte(11).and(smod.lte(CFG.MAX_SMOD_CLASS))),
    C13_population_within_3x: NA,
    V1_patch_size_plausible: NA, V2_shape_not_linear: NA,
    V3_residential_dominant: NA, V4_not_industrial_or_airport: NA,
    V5_not_on_water: NA, V6_rural_open_land_context: NA,
    V7_residents_present: NA, V8_not_a_study_site: NA,
    village_tests_passed: '', village_class: NA, is_village_eligible: NA,
    is_existing_workbook_control: NA,
    n_hard_failed: '', n_soft_failed: '', criteria_failed: '',
    d_value: '', d_within_declared_threshold: NA, star_rating: NA,

    // ---- the block summary ----------------------------------------------
    n_controls_selected:    n,
    n_controls_within_50km: within50,
    n_tier1_controls:       blk.nTier1,
    n_tier2_controls:       blk.nTier2,
    n_tier3_controls:       blk.nTier3,
    n_patches_found:        blk.inRing,
    n_patches_pooled:       blk.pooled,
    patch_pool_capped:      tf(blk.pooled.lt(blk.inRing).multiply(1)),
    n_candidates_screened:  nScreened,
    workbook_ctrl_patch_dist_m: blk.wbDist,
    workbook_ctrl_eligible:     tf(blk.wbOk.gt(0.5).multiply(1)),
    workbook_ctrl_d_value:      blk.wbD,
    workbook_ctrl_match_tier:   blk.wbTier,
    match_tier:             maxTier,
    tier_label:             lut(TIER_NAME, maxTier),
    quartet_grade:          lut(TIER_NAME, maxTier),
    ladder_step:            maxTier,
    search_radius_km:       CFG.SEARCH_MAX_KM,
    koppen_source:          CFG.KOPPEN_ASSET ? CFG.KOPPEN_ASSET
                              : 'WorldClim v1 monthly, Beck et al. logic',
    landcover_source:       CFG.LANDCOVER_SOURCE,
    script_version:         SCRIPT_VERSION,
    run_date:               RUN_DATE
  });
}

// =============================================================================
//  9.  ONE SETTLEMENT, END TO END
// =============================================================================

function processSettlement(row) {
  var qid    = row[0];
  var evName = row[1];
  var evLat  = row[2];
  var evLon  = row[3];
  var popDoc = row[4];
  var exLat  = (row[5] === null) ? row[2] : row[5];
  var exLon  = (row[6] === null) ? row[3] : row[6];
  var hasDoc = popDoc > 0;

  var evPoint   = ee.Geometry.Point([evLon, evLat]);
  var exPoint   = ee.Geometry.Point([exLon, exLat]);
  var region    = evPoint.buffer(CFG.SEARCH_MAX_KM * 1000);
  var ring      = region.difference(evPoint.buffer(CFG.SEARCH_MIN_KM * 1000),
                                    CFG.GEOM_MAXERR);
  var footprint = evPoint.buffer(CFG.SITE_RADIUS_M);

  // The three layers that have to be cut to this settlement's search region
  // are built ONCE and passed around. Rebuilding them per measurement pass is
  // what made the Code Editor slow to respond: each one filters and paints a
  // global FeatureCollection, and the browser has to construct that graph.
  var site = {
    ctx:   contextImage(region),
    pa:    protectedAreaImage(region),
    water: waterDistanceImage(evLon, evLat)
  };

  // The candidate search needs four of the settlement's own values before it
  // can gate anything, so they are read here in two cheap reduceRegion calls
  // rather than by running the whole six-call measurement chain twice. The
  // categorical read uses the SAME reducer and scale as the full measurement
  // below, so the gate can never disagree with the value finally reported.
  var gCat = ee.Image.cat([KOPPEN, site.ctx]).toInt().reduceRegion({
    reducer: ee.Reducer.mode(), geometry: footprint, scale: 100,
    maxPixels: 1e8, tileScale: CFG.TILE_SCALE});
  var gCon = ee.Image.cat([DEM, POP_DENS.rename('pop_density_km2')]).toFloat()
               .reduceRegion({
                 reducer: ee.Reducer.mean(), geometry: footprint, scale: 100,
                 maxPixels: 1e8, tileScale: CFG.TILE_SCALE});
  var footprintKm2 = Math.PI * CFG.SITE_RADIUS_M * CFG.SITE_RADIUS_M / 1e6;
  var pPop = hasDoc
    ? ee.Number(popDoc)
    : ee.Number(gCon.get('pop_density_km2')).multiply(footprintKm2);

  var patches = findPatches(ring);
  var located = locatePatches(patches, evPoint, exPoint);

  // Cap the pool band by band across the ring, so the candidates are not all
  // drawn from a disc around the settlement. Sorting on a property costs
  // nothing; measuring the shape of thousands of patches, and reducing
  // statistics over them, does.
  // The patch nearest the settlement's existing workbook control is always
  // added to the pool, whatever band it falls in and whether or not that band
  // is full. It costs one extra patch and it buys a direct check: does this
  // search independently rediscover the control the researcher already chose?
  // is_existing_workbook_control answers that per row.
  var pool = describePatchShape(
    bandedPool(located)
      .merge(located.limit(1, 'dist_to_existing_ctrl_m', true))
      .distinct(['control_lon', 'control_lat']));

  var screened  = screenPatches(pool, site.ctx,
                                ee.Number(gCat.get('koppen_group')),
                                ee.Number(gCat.get('biome_num')),
                                ee.Number(gCat.get('adm0_code')),
                                ee.Number(gCon.get('elevation_m')),
                                pPop);

  // ONE measurement pass covering the settlement and its candidates together.
  // Measuring both arms in the same call is not only half the work; it is also
  // the guarantee the design rests on, that nothing differs between them
  // except the ground itself.
  var both = ee.FeatureCollection([ee.Feature(evPoint, {is_parent: 1})])
               .merge(screened.map(function (f) {
                 return f.set('is_parent', 0);
               }));
  var measured = measureFootprints(both, site);
  var ev     = ee.Feature(measured.filter(ee.Filter.gt('is_parent', 0.5))
                                  .first());
  var cands  = measured.filter(ee.Filter.lt('is_parent', 0.5))
                       .filter(ee.Filter.notNull(FOOTPRINT_REQUIRED));
  var scored = evaluateCandidates(cands, ev, popDoc, hasDoc);

  var nearestToWorkbook = scored.limit(1, 'dist_to_existing_ctrl_m', true);
  var eligible  = scored.filter(ee.Filter.gt('eligible', 0.5))
                        .sort('sort_key');
  var chosen    = eligible.limit(
    CFG.CONTROLS_PER_SETTLEMENT + CFG.SELECTION_HEADROOM, 'sort_key', true);

  // The block summary, computed once and written onto every row of the block
  // so that each control is fully self-describing in the CSV.
  // aggregate_max returns null on an empty collection, so the tier list is
  // seeded with 0: a settlement that found nothing grades "not eligible"
  // rather than crashing the export.
  // The grade comes from the BEST THREE controls, not from all of them. The
  // plan's three tiers grade a QUARTET - one settlement against three controls
  // - and "at most one covariate outside tolerance" is a statement about that
  // trio. Applied to fifteen it becomes a statement about the fifteenth-best
  // match, so every block on earth grades Tier 3 and the grade says nothing.
  // The first live run showed exactly that. Grading the best three reproduces
  // the plan's own unit; the tier counts describe the rest of the block.
  var top3 = chosen.limit(3, 'sort_key', true);
  var blk = {
    nSelected: chosen.size(),
    maxTier:   ee.Number(ee.List(top3.aggregate_array('match_tier')).add(0)
                 .reduce(ee.Reducer.max())),
    within50:  chosen.filter(ee.Filter.lte('control_distance_km',
                                           CFG.SEARCH_TIER1_KM)).size(),
    nTier1:    chosen.filter(ee.Filter.eq('match_tier', 1)).size(),
    nTier2:    chosen.filter(ee.Filter.eq('match_tier', 2)).size(),
    nTier3:    chosen.filter(ee.Filter.eq('match_tier', 3)).size(),
    inRing:    located.size(),
    pooled:    pool.size(),
    // Does this search independently rediscover the conventional-rural control
    // the researcher already chose? The patch nearest that control is forced
    // into the pool, so if it survived screening it is the first row here.
    // A large wbDist means its patch did NOT survive - the old control is not
    // a village this method recognises, which is a finding in itself.
    wbDist:    firstOr(nearestToWorkbook, 'dist_to_existing_ctrl_m', -1),
    wbD:       firstOr(nearestToWorkbook, 'd_value', -1),
    wbTier:    firstOr(nearestToWorkbook, 'match_tier', 0),
    wbOk:      firstOr(nearestToWorkbook, 'eligible', 0)
  };

  var community = communityRow(qid, evName, evLon, evLat, ev, blk, hasDoc,
                               popDoc, screened.size());

  // The community row seeds the accumulator, so the block is never an empty
  // list and the controls come out ranked, in ladder order, beneath their own
  // settlement.
  var rows = ee.FeatureCollection(ee.List(chosen.iterate(function (f, acc) {
    var list = ee.List(acc);
    var rank = list.size();          // 1 for the first control, the seed being 0
    return list.add(ee.Feature(f).set({
      row_type:              'CONTROL',
      quartet_id:            qid,
      ecovillage_name:       evName,
      control_rank:          rank,
      control_id:            ee.String('EV').cat(ee.Number(qid).format('%03d'))
                               .cat('_CR').cat(ee.Number(rank).format('%02d')),
      latitude:              f.get('control_lat'),
      longitude:             f.get('control_lon'),
      parent_latitude:       evLat,
      parent_longitude:      evLon,
      n_controls_selected:    blk.nSelected,
      n_controls_within_50km: blk.within50,
      n_tier1_controls:       blk.nTier1,
      n_tier2_controls:       blk.nTier2,
      n_tier3_controls:       blk.nTier3,
      ladder_step:            blk.maxTier,
      quartet_grade:          lut(TIER_NAME, blk.maxTier),
      n_patches_found:        blk.inRing,
      n_patches_pooled:       blk.pooled,
      patch_pool_capped:      tf(blk.pooled.lt(blk.inRing).multiply(1)),
      n_candidates_screened:  screened.size(),
      workbook_ctrl_patch_dist_m: blk.wbDist,
      workbook_ctrl_eligible:     tf(blk.wbOk.gt(0.5).multiply(1)),
      workbook_ctrl_d_value:      blk.wbD,
      workbook_ctrl_match_tier:   blk.wbTier,
      search_radius_km:       CFG.SEARCH_MAX_KM,
      koppen_source:         CFG.KOPPEN_ASSET ? CFG.KOPPEN_ASSET
                               : 'WorldClim v1 monthly, Beck et al. logic',
      landcover_source:      CFG.LANDCOVER_SOURCE,
      script_version:        SCRIPT_VERSION,
      run_date:              RUN_DATE
    }));
  }, ee.List([community]))));

  return {
    rows:     rows,
    controls: chosen,
    eligible: eligible,
    scored:   scored,
    patches:  pool,
    allPatches: located,
    ev:       ev,
    ring:     ring
  };
}

// =============================================================================
//  10.  OUTPUT COLUMNS
// =============================================================================

var OUT_COLUMNS = [
  // ---- identity: which community does this row belong to -------------------
  'row_type', 'quartet_id', 'ecovillage_name', 'control_id', 'control_rank',
  'latitude', 'longitude', 'parent_latitude', 'parent_longitude',
  'control_distance_km',
  // ---- overall grade -------------------------------------------------------
  'match_tier', 'tier_label', 'd_value', 'd_within_declared_threshold',
  'star_rating', 'n_hard_failed', 'n_soft_failed', 'criteria_failed',
  // ---- C1 climate ----------------------------------------------------------
  'koppen_group', 'parent_koppen_group', 'C1_koppen_match',
  // ---- C2 biome ------------------------------------------------------------
  'biome_num', 'biome_name', 'parent_biome_num', 'parent_biome_name',
  'C2_biome_match',
  // ---- C3 elevation --------------------------------------------------------
  'elevation_m', 'parent_elevation_m', 'elevation_diff_m',
  'C3_elevation_within_300m',
  // ---- C4 terrain ----------------------------------------------------------
  'terrain_class', 'parent_terrain_class', 'slope_deg', 'parent_slope_deg',
  'tri', 'parent_tri', 'C4_terrain_class_match', 'C4_terrain_class_tolerant',
  'C4_workbook_slope_and_tri', 'C4_rule_applied', 'C4b_slope_within_10deg',
  'C4c_tri_within_50pct',
  // ---- C5 distance ---------------------------------------------------------
  'C5_distance_5_50km', 'C5b_distance_5_100km',
  // ---- C6 distance to permanent water --------------------------------------
  'water_dist_m', 'parent_water_dist_m', 'water_dist_diff_m',
  'water_dist_tol_m', 'water_dist_censored', 'C6_water_dist_within_tol',
  // ---- C7 accessibility ----------------------------------------------------
  'travel_time_min', 'parent_travel_time_min', 'travel_time_tol_min',
  'C7_travel_within_50pct',
  // ---- C8 tree cover -------------------------------------------------------
  'tree_cover_pct', 'parent_tree_cover_pct', 'tree_cover_diff_pp',
  'C8_treecover_within_15pp',
  // ---- C9 protected area ---------------------------------------------------
  'protected_any_pct', 'protected_iucn12_pct', 'C9_not_protected_area',
  // ---- C10 external funding or programme -----------------------------------
  'restoration_signal_pct', 'restoration_signal_flag',
  'external_programme_hit', 'C10_no_external_programme',
  // ---- C11 country ---------------------------------------------------------
  'adm0_code', 'parent_adm0_code', 'C11_same_country',
  // ---- C12 rural -----------------------------------------------------------
  'smod_class', 'smod_label', 'urban_fraction_pct', 'pop_density_km2',
  'C12_rural_settlement',
  // ---- C13 population ------------------------------------------------------
  'population_est_patch', 'population_est_footprint',
  'population_used_for_C13', 'parent_population', 'parent_population_basis',
  'population_ratio', 'C13_population_within_3x',
  // ---- is it really a village ----------------------------------------------
  'V1_patch_size_plausible', 'V2_shape_not_linear', 'V3_residential_dominant',
  'V4_not_industrial_or_airport', 'V5_not_on_water',
  'V6_rural_open_land_context', 'V7_residents_present', 'V8_not_a_study_site',
  'village_tests_passed', 'village_class', 'is_village_eligible',
  // ---- the evidence behind those tests -------------------------------------
  'patch_area_ha', 'patch_built_area_ha', 'patch_elongation',
  'patch_bbox_fill', 'patch_max_dim_m', 'built_frac_pct',
  'parent_built_frac_pct', 'nonresidential_built_pct',
  'residential_built_pct_10m', 'nonres_built_pct_10m', 'residential_share_10m',
  'road_surface_pct_10m', 'surface_water_pct', 'footprint_water_pct',
  'pop_per_built_ha', 'cropland_pct', 'grass_shrub_pct', 'builtup_pct',
  'bare_pct', 'nightlight_radiance', 'human_modification',
  'forest_gain_pct', 'forest_loss_pct',
  // ---- provenance ----------------------------------------------------------
  'is_existing_workbook_control', 'n_controls_selected',
  'n_controls_within_50km', 'n_tier1_controls', 'n_tier2_controls',
  'n_tier3_controls', 'n_patches_found', 'n_patches_pooled',
  'patch_pool_capped', 'n_candidates_screened',
  'workbook_ctrl_patch_dist_m', 'workbook_ctrl_eligible',
  'workbook_ctrl_d_value', 'workbook_ctrl_match_tier',
  'ladder_step', 'quartet_grade', 'search_radius_km', 'koppen_source',
  'landcover_source', 'script_version', 'run_date'
];

// =============================================================================
//  11.  MAIN
// =============================================================================

function previewOneSettlement() {
  var row = null;
  for (var i = 0; i < EV_TABLE.length; i++) {
    if (EV_TABLE[i][0] === CFG.PREVIEW_QUARTET_ID) { row = EV_TABLE[i]; }
  }
  if (row === null) {
    print('PREVIEW_QUARTET_ID ' + CFG.PREVIEW_QUARTET_ID +
          ' is not in EV_TABLE.');
    return;
  }
  var r = processSettlement(row);

  print('=== Settlement ' + row[0] + ':  ' + row[1] + ' ===');
  print('1. built-up patches in the ' + CFG.SEARCH_MIN_KM + '-' +
        CFG.SEARCH_MAX_KM + ' km ring', r.allPatches.size());
  print('2. nearest patches carried forward', r.patches.size());
  print('3. survived the cheap gates and were measured', r.scored.size());
  print('4. eligible controls', r.eligible.size());
  print('5. selected (up to ' + CFG.CONTROLS_PER_SETTLEMENT + ')',
        r.controls.size());

  // Compact tables only. Printing all 122 properties of every row makes a
  // request big enough for the Code Editor to give up on, which is not a
  // useful thing to look at anyway.
  print('The settlement as measured:', ee.Feature(r.ev).select([
    'koppen_group', 'biome_num', 'adm0_code', 'elevation_m', 'slope_deg',
    'tree_cover_pct', 'water_dist_m', 'travel_time_min', 'pop_density_km2',
    'smod_class', 'protected_any_pct', 'protected_iucn12_pct']));
  print('The selected controls:', r.controls.select([
    'control_distance_km', 'd_value', 'match_tier', 'koppen_group',
    'elevation_m', 'tree_cover_pct', 'water_dist_m', 'population_est_patch',
    'village_tests_passed', 'criteria_failed']));

  Map.centerObject(ee.Geometry.Point([row[3], row[2]]), 10);
  // Water distance is a matching criterion and this layer was wrong once, so
  // it is drawn: zoom in and check against the basemap that the blue matches
  // the rivers and lakes you can see. If a river you know is there is missing,
  // WATER_OCCURRENCE_PCT is too high for this basin.
  Map.addLayer(PERM_WATER.selfMask(), {palette: ['0066ff']},
               'permanent water, as the script sees it', false);
  Map.addLayer(r.allPatches, {color: 'dddd88'}, 'all built-up patches', false);
  Map.addLayer(r.patches, {color: 'cccc00'}, 'patches carried forward', false);
  Map.addLayer(r.scored, {color: '00aaff'}, 'measured candidates', false);
  Map.addLayer(r.eligible, {color: 'ff8800'}, 'eligible controls');
  Map.addLayer(r.controls, {color: '00ff00'}, 'SELECTED controls');
  Map.addLayer(ee.Geometry.Point([row[3], row[2]]), {color: 'ff0000'},
               'the settlement');
  print('On the map: RED is the settlement, GREEN are its selected controls. ' +
        'Click a green dot to read its numbers. Tick the hidden layers in the ' +
        'Layers box if you want to see what was rejected.');
}

/** A single task covering exactly the settlements named in ONLY_QUARTET_IDS. */
function queueNamedSettlements() {
  var wanted = CFG.ONLY_QUARTET_IDS;
  var out = null, found = [];
  for (var i = 0; i < EV_TABLE.length; i++) {
    for (var k = 0; k < wanted.length; k++) {
      if (EV_TABLE[i][0] === wanted[k]) {
        var res = processSettlement(EV_TABLE[i]);
        out = (out === null) ? res.rows : out.merge(res.rows);
        found.push(EV_TABLE[i][0]);
      }
    }
  }
  if (out === null) {
    print('None of ONLY_QUARTET_IDS ' + wanted + ' is in EV_TABLE.');
    return;
  }
  print('Queued ONE task for settlement(s) ' + found + ' at a ' +
        CFG.SEARCH_MAX_KM + ' km search radius.');
  print('Run it, then read its Runtime and EECU-seconds in the Tasks tab. ' +
        'Use a settlement you have NOT run before: Earth Engine caches ' +
        'computed tiles, so re-running the same one reports a fraction of ' +
        'its real cost. Multiply the cold figure by 212.');
  Export.table.toDrive({
    collection:     out,
    description:    CFG.FILE_PREFIX + '_named',
    folder:         CFG.DRIVE_FOLDER,
    fileNamePrefix: CFG.FILE_PREFIX + '_named',
    fileFormat:     'CSV',
    selectors:      OUT_COLUMNS
  });
}

function queueExports() {
  if (CFG.ONLY_QUARTET_IDS.length > 0) { queueNamedSettlements(); return; }
  var nBatches = Math.ceil(EV_TABLE.length / CFG.BATCH_SIZE);
  var last = Math.min(CFG.FIRST_BATCH + CFG.BATCHES_PER_RUN - 1, nBatches - 1);

  if (CFG.FIRST_BATCH >= nBatches) {
    print('FIRST_BATCH is ' + CFG.FIRST_BATCH + ' but there are only ' +
          nBatches + ' batches (0 to ' + (nBatches - 1) + '). ' +
          'Every settlement has already been queued - nothing to do.');
    return;
  }

  print('Settlements ' + (CFG.FIRST_BATCH * CFG.BATCH_SIZE + 1) + ' to ' +
        Math.min((last + 1) * CFG.BATCH_SIZE, EV_TABLE.length) + ' of ' +
        EV_TABLE.length + '  ->  queueing batches ' + CFG.FIRST_BATCH +
        ' to ' + last + ' of 0 to ' + (nBatches - 1) + '.');

  for (var b = CFG.FIRST_BATCH; b <= last; b++) {
    var start = b * CFG.BATCH_SIZE;
    if (start >= EV_TABLE.length) { break; }
    var stop = Math.min(start + CFG.BATCH_SIZE, EV_TABLE.length);

    var out = null;
    for (var j = start; j < stop; j++) {
      var res = processSettlement(EV_TABLE[j]);
      out = (out === null) ? res.rows : out.merge(res.rows);
    }

    // three digits, so b011 sorts before b100 when BATCH_SIZE is 1 and there
    // are 212 batches rather than 53
    var tag = 'b' + ('00' + b).slice(-3);
    // With BATCH_SIZE 1 the task name carries the quartet id, so a failed or
    // cancelled task names the settlement it belongs to without any counting.
    var label = (CFG.BATCH_SIZE === 1)
      ? tag + '_q' + ('00' + EV_TABLE[start][0]).slice(-3)
      : tag;
    Export.table.toDrive({
      collection:     out,
      description:    CFG.FILE_PREFIX + '_' + label,
      folder:         CFG.DRIVE_FOLDER,
      fileNamePrefix: CFG.FILE_PREFIX + '_' + label,
      fileFormat:     'CSV',
      selectors:      OUT_COLUMNS
    });
  }
  var next = last + 1;
  if (next < nBatches) {
    print('Run these ' + (last - CFG.FIRST_BATCH + 1) + ' tasks from the ' +
          'Tasks tab. Then set CFG.FIRST_BATCH = ' + next +
          ' and run the script again to queue the next ' +
          Math.min(CFG.BATCHES_PER_RUN, nBatches - next) + '.');
  } else {
    print('This is the LAST group - batches 0 to ' + (nBatches - 1) +
          ' have now all been queued. Run them, then merge every batch CSV ' +
          'with scripts/03_merge_and_qc.py.');
  }
}

/**
 * Sample every base layer at one point, in a single reduceRegion. If this
 * prints a dictionary, then every asset id exists, every asset TYPE is right
 * (ee.Image against ee.ImageCollection), and every band name is spelled
 * correctly. It costs a few seconds, and it is the cheapest possible way to
 * find out that something is wrong - the alternative is queueing 27 export
 * tasks and reading the failure an hour later.
 */
function preflight() {
  var row  = EV_TABLE[0];
  var lon  = row[3], lat = row[2];
  var pt   = ee.Geometry.Point([lon, lat]);
  var region = pt.buffer(CFG.SEARCH_MAX_KM * 1000);

  // ---- check 1: does every asset load? ------------------------------------
  var stack = ee.Image.cat([
    BUILT_FRAC.rename('ghsl_built_frac'),
    NRES_FRAC.rename('ghsl_nonres_frac'),
    POP_DENS.rename('ghsl_pop_density_km2'),
    GHS_SMOD.rename('ghsl_smod_class'),
    BC_RES.rename('ghsl_built_c_residential'),
    DEM, SLOPE, TRI,
    PERM_WATER.rename('gsw_permanent_water'),
    KOPPEN,
    LANDCOVER.select('tree_cover_pct'),
    TRAVEL, GHM, VIIRS,
    GAIN.rename('hansen_gain'),
    contextImage(region),
    protectedAreaImage(region),
    studySiteImage(),
    externalProgrammeImage(),
    waterDistanceImage(lon, lat)
  ]).toFloat();

  print('=== PREFLIGHT on settlement ' + row[0] + ' (' + row[1] + ') ===');
  print('CHECK 1 - every asset id, type and band name. Values below mean all ' +
        'of them load.',
        stack.reduceRegion({
          reducer: ee.Reducer.first(), geometry: pt,
          scale: CFG.FOOTPRINT_SCALE_M, maxPixels: 1e8,
          tileScale: CFG.TILE_SCALE
        }));

  // ---- check 2: does the REAL measurement path return a number for every
  //      covariate? A layer can load perfectly and still hand back null if the
  //      reducer is asked to work on a grid coarser than the footprint, and a
  //      null does not fail where it is made - it fails later, in whatever
  //      arithmetic first touches it. So this runs the actual measurement used
  //      by every settlement and every control, and shows the result. ------
  var site = {
    ctx:   contextImage(region),
    pa:    protectedAreaImage(region),
    water: waterDistanceImage(lon, lat)
  };
  var measured = ee.Feature(
    measureFootprints(ee.FeatureCollection([ee.Feature(pt)]), site).first());

  print('CHECK 2 - the real measurement over the ' + CFG.SITE_RADIUS_M +
        ' m footprint. EVERY entry below must be a number. If any shows ' +
        'null, that layer returned nothing over the footprint.',
        measured.select(FOOTPRINT_REQUIRED));

  // ---- check 3: is every covariate PRESENT, by name? ----------------------
  // A property can go missing rather than null - reduceRegions names its
  // output after the reducer instead of the band when it is handed a
  // single-band image, so the value lands under the wrong name and the one you
  // asked for simply is not there. Counting properties by eye will not find
  // that. This names the missing one.
  var missing = ee.List(FOOTPRINT_REQUIRED)
                  .removeAll(measured.propertyNames());
  print('CHECK 3 - covariates MISSING from the measurement. This list MUST ' +
        'be empty. Anything named here would fail later as a null.', missing);
  print('        (for reference, everything the measurement produced:)',
        measured.propertyNames().sort());

  print('If all three checks look right: set CFG.RUN_MODE to PREVIEW.');
}

function main() {
  if (CFG.RUN_MODE === 'PREFLIGHT') {
    preflight();
  } else if (CFG.RUN_MODE === 'PREVIEW') {
    previewOneSettlement();
  } else if (CFG.RUN_MODE === 'EXPORT') {
    queueExports();
  } else {
    print('CFG.RUN_MODE must be PREFLIGHT, PREVIEW or EXPORT; got ' +
          CFG.RUN_MODE);
  }
}

// =============================================================================
//  12.  DATA BLOCK  -  the 212 settlements of Study_1_Final_Ecovillages.xlsx
//
//  Generated by scripts/01_prepare_inputs.py. Do not edit by hand; re-run the
//  preparation script if the workbook changes.
//
//  Columns: [quartet_id, name, latitude, longitude, documentary_population,
//            existing_control_lat, existing_control_lon]
//
//  A documentary_population of -1 means Stage 1 coding recorded 'not found'
//  (183 of the 212). The quartet is then matched on a GHSL population estimate
//  instead, measured over the same footprint at both arms, and the basis is
//  stated per row in parent_population_basis - which is exactly what field E1
//  asks for: "the quartet is matched on the remaining criteria and flagged".
// =============================================================================

var EV_TABLE = [
  [1, 'Soheili Village_Hara', 26.790237, 55.771104, -1, 26.745194, 55.934976],
  [2, 'Ecovillage Bhrugu Aranya', 49.610737, 19.816232, -1, 49.407189, 19.827935],
  [3, 'Lost Valley Education Center', 43.891293, -122.825738, -1, 43.823250, -123.131455],
  [4, 'Dream village biohub', 8.202246, -0.125017, -1, 8.038907, 0.231801],
  [5, 'Kuthumba Ecovillage', -33.978198, 23.493313, -1, -34.028030, 23.170619],
  [6, 'Ssamba Foundation – Uganda Volunteer Program', 0.513729, 32.732357, -1, 0.583064, 32.732703],
  [7, 'SEKEM', 30.420438, 31.635801, -1, 30.508677, 31.510029],
  [8, 'Kufunda Village', -17.976451, 31.156586, -1, -18.036591, 31.203081],
  [9, 'The Unity Eco-Village', 28.224812, 83.879931, -1, 28.213274, 84.075498],
  [10, 'Cabiokid Foundation', 15.229279, 120.848381, -1, 15.208200, 120.913474],
  [11, 'Konohana Family', 35.255504, 138.567401, -1, 35.211726, 138.547131],
  [12, 'Southern Life Community', 26.203635, 119.190170, -1, 26.544457, 119.432939],
  [13, 'Manav Chetna Vikas Kendra (MCVK)', 22.625327, 76.032970, -1, 22.643863, 76.097458],
  [14, 'Kibbutz Lotan', 29.988996, 35.086617, -1, 30.082668, 35.130790],
  [15, 'Biosphere Foundation', -8.160640, 114.585539, 15, -8.345773, 114.253752],
  [16, 'TI EcoVillage', 12.833221, 77.498425, 55, 12.746921, 77.412924],
  [17, 'Govardhan Ecovillage', 19.655445, 72.967781, 350, 19.701080, 72.893382],
  [18, 'Kibbutz Gezer', 31.876067, 34.920482, 300, 31.831506, 34.756642],
  [19, 'Taman Petanu Eco Neighborhood', -8.548690, 115.290196, 50, -8.491055, 115.388811],
  [20, 'Sadhana Forest India', 11.980512, 79.777322, 20, 12.082296, 79.706088],
  [21, 'Better In Belize Eco-Community', 16.995635, -89.046671, 25, 17.079554, -89.016382],
  [22, 'Rancho Mastatal', 9.673092, -84.373902, 22, 9.655272, -84.451962],
  [23, 'Sat Yoga Ashram &amp; Wisdom School', 9.409167, -83.831672, 25, 9.784185, -83.845379],
  [24, 'VerdEnergia Pacifica', 9.736122, -84.463414, 10, 10.052932, -84.462822],
  [25, 'Gaia Terra', 45.893946, 13.061545, 15, 45.846532, 12.965043],
  [26, 'Cambium · Leben in Gemeinschaft', 46.932440, 16.020261, 70, 46.891045, 16.095489],
  [27, 'Boekel Ecovillage', 51.595070, 5.681080, 61, 51.849542, 5.565910],
  [28, 'Co-housing project HASENDORF (= bunny', 48.300822, 15.829862, 36, 48.265406, 15.944758],
  [29, 'La Bolina', 36.929680, -3.583287, 10, 36.990087, -3.590452],
  [30, 'EcoVillage de Pourgues', 43.177351, 1.435599, 25, 43.244960, 1.288749],
  [31, 'Oasis du coq à l’Âme', 45.880030, 0.134812, 30, 45.881669, -0.105381],
  [32, 'meltemi', 38.004674, 24.021794, 184, 38.202777, 23.966530],
  [33, 'ECOlonie – Centre Ecologique International', 48.050363, 6.105263, 10, 47.921663, 6.097229],
  [34, 'Matavenero y Poibueno', 42.537166, -6.372006, 70, 42.582011, -6.312672],
  [35, 'Communauté de l’Arche de Saint-Antoine', 45.176013, 5.217054, 50, 45.121219, 5.093767],
  [36, 'Tamera', 37.720593, -8.518849, 170, 37.813180, -8.497341],
  [37, 'Cheiry', 46.751193, 6.836893, 60, 46.760402, 6.748892],
  [38, 'Hallingelille Ecovillage', 55.494351, 11.819877, 52, 55.329647, 11.882766],
  [39, 'Munksøgårds', 55.657897, 12.132336, 225, 55.682575, 11.892698],
  [40, 'Lebensgarten Steyerberg', 52.585216, 9.020483, 60, 52.547651, 9.209823],
  [41, 'Braziers Park', 51.554688, -1.083638, 20, 51.563265, -1.461936],
  [42, 'Sólheimar Iceland', 64.065725, -20.644837, 120, 64.117357, -20.498838],
  [43, 'Sieben Linden Ecovillage', 52.689416, 11.143641, 140, 52.719774, 11.372092],
  [44, 'Schloss Glarisegg', 47.654734, 8.956555, -1, 47.262049, 8.967357],
  [45, 'Villaggio Verde', 45.650872, 8.413166, -1, 45.802775, 8.429808],
  [46, 'hagaby', 59.148556, 15.116483, -1, 59.218215, 14.899258],
  [47, 'La CittÃ della Luce', 43.662751, 13.123505, -1, 43.600483, 13.270313],
  [48, 'Sunseed Desert Technology', 37.088377, -2.073451, -1, 37.114694, -2.013009],
  [49, 'ZEGG', 52.157004, 12.590874, -1, 52.111895, 12.748534],
  [50, 'Green Commune Belica', 41.401714, 20.952099, -1, 41.232557, 21.089224],
  [51, 'The Park, Ecovillage Findhorn', 57.653174, -3.593418, -1, 57.700813, -3.395008],
  [52, 'Holistic Center Manas', 45.992388, 14.658149, -1, 46.032604, 14.716812],
  [53, 'Hertha Levefællesskab/Hertha Living Community', 56.181872, 9.971224, -1, 56.180211, 9.888343],
  [54, 'Bowden House Community', 50.417254, -3.688328, -1, 50.387177, -3.862117],
  [55, 'Vlierhof', 51.846842, 6.081005, -1, 51.683339, 6.034345],
  [56, 'Charlottendals Farm and EcoVillage', 59.090864, 17.532511, -1, 58.927319, 17.099631],
  [57, 'LUMEN Ecovillage', 45.035623, 9.933535, -1, 44.978394, 10.079465],
  [58, 'The Hollies Centre for Practical Sustainability', 51.761673, -8.954811, -1, 51.780873, -8.867639],
  [59, 'Selba – Artosilla', 42.425796, -0.262284, -1, 42.578517, -0.113526],
  [60, 'Ecoaldea Los Portales', 37.784434, -5.956900, -1, 38.084279, -6.078634],
  [61, 'Herzfeld Sennrueti', 47.376031, 9.192655, -1, 47.317686, 9.050645],
  [62, 'Lebenstraumgemeinschaft Jahnishausen', 51.273941, 13.285410, -1, 51.337710, 13.192147],
  [63, 'Zonca Ecovillage Italy', 46.057074, 8.205941, -1, 45.999547, 8.588710],
  [64, 'Suderbyn Permaculture Eco-village', 57.573741, 18.208672, -1, 57.161113, 18.333076],
  [65, 'DNS The Necessary Teacher Training', 56.257160, 8.278040, -1, 56.111988, 8.422854],
  [66, 'Bhakti Tirtha Dhama', 49.809769, 29.514843, -1, 49.891615, 29.392200],
  [67, 'Ecovillage Torri Superiore', 43.840361, 7.551118, -1, 43.828035, 7.654786],
  [68, 'Freedom Village Georgia', 33.360134, -82.863336, -1, 33.536600, -83.081106],
  [69, 'Hearthstone Village', 49.781734, -124.337462, -1, 49.892165, -124.560029],
  [70, 'Windekind Commons Vermont Cohousing', 44.315808, -72.941782, -1, 44.042115, -72.603479],
  [71, 'HawaiiSPACE', 19.408572, -154.927618, -1, 19.744333, -155.106879],
  [72, 'Greenbriar Community School', 30.249293, -97.346087, -1, 30.286531, -97.239925],
  [73, 'White Hawk Ecovillage', 42.362704, -76.493173, -1, 42.618089, -76.724826],
  [74, 'The Farm', 35.479582, -87.328645, -1, 35.323776, -87.303772],
  [75, 'Camphill Village Minnesota', 45.848562, -94.911001, -1, 45.800390, -95.083921],
  [76, 'eastwind community', 36.558903, -92.308975, -1, 36.396460, -91.983332],
  [77, 'Cinderland Ecovillage', 19.518199, -154.844215, -1, 19.493920, -154.946304],
  [78, 'Whole Village', 43.860761, -80.106729, -1, 43.792347, -80.322747],
  [79, 'Synergia Ranch (HQ of Ecotechnics)', 35.491047, -106.095476, -1, 35.395322, -105.946757],
  [80, 'Dancing Rabbit Ecovillage', 40.332966, -92.096463, -1, 40.487284, -92.367534],
  [81, 'Earthaven Ecovillage', 35.519705, -82.202311, -1, 35.479283, -82.348162],
  [82, 'Living Well Community', 35.736970, -79.681773, -1, 35.794218, -79.548599],
  [83, 'Sirius Community', 42.419219, -72.425852, -1, 42.423086, -72.104825],
  [84, 'Hickory Nut Forest Eco-Community', 35.472630, -82.339856, -1, 35.451487, -82.287069],
  [85, 'Villages at Crest Mountain', 35.610457, -82.616044, -1, 35.655129, -82.696187],
  [86, 'IDEAL Society', 49.354342, -115.296459, -1, 49.416062, -115.423628],
  [87, 'Cite Ecologique (Qc, Canada)', 45.855019, -71.639806, -1, 45.903944, -71.646884],
  [88, 'Cedar Moon', 45.440790, -122.684757, -1, 45.408333, -122.922265],
  [89, 'Twin Oaks Community', 37.932583, -77.992429, -1, 37.775639, -77.899928],
  [90, 'Cobb Hill Cohousing', 43.548718, -72.425999, -1, 43.534244, -72.356330],
  [91, 'Avalon Organic Gardens &amp; EcoVillage', 31.575956, -111.041119, -1, 31.577358, -111.330663],
  [92, 'Ixixtlan', 18.870572, -98.398332, -1, 18.891371, -98.572339],
  [93, 'Abundance Ecovillage', 41.042021, -91.959907, -1, 40.957398, -92.051316],
  [94, 'Stowe Farm Community', 42.702264, -72.775739, -1, 42.525879, -72.789554],
  [95, 'Ecovillage at Ithaca', 42.441648, -76.542637, -1, 42.232787, -76.342170],
  [96, 'The Garden', 36.598200, -85.931557, -1, 36.640071, -85.792279],
  [97, 'Gita Nagari Eco-Farm and Sanctuary', 40.490405, -77.461402, -1, 40.535893, -77.818059],
  [98, 'The Camphill School', 40.136841, -75.707889, -1, 40.129520, -75.637765],
  [99, 'Hundredfold Farm', 39.889294, -77.376676, -1, 40.009052, -77.116400],
  [100, 'Sawyer Hill Ecovillage', 42.372911, -71.626188, -1, 42.433632, -71.608996],
  [101, 'Moora Moora Co-operative', -37.720704, 145.569887, -1, -37.538390, 145.474226],
  [102, 'The Ecovillage at Currumbin', -28.176828, 153.432741, -1, -28.430035, 153.470574],
  [103, 'Crystal Waters', -26.785530, 152.718245, -1, -26.729528, 152.718551],
  [104, 'Atamai Village', -41.141905, 172.956729, -1, -41.271814, 173.006472],
  [105, 'Narara Ecovillage', -33.392643, 151.328289, -1, -33.224186, 151.278573],
  [106, 'Tui Community', -40.811793, 172.957757, -1, -40.848993, 172.806874],
  [107, 'Wilderland', -36.886277, 175.674232, -1, -36.731139, 175.730585],
  [108, 'Bellbunya Sustainable Community', -26.491096, 152.853409, -1, -26.594966, 152.726214],
  [109, 'Aldinga Arts Ecovillage', -35.265685, 138.479025, -1, -35.391444, 138.463380],
  [110, 'Gulpa Creek Community', -35.722683, 144.893102, -1, -35.997911, 145.111709],
  [111, 'Eco Aldea de los glaciares sagrados – Maras', -13.339833, -72.144032, -1, -13.629295, -72.232709],
  [112, 'Terra Luminous', -24.021940, -47.068398, -1, -23.795549, -46.926605],
  [113, 'Ecovilla GAIA – Argentina', -34.947362, -59.337962, -1, -35.052645, -59.512790],
  [114, 'El Manzano', -37.156070, -72.286233, -1, -37.130076, -72.187405],
  [115, 'Agrovilla El Prado', 4.787184, -75.643927, -1, 4.937266, -75.738550],
  [116, 'Aldeafeliz Ecovillage', 4.987656, -74.279152, -1, 5.061372, -74.236755],
  [117, 'Peoples Coast Ecovillage Network', 13.089183, -16.759665, -1, 13.176568, -16.657114],
  [118, 'Tlholego Ecovillage and Learning Centre', -25.684519, 27.099662, -1, -25.632318, 26.967176],
  [119, 'Green Village Bali', -8.574186, 115.214248, -1, -8.494753, 115.081379],
  [120, 'Assalam eco-village by the Indian Ocean', -6.448134, 39.466153, -1, -6.365779, 39.453167],
  [121, 'The Sustainability Institute and Lynedoch', -33.982689, 18.768245, -1, -33.893539, 18.958776],
  [122, 'Chisapani Ecovillage Tarebhir', 28.207350, 83.906688, -1, 28.313530, 83.878369],
  [123, 'Ruma Eco Village , Mayagdi Nepal', 28.412866, 83.384985, -1, 28.464414, 83.668348],
  [124, 'Suwan organic farmstay', 17.671088, 102.839151, -1, 17.518994, 102.955463],
  [125, 'Daruma Ecovillage', 13.236989, 100.952719, -1, 13.042134, 101.309328],
  [126, 'Protopia Community', 10.593709, -84.841019, -1, 10.426250, -84.750713],
  [127, 'Eco Aldeia do Vale â€&quot; Instituto Permacultura', 38.880436, -9.307763, -1, 38.990948, -9.240627],
  [128, 'Spoluzemě Vrábsko', 49.464480, 14.103488, -1, 49.481349, 14.440453],
  [129, 'Friskoven', 55.095061, 14.944695, -1, 55.030884, 14.993181],
  [130, 'Gemeinschaft Sulzbrunn', 47.670555, 10.384863, -1, 47.640664, 10.483004],
  [131, 'Eotopia', 46.709743, 3.681777, -1, 46.651895, 3.716473],
  [132, 'ComunitÃ rigenerative', 45.994696, 12.999064, -1, 46.058297, 12.983499],
  [133, 'Thabarwa Nature Centre EU', 44.703496, 8.851423, -1, 44.661085, 8.803369],
  [134, 'Gut Alaune', 51.526603, 11.919516, -1, 51.552848, 11.787221],
  [135, 'Ängsbacka', 59.601268, 13.700271, -1, 59.557291, 13.051997],
  [136, 'New Mayapur', 47.084388, 1.405437, -1, 46.964371, 1.373627],
  [137, 'Los Guindales', 36.566965, -5.278144, -1, 36.633683, -5.202700],
  [138, 'Ferme de la Chaux, Goshen', 47.218402, 4.671591, -1, 47.245936, 4.586472],
  [139, 'Aletheia Springs', 38.394538, -122.550868, -1, 38.346771, -122.973058],
  [140, 'Entelechy', 48.805441, -123.489671, -1, 48.629878, -123.437678],
  [141, 'Pura Vida Village at Tico Time River Resort', 36.989190, -107.870480, -1, 37.094296, -108.170304],
  [142, 'ReTribe at NorthernShire', 44.506074, -72.865140, -1, 44.636197, -72.373328],
  [143, 'PORTAL XIBALBA: ECO-VILLAGE IN THE JUNGLE OF PLAYA DEL CARMEN', 20.699931, -87.060810, -1, 20.848968, -87.257291],
  [144, 'Emerald Earth Sanctuary', 39.025389, -123.292036, -1, 39.009686, -123.367868],
  [145, 'Maleny Eco Village', -26.758032, 152.848380, -1, -26.662654, 152.874061],
  [146, 'Billen Cliff', -28.612343, 153.133824, -1, -28.414116, 153.336730],
  [147, 'Arca Verde', -29.465191, -50.500893, -1, -29.100879, -50.633341],
  [148, 'Villa Productiva Agroecológica JANUS', -38.747310, -68.117620, -1, -38.972625, -68.131450],
  [149, 'Wisdom Forest', -1.055126, -77.895996, -1, -1.052041, -77.585320],
  [150, 'Bambako Eco Farm / YIRABAH Gambia', 13.405483, -15.767966, -1, 13.330654, -16.010259],
  [151, 'Honeyville Farm', -33.931231, 24.764866, -1, -33.872566, 25.028221],
  [152, 'Yasna Sloboda', 54.756701, 37.875068, -1, 54.768880, 37.996379],
  [153, 'Ecovillage Kovcheg', 55.061992, 36.128649, -1, 55.207609, 35.770937],
  [154, 'Yeniköy', 39.933706, 26.165414, -1, 39.974498, 26.277327],
  [155, 'Serene Eco Village', 18.315759, 73.624871, -1, 18.297391, 73.722415],
  [156, 'Tasman Ecovillage', -43.093448, 147.742258, -1, -42.819808, 147.801153],
  [157, 'Patanga', -30.438118, 152.694861, -1, -30.470420, 152.940369],
  [158, 'Ecolieu Argoumbat', 43.910315, 0.980360, -1, 43.933009, 0.876668],
  [159, 'Arterra Bizimodu', 42.715388, -1.325865, -1, 42.669069, -1.345455],
  [160, 'Keuruu Ecovillage', 62.306323, 24.622492, -1, 62.203563, 24.782437],
  [161, 'Zeleni Kruchi', 49.425633, 30.869992, -1, 49.449808, 30.716784],
  [162, 'Damanhur', 45.431012, 7.757471, -1, 45.557945, 7.830989],
  [163, 'Soheili Village', 26.755264, 55.787829, -1, 26.739630, 55.661757],
  [164, 'Land van Aine', 52.867512, 7.088633, -1, 53.199015, 7.087184],
  [165, 'Bali Ecovillage', -8.268028, 115.249245, -1, -8.303242, 115.220089],
  [166, 'Pun Pun', 19.214646, 99.012448, -1, 19.299291, 99.188755],
  [167, 'Neot Semadar', 30.048671, 35.026633, -1, 30.903621, 34.397062],
  [168, 'Witchcliffe Ecovillage', -34.024552, 115.104041, -1, -34.263387, 115.124676],
  [169, 'Almost Heaven Farms', 26.885190, 88.043108, -1, 26.930480, 87.690319],
  [170, 'Baireni Ecovillage', 26.981135, 86.533428, -1, 27.243992, 86.284456],
  [171, 'Blue Star Tapovan Trinidad', 10.349735, -61.452866, -1, 10.282388, -61.382822],
  [172, 'Chambalabamba', -4.274831, -79.203292, -1, -4.364657, -79.176765],
  [173, 'Chanchos de Monte', 10.793327, -84.393727, -1, 10.453156, -84.274345],
  [174, 'Ecovila Piracanga', -14.214697, -38.995034, -1, -14.257663, -39.265282],
  [175, 'Ecovila Raiz do Anuhmas', -22.791348, -47.050440, -1, -22.625981, -46.914141],
  [176, 'Ecovila Santa Margarida', -22.789479, -47.069783, -1, -22.994257, -47.188068],
  [177, 'Ecovillage Pentierebougou', 13.086727, -7.940589, -1, 13.135917, -8.048391],
  [178, 'Jyagdi EcoVillage Chapakot Syangja Nepal', 27.935840, 83.878329, -1, 28.037134, 83.799074],
  [179, 'Habiba Community', 29.010284, 34.670396, -1, 28.612207, 34.557279],
  [180, 'Fruit Haven EcoVillage Ecuador', -3.527531, -78.529830, -1, -3.204382, -78.434897],
  [181, 'Valle de Sensaciones', 36.957270, -3.136732, -1, 37.010000, -2.739901],
  [182, 'Las Cañadas Bosque de Niebla', 19.176892, -96.972307, -1, 19.381856, -97.078764],
  [183, 'Valdepielagos', 40.760722, -3.465693, -1, 40.867064, -3.057009],
  [184, 'Earthship Greater World Community', 36.494782, -105.752179, -1, 36.438188, -105.544605],
  [185, 'Wind Spirit Community', 33.146860, -110.835378, -1, 32.920233, -110.728282],
  [186, 'TerraSante Village', 32.111705, -111.254893, -1, 31.952695, -110.933283],
  [187, 'Catfarm', 43.498233, 3.657874, -1, 43.518894, 3.142473],
  [188, 'Grishino Ecovillage', 61.087028, 34.081300, -1, 61.425742, 34.439842],
  [189, 'Hurdal Ecovillage', 60.411096, 11.052614, -1, 60.740503, 11.366020],
  [190, 'Nackunga Community', 59.024944, 17.564475, -1, 58.921292, 17.450216],
  [191, 'Tuggelite Ecovillage', 59.422998, 13.438836, -1, 59.384740, 13.047757],
  [192, 'Ecotopia Romania — Stanciova', 45.862744, 21.575335, -1, 45.894688, 21.880667],
  [193, 'Schloss Tempelhof', 49.126124, 10.206793, -1, 49.194100, 10.369826],
  [194, 'Possibility Alliance', 40.074724, -92.458811, -1, 40.147564, -92.378033],
  [195, 'Rodnoe (Rodnoye) Settlement', 55.915364, 40.553046, -1, 56.140901, 40.870870],
  [196, 'Cloughjordan Ecovillage', 52.946515, -8.036953, -1, 52.984386, -7.924957],
  [197, 'O.U.R Ecovillage', 48.640102, -123.610282, -1, 48.691610, -123.603499],
  [198, 'Lammas Ecovillage (Tir-y-Gafel)', 51.934066, -4.623775, -1, 51.894809, -4.906431],
  [199, 'Friland', 56.280995, 10.585890, -1, 56.400436, 10.712567],
  [200, 'Sadhana Forest Haiti', 18.046360, -71.762129, -1, 18.572554, -72.072359],
  [201, 'Hockerton Housing Project', 53.097341, -0.929501, -1, 53.277152, -0.794060],
  [202, 'Den Selvforsynende Landsby (Self-Sufficient Village)', 55.098410, 10.426727, -1, 55.538228, 10.347170],
  [203, 'Cité Écologique (New Hampshire)', 44.935101, -71.477490, -1, 44.810547, -71.884611],
  [204, 'Brithdir Mawr', 52.000928, -4.806572, -1, 51.946032, -5.087031],
  [205, 'Permatopia', 55.301696, 12.190720, -1, 55.408290, 11.887740],
  [206, 'Sadhana Forest Kenya', 0.867336, 36.806313, -1, 0.949224, 36.765913],
  [207, 'Ecodorp Bergen', 52.651081, 4.693376, -1, 52.544906, 4.980055],
  [208, 'Eco Truly Park', -11.636889, -77.217187, -1, -11.469052, -77.271150],
  [209, 'Khula Dhamma Community', -32.697527, 28.194990, -1, -32.728124, 28.123413],
  [210, 'Umphakatsi Peace Ecovillage', -26.132179, 30.978230, -1, -26.032377, 31.049217],
  [211, 'Green Canvas of Light', -33.982512, 22.673458, -1, -34.034836, 22.236375],
  [212, 'Agatha Amani House', -0.735154, 36.473129, -1, -0.787038, 36.506111],
];

// =============================================================================
//  13.  ENTRY POINT
// =============================================================================

main();
