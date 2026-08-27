# Baseline audit — what the two bundles actually were

Both bundles were restored into clean clones and their suites run **before
anything was changed**, on Python 3.11.15, 4 cores, 15 GB RAM.

| Bundle | HEAD | Tests | Passed | Skipped | Failed | Wall |
|---|---|---:|---:|---:|---:|---:|
| `documentaryresearchcrawlerresumableimagetriagefinal` | `c2728c4` | 310 | 256 | 54 | 0 | 17.3 s |
| `documentaryresearchcrawler30minfinal` | `1db9724` | 414 | 337 | 77 | 0 | 21.3 s |

The 54 and 77 skips are the optional-dependency suites (Playwright, OCR,
`xlrd`, `olefile`, `python-pptx`, `anthropic`) and the live-network cases. Both
bundles start, both export, neither fails on a clean machine.

## They are not two designs

`git merge-base --is-ancestor c2728c4 1db9724` succeeds. The 30-minute bundle's
history **contains the image-triage bundle's HEAD**; it is the same line of work
five commits further on:

```
76dd4f5  deep documentary research crawler        ─┐
c773bed  image triage                              │
2ccfbba  pause, resume, connectivity               │  both bundles
4be433c  researcher controls, estimation           │
8dcb141  idempotent reprocessing                   │
a13f2ed  outage tested against a real crawl        │
28cd7f3  pilot, audit, docs                        │
c2728c4  pause boundaries inside the long stages  ─┘ ← image-triage bundle HEAD
b03676d  export can no longer lose a run's work   ─┐
5591ff7  active-time budget; archive not enumerated│  only the 30-minute
1771a6d  document triage, image caps, stress test  │  bundle
9d6e8a4  measured profiling, yield rewards         │
1db9724  Tamera-shaped pilot, repair, docs        ─┘
```

So "pick the better bundle" is not the real question — the later one strictly
dominates on content and on tests. The real question is **which of its five
additions are sound**, because those five commits are where the observed
production failures were supposedly fixed, and one of them introduced the
regression this rewrite exists to remove.

## Verdict on each of the five late commits

| Commit | What it added | Verdict |
|---|---|---|
| `b03676d` | `export/sanitize.py`, `export/finalise.py` — illegal-character cleaning and a three-rung export retry ladder | **Keep, extend.** The design is right (clean before assignment, verify by reopening). Three gaps remain — see below. |
| `5591ff7` | `budget.py` — a hard 30-minute active-time cap; archive prioritised instead of enumerated | **Split.** The archive prioritisation is correct and stays. The 30-minute cap is the regression: it is the reason evidence was lost, and it is removed. |
| `1771a6d` | `extract/triage.py` — three-phase PDF handling; image caps | **Keep, extend** with document families and adaptive per-community image budgets. |
| `9d6e8a4` | `profiling.py`; yield rewards in the frontier | **Keep, promote.** Yield measurement existed but only steered per-source page budgets. It becomes the run's governing signal. |
| `1db9724` | Tamera-shaped stress fixture, self-audit repairs | **Keep, extend** into the multi-community benchmark. |

## Root causes of the five production failures

### 1. The 30-minute cap lost evidence (`budget.py`)

`DEFAULT_BUDGET_S = 30 * 60`, minus a 3-minute finalisation reserve and a
2-minute wind-down, leaves **25 minutes of retrieval** divided into fixed stage
shares — stage 2 gets 24 % (6 min), stage 4 gets 16 % (4 min), stage 5 gets
14 % (3.5 min). `stage_over_budget()` then truncates a stage at its share
*regardless of what that stage was finding*. A community whose archive was
yielding a dated PDF every forty seconds was cut off at four minutes with the
same rule as one whose archive held nothing. The cap is not sensitive to
evidence at all; the only thing it measures is the clock.

Worse, the shares are **fractions of a constant**. Setting `active_minutes: 90`
does not give the archive more time *when the archive is productive* — it gives
every stage 3× more time whether or not it deserves it. There is no mechanism
in the design by which value earns time.

