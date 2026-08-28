# Validation report — `Paper1_Final_Only_Ecovillages_Master_Input.csv`

Built 2026-08-28. Schema version 1.0.0. Original export preserved unmodified at
`master_input/Paper1_Final_Only Ecovillages.csv`.

---

## 1. The headline, stated first

**212 of 212 communities are in the file, and every one carries the mandatory
`https://ecovillage.org` seed. Source discovery was completed for 99 of them.
The other 113 are in the file with their identity, coordinates and a
gazetteer-derived country, explicitly marked `discovery_status = PENDING` — not
silently blank.**

Two environment limits, neither of them a property of the data, produced that
split. Both are stated here rather than in a footnote, because a reader who
does not know about them would misread the file.

### Limit 1 — the session's web-search budget ran out

Discovery used two searches per community: one general, one
`site:ecovillage.org "<name>"` for a defensible GEN answer. The session's cap of
200 `WebSearch` calls was reached at community 99. The remaining 113 are marked
`PENDING` and `gen_community_status = NOT_SEARCHED`.

`NOT_SEARCHED` is deliberately not `NOT_FOUND`. Register v2.4 field I12 exists
for exactly this: a community searched for four minutes and a community
searched exhaustively that genuinely has nothing arrive as identical thin
records, and they mean opposite things — one is an absence of evidence, the
other an absence of effort. Only one of them is a finding.

To finish: raise `CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION`, run
`python3 master_input/pipeline/step4_resume_discovery.py --list-pending` for the worklist, and
rebuild with `python3 master_input/pipeline/step3_build_master.py`. Completed rows are never
re-fetched.

### Limit 2 — the egress proxy blocked every research host

The session's outbound HTTPS goes through a policy-enforcing gateway that
answered **403 to CONNECT** for `ecovillage.org`, `wikipedia.org`, `doi.org`,
and every community website tried. `WebSearch` was unaffected (it does not use
that path), so discovery is real: every URL in this file was returned by a
search engine, with a title and a content summary that identified the
community. But **no address in this file has been fetched over HTTP.**

The file therefore records what actually happened:
`seed_url_verification_method = search_index`, and
`seed_url_validated_count` / `dead` / `blocked` / `duplicate` are **empty, not
zero**. Zero would be a claim; empty is the truth.

`master_input/pipeline/step5_validate_urls.py` performs the HTTP pass and writes
`http_status`, `final_url`, `content_type`, `crawl_status` (O11 vocabulary) and
`checked_at` into `seed_sources_json` beside each address, then rolls the four
counts up. Run it where the network is open — or change this environment's
network policy (Claude Code on the web → environment → network access) and run
it here.

---

## 2. Cohort integrity

| Check | Result |
|---|---|
| Communities in the original export | 212 unique names across 314 rows |
| Communities in the master file | **212** |
| Communities deleted, merged or invented | **0** |
| Original coordinates recoverable from the file | **314 of 314** |
| Duplicate `community_id` | 0 |
| Duplicate (name, coordinate) rows | 0 |
| Ragged rows / column shifts | 0 |
| UTF-8 round trip | passes |
| BOM | absent |

### The original file, audited

Structurally a valid CSV: 315 lines, all 14 columns wide, UTF-8, CRLF, no BOM,
no embedded line breaks, no blank rows, all coordinates parse and are in range.
All four URL columns × 10 were empty and all `Country` cells were empty.

Three content faults were found and handled:

**1. Double mojibake in 10 names.** The export was decoded as cp1252 and
re-encoded as UTF-8 twice, with non-breaking spaces flattened to spaces in
between and one smart quote HTML-escaped. `La CittÃ  della Luce` is bytes
`C3 83 20 20`, which is `à` plus the original space with the NBSP damage on top.
All ten repairs, with the original preserved beside each:

