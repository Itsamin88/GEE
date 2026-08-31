# Change matrix — v3.8 / v6 / v2.4  →  v4.0 / v1 / v3.0

Every deletion, rename, retention and rebuild across the three artifacts. Read with `DEPENDENCY_AUDIT.md` (what depended on what) and `DECISION_MEMO.md` (why).

**Convention.** *Deleted* = gone with no successor. *Merged* = its content now lives in another field. *Derived* = still exists but is computed, never entered. *Re-scoped* = same name, narrower or different job. *Renamed* = same job, better name.

---

## 1. Documentary fields

### 1.1 Deleted — the practice block (14 fields)

| Field | Was | Why deleted |
|---|---|---|
| `pc01_rainwater` | Block F1 | The whole block fed analysis A6 only. A6 is deleted (`DECISION_MEMO.md` §1) |
| `pc02_swales` | F2 | as above; also fed SC15's second comparison, which is deleted with it |
| `pc03_irrigation` | F3 | as above. SC7 restricts on the satellite water-subsidy flag, never on this claim, so nothing else is lost |
| `pc04_no_till` | F4 | as above |
| `pc05_mulching` | F5 | as above |
| `pc06_cover_crop` | F6 | as above |
| `pc07_tree_planting` | F7 | as above |
| `pc08_agroforestry` | F8 | as above |
| `pc09_polyculture` | F9 | as above |
| `pc10_hedgerows` | F10 | as above |
| `pc11_small_parcel` | F11 | as above |
| `pc12_organic` | F12 | as above. It had no predicted signature even in v3.8 and was descriptive only |
| `pc13_restoration` | F13 | as above |
| `practice_evidence_notes` | F14 | The prose supporting a code that no longer exists |

### 1.2 Deleted — fields that failed the downstream-consumer test (7)

The test: *what downstream decision or analysis changes because of this field?*

| Field | Was | Answer to the test |
|---|---|---|
| `date_first_residence` | C3 | Nothing. Unlike founding and land acquisition it bounds the onset in neither direction: intervention can precede first residence by years or follow it by decades |
| `domain_onsets` | C13 | Nothing. Its value was a per-domain onset; with no per-domain analysis remaining, only the earliest year is needed and that is recorded directly |
| `tenure_type` | E7 | Nothing. The anonymisation rule for published outputs is unconditional, so tenure changes no decision |
| `first_listing_year` | G3 | Nothing. Community age comes from onset, and the attrition estimate operates on directory snapshots rather than per-community listing years |
| `movement_tradition` | H1 | Nothing — not a moderator, covariate, matching variable or table entry. It is also a self-description, and admitting self-descriptions as predictors is the failure that removed the practice codes |
| `education_volunteer_program` | H3 | Nothing |
| `agricultural_orientation` | H4 | Nothing. Interpretively adjacent to the provisioning outcome, but no declared analysis uses it, and it is a self-description |

### 1.3 Merged — duplicate entry points (2)

| Field | Merged into | Why |
|---|---|---|
| `e3_population_value` (B6) | `population_value` (E1) | The same quantity was collected twice, in two blocks, landing in two workbook columns. Two authoritative entry points for one number is a guaranteed drift |
| `e5_active_currently` (B7) | `status_current` (F1) | Duplicate at lower resolution: a four-level yes/probably/unclear/no against a six-level scale with an evidence field behind it. Eligibility criterion E5 now reads `status_current` |

### 1.4 Made derived — no longer collected (4)

| Field | Now computed from | Why |
|---|---|---|
| `channel_count` | `COUNTIF(v1..v5, "yes")` | It was typed in v6 and could disagree with the five channels behind it |
| `activity_tier` → `evidence_tier` | the channels, by the rebuilt ladder | same, plus the ladder itself was defective (§4.2) |
| `founding_decade` | `FLOOR(date_formal_founding, 10)` | A pure function of a field already collected |
| `onset_band_width_years` | `upper − lower` | Already derived in v6; retained as such |

### 1.5 Renamed (4)

| Was | Now | Why |
|---|---|---|
| `activity_tier` | `evidence_tier` | The old name asserted what the variable measures — activity — and it does not. It measures documentation. See §4.2 |
| `language` (on `O6_Source_Index`) | `source_language` | Three columns named `language` meant three different things |
| `language` (on `O11_Source_Set`) | `address_language` | as above |
| `language` (on `O7_Search_Log`) | `search_language` | as above |

