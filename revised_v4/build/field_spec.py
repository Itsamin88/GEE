"""
CANONICAL FIELD SPECIFICATION — Study 1, version 4.0
====================================================

This module is the single machine-readable source of truth for the Stage 1
documentary field set. It is consumed by:

    build_workbook.py    -> Stage_1_Essential_Data_Workbook_v1.xlsx
    check_consistency.py -> CONSISTENCY_AUDIT.md verification

and it is checked, field name by field name and value by value, against
WEB_SEARCH_FIELD_REGISTER_AND_CHATGPT_PROMPT_v3.0.md.

Authority split, stated once and enforced by check_consistency.py:
    THE PLAN     is authoritative for what a field MEANS and what depends on it.
    THE REGISTER is authoritative for HOW to search for it and its ALLOWED VALUES.
    THE WORKBOOK is authoritative for WHERE it is stored.
No field may exist in one of the three and be absent from the other two
unless it is marked derived=True (computed, never entered) or
researcher=True (supplied by the researcher, never by a search assistant).

Field tuple fields:
    fid        register field id (A1, C3, ...) or None for workbook-only fields
    name       exact column / field name, used identically in all three artifacts
    block      register block letter, or a workbook-only group label
    values     None for free text/number, else the exact dropdown list
    required   'required' | 'optional' | 'conditional'
    purpose    what it is for
    downstream what breaks if it is absent
    missing    what to do when it cannot be found
    derived    True if computed by formula and never typed
    researcher True if the researcher supplies it, never the search assistant
"""

from collections import namedtuple

F = namedtuple(
    "F",
    "fid name block values required purpose downstream missing derived researcher",
)


def f(fid, name, block, values, required, purpose, downstream, missing,
      derived=False, researcher=False):
    return F(fid, name, block, values, required, purpose, downstream, missing,
             derived, researcher)


# --------------------------------------------------------------------------
# Controlled vocabularies, defined once and referenced everywhere
# --------------------------------------------------------------------------

V = {
    "coordinate_agreement": ["agrees", "differs", "no published location"],
    "e1_pathway": ["network/directory listing", "independent self-identification", "both"],
    "e2_settlement_type": ["village-scale permanent residence", "retreat centre",
                           "campus", "business", "single household",
                           "urban co-housing", "unclear"],
    "e8_setting_at_onset": ["rural", "peri-urban", "urban", "unclear"],
    "onset_evidence_rank": ["1", "2", "3", "4", "5"],
    "yes_no": ["yes", "no"],
    "onset_confidence_tier": ["A", "B", "C"],
    "onset_first_or_major": ["first intervention", "major new project", "unclear"],
    "cohort_candidate": ["core (2020-2021)", "extension (2019)", "no", "uncertain"],
    "managed_area_basis": ["measured", "stated", "inferred", "not found"],
    "source_class": ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"],
    "area_type": ["actively managed", "total holding only", "both recorded", "not stated"],
    "parcel_structure": ["contiguous", "non-contiguous", "unknown"],
    "status_current": ["active", "dormant", "transformed", "relocated", "dissolved", "unknown"],
    "delisting_reason": ["dissolution", "relocation", "changed network",
                         "administrative removal", "lost contact", "unknown", "n/a"],
    "protected_area_status": ["inside", "adjacent", "no", "unclear"],
    "evidence_tier": ["A", "B", "C", "Fail"],
    "polygon_confidence": ["clear", "moderate", "poor"],
    "polygon_imagery_source": ["Google Earth", "Bing Maps", "Esri World Imagery", "other"],
    "reference_circle": ["r75", "r110", "r150", "r210", "r300"],
    "area_agreement_tier": ["A", "B", "C"],
    "full_text_or_abstract": ["full text", "abstract only", "record only", "unreachable"],
    "platform_type": ["own website", "secondary or former website", "Facebook",
                      "Instagram", "YouTube", "Vimeo", "blog platform",
                      "directory listing", "crowdfunding", "LinkedIn",
                      "booking or hosting", "news outlet", "other"],
    "supplied_or_discovered": ["supplied", "discovered"],
    "crawl_status": ["crawled", "partial", "blocked", "dead link", "not attempted"],
    "database_type": ["academic", "thesis portal", "grey - funding", "grey - government",
                      "grey - NGO", "registry", "directory", "news", "archive"],
    "search_result": ["hits found", "none found", "unreachable", "paywalled"],
    "resolution_type": ["rule applied", "third coder", "definitions amended",
                        "evidence re-examined", "unresolved"],
    "variable_type": ["categorical", "ordered categorical", "continuous", "date"],
    "calibration_round": ["initial", "midpoint", "final"],
    "stage": ["Stage 1", "Stage 2", "Stage 3", "Stage 3b", "Stage 4",
              "Stage 5", "Stage 6", "Stage 7", "Stage 8"],
    "changes_results": ["no", "yes", "unknown"],
    "enquiry_medium": ["email", "web form", "postal", "telephone", "in person", "via network"],
    "response_status": ["sent - no reply", "responded", "declined", "undeliverable", "not contacted"],
    "consent": ["yes", "no", "not addressed"],
}


