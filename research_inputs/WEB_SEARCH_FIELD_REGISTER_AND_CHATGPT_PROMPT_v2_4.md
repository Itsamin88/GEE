# Web-search data collection — field register and crawler prompt

**Version 2.4 · aligned to THE_SIMPLIFIED_PLAN_v3.8 · pairs with Stage_1_Documentary_Coding_Workbook_v6**

Three parts. **Part A** is the field register — what to collect, in what format, with the coding rules. **Part B** is a ready-to-paste prompt for ChatGPT, built from Part A. **Part C** is honest guidance on what to expect and how to check it.

---

## What changed in version 2.4

Version 2.3 assumed one community has one website. It does not. Most have several addresses — a current site, an older domain nobody links to any more, a Facebook page, a YouTube channel, a directory listing — and version 2.3's Stage 1 said *"establish the primary source"*, singular, which funnelled everything through one of them.

| Change | Effect |
|---|---|
| **Stage 0 — BUILD THE SOURCE SET** is new | Every address you supply and every one the assistant finds is enumerated, typed and crawled as a separate target. The crawl is now **ten stages, numbered 0 to 9**. Stages 1 to 8 keep their old numbers so every existing reference to "Stage 5" or "Stage 6" still points where it did |
| **Stage 2 gains PER-PLATFORM enumeration rules** | `sitemap.xml` and forty URL paths are *website* instructions and do nothing on Instagram. Facebook, Instagram, YouTube, Vimeo, blog platforms, directory listings, crowdfunding pages, LinkedIn and hosting platforms each get their own method |
| **Stage 4 gains the archive index query** | One request to the Wayback CDX index returns *every URL ever archived* under a domain, including pages that no longer exist and are linked from nowhere. This is the single largest yield increase in the protocol |
| **Stage 9 — CROSS-SOURCE RECONCILIATION** is new | With several addresses you will get conflicting values. Stage 9 says what to do with them, and it is where the independence rule is applied |
| **The independence rule is stated properly** | Two sources corroborate each other only if neither derives from the other. A directory listing copied from the community's website is the **same** source as that website. This is version 2.3's "two pages of one website are ONE channel", extended to the whole source set |
| **Anti-fabrication rule 12** | Social media is a far richer fabrication surface than a website: undated posts, feeds that imply chronology, photographs that look like evidence. Rule 12 closes it |
| **A truncation report is now mandatory** | You cannot instruct a model past its tool budget. You *can* make it say where it stopped. `stages_completed` and `crawl_truncated` turn a silent half-search into a recorded one |
| **Run modes** | One community can be run once or split across several runs. Part C works out what each costs and which communities are worth the extra passes |
| **Five new fields (I8–I12)** | `source_set_supplied`, `source_set_discovered`, `independence_groups`, `stages_completed`, `crawl_truncated` |
| **A paste map (§A.3)** | Which block lands on which workbook sheet and which columns. Version 2.3 named field names but never said where they go, and two fields had nowhere to go at all |

### Three corrections, not additions

These were errors in version 2.3, found by counting rather than reading:

| Error | Correction |
|---|---|
| Block B called the field `e1_self_identification_quote` in Part A and `e1_self_identification` in Part B | The workbook column is `e1_self_identification`. **Part A was wrong**; both now say `e1_self_identification` |
| `coordinate_agreement` had three different value sets — `differs — see note` in Part A, `differs (say how)` in Part B, `differs` in the workbook dropdown | All three now read **`agrees` / `differs` / `no published location`**, matching the dropdown. Anything qualifying it goes in the notes column |
| Block E was headed "13 fields" while listing **15** named fields, so the stated register total of 81 was really 83 | The heading is corrected. With the five new provenance fields the register now holds **88 fields**: A 5, B 8, C 14, D 7, E 15, F 14, G 6, H 7, I 12 |

### What did NOT change, and why

Plan versions 3.7 and 3.8 arrived after this register was last revised, and **neither one touches it.** That is worth stating rather than leaving you to wonder whether something was missed:

- **v3.7 added SC17**, the multi-scale window check. It recomputes three configuration metrics at 40 m and 100 m as well as 70 m. Every input already exists in the extraction; nothing is coded documentarily.
- **v3.8 added the control-distance ladder** and the variable `control_distance_km`. That is a **Stage 2 matching output** — it is produced when you build the quartets, not when you read published sources. It belongs in the Stage 2 quartet register, which does not exist yet.

So the alignment work from v3.6 to v3.8 was a version stamp. The substance of this revision is the multi-address problem, which is not a plan change at all — it is a defect in how this register handles the sources you already have.

---
## What changed in version 2.3

Plan v3.6 replaced the measurement circle with a **hand-drawn polygon** at every settlement. That changes what this register is for, though not much of what it collects.

| Change | Effect |
|---|---|
| **Managed area is now a CHECK, not a geometry-setter** | The polygon you draw defines the measurement area. The documentary figure corroborates it — still valuable, but it no longer decides anything on its own |
| **`size_class_documentary` is retired** | Replaced by `documentary_area_note`. The class now comes from the polygon's area, so a documentary class serves no purpose |
| **The scope note is sharper** | ChatGPT supplies **six** documentary fields plus its source rows. Everything about the polygon is yours |
| **One rule made absolute** | ChatGPT must never estimate an area from imagery. It could not before either, but the polygon makes the boundary between the two routes far more consequential |

**Everything else is unchanged.** The eight-stage crawl protocol, the eleven anti-fabrication rules, all thirteen practice codes and every other block carry over exactly.

---

## What changed in version 2.2

*Historical record. Version 2.3 superseded the part below where it says managed area sets the measurement radius — since plan v3.6 the drawn polygon does that, and `size_class_documentary` has been retired.*

The plan's size-matched measurement zones (v3.4) turned **managed area from an ordinary descriptive field into a load-bearing one**. It now sets each site's measurement radius and is the predictor in analysis A9. This version gives it the weight Block C already has.

| Change | Effect |
|---|---|
| **Block E is restructured**, with managed area promoted to its own priority sub-block | A wrong area now puts a community in the wrong measurement zone, not just a wrong descriptive table |
| **Four new fields** — `managed_area_lower_ha`, `managed_area_upper_ha`, `managed_area_basis`, `managed_area_source_class` | A source saying "about 6 hectares" sits *exactly* on a class boundary. Without a band and a basis you cannot tell a firm 6 from a vague one |
| **`size_class_documentary` added** | So the paste-into-workbook is complete. **This is the documentary class only** — the final class comes from resolving it against your own visual trace |
| **One scope note added to the prompt** | ChatGPT does the DOCUMENTARY route. The VISUAL route is yours, on imagery, by the procedure in §7.1a of the plan. The prompt now says so, to stop it guessing at an extent it cannot see |
| **Register grows 77 → 81 fields** | *Corrected in v2.4: the count was wrong. Block E was headed 13 fields while carrying 15, so the true total was 83* |

**One thing ChatGPT must never do, now stated explicitly in the prompt:** estimate a managed area from satellite or map imagery. It cannot measure area reliably, and the plan needs that number to come from a controlled tracing procedure, not from an impression.

---

## What changed in version 2.1

Version 2.0 mentioned academic literature in **three lines**, as one bullet among seven, while giving the community's own website four methods and forty paths. That was a real imbalance: for the communities that *have* been studied, a thesis or a project report is often the single best source in existence — dated, independent, and written by someone who visited.

| Change | Effect |
|---|---|
| **Stage 5 — ACADEMIC LITERATURE** is now its own stage | Eleven named databases, a search-string procedure, forward and backward citation chaining, and a requirement to open **full text**, not abstracts |
| **Stage 6 — GREY LITERATURE** is now its own stage | Grey literature is defined explicitly (fourteen types), with named funding databases. **EU and national grant records are rank-1 onset evidence** and almost nobody looks for them |
| The crawl is now **eight stages**, not six | Target raised to 25–40 URLs per settlement |
| **Two new provenance fields** (I6, I7) | The academic and grey searches must be logged — which databases, how many hits, how many opened in full |
| **A new anti-fabrication rule, number 11** | Most communities have NO academic literature. Finding none is the *expected* result. Inventing a paper to look thorough is now named as the worst failure mode available |

Everything else — the field register, the anti-fabrication rules, the output format — carries over from version 2.0.

---

## What changed from version 1.0

| Change | Why |
|---|---|
| **PC13 added — land restoration or rehabilitation, non-tree** | The codebook is now **thirteen** codes. v1.0 had twelve, and only PC07 covered restoration — and only *tree* planting |
| **Cohort flag added (C14)** | The plan's longitudinal cohort needs onset in **2020–2021 (core)** or **2019 (extension)**. Flagging as you code is what lets you make decision D4 at community 100 |
| **A full crawl protocol** | v1.0 said "search deeply". This gives a procedure |
| **Website and social URLs as inputs** | Removes the least reliable step — finding the site |
| **Anti-fabrication rules made absolute** | Eleven rules plus a mandatory self-check |
| **A minimal CONTROL mode** | So the same prompt works for conventional-village controls |
| **GEE exclusion list extended** | ~40 quantities, including everything added in v3.1–v3.3 |

---

# PART A — The field register

**88 fields in nine blocks:** A identity 5 · B eligibility 8 · C onset 14 · D activity 7 · E size and land 15 · F practice codes 14 · G status 6 · H context 7 · I provenance 12.

## A.0 What NOT to search for

About forty quantities come from Google Earth Engine, not the web. Searching for them wastes budget and risks importing a number computed on an incompatible basis.

