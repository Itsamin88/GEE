# Web-search data collection — field register and crawler prompt

**Version 3.0 · aligned to THE_SIMPLIFIED_PLAN_v4.0 · pairs with Stage_1_Essential_Data_Workbook_v1**

Three parts. **Part A** is the field register — what to collect, in what format, with the coding rules. **Part B** is a ready-to-paste prompt, built from Part A. **Part C** is honest guidance on what to expect and how to check it.

---

## What changed in version 3.0 — and why this is a rebuild, not an edit

Version 2.4 collected **88 fields in nine blocks**. Fourteen of those fields were **Block F, the thirteen documentary practice codes plus their evidence notes**. Those fields, and the analysis they existed to feed, have been removed from the study.

**The reason, in one paragraph.** A practice code recorded what published sources *say* a community does. For the large majority of the 212 communities the only available source is the community's own material — the register's own independence rule collapses a website, its Facebook page, its YouTube channel and a directory listing copied from it into **one voice** — so the dominant coding level would have been `claimed` or `not mentioned`, and `evidenced` would have been reachable only for the minority of communities that have been studied, funded or certified. That minority is not a random subset: it is the larger, older, better-organised, more visible communities. The analysis those codes fed compared communities *claiming* a practice against communities *not claiming* it, which forces `not mentioned` into one arm or the other and so breaks the register's own most important rule — that silence is not absence. Worse, documentation quality plausibly correlates with the outcome, so the analysis had a live route to a **positive** result produced entirely by organisational capacity, on the study's most quotable claim. The full argument, including the partial-retention options that were considered and rejected, is in `DECISION_MEMO.md`.

**This register is rebuilt from Part A upward, not edited.** Block F is not merely deleted: the blocks are relettered, the priority order is rewritten, the crawl budget is re-allocated, and every remaining block was re-tested against the question *what downstream decision or analysis changes because of this field?* Eleven further fields failed that test and were deleted. Two duplicate entry points were merged.

| Change | Effect |
|---|---|
| **Block F — practice codes — DELETED** | 14 fields removed. No practice code, coding level, claim-to-signature mapping or practice evidence row survives anywhere in the system |
| **Blocks relettered A–H** | Nine blocks become eight. Old G status → new F, old H context → new G, old I provenance → new H. The mapping table is in §A.6 |
| **Block D renamed** | "Activity verification" → **"Evidence verification"**, and `activity_tier` → `evidence_tier`. The old name invited the reading the variable cannot support. See §A.5 |
| **`channel_count` and `evidence_tier` are no longer collected** | They are DERIVED in the workbook from V1–V5. In v2.4 the assistant supplied them and they could disagree with the channels behind them |
| **The evidence tier ladder is rebuilt** | v2.4's tier C was **unreachable** and its ordering ranked three self-documented channels above two including a thesis. See §A.5 |
| **Two duplicate fields merged** | `e3_population_value` and `population_value` collected the same quantity twice. `e5_active_currently` duplicated `status_current` at lower resolution. One entry point each now |
| **Eleven low-value fields deleted** | `date_first_residence`, `domain_onsets`, `tenure_type`, `site_plan_published`, `first_listing_year`, `movement_tradition`, `education_volunteer_program`, `agricultural_orientation`, plus the two merged duplicates and `founding_decade` (now derived). Each is listed with its reason in §A.6 |
| **Crawl budget re-allocated** | The practice sweep was a large share of the reading effort on the community's own material. That budget now goes to Stages 4, 5 and 6 — archive, academic and grey literature — which is where rank-1 onset evidence actually lives. §B has a mandatory floor on those stages |
| **Priority order rewritten** | Eligibility is a cheap gate run first. Then onset, managed-area corroboration, population, status, essential context. §A.4 |
| **The three search outcomes are named explicitly** | EVIDENCE FOUND, EVIDENCE ABSENT, SEARCH INCOMPLETE. They must never be represented identically. §A.7 |
| **Register total: 88 → 61 fields, 9 → 8 blocks** | A 5 · B 6 · C 12 · D 5 · E 13 · F 5 · G 3 · H 12 |

### What did NOT change, and deliberately so

Everything in v2.4 that was strong is kept, because it supports the revised design at least as well as it supported the old one — in several cases better, since onset dating is now the single highest-priority target:

- the **ten-stage crawl protocol**, stages 0 to 9, with the same numbering;
- **Stage 0**, the source-set construction, and per-platform enumeration rules;
- **Stage 4**, the Wayback CDX index query — the largest single yield increase in the protocol, and now more valuable, not less, because dating is what it is best at;
- **Stages 5 and 6**, academic and grey literature, promoted from "also do not skip" to the protocol's **highest-priority** stages;
- **Stage 8**, the local-language sweep;
- **Stage 9**, cross-source reconciliation, and the **independence rule** in full;
- the **eight source classes** S1–S8 and their hierarchy;
- **negative consultations**, `stages_completed` and `crawl_truncated`;
- all **twelve anti-fabrication rules**, two of whose bullets are rewritten because they referred to practice coding;
- the **run modes** FULL / SOURCE / ACADEMIC / RECONCILE;
- the rule that a search assistant **never** estimates an area from imagery.

---

# PART A — The field register

**61 fields in eight blocks:** A identity 5 · B eligibility 6 · C onset 12 · D evidence verification 5 · E size and land 13 · F status 5 · G context 3 · H provenance 12.

## A.0 What NOT to search for

These quantities come from Google Earth Engine or from the researcher's own drawing. Searching for them wastes budget and risks importing a number computed on an incompatible basis.

| Do not search | Source |
|---|---|
| VM1–VM14 (all fourteen vegetation condition metrics) | Sentinel-2, computed in the pipeline |
| PM1–PM3 (provisioning metrics) | Same |
| FC1–FC4 (flag components) | Same |
| CA (contour alignment) | SRTM aspect + land-cover boundary orientation |
| VCI, VCI-P/S/T/C, PCI, MDS, LCC | Derived from the above |
| `built_fraction`, `tree_cover_pct` | Dynamic World |
| `elevation_m`, `slope_deg`, terrain class | SRTM |
| `water_dist_m` | Global Surface Water — a matching criterion, but satellite-derived |
| `koppen_group`, `biome` | Beck et al. / RESOLVE ecoregions |
| Annual rainfall, driest month, drought-year classification | CHIRPS |
| `n_clear` | Extraction output |
| `polygon_area_ha`, `polygon_iou` | **The researcher's** drawing, by plan §7.1. Never estimated from imagery by anyone else |
| `reference_circle`, `equal_area_circle_radius_m` | Computed by formula from the polygon area. NEVER derived from Earth Engine — that would set the measurement zone from the very signal measured inside it |
| `control_distance_km` | A **Stage 2** matching output, not documentary coding |

**One exception.** If a community publishes its own figures for elevation, rainfall or landholding size, record the landholding figure as `total_holding_ha`. Never substitute any of them for a pipeline value.

---

## A.1 Two modes

| Mode | Used for | Blocks required |
|---|---|---|
| **SETTLEMENT** | The 212 intentional communities, and every cohort candidate | All blocks, A to H |
| **CONTROL** | Conventional-village controls | Blocks A, B4–B6, G2 and H only — a control makes no ecological claim |

`protected_area_status` (G2) is required for controls because it is a Stage 2 **exclusion** criterion: a control inside a protected area is not usable. `external_funding_or_programme` (G1) is likewise checked for controls, because a control carrying its own documented restoration programme is not a control.

---

## A.2 Run modes — when one community needs more than one run

**The constraint is real and no wording removes it.** A search assistant fetches pages one at a time and has a budget of tool calls per response. Expect **25 to 40 pages on a good FULL run**. That number is a property of the *run*, not of the community — so the more addresses you give it, the thinner each one gets. The arithmetic is simply that the budget is per run, so runs multiply it.

| Run mode | What it does | When to use it |
|---|---|---|
| `RUN: FULL` | All ten stages, all addresses, in one pass | The default. Every community gets this first |
| `RUN: SOURCE <address_id>` | Stages 0–4 and 7 on **one** address only | A community with several substantive addresses, after FULL showed the extra ones were skimmed. Old domains hold the oldest material, which is where dating evidence lives |
| `RUN: ACADEMIC` | Stages 5, 6 and 8 only, exhaustively | **Now the highest-value extra run.** Any community that looks likely to have been studied, and every cohort candidate |
| `RUN: RECONCILE` | No new fetching. Reads the outputs of the previous runs and produces one merged record | Whenever a community was split across more than one run. **Never skip it** — an unreconciled community has several partial records and no single answer |

---

## A.3 The paste map — where each block lands

