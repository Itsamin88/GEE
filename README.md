# Deep Documentary Research Crawler

**Stage 1 documentary coding for an academic study of intentional sustainable communities.**

This program finds, retrieves, preserves and structures the documentary evidence that
exists on the open web about one community, and writes it into a copy of
`Stage_1_Documentary_Coding_Workbook_v6` with every value traceable to the sentence
that supports it.

It records **what published sources say**. It does not evaluate ecological performance,
never infers a practice from a photograph, and never estimates an area or a polygon —
those belong to the satellite pipeline and to the researcher's own tracing procedure.

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

4. **Answer the questions.** They are:

   ```
   Community name .......... EcoVillage de Pourgues
   Latitude ................ 43.0561        (optional — press Enter to skip)
   Longitude ............... 1.8342         (optional)
   Country ................. France         (optional, but it improves the search a lot)
   URL 1 ................... https://www.pourgues.org
   URL 2 ................... https://www.facebook.com/pourgues
   URL 3 ................... https://ecovillage.org/projects/pourgues
   URL 4 ................... (press Enter on an empty line to finish)
   Run mode ................ FULL           (press Enter for the default)
   ```

   Paste **every** address you have — the current site, an old domain, Facebook,
   Instagram, YouTube, a directory listing, an academic page. Do not try to decide which
   is primary; the program works that out from what the pages contain. If you have no
   addresses at all, type `NONE` and it will go looking.

5. **Read the estimate.** Before the expensive part, the program looks briefly at
   each address — robots.txt, the sitemaps it names, one home page — and says how
   long the job is likely to take:

   ```
   ESTIMATED WORKLOAD  (an estimate, not a guarantee)
   Estimated active processing time: 40-70 min
   Estimated wall-clock duration:    50-140 min

   Looking briefly at each address to size the job...

   Initial estimate:  40-70 min active
   Updated estimate:  85-125 min active (95-180 min wall-clock)
   Why it changed:    the sitemaps list 612 pages where 75 were assumed

   Start the crawl now? (yes / no) [yes]:
   ```

   *Active processing time* is what the machine spends working. *Wall-clock duration*
   also covers politeness delays, rate limits, slow archives, retries and any time
   spent paused. Neither is a promise.

6. **Wait.** Progress is printed as it goes:

   ```
   [Stage 2/9] Enumerate every page on every address
   [SITEMAP] 42 URLs from https://www.pourgues.org/sitemap.xml
   [DOC] PDF stored: rapport-annuel-2019.pdf (parsed/extracted, 1.2 MB)
   [IMG] research-relevant site plan kept: IC001-IMG0007_site_plan_2016_IC001-S001.jpg
   [BLOCKED] Facebook (IC001-S002) — HTTP 403: login wall
   [CONFLICT] date_intervention_onset: 2016 vs 2019
   ```

7. **Read the summary**, then open the workbook it names.

---

## How long it takes, and what it does when time runs out

A run has a **hard active-processing budget**, thirty minutes by default. It is
not a timeout. A timeout would stop the work and leave you with nothing; this
reserves the part you actually need:

```
|<---------------- 30 minutes of active processing ---------------->|
|<------------ retrieval ------------>|<- wind-down ->|<- finalise ->|
                                      25 min          27 min      30 min
```

- **At 25 minutes** no new expensive work starts. Anything already in flight
  finishes cleanly.
- **At 27 minutes** retrieval stops for good and the reserved time goes to
  reconciliation, the workbook, its verification and the manifests.
- **At 30 minutes** that work is already done.

**Paused time is not spent time.** If you press PAUSE, or the network drops, the
active clock stops. A three-hour outage costs the research budget nothing. And a
resumed run continues *the same* thirty minutes rather than starting a fresh one,
so an interrupted community cannot quietly consume hours across four sessions.

### Complete is not exhaustive

Within half an hour a rich site cannot be followed to the end of every path, and
the program does not pretend otherwise:

| Status | What it means |
| --- | --- |
| `COMPLETE` | Every stage finished and nothing was cut short |
| `COMPLETE_WITH_TRUNCATION` | A usable research record, with what was not reached stated. The clock stopped it, not the sources |
| `PARTIAL_TRUNCATED` | Cut short for another reason — blocks, failures, too few pages |
| `REQUIRES_HUMAN_REVIEW` | Something needs a coder's judgement |
| `FAILED_TECHNICALLY` | No verified workbook could be produced |

A run stopped by its budget is never `COMPLETE`. The completion report says how
much of the budget was used, what remained queued, and which stages never began.

