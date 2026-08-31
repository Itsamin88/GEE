# Consistency audit — revised_v4

Verification that the three revised artifacts form one coherent system. **Every check below was executed, not asserted.** The verifier is `build/check_consistency.py`; re-run it any time the artifacts change.

```
$ cd revised_v4/build && python3 check_consistency.py
103/103 checks passed
ALL CHECKS PASSED
```

**Artifacts verified**

| File | How it was verified |
|---|---|
| `THE_SIMPLIFIED_PLAN_v4.0.docx` | Re-opened after writing and extracted to text: 834 paragraphs, 135 tables, 18 top-level headings, 299,031 characters. XSD-validated. |
| `Stage_1_Essential_Data_Workbook_v1.xlsx` | Re-opened after writing. Every cell, formula, dropdown, defined name, sheet-state flag **and the raw XML of every part** read — 1,637,384 characters. Formulas evaluated against a spreadsheet engine on seeded test data. |
| `WEB_SEARCH_FIELD_REGISTER_AND_CHATGPT_PROMPT_v3.0.md` | Read in full and cross-checked field-by-field and value-by-value against the canonical specification. |

**How drift is prevented rather than merely detected.** One machine-readable specification, `build/field_spec.py`, defines every field name, allowed-value list, purpose, downstream consumer and missing-data rule. The workbook is *generated* from it; the plan's Appendix C is *generated* from it; the register is *verified* against it. The three cannot disagree without the verifier failing.

---

## The required checklist

- [x] **no orphan practice fields**
- [x] **no orphan H6/A6 references**
- [x] **no obsolete practice-code workbook sheets**
- [x] **no obsolete practice-code web-search fields**
- [x] **no obsolete practice-code paste-map entries**
- [x] **no contradictory onset definitions**
- [x] **no contradictory managed-area definitions**
- [x] **no contradictory polygon definitions**
- [x] **no duplicate authoritative fields**
- [x] **no inconsistent sample counts**
- [x] **no inconsistent hypothesis numbering**
- [x] **no inconsistent multiplicity statements**
- [x] **no outdated reporting items**
- [x] **no outdated glossary entries**
- [x] **no broken Stage references**
- [x] **no broken table/figure references**
- [x] **no broken Study 2 handoff**

Evidence for each follows.

---

## A. Orphan scan

Every occurrence of the watched term set was located and **individually inspected**. Nothing was accepted on a keyword rule alone.

| Artifact | Occurrences | All accounted for? |
|---|---|---|
| Plan v4.0 | 103 | yes |
| Register v3.0 | 59 | yes |
| Workbook v1 | 29 | yes |

Each surviving occurrence sits in exactly one of three contexts, and no fourth context exists:

1. **The removal argument** — plan §0.1 and §0.2, register "What changed in version 3.0" and §A.6.
2. **The change record** — plan Appendix D, register §A.6 tables, workbook README and sheet notes.
3. **A limitation or prohibition** — plan §3.8, §9.5, §10.2, §10.3; register anti-fabrication rule 14; the glossary entry for "practice code", which exists precisely to record that the variable was removed.

### The hard test: no practice identifier survives anywhere in the workbook

Deleting a visible sheet is not evidence a term is gone. The verifier searches cells, formulas, data-validation lists, defined names, sheet-state flags **and the raw XML of every part in the archive** — 1,637,384 characters — for: `pc01`…`pc13`, `Practice_Matrix`, `Practice_Evidence`, `Claim_Signature`, `practice_code`, `coding_level`, `activity_tier`, `size_class`.

**Result: zero matches. Zero hidden sheets.** The 29 workbook occurrences above are all in README and sheet-note prose recording the deletion.

### H6 / A6

`H6` and `A6` are **live identifiers in v4.0 with new meanings** — the density hypothesis and its analysis. A bare-word search is therefore meaningless, so the check is structural instead: the plan is verified to contain H1–H8 and A1–A8 contiguously, and every occurrence of the retired `H9`, `A9`, `F0`, `T8a`, `T8b`, `T8c`, `F2a`, `F6a`, `F7a` and `F8a` is verified to fall **inside a change-documentation section** (§0.2, §0.4, §8.13, §9.1 or Appendix D) rather than merely to be absent. Confinement is the stronger check: absence would have destroyed traceability.