| Block | Sheet | Notes |
|---|---|---|
| A identity | `Community_Register` | Columns B–E and H. `latitude` and `longitude` at F–G are yours, never the assistant's |
| B eligibility | `Community_Register` | Columns I–N |
| C onset | `Onset_Register` | Columns C, E, F, G, H, J, K, L, N, O, P, Q. **Not** D `founding_decade`, I `onset_band_width_years` (both calculate themselves), or M `resolution_rule` (yours, when you settle a conflict) |
| D evidence verification | `Community_Register` | Columns AB–AF only. **`channel_count` (AG) and `evidence_tier` (AH) calculate themselves — never paste into them** |
| E size and land | `Community_Register` | Columns O–AA |
| F status | `Community_Register` | Columns AI–AM |
| G context | `Community_Register` | Columns AN–AP |
| H1–H5, H10–H12 | `Community_Register` | Columns AQ–AX |
| H6 `academic_search_log`, H7 `grey_literature_log` | `Search_Log` | **Unpacked into rows** — one row per database, INCLUDING those that returned nothing |
| H8 `source_set_supplied`, H9 `source_set_discovered` | `Source_Set` | **Unpacked into rows** — one row per web address |
| The sources themselves | `Source_Index` | One row each, with `independence_group` and `source_language` |

**Three distinct language columns, deliberately named apart.** `source_language` on `Source_Index` is the language a SOURCE is written in; `address_language` on `Source_Set` is the language of a WEB ADDRESS; `search_language` on `Search_Log` is the language a SEARCH was run in. Field H3 `search_languages` is the per-community summary of the third. Three different quantities sharing one column name is how a merge silently produces nonsense.

**`Community_Register` is the single paste target.** Everything the assistant returns goes there or to `Onset_Register`, and `Polygon_Geometry` reads the documentary area figures from `Community_Register` automatically. You enter each value once, in one place.

**Nothing the assistant returns ever lands on `Polygon_Geometry`.** If it returns a value for any polygon field, discard it: it has either guessed or read an area off a map, and both are forbidden.

---

## A.4 Priority order — where the budget goes

Version 2.4 spread its budget across the community's own material, where practice descriptions live. With practice codes gone, the budget moves to where the remaining fields' best evidence actually is.

**First, the gate.** Establish eligibility and coordinate agreement. It is cheap — a directory listing and an About page usually settle it — and it can end the run: an ineligible community needs no further searching. Do this before spending budget on anything else.

Then, in order:

| Priority | Target | Why here | Where the evidence is |
|---|---|---|---|
| **1** | **Onset dating** (Block C) | More analyses depend on onset than on any other documentary field — the age gradient, the entire longitudinal cohort, a named confounder in the size gradient — and it is the hardest field to establish. It is also the field where extra effort most reliably changes the answer, because rank-1 evidence exists for perhaps a third of communities and is nearly always *findable rather than absent* | Stages 4, 5 and 6. Archived snapshots, theses, grant records, permits |
| **2** | **Managed-area corroboration** (E5–E10) | The only independent check that will ever exist on the study's primary measurement geometry. A polygon with no documentary figure is measurable but uncorroborated | Stage 5 and 6 above all: a researcher who walked the site, or an applicant who had to justify a figure, reports the worked area precisely where a website gives one round number that is often the total holding |
| **3** | **Population** (E1–E4) | A Stage 2 matching criterion — an error here propagates into the control sample and cannot be repaired later — and a model covariate | Stages 2, 5, 7. Directory listings, theses, news |
| **4** | **Status and survivorship** (Block F) | Eligibility, and the survivorship limitation the plan states rather than hides | Stages 4 and 7. Directory archive history |
| **5** | **Essential context** (Block G) | Two Stage 2 exclusion criteria and the outlier-resolution field. Three fields, no more | Stage 6 for funded programmes; Stage 7 for the rest |

**Evidence verification (Block D) is not a search target.** It is scored from what the other stages found. Do not go looking for channels; record which ones the search produced.

### The mandatory floor on Stages 4–6

A FULL run may not close having spent its whole budget on the community's own current material. **At least 8 to 12 of the 25 to 40 pages must be spent on Stages 4, 5 and 6 combined** — archive, academic, grey — and the negative consultations must be recorded even when they return nothing. Version 2.4 had no such floor, and the practice sweep reliably consumed the budget before the run reached them.

Three cheap requests outperform twenty expensive ones here: a `sitemap.xml`, an RSS feed and a **Wayback CDX index query** each cost one fetch and can return hundreds of URLs, including deleted pages no live link points at.

---

## A.5 The evidence tier — read this before using Block D

Block D was called "activity verification" in v2.4 and its output was called `activity_tier`. Both names invited a reading the variable cannot support.

**What it measures.** How well documented a community's ecological work is, and how independent that documentation is. It is a property of the *record*, not of the land.

**What it does not measure.** How much ecological work the community does, or how well. A community managing land beautifully and publishing nothing scores Fail. Documentation quality correlates with size, age, funding and organisational capacity — which is exactly why it is useful as a **confounder** and exactly why it would be invalid as an **outcome**.

**Its three legitimate uses in v4.0**, each named in the plan:

1. a named confounder in the age-gradient analysis, alongside founding decade and population;
2. a sample-description variable, so a reader can see how much of the sample rests on self-report alone;
3. the restriction in sensitivity check SC18 — does the main result hold among communities whose ecological work is documented by somebody other than themselves?

**One prohibition.** The tier must never be disaggregated by *kind* of activity. Recording that a community documents tree planting rather than water works would rebuild a practice score under another name, with every defect that made practice codes unusable and none of the visibility.

### The five channels

Two channels are independent only if they do not derive from the same underlying statement. **Two pages of one website are ONE channel** — and so are a website, its own Facebook page and a directory listing copied from it. Channels count **independence groups, never addresses**.

| # | Field | Channel | What counts | External? |
|---|---|---|---|---|
| D1 | `v1_self_documentation` | V1 | The community describes *particular actions* — areas planted, earthworks built. Not aims | no |
| D2 | `v2_external_documentation` | V2 | Academic account, thesis, project record, certification, grant award, media coverage **of the work** | **yes** |
| D3 | `v3_substantive_affiliation` | V3 | Membership of a body that *assesses* practice, not one that merely lists members. Name it | **yes** |
| D4 | `v4_visual_documentation` | V4 | Dated photographs, site plans, design drawings, maps | no |
| D5 | `v5_continuity_evidence` | V5 | The work described consistently across years | no |

### The tier ladder — rebuilt

| Tier | Rule | Meaning |
|---|---|---|
| **A** | At least one external channel (V2 or V3), and **3 or more** channels in total | Externally documented and corroborated |
| **B** | At least one external channel, and **2** channels in total | Externally documented but thin |
| **C** | **No** external channel, and 2 or more channels | Community-documented only. However many forms the community's own material takes, it is one voice |
| **Fail** | Fewer than 2 channels, or aims without specific actions | Not eligible |

**Why the ladder was rebuilt.** Version 2.4's rule was: A = three or more including one external; B = two, at least one visual or continuity; C = two community-originated; Fail = fewer than two. That rule has two defects. First, **tier C is unreachable**: the only channel that is neither external nor visual nor continuity is V1, and no community can have two of V1, so every two-channel community falls to B. Second, it ordered by **count before independence**, so a community with three channels of its own material outranked a community with two including a thesis — which inverts what the tier is for. The v4.0 ladder orders by independence first. Every tier is reachable and the ordering is monotone in the thing the variable is supposed to measure.

**A thesis or a grant report satisfies V2 on its own**, which frequently moves a community from tier C to tier A or B. That is a second reason Stages 5 and 6 matter, on top of onset dating.

**`channel_count` and `evidence_tier` are computed in the workbook.** Do not supply them.

---

## A.6 What was deleted from v2.4, and why

Every deletion below was tested against one question: **what downstream decision or analysis changes because of this field?** Where the answer was "none", the field was deleted rather than kept for completeness — a large descriptive database with no analytical purpose costs coding time on the critical path and invites over-reading.

### Block F — the thirteen practice codes (14 fields). DELETED.

`pc01_rainwater` · `pc02_swales` · `pc03_irrigation` · `pc04_no_till` · `pc05_mulching` · `pc06_cover_crop` · `pc07_tree_planting` · `pc08_agroforestry` · `pc09_polyculture` · `pc10_hedgerows` · `pc11_small_parcel` · `pc12_organic` · `pc13_restoration` · `practice_evidence_notes`

The analysis they fed is deleted, so they have no consumer. See `DECISION_MEMO.md` for the full argument, including why retaining `pc02_swales` alone for the contour-alignment check, and why retaining the codes descriptively, were both considered and rejected.

### Individual fields

