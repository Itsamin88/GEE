# `Paper1_Final_Only_Ecovillages_Master_Input.csv` — schema

The master source table for the 212-community documentary crawl. One row per
community. Fifty-one columns in nine groups: what the crawler reads, who the
community is, where it is, what country that is and how it was established, its
Global Ecovillage Network status, its seed source set, **what the crawler should
do with that source set**, the address validation state, and the quality control
that lets a reader tell a thin record from a thorough one.

* **File**: UTF-8, no BOM, CRLF line endings, `QUOTE_MINIMAL`, 212 data rows.
* **Multi-value delimiters**: addresses and coordinate pairs use `" | "`
  (space, pipe, space); list-valued text fields use `"; "`.
* **Original**: `Paper1_Final_Only Ecovillages.csv` sits beside this file,
  untouched. Nothing here overwrites it; where a value was repaired or
  corrected, both the original and the new value are present.

---

## Why the schema looks like this

**One `urls` column, not `URL_1 … URL_10`.** Ten numbered columns cannot say
what an address *is* — whether it is a thesis or a Facebook page, whether it
corroborates the community's own account or merely repeats it. They also make
the file's width a function of the best-documented community. The crawler's own
reader already accepts a single delimited `urls` column, so the addresses live
there in rank order and everything known about each one lives beside it in
`seed_sources_json`, keyed by the address itself.

**The delimiter is `" | "`.** `csv.Sniffer` weighs `,`, `;` and tab when
guessing a file's dialect. A `urls` cell holding a `;`-separated list can
contain more semicolons than the header row has commas, and the sniffer then
reads the whole file as semicolon-delimited: one column, no `name`, zero
communities, and no error message. A pipe is invisible to the sniffer, and it
also leaves commas inside query strings intact.

**No column other than `urls` may begin with `url`.** The reader treats `urls`,
`url` and `url<digits>` as addresses. A QC column named the obvious way —
`url_count` — would put its own value into the crawl queue, and the frontier
would try to fetch `7`. Hence `seed_url_count`, `seed_url_dead_count`, and so
on. (The reader has since been hardened to ignore such columns, but the schema
does not rely on that.)

**Vocabularies come from the study's own documents, not from invention.**
`source_class` is S1–S8 from register v2.4 and workbook v6 `Reference_Codes`.
`platform_type` is the O11_Source_Set vocabulary. `crawl_status`, written by
the validation pass, is O11's. `independence_group` follows the register's
independence rule.

---

## Group 1 — what the crawler reads

`read_community_file()` in `src/dcr/orchestrator/session.py` uses exactly these
eight columns. Everything else in the file is provenance and QC, and the
crawler ignores it.

| Column | Used by crawler | Values | Notes |
|---|---|---|---|
| `community_id` | no | `IC001`–`IC212` | Workbook `site_id`. Assigned in original file order, stable across rebuilds. |
| `name` | **yes** | text | The normalised community name. Equal to `community_name_normalized`. |
| `latitude` | **yes** | decimal, 6 dp | The researcher's verified coordinate. See group 3. |
| `longitude` | **yes** | decimal, 6 dp | As above. |
| `country` | **yes** | ISO 3166 English short name | One spelling per country throughout (§29). Drives the local-language sweep and domain guessing. |
| `mode` | **yes** | `FULL` | The **run** mode, from `MODE_STAGES`. Not the register's SETTLEMENT/CONTROL — that is `register_mode`. Putting `SETTLEMENT` here would break stage selection. |
| `coder_id` | **yes** | empty | For the researcher to fill, or leave to the CLI. |
| `urls` | **yes** | `" | "`-delimited | Ranked seed addresses, most useful first, `https://ecovillage.org` always last. |

## Group 2 — identity, with the original preserved

| Column | Values | Notes |
|---|---|---|
| `community_name_original` | text | Verbatim from the source export, mojibake and all. The join key back to the original file. |
| `community_name_normalized` | text | Encoding damage and HTML escaping undone; nothing else changed. |
| `name_repair_applied` | `yes` / `no` | `yes` on 10 rows. |
| `alternative_names` | `"; "`-delimited | Register field A2: former names, local names, transliterations, legal entities. Every one is a separate academic search string. Empty where discovery has not run. |
| `register_mode` | `SETTLEMENT` | Register A.1. QC only — the crawler never reads it. |

