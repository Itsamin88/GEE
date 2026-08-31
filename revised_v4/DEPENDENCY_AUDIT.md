# Dependency audit — practice codes across Study 1

Every component of the v3.8 system, its dependency on documentary practice codes, and what happens to it. Compiled by reading all three source artifacts in full, then searching them for the practice-related term set and tracing each occurrence to what consumes it.

**Files audited** (all preserved unmodified in `originals/`):

| File | What it is | Size audited |
|---|---|---|
| `THE_SIMPLIFIED_PLAN_v3.8.docx` | The master specification | 878 paragraphs and 121 tables, extracting to 266,315 characters |
| `Stage_1_Documentary_Coding_Workbook_v6.xlsx` | The operational workbook | 18 sheets, all cells, formulas, dropdowns, defined names and raw XML |
| `WEB_SEARCH_FIELD_REGISTER_AND_CHATGPT_PROMPT_v2_4.md` | The documentary collection architecture | 1,397 lines, 88 fields in 9 blocks |

**Repository inventory (Step 0).** The git repository at `/home/user/GEE` contained only `README.md` (one line) and `LICENSE` at the time of the audit. There is no code, no schema, no notes file and no prior specification in the repository. The three uploaded files are therefore the complete authoritative input set, and no undocumented file was relied on. They have been copied into `originals/` so the repository now carries them.

---

## 1. Occurrence counts before the refactor

Raw counts of the search terms across the three v3.8-era artifacts.

| Term | Plan v3.8 | Register v2.4 | Workbook v6 |
|---|---|---|---|
| `practice` (any case) | 40 | 16 | present on 4 sheets |
| `PC01`…`PC13` / `pc01`…`pc13` | 27 | 29 | 13 columns + 13 codebook rows + 13 map rows |
| `H6` | 5 | 2 | — |
| `A6` | 9 | — | — |
| `claims-versus-delivery` | 3 | — | — |
| `claimed` / `evidenced` / `documented` / `explicitly absent` / `not mentioned` | 11 | 17 | 3 dropdowns |
| practice-named terms (swales, no-till, mulching, agroforestry, polyculture, hedgerows, small-parcel, organic, restoration, rainwater, irrigation, cover cropping, tree planting) | 60 | 32 | 13 codebook definitions with inclusion/exclusion examples |
| `activity_tier` / activity tier | 7 | 3 | 2 columns + 1 reliability row |
| `FDR` / false discovery | 1 | — | — |

---

## 2. Component-level dependency table

`Direct` = consumes a practice code as an input. `Indirect` = its justification or its reporting refers to practices without consuming one. `None` = no path to a practice code exists.

### 2.1 Hypotheses and analyses

| Component | Practice dependency | Status after removal | Action taken |
|---|---|---|---|
| H1 / A1 — matched contrast on condition | none | RETAINED | Outcome geometry restated as the polygon (a v3.8 inconsistency, not a practice issue) |
| H2 / A2 — provisioning equivalence | none | RETAINED | Same geometry correction |
| H3 / A3 — radial gradient | none | RETAINED | none |
| H4 / A4 — age gradient | none | RETAINED | Confounder list updated: `activity_tier` → `evidence_tier`; proxy-onset exclusion made explicit |
| H5 / A5 — management-diagnostic contrast | **indirect only** | RETAINED, justification rewritten | The MDS is seven satellite metrics; its site-selection argument is physical, not documentary. But its prose named practices ("a parcel already never ploughed"), which reads as practice identification. Rewritten to describe non-inheritable *states* without naming the decision that produced them |
| H6 / A6 — claims versus delivery | **DIRECT — its entire input** | **DELETED** | Hypothesis, analysis, objective O5, detectable-difference row, prevalence rule, two-comparison reporting rule and nested FDR family all removed |
| H7 / A7 → H6 / A6 — density comparison | none | RETAINED, renumbered | none |
| H8 / A8 → H7 / A7 — pre-onset DiD | none | RETAINED, renumbered | none |
| H9 / A9 → H8 / A8 — size gradient | none | RETAINED, renumbered | Reduced-n figures for "uncoded managed area" removed — every site has a polygon, so the attrition never applies |

### 2.2 Measured quantities

| Component | Practice dependency | Status | Action |
|---|---|---|---|
| VCI, VCI-P/S/T/C | none | RETAINED | none |
| PCI | none | RETAINED | none |
| **MDS** | **indirect (justification only)** | RETAINED | Corrected from six metrics to seven; justification rewritten per §2.1 above; a new interpretive rule states what an M-class result does and does not support |
| LCC | none | RETAINED | none |
| VM1–VM14, PM1–PM3 | none | RETAINED | none |
| **CA — contour alignment** | **partial** | RETAINED | The metric is SRTM aspect × land-cover boundary orientation; no documentary input. Only its *use* in the PC02 comparison was practice-dependent |
| FC1–FC4, both flags | none | RETAINED | none |
| The site typology | none | RETAINED | A new callout states that a typology label characterises the LAND, not the community — needed because with practices gone the typology becomes the most concrete per-community statement and will be over-read if the wording allows |