| Deleted field | Old block | Why |
|---|---|---|
| `e3_population_value` | B | **Duplicate.** The same quantity was collected again as `population_value` in Block E. Two authoritative entry points for one number is a guaranteed drift |
| `e5_active_currently` | B | **Duplicate at lower resolution.** `status_current` in Block F carries the same information on a six-level scale and with an evidence field behind it. Eligibility now reads `status_current` |
| `date_first_residence` | C | No downstream consumer. Unlike founding and land acquisition it does not bound the onset in either direction: intervention can precede first residence by years or follow it by decades. The two dates that *do* bound it are retained |
| `domain_onsets` | C | Its value was a per-domain onset — "water 1998; vegetation 1992". With no per-domain analysis there is nothing to consume it. The study's onset is the **earliest** deliberate ecological intervention of any kind, and that single year is recorded directly |
| `tenure_type` | E | No downstream consumer. It informed nothing: the anonymisation rule for published outputs is unconditional, so tenure changes no decision |
| `site_plan_published` | E | **Duplicate by another route.** A published site plan is a source: it belongs in `Source_Index` with its own row, and it satisfies channel V4. A separate yes/no field records the same fact a third time |
| `first_listing_year` | G (old) | No downstream consumer. Community age comes from onset, and the survivorship estimate operates on directory snapshots rather than on per-community listing years. `last_listing_year` is retained because it is the dating evidence behind `status_current` |
| `movement_tradition` | H (old) | No downstream consumer — not a moderator, not a covariate, not a matching variable, not in any table. It is also a **self-description**, and admitting self-descriptions as predictors is precisely the failure that removed the practice codes |
| `education_volunteer_program` | H (old) | No downstream consumer |
| `agricultural_orientation` | H (old) | No downstream consumer. Interpretively adjacent to the provisioning outcome, but no declared analysis uses it, and it is a self-description |
| `founding_decade` | H (old) | **Now derived.** It is a function of `date_formal_founding` and is computed in the workbook |
| `channel_count`, `activity_tier` | D | **Now derived** from V1–V5 in the workbook. Supplied by the assistant in v2.4, where they could disagree with the channels behind them |

### Block letters, old to new

| v2.4 | v3.0 | Block |
|---|---|---|
| A | A | Identity |
| B | B | Eligibility |
| C | C | Onset |
| D | D | Activity verification → **Evidence verification** |
| E | E | Size and land |
| **F** | — | **Practice codes — deleted** |
| G | **F** | Status and survivorship |
| H | **G** | Context |
| I | **H** | Source provenance |

---

## A.7 Three search outcomes, never represented identically

This is the discipline the whole register turns on, and it matters more now than it did in v2.4, because the fields that remain are the ones a thin search fails hardest on.

| Outcome | What it means | How it is recorded |
|---|---|---|
| **EVIDENCE FOUND** | A source states the value | The value, with its source id |
| **EVIDENCE ABSENT** | An adequately exhaustive search found no support | `not found` **and** the named negative consultations in `Search_Log`. This is a finding |
| **SEARCH INCOMPLETE** | The run was truncated, blocked, or cut short | `crawl_truncated = yes`, and `stages_completed` saying exactly where it stopped. This is **not** a finding |

A community searched for four minutes and a community searched exhaustively that genuinely has nothing produce the **same thin record full of `not found`**. They mean opposite things. One is an absence of evidence and the other is an absence of effort, and only one of them is a result.

---

## Block A — Identity and location (5 fields)

| # | Field | What to find | Format |
|---|---|---|---|
| A1 | `community_name_official` | The name it uses for itself, in its own language, plus any English form | text |
| A2 | `alternative_names` | Former names, local names, transliterations, network variants | semicolon-separated, or `not found` |
| A3 | `country` | Nation-state | text |
| A4 | `admin_region` | Province, state, county | text |
| A5 | `coordinate_agreement` | Do published sources place it where the held coordinates do? | `agrees` / `differs` / `no published location` — anything qualifying it goes in the notes |

**Why A5 matters more than it looks.** The polygon, the five rings, the common circle and every extraction are drawn about the held coordinates. Geocoded directory coordinates are frequently a postal address in a neighbouring village, and a wrong centre invalidates the entire measurement at that site.

**Why A2 matters more than it looks.** Every name variant is a separate academic and archive search string. A community listed as "Tamera" in English may appear as "Tamera Heilungsbiotop" in a German thesis, and the thesis is where the rank-1 onset date is.

---

## Block B — Eligibility (6 fields) — *criteria E1, E2, E8*

| # | Field | Criterion | What to find | Format |
|---|---|---|---|---|
| B1 | `e1_network_listing` | E1 | Which networks or directories list it | semicolon-separated |
| B2 | `e1_pathway` | E1 | How it qualifies | `network/directory listing` / `independent self-identification` / `both` |
| B3 | `e1_self_identification` | E1 | A published phrase stating ecological aims | text, under 25 words |
| B4 | `e2_settlement_type` | E2 | What kind of entity | `village-scale permanent residence` / `retreat centre` / `campus` / `business` / `single household` / `urban co-housing` / `unclear` |
| B5 | `e2_evidence_note` | E2 | One line on why | text |
| B6 | `e8_setting_at_onset` | E8 | Rural or peri-urban at onset, not urban? | `rural` / `peri-urban` / `urban` / `unclear` |

**B4 is the highest-consequence code in Stage 1.** It decides whether a community is in the study at all, and no later stage revisits it. Code it against the definitions and examples on `Definitions_And_Freeze`, and put the reason in B5.

**Criterion E5 (currently active) is now read from `status_current` in Block F**, which carries the same information on a six-level scale with an evidence field behind it.

---

## Block C — Onset dating (12 fields) — **THE PRIORITY BLOCK**

| # | Field | What to find | Format |
|---|---|---|---|
| C1 | `date_formal_founding` | Year established as an entity | year or `not found` |
| C2 | `date_land_acquisition` | Year land was bought, leased or occupied | year or `not found` |
| C3 | **`date_intervention_onset`** | **Year the first deliberate action to alter vegetation, soil, water or land cover for ecological purposes is documented. This is NOT the founding year, and it is NOT the year the land was acquired** | year or `not found` |
| C4 | `onset_lower_bound` | Earliest plausible year | year |
| C5 | `onset_upper_bound` | Latest plausible year | year |
| C6 | `onset_evidence_rank` | Strength of evidence | `1`–`5` |
| C7 | `onset_evidence_description` | What the evidence is | one line |
| C8 | `onset_conflicting_sources` | Where sources disagree, what each says | text or `none` |
| C9 | `onset_proxy_flag` | Is C3 a founding year used as a substitute? | `yes` / `no` |
| C10 | `onset_confidence_tier` | For the cohort | `A` precise / `B` ±1 year / `C` uncertain |
| C11 | `onset_first_or_major` | FIRST intervention, or a later MAJOR project? | `first intervention` / `major new project` / `unclear` |
| C12 | `cohort_candidate` | Does onset fall in the cohort window? | `core (2020–2021)` / `extension (2019)` / `no` / `uncertain` |

**Why three candidate dates and not four.** C1 exists because distinguishing founding from onset is the study's central dating rule, and because it supplies the founding decade the age analysis names as a confounder. C2 exists because it is the hardest available **lower bound**: a community cannot intervene on land it does not hold. `date_first_residence` was deleted because it bounds nothing — intervention can precede first residence or follow it by decades.

### The onset evidence rank scale

| Rank | Evidence | Typical band |
|---|---|---|
| **1** | Dated independent record — permit, **grant award, project report**, registry entry, **academic paper or thesis** | 0 to ±1 year |
| **2** | Dated archived snapshot describing work as **already under way** | ±1 to ±3 years; firm upper bound |
| **3** | The community's own dated retrospective statement | ±2 to ±5 years |
| **4** | Undated community statement, onset inferred from context | ±5 years or wider |
| **5** | Directory founding year used as a proxy | **Not an onset.** Set C9 = yes |

**Note where rank 1 comes from.** Almost every rank-1 source is academic or grey literature — a thesis that dates the fieldwork, a grant report that dates the project, a permit. That is why Stages 5 and 6 are the protocol's highest-priority stages: they are where the *best* onset evidence lives, not merely where extra evidence lives.

**The distinction that matters most:** a community founded in 1985 that began ecological work in 1992 has an onset of **1992**.

**The overall onset is the EARLIEST deliberate ecological intervention of any kind** — water, soil, vegetation or land cover. v2.4 recorded these separately in `domain_onsets`; with no per-domain analysis, only the earliest year is needed, and it is recorded directly in C3.

---

## Block D — Evidence verification (5 fields) — *see §A.5 before using this block*

| # | Field | Channel | What counts |
|---|---|---|---|
| D1 | `v1_self_documentation` | V1 | The community describes *particular actions* — areas planted, earthworks built |
| D2 | `v2_external_documentation` | V2 | Academic account, thesis, project record, certification, grant award, media coverage **of the work**. **External** |
| D3 | `v3_substantive_affiliation` | V3 | Membership of a body that *assesses* practice. Name it. **External** |
| D4 | `v4_visual_documentation` | V4 | Dated photographs, site plans, design drawings, maps |
| D5 | `v5_continuity_evidence` | V5 | The work described consistently across years |

All five are `yes` / `no`. **Do not supply `channel_count` or `evidence_tier`** — the workbook computes both, by the ladder in §A.5.

---

## Block E — Size, land and population (13 fields) — **E5 IS A PRIORITY FIELD**

