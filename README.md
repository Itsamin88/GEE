# Parallel Documentary Research Crawler

**Stage 1 documentary coding for an academic study of intentional sustainable
communities.**

This program finds, retrieves, preserves and structures the documentary evidence that
exists on the open web about a set of communities — one, twenty, two hundred and
twelve — and writes each into its own copy of
`Stage_1_Documentary_Coding_Workbook_v6`, with every value traceable to the sentence
that supports it.

It records **what published sources say**. It does not evaluate ecological performance,
never infers a practice from a photograph, and never estimates an area or a polygon —
those belong to the satellite pipeline and to the researcher's own tracing procedure.

Two things distinguish this version from the one before it:

**Communities are researched in parallel**, each in its own process with its own
database, so a run of two hundred does not need anyone at the keyboard between
them and a failure in one cannot reach the others.

**Nothing stops at a clock.** A community runs while it is still producing
evidence and stops when it stops producing. The previous version's thirty-minute
cap is gone; on the stress fixture, removing it recovers **4.4× the evidence**
(94 → 412 items) and still terminates.

---

## Running it in PyCharm

1. **Open the project folder in PyCharm.**
2. **Install the dependencies once.** In PyCharm's terminal (Alt+F12):

   ```
   pip install -r requirements.txt
   ```

   Optional extras — a browser for JavaScript-only sites, OCR, legacy Office formats —
   are in `requirements-optional.txt`. You do not need them; the program tells you at
   startup what it has and what it will do without.

3. **Open `RUN.py` and press the green ▶ button.** (Or right-click the file → Run.)

4. **Say how the communities are coming in.**

   ```
   How will you enter the communities?
     1. type them in            — fine for a handful
     2. read them from a file   — CSV or JSON, the usual way for a cohort
   ```

   Nobody types six hundred URLs at a prompt without a mistake, so for a cohort
   use a file. An example is written for you the first time:

   ```csv
   name,country,latitude,longitude,urls
   Tamera,Portugal,37.7167,-8.5333,https://www.tamera.org; https://www.facebook.com/tamera
   EcoVillage de Pourgues,France,43.0561,1.8342,https://www.pourgues.org
   Findhorn,Scotland,,,https://www.findhorn.org; https://en.wikipedia.org/wiki/Findhorn_Ecovillage
   ```

   Only `name` is required. URLs may be one column separated by `;` or `|`, or
   several columns called `url1`, `url2`, `url3` — whichever shape your
   spreadsheet already is. Paste **every** address you have: the current site, an
   old domain, Facebook, YouTube, a directory listing, an academic page. Do not
   try to decide which is primary; the program works that out from what the pages
   contain.

   Typing them in asks the same questions one community at a time:

   ```
   Number of communities: 3

   --- Community 1 ------------------------------------------------
     Name ...................... EcoVillage de Pourgues
     Latitude .................. 43.0561      (optional)
     Longitude ................. 1.8342       (optional)
     Country ................... France       (optional, improves the search a lot)
       URL 1 ................... https://www.pourgues.org
       URL 2 ................... (Enter on an empty line to finish)
   ```

5. **Look at the queue and the estimate.**

   ```
   THE QUEUE
   ID    Community                URLs  Estimated workload   Status
   ----- ------------------------ ----  -------------------- --------
   C001  Tamera                      2  42–160 min           QUEUED
   C002  EcoVillage de Pourgues      1  16–63 min            QUEUED
   C003  Findhorn                    2  19–74 min            QUEUED

   ESTIMATED WORKLOAD  (an estimate, not a guarantee)
     Communities .................. 3
     Total active processing ...... 01:17:00–04:57:00
     Expected wall-clock .......... 00:42:00–01:52:00
     Effective workers ............ 8–16 (≈8.2× a single worker, not 16×)
   ```

   The largest and most promising communities are ordered first, so the run does
   not end with one enormous community holding fifteen idle workers. Waiting
   raises a community's priority, so the small ones are never left behind.

6. **Press START, and go and do something else.** The display stays in one
   place and tells you where things are:

   ```
   ================================================================================
     37 / 212 communities complete
     [################............................................] 17%
   --------------------------------------------------------------------------------
     running 11   queued 164   paused 4   FAILED 1
     runtime 03:24:18   remaining 01:45:00–03:10:00   workers 11 / 11 (max 16)
     network CONNECTED   evidence 18,422   documents 912   images 337   workbooks 37
   --------------------------------------------------------------------------------
     ID    Community            Stage   Progress     Doing
     C044  Sieben Linden        4/9     ####......   archived versions
     C051  Cloughjordan         2/9     ##........   enumerate every page
     ...
   ================================================================================
   ```

   From a second terminal, at any point:

   ```
   dcr pause          stop everything at the next safe boundary
   dcr resume         carry on
   dcr cancel         end the run, keeping everything already found
   dcr pause C007     pause ONE community; its worker goes to the next in the queue
   dcr status         where the run has got to
   ```

