-- Migration 001: initial schema
-- Implements the locked design + gap review + ADR-006/007/008/009

-- ── bank ────────────────────────────────────────────────────────────────────
CREATE TABLE bank (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code             VARCHAR(20)  NOT NULL UNIQUE,
    name             TEXT         NOT NULL,
    institution_type TEXT,
    source_authority VARCHAR(20)  NOT NULL DEFAULT 'official'
                     CHECK (source_authority IN ('official','third_party')),
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ── rate_source ──────────────────────────────────────────────────────────────
CREATE TABLE rate_source (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bank_id              BIGINT       NOT NULL REFERENCES bank(id),
    source_url           TEXT         NOT NULL,
    collection_method    VARCHAR(20)  NOT NULL
                         CHECK (collection_method IN ('api','html','ajax_endpoint','browser')),
    adapter_key          VARCHAR(50)  NOT NULL,
    adapter_family       VARCHAR(10),          -- A, B1, B2, C1, D, E, F, G, H1, H2
    verification_status  VARCHAR(20)  NOT NULL DEFAULT 'unverified'
                         CHECK (verification_status IN
                                ('unverified','provisional','verified','blocked')),
    is_enabled           BOOLEAN      NOT NULL DEFAULT FALSE,
    ssl_verify           BOOLEAN      NOT NULL DEFAULT TRUE,  -- ADR-009
    ssl_review_by        DATE,                                -- ADR-009 temporary fallback expiry
    schema_fingerprint   TEXT,
    default_category     VARCHAR(30)           -- ADR-008: owner-set override for Type F sources
                         CHECK (default_category IS NULL OR default_category IN
                                ('cash','transactional','weighted_average','indicative_reference')),
    default_category_reason TEXT,
    default_category_set_date DATE,
    last_success_at      TIMESTAMPTZ,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ── rate_category ────────────────────────────────────────────────────────────
CREATE TABLE rate_category (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code        VARCHAR(30)  NOT NULL UNIQUE
                CHECK (code IN ('cash','transactional','weighted_average','indicative_reference')),
    name        TEXT         NOT NULL,
    description TEXT,
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    approved_at TIMESTAMPTZ  NOT NULL
);

INSERT INTO rate_category (code, name, approved_at) VALUES
    ('cash',                'Cash',                now()),
    ('transactional',       'Transactional',       now()),
    ('weighted_average',    'Weighted Average',    now()),
    ('indicative_reference','Indicative Reference',now());

-- ── collection_run ───────────────────────────────────────────────────────────
CREATE TABLE collection_run (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id       BIGINT       NOT NULL REFERENCES rate_source(id),
    started_at      TIMESTAMPTZ  NOT NULL,
    finished_at     TIMESTAMPTZ,
    status          VARCHAR(20)  NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running','success','partial_success','failed')),
    http_status     SMALLINT,
    records_found   INT          NOT NULL DEFAULT 0 CHECK (records_found   >= 0),
    records_accepted INT         NOT NULL DEFAULT 0 CHECK (records_accepted >= 0),
    records_flagged INT          NOT NULL DEFAULT 0 CHECK (records_flagged  >= 0),
    error_code      VARCHAR(50),
    error_summary   TEXT,
    duration_ms     INT
);

-- One running run per source (gap review §7)
CREATE UNIQUE INDEX uq_one_running_run_per_source
    ON collection_run (source_id)
    WHERE status = 'running';

-- ── rate_observation ─────────────────────────────────────────────────────────
CREATE TABLE rate_observation (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id               BIGINT       NOT NULL REFERENCES rate_source(id),
    collection_run_id       BIGINT       NOT NULL REFERENCES collection_run(id),
    category_id             BIGINT       REFERENCES rate_category(id),
                            -- NULL when category=UNKNOWN (ADR-008 / Type F)
    -- currency
    currency_code           VARCHAR(3),          -- canonical; NULL until verified
    source_currency_code    VARCHAR(20)  NOT NULL,
    currency_name           TEXT,
    -- rates
    buying_rate             NUMERIC(24,10) CHECK (buying_rate  IS NULL OR buying_rate  > 0),
    selling_rate            NUMERIC(24,10) CHECK (selling_rate IS NULL OR selling_rate > 0),
    CHECK (buying_rate IS NOT NULL OR selling_rate IS NOT NULL),
    -- source text preservation (ADR-006 §4.1)
    source_rate_text        TEXT,
    source_excerpt          JSONB,
    -- quote / unit (ADR-006 §4.4, default 9)
    quote_currency_code     VARCHAR(3),
    unit_multiplier         NUMERIC(10,0) NOT NULL DEFAULT 1,
    -- effective date
    effective_date          DATE,
    effective_date_basis    VARCHAR(30)  NOT NULL
                            CHECK (effective_date_basis IN
                                   ('source_published','source_inferred',
                                    'collection_date_fallback','unknown')),
    -- timestamps
    fetched_at              TIMESTAMPTZ  NOT NULL,
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    -- identity
    source_record_key       TEXT,
    source_publication_key  TEXT,
    logical_observation_key TEXT,
    -- fingerprint (gap review §4)
    snapshot_fingerprint    CHAR(64),
    fingerprint_version     SMALLINT     NOT NULL DEFAULT 1,
    -- versioning
    version_number          SMALLINT     CHECK (version_number IS NULL OR version_number > 0),
    supersedes_id           BIGINT       REFERENCES rate_observation(id)
                            CHECK (supersedes_id IS NULL OR supersedes_id <> id),
    reinterpretation_of_id  BIGINT       REFERENCES rate_observation(id)
                            CHECK (reinterpretation_of_id IS NULL OR reinterpretation_of_id <> id),
    is_current              BOOLEAN      NOT NULL DEFAULT FALSE,
    -- status dimensions (separate per LOCKED rule)
    validation_status       VARCHAR(20)  NOT NULL DEFAULT 'warning'
                            CHECK (validation_status IN ('validated','warning','rejected')),
    validation_messages     JSONB,
    identity_status         VARCHAR(20)  NOT NULL DEFAULT 'ambiguous'
                            CHECK (identity_status IN ('confirmed','derived','ambiguous')),
    change_review_status    VARCHAR(20)  NOT NULL DEFAULT 'not_required'
                            CHECK (change_review_status IN
                                   ('not_required','pending_review','confirmed_correction',
                                    'new_publication','mapping_issue','dismissed')),
    -- mapping provenance (gap review §4)
    category_mapping_version  SMALLINT   NOT NULL DEFAULT 1,
    currency_mapping_version  SMALLINT   NOT NULL DEFAULT 1
);

-- At most one current version per identified logical observation (gap review §1)
CREATE UNIQUE INDEX uq_one_current_per_logical_key
    ON rate_observation (logical_observation_key)
    WHERE is_current = TRUE AND logical_observation_key IS NOT NULL;

-- Unique committed version per logical key (gap review §2)
CREATE UNIQUE INDEX uq_version_per_logical_key
    ON rate_observation (logical_observation_key, version_number)
    WHERE version_number IS NOT NULL AND logical_observation_key IS NOT NULL;

-- Supporting indexes
CREATE INDEX idx_obs_source_date    ON rate_observation (source_id, effective_date);
CREATE INDEX idx_obs_run            ON rate_observation (collection_run_id);
CREATE INDEX idx_obs_logical_key    ON rate_observation (logical_observation_key)
    WHERE logical_observation_key IS NOT NULL;
CREATE INDEX idx_obs_is_current     ON rate_observation (is_current) WHERE is_current = TRUE;
CREATE INDEX idx_run_source_started ON collection_run (source_id, started_at DESC);

-- One adapter per bank (prevents duplicate seeding)
CREATE UNIQUE INDEX uq_source_bank_adapter ON rate_source (bank_id, adapter_key);

-- ── change_candidate ─────────────────────────────────────────────────────────
-- (default 4 / ADR-007)
CREATE TABLE change_candidate (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    observation_id   BIGINT       NOT NULL REFERENCES rate_observation(id),
    prior_version_id BIGINT       NOT NULL REFERENCES rate_observation(id),
    source_id        BIGINT       NOT NULL REFERENCES rate_source(id),
    detected_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    status           VARCHAR(20)  NOT NULL DEFAULT 'open'
                     CHECK (status IN
                            ('open','confirmed_correction','new_publication',
                             'mapping_issue','dismissed')),
    decision_reason  TEXT,
    decided_at       TIMESTAMPTZ,
    decided_by       TEXT
);

-- ── raw_capture ──────────────────────────────────────────────────────────────
CREATE TABLE raw_capture (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    collection_run_id BIGINT       NOT NULL REFERENCES collection_run(id),
    captured_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    capture_reason    VARCHAR(30)  NOT NULL
                      CHECK (capture_reason IN
                             ('http_failure','parse_failure','schema_change','suspicious_data')),
    content_hash      CHAR(64)     NOT NULL,
    storage_reference TEXT,
    retention_until   DATE         NOT NULL  -- content 90 days; hash/metadata permanent
);