## Group 3 — coordinates

**One pair per community, verified by the researcher.** No candidates, no
status, no resolution machinery.

The export gave 314 rows for 212 communities: the last 34 in file order, `seq`
179–212 with no gaps, carried four coordinates each — the signature of a
geocoder asked for candidates rather than an answer, whose output was pasted
into the export without anyone choosing between them. That is now settled. The
researcher checked those 34 by hand and returned one latitude and longitude per
community, and `master_input/pipeline/final_coordinates.csv` is that answer.
The build takes it verbatim: nothing here rounds it, overrides it or
second-guesses it.

The nine columns that used to carry the unresolved candidates
(`coordinate_primary_rule`, `coordinate_candidate_count`,
`coordinate_candidate_spread_km`, `coordinate_candidates`, `coordinate_status`,
`latitude_as_exported`, `longitude_as_exported`, `coordinate_confidence`,
`coordinate_evidence`) **have been removed**. They existed only to describe a
problem that no longer exists, and a stale `coordinate_status` in a crawler
input invites a reader to trust something that no longer describes anything.

| Column | Values | Notes |
|---|---|---|
| `source_rows` | `"; "`-delimited integers | Line numbers in the original export. Traceability back to the source file. |
| `coordinate_source` | `researcher_verified` (34) / `source_export_single_row` (178) | Whether a human checked this pair, or the export gave exactly one and it was kept. |

The 34 verified rows are `IC179`–`IC212` — precisely the block the export
mis-geocoded. Two of them (Grishino, Rodnoe) came back as exactly the candidate
this pipeline's own decoy-slot analysis had pointed at, which is a useful
independent check on that method.

**One value to check before publication.** `IC206` Sadhana Forest Kenya pairs
candidate 4's latitude with candidate 1's longitude, so the returned point is
not any of the four the export offered — about 4 km from candidate 4. That has
the shape of a spreadsheet fill slip rather than a deliberate choice. The
researcher's value is used as supplied; it is flagged here because it is
cheaper to check now than after a crawl.

## Group 4 — country, and how it was established

Country was never read off the community's name. Two independent signals:

1. **Offline gazetteer** (`geonamescache`, GeoNames cities ≥ 15 000). The
   *five* nearest populated places vote. Five agreeing at 12 km is a different
   answer from three-to-two at 60 km, and only the k-nearest form can tell them
   apart. Fully reproducible from the repository, and no coordinate leaves the
   machine.
2. **Published sources** located during discovery — official sites, government
   registers, network profiles.

| Column | Values | Notes |
|---|---|---|
| `country_iso2` / `country_iso3` | ISO 3166 alpha-2 / alpha-3 | Machine-readable pair for the human-readable `country`. |
| `admin_region` | text | Register A4: province, state, county, municipality. |
| `country_confidence` | `HIGH` / `MEDIUM` / `LOW` | `HIGH` = both signals agree. `MEDIUM` = published evidence overrode the gazetteer, or the gazetteer alone was unanimous. `LOW` = gazetteer alone and not unanimous. |
| `country_verification_method` | see below | |
| `country_verification_source` | URL or description | The specific evidence. |
| `country_gazetteer_code` | ISO alpha-2 | What the coordinate alone said, kept even where it was overruled. |
| `country_gazetteer_signal` | `UNANIMOUS` / `MAJORITY` / `SPLIT` / `REMOTE` / `NO_CITY_IN_RANGE` | The vote's own reliability. |
| `country_gazetteer_nearest` | `Place (N km)` | |

`country_verification_method` values: `coordinate_gazetteer+official_site`,
`+GEN_profile`, `+published_source`, `+government_record`,
`+government_registry`, `+municipal_source`, `+institutional_record`,
`published_source_overrides_gazetteer`, `coordinate_gazetteer+GEN_profile_CONFLICTING`,
`coordinate_gazetteer_only`.

Four rows carry `published_source_overrides_gazetteer`: Kibbutz Lotan (Jordanian
towns across the Gulf of Aqaba out-voted Israeli ones), Better In Belize
(Guatemalan towns just across the border), Schloss Glarisegg (Radolfzell lies
across the Untersee, in Germany), Vlierhof (Dutch towns nearer than the German
site address GEN publishes). Each is a real border, coast or lake artefact, and
each is flagged.

