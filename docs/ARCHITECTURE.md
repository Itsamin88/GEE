# Architecture

## Two ideas

**The database is the record; the workbook is a report.** Everything retrieved is
stored locally with its provenance the moment it arrives. The workbook, the
manifests and the completion report are all generated from that store, so they
can be rebuilt at any time, offline, without re-fetching anything. That is what
makes it possible to change a coding rule and see the effect, add a field,
re-parse a document, or audit a value two years later.

**Evidence buys time; the clock only counts it.** Nothing decides how long to
keep working from a clock. A community runs while it is still producing
evidence and stops when it stops producing, and every allocation in the system —
a source's page budget, an archive tier, a stage's share — is earned from what
that scope has actually been finding.

---

## The shape of a run

```
                        ┌──────────────────────────┐
                        │   RunSession (parent)    │
                        │                          │
   communities  ───────>│  plan      size & order  │
   (typed or a file)    │  store     the queue     │──> run.sqlite3
                        │  scheduler who runs next │
                        │  governor  how many      │
                        │  hosts     politeness    │
                        │  dashboard what you see  │
                        └────────┬─────────────────┘
                                 │ spawn, one per community
             ┌───────────────────┼───────────────────┐
             ▼                   ▼                   ▼
      ┌────────────┐      ┌────────────┐      ┌────────────┐
      │  worker    │      │  worker    │      │  worker    │
      │  C001      │      │  C002      │      │  C003      │
      │            │      │            │      │            │
      │ the ten-   │      │ the ten-   │      │ the ten-   │
      │ stage      │      │ stage      │      │ stage      │
      │ engine     │      │ engine     │      │ engine     │
      └─────┬──────┘      └─────┬──────┘      └─────┬──────┘
            ▼                   ▼                   ▼
   IC001_.../research.sqlite3, 09_final/IC001_....xlsx  (one each, shared with nobody)
```

Everything above the workers schedules. Everything inside one is the
single-community engine, unchanged from the version before this one.

### Why processes

The brief asks for the choice to be reasoned rather than fashionable (§41), and
three properties decide it.

**Failure isolation.** A malformed PDF can take a C parser down with a
segmentation fault, which no `except` will catch. In a thread that ends the run;
in a process it ends one community — the parent reads the exit code, records
`FAILED_TECHNICALLY`, and gives the slot to the next in the queue.

**The GIL.** Retrieval is I/O-bound and belongs in one event loop, which is what
the engine already does. PDF text extraction, image hashing and perceptual
comparison are CPU-bound, and sixteen communities doing those in threads would
take turns rather than run.

**Windows.** There is no `fork`, so `spawn` is the only option — used on every
platform, so the behaviour under test on Linux is the behaviour in PyCharm on
Windows.

One process per community, started fresh and discarded, rather than a pool of
reused workers: a reused worker carries whatever the last community did to it
into the next one. The cost is about a second of imports against a community
that takes twenty minutes.

### Two kinds of database, and why

| | Holds | Written by |
| --- | --- | --- |
| `run.sqlite3` | The queue: which communities exist, what state each is in, what it produced, what the scheduler decided | The parent, only |
| `<community>/research.sqlite3` | That community's sources, documents, evidence, claims and field values | That community's worker, only |

Nothing else opens a community's database. A half-written transaction, a corrupt
page, a disk full at exactly the wrong moment — none of it can reach another
community, because no other process has the file open (§8, §39). It also means
sixteen workers are not queueing behind one SQLite writer lock, which is the
difference between parallelism and the appearance of it.

Because each database numbers its own communities, the parent allocates the
`site_id` (`IC001`…) up front and the worker is told which one to use. Otherwise
two hundred and twelve databases would each call their one community `IC001`.

### The scheduler

```
  age the queue        waiting must be worth something
  ask the governor     how many workers this machine can take
  fill the slots       claim the highest-priority runnable community
  drain the events     write down what the workers said
  reap the dead        a crash is one community, not the run
  check for controls   PAUSE ALL / RESUME ALL / CANCEL ALL / PAUSE C007
```
every second, until the queue is empty.

**Fairness.** Priorities are on a 0–100 scale — largest and most valuable first,
so no huge community runs alone at the end holding fifteen idle workers. Waiting
adds a point a minute up to 110, deliberately **above** the full range, so a
community that has waited long enough outranks anything that arrived after it
however large. A cap below the range would have been starvation with extra steps.

**Concurrency is measured, not configured.** The governor starts at eight, grows
one at a time while every worker is busy and the machine is idle, cuts
immediately under memory pressure, and — the part that matters — watches
throughput per worker-minute. A count that completes less per worker-minute than
a lower one lowers its own ceiling, and it does not go looking again (§97).

**Politeness across communities.** Sixteen communities is not sixteen requests.
Most hosts are not shared, so brokering them would be pure overhead; the handful
every community reaches — `web.archive.org`, the academic indexes, the search
endpoints — go through one broker in the parent, which holds each to its own
concurrency and delay and tightens both when a host answers 429. A missing or
broken broker degrades to crawling as one community would, which is the correct
failure direction.

---

## When a community stops