### 1.6 Re-scoped — same name, different job (3)

| Field | v3.8 role | v4.0 role |
|---|---|---|
| `managed_area_ha` | Corroborated the polygon **and** was named as a fallback predictor in A9 | Corroboration only. It sets no geometry and predicts nothing. Feeds `area_ratio` → `area_agreement_tier` → SC16 and table T10 |
| `notable_context` | "War, drought, land dispute, fire, relocation" — open-ended | Narrowed to events affecting **land cover inside the study window**, so it does not become a general history field |
| `parcel_structure` | Descriptive | Load-bearing: it is what separates a legitimate non-contiguous holding from a total-holding confusion when the drawn and stated areas disagree |

### 1.7 Retained unchanged (44)

Blocks A (5), B1–B5 and B8→B6 (6), C1–C2, C4–C12 (11 of 12), D1–D5 (5), E1–E6, E8–E13 (12 of 13), F1–F2, F4–F5 (4 of 5), G1–G3 (3 of 3, one narrowed), H1–H12 (12).

### 1.8 Field count

| | v2.4 | v3.0 | Change |
|---|---|---|---|
| Blocks | 9 | 8 | Block F deleted; G→F, H→G, I→H |
| A identity | 5 | 5 | — |
| B eligibility | 8 | 6 | −2 (both duplicates) |
| C onset | 14 | 12 | −2 |
| D activity → evidence verification | 7 | 5 | −2 (both now derived) |
| E size and land | 15 | 13 | −2 |
| F practice codes | 14 | — | **−14** |
| G → F status | 6 | 5 | −1 |
| H → G context | 7 | 3 | −4 (one now derived, three no consumer) |
| I → H provenance | 12 | 12 | — |
| **Total** | **88** | **61** | **−27** |

---

## 2. Analyses, hypotheses and reporting identifiers

### 2.1 Deleted analyses

| Item | Action |
|---|---|
| A6 — within-settlement claims-versus-delivery comparison | **DELETED** with its sample definition, prevalence rule (25–75%), two-comparison reporting rule, nested FDR family and detectable-difference row (0.39 SD) |
| H6 — "communities claiming a practice show the signature that practice predicts" | **DELETED** |
| O5 — the corresponding objective | **DELETED** |
| SC15's second comparison — PC02 claimants vs non-claimants | **DELETED**. The check itself survives on its first comparison |

### 2.2 Changed analyses

| Analysis | Change |
|---|---|
| A1, A2 | Outcome geometry restated as the polygon; v3.8 still described a 150 m circle in §1.2, §8.4 and the glossary |
| A4 | Confounder `activity_tier` → `evidence_tier`, with the reason stated (documentation quality proxies organisational capacity, the named unmeasured confounder). Proxy-onset exclusion made explicit |
| A5 | MDS corrected from six metrics to seven. "Also report the six metrics individually" → seven. Justification rewritten so it describes non-inheritable *states* rather than naming practices |
| A8 (was A9) | Reduced-n figures for uncoded managed area removed — every site has a polygon. Predictor stated once as `log POLYGON_AREA`; v3.8's Appendix B.8 gave `log MANAGED_AREA`, contradicting B.7 |
| SC1 | Alternative geometry changed from the superseded size-class circle to an **equal-area circle**. Because area is held constant, SC1 now isolates *shape*, which is what hand-drawing risks. A fourth Earth Engine export supplies it |
| SC7 | Note added that it restricts on the satellite flag, never on a documentary irrigation claim |
| SC14 | "Management" narrowed to water retention as a mechanism, not a named practice |
| SC15 | Re-scoped to one comparison; interpretation narrowed; the loss stated in the limitations |

### 2.3 New

| Item | What it is |
|---|---|
| **SC18 — independent-documentation restriction** | Re-runs A1, A2 and A5 restricted to communities with at least one external evidence channel. Partially replaces what A6 was reaching for — is the ecological activity real? — without asking the documentary record a question it cannot answer. Four possible outcomes are declared in advance, including "too few communities qualify", which is itself a finding about the population |

### 2.4 Renumbering