7. **Read the summary**, then open the workbooks it names. Each community has its
   own directory with its own workbook in `09_final/`; the run's own record —
   `global_summary.md`, `community_status_table.csv`, `global_error_log.csv` — sits
   beside them.

To research a single community in one process, the way earlier versions did:
`python RUN.py --single`, or `python RUN.py --name "Tamera" --url https://tamera.org`.

---

## How many communities run at once

Between one and sixteen, and the number is **measured rather than configured**.

The governor starts at eight, adds a worker when every worker is busy and the
machine is idle, and cuts immediately under memory pressure — a killed worker
costs a community, while a slow run costs minutes. Above all it watches
throughput per worker-minute: if a higher count completes less per worker-minute
than a lower one, it lowers its own ceiling and does not go looking again.

On this machine (4 logical CPUs, 15.7 GB RAM), sixteen identical communities with
150 ms of latency per request standing in for a real server:

| Workers | Wall-clock | Speed-up | Efficiency | Actually used |
|--------:|-----------:|---------:|-----------:|--------------:|
| 1 | 441.5 s | 1.00× | 100 % | 1 |
| 4 | 142.5 s | 3.10× | 77 % | 4 |
| 8 | 109.5 s | 4.03× | 50 % | 8 |
| 16 | 103.9 s | 4.25× | 27 % | **9** |

**4.25×, not 16×.** Asked for sixteen workers on a four-core machine, the
governor ran nine. Parallel speed-up is never linear, and the estimate you are
shown before pressing START does not pretend otherwise.

Measure your own machine with `python tools/benchmark.py`; it prints the two
coefficients to paste into `config/config.yaml` so the estimate reflects your
hardware.

---

## How long a community takes, and what decides it

**Not a clock.** A community runs while it is still producing evidence, and
stops when it stops producing.

The version before this one had a thirty-minute active-processing cap divided
into fixed per-stage shares, and it truncated each stage at its share whatever
that stage was finding. A community whose archive was handing over a dated
project report every forty seconds was cut off at four minutes by the same rule
as one whose archive held nothing. That is why evidence was lost, and it is what
this version removes.

### What replaces it

The crawler measures what the brief actually asks it to optimise — **useful
independent evidence per active minute**. Every find is credited once, by
identity, and weighted by what it does for the research:

| What was found | Worth |
| --- | ---: |
| A workbook field covered for the first time | 10 |
| Dated onset evidence | 9 |
| An academic record that verified | 9 |
| A source group derived from no other | 8 |
| Land-area evidence with a resolved semantic role | 7 |
| An existing field corroborated from a **new** independence group | 6 |
| A grey-literature record | 6 |
| A practice at documented or evidenced level | 5 |
| A document nobody has seen before, by content hash | 4 |
| A map, site plan or dated intervention photograph | 4 |
| An ordinary supporting passage | 1 |
| Anything already credited | 0 |

A scope — the whole run, one stage, one source, one archived domain — is asked
to stop when its recent rate has fallen **both** below an absolute floor **and**
below a fraction of its own best sustained rate. Judging each scope against
*itself* is what detects diminishing returns: a source that was producing 40
units a minute and is now producing 3 has been worked out, even though 3 is not
nothing.

Nothing here can stop a source that is still producing. The weights and the
floors are in `config/config.yaml`, so a methodologist can change what the
crawler considers worth its time without touching Python.

### What survives from the old clock

**Active seconds are still counted**, because yield is evidence *per active
minute* and something has to count minutes. Time paused by you, or waiting for
the network, is not active time — a three-hour outage costs the research
nothing.

**A finalisation reserve is still held back.** That is not a cap on the
research; it is the guarantee that the research reaches a workbook.

**A safety ceiling is available and off by default.** Set
`budget.active_minutes` if you must bound an unattended overnight run. A
community stopped by it is reported `COMPLETE_WITH_TRUNCATION`, never
`COMPLETE`.

### Complete is not exhaustive — but exhausted is not truncated