## Group 5 — the Global Ecovillage Network

The distinction this group exists to enforce: **`https://ecovillage.org` on
every row is a network-level route, not evidence that the community is
registered with GEN.**

| Column | Values | Notes |
|---|---|---|
| `gen_global_url` | `https://ecovillage.org` | **Every row, without exception.** Also present in `urls`, ranked last. |
| `gen_global_status` | `FIXED_GLOBAL_SOURCE` | Constant. |
| `gen_community_url` | URL or empty | The community's own verified GEN page. Empty unless verified. |
| `gen_community_status` | see below | |
| `gen_verification_method` | `search_index` / `search_index_negative` / `none` | How the answer was reached. |
| `gen_evidence_note` | text | The search evidence, or why none exists. |
| `gen_independence_group` | `G1` | Always. See below. |

`gen_community_status`:

| Value | Meaning |
|---|---|
| `VERIFIED_COMMUNITY_SOURCE` | A GEN page for this community was found and identified. |
| `VERIFIED_COMMUNITY_SOURCE_LEGACY_HOST` | Found only on a legacy GEN host (`gen.ecovillage.org`). |
| `VERIFIED_COMMUNITY_SOURCE_SUBPAGE_ONLY` | Only a sub-page surfaced; the parent URL is **not** constructed from it. |
| `VERIFIED_COMMUNITY_SOURCE_PARENT_ONLY` | Only a parent/umbrella listing covering several sites. |
| `VERIFIED_COMMUNITY_SOURCE_IDENTITY_UNCERTAIN` | A GEN page of that name exists but may describe a different site. |
| `NOT_FOUND` | Searched, and no GEN page exists for this community. |
| `NOT_SEARCHED` | **Nobody looked yet.** Not the same claim as `NOT_FOUND`. |

The last distinction is register field I12 applied to this file: a community
searched for four minutes and a community searched exhaustively that genuinely
has nothing look identical in the data unless the file says which is which. One
is an absence of evidence; the other is an absence of effort.

**No GEN URL was constructed.** Real slugs include `/project/tamera-0/`,
`/ecovillage/seaview-performing-arts-center/` (for HawaiiSPACE) and
`/project/global-community-communications-all-0/` (for Avalon Organic Gardens).
None is derivable from the community name. GEN pages also appear under
`/project/`, `/ecovillage/`, `/map/community/` and `/user/` — the form actually
found is recorded, not normalised to a preferred shape.

**Why `gen_independence_group` is always `G1`.** The register's rule: two
sources are independent only if neither derives from the other. A GEN community
profile is self-submitted, so it shares a voice with the community's own
website. Placing the global GEN page in the same group satisfies the further
requirement that the global page never count as independent corroboration of a
GEN profile. Both directions of error are avoided by the conservative choice,
and over-counting independence is the error the register warns about.

## Group 6 — the seed source set

| Column | Values | Notes |
|---|---|---|
| `seed_url_count` | integer | Addresses in `urls`, including the mandatory GEN global. |
| `independence_group_count` | integer | **Groups, not URLs.** This is the number Block D's `channel_count` and the "three independent sources" target actually mean. |
| `source_classes` | `"; "`-delimited S-codes | Which of S1–S8 the set contains. |
| `strongest_source_class` | S-code | Lowest number present; S1 is strongest. |
| `seed_sources_json` | JSON array | One object per address. |

Each `seed_sources_json` object:

| Key | Values |
|---|---|
| `url` | The address, byte-identical to its entry in `urls`. |
| `rank` | Position in `urls`, 1-based. |
| `source_class` | `S1`–`S8` (register). S1 academic · S2 institutional · S3 network/directory · S4 the community's own · S5 archived · S6 journalism · S7 social · S8 direct communication. |
| `platform_type` | O11_Source_Set vocabulary: `own website`, `secondary or former website`, `Facebook`, `Instagram`, `YouTube`, `Vimeo`, `blog platform`, `directory listing`, `crowdfunding`, `LinkedIn`, `booking or hosting`, `news outlet`, `other`. |
| `independence_group` | `G1`, `G2`, … `G1` is the community's own voice — its site, its social accounts, its self-submitted directory listings including GEN. Other groups are separate origins. |
| `confidence` | `HIGH` / `MEDIUM` / `LOW` — confidence that the address belongs to *this* community and is worth crawling. |
| `quality_score` | 0.0–1.0 — expected documentary yield. **Not** the register's onset evidence rank. |
| `verification` | `search_index` or `fixed_global_source`. |
| `evidence` | One line: what identified this address as this community's. |

