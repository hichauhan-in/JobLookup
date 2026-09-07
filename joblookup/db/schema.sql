-- JobLookup schema. Applied idempotently on every startup.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- CVs & profile
CREATE TABLE IF NOT EXISTS cv (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    label         TEXT    NOT NULL,
    filename      TEXT    NOT NULL,
    stored_path   TEXT    NOT NULL,
    mime_type     TEXT,
    raw_text      TEXT    NOT NULL DEFAULT '',
    extracted     TEXT,                                    -- JSON: structured extraction
    extract_state TEXT    NOT NULL DEFAULT 'pending',      -- pending|running|ok|failed
    extract_error TEXT,
    is_primary    INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Single-row table. The merged career profile plus the wizard answers.
CREATE TABLE IF NOT EXISTS profile (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    data        TEXT    NOT NULL DEFAULT '{}',   -- JSON: merged skills, roles, preferences
    version     INTEGER NOT NULL DEFAULT 1,      -- bumped on every edit; invalidates scores
    embedding   BLOB,                            -- float32 vector of the profile summary
    embed_model TEXT    NOT NULL DEFAULT '',     -- which model produced it; blank = lexical
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------- sources
CREATE TABLE IF NOT EXISTS source (
    key           TEXT PRIMARY KEY,
    name          TEXT    NOT NULL,
    tier          TEXT    NOT NULL,              -- 'a' public API | 'ats' board | 'b' browser
    enabled       INTEGER NOT NULL DEFAULT 0,
    requires_key  INTEGER NOT NULL DEFAULT 0,
    risk_ack      INTEGER NOT NULL DEFAULT 0,    -- tier B only: user accepted the ToS risk
    config        TEXT    NOT NULL DEFAULT '{}', -- JSON: per-source options, e.g. ATS slugs
    last_run_at   TEXT,
    last_status   TEXT,
    last_error    TEXT,
    last_count    INTEGER NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------- jobs
CREATE TABLE IF NOT EXISTS job (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint     TEXT    NOT NULL UNIQUE,     -- canonical company+title+location hash
    title           TEXT    NOT NULL,
    title_norm      TEXT    NOT NULL DEFAULT '',
    company         TEXT    NOT NULL DEFAULT '',
    company_norm    TEXT    NOT NULL DEFAULT '', -- dedupe key, legal suffixes stripped
    location        TEXT    NOT NULL DEFAULT '',
    location_norm   TEXT    NOT NULL DEFAULT '',
    country         TEXT,
    work_mode       TEXT,                        -- remote | hybrid | onsite | unknown
    employment      TEXT,                        -- full-time | contract | internship | unknown
    seniority       TEXT,                        -- intern | junior | mid | senior | lead | principal
    description     TEXT    NOT NULL DEFAULT '',
    url             TEXT    NOT NULL DEFAULT '',
    apply_url       TEXT,
    posted_at       TEXT,                        -- ISO8601; null when the source omits it
    salary_min      REAL,
    salary_max      REAL,
    salary_currency TEXT,
    embedding       BLOB,
    embed_model     TEXT    NOT NULL DEFAULT '',
    first_seen_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    last_seen_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    archived        INTEGER NOT NULL DEFAULT 0,
    hidden          INTEGER NOT NULL DEFAULT 0   -- user dismissed it
);

CREATE INDEX IF NOT EXISTS idx_job_posted   ON job (posted_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_company  ON job (company_norm);
CREATE INDEX IF NOT EXISTS idx_job_archived ON job (archived, hidden);

-- Full-text index over the searchable parts of a posting. This is what makes
-- lexical recall fast enough to be the default when no embeddings exist.
CREATE VIRTUAL TABLE IF NOT EXISTS job_fts USING fts5 (
    title, company, location, description,
    content = 'job', content_rowid = 'id', tokenize = 'porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS job_fts_insert AFTER INSERT ON job BEGIN
    INSERT INTO job_fts (rowid, title, company, location, description)
    VALUES (new.id, new.title, new.company, new.location, new.description);
END;

CREATE TRIGGER IF NOT EXISTS job_fts_delete AFTER DELETE ON job BEGIN
    INSERT INTO job_fts (job_fts, rowid, title, company, location, description)
    VALUES ('delete', old.id, old.title, old.company, old.location, old.description);
END;

CREATE TRIGGER IF NOT EXISTS job_fts_update AFTER UPDATE ON job BEGIN
    INSERT INTO job_fts (job_fts, rowid, title, company, location, description)
    VALUES ('delete', old.id, old.title, old.company, old.location, old.description);
    INSERT INTO job_fts (rowid, title, company, location, description)
    VALUES (new.id, new.title, new.company, new.location, new.description);
END;

-- One row per source the job was seen on. This is what makes dedupe visible:
-- a single job card can carry five source links.
CREATE TABLE IF NOT EXISTS job_source (
    job_id        INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    source_key    TEXT    NOT NULL,
    source_job_id TEXT,
    url           TEXT    NOT NULL DEFAULT '',
    seen_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    raw           TEXT,                          -- JSON: the untouched source payload
    PRIMARY KEY (job_id, source_key)
);

-- ---------------------------------------------------------------- scoring
CREATE TABLE IF NOT EXISTS job_score (
    job_id            INTEGER PRIMARY KEY REFERENCES job(id) ON DELETE CASCADE,
    profile_version   INTEGER NOT NULL,
    band              TEXT    NOT NULL,          -- strong | good | stretch | rejected
    composite         REAL    NOT NULL DEFAULT 0,
    recall_score      REAL    NOT NULL DEFAULT 0,
    direct_fit        REAL    NOT NULL DEFAULT 0,
    transferable_fit  REAL    NOT NULL DEFAULT 0,
    growth_fit        REAL    NOT NULL DEFAULT 0,
    rationale         TEXT    NOT NULL DEFAULT '',
    matched_skills    TEXT    NOT NULL DEFAULT '[]',
    learnable_gaps    TEXT    NOT NULL DEFAULT '[]',
    hard_gaps         TEXT    NOT NULL DEFAULT '[]',
    blocker           TEXT,
    model             TEXT    NOT NULL DEFAULT '',
    scored_at         TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_score_band ON job_score (band, composite DESC);

-- ---------------------------------------------------------------- tracking
CREATE TABLE IF NOT EXISTS application (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      INTEGER NOT NULL UNIQUE REFERENCES job(id) ON DELETE CASCADE,
    status      TEXT    NOT NULL DEFAULT 'saved',  -- saved|applied|interviewing|offer|rejected
    notes       TEXT    NOT NULL DEFAULT '',
    cv_id       INTEGER REFERENCES cv(id) ON DELETE SET NULL,
    export_path TEXT,
    applied_at  TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS crawl_run (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    status      TEXT    NOT NULL DEFAULT 'running',  -- running|ok|partial|failed|cancelled
    sources     TEXT    NOT NULL DEFAULT '[]',
    stats       TEXT    NOT NULL DEFAULT '{}',
    error       TEXT,
    -- What the model cost for this search. Estimated, not billed: see llm/usage.py.
    tokens      TEXT    NOT NULL DEFAULT '{}'
);

-- Which postings each search actually produced, so history can show its results
-- rather than only its statistics. Deleting a run drops these rows, never the
-- postings themselves, which usually belong to several runs.
CREATE TABLE IF NOT EXISTS crawl_run_job (
    run_id  INTEGER NOT NULL REFERENCES crawl_run(id) ON DELETE CASCADE,
    job_id  INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    is_new  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_crawl_run_job_run ON crawl_run_job (run_id);

-- Cached tailoring output so re-opening a job does not re-run the model.
CREATE TABLE IF NOT EXISTS tailored_cv (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    cv_id       INTEGER NOT NULL REFERENCES cv(id) ON DELETE CASCADE,
    content     TEXT    NOT NULL DEFAULT '{}',   -- JSON: tailored sections
    prep_sheet  TEXT    NOT NULL DEFAULT '{}',   -- JSON: interview prep, kept out of the CV
    docx_path   TEXT,
    markdown    TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (job_id, cv_id)
);

-- ---------------------------------------------------------------- misc
CREATE TABLE IF NOT EXISTS setting (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO profile (id, data) VALUES (1, '{}');

CREATE TABLE IF NOT EXISTS search_track (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    preferences TEXT NOT NULL DEFAULT '{}',
    sources TEXT NOT NULL DEFAULT '[]',
    cv_id INTEGER REFERENCES cv(id) ON DELETE SET NULL,
    schedule_enabled INTEGER NOT NULL DEFAULT 0,
    schedule_hour INTEGER NOT NULL DEFAULT 9,
    schedule_minute INTEGER NOT NULL DEFAULT 0,
    schedule_weekdays TEXT NOT NULL DEFAULT '[0,1,2,3,4]',
    last_slot TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS inbox_state (
    job_id INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    track_id INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT NOT NULL,
    seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY(job_id, track_id)
);

CREATE TABLE IF NOT EXISTS job_feedback (
    job_id INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    track_id INTEGER NOT NULL DEFAULT 0,
    label TEXT NOT NULL CHECK(label IN ('relevant', 'adjacent', 'irrelevant')),
    reason TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    job_snapshot TEXT NOT NULL,
    profile_snapshot TEXT NOT NULL,
    posting_age REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY(job_id, track_id)
);

CREATE TABLE IF NOT EXISTS application_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES application(job_id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS application_task (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES application(job_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'followup',
    due_at TEXT NOT NULL,
    done_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_application_task_due ON application_task(done_at, due_at);

CREATE TABLE IF NOT EXISTS resume_version (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    cv_id INTEGER REFERENCES cv(id) ON DELETE SET NULL,
    markdown TEXT NOT NULL,
    base_text TEXT NOT NULL DEFAULT '',
    prep_sheet TEXT NOT NULL DEFAULT '{}',
    content TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