| Original | Repaired |
|---|---|
| `Sat Yoga Ashram &amp; Wisdom School` | Sat Yoga Ashram & Wisdom School |
| `Oasis du Coq Ã  lâ€™Ã‚me` | Oasis du Coq à l'Âme |
| `ECOlonie â€&quot; Centre Ecologique International` | ECOlonie – Centre Ecologique International |
| `CommunautÃ© de lâ€™Arche de Saint-Antoine` | Communauté de l'Arche de Saint-Antoine |
| `SÃ³lheimar Iceland` | Sólheimar Iceland |
| `La CittÃ  della Luce` | La Città della Luce |
| `Hertha LevefÃ¦llesskab/Hertha Living` | Hertha Levefællesskab/Hertha Living |
| `Avalon Organic Gardens &amp; EcoVillage` | Avalon Organic Gardens & EcoVillage |
| `Eco Aldeia do Vale â€&quot; Instituto Permacultura` | Eco Aldeia do Vale – Instituto Permacultura |
| `ComunitÃ  rigenerative` | Comunità rigenerative |

The repair function is idempotent and each output was checked against the
community's own published name during discovery.

**2. One truncated name.** Row 29 reads `Co-housing project HASENDORF (= bunny`
— an unbalanced parenthesis. GEN's page for the community gives the full name,
`Co-housing project HASENDORF (= bunny village)`. The truncated original is
preserved verbatim; the normalised column carries the complete name on GEN's
authority.

**3. Thirty-four communities with four coordinates each.** 34 names appear four
times, with candidate coordinates **27 to 101 km apart** (median ≈ 58 km). At
most one of each set can be the site. All 136 rows are preserved: the first
occurrence becomes the row's primary coordinate under an explicit,
non-substantive rule (`coordinate_primary_rule = first_source_row`), all four
are listed in `coordinate_candidates`, and every one of the 34 rows carries
`coordinate_status = MULTIPLE_CANDIDATES_UNRESOLVED` and
`review_required = yes`.

> **A lead, offered as a lead and not as a finding.** In the handful of these
> that discovery happened to reach — among them Cité Écologique (New Hampshire),
> Habiba Community and Cloughjordan Ecovillage — the **fourth** candidate is the
> one matching the community's published location, and the first three are tens
> of kilometres off. If that pattern holds it would resolve all 34. It has not
> been verified community by community, and transferring a factual result from
> one community to another without independent verification is exactly what the
> brief forbids, so nothing in the file acts on it. It is recorded here because
> checking 34 fourth-candidates is a short job for someone with a map.

---

## 3. Country

| | |
|---|---|
| Communities with a country | **212 of 212** |
| Distinct countries | **58** |
| Canonical representation | ISO 3166 English short name, one spelling per country |
| Machine-readable pair | `country_iso2`, `country_iso3` on every row |
| Rows where two independent signals agree | **95** (`HIGH`) |
| Rows resting on one signal, or on a correction | **105** (`MEDIUM`) |
| Rows resting on a non-unanimous gazetteer vote alone | **12** (`LOW`) |

Country was never inferred from the community's name. The primary signal is an
offline gazetteer vote: for each of the 314 coordinates, the five nearest
populated places (GeoNames ≥ 15 000, bundled with `geonamescache`) vote on the
country, and both the winner and the vote's own quality are carried into the
file. Fully reproducible from the repository; no coordinate leaves the machine.

Vote quality across all 314 coordinates: **UNANIMOUS 284 · MAJORITY 19 ·
SPLIT 11**. Every one of the 11 splits is a genuine border, gulf or lake case —
Kibbutz Lotan and Neot Semadar across the Gulf of Aqaba, Better In Belize on the
Guatemalan border, Vlierhof and Land van Aine on the Dutch–German line, Torri
Superiore near the French and Monegasque borders, Almost Heaven Farms on the
Nepal–India line, and all four Habiba candidates in the Sinai.

**Four countries were corrected against the gazetteer on published evidence**,
each flagged `country_corrected_from_gazetteer`:

| Community | Gazetteer said | Corrected to | Why the gazetteer was wrong |
|---|---|---|---|
| Kibbutz Lotan | Jordan | **Israel** | Jordanian towns across the Gulf of Aqaba are nearer than Israeli ones |
| Better In Belize | Guatemala | **Belize** | Guatemalan towns sit just west of the border |
| Schloss Glarisegg | Germany | **Switzerland** | Radolfzell lies across the Untersee |
| Vlierhof | Netherlands | **Germany** | GEN's own site address is Kleve-Keeken, Germany; only the postbox is Dutch |

One administrative correction did not change the country: **Cambium** is in
Fehring, **Styria**, not Burgenland. Two further placements conflict with their
coordinate and are flagged rather than resolved: **Hågaby** (the GEN ecovillage
of that name is at Uppsala; the coordinate is ~190 km away near Kumla) and
**The Garden** (GEN says Lafayette; the coordinate is ~40 km east near Celina).
**Stowe Farm Community** is in Colrain, **Massachusetts**, not Vermont, though
it sits on the state line.