| Do not search | Source |
|---|---|
| VM1–VM14 (all fourteen vegetation condition metrics) | Sentinel-2, computed in the pipeline |
| PM1–PM3 (provisioning metrics) | Same |
| FC1–FC4 (flag components) | Same |
| CA (contour alignment) | SRTM aspect + land-cover boundary orientation |
| VCI, VCI-P/S/T/C, PCI, MDS, LCC | Derived from the above |
| `built_fraction`, `tree_cover_pct` | Dynamic World |
| `elevation_m`, `slope_deg`, terrain class | SRTM |
| `water_dist_m` | Global Surface Water — a matching criterion since v3.2, but satellite-derived |
| `koppen_group`, `biome` | Beck et al. / RESOLVE ecoregions |
| Annual rainfall, driest month, drought-year classification | CHIRPS |
| `n_clear` | Extraction output |
| `polygon_area_ha`, `polygon_iou`, `reference_circle` | **Your** drawing, by plan §7.1a. Never estimated from imagery by anyone else |
| `control_distance_km` | A **Stage 2** matching output under the v3.8 distance ladder, not documentary coding |

**One exception.** If a community publishes its own figures for elevation, rainfall or landholding size, record them as *context* in Block H. Never substitute them for the pipeline values.

---

## A.1 Two modes

| Mode | Used for | Blocks required |
|---|---|---|
| **SETTLEMENT** | The 212 intentional communities, and every cohort candidate | All blocks, A to I |
| **CONTROL** | Conventional-village controls | Blocks A, B4–B8 and I only — a control makes no ecological claim |

---

## A.2 Run modes — when one community needs more than one run

This is the part of the design that actually raises yield, and it is worth understanding before you use the prompt.

**The constraint is real and no wording removes it.** ChatGPT fetches pages one at a time and has a budget of tool calls per response. Version 2.3 already told you to expect 25–40 pages on a good run. That number is a property of the *run*, not of the community — so the more addresses you give it, the thinner each one gets.

**Worked through.** Suppose a community has four addresses: its website, an old domain, a Facebook page and a YouTube channel.

- **One run.** 25–40 pages have to cover four addresses *plus* the archive stage, the academic stage, the grey-literature stage and the local-language sweep. If the addresses take half the budget, that is about 12–20 pages across four targets — **three to five pages each**. You will get the homepage and the About page of each, and nothing older than the current site design.
- **Four runs, one per address, plus a fifth for Stages 5–6.** Each run carries its own 25–40 page budget. Total **125–200 pages** for that community, of which 100–160 are on the addresses themselves. That is four to six times the depth from an identical tool.

The arithmetic is simply that the budget is per run, so runs multiply it.

| Run mode | What it does | When to use it |
|---|---|---|
| `RUN: FULL` | All ten stages, all addresses, in one pass | The default. Every community gets this first |
| `RUN: SOURCE <address_id>` | Stages 0–4 and 7 on **one** address only | A community with several substantive addresses, after FULL showed the extra ones were skimmed |
| `RUN: ACADEMIC` | Stages 5, 6 and 8 only, exhaustively | Any community that looks likely to have been studied — large, old, well known, or near a university |
| `RUN: RECONCILE` | No new fetching. Reads the outputs of the previous runs and produces one merged record | Whenever a community was split across more than one run. **Never skip it** — an unreconciled community has several partial records and no single answer |

Part C sets out which communities are worth the extra runs and what it costs you in hours.

---

## A.3 The paste map — where each block lands

Version 2.3 gave field names but never said where they go, and two fields had nowhere to go. Everything the assistant returns now has exactly one destination.

| Block | Sheet | Columns |
|---|---|---|
| A identity | `O1_Community_Attributes` | B–E **and H** (`coordinate_agreement` sits at H because `latitude` and `longitude`, which are yours, occupy F and G) |
| B eligibility | `O1_Community_Attributes` | I–P |
| C onset | `O3_Onset_Register` | C–R, **except I and M**: `onset_band_width_years` calculates itself and `resolution_rule` is yours to record when you settle a conflict |
| D activity | `O1_Community_Attributes` | AF–AL (`channel_count` at AK calculates itself from AF–AJ) |
| E size and land | `O1_Community_Attributes` | Q–AE **except U**, plus `documentary_area_note` in BK. U is `polygon_area_ha`, which reads itself from `O10` and must never be supplied by the assistant |
| F practice codes | `O2_Practice_Matrix` (the level) and `O2b_Practice_Evidence` (one row per coded practice) | C–O, then the O2b rows |
| G status | `O1_Community_Attributes` | AN–AS |
| H context | `O1_Community_Attributes` | AT–AZ |
| I1–I5 provenance | `O1_Community_Attributes` | BA–BE |
| I6 `academic_search_log`, I7 `grey_literature_log` | `O7_Search_Log` | **Unpacked into rows** — one row per database, including those that returned nothing. They are not single cells |
| I8 `source_set_supplied`, I9 `source_set_discovered` | `O11_Source_Set` | **Unpacked into rows** — one row per web address |
| I10–I12 | `O1_Community_Attributes` | BL, BM, BN |
| The sources themselves | `O6_Source_Index` | One row each, with `independence_group` in Q |

**`O1_Community_Attributes` is the single paste target.** The six documentary area fields used to be typed into `O10_Polygon_And_Area` as well. In workbook v6 `O10` reads them from `O1` automatically, so they cannot diverge and you enter them once. Everything on `O10` other than those six columns is yours, from the drawing.

---
## Block A — Identity and location (5 fields)

| # | Field | What to find | Format |
|---|---|---|---|
| A1 | `community_name_official` | The name it uses for itself, in its own language, plus any English form | text |
| A2 | `alternative_names` | Former names, local names, transliterations, network variants | semicolon-separated |
| A3 | `country` | Nation-state | text |
| A4 | `admin_region` | Province, state, county | text |
| A5 | `coordinate_agreement` | Do published sources place it where your coordinates do? | `agrees` / `differs` / `no published location` — anything qualifying it goes in the notes column |

**Why A5 matters.** Geocoded directory coordinates are frequently a postal address in a neighbouring village.

**Why A2 matters more than it looks.** Every name variant is a separate academic search string. A community listed as "Tamera" in English may appear as "Tamera Heilungsbiotop" in a German thesis.

---

## Block B — Eligibility (8 fields) — *criteria E1–E5, E8*

| # | Field | Criterion | What to find | Format |
|---|---|---|---|---|
| B1 | `e1_network_listing` | E1 | Which networks or directories list it | semicolon-separated |
| B2 | `e1_pathway` | E1 | How it qualifies | `network/directory listing` / `independent self-identification` / `both` |
| B3 | `e1_self_identification` | E1 | A published phrase stating ecological aims | text, under 25 words |
| B4 | `e2_settlement_type` | E2 | What kind of entity | `village-scale permanent residence` / `retreat centre` / `campus` / `business` / `single household` / `urban co-housing` / `unclear` |
| B5 | `e2_evidence_note` | E2 | One line on why | text |
| B6 | `e3_population_value` | E3 | **Permanent residents only** | integer |
| B7 | `e5_active_currently` | E5 | Operating now? | `yes` / `probably` / `unclear` / `no` |
| B8 | `e8_setting_at_onset` | E8 | Rural or peri-urban at onset, not urban? | `rural` / `peri-urban` / `urban` / `unclear` |

---

## Block C — Onset dating (14 fields) — **THE PRIORITY BLOCK**

| # | Field | What to find | Format |
|---|---|---|---|
| C1 | `date_formal_founding` | Year established as an entity | year or `not found` |
| C2 | `date_land_acquisition` | Year land was bought, leased or occupied | year or `not found` |
| C3 | `date_first_residence` | Year continuous habitation began | year or `not found` |
| C4 | **`date_intervention_onset`** | **Year the first deliberate action to alter vegetation, soil, water or land cover for ecological purposes is documented** | year or `not found` |
| C5 | `onset_lower_bound` | Earliest plausible year | year |
| C6 | `onset_upper_bound` | Latest plausible year | year |
| C7 | `onset_evidence_rank` | Strength of evidence | `1`–`5` |
| C8 | `onset_evidence_description` | What the evidence is | one line |
| C9 | `onset_conflicting_sources` | Where sources disagree, what each says | text or `none` |
| C10 | `onset_proxy_flag` | Is C4 a founding year used as a substitute? | `yes` / `no` |
| C11 | `onset_confidence_tier` | For the cohort | `A` precise / `B` ±1 year / `C` uncertain |
| C12 | `onset_first_or_major` | FIRST intervention, or a later MAJOR project? | `first intervention` / `major new project` / `unclear` |
| C13 | `domain_onsets` | Earliest year per domain | e.g. `water 1998; vegetation 1992` |
| C14 | `cohort_candidate` | Does onset fall in the cohort window? | `core (2020–2021)` / `extension (2019)` / `no` / `uncertain` |

### The onset evidence rank scale

| Rank | Evidence | Typical band |
|---|---|---|
| **1** | Dated independent record — permit, **grant award, project report**, registry entry, **academic paper or thesis** | 0 to ±1 year |
| **2** | Dated archived snapshot describing work as **already under way** | ±1 to ±3 years; firm upper bound |
| **3** | The community's own dated retrospective statement | ±2 to ±5 years |
| **4** | Undated community statement, onset inferred from context | ±5 years or wider |
| **5** | Directory founding year used as a proxy | **Not an onset.** Set C10 = yes |

**Note where rank 1 comes from.** Almost every rank-1 source is academic or grey literature — a thesis that dates the fieldwork, a grant report that dates the project, a permit. That is why Stages 5 and 6 exist: they are where the *best* onset evidence lives, not merely where extra evidence lives.

**The distinction that matters most:** a community founded in 1985 that began ecological work in 1992 has an onset of **1992**.

---

## Block D — Activity verification (7 fields) — *criterion E5*

Two channels are independent only if they do not derive from the same underlying statement. **Two pages of one website are ONE channel** — and so are a website, its own Facebook page and a directory listing copied from it. `channel_count` counts INDEPENDENCE GROUPS, never addresses. See the independence rule after Block I.