| Kind | v3.8 | v4.0 |
|---|---|---|
| Hypotheses | H1–H9, one deleted | H1–H8, contiguous |
| Analyses | A1–A9, one deleted | A1–A8, contiguous |
| Objectives | O1–O9, one deleted | O1–O8, contiguous |
| Sensitivity checks | SC1–SC17 | SC1–SC18 (none renumbered; SC18 added) |
| Placebo tests | PL1–PL3 | unchanged |
| Tables | T1–T12 plus T8a, T8b, T8c — 15 items with suffixes, listed out of order | T1–T15, contiguous, in reporting order |
| Figures | F0–F9 plus F2a, F6a, F7a, F8a — 14 items with suffixes | F1–F14, contiguous, in reporting order |

Full old→new mapping in the plan's Appendix D. The rationale for renumbering rather than leaving gaps is in the plan §1.4: nothing external depends on the old identifiers (no coding begun, no analysis table, no deposited preregistration), and a gap invites the reading that something was dropped after results were seen.

### 2.5 Multiplicity

| | v3.8 | v4.0 |
|---|---|---|
| Primary, uncorrected | H1, H2 | H1, H2 |
| FDR family | H3–H9 — **seven** members | H3–H8 — **six** members |
| Nested FDR family | inside A6, across tested practice codes | **none** |
| Multiplicity structures | 2 | 1 |

The plan states the consequence rather than leaving it to be noticed: one fewer member makes the adjustment marginally less severe. It also declares, before any result exists, why the cohort analysis stays inside the family despite sitting on a disjoint sample.

---

## 3. Workbook

### 3.1 Sheets removed (3)

| Sheet | Successor |
|---|---|
| `O2_Practice_Matrix` | none |
| `O2b_Practice_Evidence` | none |
| `O9_Claim_Signature_Map` | none |

### 3.2 Sheets replaced (1)

| Was | Now | Why |
|---|---|---|
| `R1_Codebook` — **13 rows**, one per practice code, with inclusion/exclusion examples, thresholds and a freeze control | `Definitions_And_Freeze` — **17 rows**, the same structure for the judgement-bearing variables that remain: onset and its rank, tier and proxy flag; cohort candidacy; settlement type; setting at onset; managed area and its basis; population; the five evidence channels; status; polygon confidence | The freeze discipline is worth keeping even though the thing it was freezing is gone. The variables that need definitions and worked examples are now the ones where two careful readers of the same page could differ |

### 3.3 Sheets renamed and rebuilt (11)

Column counts are of the contiguous data block from column A; each sheet also carries an explanatory note placed past a deliberate empty column, which is not a data column.

| v6 | v1 | Data columns | Substantive change |
|---|---|---|---|
| `O1_Community_Attributes` | `Community_Register` | 66 → **55** | Practice-adjacent and no-consumer fields removed; two duplicates merged; `channel_count` and `evidence_tier` made formulas |
| `O3_Onset_Register` | `Onset_Register` | 22 → **21** | Two fields deleted, one added back as a derived `founding_decade`; `community_name` made a lookup rather than typed |
| `O10_Polygon_And_Area` | `Polygon_Geometry` | 26 → **23** | Six mirrored documentary columns cut to two read-only lookups; `equal_area_circle_radius_m` added for SC1; empty-lookup bug fixed |
| `O6_Source_Index` | `Source_Index` | 17 → 17 | `language` → `source_language` |
| `O11_Source_Set` | `Source_Set` | 17 → 17 | `language` → `address_language` |
| `O7_Search_Log` | `Search_Log` | 12 → 12 | `language` → `search_language` |
| `O5_Disagreement_Log` | `Disagreement_Log` | 14 → 14 | `codebook_amended` → `definitions_amended` |
| `O4_Reliability_Report` | `Reliability_Report` | 16 → 16 | **Rows, not columns, are what changed: 12 pre-filled rows covering 24 variables → 14 rows, one per variable.** The single row reading "practice codes (each of THIRTEEN, reported separately)" is deleted; `activity_tier` renamed; `managed_area_basis` and `e2_settlement_type` added |
| `O8_Enquiry_Record` | `Enquiry_Record` | 19 → 19 | Unchanged in substance |
| `R2_Calibration` | `Calibration` | 12 → 12 | `date` → `calibration_date` |
| `R3_Decision_Log` | `Decision_Log` | 12 → 12 | Unchanged in substance |

