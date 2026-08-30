# Validation report — `Paper1_Final_Only_Ecovillages_Master_Input.csv`

**Status: the file is finished as a crawler input. One environment limit
remains and is not disguised anywhere in it.**

212 communities, 51 columns, 1,307 seed addresses. Coordinates are the
researcher's own verified values. The nine columns that carried the export's
unresolved geocoder candidates have been removed. Three new columns tell the
crawler what to do with each address: which sites to walk in full, and which
query strings to run the literature harvest with.

**What is still owed: not one URL has been opened over HTTP.** The egress proxy
in this container answers `403 Forbidden` to `CONNECT` for every research host,
re-tested at the end of this pass against both `ecovillage.org` and
`api.openalex.org`:

```
CONNECT ecovillage.org:443 HTTP/1.1
< HTTP/1.1 403 Forbidden
* CONNECT tunnel failed, response 403
```

So `seed_url_validated_count`, `seed_url_dead_count`, `seed_url_blocked_count`
and `seed_url_duplicate_count` are **empty on every row, not zero**. Empty means
not measured; zero would be a measurement, and a false one. The crawl itself —
the whole-site walks and the literature harvest this pass was built for — runs
on a machine with outbound HTTPS. Everything needed for it is in place and
tested offline.

**One value to check before you run it.** `IC206` Sadhana Forest Kenya pairs
candidate 4's latitude (`0.867336`) with candidate 1's longitude (`36.765913`),
so the returned point is not any of the four the export offered — about 4 km
from candidate 4, whose longitude is `36.806313`. That has the shape of a
spreadsheet fill slip rather than a deliberate choice. Your value is used
exactly as supplied; it is flagged because it is cheaper to check now than after
a crawl. Both other previously-unresolved rows (Grishino, Rodnoe) came back as
exactly the candidate this pipeline's own analysis had pointed at.

---

## 1. Cohort integrity

| Check | Result |
|---|---|
| Communities in the original export | 212 (from 314 data rows) |
| Communities in the master file | **212** |
| Deleted | 0 |
| Merged | 0 |
| Invented | 0 |
| Original name preserved verbatim | 212 / 212 |
| Original coordinate recoverable | 212 / 212 |
| Original file modified | no — `Paper1_Final_Only Ecovillages.csv` is byte-identical, sha256 `6e39c841…` |

Ten names carried double mojibake (cp1252 → UTF-8 applied twice, in one case
with HTML escaping on top). All ten are repaired in
`community_name_normalized`, flagged by `name_repair_applied = yes`, and the
damaged original is kept in `community_name_original`, which is also the join
key back to the export.

Two rows are near-duplicates of each other by identity — seq 1
`Soheili Village_Hara` and seq 163 `Soheili Village` both appear to be the
village on Qeshm Island beside the Hara mangroves. Both are **retained**, as
required, and the relationship is stated in the notes on each.

## 2. Coordinates

| | Count |
|---|---|
| `researcher_verified` | 34 |
| `source_export_single_row` | 178 |
| Rows whose coordinate this build altered | **0** |

The export gave four geocoder candidates each for the last 34 communities in
file order and chose none. Those 34 were checked by hand and returned as one
pair per community; `master_input/pipeline/final_coordinates.csv` is that
answer, and the build takes it verbatim — a test compares every row in the
master file against it and fails on any difference.

The nine columns that carried the unresolved candidates
(`coordinate_primary_rule`, `coordinate_candidate_count`,
`coordinate_candidate_spread_km`, `coordinate_candidates`, `coordinate_status`,
`latitude_as_exported`, `longitude_as_exported`, `coordinate_confidence`,
`coordinate_evidence`) have been removed, and a test fails if any reappears.
They described a problem that no longer exists, and a stale `coordinate_status`
in a crawler input invites a reader to trust something that no longer describes
anything.

Worth recording, because it bears on the earlier analysis: this pipeline had
resolved 31 of the 34 by identifying that the export's slot 3 was a
nearest-large-city decoy and slot 4 was the community, then verifying each pick
against that community's own published address. It left three open. Two of
those three — Grishino and Rodnoe — came back from the researcher as **exactly
candidate 4**, the slot that analysis had pointed at. That is an independent
check on the method, arrived at by a different route.

## 3. Country