# --------------------------------------------------------------------------
# BLOCK A — IDENTITY AND LOCATION (5 register fields)
# --------------------------------------------------------------------------

BLOCK_A = [
    f("A1", "community_name_official", "A", None, "required",
      "Identifies the community and anchors every source search.",
      "Source retrieval; the code-to-name key held privately for T12.",
      "Cannot be missing — a community with no findable name is not enumerable."),
    f("A2", "alternative_names", "A", None, "optional",
      "Former names, local names, transliterations and network variants.",
      "Each variant is a separate academic and archive search string. Directly "
      "raises Stage 5/6 yield, which is where rank-1 onset evidence lives.",
      "Write 'not found'. Search yield is lower; record it in negative_consultations."),
    f("A3", "country", "A", None, "required",
      "Nation-state the site sits in.",
      "Stage 2 matching criterion (same country, holding policy and tenure "
      "constant); T1 sample description; country income group in T12.",
      "Cannot be missing — it is derivable from the coordinates."),
    f("A4", "admin_region", "A", None, "required",
      "Province, state or county.",
      "SC12 leave-region-out reference anchoring; reporting where Tier 2 and "
      "Tier 3 quartets cluster (T2).",
      "Derive from the coordinates and record that you did."),
    f("A5", "coordinate_agreement", "A", V["coordinate_agreement"], "required",
      "Whether published sources place the community where the held coordinates do.",
      "The polygon, the rings, the reference circle and every extraction are "
      "drawn about the held coordinates. A wrong centre invalidates all of them.",
      "'no published location' is a valid value and is not a gap."),
]

# --------------------------------------------------------------------------
# BLOCK B — ELIGIBILITY (6 register fields)
# --------------------------------------------------------------------------

BLOCK_B = [
    f("B1", "e1_network_listing", "B", None, "required",
      "Which networks or directories list the community.",
      "Inclusion criterion E1. Also supplies the directory whose archive gives "
      "last_listing_year.",
      "If nothing lists it, e1_pathway must be 'independent self-identification'."),
    f("B2", "e1_pathway", "B", V["e1_pathway"], "required",
      "How the community qualifies under E1.",
      "Inclusion record. Makes the sample definition auditable.",
      "Cannot be missing; if neither route holds the community is ineligible."),
    f("B3", "e1_self_identification", "B", None, "required",
      "A published phrase, under 25 words, stating ecological aims.",
      "The evidence for E1. Without it, eligibility is an assertion.",
      "Where none exists, eligibility rests on B1 alone; record that."),
    f("B4", "e2_settlement_type", "B", V["e2_settlement_type"], "required",
      "What kind of entity the site is.",
      "Exclusion criterion E2. Retreat centres, single households, businesses "
      "and urban co-housing leave the sample. The highest-consequence "
      "categorical in Stage 1.",
      "'unclear' keeps the community in and flags it; report how many."),
    f("B5", "e2_evidence_note", "B", None, "required",
      "One line stating why B4 was coded as it was.",
      "Makes the exclusion decision auditable and double-codeable.",
      "Cannot be missing where B4 is coded."),
    f("B6", "e8_setting_at_onset", "B", V["e8_setting_at_onset"], "required",
      "Rural or peri-urban at onset, rather than urban.",
      "Exclusion criterion E8; Stage 2 matches on rural classification.",
      "'unclear' keeps the community in and flags it."),
]

# --------------------------------------------------------------------------
# BLOCK C — ONSET DATING (12 register fields) — THE PRIORITY BLOCK
# --------------------------------------------------------------------------