| # | Field | What to find | Format |
|---|---|---|---|
| E1 | `population_value` | Permanent residents only. Not visitors, volunteers or students | integer or `not found` |
| E2 | `population_lower` | Lower end where a source gives a range | integer |
| E3 | `population_upper` | Upper end where a source gives a range | integer |
| E4 | `population_source_date` | Year the figure refers to | year |
| **E5** | **`managed_area_ha`** | **Land actively worked ecologically. THE PRIORITY FIELD IN THIS BLOCK** | hectares or `not found` |
| **E6** | **`managed_area_lower_ha`** | Lowest plausible figure the sources support | hectares |
| **E7** | **`managed_area_upper_ha`** | Highest plausible figure | hectares |
| **E8** | **`managed_area_basis`** | How the figure was arrived at | `measured` / `stated` / `inferred` / `not found` |
| **E9** | **`managed_area_source_class`** | Which source class supplied it | `S1`–`S8` |
| **E10** | **`documentary_area_note`** | Anything qualifying the figure — whether it plainly refers to worked land or to the whole holding, whether it covers one parcel or several, and the year it refers to | text |
| E11 | `total_holding_ha` | The whole landholding | hectares or `not found` |
| E12 | `area_type` | Which of E5/E11 the source gives | `actively managed` / `total holding only` / `both recorded` / `not stated` |
| E13 | `parcel_structure` | One block or several | `contiguous` / `non-contiguous` / `unknown` |

**A community holding 200 ha and working 15 ha has `managed_area_ha` = 15 and `total_holding_ha` = 200. NEVER substitute one for the other** — confusing them is the commonest error in this block, and it is what produces a spurious tier-C disagreement with the drawn polygon.

### What E5 is for

Managed area **does not set the measurement area.** The polygon the researcher draws does that, and the polygon's own area is the predictor in the size-gradient analysis.

**E5 is the independent check on that drawing** — a real job, not a leftover one. It is the only outside evidence there will ever be that the drawn outline matches what the community says it works. The plan compares them and grades each site: agreement within 30% is tier A, a gap of 30 to 100% is tier B, a gap beyond a factor of two is tier C and gets investigated. **A site with a polygon and no documentary figure is tier B**, and the polygon gives it full geometry regardless.

**A gap beyond a factor of two has two common causes.** The first and commonest is that the source quotes the **total holding** rather than the worked area. The second is a genuinely **non-contiguous** holding whose detached parcels the polygon excludes, because parcels more than 500 m from the centre cannot fall inside any measurement zone. E13 is what separates the two, which is why it is retained.

**The band (E6, E7) is what makes the check meaningful.** A source saying "about 15 hectares" and a polygon of 11 ha are not in conflict; a source saying "15.4 hectares under cultivation" and the same polygon are. Recording only a point estimate throws that distinction away.

**The basis (E8) works like the onset evidence rank:**

| Basis | Meaning |
|---|---|
| `measured` | A source reports an area someone actually measured — a thesis, a survey, a land registry entry, a grant application, a site plan with a scale |
| `stated` | The community states a figure without saying how it was arrived at |
| `inferred` | You derived it from something else — a stated number of beds, plots or hectares under a named crop. Say how, in E10 |
| `not found` | No figure anywhere |

**Theses and grant applications are the best sources for E5.** A researcher who walked the site, or an applicant who had to justify a figure, usually reports the worked area precisely — where a community website says "our land" and gives one number that is often the total holding. This is why managed-area corroboration is priority 2 and why it is largely a Stage 5 and 6 target.

### What this register does NOT cover

**The assistant does the documentary route. The researcher draws the polygons.** The two do not overlap at all.

**What the assistant fills** — six documentary area fields, plus its source rows. They are entered **once**, on `Community_Register`, and `Polygon_Geometry` reads them from there automatically:

`managed_area_ha` · `managed_area_lower_ha` · `managed_area_upper_ha` · `managed_area_basis` · `managed_area_source_class` · `documentary_area_note`

**Everything on `Polygon_Geometry` is the researcher's**, from the drawing procedure in the plan:

| Column | Source |
|---|---|
| `polygon_area_ha` | The polygon you draw |
| `polygon_file_id` | The exported shapefile or GeoJSON feature |
| `polygon_imagery_date` / `polygon_imagery_source` | The imagery you drew on |
| `polygon_confidence` | `clear` / `moderate` / `poor` |
| `polygon_redrawn` / `redraw_area_ha` / `polygon_iou` | The 20% redraw after four weeks |
| `agreement_note` | What you found when you investigated a tier C |
| `controls_translated` | Confirmation the shape was moved onto all three controls |

`below_minimum_flag`, `reference_circle`, `equal_area_circle_radius_m`, `area_ratio` and `area_agreement_tier` all calculate themselves.

**If the assistant ever returns a value for one of these, discard it.** It has either guessed or read an area from a map, and both are forbidden.

---

## Block F — Status, persistence and survivorship (5 fields)

| # | Field | What to find | Format |
|---|---|---|---|
| F1 | `status_current` | Present state | `active` / `dormant` / `transformed` / `relocated` / `dissolved` / `unknown` |
| F2 | `status_evidence` | What it rests on | text |
| F3 | `last_listing_year` | Most recent year it appears in any directory or archive | year or `not found` |
| F4 | `dissolution_year` | If dissolved, when | year or `n/a` |
| F5 | `delisting_reason` | Why it left a directory | `dissolution` / `relocation` / `changed network` / `administrative removal` / `lost contact` / `unknown` / `n/a` |

**`unknown` is not `dissolved`.** A vanished website is not a vanished community. Dissolution requires **positive** evidence, and F2 is that evidence.

**Why this block survives at all.** The sample is drawn from directories, which list survivors — so it is biased in the direction of the study's own hypothesis, and the plan states that as a limitation with a partial remedy. F1 also supplies eligibility criterion E5. F3 is the dating evidence behind F1. `first_listing_year` was deleted: community age comes from onset, and the attrition estimate operates on directory snapshots rather than on per-community listing years.

---

## Block G — Context (3 fields)

Version 2.4 had seven context fields. Four had no downstream consumer and were deleted; a fifth is now derived. These three each change a specific decision.

| # | Field | What to find | Format | What it changes |
|---|---|---|---|---|
| G1 | `external_funding_or_programme` | Documented state, NGO or grant-funded restoration programme at the site | text or `none found` | **A Stage 2 exclusion criterion.** A control with a documented external restoration programme is not a control; at a settlement it is a second intervention running in parallel with the community's own. It is also frequently rank-1 onset evidence |
| G2 | `protected_area_status` | Inside or adjacent to a protected area? | `inside` / `adjacent` / `no` / `unclear` | **A Stage 2 exclusion criterion.** Controls inside protected areas are excluded |
| G3 | `notable_context` | War, drought, land dispute, major fire or relocation **affecting land cover inside the study window** | text or `none found` | The field a flagged outlier is resolved against. An extreme value must be classed as a data error, an undetected disturbance or a genuine extreme, and this is where the third possibility is checked |

**G3 is narrowly scoped on purpose.** It is not a general history field. Record events that would change what the satellite sees between 2019 and 2025 — not a founding schism in 1994.

**G1 is largely a Stage 6 output.** Grant databases are where funded restoration programmes are recorded.

---

## Block H — Source provenance (12 fields)

| # | Field | What to record |
|---|---|---|
| H1 | `pages_opened_count` | Distinct URLs actually opened, including those yielding nothing |
| H2 | `source_classes_found` | Which of S1–S8 were located |
| H3 | `search_languages` | Which languages were searched |
| H4 | `negative_consultations` | Source classes and databases checked and found empty |
| H5 | `documents_opened` | PDFs, spreadsheets and other files opened, by title |
| H6 | `academic_search_log` | Which databases searched, how many hits, how many opened in **full text** versus abstract only. **Unpacks into `Search_Log` rows** |
| H7 | `grey_literature_log` | Grey sources found, by type — thesis, grant record, NGO report, government report, conference paper, certification audit, planning permit. **Unpacks into `Search_Log` rows** |
| H8 | `source_set_supplied` | Every address you were given: URL, platform type, independence group, crawl status, pages opened. **Unpacks into `Source_Set` rows** |
| H9 | `source_set_discovered` | Every address found during the crawl that was not supplied — old domains, second Facebook pages, a YouTube channel linked only from a footer. **Unpacks into `Source_Set` rows** |
| H10 | `independence_groups` | How many distinct independence groups the sources fall into. Usually far smaller than the number of URLs |
| H11 | `stages_completed` | Which of stages 0–9 were completed, and which were cut short |
| H12 | `crawl_truncated` | `yes` / `no`. Did the run stop before the protocol was finished? |

**Why H8 and H9 are separate.** H8 proves the addresses you supplied were each actually opened rather than collapsed into one. H9 is where the value usually is: a community's *former* domain holds its oldest material, is linked from nowhere, and is invisible unless something goes looking. With dating now the protocol's first priority, H9 is the field most likely to change an analysis.

**H12 is the most important field in the block and the least interesting to look at.** You cannot instruct a model past its tool budget. What you can do is make it say where it stopped.

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
| S8 | Direct communication | Moderate-high; requires ethics clearance |