| Status | What it means |
| --- | --- |
| `COMPLETE` | Every stage ran, and retrieval ended because the community was worked out |
| `COMPLETE_WITH_UNCERTAINTY` | The same, with quality warnings a coder should read |
| `COMPLETE_WITH_TRUNCATION` | Usable, with parts deliberately not reached — a ceiling, a request, or a source deprioritised for low yield. The report says which |
| `PARTIAL_BLOCKED` | This community's own addresses refused the crawler. The evidence exists and could not be reached |
| `REQUIRES_HUMAN_REVIEW` | Something a machine must not decide |
| `FAILED_TECHNICALLY` | No verified workbook could be produced |

A run the yield governor stopped is `COMPLETE`, because the protocol finished on
the evidence rather than on a clock. Only a ceiling or your own request leaves
work undone.

### Spending the time where the evidence is

- **Sources** earn more allowance while they keep yielding, and lose it when
  they stop. A source that has just produced a thesis or a restoration report
  earns *more*, because that is where the next minute belongs.
- **Documents** are judged from their address before they are downloaded. A
  thesis, grant report or site plan earns deep extraction; an event flyer does
  not. A report published in three languages is read once; the other two share
  its independence group, so they cannot corroborate it.
- **The archive** is retrieved in three tiers. One request lists every URL a
  domain ever had — five thousand of them — and enumeration is not retrieval.
  Tier 1 is deleted documents and historically named pages and is fetched
  whatever the yield has been; tiers 2 and 3 are entered only while the archive
  is still repaying the time, and a tier not entered is recorded as
  `TRUNCATED_LOW_YIELD` rather than passed off as exhaustive.
- **Images** are triaged before download, and a community's allowance is
  **earned**: one whose retained images are mostly site plans, land-use figures
  and dated intervention photographs gets up to three times the base, while one
  producing decoration keeps the base.

`completion_report.md` ends with a measured breakdown — where the seconds went,
what the yield rate was, and the shape of the curve the stopping decision
reacted to.

---

## Stopping and starting again

A run of two hundred communities lasts hours. You do not have to sit through it,
and you do not have to kill the process to get your laptop back.

### Pausing the whole run, or just one community

| How | What it does |
| --- | --- |
| `dcr pause` | Everything stops at its next safe boundary |
| `dcr pause C007` | **One** community stops; its worker goes to the next in the queue |
| `dcr resume` / `dcr resume C007` | Carries on from the checkpoint |
| `dcr cancel` | Ends the run, keeping everything already found |
| `dcr status` | Where the run has got to |
| `python3 tools/control_panel.py` | The same, as buttons |

Nothing stops dead. A community finishes what it is doing, writes a checkpoint,
and reports where it stopped. Pausing one community is the useful case the
previous version could not do: C007 is behaving oddly and you want to look at it,
and the other fifteen workers should not be waiting while you do.

**Paused time is not active time**, so pausing costs the research nothing.

### Pausing because the internet went away

This one happens by itself. If the machine loses its connection, every running
community stops starting new requests, checkpoints, and waits:

```
Internet connection lost at 14:32:11. Crawl paused safely. 73/141 tasks complete.
Waiting for connectivity...
Internet restored at 14:37:26. Resuming from Stage 3 / source S014 / the next
incomplete task.
```

It tells one dead server apart from a dead network by probing several unrelated
sites. A single site refusing is an ordinary research fact and the crawl carries
on; only a machine that can reach nothing at all counts as offline.

**The thing this protects.** A page that was never reached is not a page that
holds nothing. A community stopped by an outage is recorded `PAUSED_NETWORK`,
marked truncated, and every stage it never began says so — so no NOT FOUND in a
workbook can come from a crawl that simply stopped early.

### If you close PyCharm, or the power goes off

Nothing is lost, and nothing restarts behind your back. The queue lives in a
database, so a run interrupted on Friday is still there on Monday. Press RUN and
it says so:

```
PREVIOUS RUN DETECTED
  1. R20260827-141233 (2026-08-27T14:12:33): 212 communities, 37 completed,
     11 active when it stopped, 160 queued, 4 paused

  What would you like to do?
    1. RESUME ALL       continue where it stopped
    2. RETRY FAILED     resume, and try the failed communities again
    3. EXPORT           rebuild workbooks from stored evidence, no network
    4. RECONCILE        redo reconciliation from stored evidence, no network
    5. AUDIT            check evidence and workbooks offline
    6. NEW RUN          leave it untouched and start something else
```

