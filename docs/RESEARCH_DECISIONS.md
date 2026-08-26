# Research decisions

Every contradiction, ambiguity or gap found between the three research documents, and how
this program resolves it. The machine-readable form is `config/decisions.yaml`; each
decision is also exported into `X11_Run_Manifest` in every workbook, so the resolution
travels with the data.

**Authority order:** `Stage_1_Documentary_Coding_Workbook_v6` → `WEB_SEARCH_FIELD_REGISTER_v2_4` → `THE_SIMPLIFIED_PLAN_v3.8`.

The workbook is the destination and carries the live vocabularies; the register defines
the fields; the plan explains why they exist. Where the plan pre-dates a workbook change,
the workbook wins.

---

## Contradictions between the documents

### D001 · Practice code names differ between the plan and the workbook
The plan (§3.10, table 45) names them `pc_rainwater` … `pc_restoration`. The workbook and
register use `pc01_rainwater` … `pc13_restoration`.

**Resolved:** the workbook's numbered names are canonical; the plan's form is kept as
`plan_alias` so a reader of the plan can still find the field.

### D002 · `size_class_documentary` and the SMALL/MEDIUM/LARGE radii still appear in the plan
Plan v3.4 gives size classes with 100/150/200 m radii. Plan v3.6 replaced the circle with
a hand-drawn polygon; register v2.3 retired `size_class_documentary`; workbook v6's
`Reference_Codes` replaces the size-class block with the reference-circle block computed
from the polygon.

**Resolved:** never code a size class. Both names are on the blocklist, so an attempt to
write either is a hard validation failure.

### D006 · Managed area changed role between plan versions
Plan v3.4 has `managed_area_ha` assigning the size class that sets the measurement
radius. Plan §7.1a and register v2.3+ make the drawn polygon the geometry and the
documentary figure the *check*.

**Resolved:** the documentary figure is coded as a stated figure with a band and a basis,
and never used to derive geometry. The program never writes `polygon_area_ha` and never
estimates an area from imagery, a map view, or a site plan it has not read a figure off.

---

## Ambiguities the documents do not settle

### D003 · The same quantity occupies two workbook columns
`e3_population_value` (O1!N) and `population_value` (O1!Q) are both permanent residents.

**Resolved:** one claim, written to both, with the same source ids, and the duplication
recorded so a later reader does not treat two columns as two findings.

### D004 · Who is the coder when the coding was done by software?
**Resolved:** `coder_id` is written as an explicit machine identity (`DCR/<version>` or
whatever you supply), and `coding_date` as the export date. Leaving them blank would
falsely suggest a human read the sources. `double_coded` and `second_coder_id` are never
written: an automated pass is a first coding, not a second coder, and the reliability
statistics in O4 must not be computed against it.

### D005 · `coordinate_agreement` cannot be assessed without your coordinates
The dropdown allows only `agrees` / `differs` / `no published location` — and the last of
those describes the *sources*, not a missing input of yours.

**Resolved:** with no coordinates supplied the field is left **empty** and a review item
is raised. With coordinates, agreement is computed against the nearest published location
and `differs` is written beyond 2 km, with the distance in the rationale.

### D007 · Disagreement about a year has a rule; disagreement elsewhere does not
**Resolved:** onset uses the register's rule (9.2) deterministically — better rank wins;
equal rank takes the earlier year and the gap becomes the band. For other fields a
stronger source class wins, and two sources of *equal* strength in *different*
independence groups go to a human rather than being decided quietly.

### D008 · A value that changed is not a value that conflicts
Register 9.4: a 2012 page saying four hectares and a 2024 page saying fifteen are not in
disagreement — the community grew.

**Resolved:** every quantitative claim carries the year the figure *refers to*, separately
from the publication and retrieval dates. Figures that move monotonically across more
than three years are recorded as a time series, and the band is taken from figures
describing the same period.

### D009 · What makes `crawl_truncated = yes` for a program rather than a chat model?
**Resolved:** any of — a budget exhausted with URLs still queued; a stage not completed; a
supplied address ending at `not attempted` or `partial`; an archive or academic endpoint
unreachable so its stage could not finish; the run interrupted. Each cause is named in
`stages_completed`, so the reason is recoverable rather than a bare `yes`.

### D010 · Directory listings are usually copies, occasionally not
**Resolved:** a listing defaults to the community's own independence group. It is promoted
to its own group only when text-overlap analysis shows low similarity *and* the listing
carries editorial signals — a byline, a visit report, an assessment. The similarity score
is stored so the decision can be audited.

### D013 · A found academic record is not a verified one
**Resolved:** a record may support a value only after `verified_resolves = yes`, which
requires that its DOI or repository record was retrieved in this run and its title
matched. Unverified records are written to `O6_Source_Index` with `verified_resolves = no`
and barred from coding. The program never constructs a DOI or a repository URL.