| | |
|---|---|
| Rows with a country | **212 / 212** |
| Distinct countries | 57 |
| Confidence HIGH / MEDIUM | 204 / 8 |
| Determined from the community name | **0** |

Country was established from coordinates first — an offline k-nearest vote over
the GeoNames gazetteer (cities ≥ 15,000; k = 5) — then checked against published
administrative geography, official sites and institutional records. The
gazetteer's own verdict is kept in `country_gazetteer_code` even where it was
overruled, so every override is visible.

Eight countries were corrected against the gazetteer vote on published
evidence, each flagged `country_corrected_from_gazetteer`. Two are worth
naming: **Almost Heaven Farms** voted India because the farm sits within a few
kilometres of the Mechi border and every nearby town is in Darjeeling or
Sikkim — GEN, Good Market and the local business record all place it in Ilam,
**Nepal**. **Cité Écologique** voted Canada because Colebrook is in the Great
North Woods and every nearby town above the size threshold is Québécois; its
French name is not evidence either, since it is the New Hampshire offshoot of a
Quebec parent. It is in the **United States**.

## 4. Global Ecovillage Network (§5–§8, §35–§37)

**The fixed network seed is on every row without exception.**

| Check | Result |
|---|---|
| `gen_global_url` = `https://ecovillage.org` on all 212 rows | ✅ |
| `gen_global_status` = `FIXED_GLOBAL_SOURCE` on all 212 | ✅ |
| The seed appears in `urls` on all 212 | ✅ |
| `gen_global_url` ever treated as proof of GEN registration | ❌ never |
| `gen_independence_group` = `G1` on all 212 | ✅ |

The last row is the one that matters for §8: the global URL and a community's
own GEN profile sit in the **same** independence group, so a community whose
only sources are its own site and its GEN listing counts as **one** voice, not
three. 21 rows are flagged `single_independence_group` for exactly that reason.

Community page status:

| Status | Count |
|---|---|
| `VERIFIED_COMMUNITY_SOURCE` | 164 |
| `VERIFIED_COMMUNITY_SOURCE_LEGACY_HOST` | 4 |
| `VERIFIED_COMMUNITY_SOURCE_IDENTITY_UNCERTAIN` | 3 |
| `VERIFIED_COMMUNITY_SOURCE_SUBPAGE_ONLY` | 3 |
| `VERIFIED_COMMUNITY_SOURCE_PARENT_ONLY` | 2 |
| `NOT_FOUND` — searched, no page exists | 36 |
| `NOT_SEARCHED` | **0** |

**No GEN URL was ever constructed.** That is not a claim of restraint; the
slugs make guessing impossible, and this pass turned up four that prove it:

* `/project/dubravushka` — Zeleni Kruchi is filed under the name it dropped in 2018.
* `/ecovillage/fruit-haven-ecovllage-ecuador/` — GEN's own typo, missing an `i`.
* `/project/chambalabamba-2/` — an internal disambiguator.
* `/project/green-canvas-light/` — silently drops the word "of".

Earlier passes found `/ecovillage/seaview-performing-arts-center/` for
HawaiiSPACE and `/ecovillage/sustainability-insitute/`, another GEN typo. No
rule derives any of these from a community name.

A defect found and fixed during this pass belongs here: a discovery entry
marked `NOT_SEARCHED` was being silently rewritten to `NOT_FOUND` when the row
was built — exactly the failure register v2.4 field I12 warns against, absence
of effort presented as absence of evidence. `step3` now preserves the
distinction, a test guards it, and the four entries that had hit that path were
re-researched with real `site:ecovillage.org` queries rather than left to the
default.

## 5. Seed source set (§9–§11, §19–§22)

| | |
|---|---|
| Total addresses | **1,307** |
| Mean per community | 6.17 |
| Range | 2 – 9 |
| Within the 3–10 target band | **206 / 212** |
| Two or more independent groups | **191 / 212** |
| Mean independence groups | 3.17 |

The six rows below three addresses are below it because the evidence is thin,
not because a quota was waived — §10 forbids inventing to reach a number. Each
says so in `qc_notes`: Bali Ecovillage could not be tied to any organisation
at all and carries **only** the network seed rather than a plausible-looking
Bali project attached to a generic name.

Source classes present (register v2.4 §S):