**Grey literature splits across S1 and S2.** Academic grey — theses, conference papers, preprints — is S1. Institutional grey — NGO reports, government documents, grant records — is S2. Both are recorded in H7 regardless of class.

**Why H4 exists.** A value supported by an independent source *and* the community's own account is stronger than one supported by the community alone. That is invisible unless the *negative* consultations are recorded.

---

## The independence rule

This is the rule the multi-address protocol turns on, and it is easy to get backwards, because more addresses feel like more evidence.

**The test.** Two sources are independent only if **neither derives from the other, and neither derives from a third source they share**. Put as a question you can answer while reading: *could this source be wrong in the same way as that one, for the same reason?* If yes, they are one source.

**Assign a short group id — G1, G2, G3 — to every source as you read it.** Sources sharing a group share a voice.

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

- The evidence-tier channels count **groups**, so a community with a website, a Facebook page and an Instagram has **one** self-documentation channel, not three, and cannot reach tier A or B on its own material however many addresses it maintains.
- The "at least three independent sources" target means three **groups**.
- `onset_conflicting_sources` is only meaningful across groups. Two members of one group agreeing tells you the copy was accurate, nothing more.

**Why it matters most for onset.** An onset date corroborated by three URLs from one group is a single self-description, and could move a community from confidence tier B to tier A on the strength of a copy of itself. Tier A is what the longitudinal cohort admits, so the error would land directly in the study's only test that can check its own identifying assumption.

---

# PART B — The prompt

## How to use it

**Set it once as a project instruction or custom instruction.** Then each community is a short block, with **one address per line**:

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

List **every** address you have, in any order, and do not try to decide which is primary — Stage 0 does that, from what the pages contain rather than from which one you happened to find first. `SOURCES: NONE` is valid and sends the assistant to Stage 0's discovery route.

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
what sources say accurately, including unfavourable and inconvenient things,
is the entire task.

You are NOT asked to identify or code what agricultural or ecological
PRACTICES a community uses. Earlier versions of this protocol did. That was
removed from the study because practice-level documentary information could
not be established with enough completeness, consistency or independent
verification across the sample to support quantitative analysis. Do not
report practices, do not infer them, and do not add them back as context.

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

MODE SETTLEMENT means an intentional community — return every block A to H.
MODE CONTROL means a conventional village used as a comparison — return only
blocks A, B4-B6, G2 and H. A control has no onset and no evidence tier,
because the point of a control is that it makes no ecological claim. Do not
invent them. G2 protected_area_status and G1 external_funding_or_programme
ARE required for controls: both are exclusion criteria for the matching.

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

This study is about DATING and about LAND. Two consequences follow.

First, most communities have SEVERAL web addresses and they are not
equivalent. The current website says what the community wants said today. An
abandoned domain from 2011, a Facebook album, a YouTube upload date or a
directory listing captured in 2013 say what was true THEN — so the old
material is usually worth more than the new. Treat every address I give you
as a separate target with its own crawl. Do not pick one and summarise the
rest.

Second, the SINGLE most valuable thing you can find is a DATED INDEPENDENT
RECORD of when ecological work began: a grant award, a project report, a
planning permit, a registry entry, an academic paper or a thesis. Those live
in Stages 5 and 6, not on the community's website. A run that enumerates
forty pages of a current website and never reaches a thesis repository has
spent its budget in the wrong place.

WHAT TO PRIORITISE

  GATE, FIRST AND CHEAPLY:  eligibility (Block B) and coordinate agreement
                            (A5). If the community is plainly ineligible, say
                            so and stop — do not spend the budget.

  PRIORITY 1  ONSET DATING (Block C). The hardest field and the one the most
              analyses depend on.
  PRIORITY 2  MANAGED-AREA CORROBORATION (E5-E10). The only independent check
              that will ever exist on the study's measurement geometry.
  PRIORITY 3  POPULATION (E1-E4). A matching criterion; an error propagates
              into the control sample.
  PRIORITY 4  STATUS AND SURVIVORSHIP (Block F).
  PRIORITY 5  ESSENTIAL CONTEXT (Block G). Three fields. Do not expand it.

  BLOCK D IS NOT A SEARCH TARGET. Score it from what the other stages found.
  Do not go looking for channels.

=============================================================
THE CRAWL PROTOCOL — TEN STAGES, 0 TO 9
THIS IS WHERE MOST OF YOUR EFFORT GOES
=============================================================

You are not doing a normal web search. You are doing a systematic harvest of
everything ever published about one organisation — by the organisation
itself, and by anyone else. Work through the stages in order and do not skip
ahead.

  Stage 0     builds the list of addresses.
  Stages 1-4  cover the community's own record, at EVERY address.
  Stages 5-6  cover academic and grey literature. THE HIGHEST-PRIORITY
              STAGES: this is where rank 1 onset evidence lives.
  Stages 7-8  cover everything else and the local language.
  Stage 9     reconciles what the different sources said.

--- STAGE 0 — BUILD THE SOURCE SET ---

Before opening anything properly, build a table of every address that belongs
to this community.

0.1 START FROM WHAT I GAVE YOU. Every line under SOURCES is a separate
    target. Open each one just far enough to confirm what it is and that it
    belongs to this community — not a similarly named project elsewhere.
    Assign each an address_id: IC001-01, IC001-02, and so on.

0.2 FIND THE ONES I DID NOT GIVE YOU. These are usually the valuable ones.
      - Follow social icons in the header and FOOTER of the main site.
        Footers carry links to accounts nobody maintains any more.
      - Search the community name plus each platform:
        <name> facebook / instagram / youtube / vimeo / linkedin
      - Look for an OLD DOMAIN. Search the name with "formerly", the name
        plus an older project name, and check whether the current site's
        oldest blog posts link to a domain that is no longer the one you are
        on.
      - Search the community's postal address, phone number or email if
        published. The same contact details appear in directory listings you
        would not otherwise find.
      - Search for the community on the intentional-community directories by
        name: GEN / ecovillage.org, Foundation for Intentional Community,
        NuMundo, WWOOF, Workaway, and the NATIONAL network of its country.
      - If the community has a legal entity name different from its public
        name, search that too. Grant and registry records use the legal name,
        and grant records are rank 1 onset evidence.

0.3 CLASSIFY EACH ADDRESS as one of:
      own website · secondary or former website · Facebook · Instagram ·
      YouTube · Vimeo · blog platform · directory listing · crowdfunding ·
      LinkedIn · booking or hosting · news outlet · other

0.4 ASSIGN INDEPENDENCE GROUPS NOW, not later. Give a short id (G1, G2, G3)
    to every address, and the SAME id to any two that derive from each other.
    A community's website, its own Facebook page and a directory listing
    whose text was submitted from that website are ALL ONE GROUP. A thesis, a
    grant record and a newspaper are three different groups.
    Ask yourself: could this source be wrong in the same way as that one, for
    the same reason? If yes, same group.

0.5 REPORT THE TABLE BEFORE YOU CRAWL. List every address, its type, its
    group and whether it is supplied or discovered. Then work through them.
    Committing to the list first is what stops the crawl quietly collapsing
    into "the homepage plus four pages".

--- STAGE 1 — RANK THE SOURCE SET AND CONFIRM IT ---

Decide which address is the community's own primary site, and confirm each
address actually belongs to this community rather than to a similarly named
one elsewhere. A wrong attribution here contaminates every field that
follows.

If NO website exists at all, say so explicitly, crawl whatever social or
directory addresses do exist, and go to Stage 4.

If I gave you no addresses, find them: search the community name plus the
country, plus terms such as "ecovillage", "community", "permaculture",
"farm", "association", in ENGLISH and in the LOCAL LANGUAGE. Also try the
name as a domain: <n>.org, <n>.com, <n>.<country code>.

--- STAGE 2 — ENUMERATE EVERY PAGE ON EVERY ADDRESS ---

DO NOT STOP AT THE HOMEPAGE, AND DO NOT DO THIS FOR ONLY ONE ADDRESS. Build a
page list for each address first, then open them. Prefer DATED material and
material about the LAND over material about aims.

2A. WEBSITES (own, secondary, former). Use all five methods:

(a) Try the sitemap directly:
      <site>/sitemap.xml     <site>/sitemap_index.xml     <site>/robots.txt
    A sitemap gives the complete page list in one request. Always try it.

(b) Read the MAIN NAVIGATION MENU and the FOOTER, and list every internal
    link including drop-down sub-items. Footers often carry links to reports
    that appear nowhere in the main menu.

(c) Try these paths directly, and their local-language equivalents. They are
    ordered by what this study needs: history and dating first, land second,
    documents third.
      /history  /our-story  /timeline  /about  /about-us  /who-we-are
      /reports  /publications  /research  /documents  /downloads  /library
      /projects  /land  /farm  /garden  /water  /restoration  /forest
      /blog  /news  /journal  /updates
      /visit  /volunteer  /wwoof  /internship  /courses
      /people  /members  /contact  /faq

    Local-language examples:
      Portuguese/Spanish: /sobre  /historia  /quem-somos  /nosotros /proyectos
      German:  /ueber-uns  /geschichte  /projekte  /landwirtschaft
      French:  /a-propos  /histoire  /projets  /le-lieu
      Italian: /chi-siamo  /storia  /progetti
      Dutch:   /over-ons  /geschiedenis
      Nordic:  /om-oss  /historia  /om
      Use the right ones for the country, not all of them.

