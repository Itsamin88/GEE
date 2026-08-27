# What was measured

Every number here was produced by running the software, on this machine, and is
reproducible with the command given beside it. Nothing is estimated, projected
or scaled from a smaller run.

**Machine.** 4 logical CPUs, 15.7 GB RAM, Linux 6.18, Python 3.11.15, SSD.
**Fixture.** The local test web (`tests/fixtures/`), which serves the real HTTP,
the real HTML, the real PDFs and the real archive index over loopback.

---

## 1. The measurement the rewrite exists for

The same rich, Tamera-shaped community — 420 pages, 5 000 archived URLs, a report
in three languages, hundreds of gallery images, extracted text carrying the
control bytes that killed the original export — run twice.

```
python3 -m pytest tests/test_stress.py -k capped_versus_governed -s
```

| | Pages opened | Documents | Evidence items | Fields coded | Wall |
|---|---:|---:|---:|---:|---:|
| **Capped** (a fixed active-time ceiling, as the previous version shipped) | 83 | 5 | **94** | 52 | 4 s |
| **Governed** (no ceiling; the yield governor decides) | 401 | 5 | **412** | 52 | 10 s |

**4.4× the evidence, for 2.5× the time — and it still terminated.**

The ceiling in the capped run is scaled to the fixture (0.06 min rather than 30),
because the fixture is on loopback and serves the whole site in seconds; a
ceiling that is never reached is not the behaviour being compared against. On
the real Tamera site the shipped 30-minute cap bit in exactly this way: a
fraction of the crawl done, the rest of the protocol never reached.

Both runs produced a workbook that was written and reopened. Neither claimed to
be exhaustive when it was not.

### Where the governed run's time went

```
  http            21.5 s   (88%)
  text_mining      1.4 s
  image_download   0.7 s
  image_classify   0.6 s
  pdf_parse        0.04 s
```

Per stage: stage 2 (enumerate every page) 80%, stage 4 (the archive) 16%,
everything else under 1% each. The run is dominated by waiting on HTTP, which is
precisely why running communities in parallel pays.

Yield: 419 finds credited, 507 units, 99 of them independent research value,
0 duplicates admitted.

---

## 2. Multi-community throughput

Sixteen identical communities, each crawled end to end by a real spawned worker
process against the fixture web, at four worker counts.

```
python3 tools/benchmark.py --workers 1,4,8,16 --communities 16 --latency-ms 150
```

**With 150 ms of latency per request**, standing in for a real server:

| Workers allowed | Actually used | Wall-clock | Speed-up | Efficiency | Mean CPU | Peak CPU | Peak RAM | Finish spread |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 441.5 s | 1.00× | 100 % | 5 % | 27 % | 812 MB | 7.4 s |
| 4 | 4 | 142.5 s | 3.10× | 77 % | 13 % | 97 % | 1 028 MB | 28.1 s |
| 8 | 8 | 109.5 s | 4.03× | 50 % | 19 % | 100 % | 1 350 MB | 46.9 s |
| 16 | **9** | 103.9 s | **4.25×** | 27 % | 27 % | 100 % | 1 455 MB | 41.8 s |

**4.25×, not 16×.** Asked for sixteen workers on a four-core machine, the
governor ran nine — it measured the machine and refused the rest. All sixteen
communities finished in every configuration, and every configuration produced
the same 808 evidence items from the same 216 pages, so the parallelism changes
how long the research takes and not what it finds.

**Without latency** (`--latency-ms 0`), the same runs saturate at 1.7×:

| Workers | Wall-clock | Speed-up |
|---:|---:|---:|
| 1 | 120.2 s | 1.00× |
| 4 | 71.9 s | 1.67× |
| 8 | 73.6 s | 1.63× |
| 16 | 70.0 s | 1.72× |

That number is the **floor**, and it is the floor for a reason worth stating:
waiting on the network is the only thing parallel communities overlap. A
loopback fixture has nothing to wait for, so it measures all of parallelism's
overhead and none of its benefit. A real crawl waits 100–800 ms per request
against a hundred different servers; 150 ms is a conservative stand-in and 4.25×
is a conservative result.

### The fitted curve

    speed-up(N) = N / (1 + σ(N−1) + κN(N−1))

| | σ (contention) | κ (interference) | residual | predicted best count |
|---|---:|---:|---:|---:|
| 150 ms latency | 0.085 | 0.00629 | 0.015 | **12** |
| 0 ms (loopback) | 0.480 | 0.00529 | 0.013 | 10 |