Only three sheets change column count. The saving is concentrated in `Community_Register` (eleven fields) and `Polygon_Geometry` (four mirrored columns), and in the three sheets that disappear entirely.

### 3.4 Sheets carried forward (3)

`README`, `Cohort_Tracker`, `Reference_Codes` — all rewritten for content, all retained in role. `Reference_Codes` loses the practice-coding-levels block and the practice section of the "what not to search for" list, and gains the three-search-outcomes block.

### 3.5 Sheet count

18 → **15**.

### 3.6 New formulas

| Field | Formula | Replaces |
|---|---|---|
| `channel_count` | `COUNTIF(v1:v5,"yes")` | a typed cell |
| `evidence_tier` | independence-first ladder | a typed cell |
| `founding_decade` | `FLOOR(date_formal_founding,10)` | a collected field |
| `equal_area_circle_radius_m` | `ROUND(SQRT(area*10000/PI()),1)` | new; SC1 needs it |
| `community_name` on two sheets | guarded lookup | a typed cell on each |
| `documentary_managed_area_ha`, `documentary_area_basis` | guarded lookups | six mirrored columns in v6 |

---

## 4. Defects found and fixed while rebuilding

### 4.1 In the plan (v3.8)

| # | Defect | Fix |
|---|---|---|
| 1 | MDS defined as **six** metrics in §3.2, §3.8 and §8.7, and **seven** in §3.8's class table, §6.5 and Appendix B.3 | Seven, everywhere |
| 2 | Expected panel size given as 105,182 in §4.4, as an arithmetic totalling **113,286** in §5.7 (double-counting the cohort at two zone counts), and as "about 59,000" in Stage 4 | Derived once in §4.4; §5.7 and Stage 4 quote it. SC1's export is a separate table with its own total of 8,276 |
| 3 | Two coexisting `size_class` definitions (5-level r75–r300 vs 4-level small/medium/large/unknown); `size_class_confidence` duplicating `area_agreement_tier`; Appendix B.8 headed "Contour alignment" but containing size-class arithmetic; B.8 and B.9 sharing a heading; A9 specified over `log MANAGED_AREA` in B.8 and `log POLYGON_AREA` in B.7 | Both size-class variables deleted. One `reference_circle`, one `area_agreement_tier`. Appendix B rebuilt with each formula under one heading |
| 4 | Primary zone described as a 150 m circle in §1.2, §4.3's callout, §8.4 and the glossary — including an instruction to "use 150 m everywhere, for every site class" that contradicts the five-radius rule on the preceding page | The polygon, everywhere. The contradictory callout replaced by the five-radius justification |
| 5 | §4.3: "For medium-class sites [the common circle] coincides with the primary zone and only one copy is written" — a leftover from when the primary zone was a circle | Removed. A polygon is never a circle, so seven geometries are always written |
| 6 | §11.1 timeline: "Three reference pools, each extracted at three radii" | Five radii |
| 7 | §4.6: a paragraph calling managed area "deliberately demoted… an ordinary descriptive variable" directly above a row calling it load-bearing | Removed; the role is stated once |
| 8 | §8.12: A9 detectable difference degraded "where managed area is uncoded" (0.50 SD at n=170, 0.53 at n=148), contradicting §8.11's "every site has a polygon, so nothing is excluded" | Removed; n = 212 |
| 9 | §2.1: "Fourteen sheets" — the workbook had eighteen | Superseded; the new workbook has fifteen |
| 10 | §0.4 said "Sixteen checks in total" while Part 9 said seventeen | Eighteen, stated consistently |

### 4.2 In the workbook (v6)

