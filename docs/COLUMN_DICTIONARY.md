# Column dictionary - `stage2_rural_controls_FINAL.csv`

Generated from `OUT_COLUMNS` in `scripts/02_stage2_control_matching.js`; regenerate with `scripts/gen_column_dictionary.py` if the script changes.

The file holds **one row per settlement** (`row_type = COMMUNITY`) followed by **one row per control** (`row_type = CONTROL`) belonging to it. All 212 settlements appear, including any that found no eligible control.

`Applies to` says which row types carry a real value; the other shows `n/a - settlement row` or is blank.


## identity: which community does this row belong to

| Column | Applies to | Meaning |
|---|---|---|
| `row_type` | both rows | COMMUNITY for one of the 212 settlements, CONTROL for one of its conventional-rural controls. Every CONTROL row sits beneath the COMMUNITY row it belongs to. |
| `quartet_id` | both rows | The settlement's id in the Study 1 workbook, 1-212. This is the key that ties a control to its own community. |
| `ecovillage_name` | both rows | Name of the settlement this row belongs to. |
| `control_id` | both rows | EV003 for a settlement; EV003_CR07 for its seventh control. Unique across the file. |
| `control_rank` | both rows | 0 on a settlement row; 1..15 on its controls, in ladder order (best first). |
| `latitude` | both rows | Latitude of this row's own site - the settlement, or the control village centre. |
| `longitude` | both rows | Longitude of this row's own site. |
| `parent_latitude` | both rows | Latitude of the settlement this row is matched to. |
| `parent_longitude` | both rows | Longitude of the settlement this row is matched to. |
| `control_distance_km` | both rows | Great-circle distance from the control to its settlement. 0 on a settlement row. The plan's control_distance_km. |

## overall grade

| Column | Applies to | Meaning |
|---|---|---|
| `match_tier` | both rows | 1, 2 or 3 on a control (see tier_label). On a settlement row, the worst tier present in its block. |
| `tier_label` | both rows | Tier 1 - close / Tier 2 - adequate / Tier 3 - best available / not eligible. |
| `d_value` | controls | Weighted standardised distance. Each covariate residual is expressed as a fraction of its own declared tolerance, so D = 1 means the covariates use up exactly their allowance on average. Lower is better. |
| `d_within_declared_threshold` | controls | TRUE when D is at or below the declared acceptance bound (CFG.D_MAX_TIER3, default 2.5). A Tier-3 control kept above it is retained, and this column is how you see that. |
| `star_rating` | controls | 3-star D<0.5, 2-star 0.5<=D<1.5, 1-star D>=1.5. The same banding the Study 1 workbook uses. |
| `n_hard_failed` | controls | How many of the eight hard gates this candidate failed. A selected control always shows 0. |
| `n_soft_failed` | controls | How many of the six soft criteria (C3, C4, C6, C7, C8, C13) this control misses. 0 for Tier 1, at most 1 for Tier 2. |
| `criteria_failed` | controls | Semicolon-separated list of every criterion this control fails, so a reader can see the whole picture in one cell without scanning 40 columns. |

## C1 climate

| Column | Applies to | Meaning |
|---|---|---|
| `koppen_group` | both rows | Koppen main climate group at this site: A, B, C, D or E. |
| `parent_koppen_group` | both rows | Koppen main group of the settlement. |
| `C1_koppen_match` | controls | TRUE when the control shares its settlement's Koppen main group. HARD gate. |

## C2 biome

| Column | Applies to | Meaning |
|---|---|---|
| `biome_num` | both rows | RESOLVE 2017 BIOME_NUM at this site (1-14). |
| `biome_name` | both rows | The biome in words. |
| `parent_biome_num` | both rows | BIOME_NUM of the settlement. |
| `parent_biome_name` | both rows | The settlement's biome in words. |
| `C2_biome_match` | controls | TRUE when control and settlement share a biome. HARD gate. |

## C3 elevation

| Column | Applies to | Meaning |
|---|---|---|
| `elevation_m` | both rows | Mean elevation over the 500 m footprint (SRTM, GMTED above 60 N). |
| `parent_elevation_m` | both rows | The settlement's mean elevation. |
| `elevation_diff_m` | controls | Absolute difference in metres. |
| `C3_elevation_within_300m` | controls | TRUE when the difference is at most 300 m. The plan's "elevation within 300 m". SOFT. |