(d) Follow every internal link to a depth of at least THREE clicks from the
    homepage. For blog and news archives, go back through the pagination —
    the OLDEST posts are the most valuable, because this study is about
    dating.

(e) Enumerate what the search engines have indexed, which catches pages
    linked from nowhere:  site:<domain>   and   site:<domain> <year>

2B. BLOG PLATFORMS (WordPress, Blogspot, Medium, Substack, Ghost).
    The feed and the sitemap give you the entire dated post list in one or
    two requests — the cheapest high-value action in the whole protocol:
      <site>/feed   <site>/rss   <site>/atom.xml   <site>/sitemap.xml
    Then open the OLDEST posts first, and the monthly or yearly archive URLs
    (/2019/03/), and the category and tag pages.

2C. FACEBOOK.
      - The ABOUT tab. It often carries a "Page created" or "Founded" date
        and a stated address. The founding date field is a dated record.
      - PHOTOS and ALBUMS. Album titles and photo dates are frequently the
        only dated evidence a community ever produced.
      - EVENTS, past as well as upcoming. Events are dated and name projects.
      - The oldest POSTS. Use the year filter where one is offered.
    Facebook often refuses automated reading. If it does, say BLOCKED and
    move on. Do not describe what is probably on it.

2D. INSTAGRAM.
      - The bio, and the link in the bio, which often points at an address
        you do not yet have.
      - The earliest posts, at the end of the profile grid, if reachable.
    Instagram is usually unreadable without an account. Reporting that is a
    complete answer. Guessing at its content is fabrication.

2E. YOUTUBE AND VIMEO.
      - Go to the channel's videos and SORT BY OLDEST. An upload date is a
        dated record and is often rank 2 onset evidence: a 2013 video showing
        an established food forest proves the planting predates 2013.
      - Read the video DESCRIPTIONS, not just the titles. Descriptions carry
        project names, areas and dates.
      - Check the playlists. Communities organise them by project.

2F. DIRECTORY LISTINGS (GEN/ecovillage.org, FIC, NuMundo, WWOOF, Workaway,
    national networks).
      - Read the structured fields: founding year, population, land area.
        Record them — but they are SELF-SUBMITTED, so they are the same
        independence group as the community's own site unless you can show
        otherwise.
      - The listing's ARCHIVE HISTORY is the valuable part: the most recent
        year the community appears in any directory is last_listing_year.

2G. CROWDFUNDING PAGES (Kickstarter, GoFundMe, Ulule, Betterplace, national
    platforms). Almost nobody looks at these and they are excellent: a dated
    campaign page describing a specific project, with a budget, a timetable
    and often photographs of the ground before work started.

2H. LINKEDIN, and BOOKING OR HOSTING platforms (Airbnb, retreat and volunteer
    listings). LinkedIn organisation pages carry a founded year. Hosting
    listings often describe the LAND — including its extent — in far more
    detail than the website does, because that is what they are selling.
    Those descriptions are a real source for managed area.

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
more than the entire rest of the website. A grant application is frequently
the best MANAGED AREA source that exists, because the applicant had to
justify the figure to somebody.

--- STAGE 4 — ARCHIVED VERSIONS ---

This is the single best DATING source available.

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

4.3 ARCHIVE THE SOCIAL AND DIRECTORY ADDRESSES TOO. A Facebook or directory
    page that refuses you today may have been archived years ago when it did
    not. An archived directory listing is also how you establish
    last_listing_year.

A dated 2011 snapshot describing work as ALREADY UNDER WAY proves the work
existed by 2011 — rank 2 evidence, obtainable no other way. Record the
earliest snapshot per address and what it says.

4.4 WATCH FOR THE AREA THAT CHANGED. A 2012 snapshot saying "we farm 4
    hectares" and a 2024 page saying "we farm 15 hectares" are not in
    conflict; the community grew. Record the year each figure refers to.

=============================================================
--- STAGE 5 — ACADEMIC LITERATURE  ***HIGHEST PRIORITY*** ---
=============================================================

For any community that HAS been studied, a paper or a thesis is usually the
single best source in existence: dated, independent, and written by someone
who visited the site. This is where RANK 1 onset evidence lives, and it is
also the best source for a MEASURED managed area.

Together with Stage 6 this stage must receive AT LEAST 8 TO 12 PAGES of a
FULL run's budget, and the databases you searched must be reported whether or
not they returned anything.

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
      TESEO and Dialnet (Spain), DiVA (Sweden), Teses USP and BDTD (Brazil).
      If you do not know the country's portal, search "<country> national
      thesis repository" and use what you find.
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
    what this study needs. ONSET DATES AND LAND AREAS LIVE IN THE METHODS AND
    SITE DESCRIPTION SECTIONS. If only the abstract is reachable, record the
    source and mark it ABSTRACT ONLY — do not code a value from an abstract
    unless the abstract itself states it.

5.4 CHAIN THE CITATIONS, BOTH DIRECTIONS.
      BACKWARD: for every relevant paper, read its REFERENCE LIST. This is
        the fastest route to grey literature, because papers cite the reports
        and theses that search engines do not index.
      FORWARD: use "Cited by" to find later work.
    Follow at least one round in each direction for every relevant paper.

5.5 EXPECT TO FIND NOTHING, AND SAY SO. Most intentional communities have NO
    academic literature about them at all. Finding none is the NORMAL and
    CORRECT outcome, and you record it as a negative consultation in H4, with
    the databases named. Read rule 11 below before you write this section.

=============================================================
--- STAGE 6 — GREY LITERATURE  ***HIGHEST PRIORITY*** ---
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
    INDEPENDENT and PUBLIC — which is the definition of rank 1 evidence. A
    grant record also frequently states the AREA the project covered, and
    satisfies channel V2 on its own.
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
    It is also what field G1 external_funding_or_programme records, and a
    funded restoration programme at the site is a MATCHING-EXCLUSION concern
    — so finding one matters twice.

6.2 SEARCH THE OFFICIAL REGISTERS.
      - Company, association and charity registers (founding dates, legal
        form)
      - Land registry and cadastral records where public — these are the best
        MEASURED source for area that exists
      - Municipal planning portals — permits are dated and specific
      - Organic certification bodies' public client lists, with FIRST YEAR
        of certification where shown. A certifier that inspects satisfies
        channel V3.

6.3 USE FILE-TYPE SEARCH. Run: "<community name>" filetype:pdf
    and the same in the local language. This surfaces reports that are on the
    open web but linked from nowhere a crawler would reach.

6.4 LOG WHAT YOU FOUND, BY TYPE, in field H7 — and log what you did NOT find,
    by database, in H4.

--- STAGE 7 — OTHER WEB SOURCES ---

  - Ecovillage and intentional-community directories and network profiles
  - Local and national news, in the local language
  - Documentary descriptions; dated video titles are evidence
  - Any address in the source set you have NOT already crawled under Stage 2.
    Some platforms block automated reading — if you cannot open one, say so
    rather than guessing at its content.

--- STAGE 8 — LOCAL-LANGUAGE SWEEP ---

Repeat the key searches from Stages 5, 6 and 7 in the local language, using
the community's local-language name. Many of these communities publish little
or nothing in English, and national thesis portals and government registers
are almost always local-language only. This stage regularly doubles what you
find, and what it finds is disproportionately dated and independent.

--- STAGE 9 — CROSS-SOURCE RECONCILIATION ---

You now have values from several addresses and they will not all agree. This
stage is what turns a pile of pages into one record.

9.1 EVERY VALUE CARRIES ITS SOURCE. No field is reported without the source
    numbers that support it.

9.2 WHERE SOURCES DISAGREE, DO NOT AVERAGE AND DO NOT PICK QUIETLY.
      - Report both values and say which source gave each.
      - Resolve by EVIDENCE RANK, not by recency and not by which sounded
        more confident. A dated grant record beats a website's round number.
      - If two sources of EQUAL rank disagree on a year, take the EARLIER as
        the value and let the gap become onset_lower_bound and
        onset_upper_bound.
      - Record the disagreement in onset_conflicting_sources whatever you do
        with it.

9.3 COUNT GROUPS, NOT URLS. Before you claim that three independent sources
    agree, check their independence groups. Four addresses belonging to one
    community are ONE voice. A directory listing copied from a website
    corroborates nothing at all.

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

AT LEAST 8 TO 12 OF THOSE PAGES MUST BE SPENT ON STAGES 4, 5 AND 6 COMBINED
— archive, academic and grey. A run that spends its whole budget on the
community's current website has searched the least valuable material
available and has not done the task either, however many pages it opened.