| Class | Rows |
|---|---|
| S1 academic | 36 |
| S2 institutional | 93 |
| S3 network / directory | 207 |
| S4 community's own | 156 |
| S5 archived | 5 |
| S6 journalism | 108 |
| S7 social | 51 |
| S8 direct communication | 1 |

Ranking (§39) puts the strongest community-specific source first and the GEN
global seed **last** on every row, so a peer-reviewed article always outranks
the network URL. 36 rows lead with an S1 academic source; 74 with an S2
institutional one.

## 5b. The crawl policy — depth of extraction

Two limits in the crawler meant a list of good addresses still produced a thin
extraction. Both are fixed, and the master file now carries the instructions.

### Walking the community's own site in full

A directory listing is one page about a community, and the right thing to do
with it is read it and follow what it points at. The community's **own** site
is a different object: the gallery, the newsletter archive going back fifteen
years, annual reports as PDFs, the land-use plan nobody linked from the front
page. Sampling the second the way you sample the first loses exactly the
material a documentary study exists to find.

| | Count |
|---|---|
| `EXHAUSTIVE_SITE_AND_ACADEMIC` | 159 |
| `ACADEMIC_EXHAUSTIVE_ONLY` | 53 |
| Site roots to walk in full (`deep_crawl_urls`) | **208** |

The 53 in the second group are communities where no site of their own was
found — mostly small projects whose whole public presence is a GEN page and a
Facebook account. There is nothing to walk in full; the literature harvest still
runs exhaustively.

What the two scopes differ by, per address:

| | `targeted` | `exhaustive` |
|---|---|---|
| base pages | 40 | 500 |
| max pages | 400 | 25,000 |
| max depth | 6 | 25 |
| pagination pages | 60 | 1,000 |
| images per source | 400 | 4,000 |
| assets | evidence-bearing only | **everything: images, PDFs, documents** |

`max_pages_per_run` rose from 4,000 to 40,000, because a 25,000-page source
budget behind a 4,000-page run ceiling would have been a lie.

An exhaustive walk still **stops**: its exhaustion window is widened, not
removed, because a newsletter archive can be forty barren pages of links before
the first PDF — but a site that has genuinely run out of pages ends the walk
like any other. "Exhaustive" must not mean "never terminates".

Two details worth naming. The deep targets are **site roots**, not pages:
discovery had recorded the single most useful page on each site, and a crawler
told to walk the whole site and handed
`tamera.org/water-retention-landscape/` starts three levels down and reaches
the archive only by luck. And `ecovillage.org` is never a deep target — it is
212 communities' shared directory, and walking it in full would crawl the whole
Global Ecovillage Network once per community without reaching a word of that
community's own voice. (`ecovillage.org.in`, Govardhan Ecovillage's own domain,
*is* walked in full: the check is on the host, not a substring. A test caught
that distinction.)

### Harvesting the whole literature

Every academic database was asked **once, for fifty rows**, and that was the
literature. For a community with six papers that is complete. For Tamera,
Damanhur or Cloughjordan — each discussed in hundreds of works — it returned
whichever fifty an API happened to rank first and looked exactly like a
complete answer. That is the failure register v2.4 field I12 exists to name:
absence of effort presented as absence of evidence.

| | |
|---|---|
| Academic APIs that now page | **15 of 15** |
| Grey-literature APIs that now page | 4 |
| Records reachable per database per query | 100 × 20 pages = **2,000** |
| Query strings supplied by the master file | **2,266** (10.7 per community) |

That is 8 core databases plus the 7 national thesis-portal APIs the crawler
adds for the community's own country — which is where a country-specific thesis
actually lives, and so where the gap would have hurt most for a non-English
community.

Each database is paged **in its own units**. Sending a page number where an API
wants a record offset silently re-reads the first window and looks exactly like
exhaustion, so OpenAlex, DOAJ, OpenAIRE and DataCite take page numbers while
Crossref, Semantic Scholar, CORE, HAL, theses.fr, BASE and the DNB's SRU take
offsets. Paging stops when a page adds nothing new, which is the honest end of a
result set — some APIs clamp an out-of-range page to the last one rather than
returning empty, so *repeats*, not emptiness, are the signal.

A test written for this found a real gap in it: **BASE had no paging rule**, so
that database alone would have silently capped at one window. It is in now, and
the test fails if anyone adds an API to `sources.yaml` and forgets its paging
entry.