κ is what lets the curve bend down, and it is why sixteen workers can be worse
than twelve. The benchmark prints these in a form that pastes into
`config/config.yaml`, so the estimate a researcher is shown before pressing
START reflects their machine rather than a model's assumptions.

### Fairness

The finish spread — first community to last — grows with the worker count, which
is expected: with one worker the communities run in sequence and finish evenly
spaced; with nine they contend. What matters is that it stays bounded and that
**every** community finished in every configuration. The starvation the ageing
rule prevents is tested directly in
`test_orchestrator.py::test_one_very_large_community_does_not_hold_the_others`,
where five small communities and one enormous one share two workers and at least
three of the five finish before the large one does.

---

## 3. Conflicts

```
python3 -m pytest tests/test_conflict_scaling.py
```

The reported production run ended with **5 569 conflicts**. Two causes, measured
separately.

| Shape | Rows from 2 000 claims |
|---|---:|
| One row per PAIR of disagreeing claims (the original) | 1 999 000 |
| One row per distinct VALUE | ~25 |
| One row per distinct value, **within one semantic role** | **< 5** |

The second column was the arithmetic fix. The third is the real one: of the six
kinds of count a community website offers — residents, visitors, guests,
volunteers, event attendance, employees — only one is a candidate for the
population field, and the other five were never disagreements at all.

On the Tamera-shaped stress community the crawl produces **0 conflicts** from 419
credited finds, and `test_conflicts_did_not_explode` holds the ceiling at 200.

---

## 4. Export

```
python3 -m pytest tests/test_export_safety.py
```

61 tests. Ten shapes of broken PDF text — null bytes, vertical tabs, form feeds,
unpaired surrogates, mixed binary — each demonstrated to be rejected by openpyxl
3.1.5, then demonstrated to be writable and saveable after cleaning.

Three further failure modes were found and closed in this version, all of which
crash inside `save()` rather than at assignment, which is what made the original
so expensive:

| | Fails at | Now |
|---|---|---|
| Timezone-aware datetime | `save()` | tzinfo dropped, the moment kept |
| Worksheet title with a control character or `[]:*?/\` | `save()` | renamed, and the rename recorded |
| Any writer that did not go through the cleaning code | assignment | the unclean route no longer exists |

"Verified" now means every cell was read back from disk, not that
`load_workbook` returned an object.

Across the whole suite, **every workbook written was reopened and read back**.
No test tolerates an unverified one.

---

## 5. The scientific audit

```
python3 -m pytest tests/test_multi_community.py -k audit
```

§108 lists nine things the finished system must not have done. A checklist a
person ticks is a checklist that drifts, so each is a test that runs against the
databases a real multi-community crawl actually produced, and each fails the
build:

| §108 requires that the system has NOT | Test |
|---|---|
| coded a satellite-derived quantity documentarily | `test_audit_no_satellite_quantity_was_coded_documentarily` |
| derived a polygon or managed area from imagery | `test_audit_no_polygon_or_managed_area_was_inferred_from_imagery` |
| treated a publication date as an intervention date | `test_audit_no_publication_date_became_an_intervention_date` |
| confused visitor counts with residents | `test_audit_no_visitor_count_reached_the_population_field` |
| confused property area with managed area | `test_audit_property_area_is_not_managed_area` |
| fabricated literature | `test_audit_no_academic_source_was_fabricated` |
| converted not-mentioned into absent | `test_audit_not_mentioned_was_never_turned_into_absent` |
| counted duplicate source groups as independent | `test_audit_copied_sources_are_not_counted_as_independent` |
| written a value with nothing behind it | `test_audit_every_coded_value_traces_to_evidence_or_a_named_rule` |

Plus §58: every normalised number keeps the wording it came from.

---

## 6. The suite

```
python3 -m pytest
```

**635 passed, 0 skipped.** Against the two bundles this replaces:

| | Tests | Passed | Skipped |
|---|---:|---:|---:|
| `documentaryresearchcrawlerresumableimagetriagefinal` | 310 | 256 | 54 |
| `documentaryresearchcrawler30minfinal` | 414 | 337 | 77 |
| this version | **635** | **635** | **0** |

The skips in both bundles were the optional-dependency suites and the
fixture-web end-to-end tests. The optional dependencies are still optional — the
program reports what it has at startup and records what it could not do — but
the fixture-web tests now run, which is where the multi-community integration
tests live.

Of the 635, **93 spawn real operating-system processes**. Mocking the process
boundary would test the part that is not hard: what makes multi-community
running difficult is that a worker can die in ways Python cannot catch, and that
is only observable with an actual exit code.