---

## 4. The Global Ecovillage Network requirement

| | |
|---|---|
| Rows carrying `https://ecovillage.org` as `gen_global_url` | **212 of 212** |
| Rows carrying it inside `urls` | **212 of 212** |
| `gen_global_status` | `FIXED_GLOBAL_SOURCE` on every row |
| **Verified community-specific GEN pages** | **92** |
| — clean `/project/` or `/ecovillage/` or `/map/community/` page | 87 |
| — legacy host (`gen.ecovillage.org`) | 1 |
| — sub-page only, parent not constructed | 2 |
| — parent/umbrella listing only | 1 |
| — page exists but identity uncertain | 1 |
| Searched, no GEN page exists | **7** |
| **Not yet searched** | **113** |
| GEN URLs constructed or guessed | **0** |

The seven searched-and-absent: Soheili Village_Hara, Cabiokid Foundation, Green
Commune Belica, DNS The Necessary Teacher Training, Windekind Commons, Dancing
Rabbit Ecovillage, Ixixtlan. Each carries the negative-search evidence in
`gen_evidence_note`.

**No GEN URL was constructed, and the file demonstrates why that rule matters.**
Real slugs found by search include `/project/tamera-0/` (an arbitrary `-0`
suffix), `/ecovillage/seaview-performing-arts-center/` for a community called
**HawaiiSPACE**, and `/project/global-community-communications-all-0/` for one
called **Avalon Organic Gardens & EcoVillage**. None is derivable from the
community's name. GEN also serves community pages under four different path
shapes; the shape actually found is recorded rather than normalised.

**Independence.** Every GEN address — global and community-specific alike —
carries `independence_group = G1`, the community's own voice. A GEN profile is
self-submitted, so it corroborates the community's website rather than
confirming it, and the global page can never count as a second source beside a
community profile. The test suite asserts this on every row.

---

## 5. The seed source set

| | |
|---|---|
| Total seed addresses | **761** |
| Distinct addresses | **550** |
| Community-specific addresses (excluding the 212 mandatory GEN globals) | **549** |
| Addresses appearing under more than one community | **0** |
| Addresses per researched community — min / median / mean / max | **2 / 7 / 6.55 / 9** |
| Researched communities with 3–10 addresses | 98 of 99 |
| Researched communities with fewer than 3 | 1, flagged |

No quota was met by padding. Where a community genuinely had little, the row
says so: `thin_source_set` (1 row) and `single_independence_group` (5 rows).

### By source class (register S1–S8, community-specific addresses)

| Class | What it is | Count |
|---|---|---|
| S1 | Academic — papers, theses, university repositories | **17** |
| S2 | Institutional — government, NGO, certification, grant records | **78** |
| S3 | External network or directory profile | **195** |
| S4 | The community's own current material | **137** |
| S5 | Archived / former-domain material | **3** |
| S6 | Journalism and documentary media | **92** |
| S7 | Social media and member accounts | **27** |
| S8 | Direct communication | 0 (not applicable to a source table) |

### By platform type (workbook O11 vocabulary)

directory listing **185** · other **147** · own website **122** · news outlet
**34** · Facebook **17** · secondary or former website **15** · booking or
hosting **11** · blog platform **8** · YouTube **5** · Instagram 2 · LinkedIn 2
· crowdfunding 1.

Social and video together are 26 addresses out of 549 — under 5%. They were
added only where the account is demonstrably the community's own and likely to
carry dated material (a YouTube channel sorted oldest-first is a dated record;
an empty Instagram is not).

### Address confidence

HIGH **376** · MEDIUM **156** · LOW **17**.

### Independence groups — the number that actually matters

| | |
|---|---|
| Groups per researched community — min / mean / max | **1 / 3.46 / 6** |
| Communities reaching the register's "three independent sources" target | **76 of 99** |
| Communities whose entire source set is one voice | **5**, all flagged |

The register is explicit that corroboration counts groups, never URLs. A
community with a website, a Facebook page, an Instagram account and a GEN
listing has **one** channel of self-documentation, not four. That is why this
table reports 3.46 groups against 6.55 addresses.