### 2.3 Design components

| Component | Practice dependency | Status | Action |
|---|---|---|---|
| Polygon geometry (§7.1a) | none | RETAINED | none |
| Translated control polygons | none | RETAINED | none |
| Reference pools, five radii, pooling ladder | none | RETAINED | Pooling rung now recorded per stratum **and per radius** — the 30-site floor applies independently at each |
| Stage 2 matching and the distance ladder | none | RETAINED | none |
| Longitudinal cohort | none | RETAINED | none |
| Earth Engine extraction | none | RETAINED | Fourth export added for SC1's equal-area circles; the "for medium-class sites only one copy is written" clause deleted as a leftover from the pre-polygon design |
| Data preparation DP1–DP12 | **one rule only** | RETAINED | The DP11 rule "a practice code not codeable excludes that community from A6 for that code only" is deleted with A6 |
| Index validation (§6.7) | none | RETAINED | A note added confirming the validation landscapes never used practice codes |
| Per-community shrinkage | none | RETAINED | none |

### 2.4 Sensitivity and placebo checks

| Check | Practice dependency | Status | Action |
|---|---|---|---|
| SC1 circle-instead-of-polygon | none | RETAINED, **re-scoped** | Alternative geometry changed from the superseded size-class circle to an **equal-area** circle, so the check isolates shape with area held constant |
| SC2, SC3, SC4, SC5, SC6, SC8, SC9, SC10, SC11, SC12, SC13, SC16, SC17 | none | RETAINED | none |
| SC7 rain-fed subset | none | RETAINED | Restricts on the satellite water-subsidy flag, never on a documentary irrigation claim. A note now says so, because `pc03_irrigation` predicted the same flag and the two could be confused |
| SC14 drought-year interaction | none | RETAINED | Prose narrowed: "management" means water retention as a *mechanism*, not any named practice |
| **SC15 contour alignment** | **PARTIAL — one of two comparisons** | RETAINED, **re-scoped** | Comparison 1 (settlement vs control, sloping sites) survives entirely. Comparison 2 (PC02 claimants vs non-claimants) **deleted**. Interpretation narrowed, and the loss stated in the limitations rather than glossed |
| SC18 | — | **NEW** | Independent-documentation restriction; partially replaces what A6 was reaching for |
| PL1, PL2, PL3 | none | RETAINED | PL1 gains a note that all four quartet members share one polygon shape, so the test is clean of geometry artefacts |

### 2.5 Variables and registers