Where a community has several substantive addresses, aim for at least 8 to 12
pages on EACH of them before moving on, rather than 30 on the first and two
on the rest.

Aim for AT LEAST THREE INDEPENDENT GROUPS for every field where three exist —
groups, not URLs.

--- WHEN YOU RUN OUT OF BUDGET ---

You will sometimes be unable to finish. That is expected and it is not a
failure. What IS a failure is finishing anyway by filling the remaining
fields from inference.

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
   silently destroys the study, because nobody can tell which values are
   real.

2. NEVER CITE A URL YOU DID NOT OPEN IN THIS SESSION. Do not reconstruct a
   plausible URL. Do not cite a page you remember from training. Every source
   you list must be one you actually fetched and read in answering THIS
   request.

3. IF A PAGE FAILS TO LOAD, SAY SO. A 404, a paywall, a blocked platform, a
   JavaScript-only site returning nothing — report it as attempted and
   failed.

4. NEVER INFER FROM A SIMILAR COMMUNITY.

5. NEVER GUESS AT A TYPICAL VALUE. "Most communities of this size have around
   40 residents" is fabrication. So is rounding an unknown to a plausible
   number.

6. RECORD DISAGREEMENT, DO NOT RESOLVE IT SILENTLY. If two sources give
   different years, report BOTH and say which came from where.

7. DISTINGUISH "the source says no" FROM "no source says anything". This
   applies hardest to status: a vanished website is status_current =
   unknown, NEVER dissolved. Dissolution requires positive evidence.

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
      - If a database was unreachable, say so rather than reporting zero
        hits.

12. SOCIAL MEDIA AND IMAGERY HAVE THEIR OWN FABRICATION TRAPS. Specifically:
      - NEVER infer a date from a post's position in a feed. Feeds are not
        reliably chronological and pinned posts sit at the top for years.
      - A caption saying "twenty years of farming here" is a RANK 3
        retrospective claim, not a dated record. Code it as rank 3.
      - NEVER describe the contents of a platform you could not open. If
        Instagram or Facebook refused you, write BLOCKED.
      - A PHOTOGRAPH IS NOT AN AREA AND NOT A DATE. An image of green rows
        tells you nothing about how many hectares are worked. A dated
        photograph of a physical structure — a pond, a terrace, a planted
        block — IS a dated record of that structure's existence, and does
        count as V4 visual documentation.
      - A video upload date IS a dated record. A video description's claim
        about the past is not.

13. NEVER ESTIMATE AN AREA FROM IMAGERY. Not from satellite view, not from a
    map, not from a site plan you have not read a figure off, not from an
    impression of how big the place looks. You cannot measure area reliably
    from a view. The study takes that measurement from a controlled drawing
    procedure carried out by the researcher, and a guessed number here would
    silently contradict it. If no source STATES an area, write NOT FOUND and
    set managed_area_basis = not found. That is a complete and correct
    answer.

14. DO NOT REPORT ECOLOGICAL PRACTICES. Do not code, list, infer or
    summarise what farming or land-management practices the community uses,
    and do not add them as context or notes. That block was removed from the
    study deliberately. If a source describes a practice and that description
    also carries a DATE or an AREA, record the date or the area in its proper
    field and cite the source — the dated fact is what the study needs, not
    the practice.

=============================================================
WHAT TO COLLECT
=============================================================

Use exactly these field names.

BLOCK A — IDENTITY
  community_name_official   name the community uses for itself, in its own
                            language
  alternative_names         former names, local names, transliterations.
                            Each one is a separate academic search string
  country
  admin_region              province / state / county
  coordinate_agreement      agrees | differs | no published location
                            (put anything qualifying it in your notes)

BLOCK B — ELIGIBILITY
  e1_network_listing        which networks or directories list it
  e1_pathway                network/directory listing |
                            independent self-identification | both
  e1_self_identification    a published phrase (under 25 words) stating
                            ecological aims
  e2_settlement_type        village-scale permanent residence | retreat
                            centre | campus | business | single household |
                            urban co-housing | unclear
  e2_evidence_note          one line on why
  e8_setting_at_onset       rural | peri-urban | urban | unclear

BLOCK C — ONSET DATING   ***THE PRIORITY BLOCK***
  date_formal_founding      year the community was founded as an entity
  date_land_acquisition     year the land was bought, leased or occupied.
                            This is the hardest LOWER BOUND on onset: a
                            community cannot intervene on land it does not
                            hold
  date_intervention_onset   YEAR THE FIRST DELIBERATE ACTION TO ALTER
                            VEGETATION, SOIL, WATER OR LAND COVER FOR
                            ECOLOGICAL PURPOSES IS DOCUMENTED. This is NOT
                            the founding year. Where work began in different
                            domains in different years, record the EARLIEST
  onset_lower_bound         earliest year it could plausibly be
  onset_upper_bound         latest year it could plausibly be
  onset_evidence_rank       1 | 2 | 3 | 4 | 5   (scale below)
  onset_evidence_description  what the evidence actually is
  onset_conflicting_sources   where sources disagree, what each says, or
                            "none"
  onset_proxy_flag          yes | no — yes if you used a founding year as a
                            substitute
  onset_confidence_tier     A precise | B plus-or-minus 1 year | C uncertain
  onset_first_or_major      first intervention | major new project | unclear
  cohort_candidate          core (2020-2021) | extension (2019) | no |
                            uncertain

  ONSET EVIDENCE RANK SCALE
    1  A dated independent record — permit, GRANT AWARD OR GRANT REPORT,
       project report, registry entry, ACADEMIC PAPER OR THESIS.
                                                        Band 0 to +/-1 year
    2  A dated archived snapshot describing the work as ALREADY UNDER WAY.
       Gives a firm UPPER bound.                        Band +/-1 to +/-3 yr
    3  The community's own dated retrospective statement — a timeline, an
       anniversary account, "we began planting in 1992". Band +/-2 to +/-5
    4  An undated community statement, onset inferred from context.
                                                        Band +/-5 or wider
    5  A directory founding year used as a proxy. NOT AN ONSET. Set
       onset_proxy_flag = yes.

  Almost every rank 1 source comes from Stage 5 or Stage 6. That is why
  those stages are the highest priority in this protocol.

  A community founded in 1985 that began ecological work in 1992 has an onset
  of 1992. If sources of equal rank disagree, take the EARLIER year as the
  value and let the gap between them become the lower and upper bounds.

BLOCK D — EVIDENCE VERIFICATION
  This block records HOW WELL DOCUMENTED the community's ecological work is.
  It does NOT record how much work there is, or how good it is. Do not go
  searching for channels — score them from what the other stages found.

  Two channels are independent only if they do not come from the same
  underlying statement. Two pages of one website = ONE channel. So are a
  website, its own Facebook page and a directory listing copied from it.
  COUNT INDEPENDENCE GROUPS, NEVER ADDRESSES.

  v1_self_documentation     yes/no — community describes SPECIFIC ACTIONS,
                            not aims
  v2_external_documentation yes/no — academic paper, THESIS, project record,
                            certification, GRANT AWARD, or media coverage OF
                            THE WORK.  *** EXTERNAL CHANNEL ***
  v3_substantive_affiliation yes/no — member of a body that ASSESSES
                            practice, not one that merely lists members.
                            Name the body.  *** EXTERNAL CHANNEL ***
  v4_visual_documentation   yes/no — dated photos, site plans, design
                            drawings, maps
  v5_continuity_evidence    yes/no — the work described consistently across
                            years

  DO NOT SUPPLY channel_count OR evidence_tier. The workbook computes both.

BLOCK E — SIZE, LAND, POPULATION   ***managed_area_ha IS A PRIORITY FIELD***
  population_value          PERMANENT RESIDENTS ONLY — not visitors,
                            volunteers or students
  population_lower / population_upper   where a source gives a range
  population_source_date    the year the figure refers to

  managed_area_ha           LAND THE COMMUNITY ACTIVELY WORKS ecologically.
                            The researcher separately draws the community's
                            outline on satellite imagery; your figure is the
                            INDEPENDENT CHECK on that drawing, and the only
                            outside evidence there will ever be. Search for
                            it specifically rather than recording whatever
                            number happens to appear.
  managed_area_lower_ha     lowest plausible figure the sources support
  managed_area_upper_ha     highest plausible figure
  managed_area_basis        measured | stated | inferred | not found
                              measured = someone actually measured it
                                (thesis, survey, land registry, grant
                                application, scaled site plan)
                              stated   = the community gives a figure
                                without saying how it was arrived at
                              inferred = you derived it from something else
                                (number of beds, plots, hectares under a
                                crop) — say how, in documentary_area_note
  managed_area_source_class S1-S8, whichever supplied the figure
  documentary_area_note     anything qualifying the figure: whether it
                            plainly refers to WORKED land or to the whole
                            holding, whether it covers one parcel or several,
                            and the year it refers to. One line.

  total_holding_ha          the whole landholding
  area_type                 actively managed | total holding only |
                            both recorded | not stated
  parcel_structure          contiguous | non-contiguous | unknown
                            — a non-contiguous holding is the legitimate
                            reason a stated area can exceed a drawn one, so
                            this field is worth establishing

  A community holding 200 ha and working 15 ha has managed_area_ha = 15 and
  total_holding_ha = 200. NEVER substitute one for the other — confusing them
  is the commonest error in this block.

  See absolute rule 13: never estimate an area from imagery.