- [x] no orphan practice fields
- [x] no orphan H6/A6 references
- [x] no obsolete practice-code workbook sheets
- [x] no obsolete practice-code web-search fields

---

## B. Field names — three artifacts, one list

| Check | Result |
|---|---|
| Every one of the 61 specified field names appears in the register | pass |
| Every specified field has a workbook column, except the four that unpack into rows (`academic_search_log`, `grey_literature_log`, `source_set_supplied`, `source_set_discovered`) | pass |
| Every one of the 9 derived fields has a workbook column | pass |
| Every one of the 13 researcher-supplied fields has a workbook column | pass |
| No workbook column exists that is not a specified, derived, researcher-supplied or named administrative field | pass |

Block totals, recounted from the specification rather than copied: **A 5 · B 6 · C 12 · D 5 · E 13 · F 5 · G 3 · H 12 = 61**, in 8 blocks. The register's stated total matches.

### Paste map

Every destination sheet named in the register's paste map exists in the workbook, and every data sheet in the workbook is named in the paste map: `Community_Register`, `Onset_Register`, `Polygon_Geometry`, `Source_Index`, `Source_Set`, `Search_Log`. No paste-map entry points at a deleted sheet.

- [x] no obsolete practice-code paste-map entries

---

## C. Allowed values

Fifty-five dropdown-bound columns were resolved to their header (by column letter, not by assumption) and compared against the specification **element by element and in order**.

| Check | Result |
|---|---|
| Every controlled-vocabulary field has a workbook dropdown | pass |
| Every dropdown matches the specification exactly | pass |
| Every allowed value appears in the register text | pass |

This check caught two real binding errors during the build: `crawl_truncated`'s dropdown was attached to `stages_completed`, and `double_coded`'s to `coding_date` — both off-by-one column references that would have made two controlled fields free-text and two free-text fields refuse valid input.

---

## D. Numerical consistency — recomputed, never copied

Every figure below was recomputed from its inputs.

| Quantity | Recomputed | In the plan |
|---|---|---|
| Main-study rows | 848 × 7 × 7 = 41,552 | yes |
| Reference rows | 1,350 × 5 × 7 = 47,250 | yes |
| Cohort rows | 260 × 7 × 9 = 16,380 | yes |
| **Panel total** | **105,182** | yes, derived once in §4.4 and quoted by §5.7 and Stage 4 |
| SC1 separate export | 848×7 + 260×9 = 8,276 | yes, with its own row-count check |
| Detectable difference | √(10.47 / 212) = 0.2222 SD | yes |
| Register fields | 61 in 8 blocks | yes |
| Workbook sheets | 15 | yes |
| Reliability variables | 14 | yes |
| Hypotheses | 8 (2 primary, 6 secondary) | yes |
| Analyses | 8 | yes |
| Objectives | 8 | yes |
| Sensitivity checks | 18 | yes |
| Placebo tests | 3 | yes |
| Reported robustness items | 21 | yes |
| FDR family size | 6 | yes |
| Multiplicity structures | 1 | yes |
| MDS metrics | 7 | yes |
| Sites | 212 / 636 / 848 / ~260 / 1,350 / 2,458 | all present |

**Superseded figures verified as confined, not merely absent.** The v3.8 figures `113,286` and `59,000`, and the statement `H3 to H9 form one family`, appear **only** in the correction sections that document them. Neither is stated anywhere as a live figure.

- [x] no inconsistent sample counts
- [x] no inconsistent multiplicity statements

---

## E. Identifier contiguity

| Series | Verified | Result |
|---|---|---|
| Hypotheses | H1…H8 all present; no live H9 | pass |
| Analyses | A1…A8 all present; no live A9 | pass |
| Tables | T1…T15, no gap, no suffixed ids | pass |
| Figures | F1…F14, no gap, no suffixed ids (F0 appears only in the Appendix D map) | pass |
| Sensitivity checks | SC1…SC18, no gap | pass |
| Placebo tests | PL1…PL3 | pass |

Every retired identifier is mapped in Appendix D with its statement and its status.

- [x] no inconsistent hypothesis numbering
- [x] no broken table/figure references

---

## F. One definition per concept

Checked because v3.8 carried four concepts defined twice with different content.