### 2. The previous crawl ran for hours

The commit before the budget (`c2728c4` and earlier) had no run-level clock at
all. `max_pages_per_source: 400` × the source set, plus 5 000 CDX rows, plus
every discovered PDF parsed deeply, is unbounded in practice. The 30-minute cap
was the reaction to this; it fixed the symptom by taking the steering wheel away
rather than by teaching the crawler what was worth doing.

### 3. Archive retrieval exploded

Found in `discovery/wayback.py::select_snapshots`. The pre-`5591ff7` code
treated the CDX index as a work list. `5591ff7` fixed the largest bug — the
priority-path list contained the site root, `"/".rstrip("/")` is `""`, and
`path.startswith("")` is true of every path, so **every** archived URL was
promoted to priority. That single line is most of why 5 000 URLs looked worth
fetching. The fix is correct and is kept. What is still missing is the tiering
the brief asks for: retrieval depth is a fixed `max_snapshot_fetches_per_domain`
ceiling scaled by stage 4's share of a fixed clock, not a decision driven by
what the archive is actually yielding.

### 4. Image extraction exploded

`images/triage.py` classifies before downloading, which is the right shape. The
budget it enforces is a single global cap per community. A research report with
forty figures and a tourist gallery with four hundred photographs are given the
same allowance, so either the report loses figures or the gallery is admitted.

### 5. Conflict count exploded (5 569 conflicts)

Two distinct causes, one fixed and one not.

*Fixed in `b03676d`/`9d6e8a4`:* `evidence/conflict.py` used to emit one row per
**pair** of disagreeing claims. Two hundred claims with fourteen distinct values
is 19 900 pairs. It now emits one row per distinct *value*, which is O(values)
rather than O(claims²). Verified by `tests/test_conflict_scaling.py`.

*Not fixed:* the values being compared are still semantically unsorted.
`quantities.py` carries a two-way `kind` (`managed` / `total_holding` /
`unclassified`; `permanent` / `visitors` / `unclassified`) and
`resolve_field()` does not use it to partition claims at all. So "200 visitors a
year", "12 permanent residents" and "60 people at the summer gathering" are
three competing values for one `e3_population_value` field, and a translated
copy of the same report contributes the same number again under a different
source id. Most of the residual conflict count is **role confusion and
translation duplicates, not disagreement** — which is precisely what brief §22,
§23 and §24 describe.

### 6. XLSX export failed with `IllegalCharacterError`

`b03676d` addressed this correctly. openpyxl 3.1.5 raises inside
`Cell._bind_value` → `check_string()` at **assignment** time, so the fix has to
sanitise before the value reaches the cell, which `export/workbook.py` now does,
with `sanitise_workbook()` as a post-hoc net and a three-rung retry ladder
behind that.

Three gaps remain, all of them the same shape as the original failure — a value
that dies at `save()` rather than at assignment:

1. **Timezone-aware datetimes.** `openpyxl.utils.datetime.to_excel()` raises
   `ValueError: Excel does not support timezones in datetimes` during `save()`,
   after every sheet has been written. Retrieval timestamps are the obvious
   route in. Nothing in `sanitize.py` looks at datetimes.
2. **Sheet titles.** `sanitise_workbook()` walks cells only. A worksheet title
   carrying a control character or one of `[]:*?/\` fails at save.
3. **No single chokepoint.** Sanitisation is applied by the exporter as it
   writes. Any future code path that writes a cell by another route bypasses it,
   which is how the original bug arrived in the first place.

## What is carried forward unchanged

The evidence model (`Source → Document → Evidence → Claim → Field` with
independence groups), the ten-stage protocol, the source-set architecture from
register v2.4, robots/rate-limit/circuit-breaker handling, the pause/resume state
machine, the workbook audit against the real v6 template, and the eighteen QC
checks are all sound and survive intact. This rewrite is above them, not through
them.