`yieldmeter.py` measures **useful independent evidence per active minute**. Each
find is credited once, by identity key, and weighted by what it does for the
research; a repetition earns nothing. Scopes nest — run, stage, source, archived
domain — and one second of work is charged to every account it belongs to.

A scope stops when its recent rate has fallen **both** below an absolute floor
**and** below a fraction of its own best sustained rate. The second condition is
the diminishing-return detector: 40 units a minute falling to 3 is exhaustion
even though 3 is not nothing, and judging each scope against itself is what
stops a rich source being held to a poor one's standard.

`budget.py` keeps only what a clock is still needed for: active seconds with
pause and outage time excluded, the finalisation reserve that guarantees a
workbook, soft per-stage allocations the estimator predicts from, and an optional
safety ceiling that is **off by default**.

Retrieval ending is no longer synonymous with truncation:

| Cause | Status |
| --- | --- |
| The yield governor: every scope went quiet | `COMPLETE` |
| A configured safety ceiling | `COMPLETE_WITH_TRUNCATION` |
| The researcher asked | `COMPLETE_WITH_TRUNCATION` |

---

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
  yieldmeter.py            evidence per active minute — the stopping rule
  budget.py                the active-processing clock (it measures; it no longer decides)
  profiling.py             where the seconds actually went
  supervisor.py            the one gate that decides whether the crawl continues
  estimate.py              workload and runtime estimation
  console.py               pause/resume/cancel typed at the running crawl
  evidence/                the evidence model, quantities, practices, onset, independence,
                           conflicts, semantic roles, document families, the optional LLM layer
  export/                  workbook, manifests, completion report,
                           sanitisation and the finalisation retry ladder
  qc/                      the eighteen checks and the coverage matrix

  orchestrator/            MANY communities at once — everything else does one
    store.py               the run-level database: the queue, and nothing else
    plan.py                sizing, ordering, identity, the scalability model
    scheduler.py           who runs next, and what happens when one dies
    governor.py            how many workers this machine can actually carry
    hosts.py               per-host politeness ACROSS communities
    pool.py                the worker processes, and surviving their deaths
    worker.py              the child process: one community, start to workbook
    events.py              what a worker tells the scheduler while it works
    dashboard.py           what the researcher sees
    recovery.py            picking a run back up after the machine was switched off
    session.py             the run, end to end, and its own outputs
    prompts.py             what the researcher is asked, and how little of it there is
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

## The finalisation reserve

The one time-shaped guarantee that survives. A crawl that spends everything
retrieving and then dies writing the spreadsheet has produced nothing, which is
exactly what happened before this was added.

```
   retrieval, for as long as it is producing evidence
        │
        ▼  the yield governor, a ceiling, or the researcher
   wind-down   nothing new starts; work in flight finishes
        │
        ▼
   finalisation   reconcile, export, reopen, verify, manifests
```

`supervisor.gate()` moves between these at every safe boundary, and `affords()`
refuses to begin a task whose expected cost would eat the reserve. This is not a
cap on the research: it is the guarantee that the research reaches a workbook.

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
| Archive tiers | `discovery/wayback.select_snapshots_by_tier` | Sorts the index by what each snapshot IS. Tier 1 (deleted documents, historical paths) is always fetched; tiers 2 and 3 only while the archive is still repaying the time |
| Image triage | `images/triage.py` | Classified from page metadata before download, with a per-document allowance |
| Image allowance | `crawl/crawler.image_allowance` | EARNED: a community whose retained images are mostly site plans and dated intervention photographs gets up to three times the base |
| Semantic roles | `evidence/roles.py` | A visitor count never competes with a resident count, and a publication date never becomes an intervention date |
| Document families | `evidence/families.py` | Three translations of one report are one report, sharing one independence group |

**The archive bug worth remembering.** `priority_paths` contains `"/"`, which
`rstrip("/")` turns into `""`, and `path.startswith("")` is true of every path.
Every one of five thousand archived URLs was therefore a "priority path", got
annual sampling, and competed for retrieval slots. The root is now matched
exactly.

## Disagreement is summarised, evidence is not — and most of it was never disagreement

The reported run ended with 5 569 conflicts. Two separate causes, both fixed.

**One row per competing VALUE, not per competing claim.** Fourteen figures across
four hundred claims is thirteen disagreements, not 79 800 pairs. Each row carries
how many claims and independence groups stand behind each side; the claims keep
their own wording and source in the `claims` table.

**Claims about different things are not competing claims.** Every claim carries a
semantic role read from its sentence, and claims with different roles are never
compared:

```
  "around 200 visitors a year"            visitor            ─┐
  "12 permanent residents"                resident           ─┼─ NOT four
  "60 people at the summer gathering"     event_attendance   ─┤   competing
  "we employ 4 people"                    employee           ─┘   populations
```

Only `resident` may reach `e3_population_value`. `publication`,
`event` and `archive_snapshot` describe the SOURCE and can never reach a field
about the community — which is §108's requirement that a publication date never
becomes an intervention date, enforced rather than audited for.

Measured end to end: 2 000 claims across six kinds of count, which the old shape
would have made 1 999 000 pairwise rows, now produce fewer than five.

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