BLOCK_C = [
    f("C1", "date_formal_founding", "C", None, "optional",
      "Year the community was established as an entity.",
      "Distinguishes founding from onset, which is the study's central dating "
      "rule; supplies founding_decade, a named confounder in A4.",
      "'not found'. founding_decade is then blank and A4 loses one named confounder."),
    f("C2", "date_land_acquisition", "C", None, "optional",
      "Year the land was bought, leased or occupied.",
      "The hardest available lower bound on onset: intervention cannot precede "
      "tenure. It is the field that makes onset_lower_bound defensible rather "
      "than guessed.",
      "'not found'. onset_lower_bound then rests on evidence rank alone and "
      "should be widened."),
    f("C3", "date_intervention_onset", "C", None, "required",
      "Year the first deliberate action to alter vegetation, soil, water or "
      "land cover for ecological purposes is documented. NOT the founding year.",
      "ONSET_AGE in A4; cohort membership in A7; the age smooth carried as a "
      "confounder in A8; onset decade in T1; T12 context.",
      "'not found'. The site leaves A4 and cannot enter the cohort. It stays "
      "in every other analysis."),
    f("C4", "onset_lower_bound", "C", None, "required",
      "Earliest plausible onset year.",
      "A4 propagates the band by multiple imputation, so a community with a "
      "wide band contributes less than one with a narrow band.",
      "Where C3 is 'not found', leave blank; the site is out of A4 anyway."),
    f("C5", "onset_upper_bound", "C", None, "required",
      "Latest plausible onset year.",
      "As C4.",
      "As C4."),
    f("C6", "onset_evidence_rank", "C", V["onset_evidence_rank"], "required",
      "Strength of the onset evidence, 1 strongest to 5 weakest.",
      "Sets the expected band width; reported in T12; the basis on which "
      "conflicting sources are resolved.",
      "Cannot be missing where C3 is coded."),
    f("C7", "onset_evidence_description", "C", None, "required",
      "One line saying what the evidence actually is.",
      "Makes the rank auditable and double-codeable.",
      "Cannot be missing where C3 is coded."),
    f("C8", "onset_conflicting_sources", "C", None, "required",
      "Where sources disagree, what each says.",
      "Absolute rule: a source conflict is never resolved silently. Feeds the "
      "resolution rule and the disagreement log.",
      "'none' is a valid and common value."),
    f("C9", "onset_proxy_flag", "C", V["yes_no"], "required",
      "Whether C3 is a founding year used as a substitute for an onset year.",
      "A proxy onset is excluded from A4. This flag is the exclusion switch.",
      "Cannot be missing; default 'no' only when C3 is genuinely an onset."),
    f("C10", "onset_confidence_tier", "C", V["onset_confidence_tier"], "required",
      "A precise, B plus or minus one year, C uncertain beyond that.",
      "Cohort admission: A7 admits tier A and B only. Decision D4 counts on it.",
      "Cannot be missing where C3 is coded."),
    f("C11", "onset_first_or_major", "C", V["onset_first_or_major"], "required",
      "Whether the onset is the community's first intervention or a later "
      "major project at an established community.",
      "The cohort must either restrict to first interventions or report the "
      "two groups separately; they are different treatments.",
      "'unclear' is valid; report how many."),
    f("C12", "cohort_candidate", "C", V["cohort_candidate"], "required",
      "Whether onset falls in the cohort window.",
      "Assembles the longitudinal cohort; drives the running tally behind "
      "decision D4.",
      "'uncertain' must be resolved before decision D4."),
]

# --------------------------------------------------------------------------
# BLOCK D — EVIDENCE VERIFICATION (5 register fields, 2 derived)
#
# Renamed from 'activity verification' in v2.4. This block records HOW WELL
# DOCUMENTED a community's ecological work is. It does not record how much
# ecological work there is, and it must never be read that way.
# --------------------------------------------------------------------------

BLOCK_D = [
    f("D1", "v1_self_documentation", "D", V["yes_no"], "required",
      "The community describes particular actions rather than aims.",
      "Channel 1 of evidence_tier.",
      "'no' where only aims are stated."),
    f("D2", "v2_external_documentation", "D", V["yes_no"], "required",
      "An academic account, thesis, project record, certification, grant award "
      "or media coverage of the work exists.",
      "Channel 2, and the channel that distinguishes tier A. Carries SC18.",
      "'no' is the expected value for most communities."),
    f("D3", "v3_substantive_affiliation", "D", V["yes_no"], "required",
      "Membership of a body that assesses practice, named.",
      "Channel 3.",
      "'no'."),
    f("D4", "v4_visual_documentation", "D", V["yes_no"], "required",
      "Dated photographs, site plans, design drawings or maps exist.",
      "Channel 4.",
      "'no'."),
    f("D5", "v5_continuity_evidence", "D", V["yes_no"], "required",
      "The work is described consistently across years.",
      "Channel 5.",
      "'no'."),
]

# --------------------------------------------------------------------------
# BLOCK E — SIZE AND LAND (13 register fields)
# --------------------------------------------------------------------------