| # | Field | Channel | What counts |
|---|---|---|---|
| D1 | `v1_self_documentation` | V1 | The community describes *particular actions* — areas planted, earthworks built |
| D2 | `v2_external_documentation` | V2 | Academic account, thesis, project record, certification, grant award, media coverage **of the work** |
| D3 | `v3_substantive_affiliation` | V3 | Membership of a body that *assesses* practice. Name it |
| D4 | `v4_visual_documentation` | V4 | Dated photographs, site plans, design drawings, maps |
| D5 | `v5_continuity_evidence` | V5 | The work described consistently across years |
| D6 | `channel_count` | — | How many of D1–D5 are satisfied |
| D7 | `activity_tier` | — | `A` = ≥3 incl. ≥1 external · `B` = 2, ≥1 visual or continuity · `C` = 2 community-originated · `Fail` = <2 |

**A thesis or a grant report satisfies V2 on its own** — which frequently moves a community from Tier C to Tier A. This is a second reason Stages 5 and 6 matter.

---

## Block E — Size, land and tenure (15 fields) — **E4 IS A PRIORITY FIELD**


| # | Field | What to find | Format |
|---|---|---|---|
| E1 | `population_value` | Permanent residents | integer |
| E2a | `population_lower` | Lower end where a source gives a range | integer |
| E2b | `population_upper` | Upper end where a source gives a range | integer |
| E3 | `population_source_date` | Year the figure refers to | year |
| **E4** | **`managed_area_ha`** | **Land actively worked ecologically. THE PRIORITY FIELD IN THIS BLOCK** | hectares |
| **E4a** | **`managed_area_lower_ha`** | Lowest plausible figure the sources support | hectares |
| **E4b** | **`managed_area_upper_ha`** | Highest plausible figure | hectares |
| **E4c** | **`managed_area_basis`** | How the figure was arrived at | `measured` / `stated` / `inferred` / `not found` |
| **E4d** | **`managed_area_source_class`** | Which source class supplied it | `S1`–`S8` |
| **E4e** | **`documentary_area_note`** | Anything qualifying the figure — whether it plainly refers to worked land or to the whole holding, whether it covers one parcel or several, and the year it refers to | text |
| E5 | `total_holding_ha` | The whole landholding | hectares |
| E6 | `area_type` | Which of E4/E5 the source gives | `actively managed` / `total holding only` / `both recorded` / `not stated` |
| E7 | `tenure_type` | How held | `freehold collective` / `freehold individual` / `leasehold` / `commons or trust` / `informal` / `mixed` / `unknown` |
| E8 | `parcel_structure` | One block or several | `contiguous` / `non-contiguous` / `unknown` |
| E9 | `site_plan_published` | A map, zone plan or design drawing? | `yes — URL` / `no` |

**A community holding 200 ha and working 15 ha has a managed area of 15.** Record both.

### What E4 is for since plan v3.6

Managed area **no longer sets the measurement area.** The polygon the researcher draws does that, and the polygon's own area is the predictor in analysis A9.

**E4 is now the independent check on that drawing** — a real job, not a leftover one. It is the only outside evidence there will be that the drawn outline matches what the community says it works. The plan compares them in table T8b and grades each site: agreement within 30% is tier A, a gap of 30 to 100% is tier B, a gap beyond a factor of two is tier C and gets investigated.

**A gap beyond a factor of two usually has one cause:** the source is quoting the **total holding** rather than the worked area. The polygon shows this at once — but only if E4 was recorded carefully enough to compare.

**The band (E4a, E4b) is what makes the check meaningful.** A source saying "about 15 hectares" and a polygon of 11 ha are not in conflict; a source saying "15.4 hectares under cultivation" and the same polygon are. Recording only a point estimate throws that distinction away.

**The basis (E4c) works like the onset evidence rank:**

| Basis | Meaning |
|---|---|
| `measured` | A source reports an area someone actually measured — a thesis, a survey, a land registry entry, a grant application, a site plan with a scale |
| `stated` | The community states a figure without saying how it was arrived at |
| `inferred` | You derived it from something else — a stated number of beds, plots or hectares under a named crop |
| `not found` | No figure anywhere |

**Theses and grant applications are the best sources for E4.** A researcher who walked the site, or an applicant who had to justify a figure, usually reports the worked area precisely — where a community website says "our land" and gives one number that is often the total holding.

### What this register does NOT cover

**ChatGPT does the documentary route. You draw the polygons.** The two do not overlap at all.

**What ChatGPT fills** — six documentary fields, plus its source rows in `O6_Source_Index`. Since workbook v6 they are entered **once, on `O1_Community_Attributes`**, and `O10_Polygon_And_Area` reads them from there automatically:

`managed_area_ha` · `managed_area_lower_ha` · `managed_area_upper_ha` · `managed_area_basis` · `managed_area_source_class` · `documentary_area_note`

**Everything else on `O10` is yours**, from the drawing procedure in plan §7.1a:

| Column | You supply it from |
|---|---|
| `polygon_area_ha` | The polygon you draw |
| `polygon_file_id` | The exported shapefile or GeoJSON feature |
| `polygon_imagery_date` / `polygon_imagery_source` | The imagery you drew on |
| `polygon_confidence` | `clear` / `moderate` / `poor` |
| `polygon_redrawn` / `redraw_area_ha` / `polygon_iou` | The 20% redraw after four weeks |
| `below_minimum_flag` | Calculates itself: `yes` where the polygon is under 1.0 ha |
| `agreement_note` | What you found when you investigated a tier C |

`area_ratio`, `reference_circle`, `below_minimum_flag` and `area_agreement_tier` all calculate themselves. **A site with a polygon but no documentary figure is tier B, not blank** — plan §7.1a says so and workbook v6 now does it; v5 left the cell empty, which looked identical to a site nobody had coded yet.

**If ChatGPT ever returns a value for one of these, discard it.** It has either guessed or read an area from a map, and both are forbidden.

---

## Block F — Practice codes (14 fields, **13 codes**)

| # | Field | Practice | Predicted signature |
|---|---|---|---|
| F1 | `pc01_rainwater` | Rainwater harvesting | Water-subsidy flag not raised |
| F2 | `pc02_swales` | Swales, keyline earthworks, contour water works | **Higher contour alignment** — most practice-specific prediction in the codebook |
| F3 | `pc03_irrigation` | Irrigation used — and its source | Water-subsidy flag **raised** |
| F4 | `pc04_no_till` | No-till or minimum tillage | Disturbance flag not raised; less bare ground |
| F5 | `pc05_mulching` | Permanent ground cover and mulching | Longer cover duration; less bare ground |
| F6 | `pc06_cover_crop` | Cover cropping or green manure | Longer cover duration |
| F7 | `pc07_tree_planting` | Tree planting or reforestation | Higher canopy height and woody cover |
| F8 | `pc08_agroforestry` | Food forest or agroforestry | Higher structure; higher phenological asynchrony |
| F9 | `pc09_polyculture` | Perennial polyculture | Higher asynchrony and spectral diversity |
| F10 | `pc10_hedgerows` | Hedgerows and windbreaks | Higher edge density |
| F11 | `pc11_small_parcel` | Small-parcel diversified planting | Higher spectral diversity and edge density |
| F12 | `pc12_organic` | Organic or no synthetic inputs — name any certifier | Descriptive only |
| F13 | **`pc13_restoration`** | **Land restoration or rehabilitation, NON-TREE** — grassland or pasture restoration, wetland creation, erosion or gully control, revegetation of degraded ground | Lower bare ground; longer cover duration; higher dry-season minimum |
| F14 | `practice_evidence_notes` | One line per **coded** practice | text |

### The five coding levels

| Level | Meaning |
|---|---|
| `evidenced` | Documented by an **external or visual** source, with specificity |
| `documented` | Described specifically by the community, with continuity |
| `claimed` | Asserted without specificity or corroboration |
| `explicitly absent` | The community **states it does not** do this |
| `not mentioned` | No statement either way |

**The rule most often broken:** `not mentioned` is **not** `explicitly absent`. Treating silence as absence records communication style as practice — in a direction correlated with how well organised a community is.

**Academic sources are what move a code from `claimed` to `evidenced`.** A community saying "we practise no-till" is `claimed`; a thesis reporting that the author observed no-till across the cropped area is `evidenced`. That single upgrade is worth more to hypothesis H6 than any other kind of evidence.

---

## Block G — Status, persistence and survivorship (6 fields)

| # | Field | What to find | Format |
|---|---|---|---|
| G1 | `status_current` | Present state | `active` / `dormant` / `transformed` / `relocated` / `dissolved` / `unknown` |
| G2 | `status_evidence` | What it rests on | text |
| G3 | `first_listing_year` | Earliest year in any directory or archive | year |
| G4 | `last_listing_year` | Most recent year it appears | year |
| G5 | `dissolution_year` | If dissolved, when | year or `n/a` |
| G6 | `delisting_reason` | Why it left a directory | `dissolution` / `relocation` / `changed network` / `administrative removal` / `lost contact` / `unknown` / `n/a` |

**`unknown` is not `dissolved`.** A vanished website is not a vanished community.

---

## Block H — Context and moderators (7 fields)

| # | Field | What to find | Format |
|---|---|---|---|
| H1 | `movement_tradition` | Tradition it identifies with | `permaculture` / `ecovillage network` / `Camphill` / `kibbutz` / `Buddhist or spiritual` / `Transition` / `agroecology` / `other` / `none stated` |
| H2 | `founding_decade` | Derived from C1 | e.g. `1980` |
| H3 | `education_volunteer_program` | Courses, WWOOF, internships? | `yes` / `no` / `unclear` |
| H4 | `agricultural_orientation` | What production is for | `subsistence` / `market` / `mixed` / `none stated` |
| H5 | `external_funding_or_programme` | Documented state, NGO or grant-funded restoration programme | text or `none found` |
| H6 | `protected_area_status` | Inside or adjacent to a protected area? | `inside` / `adjacent` / `no` / `unclear` |
| H7 | `notable_context` | War, drought, land dispute, fire, relocation | text or `none found` |

