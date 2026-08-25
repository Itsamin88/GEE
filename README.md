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

5. **Wait.** Progress is printed as it goes:

   ```
   [Stage 2/9] Enumerate every page on every address
   [SITEMAP] 42 URLs from https://www.pourgues.org/sitemap.xml
   [DOC] PDF stored: rapport-annuel-2019.pdf (parsed/extracted, 1.2 MB)
   [IMG] research-relevant site plan kept: IC001-IMG0007_site_plan_2016_IC001-S001.jpg
   [BLOCKED] Facebook (IC001-S002) — HTTP 403: login wall
   [CONFLICT] date_intervention_onset: 2016 vs 2019
   ```

6. **Read the summary**, then open the workbook it names.

### If you close PyCharm half way through

Nothing is lost. Press RUN again, enter the same community name, and choose run mode
`RESUME`. The crawl continues from where it stopped.

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
`X4_Document_Register` · `X5_Crawl_Audit` · `X6_Failure_Log` · `X7_Source_Graph` ·
`X8_Review_Queue` · `X9_Discovery_Log` · `X10_Field_Provenance` · `X11_Run_Manifest`

**To audit any value:** find it in `X10_Field_Provenance`, follow its claim ids into
`X2_Claim_Register`, follow the evidence id into `X1_Evidence_Register`, and read the
sentence. The file it came from is in `02_documents/` under its document id.

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
| `config/config.yaml` | Crawl budgets, retries, politeness, image and OCR thresholds |
| `config/field_schema.yaml` | The 88 documentary fields, their vocabularies and where each lands |
| `config/sources.yaml` | Databases, directories, URL paths and query templates |
| `config/practice_lexicon.yaml` | How each of the thirteen practices is recognised, in eight languages |
| `config/decisions.yaml` | Every ambiguity found in the research documents and how it was resolved |
| `.env` | Optional API keys (copy `.env.example`) |

If a value in `config/field_schema.yaml` stops matching the workbook, the program
**refuses to start** and says which column moved. That is deliberate: it is how the
study is protected from a silent change.

---

## Testing it

```
python3 -m pytest tests -q          # the full suite
python3 tools/run_pilot.py          # the two pilot communities, end to end
```

The pilot runs against a local test fixture, not the live web. Its output is stamped
`FIXTURE` and its identifiers are prefixed `TEST-`, so it can never be mistaken for
coded research data.

---

## Further reading

- `docs/ARCHITECTURE.md` — how the system is put together and why
- `docs/RESEARCH_DECISIONS.md` — the ambiguities found in the research documents, and the resolutions
- `docs/OPEN_QUESTIONS.md` — what remains unresolved and needs your decision
- `docs/ADDED_FIELDS.md` — evidence categories added beyond the canonical register
