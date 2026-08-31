# Decision memo — removal of documentary practice codes from Study 1

**From:** methodological review of THE_SIMPLIFIED_PLAN_v3.8, Stage_1_Documentary_Coding_Workbook_v6 and WEB_SEARCH_FIELD_REGISTER_AND_CHATGPT_PROMPT_v2_4
**Decision:** remove documentary practice codes entirely; delete hypothesis H6 and analysis A6; rebuild Stage 1, the workbook and the web-search protocol around what remains
**Status:** implemented in `revised_v4/`

---

## The short version

The proposal put to me was that practice codes should be removed because practice-level documentary information is too incomplete, uneven and unverifiable across 212 communities to support defensible quantitative analysis. I was asked to audit that hypothesis rather than implement it.

**I agree with the conclusion, and I found a stronger reason for it than the one proposed.** The proposal's argument is about data quality — the codes are noisy and patchy. That argument is correct but it is not decisive on its own, because a noisy predictor normally attenuates a result toward zero, which is conservative. The decisive problems are two others:

1. **Analysis A6 as specified contradicts the plan's own coding rule.** It compares settlements "claiming" a practice against settlements "not claiming" it. `not mentioned` is the modal level of a five-level variable, and a binary split must put it in one arm or drop it. Putting it in the not-claiming arm makes silence into absence — which §3.5 of v3.8 explicitly forbids. Dropping it leaves a comparison against `explicitly absent`, a level communities essentially never produce, so the sample collapses. There is no version of A6 that respects the plan's own rule and remains testable.

2. **The error is aligned with the outcome, not orthogonal to it.** Documentation quality tracks community size, age, funding and organisational capacity. Those same characteristics plausibly track actual land management, and therefore the measured outcome. So the "claiming" arm is enriched for well-organised communities on both sides at once, and A6 had a live route to a *positive* result manufactured entirely by organisational capacity. That result would have been reported as evidence that these communities deliver what they claim — the most quotable and least defensible sentence the study could produce.

A variable that is merely noisy is a cost. A variable whose error points at the answer is a hazard. That distinction is what makes removal the right call rather than a reluctant simplification.

---

## 1. Why practice codes were removed

### 1.1 Measurement validity — can the process produce usable practice data?

No, for most of the sample. The evidence hierarchy in the register (S1 academic … S8 direct communication) and its independence rule together determine what is reachable:

| Coding level | What it requires | Reachable for |
|---|---|---|
| `evidenced` | An external or visual source, with specificity | The minority that has been studied, funded or certified |
| `documented` | The community describing it specifically, with continuity across years | Communities with a substantial, long-lived web presence |
| `claimed` | An assertion without specificity | Most communities that mention the practice at all |
| `explicitly absent` | A published denial | Almost never |
| `not mentioned` | Nothing either way | The modal outcome for most codes |

The register itself states the constraint plainly: *"MOST COMMUNITIES HAVE NO ACADEMIC LITERATURE AT ALL … that is the answer I expect most of the time."* And its independence rule collapses a community's website, its Facebook page, its YouTube channel and a directory listing copied from it into **one voice**. So for most communities `evidenced` is structurally unreachable, and what remains is self-description.

Comparability across 212 communities in roughly sixty countries fails for the same reason, in a second way: what is publishable, and in what language, varies by country and by movement network. A code is therefore not measured on one basis across the sample.

### 1.2 Missingness — how much of the system becomes uninformative?

`not mentioned` is not missingness in the ordinary sense. It is a coded level that is neither presence nor absence, and it is the majority state. The four states the plan must never confuse are:

- **lack of evidence** — no source describes it (modal, uninformative);
- **evidence of absence** — a source says the community does not do it (rare, real);
- **poor documentary coverage** — the community publishes little, or was searched thinly (a fact about the record);
- **genuine practice absence** — the community does not do it (**not observable by this design at all**).

Version 3.8 collapsed the first and the fourth every time A6 ran. That is the specification defect above, restated as a measurement claim.

### 1.3 Construct validity — what does the variable measure?

"Practice publicly documented", not "practice performed". Version 3.8 conceded this in its own limitations: *"Practice codes measure documentation, not practice. A community managing land beautifully and publishing nothing is coded as doing little."* Having conceded it, the plan then tested a hypothesis that requires the opposite to be true.

The prevalence rule made it worse. A6 tested only codes claimed by 25–75 per cent of settlements. Whether a code passes that gate is a property of how often the practice is *written about*, not how often it is *done* — so even the choice of which codes to test was made by the documentary record.

### 1.4 Independence — is there real corroboration?