## C4 terrain

| Column | Applies to | Meaning |
|---|---|---|
| `terrain_class` | both rows | flat (<2 deg), undulating (2-8), hilly (8-15), steep (>=15), from mean slope over the footprint. |
| `parent_terrain_class` | both rows | The settlement's terrain class. |
| `slope_deg` | both rows | Mean slope in degrees over the footprint. |
| `parent_slope_deg` | both rows | The settlement's mean slope. |
| `tri` | both rows | Terrain ruggedness, as the standard deviation of elevation in a 3x3 window of the DEM. |
| `parent_tri` | both rows | The settlement's ruggedness. |
| `C4_terrain_class_match` | controls | TRUE when both sites fall in the same terrain class. The plan's "same terrain class". SOFT. |
| `C4b_slope_within_10deg` | controls | TRUE when mean slopes are within 10 degrees. The workbook's C4, reported but not itself decisive. |
| `C4c_tri_within_50pct` | controls | TRUE when ruggedness is within 50% of the settlement's own. The workbook's C4, reported. |

## C5 distance

| Column | Applies to | Meaning |
|---|---|---|
| `C5_distance_5_50km` | controls | TRUE when the control sits 5-50 km away: the plan's first ladder step. Required for Tier 1. |
| `C5b_distance_5_100km` | controls | TRUE when the control sits 5-100 km away: the plan's extended step. HARD gate - nothing outside this range is ever selected. |

## C6 distance to permanent water

| Column | Applies to | Meaning |
|---|---|---|
| `water_dist_m` | both rows | Distance to permanent surface water (JRC GSW occurrence >= 80%), on a local equidistant grid, capped at 60 km. |
| `parent_water_dist_m` | both rows | The settlement's distance to permanent water. |
| `water_dist_diff_m` | controls | Absolute difference in metres. |
| `water_dist_tol_m` | both rows | The tolerance actually applied here: 50% of the settlement's own value, but never stricter than 500 m. |
| `C6_water_dist_within_tol` | controls | TRUE when the difference is within that tolerance. The plan holds water access constant BY MATCHING; this is that criterion. SOFT. |

## C7 accessibility

| Column | Applies to | Meaning |
|---|---|---|
| `travel_time_min` | both rows | Travel time to the nearest city, minutes (Oxford MAP accessibility 2015). |
| `parent_travel_time_min` | both rows | The settlement's travel time. |
| `travel_time_tol_min` | both rows | 50% of the settlement's own travel time, floored at 15 minutes. |
| `C7_travel_within_50pct` | controls | TRUE when the difference is within that tolerance. The workbook's C7; accessibility is an adjust-for variable in the plan's causal diagram. SOFT. |

## C8 tree cover

| Column | Applies to | Meaning |
|---|---|---|
| `tree_cover_pct` | both rows | Tree cover as a per cent of the 500 m footprint (ESA WorldCover class 10, or Dynamic World trees probability if configured). |
| `parent_tree_cover_pct` | both rows | The settlement's tree cover. |
| `tree_cover_diff_pp` | controls | Absolute difference, percentage points. |
| `C8_treecover_within_15pp` | controls | TRUE when within 15 percentage points. The plan's "tree cover within 15 percentage points" - the strongest single predictor, so it also carries the heaviest weight in D. SOFT. |

## C9 protected area

| Column | Applies to | Meaning |
|---|---|---|
| `protected_any_pct` | both rows | Per cent of the footprint inside ANY designated WDPA protected area (UNESCO-MAB biosphere reserves excluded by default - see METHODS). |
| `protected_iucn12_pct` | both rows | Per cent inside a WDPA area of IUCN category Ia, Ib or II. |
| `C9_not_protected_area` | both rows | TRUE when protected overlap is at most 5% of the footprint. The plan's "controls inside protected areas are excluded". HARD gate. Which of the two columns above is used is set by CFG.PA_EXCLUSION_MODE (default IUCN I-II, matching the workbook). |

## C10 external funding or programme