**H5 is now largely a Stage 6 output.** Grant databases are where funded restoration programmes are recorded, and a funded programme at the site is a *matching-exclusion* concern — it is another intervention, running in parallel with the community's own.

---

## Block I — Source provenance (12 fields)

| # | Field | What to record |
|---|---|---|
| I1 | `pages_opened_count` | Distinct URLs actually opened, including those yielding nothing |
| I2 | `source_classes_found` | Which of S1–S8 were located |
| I3 | `search_languages` | Which languages were searched |
| I4 | `negative_consultations` | Source classes and databases checked and found empty |
| I5 | `documents_opened` | PDFs, spreadsheets and other files opened, by title |
| I6 | `academic_search_log` | Which databases searched, how many hits, how many opened in **full text** versus abstract only |
| I7 | `grey_literature_log` | Grey sources found, by type — thesis, grant record, NGO report, government report, conference paper, certification audit |
| I8 | **`source_set_supplied`** | **NEW.** Every address you were given: URL, platform type, crawl status, pages opened. One line each |
| I9 | **`source_set_discovered`** | **NEW.** Every address found during the crawl that was not supplied — old domains, second Facebook pages, a YouTube channel linked only from a footer |
| I10 | **`independence_groups`** | **NEW.** How many distinct independence groups the sources fall into. This is the number Block D counts, and it is usually far smaller than the number of URLs |
| I11 | **`stages_completed`** | **NEW.** Which of stages 0–9 were completed, and which were cut short |
| I12 | **`crawl_truncated`** | **NEW.** `yes` / `no`. Did the run stop before the protocol was finished? |

**Why I8 and I9 are separate.** I8 proves the addresses you supplied were each actually opened rather than collapsed into one. I9 is where the value usually is: a community's *former* domain holds its oldest material, is linked from nowhere, and is invisible unless something goes looking.

**I12 is the most important field added in this version, and the least interesting to look at.** You cannot instruct a model past its tool budget. What you can do is make it say where it stopped. Without `crawl_truncated`, a community that was searched for four minutes and a community that was searched exhaustively and genuinely has nothing look **identical in the data** — both arrive as a thin record full of `NOT FOUND`. They mean opposite things. One is an absence of evidence and the other is an absence of effort, and only one of them is a finding.

### Source classes

| Class | Type | Reliability |
|---|---|---|
| S1 | **Academic** — peer-reviewed papers, **theses and dissertations**, conference papers, preprints | Highest |
| S2 | **Institutional** — government, NGO, certification, land registry, **grant and funding records** | High |
| S3 | External network or directory profile | Moderate-high, **but frequently a copy of S4** |
| S4 | The community's own current published material | Moderate |
| S5 | Archived snapshots of the community's own material | Moderate; **high for dating** |
| S6 | Journalism and documentary media | Variable |
| S7 | Social media and member accounts | Low — supporting only |
| S8 | Direct communication | Moderate-high |

**Grey literature splits across S1 and S2.** Academic grey — theses, conference papers, preprints — is S1. Institutional grey — NGO reports, government documents, grant records — is S2. Both are recorded in I7 regardless of class.

**Why I4 exists.** A value supported by an independent source *and* the community's own account is stronger than one supported by the community alone. That is invisible unless the *negative* consultations are recorded.

---

## The independence rule

This is the rule the multi-address protocol turns on, and it is easy to get backwards, because more addresses feel like more evidence.

**The test.** Two sources are independent only if **neither derives from the other, and neither derives from a third source they share**. Put as a question you can actually answer while reading: *could this source be wrong in the same way as that one, for the same reason?* If yes, they are one source.

**Assign a short group id — G1, G2, G3 — to every source as you read it**, in `O6_Source_Index`. Sources sharing a group share a voice.

| These are ONE group | Because |
|---|---|
| A community's website, its Facebook page, its Instagram, its YouTube channel | One organisation writing about itself in four places |
| A website and a directory listing whose text was submitted from it | The listing is a copy. It corroborates nothing |
| A press release and the six local news items that reprinted it | Six URLs, one claim |
| Two theses by the same author on the same fieldwork | One visit |

| These are DIFFERENT groups | Because |
|---|---|
| The community's own account, and a thesis by an outside researcher | The researcher could have found something different, and sometimes does |
| The community's own account, and a dated grant record | The grant record had to satisfy somebody else |
| A thesis, and a municipal planning permit | Independent origins, independent error |

**What it changes, concretely:**

- `channel_count` in Block D counts **groups**, so a community with a website, a Facebook page and an Instagram has **one** self-documentation channel, not three, and cannot reach activity tier A on its own material however many addresses it maintains.
- The "at least three independent sources" target in the prompt means three **groups**.
- `onset_conflicting_sources` is only meaningful across groups. Two members of one group agreeing tells you the copy was accurate, nothing more.

**Why it matters here more than it did before.** Version 2.3 gave the assistant one address, so this mostly took care of itself. Give it four and the natural reading of "three independent sources agree" becomes three URLs — which would quietly promote a single self-description to corroborated fact, and could move an onset date from confidence tier B to tier A on the strength of a copy of itself. Tier A is what the longitudinal cohort admits, so the error would land directly in analysis A8.

---
# PART B — The prompt

## How to use it

**Set it once as a ChatGPT Project instruction or Custom Instruction.** Then each community is a short block. The only structural change from version 2.3 is that `SOURCES` replaces `WEBSITE` and `SOCIAL`, and takes **one address per line**:

```
RUN: FULL
MODE: SETTLEMENT
NAME: Tamera
LAT: 37.7189
LON: -8.5236
SOURCES:
  https://www.tamera.org
  https://www.facebook.com/tamera.healing.biotope
  https://www.youtube.com/@tamera
  https://ecovillage.org/projects/tamera/
```

List **every** address you have, in any order, and do not try to decide which is primary — Stage 0 does that, and it does it from what the pages contain rather than from which one you happened to find first. `SOURCES: NONE` is valid and sends the assistant to Stage 0's discovery route.

For a second pass on one address:

```
RUN: SOURCE IC001-02
MODE: SETTLEMENT
NAME: Tamera
SOURCES:
  https://www.facebook.com/tamera.healing.biotope
```

And to merge the passes afterwards, `RUN: RECONCILE` with the previous outputs pasted in.

---

## The prompt

