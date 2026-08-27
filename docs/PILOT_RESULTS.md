# Pilot results

## What was actually run

The two pilot communities were run end to end through the production pipeline —
the real crawler, extractors, evidence model, exporter and quality checks — against a
**local test fixture**, not the live web.

```
python3 tools/run_pilot.py
python3 tools/self_audit.py
python3 -m pytest tests -q
```

### Why the fixture and not the live web

The environment this was built in blocks outbound HTTPS to everything except package
registries: every request to a real host returns `403` from the egress proxy before it
reaches the network. Running the pilot against `pourgues.org` or `ecodorpboekel.nl` was
therefore not possible here, and **no result in this repository is derived from the live
web**.

Rather than report an untested system, the fixture serves a small realistic web on
loopback: a current site with a sitemap, a feed and orphan pages; an abandoned domain; a
directory listing that copied the site's text; a login-walled social platform; a web
archive with a CDX index and snapshots; an academic API with a verifiable DOI; PDFs, a
spreadsheet, a Word document, a zip, a corrupt file, a file served under a lying
Content-Type, and images ranging from a site plan to a logo.

Only the *endpoints* are redirected. Everything the pipeline does with what comes back is
the production code path.

### The fixture is a test case, never data

Fixture runs are stamped `provenance_mode: FIXTURE`, their identifiers are prefixed
`TEST-`, and the workbook's notes column says `FIXTURE RUN — synthetic test data, not
research evidence`. Nothing from a fixture run can be mistaken for coded research data.

---

## What the pilot produced

| | EcoVillage de Pourgues | Boekel Ecovillage |
| --- | ---: | ---: |
| Addresses supplied | 2 | 1 |
| Addresses discovered | 3 | 1 |
| **Independence groups** | **2** | **1** |
| Pages opened | 20 (8 archived) | 6 (3 archived) |
| Documents stored | 10 (9 parsed, 1 recorded corrupt) | 1 |
| Images retained | 4 (3 likely relevant) | 1 (1 likely relevant) |
| Evidence items | 96 | 37 |
| Claims | 134 | 51 |
| Fields coded | 66 (1 `NOT FOUND`) | 60 (2 `NOT FOUND`) |
| Conflicts recorded | 12 | 1 |
| Quality checks | 16 pass, 2 warn, 0 fail | 17 pass, 1 warn, 0 fail |
| Completion status | `COMPLETE_WITH_TRUNCATION` | `COMPLETE_WITH_TRUNCATION` |

`COMPLETE_WITH_TRUNCATION` is the correct status: the fixture deliberately makes some academic
and every grey-literature database unreachable, and the program refuses to call a run
complete when a stage could not finish. `stages_completed` names which ones and why.

### What it got right, on evidence

- **The independence rule held.** Five addresses for Pourgues — website, Facebook, former
  domain, directory listing, thesis — collapsed to **two** groups. The directory listing
  joined the community's own group; the verified thesis did not.
- **A blocked platform was recorded, not described.** Facebook returned a login wall; the
  source is `blocked`, zero pages, and no claim cites it.
- **An orphan page was reached.** `/pages-orphelines/chantier-eau-2017` is linked from
  nowhere and appears only in the sitemap. It was opened, and it carried a dated pond
  and wet-meadow restoration.
- **The archive yielded material the live site no longer has.** Eight archived snapshots,
  including a deleted 2016 planting page and a bulletin PDF.
- **A verified thesis upgraded the coding.** `managed_area_ha` came out as **4.2 ha,
  basis `measured`, class `S1`** — from the thesis, not from the website's rounder figure —
  and `total_holding_ha` stayed at 55 ha, separate.
- **A denial was coded as a denial.** "Nous n'irriguons pas les prairies" produced
  `pc03_irrigation = explicitly absent`; the seven practices no source mentions came out
  `not mentioned`, never as absence.
- **A corrupt PDF was stored and reported.** `parser_status = corrupt`, hash recorded,
  original preserved, run unaffected.
- **A PDF served as `text/html` was parsed as a PDF**, because extensions and
  Content-Type headers are never trusted.

---

## Defects the pilot found

Every one of these was a real defect in the program, found by running it rather than by
reading it. They are listed in full in `docs/RESEARCH_DECISIONS.md`; the ones that would
have quietly damaged the research are:

1. **URL normalisation destroyed every Wayback URL** by collapsing the `//` inside the
   embedded original URL. Stage 4 would have returned nothing but 404s, on every
   community, with no error that looked like a bug.
2. **A verified thesis fetched outside a registered source was coded as community-class
   `S4`.** No practice could ever have reached `evidenced` and no onset could ever have
   reached rank 1 — silently defeating the entire purpose of stages 5 and 6.
3. **The onset engine chose the best-evidenced year rather than the earliest documented
   action**, contradicting the workbook's own worked example.
4. **Population extraction read "En 2017 nous avons creusé…" as a population of 2017.**
5. **One community collected another's addresses**, because any platform URL was treated
   as plausible without a name match.
6. **Speculative 404 path-probes exhausted a source's crawl budget** before its sitemap
   pages were read, turning a deep crawl into a shallow one.
7. **Writing into the template's row 2 gave the first community the example row's polygon
   area**, because row 2 is the one row where formula columns hold constants.
8. **Numeric values reached Excel as text**, which would have excluded them from every
   calculation in `O4_Reliability_Report` without any visible failure.

---

## Before the first live run

The pipeline is verified against the fixture, not against the live web. On the first real
community, check these — they are the things a fixture cannot exercise:

1. **Set `DCR_CONTACT` in `.env`.** Site owners should be able to reach you.
2. **Watch the first run's `X6_Failure_Log`.** Real sites produce TLS quirks, redirect
   chains and rate limits that no fixture reproduces. The program records them all; read
   them once to confirm nothing systematic is being lost.
3. **Confirm the Wayback CDX endpoint responds.** It is the single largest yield increase
   in the protocol. If `stages_completed` says stage 4 was blocked, the archive was down
   or the endpoint moved.
4. **Check one academic record by hand.** Open the DOI the program verified and confirm it
   is the paper it says. Verification is automated but the first one should be seen.
5. **Read `X8_Review_Queue` before coding anything.** It is where the program puts the
   cases it should not decide.
6. **Compare `pages_opened_count` against the sources list.** A real crawl has a low hit
   rate. If it opens thirty pages and cites thirty, be suspicious.