### Spending the time where the evidence is

Rather than crawling every URL it can reach, the crawler spends its minutes on
what yields evidence:

- **Sources** earn more allowance while they keep yielding, and lose it when
  they stop. A source that has just produced a thesis or a restoration report
  earns *more*, because that is where the next minute belongs.
- **Documents** are judged from their address before they are downloaded. A
  thesis, grant report or site plan earns deep extraction; an event flyer or a
  price list does not. A report published in three languages is read once, and
  the other two are kept as provenance mirrors.
- **The archive** is sampled, not enumerated. Five thousand archived URLs is one
  site's navigation captured five thousand times; selection scores each by what
  its path says and by how much its date is worth for onset, and takes what the
  time affords.
- **Images** are triaged before download, with an allowance per document that
  scales with the document's value, and a ceiling on image work overall.

`completion_report.md` ends with a measured breakdown — how many seconds went to
HTTP, PDF parsing, image work, reconciliation and export — so a slow run can be
diagnosed rather than guessed at.

---

## Stopping and starting again

A full crawl can run for a couple of hours. You do not have to sit through it, and you
do not have to kill the process to get your laptop back.

### Pausing on purpose

Three ways in, all of which do the same thing:

| How | What to do |
| --- | --- |
| **Type it at the crawl** | In the Run window, type `pause` and press Enter |
| **Press a button** | `python3 tools/control_panel.py` opens a small PAUSE / RESUME / CANCEL window with live status |
| **From another terminal** | `python3 RUN.py pause` |

The crawl does not stop dead. It finishes what it is doing, writes a checkpoint, and
reports:

```
Manual pause completed safely. 73/141 tasks complete.
Status: PAUSED_MANUAL
```

`resume` (or the RESUME button, or `python3 RUN.py resume`) picks it up from that
checkpoint. `status` prints where it has got to; `cancel` ends the run for good,
keeping everything it found.

### Pausing because the internet went away

This one happens by itself. If the machine loses its connection, the crawler stops
starting new requests, checkpoints, and waits:

```
Internet connection lost at 14:32:11. Crawl paused safely. 73/141 tasks complete.
Waiting for connectivity...
Internet restored at 14:37:26. Resuming from Stage 3 / source S014 / the next
incomplete task.
```

It tells one dead server apart from a dead network by probing several unrelated
sites. A single site refusing is an ordinary research fact and the crawl carries on;
only a machine that can reach nothing at all counts as offline.

**The thing this protects.** A page that was never reached is not a page that holds
nothing. A run stopped by an outage is recorded as `PAUSED_NETWORK`, marked truncated,
and every stage it never began says so — so no NOT FOUND in the workbook can come from
a crawl that simply stopped early.

### If you close PyCharm, or the power goes off

Nothing is lost, and nothing restarts behind your back. The pause state lives in the
database, not in the process, so a run paused on Friday is still paused on Monday.
Press RUN and it says so:

```
UNFINISHED RUN FOUND
  1. EcoVillage de Pourgues - PAUSED_MANUAL at Stage 4 (archived versions) /
     source IC001-02, 73/141 tasks complete, last checkpoint 2026-08-22T16:18:21

  Resume it? (yes / no) [yes]:
```

`python3 RUN.py runs` lists everything unfinished without starting anything.

Resuming continues from the last checkpoint: it does not re-crawl pages already opened,
re-download documents already stored, or re-record evidence already gathered. Stages an
earlier run completed are carried forward rather than repeated (reconciliation always
re-runs, so it sees whatever the resumed run added).

### Pause is not cancel

| | What it means |
| --- | --- |
| **PAUSE** | The run is unfinished and waiting. Resume whenever you like. |
| **CANCEL** | The run is over. Everything already retrieved is kept and can still be exported, but it will not resume by itself. |

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

**It will preserve disagreement.** Where two sources differ, both are kept, the
protocol's rule is applied where one exists, and where none does the case goes to
`X8_Review_Queue` for you rather than being decided quietly.

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
| `COMPLETE` | Every stage finished and every check passed |
| `COMPLETE_WITH_UNCERTAINTY` | Finished, with warnings worth reading |
| `PARTIAL_TRUNCATED` | Stopped before the protocol finished — the report says where |
| `PARTIAL_BLOCKED` | Key sources refused automated reading |
| `FAILED_TECHNICALLY` | A quality check that matters failed |
| `REQUIRES_HUMAN_REVIEW` | Something needs your judgement before the record is usable |

A partial crawl is never labelled complete.

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