| Column | Applies to | Meaning |
|---|---|---|
| `restoration_signal_pct` | both rows | Per cent of the footprint showing Hansen tree-cover GAIN. A satellite proxy for a restoration programme, not proof of one. |
| `restoration_signal_flag` | both rows | TRUE when that proxy is at or above 10%. A prompt for documentary follow-up on a shortlist, not an exclusion by default. |
| `external_programme_hit` | both rows | TRUE when the site falls inside a polygon of your own CFG.EXTERNAL_PROGRAMME_ASSET. |
| `C10_no_external_programme` | both rows | TRUE when the site is in none of those polygons (and, if you set CFG.TREAT_RESTORATION_SIGNAL_AS_EXCLUSION, also below the restoration signal). The plan's field G1. HARD gate. Read METHODS before trusting it: no global dataset of funded restoration programmes exists. |

## C11 country

| Column | Applies to | Meaning |
|---|---|---|
| `adm0_code` | both rows | FAO GAUL ADM0_CODE of the country the site sits in. |
| `parent_adm0_code` | both rows | The settlement's country code. |
| `C11_same_country` | controls | TRUE when both sit in the same country. The plan holds country constant BY MATCHING, so this is a HARD gate: every selected control is in its settlement's country. |

## C12 rural

| Column | Applies to | Meaning |
|---|---|---|
| `smod_class` | both rows | GHS-SMOD Degree of Urbanisation class: 11, 12, 13 rural; 21, 22, 23 urban cluster; 30 urban centre. |
| `smod_label` | both rows | That class in words. |
| `urban_fraction_pct` | both rows | Per cent of the footprint in SMOD class 21 or above. |
| `pop_density_km2` | both rows | Mean population density over the footprint, people per km2 (GHS-POP 2020). |
| `C12_rural_settlement` | both rows | TRUE when the site is in a rural SMOD class, has under 10% of its footprint in urban cells, and under 1500 people/km2. The plan's "classified rural". HARD gate. |

## C13 population

| Column | Applies to | Meaning |
|---|---|---|
| `population_est_patch` | both rows | Residents of the control VILLAGE itself, summed from GHS-POP over its built patch. On a settlement row, where no patch is detected, this repeats the 500 m footprint estimate. |
| `population_est_footprint` | both rows | Residents inside the 500 m footprint, from GHS-POP. |
| `population_used_for_C13` | controls | Whichever of the two above was compared against the settlement, chosen to match the settlement's own basis. |
| `parent_population` | both rows | The settlement's population: the Stage 1 documentary figure where one exists, otherwise the GHSL footprint estimate. |
| `parent_population_basis` | both rows | Which of those two it is. 29 of the 212 settlements have a documentary figure; the other 183 are matched on the GHSL estimate and flagged here, which is what field E1 asks for. |
| `population_ratio` | both rows | The larger of the two populations divided by the smaller, so it is always >= 1. |
| `C13_population_within_3x` | controls | TRUE when that ratio is at most 3. The plan's "population within a factor of three". SOFT. |

## is it really a village

| Column | Applies to | Meaning |
|---|---|---|
| `V1_patch_size_plausible` | controls | The built patch is village-sized: 0.5-400 ha of patch, carrying 0.2-60 ha of actual built surface. MANDATORY. |
| `V2_shape_not_linear` | controls | The patch is a place, not a line: bounding-box elongation at most 4, fill at least 0.25, longest side at most 2500 m. This is the test that rejects BRIDGES, RUNWAYS, pipelines and roadside ribbon development. MANDATORY. |
| `V3_residential_dominant` | controls | The built space is mostly RESIDENTIAL: at most 40% non-residential built surface (GHS_BUILT_S), and at least 55% of the 10 m built pixels residential rather than non-residential (GHS_BUILT_C). This is the test that rejects FACTORIES, works, depots and warehouse parks. |
| `V4_not_industrial_or_airport` | controls | At least 3 residents per hectare of built surface, and at most 25% of the footprint bare road surface. This is the test that rejects INDUSTRIAL ESTATES, AIRPORTS, terminals and motorway interchanges - all of which have buildings and pavement but almost no residents. |
| `V5_not_on_water` | controls | At most 10% permanent water under the patch and 40% in the footprint: rejects bridges, piers, dams and stilt platforms. |
| `V6_rural_open_land_context` | controls | At most 35% sealed surface in the footprint, and at least 40% tree, crop, grass or shrub: the village sits in open rural land. |
| `V7_residents_present` | controls | The patch holds 10-10000 residents. MANDATORY. The lower bound is the study's own E3 threshold. |
| `V8_not_a_study_site` | controls | The candidate is more than 3 km from every one of the 212 study settlements, so a control can never be another intentional community. MANDATORY. |
| `village_tests_passed` | controls | How many of V1-V8 passed, 0-8. |
| `village_class` | controls | A - strong (8/8), B - probable (6-7), C - weak (<6). |
| `is_village_eligible` | controls | TRUE when all four mandatory tests passed AND at least CFG.MIN_VILLAGE_TESTS of the eight. HARD gate. |