Rarely. By the register's own rule, most communities yield a single independence group. Two sources corroborate only if neither derives from the other; four addresses belonging to one community are one voice. Corroboration is therefore structurally unavailable for most of the sample, and where it is available it is available *non-randomly* — at exactly the communities with theses, grants and certifications.

### 1.5 Consequences — does keeping them add more bias than removing them?

Yes, and this is the decisive item. The mechanism is set out at the top of this memo. Two further consequences:

- **Cost.** Block F was fourteen of eighty-eight register fields, but a disproportionate share of the *reading* effort — every practice must be assessed against every source — plus a per-practice evidence row per community, plus thirteen of the twenty-four double-coded reliability variables. Removing it shortens the critical path materially (§7 below).
- **Contamination downstream.** The per-community table hands Study 2 its features. Thirteen self-described variables in a machine-learning feature set would let a model learn, with high apparent accuracy, that well-documented communities score better.

### 1.6 Two partial-retention options, considered and rejected

I was explicitly authorised to conclude that partial retention is justified. I considered the two serious versions and rejected both.

**(a) Restrict A6 to the `evidenced` level.** This fixes construct validity — an external source with specificity is a real observation. It fails on power and on selection. `Evidenced` is reachable for a small minority, so each code would compare perhaps ten to twenty communities against nearly two hundred; the detectable difference would exceed one standard deviation against 0.39 SD at balanced prevalence. And the evidenced group is the studied, funded and certified minority, so the comparison is confounded by the very characteristics that produced the evidence. Underpowered *and* confounded.

**(b) Retain `pc02_swales` alone, for the contour-alignment check.** This was the closest call, because SC15's within-settlement comparison was the sharpest practice-specific test in the study and v3.8 said it carried more weight than the settlement-versus-control one. Rejected on three counts: the comparison is restricted to sloping sites, so it is a subset of a subset; the claim carries the same documentation bias as every other code; and retaining one code means retaining the whole apparatus — coding levels, evidence rows, the frozen claim-to-signature mapping, double-coding and reliability reporting — for a single field. **This is the one place where the removal costs a real capability rather than removing a defective one, and it is stated as such in the plan's limitations rather than glossed.**

---

## 2. Does H6 / A6 survive?

**No. Deleted completely, not retained as a weak quantitative analysis and not retained as qualitative context.**

| Question | Answer |
|---|---|
| Is H6 load-bearing? | No. Nothing else in the design consumes it. |
| Does it affect the main research question? | No. The question is whether these communities hold land in better condition without producing less — H1 and H2. |
| Does it affect VCI? | No. VCI is fourteen satellite metrics rescaled against reference pools. |
| Does it affect PCI? | No. |
| Does it affect the management-diagnostic argument? | No. The MDS rests on the E/M/X metric classification, which is a physical argument about what can be inherited with a parcel. It has no documentary input. |
| Can it be retained as qualitative context? | No — and this is the option most likely to be proposed. A descriptive practice table changes no decision and no analysis, costs weeks on the critical path, and would be over-read precisely because it is the only practice-level statement in the document. It would also flow into the Study 2 handoff. |
| Does removing it strengthen overall validity? | Yes: it removes the study's one route to a false positive aligned with its own central claim. |

Everything downstream is handled: the hypothesis, the analysis, the objective, the detectable-difference row, the multiplicity family, the mediator, the missing-data rule, the workbook sheets, the register block, the risk-register contingency and the Study 2 handoff. **There is no ghost H6/A6** — verified programmatically (§9).

---

## 3. What scientific capability is lost

One, and it should not be minimised: **the study can no longer say anything about the relationship between what these communities claim and what their land shows.** That was novel, nobody has answered it for this population, and version 4.0 does not answer it either.

The honest position is that this study never could have. A claims-versus-delivery test needs a claim record with even coverage and independent verification, and the documentary record for 212 globally distributed intentional communities does not supply one. Answering the question properly needs a survey with a defined response frame, or site visits — both outside an M.Sc. and both raising the ethics questions decision D1 exists to keep narrow.

A second, smaller loss: **SC15's sharpest comparison.** See §1.6(b).

Partly replacing the first loss, `SC18` is new: it restricts the primary analyses to communities whose ecological work is documented by somebody *other than themselves*. It does not ask what a community does. It asks whether anyone independent recorded that ecological work happens there, and whether the result holds among those communities. That is an evidence-quality restriction and it is described as one.

---

## 4. What remains intact

Everything except the one variable class and the one analysis:

- Both primary hypotheses and their analyses; the radial gradient; the age gradient; the management-diagnostic contrast; the density comparison; the longitudinal cohort; the size gradient.
- VCI and its four dimensions, PCI, MDS, LCC, both diagnostic flags, all fourteen condition metrics, all three provisioning metrics, the contour-alignment metric.
- The polygon geometry, the translated control polygons, the five reference radii, the three reference pools and the semi-urban split.
- The matched design, the distance ladder, the three-tier match quality, the quartet fixed effect.
- All seventeen sensitivity checks (two re-scoped, none deleted), all three placebo tests, plus SC18.
- The typology, the shrinkage step, the per-community table, the decisions log, the language rules and the integrity architecture.

---

## 5. Is Study 1 stronger, weaker, or more focused?

**More focused, and on balance stronger.** Weaker in scope: one objective and one analysis are gone, and one sensitivity check lost half its interpretive power. Stronger in defensibility on four counts:

1. The one analysis whose most likely positive result would have been an artefact aligned with the study's central claim is gone.
2. The interpretive boundary is now explicit and enforced by the data model rather than by discipline: there is no practice variable to over-read, because there is no practice variable.
3. Four internal inconsistencies unrelated to practice codes were found and fixed in the same pass (§8).
4. The critical path shortens, and the freed effort is redirected to onset dating — the field the most analyses depend on and the hardest to establish.

The scope reduction is real and it is stated in the plan's limitations in its own words, not buried.

---

## 6. What happens to Stage 1

**Redesigned and renamed, not deleted.** The proposal correctly anticipated that Stage 1 contains load-bearing work unrelated to practice codes. It does: the polygon alone would justify the stage, and onset dating carries two analyses.

**Stage 1 — Essential documentary coding and measurement geometry.** Every retained field carries a named downstream consumer, documented field by field in the plan's Appendix C.

Beyond the fourteen practice fields, eleven more were deleted on the test *what downstream decision or analysis changes because of this field?* — two duplicates (`e3_population_value` duplicated `population_value`; `e5_active_currently` duplicated `status_current` at lower resolution), two now derived, and seven with no consumer at all. Two more were merged into computed fields. The register goes from 88 fields in 9 blocks to **61 in 8**.

Retained and re-scoped:

- **Onset** — the priority block. Twelve fields. `date_first_residence` deleted (bounds nothing: intervention can precede first residence or follow it by decades); `domain_onsets` deleted (no per-domain analysis remains to consume it). `date_formal_founding` and `date_land_acquisition` are kept because they are the two dates that actually *bound* the onset estimate.
- **Documentary managed area** — retained, re-scoped to corroboration only. It sets no geometry and predicts nothing. It produces the area-agreement tier, table T10 and the SC16 restriction. The `actively managed ≠ total holding` distinction is preserved with both figures recorded separately, and `parcel_structure` is retained specifically because a non-contiguous holding is the *legitimate* reason a stated area can exceed a drawn one.
- **Activity tier → evidence tier** — retained, renamed, redefined and re-laddered (§7 of the register). It is an evidence-quality variable with three named uses and one prohibition: never disaggregated by kind of activity, which would rebuild a practice score under another name.
- **Status** — simplified from six fields to five. `first_listing_year` deleted; `last_listing_year` retained as the dating evidence behind `status_current`. The unknown-is-not-dissolved rule is preserved.
- **Context** — cut from seven fields to three, each of which changes a specific decision: two Stage 2 exclusion criteria and the field a flagged outlier is resolved against. `movement_tradition`, `education_volunteer_program` and `agricultural_orientation` are deleted — all self-descriptions with no consumer, and admitting self-descriptions as predictors is the failure that removed the practice codes.
- **Provenance** — retained in full, twelve fields, under the explicit audit-metadata exemption.

---

## 7. What happens to the workbook

**Rebuilt from scratch as `Stage_1_Essential_Data_Workbook_v1.xlsx`.** Not edited: the practice sheets are *absent*, not hidden. Fifteen sheets against eighteen; `O2_Practice_Matrix`, `O2b_Practice_Evidence` and `O9_Claim_Signature_Map` have no successor. `R1_Codebook`, whose entire content was thirteen practice definitions, is replaced by `Definitions_And_Freeze`, which carries definitions, worked examples and agreement thresholds for the seventeen judgement-bearing variables that remain — so the freeze discipline survives even though the thing it was freezing does not.

Three defects in v6 were fixed while rebuilding:

1. **`channel_count` and `activity_tier` were typed**, so they could disagree with the five channels behind them. Both are now formulas.
2. **The evidence tier's own rule was unreachable.** v2.4's tier C — "2 community-originated channels" — cannot occur: the only channel that is neither external nor visual nor continuity is V1, and no community can have two of V1. The ladder also ordered by channel *count* before independence, so three self-documented channels outranked two including a thesis. The ladder is rebuilt to order by independence first; every tier is now reachable.
3. **`language` meant three different things on three sheets** — the language of a source, of a web address, and of a search. Renamed `source_language`, `address_language`, `search_language`.