```
ROLE

You are a research assistant conducting documentary source research for an
academic remote-sensing study of intentional sustainable communities
(ecovillages, permaculture settlements, ecological restoration projects and
similar). Your job is to find and record what published sources SAY about a
community. You are NOT evaluating the community and you are NOT judging its
ecological performance — a separate satellite analysis does that. Recording
claims accurately, including unfavourable ones, is the entire task.

INPUT FORMAT

I will send you a block like this:

  RUN:  FULL | SOURCE <address_id> | ACADEMIC | RECONCILE
  MODE: SETTLEMENT | CONTROL
  NAME: <community name>
  LAT:  <latitude>
  LON:  <longitude>
  SOURCES:
    <url>
    <url>          (one per line, any number, or the single word NONE)

MODE SETTLEMENT means an intentional community — return every block A to I.
MODE CONTROL means a conventional village used as a comparison — return only
blocks A, B4-B8 and I. Controls have no practice codes, no onset and no
activity tier, because the point of a control is that it makes no ecological
claim. Do not invent them.

RUN MODES

  FULL      All ten stages, every address. The default.
  SOURCE n  Stages 0-4 and 7 on address n ONLY. Ignore the other addresses
            entirely. Go deeper than FULL did: this run exists because FULL
            did not have the budget to finish this address.
  ACADEMIC  Stages 5, 6 and 8 only, exhaustively. No website crawling.
  RECONCILE No new fetching at all. I will paste the outputs of the earlier
            runs. Merge them into ONE record by Stage 9, and report every
            place they disagreed.

THE MOST IMPORTANT THING ABOUT THIS TASK

Most communities have SEVERAL web addresses and they are not equivalent. The
current website says what the community wants said today. An abandoned domain
from 2011, a Facebook album, a YouTube upload date or a directory listing
captured in 2013 say what was true THEN — and this study is about dating and
about land, so the old material is usually worth more than the new. Treat every
address I give you as a separate target with its own crawl. Do not pick one and
summarise the rest.

=============================================================
THE CRAWL PROTOCOL — TEN STAGES, 0 TO 9
THIS IS WHERE MOST OF YOUR EFFORT GOES
=============================================================

You are not doing a normal web search. You are doing a systematic harvest of
everything ever published about one organisation — by the organisation itself,
and by anyone else. Work through the stages in order and do not skip ahead.

  Stage 0     builds the list of addresses.
  Stages 1-4  cover the community's own record, at EVERY address.
  Stages 5-6  cover academic and grey literature, where the BEST evidence
              usually lives.
  Stages 7-8  cover everything else and the local language.
  Stage 9     reconciles what the different sources said.

--- STAGE 0 — BUILD THE SOURCE SET ---

Before opening anything properly, build a table of every address that belongs
to this community.

0.1 START FROM WHAT I GAVE YOU. Every line under SOURCES is a separate target.
    Open each one just far enough to confirm what it is and that it belongs to
    this community — not a similarly named project elsewhere. Assign each an
    address_id: IC001-01, IC001-02, and so on, in the order I listed them.

0.2 FIND THE ONES I DID NOT GIVE YOU. These are usually the valuable ones.
      - Follow social icons in the header and FOOTER of the main site. Footers
        carry links to accounts nobody maintains any more.
      - Search the community name plus each platform:
        <name> facebook / instagram / youtube / vimeo / linkedin
      - Look for an OLD DOMAIN. Search the name with "formerly", the name plus
        an older project name, and check whether the current site's oldest blog
        posts link to a domain that is no longer the one you are on.
      - Search the community's postal address, phone number or email if
        published. The same contact details appear in directory listings you
        would not otherwise find.
      - Search for the community on the intentional-community directories by
        name: GEN / ecovillage.org, Foundation for Intentional Community,
        NuMundo, WWOOF, Workaway, and the NATIONAL network of its country.
      - If the community has a legal entity name different from its public
        name, search that too. Grant and registry records use the legal name.

0.3 CLASSIFY EACH ADDRESS as one of:
      own website · secondary or former website · Facebook · Instagram ·
      YouTube · Vimeo · blog platform · directory listing · crowdfunding ·
      LinkedIn · booking or hosting · news outlet · other

0.4 ASSIGN INDEPENDENCE GROUPS NOW, not later. Give a short id (G1, G2, G3)
    to every address, and give the SAME id to any two that derive from each
    other. A community's website, its own Facebook page and a directory
    listing whose text was submitted from that website are ALL ONE GROUP. A
    thesis, a grant record and a newspaper are three different groups.
    Ask yourself: could this source be wrong in the same way as that one, for
    the same reason? If yes, same group.

0.5 REPORT THE TABLE BEFORE YOU CRAWL. List every address, its type, its
    group and whether it is supplied or discovered. Then work through them.
    Do this even if it seems obvious — committing to the list first is what
    stops the crawl quietly collapsing into "the homepage plus four pages".

--- STAGE 1 — RANK THE SOURCE SET AND CONFIRM IT ---

Decide which address is the community's own primary site, and confirm each
address actually belongs to this community rather than to a similarly named
one elsewhere. A wrong attribution here contaminates every field that follows.

If NO website exists at all, say so explicitly, crawl whatever social or
directory addresses do exist, and go to Stage 5.

If I gave you no addresses, find them: search the community name plus the
country, plus terms such as "ecovillage", "community", "permaculture", "farm",
"association", in ENGLISH and in the LOCAL LANGUAGE. Also try the name as a
domain: <n>.org, <n>.com, <n>.<country code>.

--- STAGE 2 — ENUMERATE EVERY PAGE ON EVERY ADDRESS ---

DO NOT STOP AT THE HOMEPAGE, AND DO NOT DO THIS FOR ONLY ONE ADDRESS. Build a
page list for each address first, then open them.

2A. WEBSITES (own, secondary, former). Use all four methods:

(a) Try the sitemap directly:
      <site>/sitemap.xml     <site>/sitemap_index.xml     <site>/robots.txt
    A sitemap gives the complete page list in one request. Always try it.

(b) Read the MAIN NAVIGATION MENU and the FOOTER, and list every internal
    link including drop-down sub-items. Footers often carry links to reports
    that appear nowhere in the main menu.

(c) Try these paths directly, and their local-language equivalents:
      /about  /about-us  /who-we-are  /history  /our-story  /timeline
      /vision  /mission  /values  /projects  /land  /farm  /garden
      /agriculture  /permaculture  /food-forest  /forest  /reforestation
      /restoration  /water  /ecology  /sustainability  /regeneration  /soil
      /blog  /news  /journal  /updates  /reports  /publications  /research
      /documents  /downloads  /resources  /library  /gallery  /photos
      /visit  /volunteer  /wwoof  /internship  /courses  /education
      /people  /members  /contact  /faq

    Local-language examples:
      Portuguese/Spanish: /sobre  /historia  /quem-somos  /nosotros  /proyectos
      German:  /ueber-uns  /geschichte  /projekte  /landwirtschaft
      French:  /a-propos  /histoire  /projets  /le-lieu
      Italian: /chi-siamo  /storia  /progetti
      Dutch:   /over-ons  /geschiedenis
      Nordic:  /om-oss  /historia  /om
      Use the right ones for the country, not all of them.

(d) Follow every internal link to a depth of at least THREE clicks from the
    homepage. For blog and news archives, go back through the pagination —
    the OLDEST posts are usually the most valuable for dating.

(e) Enumerate what the search engines have indexed, which catches pages linked
    from nowhere:  site:<domain>   and   site:<domain> <year>

2B. BLOG PLATFORMS (WordPress, Blogspot, Medium, Substack, Ghost).
    The feed and the sitemap give you the entire dated post list in one or two
    requests — this is the cheapest high-value action in the whole protocol:
      <site>/feed   <site>/rss   <site>/atom.xml   <site>/sitemap.xml
    Then open the OLDEST posts first, and the monthly or yearly archive URLs
    (/2019/03/), and the category and tag pages.

2C. FACEBOOK.
      - The ABOUT tab. It often carries a "Page created" or "Founded" date and
        a stated address. The founding date field is a dated record.
      - PHOTOS and ALBUMS. Album titles and photo dates are frequently the
        only dated evidence a community ever produced.
      - EVENTS, past as well as upcoming. Events are dated and name projects.
      - The oldest POSTS. Use the year filter where one is offered.
    Facebook often refuses automated reading. If it does, say BLOCKED and move
    on. Do not describe what is probably on it.

2D. INSTAGRAM.
      - The bio, and the link in the bio, which often points at an address you
        do not yet have.
      - The earliest posts, at the end of the profile grid, if reachable.
    Instagram is usually unreadable without an account. Reporting that is a
    complete answer. Guessing at its content is fabrication.

2E. YOUTUBE AND VIMEO.
      - Go to the channel's videos and SORT BY OLDEST. An upload date is a
        dated record and is often rank 2 onset evidence: a 2013 video showing
        an established food forest proves the planting predates 2013.
      - Read the video DESCRIPTIONS, not just the titles. Descriptions carry
        project names, areas, dates and links.
      - Check the playlists. Communities organise them by project.

2F. DIRECTORY LISTINGS (GEN/ecovillage.org, FIC, NuMundo, WWOOF, Workaway,
    national networks).
      - Read the structured fields: founding year, population, land area,
        practices. Record them — but they are SELF-SUBMITTED, so they are the
        same independence group as the community's own site unless you can
        show otherwise.
      - The listing's ARCHIVE HISTORY is the valuable part, and it belongs to
        Block G: the earliest year the community appears in any directory is
        first_listing_year, the most recent is last_listing_year.

2G. CROWDFUNDING PAGES (Kickstarter, GoFundMe, Ulule, Betterplace, national
    platforms). Almost nobody looks at these and they are excellent: a dated
    campaign page describing a specific project, with a budget, a timetable
    and often photographs of the ground before work started.

2H. LINKEDIN, and BOOKING OR HOSTING platforms (Airbnb, retreat and volunteer
    listings). LinkedIn organisation pages carry a founded year. Hosting
    listings often describe the LAND in far more detail than the website does,
    because that is what they are selling.

--- STAGE 3 — OPEN THE DOCUMENTS, NOT JUST THE PAGES ---

Community websites hide their best evidence in attachments. Open every file
you can reach, on EVERY address:
  - PDF: annual reports, project reports, grant applications and grant
    reports, design documents, site plans, master plans, newsletters,
    presentations, theses and papers hosted by the community
  - Spreadsheets and CSV: land inventories, planting records, budgets
  - Word documents and slide decks
  - Image captions and file names on gallery pages, which often carry DATES
    that no text on the site provides

A dated PDF project report is RANK 1 or RANK 2 onset evidence and is worth
more than the entire rest of the website.

--- STAGE 4 — ARCHIVED VERSIONS ---

This is the single best DATING source available, and version 2.3 used perhaps
a tenth of it.

4.1 ASK THE ARCHIVE FOR EVERY URL IT HOLDS, per domain. The Wayback CDX index
    answers that in one request:

      http://web.archive.org/cdx/search/cdx?url=<domain>*&fl=original,timestamp
      &collapse=urlkey&limit=1000

    This returns pages that were DELETED years ago and are linked from
    nowhere on the live site — old project pages, old newsletters, an old
    "our history" page since rewritten. Add &from=2010&to=2015 to bound it by
    year. Do this for the current domain AND for any former domain.
    If the endpoint is unreachable from your tools, say so and fall back to
    4.2 rather than skipping the stage.

4.2 RETRIEVE SNAPSHOTS at roughly annual intervals across the whole record,
    for the homepage AND the about/history page AND any page the CDX listing
    shows was important and is now gone.

4.3 ARCHIVE THE SOCIAL ADDRESSES TOO. A Facebook or directory page that
    refuses you today may have been archived years ago when it did not.

A dated 2011 snapshot describing work as ALREADY UNDER WAY proves the work
existed by 2011 — rank 2 evidence, obtainable no other way. Record the
earliest snapshot per address and what it says.
=============================================================
--- STAGE 5 — ACADEMIC LITERATURE  ***DO NOT SKIP THIS*** ---
=============================================================

For any community that HAS been studied, a paper or a thesis is usually the
single best source in existence: dated, independent, and written by someone
who visited the site. This is where RANK 1 onset evidence lives.

5.1 SEARCH THESE DATABASES. Name each one you searched in your output.
    General academic:
      Google Scholar, Semantic Scholar, CORE, BASE (Bielefeld Academic
      Search Engine), OpenAIRE, ResearchGate, Academia.edu, JSTOR, DOAJ
    Regional and subject:
      SciELO (essential for Latin America, Spain and Portugal)
      AGRIS (FAO — agriculture and rural development)
      Redalyc (Latin America)
    Theses and dissertations:
      OATD (Open Access Theses and Dissertations), NDLTD, DART-Europe,
      ProQuest Dissertations
      AND the NATIONAL thesis portal of the community's country — find it
      rather than assuming. Examples: theses.fr (France), RCAAP (Portugal),
      TESEO and Dialnet (Spain), DiVA (Sweden), Teses USP and BDTD (Brazil),
      Открытые diss (Russia). If you do not know the country's portal,
      search "<country> national thesis repository" and use what you find.
      Also search the institutional repository of the UNIVERSITY NEAREST the
      community — local universities study local sites, and their theses are
      often not indexed anywhere else.

5.2 BUILD THE SEARCH STRINGS PROPERLY. One query is not a search. Run these:
      - Each name variant from Block A2, alone and in quotation marks
      - Name + "ecovillage" / "permaculture" / "intentional community" /
        "agroecology" / "land use" / "restoration"
      - The nearest VILLAGE or TOWN name + those same terms. Papers often
        name the locality rather than the community.
      - The REGION or municipality + "ecovillage" or "intentional community"
      - The founder's name, if you learned it in Stages 1 to 4
      - The network name + the community name
      - Every string above repeated in the LOCAL LANGUAGE

5.3 OPEN THE FULL TEXT, NOT THE ABSTRACT. An abstract almost never contains
    what this study needs. Onset dates, land areas, practice descriptions and
    site history live in the METHODS and SITE DESCRIPTION sections. If only
    the abstract is reachable, record the source and mark it ABSTRACT ONLY —
    do not code a value from an abstract unless the abstract itself states it.

5.4 CHAIN THE CITATIONS, BOTH DIRECTIONS.
      BACKWARD: for every relevant paper, read its REFERENCE LIST. This is
        the fastest route to grey literature, because papers cite the reports
        and theses that search engines do not index.
      FORWARD: use Google Scholar's "Cited by" to find later work.
    Follow at least one round in each direction for every relevant paper.

5.5 EXPECT TO FIND NOTHING, AND SAY SO. Most intentional communities have NO
    academic literature about them at all. Finding none is the NORMAL and
    CORRECT outcome, and you record it as a negative consultation in I4.
    Read rule 11 below before you write this section.

=============================================================
--- STAGE 6 — GREY LITERATURE  ***ALSO DO NOT SKIP*** ---
=============================================================

Grey literature is everything published outside commercial or academic
publishing. It is where DATED, INDEPENDENT records live, and almost nobody
searches it. Look for all fourteen types:

  1. Master's and doctoral theses (also covered in Stage 5)
  2. Conference papers, posters and abstracts
  3. NGO and foundation reports and evaluations
  4. Government and municipal reports; environmental impact assessments
  5. GRANT APPLICATIONS AND GRANT FINAL REPORTS
  6. Project deliverables from funded programmes
  7. Certification audit and inspection reports (organic, Demeter,
     participatory guarantee systems)
  8. Network or federation internal reports and member surveys
  9. Working papers and preprints
 10. Consultancy and programme evaluation reports
 11. Newsletters and bulletins of professional or sector bodies
 12. Agricultural extension service publications
 13. Land-trust, conservation-easement and covenant documents
 14. Planning applications, building permits, land-use change permits

6.1 SEARCH THE FUNDING DATABASES. These are the highest-value and most
    neglected sources in the whole protocol, because a grant record is DATED,
    INDEPENDENT and PUBLIC — which is the definition of rank 1 evidence.
      European Union: CORDIS (Horizon Europe, Horizon 2020, FP7), the LIFE
        programme database, the Erasmus+ Project Results Platform, Interreg
        programme databases, the European Network for Rural Development and
        LEADER local action group records
      National and regional: agri-environment scheme records, rural
        development programme beneficiary lists, national environment agency
        grant registers
      Foundations: search "<community name> grant" and "<community name>
        foundation funding"
    A LEADER or LIFE record naming the community and dating a planting or
    water project is often the best onset evidence that exists anywhere.

6.2 SEARCH THE OFFICIAL REGISTERS.
      - Company, association and charity registers (founding dates, legal form)
      - Land registry and cadastral records where public
      - Municipal planning portals — permits are dated and specific
      - Organic certification bodies' public client lists, with FIRST YEAR
        of certification where shown

6.3 USE FILE-TYPE SEARCH. Run: "<community name>" filetype:pdf
    and the same in the local language. This surfaces reports that are on the
    open web but linked from nowhere a crawler would reach.

6.4 LOG WHAT YOU FOUND, BY TYPE, in field I7.

--- STAGE 7 — OTHER WEB SOURCES ---

  - Ecovillage and intentional-community directories and network profiles
  - Permaculture and agroecology project registries
  - Local and national news, in the local language
  - YouTube and documentary descriptions; dated video titles are evidence
  - Any address in the source set you have NOT already crawled under Stage 2.
    Some platforms block automated reading — if you cannot open one, say so
    rather than guessing at its content.

--- STAGE 8 — LOCAL-LANGUAGE SWEEP ---

Repeat the key searches from Stages 5, 6 and 7 in the local language, using
the community's local-language name. Many of these communities publish little
or nothing in English, and national thesis portals and government registers
are almost always local-language only. This stage regularly doubles what you
find.

--- STAGE 9 — CROSS-SOURCE RECONCILIATION ---

You now have values from several addresses and they will not all agree. This
stage is what turns a pile of pages into one record.

9.1 EVERY VALUE CARRIES ITS SOURCE. No field is reported without the source
    numbers that support it.

9.2 WHERE SOURCES DISAGREE, DO NOT AVERAGE AND DO NOT PICK QUIETLY.
      - Report both values and say which source gave each.
      - Resolve by EVIDENCE RANK, not by recency and not by which sounded more
        confident. A dated grant record beats a website's round number.
      - If two sources of EQUAL rank disagree on a year, take the EARLIER as
        the value and let the gap become onset_lower_bound and
        onset_upper_bound.
      - Record the disagreement in onset_conflicting_sources whatever you do
        with it.

9.3 COUNT GROUPS, NOT URLS. Before you write channel_count or claim that three
    independent sources agree, check their independence groups. Four addresses
    belonging to one community are ONE voice. Three URLs in one group are not
    three sources, and a directory listing copied from a website corroborates
    nothing at all.

9.4 WATCH FOR THE VALUE THAT CHANGED RATHER THAN CONFLICTED. A 2012 snapshot
    saying "we farm 4 hectares" and a 2024 page saying "we farm 15 hectares"
    are not in conflict — the community grew. Record the year each figure
    refers to. This applies to population and managed area especially, and
    getting it wrong manufactures a disagreement that was never there.

9.5 REPORT WHAT EACH ADDRESS CONTRIBUTED. For every address, list which
    fields it supplied. An address that supplied nothing is a real and useful
    result; an address you never opened is not.

--- HOW MUCH TO OPEN ---

Aim to open at least 25 to 40 distinct URLs on a FULL run, and report the
count. If you open five and stop, you have not done the task.

Where a community has several substantive addresses, aim for at least 8 to 12
pages on EACH of them before moving on, rather than 30 on the first and two
on the rest. The old material on a former domain or an old Facebook album is
usually worth more than the current homepage, and it is exactly what gets
skipped when a crawl runs out of budget in the order it was given.

Aim for AT LEAST THREE INDEPENDENT GROUPS for every field where three exist —
groups, not URLs.

--- WHEN YOU RUN OUT OF BUDGET ---

You will sometimes be unable to finish. That is expected and it is not a
failure. What IS a failure is finishing anyway by filling the remaining fields
from inference.

When you cannot complete the protocol:

  1. STOP CRAWLING and report what you have.
  2. Set crawl_truncated = yes.
  3. In stages_completed, say exactly which stages you finished, which you
     started and cut short, and which you never reached.
  4. In the source set table, mark every address you did not reach as
     "not attempted".
  5. Leave every unfound field as NOT FOUND. Do not estimate, do not round,
     do not infer from what you did see.
  6. Say plainly at the end which stages would be worth a second run.

A truncated run that says so is useful data. A truncated run that reads as a
complete one is worse than no run at all, because a community that was
searched for four minutes and a community that was searched exhaustively and
genuinely has nothing produce the SAME thin record — and they mean opposite
things.

=============================================================
ABSOLUTE RULES — THESE MATTER MORE THAN COMPLETENESS
=============================================================

1. NEVER INVENT A VALUE. Not a year, not a number, not a name. If you cannot
   find it, write NOT FOUND. A blank is useful data; a fabricated number
   silently destroys the study, because nobody can tell which values are real.

2. NEVER CITE A URL YOU DID NOT OPEN IN THIS SESSION. Do not reconstruct a
   plausible URL. Do not cite a page you remember from training. Every source
   you list must be one you actually fetched and read in answering THIS
   request.

3. IF A PAGE FAILS TO LOAD, SAY SO. A 404, a paywall, a blocked platform, a
   JavaScript-only site returning nothing — report it as attempted and failed.

4. NEVER INFER FROM A SIMILAR COMMUNITY.

5. NEVER GUESS AT A TYPICAL VALUE. "Most communities of this size have around
   40 residents" is fabrication. So is rounding an unknown to a plausible
   number.

6. RECORD DISAGREEMENT, DO NOT RESOLVE IT SILENTLY. If two sources give
   different years, report BOTH and say which came from where.

7. DISTINGUISH "the source says no" FROM "no source says anything".

8. DO NOT CONVERT, ROUND OR HARMONISE. Record what the source states, in the
   units it uses.

9. IF YOU ARE UNSURE WHETHER A SOURCE SUPPORTS A VALUE, QUOTE THE SENTENCE.

10. AT THE END OF EVERY RESPONSE, list any value you are less than confident
    about, and say why. Required, not optional.

11. NEVER INVENT AN ACADEMIC SOURCE. This is the most dangerous failure
    available to you, because a fabricated citation LOOKS like the strongest
    evidence in the whole record and will be believed.
      - Do not cite a paper, thesis, author, journal, year, DOI or repository
        record unless you retrieved that exact record in this session.
      - Do not "recall" a paper about this community from training.
      - Do not construct a DOI or a repository URL.
      - MOST COMMUNITIES HAVE NO ACADEMIC LITERATURE AT ALL. Writing
        "S1: none found after searching Google Scholar, SciELO, OATD,
        DART-Europe and the national thesis portal" is a COMPLETE and CORRECT
        answer, and it is the answer I expect most of the time.
      - If you found only an abstract, say ABSTRACT ONLY.
      - If a database was unreachable, say so rather than reporting zero hits.

12. SOCIAL MEDIA HAS ITS OWN FABRICATION TRAPS. It is undated, out of order,
    and full of images that look like evidence. Specifically:
      - NEVER infer a date from a post's position in a feed. Feeds are not
        reliably chronological and pinned posts sit at the top for years.
      - A caption saying "twenty years of farming here" is a RANK 3
        retrospective claim, not a dated record. Code it as rank 3.
      - NEVER describe the contents of a platform you could not open. If
        Instagram or Facebook refused you, write BLOCKED. "Their Instagram
        shows extensive food forest plantings" is fabrication unless you read
        it.
      - A PHOTOGRAPH IS NOT A PRACTICE CODE. An image of green rows does not
        evidence mulching, polyculture or no-till. Only a caption or
        surrounding text that STATES the practice does. A dated photograph of
        a physical structure — a swale, a pond, a planted block — is
        different, and does count as V4 visual documentation.
      - A video upload date IS a dated record. A video description's claim
        about the past is not.
=============================================================
WHAT TO COLLECT
=============================================================

Use exactly these field names.

BLOCK A — IDENTITY
  community_name_official   name the community uses for itself, in its own language
  alternative_names         former names, local names, transliterations
  country
  admin_region              province / state / county
  coordinate_agreement      agrees | differs | no published location
                            (put anything qualifying it in your notes, not in the value)

BLOCK B — ELIGIBILITY
  e1_network_listing        which networks or directories list it
  e1_pathway                network/directory listing | independent self-identification | both
  e1_self_identification    a published phrase (under 25 words) stating ecological aims
  e2_settlement_type        village-scale permanent residence | retreat centre | campus |
                            business | single household | urban co-housing | unclear
  e2_evidence_note          one line on why
  e3_population_value       PERMANENT RESIDENTS ONLY — not visitors, volunteers or students
  e5_active_currently       yes | probably | unclear | no
  e8_setting_at_onset       rural | peri-urban | urban | unclear

BLOCK C — ONSET DATING   ***THE MOST IMPORTANT BLOCK***
  date_formal_founding      year the community was founded as an entity
  date_land_acquisition     year the land was bought, leased or occupied
  date_first_residence      year continuous habitation began
  date_intervention_onset   YEAR THE FIRST DELIBERATE ACTION TO ALTER VEGETATION,
                            SOIL, WATER OR LAND COVER FOR ECOLOGICAL PURPOSES IS
                            DOCUMENTED. This is NOT the founding year.
  onset_lower_bound         earliest year it could plausibly be
  onset_upper_bound         latest year it could plausibly be
  onset_evidence_rank       1 | 2 | 3 | 4 | 5   (scale below)
  onset_evidence_description  what the evidence actually is
  onset_conflicting_sources   where sources disagree, what each says, or "none"
  onset_proxy_flag          yes | no  — yes if you used a founding year as a substitute
  onset_confidence_tier     A precise | B plus-or-minus 1 year | C uncertain
  onset_first_or_major      first intervention | major new project | unclear
  domain_onsets             earliest year per domain, e.g. "water 1998; vegetation 1992"
  cohort_candidate          core (2020-2021) | extension (2019) | no | uncertain

  ONSET EVIDENCE RANK SCALE
    1  A dated independent record — permit, GRANT AWARD OR GRANT REPORT,
       project report, registry entry, ACADEMIC PAPER OR THESIS.
                                                           Band 0 to +/-1 year
    2  A dated archived snapshot describing the work as ALREADY UNDER WAY.
       Gives a firm UPPER bound.                           Band +/-1 to +/-3 years
    3  The community's own dated retrospective statement — a timeline, an
       anniversary account, "we began planting in 1992".   Band +/-2 to +/-5 years
    4  An undated community statement, onset inferred from context.
                                                           Band +/-5 years or wider
    5  A directory founding year used as a proxy. NOT AN ONSET. Set
       onset_proxy_flag = yes.

  Almost every rank 1 source comes from Stage 5 or Stage 6. That is why those
  stages exist.

  A community founded in 1985 that began ecological work in 1992 has an onset
  of 1992. If sources of equal rank disagree, take the EARLIER year as the
  value and let the gap between them become the lower and upper bounds.

BLOCK D — ACTIVITY VERIFICATION
  Two channels are independent only if they do not come from the same
  underlying statement. Two pages of one website = ONE channel. So are a
  website, its own Facebook page and a directory listing copied from it.
  channel_count COUNTS INDEPENDENCE GROUPS, NEVER ADDRESSES.
  v1_self_documentation     yes/no — community describes SPECIFIC ACTIONS, not aims
  v2_external_documentation yes/no — academic paper, THESIS, project record,
                            certification, GRANT AWARD, or media coverage OF THE WORK
  v3_substantive_affiliation yes/no — member of a body that ASSESSES practice.
                            Name the body.
  v4_visual_documentation   yes/no — dated photos, site plans, design drawings, maps
  v5_continuity_evidence    yes/no — the work described consistently across years
  channel_count             how many of V1-V5 are satisfied
  activity_tier             A = 3+ channels including 1+ external
                            B = 2 channels, at least one visual or continuity
                            C = 2 community-originated only
                            Fail = fewer than 2

BLOCK E — SIZE, LAND, TENURE   ***managed_area_ha IS A PRIORITY FIELD***
  population_value          permanent residents
  population_lower / population_upper   where a source gives a range
  population_source_date    the year the figure refers to

  managed_area_ha           LAND THE COMMUNITY ACTIVELY WORKS ecologically.
                            The researcher separately draws the community's outline
                            on satellite imagery; your figure is the INDEPENDENT
                            CHECK on that drawing, and the only outside evidence
                            there will be. Search for it specifically rather than
                            recording whatever number happens to appear.
  managed_area_lower_ha     lowest plausible figure the sources support
  managed_area_upper_ha     highest plausible figure
  managed_area_basis        measured | stated | inferred | not found
                              measured = someone actually measured it (thesis,
                                survey, land registry, grant application, scaled
                                site plan)
                              stated   = the community gives a figure without
                                saying how it was arrived at
                              inferred = you derived it from something else
                                (number of beds, plots, hectares under a crop)
  managed_area_source_class S1-S8, whichever supplied the figure
  documentary_area_note     anything qualifying the figure: whether it plainly
                            refers to WORKED land or to the whole holding, whether
                            it covers one parcel or several, and the year it
                            refers to. One line.

  total_holding_ha          the whole landholding
  area_type                 actively managed | total holding only | both recorded | not stated
  tenure_type               freehold collective | freehold individual | leasehold |
                            commons or trust | informal | mixed | unknown
  parcel_structure          contiguous | non-contiguous | unknown
  site_plan_published       yes (give URL) | no

  A community holding 200 ha and working 15 ha has managed_area_ha = 15 and
  total_holding_ha = 200. NEVER substitute one for the other — confusing them is
  the commonest error in this block, and it moves a community two size classes.

  NEVER ESTIMATE managed_area_ha FROM SATELLITE OR MAP IMAGERY, and never from a
  map view, a site plan you have not read a figure off, or an impression of how
  big the place looks. You cannot measure area reliably from a view. The study
  takes that measurement from a controlled drawing procedure carried out by the
  researcher, and a guessed number here would silently contradict it.

  If no source STATES an area, write NOT FOUND and set managed_area_basis = not
  found. That is a complete and correct answer, and the researcher's polygon will
  still give the site its full geometry.

BLOCK F — PRACTICE CODES  (THIRTEEN CODES)
  Code each at ONE of these five levels:
    evidenced         documented by an EXTERNAL or VISUAL source, with specificity
    documented        described specifically by the community, with continuity
    claimed           asserted without specificity or corroboration
    explicitly absent the community STATES IT DOES NOT do this
    not mentioned     no statement either way

  CRITICAL: "not mentioned" is NOT "explicitly absent". Only use "explicitly
  absent" when a source contains an actual denial.

  An academic or grey source is what upgrades a code from "claimed" to
  "evidenced". Look for one before settling on "claimed".

  pc01_rainwater        rainwater harvesting
  pc02_swales           swales, keyline earthworks, contour water works
  pc03_irrigation       irrigation used — and its source if stated
  pc04_no_till          no-till or minimum tillage
  pc05_mulching         permanent ground cover and mulching
  pc06_cover_crop       cover cropping or green manure
  pc07_tree_planting    tree planting or reforestation
  pc08_agroforestry     food forest or agroforestry
  pc09_polyculture      perennial polyculture
  pc10_hedgerows        hedgerows and windbreaks
  pc11_small_parcel     small-parcel diversified planting
  pc12_organic          organic or no synthetic inputs — name any certifying body
  pc13_restoration      LAND RESTORATION OR REHABILITATION, NON-TREE — grassland
                        or pasture restoration, wetland creation, erosion or gully
                        control, revegetation of degraded ground. SEPARATE from
                        pc07: pc07 is tree planting, pc13 is everything else.
  practice_evidence_notes  one line per CODED practice: what the source said,
                           and which source number it came from

BLOCK G — STATUS AND SURVIVORSHIP
  status_current       active | dormant | transformed | relocated | dissolved | unknown
  status_evidence      what the status rests on
  first_listing_year   earliest year it appears in ANY directory or archive
  last_listing_year    most recent year it appears
  dissolution_year     if dissolved, when — else n/a
  delisting_reason     dissolution | relocation | changed network |
                       administrative removal | lost contact | unknown | n/a

  "unknown" is NOT "dissolved". A vanished website is not a vanished community.

BLOCK H — CONTEXT
  movement_tradition   permaculture | ecovillage network | Camphill | kibbutz |
                       Buddhist or spiritual | Transition | agroecology | other | none stated
  founding_decade      derived from date_formal_founding, e.g. 1980
  education_volunteer_program  yes | no | unclear
  agricultural_orientation     subsistence | market | mixed | none stated
  external_funding_or_programme  any documented state, NGO or grant-funded
                       restoration programme at the site, or "none found".
                       This comes mainly from Stage 6.
  protected_area_status  inside | adjacent | no | unclear
  notable_context      war, drought, land dispute, major fire, relocation, or "none found"

BLOCK I — PROVENANCE
  source_set_supplied  every address I gave you: url | platform type |
                       independence group | crawl status | pages opened.
                       One line each. An address I supplied and you did not
                       open must appear here as "not attempted".
  source_set_discovered  every address you FOUND that I did not give you, in
                       the same format. Old domains especially.
  independence_groups  how many distinct groups the sources fall into. This is
                       normally far smaller than the number of URLs, and it is
                       the number channel_count is built on.
  stages_completed     which of stages 0-9 you finished, which you cut short,
                       and which you never reached
  crawl_truncated      yes | no  — did you stop before finishing the protocol?
  pages_opened_count   distinct URLs you OPENED, including those yielding nothing
  documents_opened     PDFs, spreadsheets and other files opened, by title
  academic_search_log  WHICH DATABASES you searched, how many hits each returned,
                       and how many you opened in FULL TEXT versus abstract only
  grey_literature_log  grey sources found, BY TYPE — thesis | grant record |
                       NGO report | government report | conference paper |
                       certification audit | planning permit | other
  source_classes_found which of S1-S8 you located
  search_languages     which languages you searched in
  negative_consultations  source classes and DATABASES checked and found empty,
                       e.g. "S1: none found in Google Scholar, SciELO, OATD,
                       DART-Europe, national portal. S2: none found in CORDIS, LIFE."

  SOURCE CLASSES
    S1 ACADEMIC — peer-reviewed papers, THESES AND DISSERTATIONS, conference
       papers, preprints
    S2 INSTITUTIONAL — government, NGO, certification, land registry,
       GRANT AND FUNDING RECORDS
    S3 external network or directory profile
    S4 the community's own current published material
    S5 ARCHIVED snapshots of the community's own material  (best for dating)
    S6 journalism and documentary media
    S7 social media and member accounts  (supporting evidence only)
    S8 direct communication

=============================================================
OUTPUT FORMAT
=============================================================

Be compact. One line per field. No preamble, no summary paragraph, no
commentary except where a value genuinely needs a one-line qualification.

  COMMUNITY: <n>   |   COORDINATES: <lat>, <lon>   |   MODE: <mode>
                                                   |   RUN: <run mode>

  -- SOURCE SET --
  (report this FIRST, before any field, and before you crawl)
  id        url                        type              group  status   pages
  IC001-01  https://...                own website       G1     crawled   18
  IC001-02  https://...                former website    G1     crawled    9
  IC001-03  https://facebook.com/...   Facebook          G1     blocked    0
  IC001-04  https://ecovillage.org/... directory listing G1     crawled    3
  IC001-05  https://youtube.com/...    YouTube           G1     crawled    6
  supplied: <n>   discovered: <n>   independence groups: <n>

  CRAWL: <n> URLs opened, <n> documents opened, <n> yielded data
         languages: <...>   |   sitemaps found: <n>   |   feeds found: <n>
         archived snapshots retrieved: <n>, earliest <year>
         CDX index queried: yes/no, <n> archived URLs listed
  STAGES: completed <list>  |  cut short <list>  |  not reached <list>
         crawl_truncated: yes/no
  ACADEMIC: databases searched <list> | hits <n> | full text opened <n> |
         abstract only <n> | citation chains followed <n>
  GREY: <n> items — <types found, or "none found">

  -- BLOCK A --
  field_name = value   [src 1,4]
  ...
  (repeat for blocks B to I)

  -- SOURCES --
  1. <full URL>  — <source class S1-S8> — <independence group> —
     <what it supplied>  [full text | abstract only]
  2. ...

  -- WHAT EACH ADDRESS CONTRIBUTED --
  <address_id>: <fields it supplied, or "nothing">

  -- CONFLICTS BETWEEN SOURCES --
  <field> : <value A> [src n] vs <value B> [src m] — resolved to <x> because
  <rank reason>, or left unresolved with both bounds recorded

  -- PAGES OPENED THAT YIELDED NOTHING --
  <list the URLs, so the search is auditable>

  -- DATABASES SEARCHED WITH NO RESULT --
  <name each one, so the negative consultation is auditable>

  -- FAILED TO LOAD OR BLOCKED --
  <URLs or databases attempted that returned an error, paywall, login wall or
  empty page>

  -- DATA GAPS --
  <fields you could not find, one line each, with what you tried>

  -- LOW CONFIDENCE --
  <any value you are less than confident about, and why>

  -- WORTH A SECOND RUN --
  <only if crawl_truncated = yes: which stages or addresses, and why>

Then stop. Do not add advice, interpretation or next steps.

Confirm you have understood, and I will send the first community.
```