| Concept | Check | Result |
|---|---|---|
| Primary zone | Defined as the polygon; no live "150 m primary zone" claim survives | pass |
| Reference circle | One variable, five levels, thresholds stated once | pass |
| Equal-area circle | Defined once, for SC1, with the reason area is held constant | pass |
| Area agreement tier | Tier B explicitly covers the no-documentary-figure case, in all three artifacts | pass |
| Evidence tier | Described as an evidence-quality variable in the plan; the same ladder stated in the register and the workbook | pass |
| Onset | "NOT the founding year" present in all three artifacts | pass |
| Managed area vs total holding | The 200 ha / 15 ha distinction present in all three artifacts | pass |
| MDS | Seven metrics; no surviving "mean of the six" statement | pass |

The register's Block C table was amended during this audit: it carried the founding-year rule only in prose and in the prompt block, not in the field table where a coder would meet it. It now carries the plan's exact phrasing.

- [x] no contradictory onset definitions
- [x] no contradictory managed-area definitions
- [x] no contradictory polygon definitions

---

## G. No duplicate authoritative entry points

193 distinct data columns were resolved across the workbook, and every repeated column name was classified.

| Classification | Rule | Result |
|---|---|---|
| Key / label / cross-reference columns (`site_id`, `variable`, `source_class`, `independence_group`, `date`, `url`) | Shared by design: they say which entity a row is about and carry no value that can drift | accepted |
| Read-only lookups (`community_name`, `documentary_managed_area_ha`, `documentary_area_basis`) | Formula on one sheet, typed on the other. One direction only | accepted |
| **Value columns typed on two sheets** | Not permitted | **none found** |

Two real defects were fixed to reach this state:

1. **v6 mirrored bidirectionally**: `O1!U` read from `O10!C` while `O10!M–R` read back from `O1!V–Z, BK`. Replaced with one-directional lookups; nothing reads back.
2. **Three columns named `language`** meant the language of a *source*, of a *web address*, and of a *search*. Renamed `source_language`, `address_language`, `search_language`, and the distinction documented in the register's paste map and on the sheet itself. The verifier now asserts the three names are distinct.

- [x] no duplicate authoritative fields

---

## H. Workbook quality control

Beyond the structural checks, the workbook was **executed**: the formulas were evaluated against a spreadsheet engine on seeded test data covering the boundary cases.

| Case | Expected | Observed |
|---|---|---|
| 4 channels incl. external | tier A | A |
| 2 channels, no external | tier C | C |
| 3 channels, no external | tier C | C |
| 1 channel | Fail | Fail |
| 3 channels incl. affiliation | tier A | A |
| Polygon 13.4 ha, stated 15 ha | tier A, r210, radius 206.5 m | as expected |
| Polygon 13.4 ha, stated 200 ha (total-holding confusion) | tier C, ratio 14.93 | as expected |
| **Polygon 0.7 ha, no stated figure** | **tier B**, below-minimum yes, r75 | as expected |
| **Polygon 25 ha, no stated figure** | **tier B**, r300 | as expected |
| Polygon 6.0 ha, stated 6.0 ha | tier A, r150 | as expected |
| Cohort tracker: 3 core, 2 at tier A/B | 3 and 2 | as expected |

Two defects were found by this execution and fixed:

1. **Tier C was unreachable.** The v2.4 ladder ordered by channel count before independence, and the only channel that is neither external nor visual nor continuity is V1 — so no community could reach "2 community-originated channels". Rebuilt to order by independence first; all four tiers now occur.
2. **An unguarded lookup graded uncorroborated sites as contradicted.** `INDEX` over an empty cell returns `0`, not blank, so a site with **no** documentary area was receiving `area_ratio = 0` and `area_agreement_tier = C` — "the two disagree by more than a factor of two" — when there is no figure to disagree with. The plan requires tier B. This is the exact failure mode the plan warns about ("a blank looks identical to a site nobody has coded yet"), reintroduced by the rebuild and caught before it shipped.

Also verified: sheet names, header rows, frozen panes on every data sheet, auto-filters, no duplicate columns within a sheet, no `#REF!` or broken references, no named ranges, no hidden sheets, and no example rows to forget to delete.

---

## I. Document quality control