BLOCK_E = [
    f("E1", "population_value", "E", None, "required",
      "Permanent residents only. Not visitors, volunteers or students.",
      "Stage 2 matching criterion (population within a factor of three); a "
      "model covariate; a named confounder in A4 and A8; population band in "
      "T1 and T12.",
      "'not found'. The quartet is matched on the remaining criteria and "
      "flagged; report how many."),
    f("E2", "population_lower", "E", None, "optional",
      "Lower end where a source gives a range.",
      "Bounds the matching tolerance where the point value is soft.",
      "Blank where the source gives a single figure."),
    f("E3", "population_upper", "E", None, "optional",
      "Upper end where a source gives a range.",
      "As E2.",
      "Blank where the source gives a single figure."),
    f("E4", "population_source_date", "E", None, "required",
      "The year the population figure refers to.",
      "A 2009 figure and a 2024 figure are not in conflict; without the year "
      "the matching tolerance is applied to an unknown quantity.",
      "'not found'. Treat the figure as undated and widen the tolerance."),
    f("E5", "managed_area_ha", "E", None, "required",
      "Land the community actively works ecologically, in hectares. NOT the "
      "total holding.",
      "The only independent check on the drawn polygon. Feeds area_ratio, "
      "area_agreement_tier, table T10 and the SC16 restriction.",
      "'not found'. area_agreement_tier becomes B and the polygon stands "
      "unaffected. This is a complete and correct answer."),
    f("E6", "managed_area_lower_ha", "E", None, "optional",
      "Lowest plausible worked area the sources support.",
      "A source saying 'about 15 ha' and a polygon of 11 ha are not in "
      "conflict; a source saying '15.4 ha under cultivation' and the same "
      "polygon are. The band is what makes the check meaningful.",
      "Blank where the source gives a firm single figure."),
    f("E7", "managed_area_upper_ha", "E", None, "optional",
      "Highest plausible worked area.",
      "As E6.",
      "Blank where the source gives a firm single figure."),
    f("E8", "managed_area_basis", "E", V["managed_area_basis"], "required",
      "How the documentary figure was arrived at.",
      "Weights the corroboration. A 'measured' figure disagreeing with the "
      "polygon means something different from a 'stated' one disagreeing.",
      "'not found' where E5 is 'not found'."),
    f("E9", "managed_area_source_class", "E", V["source_class"], "conditional",
      "Which source class supplied the area figure.",
      "Records whether the only external check on the geometry is itself the "
      "community's own voice.",
      "Blank where E5 is 'not found'."),
    f("E10", "documentary_area_note", "E", None, "conditional",
      "Anything qualifying the figure: whether it plainly refers to worked "
      "land or to the whole holding, whether it covers one parcel or several, "
      "and the year it refers to.",
      "The text a tier C investigation is resolved from.",
      "Blank where E5 is 'not found'."),
    f("E11", "total_holding_ha", "E", None, "optional",
      "The whole landholding.",
      "Exists so that the total holding is never silently substituted for the "
      "worked area, and so a tier C disagreement can be explained. A community "
      "holding 200 ha and working 15 ha has managed_area_ha = 15.",
      "'not found'."),
    f("E12", "area_type", "E", V["area_type"], "required",
      "Which of the two area figures the sources actually give.",
      "Distinguishes 'the community says it works 15 ha' from 'the community "
      "says it holds 200 ha and says nothing about what it works'.",
      "'not stated'."),
    f("E13", "parcel_structure", "E", V["parcel_structure"], "required",
      "One block or several.",
      "A non-contiguous holding is the legitimate reason a documentary area "
      "can exceed the polygon area: the polygon excludes detached parcels more "
      "than 500 m from the centre. Without it, that case is indistinguishable "
      "from a total-holding confusion.",
      "'unknown'."),
]

# --------------------------------------------------------------------------
# BLOCK F — STATUS AND SURVIVORSHIP (5 register fields)
# --------------------------------------------------------------------------

BLOCK_F = [
    f("F1", "status_current", "F", V["status_current"], "required",
      "Present state of the community.",
      "Eligibility criterion E5; the survivorship limitation; T1 sample "
      "description. Dissolved sites are analysed separately.",
      "'unknown'. UNKNOWN IS NOT DISSOLVED."),
    f("F2", "status_evidence", "F", None, "required",
      "What the status rests on.",
      "Dissolution requires positive evidence. This field is that evidence.",
      "Cannot be missing where F1 is coded."),
    f("F3", "last_listing_year", "F", None, "optional",
      "Most recent year the community appears in any directory or archive.",
      "The dating evidence behind status_current; the input to the attrition "
      "estimate in the survivorship section.",
      "'not found'."),
    f("F4", "dissolution_year", "F", None, "conditional",
      "If dissolved, when.",
      "Places a dissolved community on the timeline for the separate analysis.",
      "'n/a' unless F1 = dissolved."),
    f("F5", "delisting_reason", "F", V["delisting_reason"], "conditional",
      "Why the community left a directory.",
      "Separates dissolution from relocation and administrative removal, which "
      "is the discipline that stops a vanished website becoming a vanished "
      "community.",
      "'n/a' where the community is still listed."),
]