| Component | Practice dependency | Status | Action |
|---|---|---|---|
| PC01–PC13 in the independent-variable register | **direct** | **DELETED** | 13 variables removed |
| MED1 practice adoption (mediator) | **direct** | **DELETED** | MED2 land-cover composition is renumbered MED1 and becomes the single candidate mediator |
| The causal diagram (§3.9) | **indirect** | RETAINED, one node redrawn | Adjustment logic unchanged — practices were never adjusted for, being on the causal path. The practices node is now drawn as **UNMEASURED** |
| `activity_tier` | none | RETAINED, **renamed and redefined** | → `evidence_tier`. Reframed as an evidence-quality variable with three named uses and one prohibition; tier ladder rebuilt (v2.4's tier C was unreachable) |
| `MANAGED_AREA` | none | RETAINED, **re-scoped** | Corroboration only. Sets no geometry, predicts nothing |
| `SIZE_CLASS` (two coexisting definitions) | none | **DELETED** | Deduplicated to `reference_circle` |
| `SIZE_CLASS_CONFIDENCE` | none | **DELETED** | Duplicated `area_agreement_tier` |
| Language rules (§10.2) | **indirect** | RETAINED, extended | Two rules added: do not name practices, and do not substitute a movement label for a practice name |
| Limitations (§10.3) | **indirect** | REWRITTEN | The "practice codes measure documentation" limitation is replaced by six new ones stating that the study makes no practice-level claim at all |

### 2.6 Stage 1, the workbook and the register

| Component | Practice dependency | Status | Action |
|---|---|---|---|
| Stage 1 as a stage | **mixed** | **REDESIGNED**, not deleted | Renamed *Essential documentary coding and measurement geometry*. Its two load-bearing halves — onset dating and the polygon — have no practice dependency |
| `O2_Practice_Matrix` | direct | **DELETED** | No successor |
| `O2b_Practice_Evidence` | direct | **DELETED** | No successor |
| `O9_Claim_Signature_Map` | direct | **DELETED** | No successor |
| `R1_Codebook` | direct (13 practice definitions were its entire content) | **REPLACED** | → `Definitions_And_Freeze`, carrying definitions, examples and thresholds for the 17 judgement-bearing variables that remain. The freeze mechanism survives |
| `O1_Community_Attributes` | mixed | **REBUILT** | → `Community_Register`, 55 columns. `activity_tier` renamed; `channel_count` and `evidence_tier` made formulas; two duplicate fields merged out |
| `O3_Onset_Register` | none | **REBUILT** | → `Onset_Register`, 21 columns. Two fields with no consumer deleted; `founding_decade` and `onset_band_width_years` made formulas |
| `O10_Polygon_And_Area` | none | **REBUILT** | → `Polygon_Geometry`, 23 columns. Bidirectional mirroring with `O1` replaced by one-directional lookups; `equal_area_circle_radius_m` added for SC1; the empty-lookup bug fixed |
| `O4_Reliability_Report` | mixed | **REBUILT** | 12 pre-filled rows covering 24 variables → 14 rows, one per variable. The single row standing for all thirteen practice codes is gone; `managed_area_basis` and `e2_settlement_type` added |
| `O5`, `O6`, `O7`, `O8`, `O11`, `R2`, `R3`, `Cohort_Tracker`, `Reference_Codes`, `README` | none / mixed | **REBUILT** | Carried forward with the practice vocabulary removed and the three colliding `language` columns disambiguated |
| Register Block F (14 fields) | direct | **DELETED** | Blocks relettered A–H |
| Register Blocks A, B, C, D, E, G, H, I | none | **REBUILT** | 11 further fields deleted on the downstream-consumer test; 2 duplicates merged; 2 made derived |
| The paste map | mixed | **REBUILT** | Every destination re-pointed at the new sheets |
| The crawl protocol (10 stages) | **partial** | RETAINED, re-prioritised | No stage was practice-specific, but the *budget* went disproportionately to the community's own material. A floor on Stages 4–6 is added |
| The 12 anti-fabrication rules | mixed | RETAINED, 2 rewritten, 2 added | Rule 12's "a photograph is not a practice code" bullet becomes "a photograph is not an area and not a date"; rules 13 (never estimate area from imagery) and 14 (do not report practices) added |

---

## 3. Terms searched, and where each survives

Every term from the required search list, with its status in the revised system. **All remaining occurrences were individually inspected**; each sits in one of exactly three contexts: the §0.1 removal argument, the Appendix D change map, or a limitation stating what the study consequently cannot claim.

| Term | Plan v4.0 | Register v3.0 | Workbook v1 |
|---|---|---|---|
| `practice` / `practice code(s)` | 61 occurrences, all in §0.1, §0.2, §3.6, §3.8, §9.5, §10.2, §10.3, §10.5, Appendix D or the glossary entry that records the removal | 15 occurrences, all in the "what changed" and "what was deleted" sections and in anti-fabrication rule 14 | 19 occurrences, all in README and sheet notes recording the removal |
| `PC01`…`PC13` | 6 (Appendix D map, §0.1 examples) | 14 (the §A.6 deletion list) | **0** |
| `pc01_rainwater`…`pc13_restoration` | 0 | 14 (deletion list only) | **0** |
| `practice matrix` / `practice evidence` / `claim-to-signature` | 10 (deletion records) | 3 | 4 (README, recording deletion) |
| `claims-versus-delivery` | 8 (deletion records) | 0 | 0 |
| `practice prevalence` / `practice-signature` | 2 (deletion records) | 0 | 0 |
| `H6` / `A6` | **live identifiers with new meaning** — the density hypothesis and analysis. Old meaning recorded in Appendix D | n/a | n/a |
| `explicitly absent` / `not mentioned` | 5, all in §0.1 explaining why a binary split of a five-level variable fails | 1 | **0** |
| `activity_tier` | 5, all recording the rename | 3, same | **0** |
| `size_class` / `size_class_confidence` | 4, all in §0.4 correction 3 and Appendix D | 0 | **0** |
| `FDR` / false discovery | Live: one family of six | n/a | n/a |
| Practice-named terms (swales, no-till, mulching, agroforestry, polyculture, hedgerows, organic, restoration…) | Present only in: the sub-pixel resolution callout (what the sensor cannot see), the language rules (words not to write), the §3.8 interpretive rule and the limitations | Absent except in the deletion list | **0** |

**Verified programmatically.** `build/check_consistency.py` searches 1,637,384 characters of workbook content *including raw XML, every formula, every dropdown, every defined name and any hidden sheet* — because deleting a visible sheet is not evidence a term is gone. Result: **zero** practice identifiers anywhere in the workbook, and **zero hidden sheets**.

---

## 4. What the audit found that was NOT about practice codes

Four internal inconsistencies in v3.8, found while tracing dependencies. Full detail in `CHANGE_MATRIX.md` §5.

1. **MDS defined as six metrics in three places and seven in three others.** It is seven.
2. **Expected panel size computed two incompatible ways** (105,182 vs 113,286) plus a third figure of "about 59,000" in Stage 4.
3. **Two coexisting size-class systems**, a redundant confidence tier, two appendix sections sharing a heading, and two contradictory specifications for the size-gradient analysis.
4. **The primary zone described as a 150 m circle in four places** after it had become a polygon — including a callout instructing the reader to "use 150 m everywhere, for every site class", which directly contradicts the five-radius rule stated on the preceding page.

Three further defects were found in the workbook and register while rebuilding, listed in `DECISION_MEMO.md` §7 and §8: two typed fields that could disagree with their inputs, an **unreachable tier** in the evidence ladder, three columns named `language` meaning three different things, and an unguarded lookup that graded uncorroborated sites as *contradicted*.

---

## 5. Data flow after removal

Where each variable originates, and what consumes it.

```
   DOCUMENTARY (published sources)          MANUAL (high-res imagery)
   onset + bounds + rank + tier             the drawn polygon
   population                               its area, confidence, redraw
   documentary managed area                 translation onto 3 controls
   evidence channels V1-V5
   status, eligibility, 3 context fields
   12 provenance fields
              |                                        |
              +--------------------+-------------------+
                                   v
                 STAGE 1  essential data + geometry
                                   |
        +--------------------------+--------------------------+
        v                          v                          v
   STAGE 2 matching          STAGE 3 reference pools    STAGE 3b cohort
   (population, protected     (independent of Stage 1)  (onset years)
    area, external programme)
        |                          |                          |
        +--------------------------+--------------------------+
                                   v
                 STAGE 4  EARTH ENGINE  (4 exports)
                 6 indices x 12 months x 7 geometries
                                   v
                 STAGE 5  DP1-DP12  ->  FROZEN analysis table
                                   v
                 STAGE 6  rescale -> VCI / PCI / MDS / LCC / flags
                                   v
                 STAGE 7  A1...A8 + shrinkage + SC1-SC18 + PL1-PL3
                                   v
                 STAGE 8  reporting -> T15 -> STUDY 2
```

**Origins, and the rule for each:**

| Origin | Rule |
|---|---|
| DOCUMENTARY | Never inferred from imagery; never inferred from silence. A field with no source is `not found`, which is a value |
| MANUAL | Traced from structure, never from colour. Never derived from Earth Engine, which would set the measurement zone from the signal measured inside it |
| EXTRACTION | Never searched for on the web |
| DERIVED | One authoritative source each; never also typed |

**What no longer flows anywhere:** the thirteen practice codes, the practice evidence rows, the claim-to-signature mapping, and the arc from Stage 1 into A6. The arc from Stage 1 into A4 (onset), A7 (cohort), A8 (age confounder), SC16 (area corroboration) and SC18 (evidence tier) is unchanged or strengthened.

---

## 6. Load-bearing components confirmed after removal

Audited individually, as required. Each survives, and each is listed with the thing that would break if it were removed.

| Component | Still load-bearing? | What breaks without it |
|---|---|---|
| H1–H5, H6, H7, H8 (v4.0 numbering) | yes | The study |
| VCI, PCI | yes | Both primary outcomes |
| MDS | yes | H5, the site-selection defence |
| LCC | yes | "More vegetation" cannot be told from "better vegetation" |
| Water-subsidy flag | yes | "Greener" cannot be told from "irrigated"; SC7 dies |
| Disturbance flag | yes | The typology's maintenance-mode axis |
| Polygon measurement | yes | The measurement itself |
| Translated control polygons | yes | The comparison becomes chosen land vs whatever is there |
| Reference circles at five radii | yes | Every rescaled score at a small or large site is biased, invisibly |
| Matching + quartet fixed effect | yes | The comparison |
| Onset dating | yes | A4, the cohort, and A8's age confounder |
| Population | yes | A matching criterion and a covariate |
| Documentary managed-area corroboration | yes, re-scoped | T10 and the SC16 restriction; the only external check on the geometry |
| Status / survivorship | yes, simplified | Eligibility criterion E5 and the survivorship limitation |
| Evidence tier | yes, redefined | A confounder in A4, the sample description, and SC18 |
| Sensitivity checks | yes | The robustness section |
| Placebo tests | yes | PL1 gates everything downstream |
| Per-community outputs | yes | The typology and the entire Study 2 handoff |