| # | Defect | Fix |
|---|---|---|
| 1 | `channel_count` and `activity_tier` were **typed**, so they could disagree with the channels behind them | Both are formulas |
| 2 | **The evidence tier's tier C was unreachable.** v2.4's rule: A = ≥3 incl. ≥1 external; B = 2 with visual or continuity; C = 2 community-originated; Fail = <2. The only channel that is neither external nor visual nor continuity is V1, and no community can have two of V1 — so every two-channel community falls to B and C never occurs. The ladder also ordered by count before independence, ranking three self-documented channels above two including a thesis | Ladder rebuilt to order by independence first: Fail if <2; A if external and ≥3; B if external and =2; C otherwise. Every tier reachable, ordering monotone in the thing measured. Verified by evaluation: all four tiers produced from test data |
| 3 | Three columns named `language`, meaning the language of a source, of an address, and of a search | Renamed apart |
| 4 | Bidirectional mirroring: `O1!U` read from `O10!C`, and `O10!M–R` read back from `O1!V–Z, BK` | One direction only. `Polygon_Geometry` reads `Community_Register`; nothing reads back |
| 5 | **Unguarded lookup** (introduced in the rebuild, caught by testing): `INDEX` over an empty cell returns `0`, not blank, so a site with **no** documentary area got `area_ratio = 0` and `area_agreement_tier = C` — "the two disagree by more than a factor of two" — when there is no figure to disagree with. The plan requires tier B | Inner `IF(INDEX(...)="","",INDEX(...))` guard. Verified: a site with no figure now returns blank ratio and tier B |

### 4.3 In the register (v2.4)

| # | Defect | Fix |
|---|---|---|
| 1 | `e3_population_value` and `population_value` collected the same quantity in two blocks | One field |
| 2 | `e5_active_currently` duplicated `status_current` at lower resolution | One field |
| 3 | `channel_count` and `activity_tier` were requested from the search assistant, though they are functions of V1–V5 | No longer requested |
| 4 | Block C's table did not carry the plan's "NOT the founding year" phrasing, though the plan and workbook both use it | Added |
| 5 | Stages 5 and 6 named as "do not skip" with no budget floor, so the practice sweep consumed the budget before the run reached them | Mandatory floor of 8–12 pages on Stages 4–6, reported in the output format |

---

## 5. Cross-reference changes

| Reference | v3.8 | v4.0 |
|---|---|---|
| §7.1a "Drawing the polygons" | §7.1a | §7.1 |
| Stage 1 title | "Documentary coding" | "Essential documentary coding and measurement geometry" |
| A6 → SC15's second comparison | live | both gone |
| §3.6 mediators | MED1 practices, MED2 land cover | MED1 land cover only |
| §5.9 missing-data | included a practice-code rule | rule removed; two new rules added for the documentary area and the evidence tier |
| §10.4 per-community context | included "the thirteen practice codes" | removed, nothing added; a geometry group added |
| §11.2 risk register | "code the thirteen practices for a random 120 communities" as the coding-overrun contingency | Contingency removed and its absence stated: onset, population and eligibility are needed for every community and none can be sampled |
| §11.3 decision D2 | "Keep managed area as a variable?" | "How much documentary corroboration of the polygon is enough?" — the old question no longer arises |
| Decisions D1/D3/D4 | D1, D2, D4, D3 in that order | D1, D2, D3, D4 with the two Stage 1 decisions adjacent |
| Appendix B headings | B.8 and B.9 both "Contour alignment (SC15)" | B.7 geometry, B.8 size gradient, B.9 contour alignment; a new B.13 for the evidence tier and B.15 for the panel size |
| Glossary | 54 entries, incl. size class and documentary managed area as a class route | 56 entries. Superseded entries removed; new entries for management-consistent, external channel, equal-area circle, onset proxy, crawl truncation and the evidence tier; "practice code" retained as a historical entry recording the removal |

---

## 6. Effort consequences

| | v3.8 | v4.0 | Basis |
|---|---|---|---|
| Register fields per community | 88 | 61 | counted |
| Documentary coding | 8–12 weeks | 5–8 weeks | fewer fields; no thirteen-code assessment; no per-practice evidence row |
| Search time per community, single run | 8–12 min | 6–9 min | v2.4 Part C timings adjusted for the removed block |
| Reliability variables to double-code | 24 | 14 | counted |
| Polygon drawing | 60–90 h | 60–90 h | **unchanged** — now the largest manual cost |
| Stage 1 total | 11–15 weeks | 8–11 weeks | sum of the above |
| Study total | 9–12 months | 8–11 months | sum |

The plan states these are planning estimates derived from field counts and per-community timings, not measurements, and instructs recording the actual rate once fifty communities are coded.
