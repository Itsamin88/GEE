-- ===========================================================================
-- Documentary research crawler — durable local store.
--
-- The Excel workbook is an export layer. THIS is the record: every artefact
-- keeps its provenance here so the workbook can be rebuilt, a claim audited, a
-- document reprocessed or a field added without re-crawling anything.
-- ===========================================================================
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- --------------------------------------------------------------------------
-- Communities and runs
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS communities (
    community_id      TEXT PRIMARY KEY,          -- IC001, or TEST-IC001 for fixtures
    site_id           TEXT NOT NULL,             -- what goes in the workbook's site_id column
    name_input        TEXT NOT NULL,             -- exactly what the researcher typed
    safe_name         TEXT NOT NULL,             -- filesystem-safe form
    latitude          REAL,                      -- researcher-supplied only
    longitude         REAL,                      -- researcher-supplied only
    country_hint      TEXT,
    mode              TEXT NOT NULL DEFAULT 'SETTLEMENT',  -- SETTLEMENT | CONTROL
    provenance_mode   TEXT NOT NULL DEFAULT 'LIVE',        -- LIVE | FIXTURE  (DCR-D022)
    output_dir        TEXT,
    completion_status TEXT,                      -- COMPLETE | COMPLETE_WITH_UNCERTAINTY | ...
    created_utc       TEXT NOT NULL,
    updated_utc       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS community_names (
    community_id TEXT NOT NULL REFERENCES communities(community_id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    name_kind    TEXT NOT NULL,   -- official | alternative | local | former | legal_entity | founder | transliteration
    language     TEXT,
    source_id    TEXT,            -- NULL where supplied by the researcher
    confidence   REAL,
    created_utc  TEXT NOT NULL,
    PRIMARY KEY (community_id, name, name_kind)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id        TEXT PRIMARY KEY,
    community_id  TEXT NOT NULL REFERENCES communities(community_id) ON DELETE CASCADE,
    mode          TEXT NOT NULL,   -- FULL | SOURCE | ACADEMIC | RECONCILE | RESUME | RETRY_FAILED | AUDIT | EXPORT
    target        TEXT,            -- address_id for SOURCE runs
    status        TEXT NOT NULL,   -- running | complete | interrupted | failed
    truncated     INTEGER,         -- 1 = crawl_truncated yes
    truncation_reason TEXT,
    app_version   TEXT NOT NULL,
    config_hash   TEXT NOT NULL,
    manifest_json TEXT,
    started_utc   TEXT NOT NULL,
    finished_utc  TEXT
);

CREATE TABLE IF NOT EXISTS run_stages (
    run_id      TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    stage_no    INTEGER NOT NULL,
    stage_name  TEXT NOT NULL,
    status      TEXT NOT NULL,   -- complete | partial | blocked | not_reached | failed
    detail      TEXT,
    started_utc TEXT,
    finished_utc TEXT,
    PRIMARY KEY (run_id, stage_no)
);

-- --------------------------------------------------------------------------
-- Sources (one row per web address) and the domains behind them
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sources (
    source_id            TEXT PRIMARY KEY,   -- IC001-S001
    community_id         TEXT NOT NULL REFERENCES communities(community_id) ON DELETE CASCADE,
    address_id           TEXT NOT NULL,      -- IC001-01, the register's own address numbering
    url                  TEXT NOT NULL,
    canonical_url        TEXT,
    domain               TEXT,
    registrable_domain   TEXT,
    platform_type        TEXT,               -- O11 vocabulary
    source_class         TEXT,               -- S1..S8
    supplied_or_discovered TEXT NOT NULL,    -- supplied | discovered
    discovery_method     TEXT,
    discovery_query      TEXT,
    discovered_from      TEXT,               -- source_id that led here
    independence_group   TEXT,               -- G1, G2 ...
    independence_reason  TEXT,
    language             TEXT,
    http_status          INTEGER,
    access_status        TEXT,               -- ok | blocked | dead | login_required | js_required | robots_denied | not_attempted
    crawl_status         TEXT,               -- crawled | partial | blocked | dead link | not attempted
    belongs_confirmed    INTEGER DEFAULT 0,  -- Stage 1 identity confirmation
    belongs_evidence     TEXT,
    first_discovered_utc TEXT,
    last_crawled_utc     TEXT,
    archive_checked      INTEGER DEFAULT 0,
    archive_earliest_snapshot TEXT,
    archive_snapshot_count INTEGER DEFAULT 0,
    pages_opened         INTEGER DEFAULT 0,
    documents_found      INTEGER DEFAULT 0,
    images_found         INTEGER DEFAULT 0,
    evidence_count       INTEGER DEFAULT 0,
    earliest_dated_item  TEXT,
    latest_dated_item    TEXT,
    budget_pages         INTEGER,
    budget_spent         INTEGER DEFAULT 0,
    exhausted            INTEGER DEFAULT 0,
    retrieval_priority   TEXT,               -- A | B | C  (crawl priority, NOT evidence rank)
    notes                TEXT,
    UNIQUE (community_id, url)
);
CREATE INDEX IF NOT EXISTS idx_sources_community ON sources(community_id);

CREATE TABLE IF NOT EXISTS domains (
    domain            TEXT PRIMARY KEY,
    robots_status     TEXT,          -- fetched | missing | unreachable
    robots_body       TEXT,
    crawl_delay_s     REAL,
    sitemaps          TEXT,          -- JSON array of sitemap URLs found
    feeds             TEXT,          -- JSON array of feed URLs found
    platform_engine   TEXT,          -- wordpress | blogspot | ghost | wix | ...
    checked_utc       TEXT
);

-- Relations between sources: which copied which, which superseded which.
CREATE TABLE IF NOT EXISTS source_relations (
    source_a   TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    source_b   TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    relation   TEXT NOT NULL,   -- copy_of | mirrors | former_domain_of | links_to | cites | same_operator
    similarity REAL,
    evidence   TEXT,
    created_utc TEXT NOT NULL,
    PRIMARY KEY (source_a, source_b, relation)
);

-- --------------------------------------------------------------------------
-- The crawl frontier — persisted so a run can resume exactly where it stopped
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS frontier (
    url_key       TEXT NOT NULL,          -- sha1 of the normalised URL
    community_id  TEXT NOT NULL REFERENCES communities(community_id) ON DELETE CASCADE,
    source_id     TEXT,
    url           TEXT NOT NULL,
    normalized_url TEXT NOT NULL,
    depth         INTEGER NOT NULL DEFAULT 0,
    priority      REAL NOT NULL DEFAULT 0,
    kind          TEXT NOT NULL DEFAULT 'page',  -- page | document | image | archive | api
    stage         INTEGER,
    discovered_by TEXT,
    status        TEXT NOT NULL DEFAULT 'queued', -- queued | in_flight | done | failed | skipped | deferred
    attempts      INTEGER NOT NULL DEFAULT 0,
    last_error    TEXT,
    added_utc     TEXT NOT NULL,
    updated_utc   TEXT NOT NULL,
    PRIMARY KEY (community_id, url_key)
);
CREATE INDEX IF NOT EXISTS idx_frontier_status ON frontier(community_id, status, priority DESC);

-- --------------------------------------------------------------------------
-- Pages, documents and images
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pages (
    page_id        TEXT PRIMARY KEY,      -- IC001-P0001
    community_id   TEXT NOT NULL REFERENCES communities(community_id) ON DELETE CASCADE,
    source_id      TEXT REFERENCES sources(source_id) ON DELETE SET NULL,
    url            TEXT NOT NULL,
    normalized_url TEXT NOT NULL,
    final_url      TEXT,
    http_status    INTEGER,
    content_type   TEXT,
    bytes          INTEGER,
    sha256         TEXT,
    title          TEXT,
    language       TEXT,
    published_date TEXT,                  -- the page's own date, if it states one
    archive_timestamp TEXT,               -- set when this page IS an archived snapshot
    archived_original TEXT,
    depth          INTEGER,
    discovery_method TEXT,
    render_mode    TEXT,                  -- http | browser | archive
    text_path      TEXT,                  -- 05_extracted_text/...
    text_chars     INTEGER,
    simhash        TEXT,
    yielded_evidence INTEGER DEFAULT 0,
    stage          INTEGER,
    fetched_utc    TEXT NOT NULL,
    notes          TEXT,
    UNIQUE (community_id, normalized_url, archive_timestamp)
);
CREATE INDEX IF NOT EXISTS idx_pages_source ON pages(source_id);

-- Content is stored once, under its hash (DCR-D018).
CREATE TABLE IF NOT EXISTS documents (
    document_id     TEXT PRIMARY KEY,     -- IC001-D001
    community_id    TEXT NOT NULL REFERENCES communities(community_id) ON DELETE CASCADE,
    sha256          TEXT NOT NULL,
    filename        TEXT,
    title           TEXT,
    mime_declared   TEXT,
    mime_sniffed    TEXT,
    extension       TEXT,
    bytes           INTEGER,
    storage_path    TEXT,
    page_count      INTEGER,
    publication_date TEXT,
    language        TEXT,
    parser          TEXT,
    parser_status   TEXT,   -- parsed | unsupported_format | corrupt | encrypted | too_large | not_attempted
    text_status     TEXT,   -- extracted | empty | ocr_used | ocr_unavailable | failed
    table_status    TEXT,   -- extracted | none_found | unavailable | failed
    image_status    TEXT,   -- extracted | none_found | unavailable | failed
    text_path       TEXT,
    text_chars      INTEGER,
    simhash         TEXT,
    doc_kind        TEXT,   -- report | thesis | paper | permit | plan | newsletter | inventory | unknown
    notes           TEXT,
    created_utc     TEXT NOT NULL,
    UNIQUE (community_id, sha256)
);

-- One row per (document, source) so a mirrored file keeps every provenance.
CREATE TABLE IF NOT EXISTS document_sources (
    document_id    TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    source_id      TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    original_url   TEXT NOT NULL,
    final_url      TEXT,
    archive_url    TEXT,
    archive_timestamp TEXT,
    discovery_stage INTEGER,
    discovery_method TEXT,
    retrieved_utc  TEXT NOT NULL,
    PRIMARY KEY (document_id, source_id, original_url)
);

CREATE TABLE IF NOT EXISTS document_tables (
    table_id     TEXT PRIMARY KEY,   -- IC001-T001
    document_id  TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    community_id TEXT NOT NULL,
    sheet_name   TEXT,
    page_number  INTEGER,
    cell_range   TEXT,
    n_rows       INTEGER,
    n_cols       INTEGER,
    header_json  TEXT,
    csv_path     TEXT,
    created_utc  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS images (
    image_id        TEXT PRIMARY KEY,   -- IC001-IMG0001
    community_id    TEXT NOT NULL REFERENCES communities(community_id) ON DELETE CASCADE,
    source_id       TEXT REFERENCES sources(source_id) ON DELETE SET NULL,
    document_id     TEXT REFERENCES documents(document_id) ON DELETE SET NULL,
    page_id         TEXT REFERENCES pages(page_id) ON DELETE SET NULL,
    sha256          TEXT NOT NULL,
    filename        TEXT,
    local_path      TEXT,
    original_url    TEXT,
    page_number     INTEGER,
    width           INTEGER,
    height          INTEGER,
    bytes           INTEGER,
    format          TEXT,
    source_title    TEXT,
    publication_date TEXT,
    image_type      TEXT,             -- site plan | map | photograph | diagram | aerial | before_after | unknown
    research_topic  TEXT,
    caption         TEXT,
    alt_text        TEXT,
    surrounding_text TEXT,
    surrounding_summary TEXT,
    evidence_subject TEXT,
    possible_fields TEXT,             -- semicolon list of workbook fields it MAY support
    visual_evidence_allowed TEXT,     -- what the image alone may evidence (never a practice code)
    documentary_text_support TEXT,    -- the caption/text that would license a claim, or NOT FOUND
    image_date      TEXT,
    image_date_confidence TEXT,
    ocr_text        TEXT,
    ocr_status      TEXT,
    relevance_class TEXT,             -- likely_relevant | possibly_relevant | decorative | uncertain
    relevance_score REAL,
    relevance_reason TEXT,
    confidence      REAL,
    classifier      TEXT,
    notes           TEXT,
    created_utc     TEXT NOT NULL,
    UNIQUE (community_id, sha256, source_id)
);

-- --------------------------------------------------------------------------
-- Evidence -> Claim -> Field
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id    TEXT PRIMARY KEY,   -- IC001-E0001
    community_id   TEXT NOT NULL REFERENCES communities(community_id) ON DELETE CASCADE,
    source_id      TEXT REFERENCES sources(source_id) ON DELETE SET NULL,
    document_id    TEXT REFERENCES documents(document_id) ON DELETE SET NULL,
    page_id        TEXT REFERENCES pages(page_id) ON DELETE SET NULL,
    image_id       TEXT REFERENCES images(image_id) ON DELETE SET NULL,
    table_id       TEXT REFERENCES document_tables(table_id) ON DELETE SET NULL,
    evidence_type  TEXT NOT NULL,      -- passage | table_cell | metadata | image | caption | upload_date | archive_snapshot
    locator        TEXT,               -- 'p.12' | 'Sheet1!B7' | 'section: History'
    section        TEXT,
    page_number    INTEGER,
    quote          TEXT NOT NULL,      -- the exact wording, never paraphrased
    context        TEXT,
    language       TEXT,
    translated_quote TEXT,
    translation_method TEXT,
    translation_verified TEXT,
    char_start     INTEGER,
    char_end       INTEGER,
    source_class   TEXT,
    publication_date TEXT,
    retrieval_date TEXT,
    created_utc    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_community ON evidence(community_id);

CREATE TABLE IF NOT EXISTS claims (
    claim_id        TEXT PRIMARY KEY,  -- IC001-C0001
    community_id    TEXT NOT NULL REFERENCES communities(community_id) ON DELETE CASCADE,
    field_name      TEXT NOT NULL,
    value           TEXT,
    value_type      TEXT,              -- year | integer | float | enum | text | boolean
    original_value  TEXT,              -- exactly as the source stated it, units and all
    normalized_value TEXT,             -- the converted form, kept separately (rule 8)
    normalization_note TEXT,
    exact_wording   TEXT,
    source_id       TEXT REFERENCES sources(source_id) ON DELETE SET NULL,
    document_id     TEXT REFERENCES documents(document_id) ON DELETE SET NULL,
    evidence_id     TEXT REFERENCES evidence(evidence_id) ON DELETE SET NULL,
    image_id        TEXT REFERENCES images(image_id) ON DELETE SET NULL,
    locator         TEXT,
    publication_date TEXT,
    reference_year  INTEGER,           -- the year the VALUE refers to (DCR-D008)
    retrieval_date  TEXT,
    source_class    TEXT,
    independence_group TEXT,
    evidence_rank   INTEGER,           -- onset rank 1-5 where applicable
    coding_level    TEXT,              -- practice codes only
    confidence      REAL,
    conflict_status TEXT,              -- none | conflicting | superseded | time_series
    rationale       TEXT,
    extractor       TEXT NOT NULL,     -- rule:<name> | llm:<model> | metadata
    model_name      TEXT,
    prompt_version  TEXT,
    extracted_utc   TEXT NOT NULL,
    verified_passage INTEGER DEFAULT 0,
    notes           TEXT
);
CREATE INDEX IF NOT EXISTS idx_claims_field ON claims(community_id, field_name);

-- The resolved value per field, with the reasoning that produced it.
CREATE TABLE IF NOT EXISTS field_values (
    community_id   TEXT NOT NULL REFERENCES communities(community_id) ON DELETE CASCADE,
    field_name     TEXT NOT NULL,
    value          TEXT,
    status         TEXT NOT NULL,   -- coded | not_found | not_searched | blocked | review_required | researcher_input
    method         TEXT,            -- single_source | rank_resolution | earliest_of_equal_rank | time_series | rule
    claim_ids      TEXT,            -- semicolon list
    source_ids     TEXT,
    independence_groups TEXT,
    group_count    INTEGER,
    residual_uncertainty TEXT,
    rationale      TEXT,
    updated_utc    TEXT NOT NULL,
    PRIMARY KEY (community_id, field_name)
);

CREATE TABLE IF NOT EXISTS conflicts (
    conflict_id    TEXT PRIMARY KEY,   -- IC001-X001
    community_id   TEXT NOT NULL REFERENCES communities(community_id) ON DELETE CASCADE,
    field_name     TEXT NOT NULL,
    value_a        TEXT,
    claim_a        TEXT,
    source_a       TEXT,
    group_a        TEXT,
    rank_a         INTEGER,
    date_a         TEXT,
    value_b        TEXT,
    claim_b        TEXT,
    source_b       TEXT,
    group_b        TEXT,
    rank_b         INTEGER,
    date_b         TEXT,
    rule_invoked   TEXT,
    resolution_type TEXT,             -- rule applied | unresolved | time_series | evidence_re_examined
    final_value    TEXT,
    residual_uncertainty TEXT,
    human_review   INTEGER DEFAULT 0,
    created_utc    TEXT NOT NULL
);

-- --------------------------------------------------------------------------
-- Searches: every consultation, including the empty and the unreachable ones
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS searches (
    search_id      TEXT PRIMARY KEY,
    community_id   TEXT NOT NULL REFERENCES communities(community_id) ON DELETE CASCADE,
    run_id         TEXT,
    stage          INTEGER,
    database_id    TEXT,
    database_name  TEXT NOT NULL,
    database_type  TEXT NOT NULL,     -- O7 vocabulary
    query          TEXT NOT NULL,
    language       TEXT,
    hits_returned  INTEGER,
    full_text_opened INTEGER DEFAULT 0,
    abstract_only  INTEGER DEFAULT 0,
    result         TEXT NOT NULL,     -- hits found | none found | unreachable | paywalled
    http_status    INTEGER,
    detail         TEXT,
    searched_utc   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_searches_community ON searches(community_id);

CREATE TABLE IF NOT EXISTS academic_records (
    record_id       TEXT PRIMARY KEY,
    community_id    TEXT NOT NULL REFERENCES communities(community_id) ON DELETE CASCADE,
    database_id     TEXT,
    title           TEXT NOT NULL,
    authors         TEXT,
    year            INTEGER,
    venue           TEXT,
    doi             TEXT,
    url             TEXT,
    repository      TEXT,
    record_type     TEXT,             -- paper | thesis | conference | preprint | report | dataset
    abstract        TEXT,
    full_text_status TEXT NOT NULL,   -- full text | abstract only | record only | unreachable
    verified_resolves TEXT NOT NULL DEFAULT 'no',  -- yes | no  (DCR-D013)
    verification_detail TEXT,
    verified_utc    TEXT,
    relevance_score REAL,
    relevance_reason TEXT,
    source_id       TEXT,
    document_id     TEXT,
    citation_depth  INTEGER DEFAULT 0,
    cited_by_record TEXT,
    created_utc     TEXT NOT NULL
);

-- --------------------------------------------------------------------------
-- Failures, review queue, and the text-fingerprint store
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS errors (
    error_id      TEXT PRIMARY KEY,
    run_id        TEXT,
    community_id  TEXT,
    stage         INTEGER,
    source_id     TEXT,
    url           TEXT,
    error_type    TEXT NOT NULL,
    http_status   INTEGER,
    retry_count   INTEGER DEFAULT 0,
    resolution    TEXT,              -- retried_ok | permanent | deferred | skipped | unresolved
    unresolved    INTEGER DEFAULT 1,
    human_review  INTEGER DEFAULT 0,
    detail        TEXT,
    ts_utc        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_errors_community ON errors(community_id);

CREATE TABLE IF NOT EXISTS review_queue (
    item_id      TEXT PRIMARY KEY,
    community_id TEXT NOT NULL REFERENCES communities(community_id) ON DELETE CASCADE,
    category     TEXT NOT NULL,
    subject      TEXT NOT NULL,
    detail       TEXT,
    severity     TEXT NOT NULL DEFAULT 'normal',  -- blocking | normal | advisory
    related_ids  TEXT,
    suggested_action TEXT,
    resolved     INTEGER DEFAULT 0,
    created_utc  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fingerprints (
    fingerprint_id TEXT PRIMARY KEY,
    community_id  TEXT NOT NULL,
    kind          TEXT NOT NULL,   -- page | document | source
    ref_id        TEXT NOT NULL,
    source_id     TEXT,
    simhash       TEXT NOT NULL,
    shingles      TEXT,            -- JSON array of hashed shingles (sampled)
    text_chars    INTEGER,
    created_utc   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fingerprints_community ON fingerprints(community_id, kind);

CREATE TABLE IF NOT EXISTS translations (
    translation_id TEXT PRIMARY KEY,
    community_id   TEXT NOT NULL,
    evidence_id    TEXT,
    source_language TEXT,
    target_language TEXT,
    method         TEXT NOT NULL,      -- llm | dictionary | none
    original_text  TEXT NOT NULL,
    translated_text TEXT,
    verified       TEXT NOT NULL DEFAULT 'no',
    created_utc    TEXT NOT NULL
);

-- Every change the exporter makes to a workbook field, so the study can see
-- what moved between runs.
CREATE TABLE IF NOT EXISTS field_change_log (
    change_id    TEXT PRIMARY KEY,
    community_id TEXT NOT NULL,
    run_id       TEXT,
    field_name   TEXT NOT NULL,
    old_value    TEXT,
    new_value    TEXT,
    reason       TEXT,
    ts_utc       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS discovery_log (
    discovery_id TEXT PRIMARY KEY,
    community_id TEXT NOT NULL,
    run_id       TEXT,
    stage        INTEGER,
    method       TEXT NOT NULL,      -- sitemap | feed | path_probe | link | search | cdx | footer | oembed | api
    query        TEXT,
    input_ref    TEXT,
    found_url    TEXT,
    outcome      TEXT NOT NULL,      -- new_source | new_url | duplicate | out_of_scope | failed
    detail       TEXT,
    ts_utc       TEXT NOT NULL
);

-- ===========================================================================
-- Run control: pause, resume, cancel, connectivity and checkpointing.
--
-- The state below is what makes an interruption survivable. It is written
-- BEFORE the crawler stops, so a laptop that loses its network, or a
-- researcher who presses PAUSE and shuts the machine down, can be resumed
-- from the last safe boundary rather than restarted.
--
-- An interruption is never an absence of evidence: a run that stops in
-- PAUSED_MANUAL or PAUSED_NETWORK is unfinished, and the completion report
-- says so instead of writing NOT FOUND for pages that were never reached.
-- ===========================================================================
CREATE TABLE IF NOT EXISTS run_control (
    run_id          TEXT PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
    community_id    TEXT NOT NULL,
    state           TEXT NOT NULL,   -- RUNNING | PAUSING | PAUSED_MANUAL | PAUSED_NETWORK
                                     -- | RESUMING | COMPLETED | FAILED | CANCELLING | CANCELLED
    pause_reason    TEXT,            -- free text: why this run is not running
    requested_state TEXT,            -- what a researcher or the monitor has asked for
    requested_by    TEXT,            -- researcher | network_monitor | scheduler
    requested_utc   TEXT,
    connectivity    TEXT,            -- FULL | PARTIAL | OFFLINE | UNKNOWN
    connectivity_detail TEXT,
    stage_no        INTEGER,         -- the stage in progress at the last checkpoint
    stage_name      TEXT,
    source_id       TEXT,            -- the source in progress at the last checkpoint
    task_ref        TEXT,            -- the next incomplete task (a url_key, usually)
    task_detail     TEXT,
    tasks_total     INTEGER DEFAULT 0,
    tasks_done      INTEGER DEFAULT 0,
    checkpoint_utc  TEXT,
    checkpoint_seq  INTEGER DEFAULT 0,
    resumable       INTEGER DEFAULT 1,
    -- The yield account, so a resumed run continues one measurement of this
    -- community rather than starting a fresh one.
    yield_state     TEXT,            -- JSON: credited identity keys and per-scope totals
    yield_units     REAL,
    updated_utc     TEXT NOT NULL
);

-- Every pause, resume, cancel and connectivity transition, in order. This is
-- the audit trail the completion report draws on (brief §37): the reader can
-- see that a stage was cut short by an outage rather than by absent sources.
CREATE TABLE IF NOT EXISTS pause_events (
    event_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       TEXT NOT NULL,
    community_id TEXT NOT NULL,
    event        TEXT NOT NULL,      -- pause_requested | paused | resume_requested | resumed
                                     -- | cancel_requested | cancelled | connectivity_lost
                                     -- | connectivity_restored | checkpoint
    kind         TEXT,               -- manual | network | crash | unknown
    from_state   TEXT,
    to_state     TEXT,
    stage_no     INTEGER,
    source_id    TEXT,
    task_ref     TEXT,
    tasks_done   INTEGER,
    tasks_total  INTEGER,
    detail       TEXT,
    ts_utc       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pause_events_run ON pause_events(run_id, event_id);

-- ===========================================================================
-- Image candidates: the ledger of every image the crawl SAW.
--
-- Triage means most candidates are never downloaded. Their metadata is still
-- research material — the register notes that gallery captions and file names
-- often carry dates no text on the site provides — and keeping the ledger is
-- what makes the decision auditable: a reader can see what was passed over and
-- why, rather than having to trust that nothing was missed.
-- ===========================================================================
CREATE TABLE IF NOT EXISTS image_candidates (
    candidate_id    TEXT PRIMARY KEY,   -- IC001-IMGC0001
    community_id    TEXT NOT NULL REFERENCES communities(community_id) ON DELETE CASCADE,
    run_id          TEXT,
    source_id       TEXT,
    document_id     TEXT,
    page_id         TEXT,
    image_id        TEXT,               -- set once downloaded and kept
    url_key         TEXT,               -- sha1 of the normalised image URL
    original_url    TEXT,
    page_url        TEXT,
    archive_url     TEXT,
    origin          TEXT,               -- html | document | standalone
    filename        TEXT,
    alt_text        TEXT,
    title_text      TEXT,
    caption         TEXT,
    surrounding_text TEXT,
    page_heading    TEXT,
    document_title  TEXT,
    page_number     INTEGER,
    figure_number   TEXT,
    extraction_method TEXT,
    width           INTEGER,
    height          INTEGER,
    bytes           INTEGER,
    mime_type       TEXT,
    publication_date TEXT,
    image_date      TEXT,
    source_class    TEXT,
    independence_group TEXT,
    image_type      TEXT,
    research_topic  TEXT,
    relevance_class TEXT,               -- likely_relevant | possibly_relevant | uncertain | decorative
    priority        TEXT,               -- HIGH | MEDIUM | LOW | DUPLICATE
    priority_rank   REAL,
    relevance_score REAL,
    relevance_reason TEXT,
    possible_fields TEXT,
    documentary_text_support TEXT,
    decision        TEXT NOT NULL,      -- downloaded | skipped_low_priority | skipped_duplicate
                                        -- | skipped_budget | skipped_too_small | fetch_failed
                                        -- | skipped_paused
    decision_reason TEXT,
    sha256          TEXT,
    stage           INTEGER,
    seen_utc        TEXT NOT NULL,
    decided_utc     TEXT
);
CREATE INDEX IF NOT EXISTS idx_image_candidates_community
    ON image_candidates(community_id, priority, priority_rank DESC);
CREATE INDEX IF NOT EXISTS idx_image_candidates_urlkey
    ON image_candidates(community_id, url_key);

-- ===========================================================================
-- Runtime estimation, and the run history that sharpens it.
-- ===========================================================================
CREATE TABLE IF NOT EXISTS run_estimates (
    estimate_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       TEXT,
    community_id TEXT NOT NULL,
    phase        TEXT NOT NULL,      -- initial | after_discovery | final
    active_low_s  REAL,
    active_high_s REAL,
    wall_low_s    REAL,
    wall_high_s   REAL,
    unit_count   INTEGER,            -- the workload the estimate was built on
    basis        TEXT,               -- JSON: the factors and their weights
    reason       TEXT,               -- why this estimate differs from the previous one
    calibrated   INTEGER DEFAULT 0,  -- 1 = history from previous runs was used
    ts_utc       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_history (
    run_id          TEXT PRIMARY KEY,
    community_id    TEXT NOT NULL,
    mode            TEXT,
    estimated_active_s REAL,
    actual_active_s    REAL,
    wall_clock_s       REAL,
    offline_s          REAL DEFAULT 0,
    paused_manual_s    REAL DEFAULT 0,
    pages_processed INTEGER DEFAULT 0,
    documents       INTEGER DEFAULT 0,
    images_kept     INTEGER DEFAULT 0,
    image_candidates INTEGER DEFAULT 0,
    retries         INTEGER DEFAULT 0,
    errors          INTEGER DEFAULT 0,
    pauses_manual   INTEGER DEFAULT 0,
    pauses_network  INTEGER DEFAULT 0,
    final_state     TEXT,
    ts_utc          TEXT NOT NULL
);
