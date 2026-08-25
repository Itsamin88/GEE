# Unresolved methodological questions

These are the places where the research documents do not settle a question and the
program has made a documented, conservative choice. Each needs your decision before the
dataset is frozen.

---

## 1. Which independence group does a verified thesis belong to?

The register is clear that a thesis and the community's own account are different groups.
It does not say whether **two theses by different authors on the same fieldwork season**
are one group or two, nor whether a thesis and the grant that funded it are independent.

**What the program does now:** every verified academic record gets its own group; grey
records get one shared institutional group. This is the *generous* reading and may
overstate corroboration where a paper and a grant record describe the same project.

**What you should decide:** whether same-project academic and funding records should share
a group. Changing it is a one-line change in `_register_evidence_source` and a re-run of
mode `AUDIT`.

---

## 2. Should `channel_count` count groups that no longer exist?

Block D counts independence groups. If a community's only external documentation is a
2011 thesis and the community is now dormant, V2 is still satisfied — the documentation
exists — but the *activity* it verifies may not.

**What the program does now:** counts the channel as satisfied regardless of age, per the
register's wording, and records the years in `activity_tier_note`.

**What you should decide:** whether V2 and V5 should carry a recency window for
criterion E5 (operating now).

---

## 3. What counts as "the same period" for a managed-area band?

Register 9.4 distinguishes growth from conflict but gives no window.

**What the program does now:** three years, from `config/decisions.yaml` DCR-D008. Figures
within three years of the latest dated figure form the band; older ones are kept as
history in `documentary_area_note`.

**What you should decide:** whether three years is right for this population. A slow-growing
community may hold one figure accurate for a decade; a fast-growing one may outgrow it in
two.

---

## 4. Should an `explicitly absent` denial outrank a positive statement elsewhere?

A community that says "we do not irrigate the pasture" on one page and describes drip
irrigation in the market garden on another is not contradicting itself — it is describing
two parts of the site. The register's five levels have no way to express "absent here,
present there".

**What the program does now:** where both a denial and a positive statement exist, the
positive level is coded, the contradiction is recorded in the rationale, and a review item
is raised. It never codes `explicitly absent` when a positive statement also exists.

**What you should decide:** whether such cases should be coded at the whole-site level at
all, or flagged for exclusion from H6.

---

## 5. `onset_first_or_major` is often genuinely unclear

Distinguishing the first intervention from a later major project needs a complete history,
which most communities do not publish.

**What the program does now:** `first intervention` when the sentence carries a
first/began marker and no earlier dated action exists; `major new project` when an earlier
action is dated; `unclear` otherwise. In the pilot this returned `unclear` more often than
either alternative.

**What you should decide:** whether `unclear` should exclude a community from the cohort,
or only widen its band.

---

## 6. Whether an automated pass may count towards double-coding

It may not, in this implementation (decision DCR-D004): `double_coded` and
`second_coder_id` are never written, and `O4_Reliability_Report` is left entirely to you.

But the program produces a genuinely independent second reading of the same sources, and
the plan's reliability requirement is about coder agreement rather than about humans as
such.

**What you should decide:** whether a human coder double-coding *against* the program's
output — a different and arguably harder test — can serve the plan's ≥20% subsample, and
if so how to report it in the methods chapter. This is a methodological question, not a
software one.

---

## 7. Local-language coverage is uneven

The practice lexicon covers English, French, Dutch, German, Spanish, Portuguese and
Italian well, and Nordic, Polish, Czech, Romanian, Hungarian, Greek and Turkish thinly.
A community publishing only in a thinly covered language will yield fewer practice codes —
and that shortfall will look like an absence of practice rather than an absence of
vocabulary.

**What the program does now:** records `search_languages` so the coverage is visible, and
`crawl_truncated` where a stage could not complete. It does not currently flag
"language not well covered" as a review item.

**What you should decide:** whether to extend the lexicon for the languages actually
present in your 212, or to flag thin-language communities for manual coding. Counting
`search_languages` across the sample after the first fifty communities would tell you
which.

---

## 8. Verification of institutional records

Academic records are verified by retrieving the DOI or repository record and matching the
title. Grey records — a LEADER entry, a planning permit — have no equivalent identifier
system, so they are accepted on the strength of the retrieval alone.

**What you should decide:** whether an S2 record should be barred from supporting a
rank-1 onset until you have opened it yourself. The program makes this easy either way:
every grey record is a row in `O6_Source_Index` with its URL.