---
# PART C — Practical notes

## What to realistically expect

**ChatGPT is not literally a crawler**, and no prompt can make it one. It fetches pages one at a time, has a budget of tool calls per response, and will sometimes stop earlier than you want. Version 2.4 pushes it considerably harder than version 2.3 did — but the honest position has not changed: expect **25–40 pages on a good FULL run**, not a full harvest of every address and every database named.

**What version 2.4 actually buys you** is not a bigger budget. It is three other things:

- **The budget is spent more evenly.** Stage 0 commits to the address list before crawling, and the instruction to reach 8–12 pages on each address before moving on stops the run spending everything on the first URL in the list.
- **Some single requests return a great deal.** A `sitemap.xml`, an RSS feed and a CDX index query each cost one fetch and can return hundreds of URLs, including deleted pages that no live link points at. Three cheap requests can outperform twenty expensive ones.
- **The shortfall becomes visible.** `crawl_truncated` and `stages_completed` convert a silent half-search into a recorded one, which is the difference between a gap you can fix and a gap you never see.

## Which communities deserve extra runs, and what it costs

Running everything four times is not worth it. Here is the arithmetic, and then the recommendation.

**One run per community.** 212 communities. At roughly 8–12 minutes each, including your own reading and pasting, that is **28 to 42 hours**.