and then says exactly what resuming would do, before doing it:

```
  Resuming this run would:
    11 community(ies) were active when the run stopped and will be requeued;
       each resumes from its own last checkpoint rather than from the beginning
    160 still queued
    37 already complete and will NOT be re-run: their workbooks are written
       and verified
    4 paused by the researcher and will be LEFT paused; resuming one is a
       separate choice
```

Three rules hold, and they are why recovery reads the queue rather than the
filesystem — a half-written workbook looks exactly like a finished one from the
outside:

- **A community that was RUNNING when the power went is requeued.** Nothing was
  watching it and its worker is gone. Its own crawl resumes from its checkpoint,
  so this costs the tail of one stage, not the community.
- **A community you PAUSED stays paused.** It was stopped on purpose, and
  restarting it would be the software overruling your decision.
- **A community that COMPLETED is never re-run.** Its workbook exists and has
  been verified.

### Recovery that touches no network

The expensive part is the crawl. When it succeeded and only the cheap part
failed, re-fetching the web to fix a spreadsheet would be absurd:

```
dcr export        rebuild the workbooks from stored evidence
dcr reconcile     redo reconciliation from stored evidence
dcr audit         check evidence, sources and workbooks offline
dcr retry-failed  put the failed communities back in the queue
```

Each takes an optional community id — `dcr export C017` — to act on one.

### Pause is not cancel

| | What it means |
| --- | --- |
| **PAUSE** | Unfinished and waiting. Resume whenever you like. |
| **CANCEL** | Over. Everything retrieved is kept and can still be exported, but it will not resume by itself. |

---

## What you get

Everything lands in one folder per community:

```
Research_Web_Crawler_Output/IC001_EcoVillage_de_Pourgues/
├── 01_raw_sources/     the exact HTML of every page opened
├── 02_documents/       every downloaded file, named by document id
├── 03_images/          retained images, each traceable to its source
├── 04_archives/        files retrieved from web-archive snapshots
├── 05_extracted_text/  plain text pulled out of pages and documents
├── 06_tables/          tables from PDFs and spreadsheets, as CSV
├── 07_evidence/        evidence exports
├── 08_logs/            run.log and the machine-readable events.jsonl
├── 09_final/           the workbook, the manifests and the report
├── 10_debug/           diagnostic output
└── README_run.md       what is in each folder
```

`09_final/` holds the deliverables:

| File | What it is |
| --- | --- |
| `IC001_..._Stage1_Documentary_Coding.xlsx` | The workbook, filled in |
| `completion_report.md` | What was searched, what was found, what was not |
| `run_manifest.json` | Versions and hashes of everything used, for reproducibility |
| `source_manifest.csv` | One row per address, with its independence group |
| `evidence_manifest.csv` | Every passage behind every value |
| `image_manifest.csv` | Every image kept, and why |
| `image_candidates.csv` | Every image *seen*, kept or not, and the reason for the decision |
| `interruptions.csv` | Every pause, outage and resume, in order |
| `document_manifest.csv` | Every file, its hash and its parser status |
| `search_log.csv` | Every database consulted, including the empty ones |
| `claims.jsonl` | Every claim, before reconciliation |
| `conflicts.jsonl` | Every disagreement between sources |
| `review_queue.jsonl` | Cases where a machine decision would be a bad one |
| `errors.jsonl` | Every failure, with its cause |

### The workbook

It is a copy of your own `Stage_1_Documentary_Coding_Workbook_v6`, with its sheet names,
columns, dropdowns and formulas intact. The program **refuses** to write into a formula
cell, into a column that belongs to you (the polygon columns, your coordinates), or a
value that a dropdown does not allow — and it tells you when it refuses.

It also appends supplementary sheets, prefixed `X`, for evidence the canonical workbook
has nowhere to put:

`X1_Evidence_Register` · `X2_Claim_Register` · `X3_Image_Evidence` ·
`X3b_Image_Triage` · `X4_Document_Register` · `X5_Crawl_Audit` · `X6_Failure_Log` ·
`X7_Source_Graph` · `X8_Review_Queue` · `X9_Discovery_Log` · `X10_Field_Provenance` ·
`X11_Run_Manifest`

**To audit any value:** find it in `X10_Field_Provenance`, follow its claim ids into
`X2_Claim_Register`, follow the evidence id into `X1_Evidence_Register`, and read the
sentence. The file it came from is in `02_documents/` under its document id.

---

## Images: what is kept, and what it proves