### Sources worth naming

Discovery turned up material well beyond directory listings, which is the point
of the exercise:

* **Government and registry records** — the French Ministry of Housing
  ÉcoQuartier file for Oasis du Coq à l'Âme; the French open business registry
  entry (SIREN 379340524) for ECOlonie; the Canton Thurgau heritage-database PDF
  for Schloss Glarisegg; Minnesota's state disability-services register for
  Camphill Village Minnesota; Saxony-Anhalt's state feature on Sieben Linden;
  Bonjour Québec for Cité Écologique.
* **Peer-reviewed and academic** — an economic analysis of the Tamera Water
  Retention Landscape; *npj Climate Action* (2024) on Danish ecovillages; a
  Tufts case study of Sirius and its town; a University of Brighton publication
  drawing on the **Braziers Park archive**; the **UMass Amherst Special
  Collections finding aid for the Sirius Community papers**.
* **EU and international institutions** — the BASE adaptation platform and
  Spain's AdapteCCa on Tamera; European Social Fund Plus on Suderbyn; Horizon
  HOUSEFUL on Cambium; NOBEL GRID on Meltemi; UNCCD on Govardhan; UNEP Champions
  of the Earth on SEKEM; the UN SDG partnership register on Biosphere
  Foundation; REScoop and the EU Energy Community Platform on Belica.
* **Dated land instruments** — Whole Village's 999-year conservation easement;
  the permanent easement over West Haven Farm at EcoVillage at Ithaca via the
  Finger Lakes Land Trust; the 1986 transfer of Artosilla by the Government of
  Aragón; the 2001 purchase of the Jahnishausen estate; Hearthstone Village's
  move-in on 8 January 2019; the October 1963 purchase of the 57-acre East
  Nantmeal farm by The Camphill School.
* **Published plans and drawings** — Taman Petanu's site master plan; Living
  Well's landscape-architecture project record; einszueins architektur's
  documentation of Wohnprojekt Hasendorf; Dancing Rabbit's quantified land page
  (six ponds, 40 acres woodland, 12,000+ trees on 30 acres, ~20 acres restored
  prairie).
* **Former identities**, each a distinct search string the crawler would
  otherwise miss: Sunseed was **Green Deserts**; Stowe Farm was **Katywil**;
  The Garden was **Shut Up and Grow It**; EcoVillage de Pourgues now continues
  as **Bloom Hills**.

---

## 6. Review queue

**133 of 212 rows** carry `review_required = yes`. Reasons overlap; counts are
per reason.

| Reason | Rows |
|---|---|
| `discovery_pending` | 113 |
| `gen_not_searched` | 113 |
| `country_not_web_verified` | 113 |
| `multiple_coordinate_candidates` | 34 |
| `identity_confidence_below_high` | 12 |
| `gazetteer_split` | 8 |
| `single_independence_group` | 5 |
| `gen_page_qualified` | 5 |
| `country_corrected_from_gazetteer` | 4 |
| `thin_source_set` | 1 |

Of the 99 researched communities, **20 are flagged** and 79 are clean.

---

## 7. Crawler compatibility

Verified against the real reader, `read_community_file()` in
`src/dcr/orchestrator/session.py`, not against an assumption about it.

| Check | Result |
|---|---|
| Rows loaded | **212 of 212** |
| Communities with a usable name | 212 |
| Address lists reconstructed exactly | 212 of 212, byte-identical |
| Addresses truncated, split or merged | 0 |
| Spurious entries in the queue | 0 |
| Coordinates parsed | 212 |
| Countries resolving to a ccTLD for the local-language sweep | 212 |
| `mode` accepted by `MODE_STAGES` | 212 |
| `build_plan()` sizes and orders the cohort | 212 jobs, 212 distinct `site_id` |
| `https://ecovillage.org` classified as `directory`, not `website` | yes |

### Three parser faults found and fixed

Testing the real file against the real reader found three defects that would
each have damaged this run. All three are fixed in
`src/dcr/orchestrator/session.py`, and the full existing suite still passes
(554 passed; 3 pre-existing failures are missing PDF libraries in this
container, untouched by these changes).