**Four runs for everyone.** 212 × 4 = 848 runs — **113 to 170 hours**. That is three to four times the cost of the polygon drawing, for depth you do not need at most sites.

**The tiered version, which is what I would do.** Give every community one FULL run. Then add runs only where a second pass could change an analysis:

| Extra run | Which communities | Roughly |
|---|---|---|
| `RUN: SOURCE` on each substantive extra address | Those where FULL reported `crawl_truncated = yes`, or reported an address as `not attempted`, **and** the community has more than one substantive address | ~70–80 communities |
| `RUN: ACADEMIC` | Any community that looks likely to have been studied — large, old, well known, near a university — plus every one where activity tier came back B or C, since a single thesis moves it to A | ~50–60 communities |
| `RUN: SOURCE` plus `RUN: ACADEMIC` regardless | **Every cohort candidate.** Analysis A8 admits only confidence tier A or B, and decision D4 turns on how many core candidates reach that bar. An hour spent here changes whether the component survives | ~65 communities |
| `RUN: RECONCILE` | Every community that was split across more than one run — mandatory, never optional | as many as were split |

That comes to roughly **350–400 runs**, or **47 to 70 hours** — about **20 to 28 hours more** than single-pass, for most of the available benefit. Spend it on the cohort first.

**One thing not to economise on.** If a community was split across several runs, it must get a `RECONCILE` run. Several partial records with no merge is worse than one thin record, because it looks complete when read one piece at a time.