| Check | Result |
|---|---|
| XSD schema validation of the `.docx` | **All validations PASSED** (3,652 paragraphs) |
| Re-opened after writing and fully re-read | 834 paragraphs, 135 tables, 299,031 characters |
| Top-level structure | 18 top-level headings: Parts 0–11 and Appendices A–F. No duplicate part numbers |
| No section says "same as v3.8" or "unchanged from the previous version" for a substantive implementation section | pass — every such statement is a *change record* in §0.2, §0.4 or Appendix D |
| Terminology consistent with the register and the workbook | pass (§B, §F) |
| Practice-code remnants | pass (§A) |
| Cross-references to renamed stages and sections | pass — `§7.1a` → `§7.1`, Stage 1 renamed throughout |

- [x] no outdated reporting items
- [x] no broken Stage references

---

## J. Glossary

Rebuilt rather than edited. Verified against the body of the plan.

| Check | Result |
|---|---|
| No entry describes the primary zone as a circle | pass |
| No entry describes a size class | pass |
| `activity_tier` does not appear; `evidence_tier` is defined as an evidence-quality variable | pass |
| Contour alignment entry describes one comparison, not two | pass |
| New entries exist for concepts introduced in v4.0: management-consistent, external channel, equal-area circle, onset proxy, crawl truncation | pass |
| `practice code` is retained as a **historical** entry that states the removal and says no practice variable exists in the data model | pass — deliberate, so a reader meeting the term in an older draft can find out what happened to it |

- [x] no outdated glossary entries

---

## K. Study 2 handoff

| Check | Result |
|---|---|
| The per-community table specification lists no practice field | pass |
| Nothing was added to fill the gap | pass — stated explicitly in §10.4 |
| The handoff is specified item by item with each item's status | pass — plan §10.5 |
| The one retained documentary variable carries its interpretation constraint | pass — the evidence tier may enter as a data-quality feature only |
| The constraint is enforced by the data rather than by discipline | pass — the register no longer collects any self-described variable, so none can reach the feature set |

- [x] no broken Study 2 handoff

---

## L. Source files unmodified

| File | MD5 before | MD5 after | Status |
|---|---|---|---|
| `THE_SIMPLIFIED_PLAN_v3.8.docx` | `6452eea16c6cf9272ec17d8b8439035f` | unchanged | preserved in `originals/` |
| `Stage_1_Documentary_Coding_Workbook_v6.xlsx` | `e347c83b830dcc8e7877bccca0dd95c1` | unchanged | preserved in `originals/` |
| `WEB_SEARCH_FIELD_REGISTER_AND_CHATGPT_PROMPT_v2_4.md` | `651e52b74ae310ba501cc122ca59be21` | unchanged | preserved in `originals/` |

The originals were read only. Every revised artifact was written to `revised_v4/`. The workbook was **rebuilt from scratch**, not mutated: it shares no cell, formula or sheet with v6.

---

## M. What this audit does NOT establish

Stated so that the passing result is not read for more than it is worth.

1. **LibreOffice is non-functional in the build environment** — it fails to load the *original* v3.8 `.docx` and v6 `.xlsx` as well as the new files — so the plan was **not** rendered to PDF and visually inspected page by page. It was instead XSD-validated and fully re-read after writing. Layout defects that would only appear on a rendered page (a table overflowing the margin, an awkward page break) are therefore **not** ruled out. Open the `.docx` in Word or LibreOffice on a working machine before submitting it.

2. **Formula evaluation used the `formulas` Python engine, not Excel.** The logic is verified; Excel-specific rendering of the same formulas is not.

3. **The verifier checks consistency, not correctness.** It confirms the three artifacts agree with one another and with the specification. It cannot confirm that the specification is the right one — that is what `DECISION_MEMO.md` argues, and the argument is for a reader to judge.

4. **Effort estimates are estimates.** The recalculated timings derive from field counts and per-community search timings, not from measurement. The plan says to record the actual rate once fifty communities are coded.

5. **Nothing here is a result.** No community has been coded, no polygon drawn and no imagery extracted.

---

## Verdict

**PASS.** 103 of 103 automated checks pass, every orphan-scan occurrence was individually inspected and accounted for, and the workbook's logic was verified by execution rather than by reading. Four inconsistencies in the source plan and five defects in the workbook and register were found and fixed in the process, five of which were unrelated to the practice-code decision.

Re-run `build/check_consistency.py` after any edit to any of the three artifacts.
