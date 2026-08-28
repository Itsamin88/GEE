# Validation report — `Paper1_Final_Only_Ecovillages_Master_Input.csv`

**Status: complete for the work that could be done offline. One environment
limit remains and is not disguised anywhere in the file.**

All 212 communities have been researched. Every row carries a determined
country, an actively-checked Global Ecovillage Network status, and a ranked
seed source set. The 34 communities the export gave four coordinates for have
been worked through individually; 31 are resolved against their own published
addresses and 3 are left open on purpose.

**What is still owed: not one URL has been opened over HTTP.** The egress proxy
in this container answers `403 Forbidden` to `CONNECT` for every research host,
re-tested at the end of this pass:

```
CONNECT ecovillage.org:443 HTTP/1.1
< HTTP/1.1 403 Forbidden
* CONNECT tunnel failed, response 403
```

`WebSearch` works, because it runs through a different path; direct fetching of
arbitrary hosts does not. So `seed_url_validated_count`, `seed_url_dead_count`,
`seed_url_blocked_count` and `seed_url_duplicate_count` are **empty on every
row, not zero**. Empty means not measured. Zero would be a measurement, and it
would be a false one. `seed_url_verification_method` says `search_index`, which
is exactly what was done: every address was seen in a search index and its
identity checked against the community, but the page itself was never fetched.
`master_input/pipeline/step5_validate_urls.py` is written and ready; it needs
only an environment that permits outbound HTTPS.

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
| `SINGLE` — the export gave one coordinate | 178 |
| `MULTIPLE_CANDIDATES_RESOLVED` | 31 |
| `MULTIPLE_CANDIDATES_UNRESOLVED` | 3 |
| Coordinate confidence HIGH / MEDIUM / LOW | 204 / 5 / 3 |

The 34 multi-coordinate communities are the **last 34 in file order**, seq
179–212 with no gaps, each with exactly four candidates — the signature of a
geocoder asked for candidates rather than an answer. Slot 3 is a decoy that
lands on the nearest large city; slot 4 is the community; **slot 1, which the
export puts first and which this file was previously shipping, is frequently
wrong by up to ninety kilometres.**

Nearly every "location conflict" flagged during source discovery turned out to
be that artefact rather than a real disagreement. Sadhana Forest Haiti was
pointing near Port-au-Prince instead of Anse-à-Pitres, in the wrong department.
Cité Écologique's slot-1 coordinate is what drove the gazetteer to vote Canada
for a community in New Hampshire.

Each of the 31 resolutions was verified against **that** community's published
address, not inferred from the pattern — §33 forbids transferring a result
between communities, and this is precisely where that temptation was strongest.
Every pick carries its published locality, the URL that published it, and the
reasoning, in `coordinate_evidence`.

Three are unresolved and say why: **Grishino** (no gazetteer city near any
candidate, so no slot betrays itself), **Rodnoe** (sources name only an oblast,
and a hundred one-hectare kin domains have no single point), and **Sadhana
Forest Kenya** (sources say only "the Maralal area", and the planting is
scattered across family farms county-wide, so no point represents it).

Nothing was discarded: all four candidates remain in `coordinate_candidates`
and the export's original first coordinate has its own two columns.

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

## 6. Review queue (§38)

**68 rows** carry `review_required = yes`, each with machine-readable reasons:

| Reason | Rows |
|---|---|
| `identity_confidence_below_high` | 35 |
| `single_independence_group` | 21 |
| `gen_page_qualified` | 12 |
| `country_corrected_from_gazetteer` | 8 |
| `gazetteer_split` | 8 |
| `thin_source_set` | 6 |
| `coordinate_resolved_below_high` | 5 |
| `multiple_coordinate_candidates` | 3 |

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
| Consistent row length | ✅ 56 fields on every row |
| Parses with `csv` | ✅ |
| Parses with `pandas` | ✅ |
| Opens in Excel | not tested — no Excel here. The file meets the requirements (valid CSV, CRLF, `QUOTE_MINIMAL`), but note it is UTF-8 **without** BOM, which some Windows builds of Excel mis-render for non-ASCII names unless the file is imported rather than double-clicked. A BOM was left off because a BOM is not part of UTF-8 and trips many naive parsers; this crawler is not one of them — prepending a BOM was tested and it still reads all 212 rows. |
| Embedded commas, semicolons, quotes, non-ASCII survive | ✅ |
| Query-parameter URLs survive | ✅ |
| Address list reconstructs deterministically from `seed_sources_json` | ✅ |
| Separate QC file created | ❌ none — QC is inside this CSV, as §23 requires |

Size 833,554 bytes.

## 9. Automated checks

`tests/test_master_input.py` — **37 tests, all passing.** They are written as
falsifiable claims, not smoke tests. Among them:

* the fixed network seed is on every single row;
* absence of a GEN page is never dressed up as a search having been run;
* GEN never counts as an independent second voice;
* no community GEN URL was invented;
* the address list reconstructs exactly from the structured column;
* the exported coordinate is never lost;
* a single-coordinate row is never second-guessed;
* a moved coordinate is one of the exported candidates, verbatim, never a new point;
* every moved coordinate cites the address that justifies it;
* an unresolved coordinate still carries the exported value and its review flag;
* the crawler reads all 212 communities;
* the original export would now load too.

Full suite: **558 passed**, 114 skipped, 3 failed. The three failures are in
`tests/test_extraction.py` and are pre-existing container problems — a missing
`reportlab` and a broken `_cffi_backend` behind `cryptography` — untouched by
and unrelated to this work.

## 10. What a reader should not conclude from this file

* **That any address resolves.** None has been fetched. The four validation
  columns are empty for that reason and must stay empty until step 5 runs.
* **That a `NOT_FOUND` GEN status means a community is not in GEN.** It means
  no community page was returned by a `site:ecovillage.org` query. Several of
  the 36 are demonstrably in the network — Arterra Bizimodu is a GEN Europe
  full member and hosts GEN Europe's office; Ecodorp Bergen is reported as the
  first Dutch initiative to hold full membership. GEN's site structure and its
  membership are not the same thing.
* **That a thin row means a thin community.** Register field I12
  (`crawl_truncated`) exists precisely so that absence of effort is never
  mistaken for absence of evidence, and rows where the record is genuinely
  sparse say so in `qc_notes` rather than looking merely unremarkable.
