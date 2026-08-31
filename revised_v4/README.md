# revised_v4 — Study 1 after the removal of documentary practice codes

A complete replacement system for Study 1. The three deliverables work together and are verified against one another; the four audit documents record what changed and why.

## Deliverables

| File | Replaces | What it is |
|---|---|---|
| `THE_SIMPLIFIED_PLAN_v4.0.docx` | `THE_SIMPLIFIED_PLAN_v3.8.docx` | The master specification. Standalone — implementable without reading v3.8. 12 parts, 6 appendices |
| `Stage_1_Essential_Data_Workbook_v1.xlsx` | `Stage_1_Documentary_Coding_Workbook_v6.xlsx` | The operational workbook. 15 sheets, rebuilt from scratch |
| `WEB_SEARCH_FIELD_REGISTER_AND_CHATGPT_PROMPT_v3.0.md` | `..._v2_4.md` | The documentary collection architecture and its ready-to-use prompt. 61 fields in 8 blocks |

## Audit documents

| File | Answers |
|---|---|
| `DECISION_MEMO.md` | Why practice codes were removed, what is lost, what remains, and what happens to each component |
| `DEPENDENCY_AUDIT.md` | What depended on practice codes, component by component, with the data flow |
| `CHANGE_MATRIX.md` | Every deletion, rename, retention and rebuild across all three artifacts |
| `CONSISTENCY_AUDIT.md` | Verification that the three form one coherent system, with the executed check results |

## Read in this order

1. `DECISION_MEMO.md` — the argument.
2. `THE_SIMPLIFIED_PLAN_v4.0.docx` §0 — the same argument in the plan's own voice, with the full consequence list.
3. Whichever of the three deliverables you need to execute.
4. `CONSISTENCY_AUDIT.md` §M — what the verification does *not* establish, before relying on it.

## build/

Reproducible build and verification. Not part of the deliverable set, but the reason the three artifacts cannot silently diverge.

| File | Role |
|---|---|
| `field_spec.py` | **The single source of truth.** Every field name, allowed-value list, purpose, downstream consumer and missing-data rule |
| `build_workbook.py` | Generates the workbook from `field_spec.py` |
| `build_plan.js` + `plan_content_1..4.js` | Generates the plan; Appendix C is generated from `field_spec.py` |
| `check_consistency.py` | Verifies all three artifacts against the spec and each other, and scans for orphan practice references |
| `fields.json` | `field_spec.py` exported for the plan builder |

```bash
cd build
python3 field_spec.py         # self-check the specification
python3 build_workbook.py     # rebuild the workbook
node build_plan.js            # rebuild the plan
python3 check_consistency.py  # verify everything  ->  103/103 checks passed
```

Re-run `check_consistency.py` after editing any of the three artifacts.

## Originals

The three source files are preserved unmodified in `../originals/`. Nothing in this directory was produced by editing them in place; the workbook in particular was rebuilt from scratch and shares no cell, formula or sheet with v6.
