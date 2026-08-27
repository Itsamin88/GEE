# Added evidence categories

The canonical 88 fields of register v2.4 are implemented exactly, with their vocabularies
and their workbook destinations. This document lists what was added *around* them, and why.

Nothing here changes a canonical field. The five categories the register distinguishes —
canonical study fields, additional discovery metadata, auxiliary evidence, derived
variables and satellite-derived variables — are kept apart, and the additions below are
all in the second and third categories.

---

## Auxiliary evidence: the supplementary workbook sheets

The canonical workbook records *which source* supported a value. It has nowhere to put the
*sentence*. These sheets fill that gap, each with a stated methodological purpose.

| Sheet | Why it exists |
| --- | --- |
| `X1_Evidence_Register` | The exact wording behind every coded value, with its locator — a page number, a `Sheet1!B7` cell reference, a section heading. Without it a value can be traced to a document but not to a claim inside it. |
| `X2_Claim_Register` | Every claim *before* reconciliation, including the ones that lost. A value that was overruled is visible rather than discarded. |
| `X3_Image_Evidence` | The image manifest, with what each image alone may evidence and which sentence would license a claim from it. |
| `X4_Document_Register` | Every file, its hash, its parser status and every address it was reached from. A document downloaded but not parsed is visible here rather than counted as read. |
| `X5_Crawl_Audit` | Per source: pages, documents, images, budget spent, and why crawling stopped. This is what distinguishes an exhausted source from an abandoned one. |
| `X6_Failure_Log` | Every failure with its cause. A reported block is data; a silent gap is not. |
| `X7_Source_Graph` | Which source derives from which, and the similarity that established it — the evidence behind the independence groups. |
| `X8_Review_Queue` | Cases where a machine decision would be a bad decision. |
| `X9_Discovery_Log` | How each address was found, and why candidates were rejected. This is what distinguishes a narrow search from a thin result. |
| `X10_Field_Provenance` | One row per field: value, method, supporting sources, independence groups, residual uncertainty. The audit entry point. |
| `X11_Run_Manifest` | Versions, configuration hashes, research-document hashes, optional features available, and every research decision applied. |

---

## Discovery metadata: fields kept in the database, not the workbook

These support retrieval and audit. None is a study variable.

**On a source:** `retrieval_priority` (A/B/C — how much crawl effort it earns, deliberately
*not* the evidence rank), `discovery_method` and `discovery_query` (how it was found),
`independence_reason` (why it is in its group), `belongs_confirmed` and `belongs_evidence`
(Stage 1 identity confirmation), `budget_pages` / `budget_spent` / `exhausted`,
`archive_snapshot_count`, `earliest_dated_item` and `latest_dated_item`.

**On a page:** `render_mode` (http, browser or archive), `archive_timestamp` and
`archived_original`, `simhash` (for copy detection), `yielded_evidence`, `depth`.

**On a document:** separate `parser_status`, `text_status`, `table_status` and
`image_status`, so "downloaded" is never confused with "read". `mime_declared` and
`mime_sniffed` are both kept, because a server that mislabels a PDF is itself a fact.

**On a claim:** `reference_year` (the year the value refers to, distinct from publication
and retrieval), `extractor`, `model_name`, `prompt_version`, `verified_passage`.

---

## Image evidence

The register has one image-related field, `site_plan_published`. The brief asks for image
discovery as a first-class task, so each retained image carries:

`image_type` · `research_topic` · `caption` · `surrounding_text_summary` ·
`evidence_subject` · `possible_relevant_fields` · `visual_evidence_allowed` ·
`documentary_text_support` · `image_date_if_known` · `image_date_confidence` ·
`OCR_text_if_used` · `relevance_class` · `relevance_reason` · `confidence`

Two of these carry the methodological weight:

- **`visual_evidence_allowed`** — what the image on its own may evidence. For a photograph
  this is *"V4 visual documentation ONLY where the photograph is dated and shows a physical
  structure"*. It never names a practice code.
- **`documentary_text_support`** — the exact sentence that would license a claim, or
  `NOT FOUND`. A photograph of green rows returns `NOT FOUND`; a caption reading "we
  planted mixed perennial crops between 2015 and 2018" returns that sentence.

This is the register's rule 12 made auditable: the artefact is preserved either way, and
whether it may support a code is a recorded property rather than a judgement made once and
forgotten.

---

## Context fields the register mentions but does not name

Register A.0 allows a community's own published elevation, rainfall or landholding figure
to be recorded as Block H context, but names no field for it.

**Added:** `context_elevation_m` and `context_annual_rainfall_mm`, stored as claims with
full provenance and prefixed `context_` so they are structurally incapable of reaching a
satellite-route field. They surface in the workbook as text with a source id, never as a
number in a pipeline column.

---

## Additional search routes

Beyond the databases the register names, the following are consulted and logged. Each is a
route to *existing* register fields — mainly `date_intervention_onset`,
`external_funding_or_programme` and `managed_area_ha` — not a new variable.

- **Academic APIs**: OpenAlex, Crossref, Semantic Scholar, OpenAIRE, DOAJ, DataCite, CORE,
  HAL, theses.fr, DNB — machine-readable and verifiable, where the register's named
  databases are mostly not.
- **Registries**: the French RNA association register and Annuaire des Entreprises,
  OpenCorporates, OpenStreetMap Nominatim (locality confirmation only — never an area
  source).
- **Planning portals**: Ruimtelijkeplannen.nl, Géoportail de l'urbanisme.
- **Funding**: CORDIS, LIFE, Erasmus+, Keep.eu (Interreg), ENRD/LEADER, the EU Funding &
  Tenders portal, OpenAIRE projects.

Every one is logged in `O7_Search_Log` whether it returned anything or not, and one that
cannot be read by a program is recorded as `unreachable` — never as zero results.

---

## What was deliberately *not* added

- **No new practice codes.** The codebook is thirteen and frozen.
- **No new coding levels.** Five, exactly as the register defines them.
- **No confidence score on a workbook field.** Confidence lives on the claim, where it
  belongs; a canonical field carries a value and its provenance.
- **No derived ecological measure of any kind.** Everything on the satellite blocklist is
  refused at the point of writing, and an attempt to code one is a hard validation failure
  rather than a warning.