# --------------------------------------------------------------------------
# BLOCK G — CONTEXT (3 register fields, 1 derived)
#
# Every field here passes the test: what downstream decision or analysis
# changes because of it? Fields that failed the test were deleted.
# --------------------------------------------------------------------------

BLOCK_G = [
    f("G1", "external_funding_or_programme", "G", None, "required",
      "Any documented state, NGO or grant-funded restoration programme at the "
      "site.",
      "Stage 2 exclusion criterion: a control with a documented external "
      "restoration programme is excluded, and at a settlement such a programme "
      "is a second intervention running in parallel. Also frequently rank-1 "
      "onset evidence.",
      "'none found'."),
    f("G2", "protected_area_status", "G", V["protected_area_status"], "required",
      "Inside or adjacent to a protected area.",
      "Stage 2 exclusion criterion: controls inside protected areas are "
      "excluded.",
      "'unclear'; the quartet is flagged."),
    f("G3", "notable_context", "G", None, "required",
      "War, drought, land dispute, major fire or relocation AFFECTING LAND "
      "COVER INSIDE THE STUDY WINDOW. Not a general history field.",
      "Resolution of flagged outliers in DP10, where an extreme value must be "
      "classed as a data error, an undetected disturbance or a genuine extreme.",
      "'none found'."),
]

# --------------------------------------------------------------------------
# BLOCK H — SOURCE PROVENANCE (12 register fields)
#
# Retained in full as audit metadata under the explicit provenance exemption.
# H6-H9 unpack into rows on Search_Log and Source_Set rather than into cells.
# --------------------------------------------------------------------------

BLOCK_H = [
    f("H1", "pages_opened_count", "H", None, "required",
      "Distinct URLs actually opened, including those yielding nothing.",
      "Effort audit. Separates a thin record from a thin search.",
      "Cannot be missing."),
    f("H2", "source_classes_found", "H", None, "required",
      "Which of S1-S8 were located.",
      "Shows at a glance whether anything outside the community's own voice "
      "was found.",
      "Cannot be missing."),
    f("H3", "search_languages", "H", None, "required",
      "Which languages were searched.",
      "A community that publishes only in its own language and was searched "
      "only in English produces an absence of effort, not an absence of evidence.",
      "Cannot be missing."),
    f("H4", "negative_consultations", "H", None, "required",
      "Source classes and databases checked and found empty.",
      "The field that makes 'evidence absent' distinguishable from 'not looked "
      "for'. Required by the three-state success criterion.",
      "Cannot be missing."),
    f("H5", "documents_opened", "H", None, "required",
      "PDFs, spreadsheets and other files opened, by title.",
      "Documents carry most rank-1 and rank-2 onset evidence; this records "
      "whether any were reached.",
      "'none' is valid."),
    f("H6", "academic_search_log", "H", None, "required",
      "Which databases searched, how many hits, how many opened in full text "
      "versus abstract only. UNPACKS INTO Search_Log ROWS, one per database.",
      "The negative consultation record for Stage 5, which is now the "
      "highest-priority evidence route.",
      "Rows must exist even where every database returned nothing."),
    f("H7", "grey_literature_log", "H", None, "required",
      "Grey sources found, by type. UNPACKS INTO Search_Log ROWS.",
      "The negative consultation record for Stage 6.",
      "Rows must exist even where nothing was found."),
    f("H8", "source_set_supplied", "H", None, "required",
      "Every address supplied: URL, platform type, independence group, crawl "
      "status, pages opened. UNPACKS INTO Source_Set ROWS.",
      "Proves each supplied address was opened separately rather than "
      "collapsed into one.",
      "Every supplied address must appear with a status."),
    f("H9", "source_set_discovered", "H", None, "required",
      "Every address found during the crawl that was not supplied. UNPACKS "
      "INTO Source_Set ROWS.",
      "Former domains hold the oldest material and are the best open-web "
      "dating source. This is where onset yield usually comes from.",
      "'none discovered' is valid."),
    f("H10", "independence_groups", "H", None, "required",
      "How many distinct independence groups the sources fall into.",
      "channel_count and evidence_tier are built on groups, never on URLs. "
      "Also the number behind any claim that sources corroborate each other.",
      "Cannot be missing."),
    f("H11", "stages_completed", "H", None, "required",
      "Which of stages 0-9 were completed, cut short, or never reached.",
      "Turns a silent half-search into a recorded one.",
      "Cannot be missing."),
    f("H12", "crawl_truncated", "H", V["yes_no"], "required",
      "Did the run stop before the protocol was finished?",
      "Without it, a community searched for four minutes and a community "
      "searched exhaustively that genuinely has nothing look identical in the "
      "data. They mean opposite things.",
      "Cannot be missing."),
]