After `master_input/pipeline/step5_validate_urls.py` runs, each object also carries
`http_status`, `final_url`, `content_type`, `crawl_status` (O11 vocabulary) and
`checked_at`.

**The quality score.** A defensible ordering, not a measurement. It rises with
community specificity (a page about this community beats a page mentioning it),
research-topic relevance (land, water, planting, area, dates), source authority
and independence (a government register or a thesis above a self-submitted
listing), historical depth (an old domain above a current one for dating), and
document richness (a PDF site plan above a homepage). It falls for generic
profiles and login-walled social accounts. It exists to order the crawl, and
the crawler crawls every supplied address regardless of it.

## Group 6b — the crawl policy

Three columns that turn a list of addresses into instructions. Everything here
is **optional** for the reader: a plain sheet of names and URLs still loads and
simply gets the standard treatment for every address.

| Column | Values | Notes |
|---|---|---|
| `crawl_policy` | `EXHAUSTIVE_SITE_AND_ACADEMIC` (159) / `ACADEMIC_EXHAUSTIVE_ONLY` (53) | The second means no site of the community's own was found, so there is nothing to walk in full. The literature harvest still runs exhaustively. |
| `deep_crawl_urls` | `" | "`-delimited **site roots** | The community's own domains: current site, former domain, its blog. 208 roots across 159 communities. |
| `academic_search_terms` | `" | "`-delimited query strings | 2,266 across the cohort, 10.7 per community. |

### Why `deep_crawl_urls` holds roots, not pages

Discovery recorded the single most useful page on each site, because that is
what a ranked seed list wants — Tamera's water-retention-landscape page, not
`tamera.org`. A crawler told to walk the whole site and handed that page starts
three levels down and reaches the newsletter archive only by luck. So this
column holds origins (`https://www.tamera.org/`), and the specific pages stay
in `urls` where their ranking still means something.

`ecovillage.org` is never a deep target. It is 212 communities' shared
directory, and walking it in full would crawl the whole Global Ecovillage
Network once per community without reaching one word of that community's own
voice. (`ecovillage.org.in` — Govardhan Ecovillage's own domain — is a
different host and *is* walked in full; the check is on the host, not a
substring.)

### What the two scopes actually differ by

Set in `config/config.yaml` under `crawl.scopes`, and mirrored per address in
`seed_sources_json` as `crawl_scope` and `asset_download`.

| | `targeted` | `exhaustive` |
|---|---|---|
| base pages | 40 | 500 |
| max pages | 400 | 25,000 |
| max depth | 6 | 25 |
| pagination pages | 60 | 1,000 |
| images per source | 400 | 4,000 |
| assets | evidence-bearing only | everything: images, PDFs, documents |

An exhaustive walk still **stops**. Its exhaustion window is widened, not
removed, because a newsletter archive can be forty barren pages of links before
the first PDF — but a site that has genuinely run out of pages ends the walk
like any other.

### Why the search terms are written down

Putting the queries in the file rather than re-deriving them at crawl time is
what makes the literature search reproducible and auditable: a reader can see
precisely which strings were searched, and a community that turns up nothing
can be told apart from one that was never asked about properly.

Every name the community is known by becomes a query, because **the literature
does not agree on names**: Khula Dhamma is published as Khula Dharma, Ecovila
Raiz do Anuhmas as Anhumas, Zeleni Kruchi under Dubravushka. Each name is also
paired with its locality, which is what separates a paper about *this* Baireni
from the several other places in Nepal called Baireni. A locality that is a
description rather than a name — "between Colos and Reliquias", "on the Quko
River" — is skipped, since pasting it into a database query returns nothing.

## Group 7 — address validation

