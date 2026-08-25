# Architecture

## The one idea

**The database is the record; the workbook is a report.**

Everything retrieved is stored locally with its provenance the moment it arrives. The
workbook, the manifests and the completion report are all generated from that store, so
they can be rebuilt at any time, offline, without re-fetching anything. That is what
makes it possible to change a coding rule and see the effect, add a field, re-parse a
document, or audit a value two years later.

## The evidence model

```
Source ──< Document ──< Evidence ──< Claim ──> Field
   │           │            │
   └───────────┴────────────┴──> Independence group
```

| Level | What it is | Table |
| --- | --- | --- |
| **Source** | One web address, or one verified academic or grey record | `sources` |
| **Document** | One file reached from a source. Stored once by hash, with one provenance row per address it was reached from | `documents`, `document_sources` |
| **Evidence** | One concrete thing: a passage, a table cell, a figure, an upload date. Carries the exact wording and where it sits | `evidence` |
| **Claim** | A structured assertion drawn from one evidence item, with its extractor, confidence and reference year | `claims` |
| **Field** | The resolved value for one workbook column, with the reasoning that produced it | `field_values` |

One source yields many evidence items; one evidence item supports several claims; one
claim contributes to several fields; one field may be supported by several independent
sources. Nothing reaches a workbook cell without an evidence row carrying the sentence
behind it.

## The ten stages

The protocol from register v2.4, implemented as checkpointed pipeline stages. Each
records its own status — `complete`, `partial`, `blocked`, `not_reached`, `failed` — so
`stages_completed` and `crawl_truncated` are *generated* from what happened rather than
asserted.

| Stage | What it does | Key modules |
| --- | --- | --- |
| 0 | Build the source set: supplied addresses, then the ones nobody supplied | `runner`, `discovery/search` |
| 1 | Confirm each address belongs to this community | `runner` |
| 2 | Enumerate every page: robots, sitemaps, feeds, well-known paths, `site:` queries, deep crawl | `crawl/crawler`, `discovery/sitemap` |
| 3 | Open the documents, not just the pages, including file-type search | `extract/*` |
| 4 | The web archive: CDX enumeration, then snapshot retrieval | `discovery/wayback` |
| 5 | Academic literature, with verification and citation chaining | `discovery/academic` |
| 6 | Grey literature, funding databases and official registers | `discovery/grey` |
| 7 | Other web sources; promote the addresses the crawl found | `runner` |
| 8 | Local-language sweep | `language`, `discovery/*` |
| 9 | Cross-source reconciliation | `resolve`, `evidence/conflict` |

## Module map

```
RUN.py                     press RUN in PyCharm; adds src/ to the path and calls the CLI
src/dcr/
  app.py                   prompts, run modes, the export pipeline, the summary
  cli.py                   argument parsing
  runner.py                the ten stages, resumably
  resolve.py               stage 9: claims to one value per field
  config.py                configuration, .env, optional-feature detection
  workbook_audit.py        reads the real workbook and checks the schema against it
  storage.py               the per-community output tree
  language.py              language detection and country mapping
  ids.py                   stable identifiers, safe filenames
  logging_setup.py         console, file and JSONL logging
  db/                      SQLite schema and access layer
  net/                     fetcher (retry, robots, rate limits, circuit breaker),
                           MIME sniffing, optional browser rendering
  crawl/                   URL normalisation and traps, frontier and adaptive budget,
                           platform profiles, the crawl engine
  discovery/               sitemaps and feeds, web archive, academic, grey, search engines
  extract/                 HTML, PDF, Office, spreadsheets, text, and the dispatcher
  images/                  relevance classification
  evidence/                the evidence model, quantities, practices, onset, independence,
                           conflicts, the optional LLM layer
  export/                  workbook, manifests, completion report
  qc/                      the eighteen checks and the coverage matrix
```

## Design decisions worth knowing

**Retrieval priority is not evidence rank.** `retrieval_priority` (A/B/C) decides what to
fetch first and how much effort a source earns. `onset_evidence_rank` (1–5) is the
study's measure of how strong a piece of dating evidence is. They are separate concepts
and never touch.

**The crawl budget is adaptive.** A source starts with a page allowance and earns more
while its pages keep yielding evidence. When they stop, it is declared exhausted and the
effort moves elsewhere. Speculative path probes that 404 do *not* count towards
exhaustion — the protocol asks for forty guessed paths and most sites have few of them,
so charging those 404s would abandon a site before its sitemap was read.

**Failure is data.** Every failure is caught, classified and written to `errors`. A run
never aborts because one URL failed. A host that refuses five times in a row is recorded
as unreachable and no longer probed, so a dead domain costs a handful of requests rather
than sixty.

**Deterministic first, LLM second.** Rules do URLs, dates, numbers, vocabularies,
provenance and validation. The optional LLM layer only classifies text already stored
locally, and every field it proposes must quote a passage that is then verified,
character for character, against that stored text. Without an API key the pipeline runs
unchanged and the review queue grows instead.

**The workbook is treated as read-mostly.** Before writing, the exporter profiles the
template: headers, dropdowns, merged ranges, formula cells. It refuses to write a
formula cell, a researcher-owned column, or a value outside a dropdown, and reports every
refusal. Coded rows start at row 3 because row 2 is the template's worked example, which
holds static values in the columns that carry formulas from row 3 down.

## Data flow of one page

```
frontier ──> fetcher ──> (browser if the HTML is a JS shell)
                │
                ├──> raw HTML          -> 01_raw_sources/
                ├──> parsed text       -> 05_extracted_text/  + pages row
                ├──> links             -> frontier (in scope) or candidate source (out)
                ├──> documents         -> fetch, hash, parse -> 02_documents/ + tables
                ├──> images            -> classify -> keep or drop -> 03_images/
                └──> TextMiner         -> evidence + claims -> database
```

## Extending it

- **A new field**: add it to `config/field_schema.yaml` with its column and vocabulary.
  The startup audit will tell you immediately if the workbook disagrees.
- **A new practice vocabulary or language**: `config/practice_lexicon.yaml`. Patterns are
  matched against accent-folded text, so `forêt-jardin` and `foret-jardin` both hit.
- **A new database or directory**: `config/sources.yaml`. An entry with
  `access: manual` is logged honestly as unreachable-by-automation rather than skipped.
- **A changed rule**: change it, then run mode `AUDIT` — no network needed — and compare
  `X10_Field_Provenance` before and after. Changes are recorded in `field_change_log`.