A community photo gallery can run to several hundred megabytes of accommodation shots,
sunsets and event photos, with one site plan buried in the middle. Downloading all of it
to find that plan wastes an afternoon, so the crawler works the other way round:

```
discover candidates -> read the metadata the page already gave us -> classify
    -> prioritise -> download the ones worth keeping -> provenance -> link to evidence
```

Nothing is fetched until it has earned it. Candidates are ranked into four bands:

| Band | What is in it |
| --- | --- |
| **HIGH** | Site plans, master plans, land-use and zoning maps, restoration and planting plans, water-system and contour diagrams, before/after pairs, figures in documents, dated intervention photographs |
| **MEDIUM** | Captioned or dated field photographs with research context |
| **LOW** | Decoration: logos, portraits, accommodation shots, generic event and landscape photos |
| **DUPLICATE** | The same address, or the same bytes, already triaged |

HIGH and MEDIUM are downloaded; the default is set in `config.yaml` under
`images.download_priorities`.

**Everything seen is recorded, including what was passed over.** The register notes that
gallery captions and file names often carry dates that no text on the site provides, so a
skipped candidate's metadata is still research material — and keeping the ledger is what
makes the triage auditable, instead of something you have to take on trust. It is in
`X3b_Image_Triage` and `image_candidates.csv`.

Figures inside PDFs, Word files and slide decks are triaged too, and keep their page
number, figure number, caption and the parser that extracted them.

### A photograph is not a practice code

This is the rule that matters, and it comes from the register (v2.4, rule 12), not from
the software. An image of green rows does not evidence mulching, polyculture or no-till.
Only a caption or surrounding text that *states* the practice does that.

So each kept image records two separate things:

- **`visual_evidence_allowed`** — what the picture alone may support. For a dated
  photograph of a physical structure (a swale, a pond, a planted block) that is V4 visual
  documentation, and no more.
- **`documentary_text_support`** — the sentence that would license a claim, quoted, or
  `NOT FOUND`.

Priority is about bandwidth, never about proof: a HIGH-priority image is one worth
fetching first, and that says nothing about what it evidences.

---

## Run modes

| Mode | What it does | When to use it |
| --- | --- | --- |
| `FULL` | All ten stages, every address | **The default.** Every community gets this first |
| `SOURCE` | Stages 0–4 and 7 on one address only, deeper | After FULL reported an address as skimmed |
| `ACADEMIC` | Academic, grey literature and local language only | A community likely to have been studied |
| `RESUME` | Continues an interrupted run | PyCharm closed, the laptop slept |
| `RETRY_FAILED` | Retries only the failed and blocked addresses | A site was down when you first ran it |
| `RECONCILE` | Merges previous runs without re-fetching | A community split across several runs |
| `AUDIT` | Re-runs validation and reconciliation offline | You changed a rule and want the effect |
| `EXPORT` | Rebuilds the workbook and reports from the database | You want the outputs again, without crawling |

`AUDIT` and `EXPORT` need no internet at all.

---

## What it will and will not tell you

**It will say when it does not know.** A field with no supporting source is `NOT FOUND`,
not a plausible number. A database that could not be reached is recorded as
`unreachable`, never as "no results". A run that stopped early sets
`crawl_truncated = yes` and says exactly why. An absence of evidence and an absence of
effort are recorded differently, because they mean opposite things.

**It will preserve disagreement — and it will not manufacture it.** Where two
sources differ, both are kept, the protocol's rule is applied where one exists,
and where none does the case goes to `X8_Review_Queue` rather than being decided
quietly.

But claims about different things are not competing claims. "Around 200 visitors
a year", "12 permanent residents" and "60 people came to the summer gathering"
are three facts, not three candidate populations; "the property is 134 hectares"
and "we cultivate 4 hectares" are two figures about two different things. Every
claim carries a **semantic role**, read from the sentence rather than asserted by
the extractor, and claims with different roles are never compared. Only the role
a field is actually about may be written to it; a figure whose role cannot be
determined goes to a coder rather than to a cell.

A publication date, an event date and an archive snapshot date are properties of
the **source**, and can never reach a field about the community.

**It counts voices, not addresses.** A community's website, its Facebook page and a
directory listing copied from it are **one** source, not three. The number that matters
is `independence_groups`.

**It will not invent an academic citation.** A paper or thesis may support a value only
after its record has been retrieved and its title matched in the same run. Unverified
records are stored, marked `verified_resolves = no`, and barred from coding.