REGISTER_BLOCKS = {
    "A": ("Identity and location", BLOCK_A),
    "B": ("Eligibility", BLOCK_B),
    "C": ("Onset dating", BLOCK_C),
    "D": ("Evidence verification", BLOCK_D),
    "E": ("Size and land", BLOCK_E),
    "F": ("Status and survivorship", BLOCK_F),
    "G": ("Context", BLOCK_G),
    "H": ("Source provenance", BLOCK_H),
}

REGISTER_FIELDS = [x for _, (_, lst) in REGISTER_BLOCKS.items() for x in lst]


# --------------------------------------------------------------------------
# DERIVED AND RESEARCHER-SUPPLIED FIELDS
# These are NOT register fields. A search assistant must never supply them.
# --------------------------------------------------------------------------

DERIVED = [
    f(None, "channel_count", "derived", None, "derived",
      "How many of V1-V5 are satisfied.",
      "Input to evidence_tier.",
      "Computed; blank until V1-V5 are entered.", derived=True),
    f(None, "evidence_tier", "derived", V["evidence_tier"], "derived",
      "A = 3 or more channels including at least one external; B = 2 channels "
      "including at least one of visual or continuity; C = 2 "
      "community-originated channels; Fail = fewer than 2. AN EVIDENCE-QUALITY "
      "VARIABLE, NOT AN ECOLOGICAL-PERFORMANCE VARIABLE.",
      "Named confounder in A4; sample description T1 and T5; the restriction "
      "in SC18; T12 context.",
      "Computed; blank until V1-V5 are entered.", derived=True),
    f(None, "founding_decade", "derived", None, "derived",
      "Decade of date_formal_founding.",
      "Named confounder (cohort) in A4.",
      "Blank where date_formal_founding is 'not found'.", derived=True),
    f(None, "onset_band_width_years", "derived", None, "derived",
      "onset_upper_bound minus onset_lower_bound.",
      "The width A4's multiple imputation draws over.",
      "Blank until both bounds are entered.", derived=True),
    f(None, "below_minimum_flag", "derived", None, "derived",
      "'yes' where the polygon is under 1.0 ha.",
      "Sends the site to a 75 m circle and flags it.",
      "Computed from polygon_area_ha.", derived=True),
    f(None, "reference_circle", "derived", V["reference_circle"], "derived",
      "Which of the five reference-circle sizes the site is rescaled against, "
      "whichever is closest in AREA to the polygon.",
      "Rescaling. A site rescaled against a reference distribution computed on "
      "the wrong unit size is biased, invisibly.",
      "Computed from polygon_area_ha.", derived=True),
    f(None, "equal_area_circle_radius_m", "derived", None, "derived",
      "Radius of the circle whose area equals the polygon's: sqrt(A/pi).",
      "The alternative measurement geometry for SC1, generated rather than "
      "hand-computed.",
      "Computed from polygon_area_ha.", derived=True),
    f(None, "area_ratio", "derived", None, "derived",
      "documentary managed area divided by polygon area.",
      "Input to area_agreement_tier and to table T10.",
      "Blank where either figure is absent.", derived=True),
    f(None, "area_agreement_tier", "derived", V["area_agreement_tier"], "derived",
      "A = within 30 per cent; B = no documentary figure, or a gap of 30 to "
      "100 per cent; C = a gap beyond a factor of two.",
      "The SC16 restriction. The polygon stands in every case; the tier records "
      "how well corroborated it is.",
      "A site with a polygon and no documentary figure is tier B, NEVER blank.",
      derived=True),
]