A fourth was caught by testing the rebuild itself: an unguarded `INDEX` lookup returns `0` for an empty cell, not blank, so a site with **no** documentary area was being graded agreement-tier **C** ("the two disagree by more than a factor of two") when there is no figure to disagree with. The plan requires tier B there. Verified fixed against a spreadsheet engine.

Bidirectional mirroring between `O1` and `O10` in v6 is replaced by one-directional read-only lookups, so no value is typed on two sheets.

---

## 8. What happens to the web-search protocol

**Rebuilt as version 3.0**, not edited. Block F is deleted, the blocks are relettered A–H, and the crawl budget is re-allocated.

The redesign that matters is not the deletion. It is that v2.4 spread its budget across the community's own material, which is where practice descriptions live, and named Stages 5 and 6 — academic and grey literature — as important while letting the budget be consumed before the run reached them. Version 3.0 puts a **mandatory floor of 8–12 pages on Stages 4, 5 and 6**, because that is where rank-1 onset evidence and measured areas actually live. Priority order: eligibility as a cheap gate, then onset, managed-area corroboration, population, status, essential context.

Everything strong in v2.4 is preserved: the ten-stage protocol with its numbering, the source-set construction, per-platform enumeration, the Wayback CDX query, the local-language sweep, cross-source reconciliation, the independence rule, the eight source classes, negative consultations, truncation reporting and all twelve anti-fabrication rules — two of whose bullets are rewritten, and to which a thirteenth and fourteenth are added: never estimate an area from imagery, and do not report ecological practices.

The three search outcomes — **evidence found**, **evidence absent**, **search incomplete** — are named explicitly and must never be represented identically.

---

## 9. What happens to Study 2

The handoff loses thirteen predictors and gains none. That is stated in the plan (§10.5) rather than left as an absence in a spreadsheet, because a feature removed from Study 1 for measurement-validity reasons does not become valid by being handed to a model.

One retained variable carries a constraint: the documentary evidence tier may enter as a **data-quality** feature and must be interpreted as one. If Study 2 reports feature importances, the tier's importance is a statement about the documentary record, not about land management.

One design rule follows: **no self-described variable enters the feature set.** Because the register no longer collects any, the constraint is enforced by the data rather than by discipline — which is the only way constraints of this kind survive contact with a deadline.

---

## 10. Four corrections made in the same pass

Found by the dependency audit, unrelated to practice codes, and fixed:

1. **The management-diagnostic score was defined twice with different arithmetic** — six metrics in three places, seven in three others. It is seven.
2. **The expected panel size was computed two ways and only one was right.** §4.4 gave 105,182; the §5.7 integrity check gave an arithmetic that double-counted the cohort and totals 113,286; Stage 4 said "about 59,000". The integrity check now uses the one correct derivation.
3. **Two size-class systems coexisted**, plus a confidence tier duplicating the area-agreement tier, plus two appendix sections sharing a heading and giving contradictory specifications for the size-gradient analysis. Deduplicated to one `reference_circle` and one `area_agreement_tier`.
4. **The primary zone was described as a 150 m circle in four places** after it had become a polygon.

One further improvement follows from correction 3: **SC1's alternative geometry is now the equal-area circle** — a circle of the same area as the polygon — rather than the superseded size-class circle. Because area is held constant, SC1 now isolates the effect of *shape*, which is the thing hand-drawing actually risks. The old version varied area and shape together and could not separate them.

---

## 11. What I am not certain about

Stated rather than smoothed over:

- **The evidence tier's retention is the weakest judgement in this memo.** It survives on three uses, and one of them (SC18) is new. If SC18 cannot run — because too few communities reach tier A or B — the tier's justification narrows to a confounder in one analysis and a sample descriptor. That is still enough to keep it, but it is thin, and the plan says to report the tier distribution precisely so this can be judged from the data rather than assumed.
- **The recalculated timings are estimates, not measurements.** Documentary coding at 5–8 weeks rather than 8–12 is derived from field counts and per-community search timings. The plan says to record the actual rate once fifty communities are done.
- **Whether the FDR family should include the cohort analysis is arguable.** It sits on a disjoint sample with a different estimand. It is kept inside the family of six because that is the more conservative choice and because carving out the test most likely to produce a clean result would look like what it would be. The composition is declared before any result exists.
- **SC18 cannot distinguish its own two positive readings.** If the effect is larger among externally documented communities, that is either a real difference in management or a shared cause — organisational capacity. The plan says to report both readings and not to resolve it.