### D019 · A keyword match is not a coding level
**Resolved:** level is assigned by rule from the evidence — `evidenced` needs an external
class (S1/S2/S6) or dated visual source *with* a specific statement; `documented` needs a
community-class statement that is specific *and* recurs across years; `claimed` is a
community statement without either; `explicitly absent` needs an actual denial in the same
sentence; `not mentioned` is silence, and never absence.

### D023 · Where does the first coded row go?
Row 2 of each sheet is the template's worked example, which the README says to delete —
but it is also the one row where the formula columns hold *constants*, and deleting it
would shift every formula.

**Resolved:** row 2 is **emptied**, not deleted, and coded rows start at **row 3**. That
keeps every formula intact, matches `Cohort_Tracker`'s own `A3:A500` range, and leaves the
README's progress counters reading exactly as the README says they will.

### D026 · Which discovered addresses may be adopted?
**Resolved:** only when the community's name appears in the host or the URL path, or the
address is on a domain already established as the community's, or it is a platform
profile linked from the navigation or footer of a confirmed page. A footer also carries
funders, partners and the web designer, so being linked from one is not sufficient on its
own. Every rejection is written to the discovery log with its reason.

---

## Defects found by running the code

These were found by running the pipeline against the pilot fixture, and each was a real
defect rather than a fixture artefact.

| # | Defect | Fix |
| --- | --- | --- |
| D023 | Writing into row 2 gave the first community the example row's polygon area | Empty row 2; write from row 3 |
| D024 | Values stored as text reached Excel as text, silently excluding them from O4's calculations | Convert per the schema's datatype |
| D025 | A dead host cost sixty slow probes and stalled the run | Circuit breaker after five consecutive failures |
| D026 | Any platform URL was adopted without a name match, so one community collected another's addresses | Require a name match or a confirmed-page platform link |
| D027 | Relative links in an archived snapshot resolved against the archive host, inventing addresses | Resolve against the original URL and follow as same-date snapshots |
| — | `normalize()` flattened `//` inside Wayback URLs, turning every snapshot into a 404 | Never collapse slashes inside an embedded URL |
| — | Population extraction read "En 2017 nous avons…" as a population of 2017 | Require a resident noun; refuse year-shaped numbers |
| — | The onset engine picked the best-*evidenced* year rather than the *earliest* documented action | Earliest action is the value; rank sets the band |
| — | A verified thesis fetched outside a registered source was coded as community-class S4, so it could never upgrade a practice to `evidenced` | Register academic and grey records as sources with their own class and group |
| — | Speculative 404 probes exhausted a source's budget before its sitemap pages were read | Probe failures no longer count towards exhaustion |
| — | Free-text notes differing between pages were recorded as conflicts, burying the real ones | Accumulate distinct observations instead |

---

## Defects found while adding image triage, pause/resume and estimation

Each was found by running the pipeline or by writing a test for it, and each was verified
against the restored baseline before being called a defect rather than a regression.

| Defect | Why it mattered | Fix |
| --- | --- | --- |
| A quoted YAML scalar in the image lexicon wrapped across two lines, and YAML folded the newline into a space, turning `\|plan.?de.?masse\|` into `\| plan.?de.?masse\|` | A French caption *beginning* "Plan de masse" scored nothing, so the site plan behind it was never downloaded — on a pilot community whose site is in French | Each alternation kept on one line; the compiler strips whitespace around `\|`; a test fails if a folded pattern reappears |
| A strong keyword bypassed the size floor entirely | `map-pin.png` at 24×24 with alt="map" classified as likely_relevant and was downloaded as research material | Anything at icon size is decoration whatever it is called; a thumbnail of a real plan still is not |
| `run_control.failures_before_probe` was configurable but `classify_failures` hard-coded a minimum of 3 | Lowering the threshold silently did nothing, and an outage was never detected | The threshold is passed through and honoured |
| Evidence and claims were written afresh on every pass | One FULL run on the fixture produced 96 evidence rows with 18 duplicated (source, locator, quote) keys, some identical down to the character offset; every count in the completion report was inflated | A dedupe key on evidence and claims; 76 rows, none duplicated |
| `INSERT OR REPLACE` deletes before re-inserting, and `claims.evidence_id` is `ON DELETE SET NULL` | Re-writing a passage that already existed cut every claim resting on it loose from its evidence, leaving a coded value with no traceable sentence — the one thing this design exists to prevent. Only reachable once evidence ids started being reused | Existing rows are never re-inserted; a regression test asserts every claim still resolves to a real evidence row |
| `_finish_run` marked every run `complete`, including one that stopped early | An interrupted run was indistinguishable from a finished one, so its NOT FOUND values read as searched-and-absent | `runs.status` follows the control state; stages never begun say so |

---

## The full list

`config/decisions.yaml` carries all 32 decisions with their evidence, resolution, affected
modules and parameters. Each is reproduced in `X11_Run_Manifest` in every exported
workbook.