RESEARCHER_FIELDS = [
    f(None, "site_id", "key", None, "required",
      "The study's sole key. Names are not unique; identifiers must be.",
      "Every join in DP8. A key mismatch drops rows silently.",
      "Cannot be missing.", researcher=True),
    f(None, "latitude", "researcher", None, "required",
      "Held coordinate, latitude.",
      "The centre of the polygon, the rings and the common circle.",
      "Cannot be missing.", researcher=True),
    f(None, "longitude", "researcher", None, "required",
      "Held coordinate, longitude.",
      "As latitude.",
      "Cannot be missing.", researcher=True),
    f(None, "polygon_area_ha", "researcher", None, "required",
      "Area enclosed by the hand-drawn outline of the managed ground.",
      "THE PRIMARY MEASUREMENT GEOMETRY. Picks the reference circle; the "
      "predictor in A8; the translated control geometry.",
      "Cannot be missing. Every settlement is drawn.", researcher=True),
    f(None, "polygon_file_id", "researcher", None, "required",
      "The exported shapefile or GeoJSON feature id.",
      "The Earth Engine table asset join. A mismatch fails the DP8 join.",
      "Cannot be missing.", researcher=True),
    f(None, "polygon_imagery_date", "researcher", None, "required",
      "Capture date of the imagery drawn on.",
      "Imagery outside the study window may show an extent that did not exist "
      "during it.",
      "Cannot be missing.", researcher=True),
    f(None, "polygon_imagery_source", "researcher", V["polygon_imagery_source"],
      "required", "Which imagery was drawn on.",
      "Provenance of the primary measurement.",
      "Cannot be missing.", researcher=True),
    f(None, "polygon_confidence", "researcher", V["polygon_confidence"], "required",
      "How clear the managed boundary was: clear, moderate or poor.",
      "Reported beside the redraw overlap in the reliability table.",
      "Cannot be missing.", researcher=True),
    f(None, "polygon_redrawn", "researcher", V["yes_no"], "required",
      "Whether this site is in the 20 per cent redraw subsample.",
      "Identifies the reliability subsample.",
      "Cannot be missing.", researcher=True),
    f(None, "redraw_area_ha", "researcher", None, "conditional",
      "Area of the second, independent drawing.",
      "Reliability of the primary geometry.",
      "Blank unless polygon_redrawn = yes.", researcher=True),
    f(None, "polygon_iou", "researcher", None, "conditional",
      "Shared area divided by combined area between the two drawings.",
      "THE reliability statistic for the study's primary measurement. Reported "
      "as its own table. A mean below 0.80 makes SC1 the primary specification.",
      "Blank unless polygon_redrawn = yes.", researcher=True),
    f(None, "agreement_note", "researcher", None, "conditional",
      "What was found when a tier C disagreement was investigated.",
      "Absolute rule: a source conflict is never resolved silently.",
      "Blank unless area_agreement_tier = C.", researcher=True),
    f(None, "controls_translated", "researcher", V["yes_no"], "required",
      "Whether the polygon has been translated onto all three controls.",
      "A control measured over a circle while its settlement is measured over "
      "a drawn shape would produce a difference from geometry alone.",
      "Cannot be missing at Stage 1 close.", researcher=True),
]


# --------------------------------------------------------------------------
# WHAT MUST NEVER BE SEARCHED FOR — computational outputs
# --------------------------------------------------------------------------

NEVER_SEARCH = [
    ("VM1-VM14", "All fourteen vegetation condition metrics", "Sentinel-2, computed in the pipeline"),
    ("PM1-PM3", "Provisioning metrics", "Sentinel-2, computed in the pipeline"),
    ("FC1-FC4", "Flag components", "Sentinel-2 and CHIRPS"),
    ("CA", "Contour alignment", "SRTM aspect and land-cover boundary orientation"),
    ("VCI, VCI-P/S/T/C, PCI, MDS, LCC", "The index and its components", "Derived from the above"),
    ("built_fraction, tree_cover_pct", "Land-cover fractions", "Dynamic World"),
    ("elevation_m, slope_deg, terrain class", "Terrain", "SRTM"),
    ("water_dist_m", "Distance to permanent water", "Global Surface Water"),
    ("koppen_group, biome", "Stratifiers", "Beck et al. / RESOLVE ecoregions"),
    ("rainfall, driest month, drought-year classification", "Climate", "CHIRPS"),
    ("n_clear", "Clear-observation count", "Extraction output"),
    ("polygon_area_ha, polygon_iou, reference_circle, equal_area_circle_radius_m",
     "The drawn geometry", "The researcher's own drawing. Never estimated from imagery by anyone else"),
    ("control_distance_km", "How far each control sits from its settlement",
     "A Stage 2 matching output, not documentary coding"),
]


# --------------------------------------------------------------------------
# HYPOTHESIS AND ANALYSIS REGISTER — v4.0, with the v3.8 mapping
# --------------------------------------------------------------------------

HYPOTHESES = [
    ("H1", "A1", "PRIMARY", "H1",
     "Settlements score HIGHER than their matched controls on vegetation condition"),
    ("H2", "A2", "PRIMARY", "H2",
     "Settlements are NOT LOWER than their controls on provisioning capacity, "
     "within a declared margin"),
    ("H3", "A3", "Secondary", "H3",
     "The settlement advantage is larger near the centre and smaller further out"),
    ("H4", "A4", "Secondary", "H4",
     "The advantage is larger at settlements that began intervening longer ago"),
    ("H5", "A5", "Secondary", "H5",
     "The advantage holds when only management-diagnostic metrics are used"),
    ("H6", "A6", "Secondary", "H7",
     "The advantage is not explained by low settlement density alone"),
    ("H7", "A7", "Secondary", "H8",
     "Among communities whose work began in 2020-2021, vegetation condition "
     "IMPROVES over the four years after onset relative to matched controls, "
     "with no divergence in the three years BEFORE onset"),
    ("H8", "A8", "Secondary", "H9",
     "The settlement advantage varies with how much land a community works, "
     "BEYOND what measurement dilution alone predicts"),
]