**A photograph is never a practice code.** An image is preserved as an artefact with its
provenance, and the manifest records both what the image alone may evidence and which
sentence — if any — would license a claim from it.

---

## The completion status

Every community ends in exactly one of:

| Status | Meaning |
| --- | --- |
| `COMPLETE` | Every stage ran, every check passed, and retrieval ended because the community was worked out |
| `COMPLETE_WITH_UNCERTAINTY` | The same, with warnings worth reading |
| `COMPLETE_WITH_TRUNCATION` | Parts deliberately not reached — a safety ceiling, your own request, or a source deprioritised for low yield. The report says which |
| `PARTIAL_BLOCKED` | This community's own addresses refused the crawler |
| `FAILED_TECHNICALLY` | No verified workbook, or a quality check that matters failed |
| `REQUIRES_HUMAN_REVIEW` | Something needs your judgement before the record is usable |

A partial crawl is never labelled complete — and a crawl that finished because
there was nothing left to find is never labelled partial.

---

## Configuration

You should not need to touch any of this, but nothing is hidden:

| File | What it controls |
| --- | --- |
| `config/config.yaml` | The active-time budget and its per-stage shares, crawl budgets, retries, politeness, document and image triage, run control, connectivity probes, time-estimation costs |
| `config/field_schema.yaml` | The 88 documentary fields, their vocabularies and where each lands |
| `config/sources.yaml` | Databases, directories, URL paths and query templates |
| `config/practice_lexicon.yaml` | How each of the thirteen practices is recognised, in eight languages |
| `config/decisions.yaml` | Every ambiguity found in the research documents and how it was resolved |
| `.env` | Optional API keys (copy `.env.example`) |

If a value in `config/field_schema.yaml` stops matching the workbook, the program
**refuses to start** and says which column moved. That is deliberate: it is how the
study is protected from a silent change.

The settings most worth knowing about:

| Setting | Default | What it does |
| --- | --- | --- |
| `images.download_priorities` | `[HIGH, MEDIUM]` | Which triage bands are worth the bandwidth |
| `run_control.manual_pause_behavior` | `wait` | `wait` keeps the process alive for RESUME; `exit` checkpoints and returns |
| `run_control.max_offline_wait_s` | `0` | How long to wait for the network. `0` means indefinitely |
| `run_control.failures_before_probe` | `3` | Consecutive network-shaped failures before a connectivity probe is worth making |
| `connectivity.probes` | four operators | The endpoints that decide offline from partial |
| `estimation.costs` | per unit of work | Seconds per page, document, query and image; corrected by what previous runs actually took |
| `budget.active_minutes` | `30` | The hard ceiling on active processing per community |
| `budget.finalisation_reserve_minutes` | `3` | Held back for reconciliation, export and verification. Never borrowed |
| `budget.stage_shares` | per stage | Ceilings, not allocations: a stage that finishes early hands the rest back |
| `documents.max_per_family` | `1` | How many languages of one report are read in full |
| `archive.max_snapshot_fetches_per_domain` | `40` | Further reduced by what stage 4's time actually affords |
| `images.max_images_per_document` | `12` | Default per-document allowance; scales with the document's priority |

---

## Testing it

```
python3 -m pytest tests -q          # the full suite
python3 tools/run_pilot.py          # the two pilot communities, end to end
python3 tools/self_audit.py         # the forty audit questions, answered from a pilot run
```

The pilot runs against a local test fixture, not the live web. Its output is stamped
`FIXTURE` and its identifiers are prefixed `TEST-`, so it can never be mistaken for
coded research data.

It also rehearses the interruptions, in a workspace of its own: a crawl paused mid-flight
and resumed the next "morning", and a crawl whose network is switched off underneath it
and then switched back on. Those two matter more than the happy path, because a pilot
that only ever runs to completion proves nothing about what happens when it does not.

`tools/self_audit.py` then answers forty questions from the code and that run — twenty
operational (can an outage end the run falsely, does a pause survive a restart, are
decorative images avoided) and twenty on research integrity (can a value be fabricated,
can a citation be invented, can silence be mistaken for absence). A `NO` is a defect to
fix, not a caveat to note.

---

## Further reading

- `docs/ARCHITECTURE.md` — how the system is put together and why
- `docs/RESEARCH_DECISIONS.md` — the ambiguities found in the research documents, and the resolutions
- `docs/OPEN_QUESTIONS.md` — what remains unresolved and needs your decision
- `docs/ADDED_FIELDS.md` — evidence categories added beyond the canonical register