The query strings are written into the file rather than re-derived at crawl
time, which is what makes the literature search reproducible: a reader can see
precisely which strings were searched, and a community that turns up nothing can
be told apart from one that was never asked about properly. Every name the
community is known by becomes a query, because **the literature does not agree
on names** — Khula Dhamma is published as Khula Dharma, Ecovila Raiz do Anuhmas
as Anhumas, Zeleni Kruchi under Dubravushka. A test fails if any recorded
alternative name is missing from the harvest.

## 6. Review queue (§38)

**64 rows** carry `review_required = yes`, each with machine-readable reasons:

| Reason | Rows |
|---|---|
| `identity_confidence_below_high` | 35 |
| `single_independence_group` | 21 |
| `gen_page_qualified` | 12 |
| `country_corrected_from_gazetteer` | 8 |
| `gazetteer_split` | 8 |
| `thin_source_set` | 6 |

The two coordinate reasons are gone: with verified coordinates in hand, no row
is still asking about them. A test fails if either reappears.

Findings a coder should see before analysis, all flagged in the file:

* **Ecovila Santa Margarida (seq 176) is not an intentional community.** Every
  source identifies it as a 192-unit residential condominium launched in 2021
  by a developer trading as "Eco Vila Incorporadora" — four towers, a heated
  pool, a cinema, a sports court. The row is **retained** as required, but
  including it would bias any cohort statistic. It sits about 2 km from seq 175
  Ecovila Raiz do Anuhmas, which is a genuine community, and the shared
  "Ecovila" prefix is the likely route by which it entered the list.
* **Agatha Amani House (seq 212) is a refuge for survivors of sexual and
  domestic violence.** It appears in GEN because it runs permaculture on site.
  Publishing precise coordinates or identifying imagery could put residents at
  risk. The row carries a safeguarding note; that consideration should override
  the rest of the protocol for this site.
* **The Possibility Alliance (seq 194) was electricity-free by choice** — no
  grid connection and no solar array — so it has no night-lights signal and no
  photovoltaic signature at all, and their absence must not be read as the
  community's absence. Multiple sources report it relocated from Missouri to
  Maine; the site should not be assumed occupied for the later study period.
* **Hockerton's five houses are earth-sheltered** and will read from above as a
  grassed bank. A built-up classifier will likely record no construction there.
* **Sadhana Forest Haiti and Kenya** plant across thousands of scattered family
  plots, not on their campus parcels. A point-anchored reading misses the
  intervention almost entirely; the right unit is the municipality or county.
* **Brithdir Mawr was discovered in 1998 by an aerial survey** that
  photographed sunlight glinting off a solar panel — a community found by
  remote sensing, which bears directly on this study's own method.

## 7. Crawler compatibility (§25, §26, §42)

The crawler's real input parser is `read_community_file()` in
`src/dcr/orchestrator/session.py`. It was read, not assumed, and tested against
this file.

| Check | Result |
|---|---|
| Communities loaded | **212 / 212** |
| Addresses delivered | 1,307 |
| Rows with a name, coordinates and a country | 212 |
| Every row's last URL is the GEN seed | ✅ |
| Deep-crawl roots surfaced to the crawler | 208 |
| Academic query strings surfaced | 2,266 |
| Policy columns are optional (a plain sheet still loads) | ✅ |

The reader takes the eight crawler columns plus the three policy columns and
ignores the other forty — those are provenance and QC for the researcher, not
instructions. The policy columns are optional by design: a two-column sheet of
names and URLs still loads and simply gets the standard treatment for every
address, which a test checks.

One parser detail that mattered: search terms are split **only** on the pipe.
"Baireni, Udayapur" is one query string, and splitting it the way an address
list is split would search "Baireni" and "Udayapur" separately, quietly losing
the disambiguation that makes the query work. A test asserts that at least one
term in the cohort contains a comma, so the guard cannot rot into a tautology.

**The original export would have loaded as zero communities.** Its header says
`Ecovillage_Name`; the parser wanted `name`. Three further defects were found
and fixed in the parser, each with a regression test:

1. Any column whose key merely *started with* `url` was swept into the address
   list, so `url_verification_method` would have been crawled as an address.
2. `csv.Sniffer` was trusted unconditionally and mis-detected the delimiter on
   files containing quoted commas.
3. A single URL containing a comma — ordinary in query strings — was split into
   two broken addresses.