DELETED_HYPOTHESES = [
    ("H6 (v3.8)", "A6 (v3.8)",
     "Communities claiming a practice show the signature that practice predicts",
     "Deleted. See DECISION_MEMO.md."),
]

MDE = [
    ("A1", "Condition, matched contrast", "0.22 SD  =~ 0.020 NDVI", "The study's best-powered test."),
    ("A2", "Provisioning, equivalence", "0.22 SD  =~ 0.020 NDVI", "Against a declared margin of 0.15 SD."),
    ("A3", "Ring interaction", "0.36 SD  =~ 0.032 NDVI", "Interactions cost precision."),
    ("A4", "Age interaction", "0.44 SD  =~ 0.040 NDVI",
     "The weakest secondary test, further attenuated by onset dating error."),
    ("A5", "Management-diagnostic score", "0.22 SD  =~ 0.020 NDVI",
     "Same power as A1 - the same contrast on a different scale."),
    ("A6", "Density comparison", "0.40 SD  =~ 0.035 NDVI", "1:1 matching against ~150 held-out sites."),
    ("A7", "Pre-onset difference-in-differences", "0.40 SD  =~ 0.006-0.012 NDVI",
     "The NDVI-unit figure is much smaller because the residual is interannual "
     "rather than between-site variation."),
    ("A8", "Size gradient", "0.44 SD at n = 212",
     "A smooth interaction, so it carries the same penalty as A4. Every site "
     "has a polygon, so n is 212 with no uncoded-area attrition."),
]

SENSITIVITY_CHECKS = 18
PLACEBO_TESTS = 3
FDR_FAMILY_SIZE = 6
MULTIPLICITY_FAMILIES = 1

# Counts recalculated for v4.0 rather than carried forward.
COUNTS = {
    "hypotheses": 8,
    "primary_hypotheses": 2,
    "secondary_hypotheses": 6,
    "analyses": 8,
    "objectives": 8,
    "sensitivity_checks": 18,
    "placebo_tests": 3,
    "reported_robustness_items": 21,
    "multiplicity_families": 1,
    "fdr_family_size": 6,
    "condition_metrics": 14,
    "supplementary_metrics": 1,
    "provisioning_metrics": 3,
    "flag_components": 4,
    "flags": 2,
    "mds_metrics": 7,
    "dimensions": 4,
    "reference_pools": 3,
    "reference_radii": 5,
    "zones_per_study_site": 7,
    "settlements": 212,
    "controls": 636,
    "study_sites": 848,
    "cohort_settlements": 65,
    "cohort_sites": 260,
    "reference_sites": 1350,
    "total_sites": 2458,
    "panel_rows": 105182,
    "register_fields": 61,
    "register_blocks": 8,
    "workbook_sheets": 15,
    "reliability_variables": 14,
    "crawl_stages": 10,
    "anti_fabrication_rules": 12,
    "study_years": 7,
    "cohort_years": 9,
    "detectable_difference_sd": 0.222,
}


def panel_rows():
    """Recomputed, not copied forward. See CONSISTENCY_AUDIT.md."""
    main = 848 * 7 * 7          # 7 geometries x 7 vegetation years
    reference = 1350 * 5 * 7    # 5 radii x 7 vegetation years, no rings
    cohort = 260 * 7 * 9        # 7 geometries x 9 vegetation years
    return main, reference, cohort, main + reference + cohort


if __name__ == "__main__":
    n = len(REGISTER_FIELDS)
    print("register fields:", n)
    for k, (label, lst) in REGISTER_BLOCKS.items():
        print(f"  {k} {label}: {len(lst)}")
    assert n == COUNTS["register_fields"], (n, COUNTS["register_fields"])
    m, r, c, t = panel_rows()
    print("panel rows:", m, "+", r, "+", c, "=", t)
    assert t == COUNTS["panel_rows"], (t, COUNTS["panel_rows"])
    names = [x.name for x in REGISTER_FIELDS + DERIVED + RESEARCHER_FIELDS]
    assert len(names) == len(set(names)), "duplicate field name"
    print("derived:", len(DERIVED), " researcher:", len(RESEARCHER_FIELDS))
    print("OK")