## How to check the output

**Verify 20 communities yourself, chosen at random.** Open the cited URLs and confirm each field. This *is* the double-coding exercise the plan requires, and it produces the reliability statistics the methods chapter needs.

**Check every academic citation individually.** This is not the same as checking a website link. A fabricated paper is the most damaging error possible here, because it looks like your strongest evidence. For every S1 source: does the DOI resolve? Does the repository record exist? Does the named author have that publication? If any answer is no, discard the whole record for that community and re-code from scratch.

**Check the source set table against what you supplied.** Every address you listed must appear with a status. An address that has silently vanished from the output was not crawled, whatever the rest of the response implies.

**Check the independence groups, not just the source count.** If a community reports eight sources in one group, it has one source. This is the single easiest place for a thin record to look thorough.

**A useful spot-check on effort.** Compare `pages_opened_count` against the sources list. If it opened 30 and cites 4, that is normal — real crawls have a low hit rate. If it claims 30 and lists 30 that all yielded data, be suspicious.

**Expect most academic searches to return nothing.** If ChatGPT reports finding papers for most of your 212 communities, something is wrong. In this population, a handful are well studied and the large majority have never been written about at all.

**Expect `crawl_truncated = yes` reasonably often.** If it never appears across 212 communities, that is not good news — it means the field is not being used, and truncation is being hidden rather than avoided.

## Three things to track as you go

**Block C will succeed unevenly.** Rank 1 and 2 evidence exists for perhaps a third of communities — and Stages 5 and 6 are what raise that fraction. For the rest expect rank 3 or 4 with wide bands. That is a real result, and it is why the plan propagates onset uncertainty by multiple imputation rather than pretending to a precise year.

**Keep a running tally of `cohort_candidate = core`.** The longitudinal cohort needs about 65 communities with onset in 2020–2021. Decision D4 says: at community 100, count the core candidates **at confidence tier A or B** — above 50 proceed; 40–50 proceed but report as exploratory; below 40, drop the component. `Cohort_Tracker` in workbook v6 computes this for you. (In v5 it read the wrong cell and would have printed PROCEED at community 50 regardless of the cohort; that is fixed.)

**Keep a tally of `crawl_truncated = yes` as well.** If it climbs past about a fifth of the sample, the single-run mode is not doing the job for your population and the tiered plan above needs to become the default rather than the exception.
