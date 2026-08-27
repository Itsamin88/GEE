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
                           MIME sniffing, optional browser rendering, connectivity
  crawl/                   URL normalisation and traps, frontier and adaptive budget,
                           platform profiles, the crawl engine
  discovery/               sitemaps and feeds, web archive, academic, grey, search engines
  extract/                 HTML, PDF, Office, spreadsheets, text, and the dispatcher
  images/                  relevance classification, and the triage ledger
  control.py               run state: pause, resume, cancel, checkpoints
  budget.py                the active-processing clock and its reserve
  profiling.py             where the seconds actually went
  supervisor.py            the one gate that decides whether the crawl continues
  estimate.py              workload and runtime estimation
  console.py               pause/resume/cancel typed at the running crawl
  evidence/                the evidence model, quantities, practices, onset, independence,
                           conflicts, the optional LLM layer
  export/                  workbook, manifests, completion report,
                           sanitisation and the finalisation retry ladder
  qc/                      the eighteen checks and the coverage matrix
```

## Stopping, and starting again

Three things stop a long crawl before the protocol finishes: the researcher asks, the
network goes away, or the machine does. None of them is an absence of evidence, and the
difference between them matters to the finished research — so each is a distinct state
with its own recorded reason.

```
RUNNING ──pause requested──> PAUSING ──safe boundary──> PAUSED_MANUAL
   │                                                          │
   ├──connection lost──> PAUSED_NETWORK ──restored──> RESUMING ┘──> RUNNING
   │
   ├──cancel requested──> CANCELLING ──> CANCELLED
   │
   └──stages finished──> COMPLETED
```

**One gate.** `supervisor.gate()` is asked at every safe boundary — the crawler at each
batch, the runner at each stage — whether the next piece of work may start. A safe
boundary is a point where nothing is half-written: the previous task is committed and
the next has not been claimed. Keeping the decision in one object is what stops manual
pause and network pause drifting apart, and it is why a pause leaves nothing `in_flight`.

**The state is in the database, the request is in a file.** The file (`control/*.request`
under the output root) is what lets a second process reach a crawler busy inside an
await — `dcr pause` in another terminal, or the button panel. The database is what lets
the state survive the machine being switched off: a run paused on Friday is still paused
on Monday, and the application offers to resume it rather than quietly starting a new
crawl.

**Offline is not the same as unreachable.** A single refusing server is an ordinary
research fact, and that source's record says so. A machine that can reach nothing is an
operational state. The monitor probes several unrelated operators to tell them apart,
and while the machine is offline the fetcher's circuit breaker is suspended — otherwise
an outage would be written down as a finding about every live site the crawl happened to
be visiting, and the circuits opened during it would outlive it.

**RUNNING never means finished.** A run left RUNNING is what a power cut looks like from
the outside. It is offered for resume, and anything left `in_flight` in the frontier is
re-queued.

## Images: triage before download

The pipeline is `discover -> metadata -> classify -> prioritise -> download -> provenance`.
Candidates are classified from what the page already said about them — alt text, caption,
surrounding text, file name, declared dimensions — and only HIGH and MEDIUM bands are
fetched.

Every candidate is recorded in `image_candidates`, including the ones passed over. That
is partly auditability and partly research: the register notes that gallery captions and
file names often carry dates no text on the site provides, so a skipped candidate's
metadata is still worth keeping.

**Priority is not evidence rank, and neither is a licence to code.** `priority`
(HIGH/MEDIUM/LOW/DUPLICATE) decides what is fetched first. What an image may evidence is
decided separately in `images/classify.py`, and a photograph never sets a practice code:
each image records what it alone may support and, separately, the sentence that would
license a claim — or `NOT FOUND`.

## Estimating the work

Before the expensive crawl, `estimate.py` builds a workload from the addresses supplied,
then `discovery/probe.py` spends three or four requests per address — robots.txt, the
sitemaps it names, one home page — and the estimate is rebuilt with a sentence saying
what moved it. Active processing time and wall-clock duration are reported separately as
bands; the difference is politeness delays, rate limits, retries and time spent paused.
Recorded actuals from previous runs calibrate later estimates through a clamped median,
so one pathological run cannot distort the model.

## The time budget, and why it reserves rather than stops

A crawl that spends its whole allowance retrieving and then dies writing the
spreadsheet has produced nothing, which is exactly what happened before this was
added. So the budget is not a timeout:

```
|<---------------- active budget (default 30 min) ----------------->|
|<----------- retrieval ----------->|<- wind-down ->|<- finalise -->|
```

`supervisor.gate()` enforces it at every safe boundary, and `affords()` refuses
to begin any task whose expected cost would eat the reserve. Running out is a
normal ending: the run reconciles what it has, exports, verifies, and reports
COMPLETE_WITH_TRUNCATION.

Time spent paused or offline does not count, and the clock is persisted, so a
resumed run continues the same budget instead of starting a fresh one.

## Finalisation cannot be skipped

```
crawl -> reconcile -> sanitise -> export -> reopen and verify -> manifests -> status
```

The workbook is reopened from disk and checked — core sheets present, coded rows
present, formulas still formulas, not zero bytes — before the run is allowed to
call itself finished. If that fails, a ladder runs: retry with aggressive
sanitisation, then write the core workbook with the supplementary evidence
sheets omitted and a notice in each saying where its rows still are. A
supplementary sheet cannot take the workbook with it.

Only the Excel representation is ever cleaned. The raw extracted text stays in
the database and in `05_extracted_text/`, because the workbook is a report and
the database is the record.

## Spending minutes where the evidence is

Efficiency here comes from prioritisation and deduplication, never from
discarding provenance.

| Decision | Where | What it does |
| --- | --- | --- |
| Source allowance | `crawl/frontier.SourceBudget` | Grows while a source yields, shrinks when it stops, and grows again when it produces a thesis or a report |
| Document priority | `extract/triage.py` | Judged from the address before download; decides deep extraction and the image allowance |
| Document families | `extract/triage.py` | One language of a report is read in full; the others are provenance mirrors |
| Archive selection | `discovery/wayback.select_snapshots` | Scores by path relevance and dating value, caps documents at four captures, limits the navigation share, and takes what the stage's time affords |
| Image triage | `images/triage.py` | Classified from page metadata before download, with a per-document allowance and a global ceiling |

**The archive bug worth remembering.** `priority_paths` contains `"/"`, which
`rstrip("/")` turns into `""`, and `path.startswith("")` is true of every path.
Every one of five thousand archived URLs was therefore a "priority path", got
annual sampling, and competed for retrieval slots. The root is now matched
exactly.

## Disagreement is summarised, evidence is not

One conflict row per competing VALUE, not per competing claim. Fourteen figures
across four hundred claims is thirteen disagreements, and each row carries how
many claims and independence groups stand behind each side. The claims
themselves keep their own wording and source in the `claims` table: what is
summarised is the disagreement, never the evidence.

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

**Reprocessing is idempotent.** A pause, a retry and a resumed run all reach the same
passage again. Evidence and claims carry a `dedupe_key`, so each time the answer is the
same row rather than another copy. The key is one sentence, in one place, in one
artefact — character offsets are excluded, because the same passage is often recorded
once by a pass that knows where it sits and once by a pass that does not. The same
sentence found on a *different* page is still separate evidence: that is corroboration,
and collapsing it would quietly weaken the independence counts.

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