## the evidence behind those tests

| Column | Applies to | Meaning |
|---|---|---|
| `patch_area_ha` | controls | Area of the contiguous built-up patch that defines this village. |
| `patch_built_area_ha` | controls | Built SURFACE inside that patch, in hectares. |
| `patch_elongation` | controls | Long side of the patch bounding box divided by the short side. A runway or bridge runs high. |
| `patch_bbox_fill` | controls | Patch area divided by bounding-box area. A diagonal line runs low. |
| `patch_max_dim_m` | controls | Longest bounding-box side, in metres. |
| `built_frac_pct` | both rows | Built surface as a per cent of the 500 m footprint (GHS_BUILT_S). |
| `parent_built_frac_pct` | both rows | The settlement's built fraction. It enters D as a covariate and is a model covariate in the plan. |
| `nonresidential_built_pct` | both rows | Non-residential share of built surface, per cent (GHS_BUILT_S nres band). |
| `residential_built_pct_10m` | both rows | Per cent of the footprint that is residential built space at 10 m (GHS_BUILT_C classes 11-15). |
| `nonres_built_pct_10m` | both rows | Per cent that is non-residential built space at 10 m (classes 21-25). |
| `residential_share_10m` | both rows | Residential divided by residential-plus-non-residential at 10 m. |
| `road_surface_pct_10m` | both rows | Per cent of the footprint that is bare road surface (GHS_BUILT_C class 5). |
| `surface_water_pct` | both rows | Permanent water under the built patch, per cent. |
| `footprint_water_pct` | both rows | Permanent water in the 500 m footprint, per cent. |
| `pop_per_built_ha` | both rows | Residents per hectare of built surface. Low means industry, not housing. |
| `cropland_pct` | both rows | Cropland as a per cent of the footprint. |
| `grass_shrub_pct` | both rows | Grassland plus shrubland, per cent. |
| `builtup_pct` | both rows | Built-up land cover, per cent (from the land-cover source, not GHSL). |
| `bare_pct` | both rows | Bare or sparsely vegetated ground, per cent. |
| `nightlight_radiance` | both rows | VIIRS annual mean night-time radiance. A diagnostic: a bright, unpopulated patch is usually industrial. |
| `human_modification` | both rows | CSP global human modification index, 0-1. |
| `forest_gain_pct` | both rows | Hansen tree-cover gain in the footprint, per cent. |
| `forest_loss_pct` | both rows | Hansen tree-cover loss in the footprint, per cent. |

## provenance

| Column | Applies to | Meaning |
|---|---|---|
| `is_existing_workbook_control` | controls | TRUE when this control falls within 500 m of the conventional-rural control already held for this settlement in the Study 1 workbook - so you can see where the new search reproduces the old choice. |
| `n_controls_selected` | both rows | How many controls were selected for this settlement, 0-15. Identical on every row of a block. |
| `n_controls_within_50km` | both rows | How many of those sit inside 50 km. The rest came from the extended 50-100 km step of the ladder. |
| `n_patches_found` | both rows | How many built-up patches the detector found in the 5-100 km ring before any criterion was applied. A low number here explains a thin block. |
| `n_candidates_screened` | both rows | How many of those survived the cheap gates and were measured in full. |
| `ladder_step` | both rows | The worst tier in this settlement's block: 1 all controls close, 2 the search was extended or a tolerance missed, 3 best available. |
| `quartet_grade` | both rows | That same tier, in words. The plan's three-tier quartet grading. |
| `search_radius_km` | both rows | The outer search radius used, in km. |
| `koppen_source` | both rows | Which Koppen layer produced C1. |
| `landcover_source` | both rows | ESA_WORLDCOVER or DYNAMIC_WORLD. |
| `script_version` | both rows | Version of the Earth Engine script that produced the row. |
| `run_date` | both rows | Date the export ran. |