BLOCK F — STATUS AND SURVIVORSHIP
  status_current       active | dormant | transformed | relocated |
                       dissolved | unknown
  status_evidence      what the status rests on
  last_listing_year    most recent year it appears in ANY directory or
                       archive
  dissolution_year     if dissolved, when — else n/a
  delisting_reason     dissolution | relocation | changed network |
                       administrative removal | lost contact | unknown | n/a

  "unknown" is NOT "dissolved". A vanished website is not a vanished
  community. Dissolution requires POSITIVE evidence, recorded in
  status_evidence.

BLOCK G — CONTEXT   (three fields only — do not add more)
  external_funding_or_programme  any documented state, NGO or grant-funded
                       restoration programme at the site, or "none found".
                       This comes mainly from Stage 6, and it matters twice:
                       it is often rank 1 onset evidence AND it is a
                       matching-exclusion concern, because it is a second
                       intervention running in parallel.
  protected_area_status  inside | adjacent | no | unclear
                       A matching-exclusion criterion. Required for CONTROLS
                       as well as settlements.
  notable_context      war, drought, land dispute, major fire or relocation
                       AFFECTING LAND COVER BETWEEN 2019 AND 2025, or "none
                       found". This is not a general history field.

BLOCK H — PROVENANCE
  source_set_supplied  every address I gave you: url | platform type |
                       independence group | crawl status | pages opened.
                       One line each. An address I supplied and you did not
                       open must appear here as "not attempted".
  source_set_discovered  every address you FOUND that I did not give you, in
                       the same format. Old domains especially — they hold
                       the oldest material and are the best dating source on
                       the open web.
  independence_groups  how many distinct groups the sources fall into. This
                       is normally far smaller than the number of URLs.
  stages_completed     which of stages 0-9 you finished, which you cut short,
                       and which you never reached
  crawl_truncated      yes | no — did you stop before finishing the protocol?
  pages_opened_count   distinct URLs you OPENED, including those yielding
                       nothing
  documents_opened     PDFs, spreadsheets and other files opened, by title
  academic_search_log  WHICH DATABASES you searched, how many hits each
                       returned, and how many you opened in FULL TEXT versus
                       abstract only
  grey_literature_log  grey sources found, BY TYPE — thesis | grant record |
                       NGO report | government report | conference paper |
                       certification audit | planning permit | other
  source_classes_found which of S1-S8 you located
  search_languages     which languages you searched in
  negative_consultations  source classes and DATABASES checked and found
                       empty, e.g. "S1: none found in Google Scholar, SciELO,
                       OATD, DART-Europe, national portal. S2: none found in
                       CORDIS, LIFE."

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
         pages spent on Stages 4-6: <n>       <- must be at least 8
  STAGES: completed <list>  |  cut short <list>  |  not reached <list>
         crawl_truncated: yes/no
  ACADEMIC: databases searched <list> | hits <n> | full text opened <n> |
         abstract only <n> | citation chains followed <n>
  GREY: <n> items — <types found, or "none found">

  -- BLOCK A --
  field_name = value   [src 1,4]
  ...
  (repeat for blocks B to H)

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

**A chat assistant is not literally a crawler**, and no prompt makes it one. It fetches pages one at a time, has a budget of tool calls per response, and will sometimes stop earlier than you want. Expect **25 to 40 pages on a good FULL run**.

**What version 3.0 changes is where those pages go, not how many there are.** Three things:

- **Fewer fields, deeper on each.** The register asks for 61 fields instead of 88, and the fourteen it dropped were spread across every source the community publishes. That reading time returns to the five fields that carry analyses.
- **A floor on Stages 4–6.** The archive, academic and grey stages must receive at least 8 to 12 pages. Version 2.4 named them as important and then let the budget be consumed before the run reached them. A `sitemap.xml`, an RSS feed and a CDX index query each cost one fetch and can return hundreds of URLs.
- **The shortfall stays visible.** `crawl_truncated` and `stages_completed` convert a silent half-search into a recorded one, which is the difference between a gap you can fix and a gap you never see.

## Which communities deserve extra runs, and what it costs

**One run per community.** 212 communities. At roughly **6 to 9 minutes** each including your own reading and pasting — down from 8 to 12 in v2.4, because there are no longer thirteen practice codes to assess and no per-practice evidence rows to write — that is **21 to 32 hours**.

**The tiered version, which is what I would do.** Give every community one FULL run. Then add runs only where a second pass could change an analysis:

| Extra run | Which communities | Roughly |
|---|---|---|
| `RUN: ACADEMIC` | **Now the highest-value extra run**, because rank-1 onset evidence and measured areas both live there. Any community that looks likely to have been studied — large, old, well known, near a university — plus every one where evidence tier came back C or Fail | ~60–70 communities |
| `RUN: SOURCE` on each substantive extra address | Those where FULL reported `crawl_truncated = yes`, or reported an address as `not attempted`, **and** the community has more than one substantive address. Former domains are dating evidence, so this keeps its value | ~60–70 communities |
| `RUN: SOURCE` plus `RUN: ACADEMIC` regardless | **Every cohort candidate.** The longitudinal analysis admits only confidence tier A or B, and decision D4 turns on how many core candidates reach that bar. An hour spent here changes whether the component survives | ~65 communities |
| `RUN: RECONCILE` | Every community split across more than one run — mandatory, never optional | as many as were split |

That comes to roughly **330–380 runs**, or **38 to 58 hours** — about **17 to 26 hours more** than single-pass, for most of the available benefit. **Spend it on the cohort first**, and on onset before anything else.

**One thing not to economise on.** If a community was split across several runs, it must get a `RECONCILE` run. Several partial records with no merge is worse than one thin record, because it looks complete when read one piece at a time.

## How to check the output

**Verify 20 communities yourself, chosen at random.** Open the cited URLs and confirm each field. This *is* the double-coding exercise the plan requires, and it produces the reliability statistics the methods chapter needs.

**Check every academic citation individually.** This is not the same as checking a website link. A fabricated paper is the most damaging error possible here, because it looks like your strongest evidence. For every S1 source: does the DOI resolve? Does the repository record exist? Does the named author have that publication? If any answer is no, discard the whole record for that community and re-code from scratch. Record the check as `verified_resolves` in `Source_Index`.

**Check the pages spent on Stages 4–6.** This is the new number to watch. A run reporting 35 pages opened and 2 on the archive, academic and grey stages has searched the least valuable material available.

**Check the source set table against what you supplied.** Every address you listed must appear with a status. An address that has silently vanished from the output was not crawled, whatever the rest of the response implies.

**Check the independence groups, not just the source count.** If a community reports eight sources in one group, it has one source. This is the single easiest place for a thin record to look thorough.

**Check that nothing came back about practices.** If a record contains practice descriptions, notes about farming methods, or a helpfully reconstructed Block F, discard those parts. They have no destination in the workbook and no consumer in the study, and letting them accumulate in a notes field rebuilds by the back door the variable that was removed on purpose.

**A useful spot-check on effort.** Compare `pages_opened_count` against the sources list. If it opened 30 and cites 4, that is normal — real crawls have a low hit rate. If it claims 30 and lists 30 that all yielded data, be suspicious.

**Expect most academic searches to return nothing.** If the assistant reports finding papers for most of your 212 communities, something is wrong. In this population a handful are well studied and the large majority have never been written about at all.

**Expect `crawl_truncated = yes` reasonably often.** If it never appears across 212 communities, that is not good news — it means the field is not being used, and truncation is being hidden rather than avoided.

## Three things to track as you go

**Block C will succeed unevenly.** Rank 1 and 2 evidence exists for perhaps a third of communities — and Stages 5 and 6 are what raise that fraction, which is why v3.0 puts a floor under them. For the rest expect rank 3 or 4 with wide bands. That is a real result, and it is why the plan propagates onset uncertainty by multiple imputation rather than pretending to a precise year.

**Keep a running tally of `cohort_candidate = core`.** The longitudinal cohort needs about 65 communities with onset in 2020–2021. At community 100, count the core candidates **at confidence tier A or B** — above 50 proceed; 40–50 proceed but report as exploratory; below 40, drop the component. `Cohort_Tracker` in the workbook computes this for you.

**Keep a tally of `evidence_tier`.** It is now a sample-description variable and the basis of a sensitivity check, so its distribution is reported. If almost every community comes back tier C, that is a finding about the population — the movement documents itself and is documented by almost nobody else — and it should be stated rather than buried. It is also the signal that `RUN: ACADEMIC` is worth running more widely.

**Keep a tally of `crawl_truncated = yes`.** If it climbs past about a fifth of the sample, the single-run mode is not doing the job for your population and the tiered plan above needs to become the default rather than the exception.