**1. Any column beginning with `url` became an address.** The reader collected
values from every key matching `key.startswith("url")`. A QC column named the
obvious way — `url_count` — would have put its own value into the crawl queue,
and the frontier would have tried to fetch `7`. Now only `urls`, `url` and
`url<digits>` are addresses. The schema also avoids the trap independently, so
the file is safe against an unpatched copy of the reader.

**2. The delimiter sniffer could silently choose the wrong character.** A
`urls` cell holding a `;`-separated list can contain more semicolons than the
header row has commas; `csv.Sniffer` then reads the whole file as
semicolon-delimited, finds no `name` column, and returns **zero communities
with no error at all**. The sniffed dialect is now checked against the header
and discarded if it does not yield a name column. The file additionally uses
`" | "`, which the sniffer does not consider.

**3. A single address containing a comma was split in two.** The splitter fell
through to comma-splitting whenever no `;` or `|` was present, so
`https://maps.example.org/?bbox=1,2,3,4` became four fragments. Comma-splitting
now only fires when every resulting piece still looks like an address. The file
contains several comma- and query-string addresses that exercise this.

### Two further fixes, both required by this cohort

**The reader now accepts `Ecovillage_Name` as the name column.** The
researcher's own export uses it. Before the alias, that file loaded as **zero
communities, with no error message** — the failure most likely to cost a day.
It now loads all 314 rows, and there is a test that says so.

**`_country_code()` covered 18 countries; the cohort spans 58.** Every country
outside that list returned `None`, and the local-language sweep and domain
guessing were skipped for it. The map now covers ~130 countries by ISO English
short name and passes an ISO alpha-2 code straight through.

---

## 8. Format conformance

| Requirement | Result |
|---|---|
| Valid CSV | yes — 213 lines, 52 columns throughout |
| UTF-8 | yes, round-trips byte-identically |
| BOM | absent |
| Quoting | `QUOTE_MINIMAL`, correctly escaped throughout |
| Consistent row lengths | yes |
| Excel-readable | yes — no formula-leading cells, no embedded newlines, CRLF endings |
| pandas-readable | yes — `read_csv` returns 212 × 52 with identical column order |
| Crawler-readable | yes — 212 communities via `read_community_file` |
| Safe for query-parameter URLs | yes — pipe delimiter, and the comma fix above |
| Safe for Unicode names | yes — Sólheimar, Città, Levefællesskab, Cité Écologique, Comunità |
| Safe for semicolons and commas in cells | yes |
| Malformed records | 0 |
| Column shifts | 0 |

---

## 9. Automated checks

`tests/test_master_input.py` — **33 checks, all passing.** They are assertions
about this file, not smoke tests:

* all 212 original names survive; none invented; all 314 original coordinates
  recoverable; the primary coordinate is provably the first source row
* every row carries the fixed GEN global URL, in both `gen_global_url` and
  `urls`
* `gen_community_url` is non-empty exactly when the status says verified, is
  never the global URL, and always carries evidence
* `NOT_SEARCHED` and `NOT_FOUND` never blur into each other
* every GEN address sits in independence group G1
* the address list reconstructs exactly from `seed_sources_json`, with no
  duplicates, and ranking is descending by quality with the GEN global last
* every address carries a valid source class, platform type, independence group
  and confidence from the study's own vocabularies
* independence counts groups rather than URLs
* one country name per ISO code across the whole file
* every non-`HIGH` confidence row is flagged for review
* the crawler's reader returns 212 communities with byte-identical addresses,
  usable coordinates, a resolvable ccTLD and a valid run mode
* `build_plan()` sizes and orders the whole cohort
* the researcher's original export now loads too

Run: `python3 -m pytest tests/test_master_input.py -q`

---

## 10. What is still owed

1. **Discovery for 113 communities** — blocked only by the search budget.
   `master_input/pipeline/step4_resume_discovery.py --list-pending` is the worklist; the file is
   built to absorb the results without regeneration.
2. **The HTTP validation pass** — blocked only by the egress policy.
   `master_input/pipeline/step5_validate_urls.py` fills the four empty count columns and adds
   `http_status`, `final_url`, `content_type` and `crawl_status` per address.
3. **The 34 multi-candidate coordinates** — resolvable with a map; see the lead
   in §2.
4. **Two identity conflicts** — Hågaby and The Garden, where the GEN page and
   the coordinate disagree about which place is meant.

Nothing in items 1–4 requires the file to be rebuilt from scratch, and nothing
already in it depends on their outcome.
