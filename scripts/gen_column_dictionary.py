import re, sys

DESC = {
 # identity
 'row_type': ('COMMUNITY for one of the 212 settlements, CONTROL for one of its conventional-rural controls. Every CONTROL row sits beneath the COMMUNITY row it belongs to.', 'both'),
 'quartet_id': ('The settlement\'s id in the Study 1 workbook, 1-212. This is the key that ties a control to its own community.', 'both'),
 'ecovillage_name': ('Name of the settlement this row belongs to.', 'both'),
 'control_id': ('EV003 for a settlement; EV003_CR07 for its seventh control. Unique across the file.', 'both'),
 'control_rank': ('0 on a settlement row; 1..15 on its controls, in ladder order (best first).', 'both'),
 'latitude': ('Latitude of this row\'s own site - the settlement, or the control village centre.', 'both'),
 'longitude': ('Longitude of this row\'s own site.', 'both'),
 'parent_latitude': ('Latitude of the settlement this row is matched to.', 'both'),
 'parent_longitude': ('Longitude of the settlement this row is matched to.', 'both'),
 'control_distance_km': ('Great-circle distance from the control to its settlement. 0 on a settlement row. The plan\'s control_distance_km.', 'both'),
 # grade
 'match_tier': ('1, 2 or 3 on a control (see tier_label). On a settlement row, the worst tier present in its block.', 'both'),
 'tier_label': ('Tier 1 - close / Tier 2 - adequate / Tier 3 - best available / not eligible.', 'both'),
 'd_value': ('Weighted standardised distance. Each covariate residual is expressed as a fraction of its own declared tolerance, so D = 1 means the covariates use up exactly their allowance on average. Lower is better.', 'control'),
 'd_within_declared_threshold': ('TRUE when D is at or below the declared acceptance bound (CFG.D_MAX_TIER3, default 2.5). A Tier-3 control kept above it is retained, and this column is how you see that.', 'control'),
 'star_rating': ('3-star D<0.5, 2-star 0.5<=D<1.5, 1-star D>=1.5. The same banding the Study 1 workbook uses.', 'control'),
 'n_hard_failed': ('How many of the eight hard gates this candidate failed. A selected control always shows 0.', 'control'),
 'n_soft_failed': ('How many of the six soft criteria (C3, C4, C6, C7, C8, C13) this control misses. 0 for Tier 1, at most 1 for Tier 2.', 'control'),
 'criteria_failed': ('Semicolon-separated list of every criterion this control fails, so a reader can see the whole picture in one cell without scanning 40 columns.', 'control'),
 # C1
 'koppen_group': ('Koppen main climate group at this site: A, B, C, D or E.', 'both'),
 'parent_koppen_group': ('Koppen main group of the settlement.', 'both'),
 'C1_koppen_match': ('TRUE when the control shares its settlement\'s Koppen main group. HARD gate.', 'control'),
 # C2
 'biome_num': ('RESOLVE 2017 BIOME_NUM at this site (1-14).', 'both'),
 'biome_name': ('The biome in words.', 'both'),
 'parent_biome_num': ('BIOME_NUM of the settlement.', 'both'),
 'parent_biome_name': ('The settlement\'s biome in words.', 'both'),
 'C2_biome_match': ('TRUE when control and settlement share a biome. HARD gate.', 'control'),
 # C3
 'elevation_m': ('Mean elevation over the 500 m footprint (SRTM, GMTED above 60 N).', 'both'),
 'parent_elevation_m': ('The settlement\'s mean elevation.', 'both'),
 'elevation_diff_m': ('Absolute difference in metres.', 'control'),
 'C3_elevation_within_300m': ('TRUE when the difference is at most 300 m. The plan\'s "elevation within 300 m". SOFT.', 'control'),
 # C4
 'terrain_class': ('flat (<2 deg), undulating (2-8), hilly (8-15), steep (>=15), from mean slope over the footprint.', 'both'),
 'parent_terrain_class': ('The settlement\'s terrain class.', 'both'),
 'slope_deg': ('Mean slope in degrees over the footprint.', 'both'),
 'parent_slope_deg': ('The settlement\'s mean slope.', 'both'),
 'tri': ('Terrain ruggedness, as the standard deviation of elevation in a 3x3 window of the DEM.', 'both'),
 'parent_tri': ('The settlement\'s ruggedness.', 'both'),
 'C4_terrain_class_match': ('TRUE when both sites fall in the same terrain class. The plan\'s "same terrain class". SOFT.', 'control'),
 'C4b_slope_within_10deg': ('TRUE when mean slopes are within 10 degrees. The workbook\'s C4, reported but not itself decisive.', 'control'),
 'C4c_tri_within_50pct': ('TRUE when ruggedness is within 50% of the settlement\'s own. The workbook\'s C4, reported.', 'control'),
 # C5
 'C5_distance_5_50km': ('TRUE when the control sits 5-50 km away: the plan\'s first ladder step. Required for Tier 1.', 'control'),
 'C5b_distance_5_100km': ('TRUE when the control sits 5-100 km away: the plan\'s extended step. HARD gate - nothing outside this range is ever selected.', 'control'),
 # C6
 'water_dist_m': ('Distance to permanent surface water (JRC GSW occurrence >= 80%), on a local equidistant grid, capped at 30 km. The mask is thresholded at GSW\'s own 30 m grid and carried up with a max reducer, so narrow rivers survive; note that occurrence >= 80% excludes reservoirs with a large seasonal drawdown, so in regulated basins this is distance to year-round water.', 'both'),
 'parent_water_dist_m': ('The settlement\'s distance to permanent water.', 'both'),
 'water_dist_diff_m': ('Absolute difference in metres.', 'control'),
 'water_dist_tol_m': ('The tolerance actually applied here: 50% of the settlement\'s own value, but never stricter than 500 m.', 'both'),
 'water_dist_censored': ('TRUE when this site or its settlement sits at the search cap (30 km) rather than at a measured distance, so C6 compared two censored values. Rare, but it means the criterion told you nothing for that pair.', 'both'),
 'C6_water_dist_within_tol': ('TRUE when the difference is within that tolerance. The plan holds water access constant BY MATCHING; this is that criterion. SOFT.', 'control'),
 # C7
 'travel_time_min': ('Travel time to the nearest city, minutes (Oxford MAP accessibility 2015).', 'both'),
 'parent_travel_time_min': ('The settlement\'s travel time.', 'both'),
 'travel_time_tol_min': ('50% of the settlement\'s own travel time, floored at 15 minutes.', 'both'),
 'C7_travel_within_50pct': ('TRUE when the difference is within that tolerance. The workbook\'s C7; accessibility is an adjust-for variable in the plan\'s causal diagram. SOFT.', 'control'),
 # C8
 'tree_cover_pct': ('Tree cover as a per cent of the 500 m footprint (ESA WorldCover class 10, or Dynamic World trees probability if configured).', 'both'),
 'parent_tree_cover_pct': ('The settlement\'s tree cover.', 'both'),
 'tree_cover_diff_pp': ('Absolute difference, percentage points.', 'control'),
 'C8_treecover_within_15pp': ('TRUE when within 15 percentage points. The plan\'s "tree cover within 15 percentage points" - the strongest single predictor, so it also carries the heaviest weight in D. SOFT.', 'control'),
 # C9
 'protected_any_pct': ('Per cent of the footprint inside ANY designated WDPA protected area (UNESCO-MAB biosphere reserves excluded by default - see METHODS).', 'both'),
 'protected_iucn12_pct': ('Per cent inside a WDPA area of IUCN category Ia, Ib or II.', 'both'),
 'C9_not_protected_area': ('TRUE when protected overlap is at most 5% of the footprint. The plan\'s "controls inside protected areas are excluded". HARD gate. Which of the two columns above is used is set by CFG.PA_EXCLUSION_MODE (default IUCN I-II, matching the workbook).', 'both'),
 # C10
 'restoration_signal_pct': ('Per cent of the footprint showing Hansen tree-cover GAIN. A satellite proxy for a restoration programme, not proof of one.', 'both'),
 'restoration_signal_flag': ('TRUE when gain is at or above 10% AND loss stayed below 5%. Gain beside matching loss is rotation forestry, not restoration, so both bounds must hold. A prompt for documentary follow-up, not an exclusion by default.', 'both'),
 'external_programme_hit': ('TRUE when the site falls inside a polygon of your own CFG.EXTERNAL_PROGRAMME_ASSET.', 'both'),
 'C10_no_external_programme': ('TRUE when the site is in none of those polygons (and, if you set CFG.TREAT_RESTORATION_SIGNAL_AS_EXCLUSION, also below the restoration signal). The plan\'s field G1. HARD gate. Read METHODS before trusting it: no global dataset of funded restoration programmes exists.', 'both'),
 # C11
 'adm0_code': ('FAO GAUL ADM0_CODE of the country the site sits in.', 'both'),
 'parent_adm0_code': ('The settlement\'s country code.', 'both'),
 'C11_same_country': ('TRUE when both sit in the same country. The plan holds country constant BY MATCHING, so this is a HARD gate: every selected control is in its settlement\'s country.', 'control'),
 # C12
 'smod_class': ('GHS-SMOD Degree of Urbanisation class: 11, 12, 13 rural; 21, 22, 23 urban cluster; 30 urban centre.', 'both'),
 'smod_label': ('That class in words.', 'both'),
 'urban_fraction_pct': ('Per cent of the footprint in SMOD class 21 or above.', 'both'),
 'pop_density_km2': ('Mean population density over the footprint, people per km2 (GHS-POP 2020).', 'both'),
 'C12_rural_settlement': ('TRUE when the site is in a rural SMOD class, has under 10% of its footprint in urban cells, and under 1500 people/km2. The plan\'s "classified rural". HARD gate.', 'both'),
 # C13
 'population_est_patch': ('Residents of the control VILLAGE itself, summed from GHS-POP over its built patch. On a settlement row, where no patch is detected, this repeats the 500 m footprint estimate.', 'both'),
 'population_est_footprint': ('Residents inside the 500 m footprint, from GHS-POP.', 'both'),
 'population_used_for_C13': ('Whichever of the two above was compared against the settlement, chosen to match the settlement\'s own basis.', 'control'),
 'parent_population': ('The settlement\'s population: the Stage 1 documentary figure where one exists, otherwise the GHSL footprint estimate.', 'both'),
 'parent_population_basis': ('Which of those two it is. 29 of the 212 settlements have a documentary figure; the other 183 are matched on the GHSL estimate and flagged here, which is what field E1 asks for.', 'both'),
 'population_ratio': ('The larger of the two populations divided by the smaller, so it is always >= 1.', 'both'),
 'C13_population_within_3x': ('TRUE when that ratio is at most 3. The plan\'s "population within a factor of three". SOFT.', 'control'),
 # village tests
 'V1_patch_size_plausible': ('The built patch is village-sized: 0.5-400 ha of patch, carrying 0.2-60 ha of actual built surface. MANDATORY.', 'control'),
 'V2_shape_not_linear': ('The patch is a place, not a line: bounding-box elongation at most 4, fill at least 0.25, longest side at most 2500 m. This is the test that rejects BRIDGES, RUNWAYS, pipelines and roadside ribbon development. MANDATORY.', 'control'),
 'V3_residential_dominant': ('The built space is mostly RESIDENTIAL: at most 40% non-residential built surface (GHS_BUILT_S), and at least 55% of the 10 m built pixels residential rather than non-residential (GHS_BUILT_C). This is the test that rejects FACTORIES, works, depots and warehouse parks.', 'control'),
 'V4_not_industrial_or_airport': ('At least 3 residents per hectare of built surface, and at most 25% of the footprint bare road surface. This is the test that rejects INDUSTRIAL ESTATES, AIRPORTS, terminals and motorway interchanges - all of which have buildings and pavement but almost no residents.', 'control'),
 'V5_not_on_water': ('At most 10% permanent water under the patch and 40% in the footprint: rejects bridges, piers, dams and stilt platforms.', 'control'),
 'V6_rural_open_land_context': ('At most 35% sealed surface in the footprint, and at least 40% tree, crop, grass or shrub: the village sits in open rural land.', 'control'),
 'V7_residents_present': ('The patch holds 10-10000 residents. MANDATORY. The lower bound is the study\'s own E3 threshold.', 'control'),
 'V8_not_a_study_site': ('The candidate is more than 3 km from every one of the 212 study settlements, so a control can never be another intentional community. MANDATORY.', 'control'),
 'village_tests_passed': ('How many of V1-V8 passed, 0-8.', 'control'),
 'village_class': ('A - strong (8/8), B - probable (6-7), C - weak (<6).', 'control'),
 'is_village_eligible': ('TRUE when all four mandatory tests passed AND at least CFG.MIN_VILLAGE_TESTS of the eight. HARD gate.', 'control'),
 # evidence
 'patch_area_ha': ('Area of the contiguous built-up patch that defines this village.', 'control'),
 'patch_built_area_ha': ('Built SURFACE inside that patch, in hectares.', 'control'),
 'patch_elongation': ('Long side of the patch bounding box divided by the short side. A runway or bridge runs high.', 'control'),
 'patch_bbox_fill': ('Patch area divided by bounding-box area. A diagonal line runs low.', 'control'),
 'patch_max_dim_m': ('Longest bounding-box side, in metres.', 'control'),
 'built_frac_pct': ('Built surface as a per cent of the 500 m footprint (GHS_BUILT_S).', 'both'),
 'parent_built_frac_pct': ('The settlement\'s built fraction. It enters D as a covariate and is a model covariate in the plan.', 'both'),
 'nonresidential_built_pct': ('Non-residential share of built surface, per cent (GHS_BUILT_S nres band).', 'both'),
 'residential_built_pct_10m': ('Per cent of the footprint that is residential built space at 10 m (GHS_BUILT_C classes 11-15).', 'both'),
 'nonres_built_pct_10m': ('Per cent that is non-residential built space at 10 m (classes 21-25).', 'both'),
 'residential_share_10m': ('Residential divided by residential-plus-non-residential at 10 m.', 'both'),
 'road_surface_pct_10m': ('Per cent of the footprint that is bare road surface (GHS_BUILT_C class 5).', 'both'),
 'surface_water_pct': ('Permanent water under the built patch, per cent.', 'both'),
 'footprint_water_pct': ('Permanent water in the 500 m footprint, per cent.', 'both'),
 'pop_per_built_ha': ('Residents per hectare of built surface. Low means industry, not housing.', 'both'),
 'cropland_pct': ('Cropland as a per cent of the footprint.', 'both'),
 'grass_shrub_pct': ('Grassland plus shrubland, per cent.', 'both'),
 'builtup_pct': ('Built-up land cover, per cent (from the land-cover source, not GHSL).', 'both'),
 'bare_pct': ('Bare or sparsely vegetated ground, per cent.', 'both'),
 'nightlight_radiance': ('VIIRS annual mean night-time radiance. A diagnostic: a bright, unpopulated patch is usually industrial.', 'both'),
 'human_modification': ('CSP global human modification index, 0-1.', 'both'),
 'forest_gain_pct': ('Hansen tree-cover gain in the footprint, per cent.', 'both'),
 'forest_loss_pct': ('Hansen tree-cover loss in the footprint, per cent.', 'both'),
 # provenance
 'C4_terrain_class_tolerant': ('TRUE when the classes are identical OR one class apart with slopes within 5 degrees. A settlement near a class boundary otherwise fails C4 against almost every neighbour: Lost Valley at 6.6 degrees, 1.4 below the 8-degree cut, failed 12 of 15 while every control was within 10 degrees of its slope.', 'control'),
 'C4_workbook_slope_and_tri': ('TRUE when slope is within 10 degrees AND ruggedness within 50 per cent - the Study 1 workbook\'s own operationalisation of C4.', 'control'),
 'C4_rule_applied': ('Which of the three C4 rules actually counted towards the tier: CLASS, CLASS_TOLERANT or SLOPE_TRI. All three are reported regardless, so the CSV can be re-filtered under a different rule without re-running.', 'both'),
 'n_tier1_controls': ('How many of this settlement\'s selected controls are Tier 1.', 'both'),
 'n_tier2_controls': ('How many are Tier 2.', 'both'),
 'n_tier3_controls': ('How many are Tier 3.', 'both'),
 'n_patches_pooled': ('How many of those patches were carried into the statistics, after the per-band cap and the shape gate.', 'both'),
 'patch_pool_capped': ('TRUE when the ring held more patches than the cap allowed, so the pool is a sample rather than the whole ring. Bands keep that sample spread across the ring instead of clustered near the settlement.', 'both'),
 'is_existing_workbook_control': ('TRUE when this control falls within 500 m of the conventional-rural control already held for this settlement in the Study 1 workbook - so you can see where the new search reproduces the old choice.', 'control'),
 'n_controls_selected': ('How many controls were selected for this settlement, 0-15. Identical on every row of a block.', 'both'),
 'n_controls_within_50km': ('How many of those sit inside 50 km. The rest came from the extended 50-100 km step of the ladder.', 'both'),
 'n_patches_found': ('How many built-up patches the detector found in the search ring, before any cap or criterion. A low number here explains a thin block.', 'both'),
 'n_candidates_screened': ('How many of those survived the cheap gates and were measured in full.', 'both'),
 'workbook_ctrl_patch_dist_m': ('How far the nearest SCORED patch is from the conventional-rural control this settlement already holds in the Study 1 workbook. The patch nearest that control is forced into the candidate pool, so a small value means the search reached the researcher\'s own choice and judged it; a large value means that patch did not survive the village tests or the cheap gates, which is itself a finding about the old control. -1 means nothing reached scoring.', 'both'),
 'workbook_ctrl_eligible': ('TRUE when that patch passed every hard gate, i.e. the new method would accept the control the researcher already chose.', 'both'),
 'workbook_ctrl_d_value': ('Its weighted standardised distance, for comparison against the controls actually selected.', 'both'),
 'workbook_ctrl_match_tier': ('Its tier, 0 if it was not eligible.', 'both'),
 'ladder_step': ('The worst tier among the settlement\'s best three controls: 1 all close, 2 the search was extended or a tolerance missed, 3 best available.', 'both'),
 'quartet_grade': ('That same tier, in words. Graded on the BEST THREE controls, which is the quartet the plan\'s tiers were written for - grading fifteen by their worst member makes every block Tier 3 and says nothing.', 'both'),
 'search_radius_km': ('The outer search radius used, in km.', 'both'),
 'koppen_source': ('Which Koppen layer produced C1.', 'both'),
 'landcover_source': ('ESA_WORLDCOVER or DYNAMIC_WORLD.', 'both'),
 'script_version': ('Version of the Earth Engine script that produced the row.', 'both'),
 'run_date': ('Date the export ran.', 'both'),
}