`" | "` was chosen as the address delimiter specifically because `csv.Sniffer`
weighs only `,`, `;` and tab, so it cannot mis-fire on it.

## 8. Format conformance (§27, §28)

| Check | Result |
|---|---|
| Valid CSV, `QUOTE_MINIMAL` | ✅ |
| UTF-8, no BOM | ✅ |
| CRLF line endings | ✅ 213 (header + 212) |
| Consistent row length | ✅ 51 fields on every row |
| Parses with `csv` | ✅ |
| Parses with `pandas` | ✅ |
| Opens in Excel | not tested — no Excel here. The file meets the requirements (valid CSV, CRLF, `QUOTE_MINIMAL`), but note it is UTF-8 **without** BOM, which some Windows builds of Excel mis-render for non-ASCII names unless the file is imported rather than double-clicked. A BOM was left off because a BOM is not part of UTF-8 and trips many naive parsers; this crawler is not one of them — prepending a BOM was tested and it still reads all 212 rows. |
| Embedded commas, semicolons, quotes, non-ASCII survive | ✅ |
| Query-parameter URLs survive | ✅ |
| Address list reconstructs deterministically from `seed_sources_json` | ✅ |
| Separate QC file created | ❌ none — QC is inside this CSV, as §23 requires |

Size 1,005,871 bytes. 51 columns.

## 9. Automated checks

**`tests/test_master_input.py` — 42 tests.** Written as falsifiable claims, not
smoke tests:

* the coordinates are the researcher's verified ones, compared row by row
  against their own file;
* the nine candidate columns are gone, and none may reappear;
* the 34 rows a human checked say so, and they are exactly `IC179`–`IC212`;
* every deep-crawl target is a bare site root, not a page;
* the network seed is never walked exhaustively;
* `deep_crawl_urls` and the per-source `crawl_scope` cannot disagree;
* every alternative name a community is known by is actually searched;
* search terms survive the reader intact, commas and all;
* the fixed network seed is on every single row;
* absence of a GEN page is never dressed up as a search having been run;
* GEN never counts as an independent second voice;
* no community GEN URL was invented;
* the address list reconstructs exactly from the structured column;
* the crawler reads all 212 communities, and the original export would too.

**`tests/test_deep_crawl_and_harvest.py` — 15 tests** on the two new
capabilities:

* an exhaustive source is not abandoned for a quiet stretch — and still stops;
* the two scopes actually differ in budget, depth, pagination and assets;
* the run-wide page ceiling can hold an exhaustive walk (a 25,000-page source
  budget behind a 4,000-page run limit would have been a lie);
* page zero is byte-identical to the request that was always made, so paging is
  purely additive and nothing regresses;
* each database is paged in its own units — page numbers and record offsets are
  not interchangeable;
* **every API database in `sources.yaml` has a paging rule.** This is the test
  that found BASE missing, and the one that fails when someone adds a database
  and forgets.

Full suite: **578 passed**, 114 skipped, 3 failed. The three failures are in
`tests/test_extraction.py` and are pre-existing container problems — a missing
`reportlab` and a broken `_cffi_backend` behind `cryptography` — untouched by
and unrelated to this work.

## 10. What a reader should not conclude from this file

* **That any address resolves.** None has been fetched. The four validation
  columns are empty for that reason and must stay empty until the crawl runs.
* **That the extraction has happened.** This file is the *input* to it. It says
  which sites to walk in full and which queries to run; it does not contain the
  images, documents or papers those will produce.
* **That a `NOT_FOUND` GEN status means a community is not in GEN.** It means no
  community page was returned by a `site:ecovillage.org` query. Several of the
  36 are demonstrably in the network — Arterra Bizimodu is a GEN Europe full
  member and hosts GEN Europe's office; Ecodorp Bergen is reported as the first
  Dutch initiative to hold full membership. GEN's site structure and its
  membership are not the same thing.
* **That a thin row means a thin community.** Register field I12
  (`crawl_truncated`) exists precisely so that absence of effort is never
  mistaken for absence of evidence, and rows where the record is genuinely
  sparse say so in `qc_notes` rather than looking merely unremarkable.
* **That 2,000 records per database per query will all be relevant.** It is a
  reachable ceiling, not an expectation. The relevance scoring and the
  verification requirement in `config/config.yaml` still apply to every record,
  and an unverified one goes to the review queue rather than to the workbook.