| Column | Values | Notes |
|---|---|---|
| `seed_url_verification_method` | `search_index` / `search_index+http` / `none` | **`search_index` means no address has been fetched.** |
| `seed_url_validated_count` | integer or empty | `crawled` addresses. |
| `seed_url_dead_count` | integer or empty | |
| `seed_url_blocked_count` | integer or empty | A reported block is data; a guess about the content behind it is fabrication. |
| `seed_url_duplicate_count` | integer or empty | Addresses resolving to something already seen. |

Empty in this build. The session that produced the file reached the web only
through a search API — the egress proxy refused a direct connection to every
research host — so the four counts are empty rather than zero, and the method
column says which verification actually happened.
`master_input/pipeline/step5_validate_urls.py` fills them in wherever the network is open.

## Group 8 — quality control and provenance

| Column | Values | Notes |
|---|---|---|
| `discovery_status` | `COMPLETE` / `PENDING` | |
| `community_identity_confidence` | `HIGH` / `MEDIUM` / `LOW` / `NOT_ASSESSED` | Confidence that the sources describe the community this row denotes. |
| `review_required` | `yes` / `no` | |
| `review_reasons` | `"; "`-delimited codes | See below. |
| `qc_notes` | text, `" | "`-separated clauses | Short. The crawler produces the evidence database; this file is its control table. |
| `verification_date` | ISO date | |
| `schema_version` | `1.0.0` | Per row, so rows merged across passes stay self-describing. |

`review_reasons` codes:

| Code | Meaning |
|---|---|
| `discovery_pending` | No source discovery has run for this community. |
| `gen_not_searched` | No GEN search has run. |
| `country_not_web_verified` | Country rests on the gazetteer alone. |
| `country_corrected_from_gazetteer` | Published evidence overrode the coordinate vote. |
| `gazetteer_split` / `gazetteer_remote` / `gazetteer_no_city_in_range` | The coordinate vote was not clean. |
| `multiple_coordinate_candidates` | The export gave four coordinates and none could be established as the site. 3 rows. |
| `coordinate_resolved_below_high` | A candidate was chosen, but the published address is coarse or a second candidate is nearly as good. 5 rows. |
| `identity_confidence_below_high` | The sources may describe a different site of the same name. |
| `thin_source_set` | Fewer than two addresses beyond the GEN global. |
| `single_independence_group` | Every source is one voice; nothing corroborates anything. |
| `gen_page_qualified` | The GEN page found is a legacy host, a sub-page, a parent listing, or of uncertain identity. |

---

## Rebuilding and extending

```
master_input/pipeline/repair_text.py            undo the export's mojibake (idempotent)
master_input/pipeline/step1_normalise.py        original CSV -> 212 communities, names repaired
master_input/pipeline/step2_geocode.py          offline k-nearest country vote
master_input/pipeline/discovery_store.py        the discovery record, with vocabulary validation
master_input/pipeline/final_coordinates.csv     THE RESEARCHER'S VERIFIED LATITUDE AND LONGITUDE
master_input/pipeline/step3_build_master.py     assemble the master CSV
master_input/pipeline/step4_resume_discovery.py list what is still PENDING; emit a record skeleton
master_input/pipeline/step5_validate_urls.py    open every address, write the results back in place
tests/test_master_input.py                      42 checks on the file and the crawler's own reader
tests/test_deep_crawl_and_harvest.py            15 checks on the crawl scopes and the paging
```

Steps 1–3 are deterministic and safe to re-run. `final_coordinates.csv` is
authoritative input, not a derived artefact: step 3 reads it and takes it
verbatim. To correct a coordinate, edit that file and rebuild — never edit the
master CSV by hand, or the next rebuild silently reverts it.

`master_input/pipeline/step6_resolve_coordinates.py` is retained for the record.
It is what analysed the export's four-candidate block and identified the decoy
slot; its conclusions have since been superseded by the researcher's own
verification, so it no longer runs as part of the build.

### Running the crawl against this file

```
python RUN.py --communities master_input/Paper1_Final_Only_Ecovillages_Master_Input.csv
```

The reader is `read_community_file()` in `src/dcr/orchestrator/session.py`. It
takes the eight crawler columns plus the three policy columns, and ignores the
other forty — they are provenance and QC for the researcher, not instructions.