src = open('/home/user/GEE/scripts/02_stage2_control_matching.js', encoding='utf-8').read()
block = src.split('var OUT_COLUMNS = [',1)[1].split('];',1)[0]
cols = re.findall(r"'([^']+)'", block)

missing = [c for c in cols if c not in DESC]
extra   = [c for c in DESC if c not in cols]
if missing or extra:
    print('MISMATCH'); print(' undocumented:', missing); print(' stale:', extra); sys.exit(1)

# section boundaries, taken from the comment headers in OUT_COLUMNS
sections = re.findall(r"//\s*----\s*(.+?)\s*-*\n((?:\s*'[^\n]*\n)+)", block)
out = []
out.append('# Column dictionary - `stage2_rural_controls_FINAL.csv`\n')
out.append('Generated from `OUT_COLUMNS` in `scripts/02_stage2_control_matching.js`; '
           'regenerate with `scripts/gen_column_dictionary.py` if the script changes.\n')
out.append('The file holds **one row per settlement** (`row_type = COMMUNITY`) '
           'followed by **one row per control** (`row_type = CONTROL`) belonging '
           'to it. All 212 settlements appear, including any that found no '
           'eligible control.\n')
out.append('`Applies to` says which row types carry a real value; the other '
           'shows `n/a - settlement row` or is blank.\n')
seen = set()
for title, body in sections:
    names = re.findall(r"'([^']+)'", body)
    names = [n for n in names if n in DESC and n not in seen]
    if not names: continue
    seen.update(names)
    out.append('\n## %s\n' % title.strip())
    out.append('| Column | Applies to | Meaning |')
    out.append('|---|---|---|')
    for n in names:
        d, ap = DESC[n]
        ap = {'both':'both rows','control':'controls'}[ap]
        out.append('| `%s` | %s | %s |' % (n, ap, d.replace('|','\\|')))
left = [c for c in cols if c not in seen]
if left:
    out.append('\n## Other\n')
    out.append('| Column | Applies to | Meaning |'); out.append('|---|---|---|')
    for n in left:
        d, ap = DESC[n]
        out.append('| `%s` | %s | %s |' % (n, {'both':'both rows','control':'controls'}[ap], d))
out.append('')
open('/home/user/GEE/docs/COLUMN_DICTIONARY.md','w',encoding='utf-8').write('\n'.join(out))
print('wrote docs/COLUMN_DICTIONARY.md with %d columns in %d sections'
      % (len(cols), len(sections)))
