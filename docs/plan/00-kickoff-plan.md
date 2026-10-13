# Kickoff Plan

## 1. Understanding (under 300 words)

This system collects published foreign-exchange rates from up to 32 Ethiopian banks, normalizes them into a consistent data contract, preserves immutable history with a full correction audit trail, and presents trusted rates with explicit freshness and uncertainty labels.

The core separation is: Bank (institution) → Rate Source (one URL/endpoint) → Collection Run (one fetch attempt) → Rate Observation (one currency/category rate from that run) → Observation Version (an immutable accepted or corrected version). No separate publication table in the first implementation.

A shared pipeline handles validation, normalization, fingerprinting, identity/deduplication, change-candidate routing, versioning, and persistence. Per-bank adapters handle only source-specific parsing. Bank-specific logic never leaks into shared persistence code.

History is immutable. Identical normalized snapshots deduplicate silently. A changed value is never an automatic correction — it becomes a review candidate. Only a human-confirmed correction creates a new version linked by supersedes_id. Ambiguous identity is retained and flagged, never guessed.

Rates are exact decimals (NUMERIC). Missing sides are NULL, never zero. effective_date is the date the rate applies, not the fetch date. Current-rate selection never relies on fetched_at alone.

The trusted view excludes rejected observations, ambiguous identities, and unverified mappings. Provisional sources are visibly labeled. Stale rates show their effective date and age — never silently substituted.

Wave 1 covers CBE (structured API), Dashen (HTML page, three tables), and Addis International Bank (structured API, one capture already saved). The stack is PostgreSQL 16 + Python 3.12 + pytest, per defaults.md default 13.

---

## 2. Reconciliation Report

### 2.1 `other` category in the register vs. handoff's four categories
- **Conflict:** source-register.json lists `other` as a fifth canonical category. The handoff approves exactly four: cash, transactional, weighted_average, indicative_reference.
- **Evidence:** register field `canonical_categories` includes `"other"`. Handoff §3 says "Add a category only when the published rate has genuinely different business meaning."
- **Resolution (default 1):** `other` is not adopted. Unknown categories use the unknown-category flag and review queue. No change to LOCKED rules.

### 2.2 Third-party mirrors (Anbesa, Shabelle) — source authority
- **Conflict:** Register lists kehulum.com mirror URLs as sources with no official-source fallback policy defined.
- **Evidence:** Register mapping_status = `official_source_unresolved` for both. Handoff §11 says adapter output must include source identity.
- **Resolution (default 2):** Add a `source_authority` field (official / third_party). Mirror sources are disabled by default and never feed the trusted view. Recorded as ADR-002.

### 2.3 Non-collected observations — collection_run_id nullability
- **Conflict:** Handoff §5 says `collection_run_id` is "required for collected observations" (implying others exist). Handoff §8 says "every observation references a run."
- **Evidence:** No backfill or manual-entry use case is described anywhere.
- **Resolution (default 3):** Non-collected observations are out of scope. Every observation references a collection run. collection_run_id is NOT NULL. Revisit only if a backfill need appears.

### 2.4 Where review candidates live
- **Conflict:** Handoff §6 says keep a "pending_review candidate" but does not specify whether it lives in the observation table or a separate table. Gap review §2 notes the version_number > 0 constraint must allow NULL for candidates.
- **Resolution (default 4):** Changed-value candidates go in a separate `change_candidate` table. Ambiguous-identity records stay in the observation table with `identity_status = ambiguous` and no committed version. The unique `(logical_observation_key, version_number)` constraint applies only to committed versions.

### 2.5 Mapping reinterpretation mechanism
- **Conflict:** Handoff §7 says "preserve the original stored result and record the corrected interpretation" but gives no field. Using supersedes_id would mislabel a parser fix as a bank correction. A second current row violates the one-current rule.
- **Resolution (default 5):** Add a `reinterpretation_of_id` foreign key on the observation table. The trusted view uses the reinterpreted row. supersedes_id is reserved for confirmed bank corrections only.

### 2.6 is_current / current flag missing from field contract
- **Conflict:** Handoff §7 and §8 rely on current status and a partial unique index, but §5's field contract has no `is_current` field.
- **Evidence:** Gap review §1 explicitly flags this.
- **Resolution:** Add `is_current BOOLEAN NOT NULL DEFAULT FALSE` to the observation table. A partial unique index enforces at most one current version per `logical_observation_key` where `is_current = TRUE`.

### 2.7 Fingerprint version missing
- **Conflict:** Handoff §6 defines `snapshot_fingerprint` but no `fingerprint_version`. A mapping change would make every stored observation look changed.
- **Evidence:** Gap review §4.
- **Resolution (default 8 extended):** Add `fingerprint_version SMALLINT NOT NULL DEFAULT 1`. Comparisons happen only under the same fingerprint version.

### 2.8 Quote currency and unit multiplier missing
- **Conflict:** Handoff §5 field contract has no quote_currency or unit_multiplier. The Addis capture implies ETB as quote currency but does not state it.
- **Evidence:** Gap review §6; defaults.md default 9.
- **Resolution:** Add `quote_currency_code VARCHAR(3)` and `unit_multiplier NUMERIC(10,0) NOT NULL DEFAULT 1`, both TO VERIFY per source.

### 2.9 Run overlap — no constraint defined
- **Conflict:** Handoff §9 says "one running run per source" but defines no enforcement mechanism.
- **Evidence:** Gap review §7.
- **Resolution:** Add a partial unique index on `collection_run (source_id) WHERE status = 'running'`. Stuck-run recovery rule: a run in `running` status for more than 2 hours is eligible for manual recovery (set to `failed`), recorded in the runbook.

### 2.10 CBE `_limit=1` parameter
- **Conflict:** Register lists `_limit: 1` as a query parameter. Default 16 says do not set it until its effect is known — it may silently truncate results.
- **Resolution:** Investigate during Wave 1 onboarding. Do not send `_limit` until behavior is confirmed.

### 2.11 National Bank of Ethiopia reference rate
- **Conflict:** The handoff keeps the `indicative_reference` category but names no source for it. The register has no NBE entry.
- **Resolution (default 17):** Investigate whether an official NBE publication exists. Add as `indicative_reference` source only if it is a public official feed. Record finding in STATUS.md.

### 2.12 Addis register entry predates the 2026-10-10 capture
- **Conflict:** Register shows Addis as `source_identified_schema_unverified`. The capture shows actual field names.
- **Resolution (default 18):** Update Addis entry to `partially_verified`, citing the capture. Done in the normalized register (step 7).

### 2.13 schema_fingerprint optionality
- **Conflict:** Register marks schema_fingerprint optional, but the schema_change raw-capture trigger cannot fire without it.
- **Evidence:** Gap review smaller items.
- **Resolution:** schema_fingerprint is required (NOT NULL) for all API and HTML sources. It may be NULL only for sources where schema detection is not yet implemented (recorded as TO VERIFY).

---

## 3. Wave 1 Source Analysis

### 3.1 CBE
- **URL:** https://combanketh.et/cbeapi/daily-exchange-rates/
- **What I can confirm from the register and handoff:** Field names (currency.CurrencyCode, currency.CurrencyName, cashBuying, cashSelling, transactionalBuying, transactionalSelling) and the ?Date= parameter are inventoried.
- **What I could not confirm:** I have not fetched the live endpoint in this session. No fixture exists in docs/evidence/. No comparison with the official CBE display has been made.
- **TO VERIFY:** Exact response envelope/nesting; effective/publication-date semantics; whether ?Date= filters or just hints; multiple publications per date; stable record ID; currency-code validity; buying/selling meaning and values vs. official CBE display; empty/error behavior; effect of _limit parameter.
- **Timestamp:** No live fetch performed this session.

### 3.2 Dashen
- **URL:** https://dashenbanksc.com/daily-exchange-rates/
- **What I can confirm:** Three table sections are inventoried (Transactions Buying/Selling → transactional; Cash Buying/Selling → cash; Weighted Average Rate → weighted_average).
- **What I could not confirm:** No fixture exists. No live fetch performed. Selectors, column order, currency labels, per-table dates, and partial-failure behavior are all unverified.
- **TO VERIFY:** All items in the register's requires_verification list. Per-table effective dates (gap review test F).
- **Timestamp:** No live fetch performed this session.

### 3.3 Addis International Bank
- **URL:** https://api.addisbanksc.com/api/exchange-rates
- **Fixture:** docs/evidence/addis/2026-10-10-exchange-rates.json (8 records, captured 2026-10-10, exact time and HTTP status not recorded).
- **What the fixture shows:**
  - Top-level JSON array, no envelope. Fields: id, currency, buying, selling, transactionBuying, transactionSelling, weightedBuying, weightedSelling, createdAt, updatedAt.
  - id is a row number (1–8), not a publication ID.
  - createdAt is identical across rows; updatedAt varies — rows appear edited in place, no history kept by the API.
  - No effective_date or publication_date field. updatedAt is a last-edit time; its meaning as effective date is unverified.
  - "0.0000" appears in buying/selling for SAR, CHF, AED, KWD, and in weightedSelling for EUR and GBP. Zero is invalid under the contract. Whether it means "not offered" is unverified.
  - weightedBuying/weightedSelling use both null (ETB, KWD) and "0.0000" — difference unverified.
  - The category of plain buying/selling is unresolved: for USD, EUR, GBP they equal transactionBuying/transactionSelling. Do not assume cash.
  - ETB row (id=1, all 1.0000) is the quote currency itself — proposal: do not ingest as a rate observation.
  - Review signals: GBP weightedBuying 224.5035 is exactly 10.0000 above buying 214.5035; USD weightedSelling 170.4175 >> selling 164.9103.
- **What I could not confirm:** No comparison with Addis's official display has been made. Exact capture time and HTTP status were not recorded. Repeat fetch, error/empty behavior, and HTTP headers are not yet done.
- **TO VERIFY:** Category of plain buying/selling; zero-means-not-offered rule; updatedAt as effective date; stable record ID; official-display comparison for at least 3 currencies and both sides; repeat fetch behavior; HTTP status and headers.
- **Status update:** Register entry updated to `partially_verified` per default 18.

---

## 4. Repository and Stack Assessment

The repository contains only documentation files. No source code, migrations, or tests exist yet.

**Stack adopted (default 13):**
- Database: PostgreSQL 16.15 (confirmed available: `psql --version`)
- Language: Python 3.12.3 (confirmed: `python3 --version`)
- Test runner: pytest 9.1.1 (installed this session: `pip3 install --break-system-packages pytest psycopg2-binary`)
- DB driver: psycopg2-binary 2.9.13 (installed this session)
- Databases created: `exchange_rates` and `exchange_rates_test`

No deviation from default 13. ADR-013 records this.

---

## 5. Schema Proposal

All items marked (PROPOSED) depend on Wave 1 evidence. Items marked (LOCKED) follow the handoff directly.

### 5.1 Tables

**bank**
```
id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
code            VARCHAR(20) NOT NULL UNIQUE          -- e.g. 'CBE'
name            TEXT NOT NULL
institution_type TEXT
source_authority VARCHAR(20) NOT NULL DEFAULT 'official'  -- 'official' | 'third_party'
is_active       BOOLEAN NOT NULL DEFAULT TRUE
created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
```

**rate_source**
```
id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
bank_id         BIGINT NOT NULL REFERENCES bank(id)
source_url      TEXT NOT NULL
collection_method VARCHAR(20) NOT NULL  -- 'api' | 'html' | 'browser' | 'ajax_endpoint'
adapter_key     VARCHAR(50) NOT NULL
verification_status VARCHAR(20) NOT NULL DEFAULT 'unverified'
  -- CHECK IN ('unverified','provisional','verified','blocked')
is_enabled      BOOLEAN NOT NULL DEFAULT FALSE
schema_fingerprint TEXT                              -- required for api/html; NULL only while TO VERIFY
last_success_at TIMESTAMPTZ
created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
```

**rate_category**
```
id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
code            VARCHAR(30) NOT NULL UNIQUE  -- 'cash'|'transactional'|'weighted_average'|'indicative_reference'
name            TEXT NOT NULL
description     TEXT
is_active       BOOLEAN NOT NULL DEFAULT TRUE
approved_at     TIMESTAMPTZ NOT NULL
```

**collection_run**
```
id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
source_id       BIGINT NOT NULL REFERENCES rate_source(id)
started_at      TIMESTAMPTZ NOT NULL
finished_at     TIMESTAMPTZ
status          VARCHAR(20) NOT NULL DEFAULT 'running'
  -- CHECK IN ('running','success','partial_success','failed')
http_status     SMALLINT
records_found   INT NOT NULL DEFAULT 0
records_accepted INT NOT NULL DEFAULT 0
records_flagged INT NOT NULL DEFAULT 0
error_code      VARCHAR(50)
error_summary   TEXT
duration_ms     INT
-- one running run per source:
UNIQUE (source_id) WHERE status = 'running'   -- partial unique index
```

**rate_observation**
```
id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
source_id               BIGINT NOT NULL REFERENCES rate_source(id)
collection_run_id       BIGINT NOT NULL REFERENCES collection_run(id)
category_id             BIGINT NOT NULL REFERENCES rate_category(id)
-- currency
currency_code           VARCHAR(3)       -- canonical; NULL until verified
source_currency_code    VARCHAR(20) NOT NULL
currency_name           TEXT
-- rates (PROPOSED precision; confirm after Wave 1)
buying_rate             NUMERIC(24,10)   -- NULL if not offered
selling_rate            NUMERIC(24,10)   -- NULL if not offered
-- at least one side non-NULL enforced by CHECK
-- quote / unit (TO VERIFY per source)
quote_currency_code     VARCHAR(3)       -- TO VERIFY; likely 'ETB'
unit_multiplier         NUMERIC(10,0) NOT NULL DEFAULT 1  -- TO VERIFY
-- source text preservation
source_rate_text        TEXT             -- original text excerpt, size-limited
source_excerpt          JSONB            -- source record's own JSON, size-limited
-- effective date
effective_date          DATE             -- NULL when genuinely unknown
effective_date_basis    VARCHAR(30) NOT NULL
  -- CHECK IN ('source_published','source_inferred','collection_date_fallback','unknown')
-- timestamps
fetched_at              TIMESTAMPTZ NOT NULL
created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
-- identity
source_record_key       TEXT             -- stable ID from source, if any
source_publication_key  TEXT
logical_observation_key TEXT             -- NULL for ambiguous
-- fingerprint
snapshot_fingerprint    CHAR(64)         -- SHA-256, excludes fetched_at
fingerprint_version     SMALLINT NOT NULL DEFAULT 1
-- versioning
version_number          SMALLINT         -- NULL for candidates; > 0 for committed
supersedes_id           BIGINT REFERENCES rate_observation(id)
reinterpretation_of_id  BIGINT REFERENCES rate_observation(id)
is_current              BOOLEAN NOT NULL DEFAULT FALSE
-- status dimensions (separate, per LOCKED rule)
validation_status       VARCHAR(20) NOT NULL DEFAULT 'warning'
  -- CHECK IN ('validated','warning','rejected')
validation_messages     JSONB
identity_status         VARCHAR(20) NOT NULL DEFAULT 'ambiguous'
  -- CHECK IN ('confirmed','derived','ambiguous')
change_review_status    VARCHAR(20) NOT NULL DEFAULT 'not_required'
  -- CHECK IN ('not_required','pending_review','confirmed_correction','new_publication','mapping_issue','dismissed')
-- mapping provenance
category_mapping_version SMALLINT NOT NULL DEFAULT 1
currency_mapping_version SMALLINT NOT NULL DEFAULT 1
-- constraints
CHECK (buying_rate IS NOT NULL OR selling_rate IS NOT NULL)
CHECK (buying_rate IS NULL OR buying_rate > 0)
CHECK (selling_rate IS NULL OR selling_rate > 0)
CHECK (version_number IS NULL OR version_number > 0)
CHECK (supersedes_id IS NULL OR supersedes_id <> id)
CHECK (reinterpretation_of_id IS NULL OR reinterpretation_of_id <> id)
-- at most one current version per identified logical observation:
UNIQUE (logical_observation_key) WHERE is_current = TRUE AND logical_observation_key IS NOT NULL
-- unique committed version per logical key:
UNIQUE (logical_observation_key, version_number) WHERE version_number IS NOT NULL AND logical_observation_key IS NOT NULL
```

**change_candidate** (default 4)
```
id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
observation_id      BIGINT NOT NULL REFERENCES rate_observation(id)  -- the new/changed observation
prior_version_id    BIGINT NOT NULL REFERENCES rate_observation(id)  -- the current committed version
source_id           BIGINT NOT NULL REFERENCES rate_source(id)
detected_at         TIMESTAMPTZ NOT NULL DEFAULT now()
status              VARCHAR(20) NOT NULL DEFAULT 'open'
  -- CHECK IN ('open','confirmed_correction','new_publication','mapping_issue','dismissed')
decision_reason     TEXT
decided_at          TIMESTAMPTZ
decided_by          TEXT
```

**raw_capture**
```
id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
collection_run_id   BIGINT NOT NULL REFERENCES collection_run(id)
captured_at         TIMESTAMPTZ NOT NULL DEFAULT now()
capture_reason      VARCHAR(30) NOT NULL
  -- CHECK IN ('http_failure','parse_failure','schema_change','suspicious_data')
content_hash        CHAR(64) NOT NULL   -- SHA-256
storage_reference   TEXT                -- path or object key
retention_until     DATE NOT NULL       -- content kept 90 days; hash/metadata permanent
```

### 5.2 Indexes
```sql
CREATE INDEX ON rate_observation (source_id, effective_date);
CREATE INDEX ON rate_observation (collection_run_id);
CREATE INDEX ON rate_observation (logical_observation_key) WHERE logical_observation_key IS NOT NULL;
CREATE INDEX ON rate_observation (is_current) WHERE is_current = TRUE;
CREATE INDEX ON collection_run (source_id, started_at DESC);
```

### 5.3 Items depending on evidence not yet available
- NUMERIC(24,10) precision: PROPOSED. Confirm after Wave 1 captures show no rounding. Keep original rate text.
- quote_currency_code and unit_multiplier: TO VERIFY per source.
- schema_fingerprint on rate_source: required for api/html; NULL only while TO VERIFY.
- Freshness thresholds: not hardcoded; propose after 14 days of data (default 11).

---

## 6. Milestone Plan

| Milestone | Description | Risk |
|-----------|-------------|------|
| M0 | Kickoff plan, normalized register, ADR index | Low — documentation only |
| M1 | Wave 1 evidence: live fetches for CBE, Dashen, Addis; mapping docs | Medium — CBE and Dashen not yet fetched; Dashen may need browser rendering |
| M2 | Physical schema, constraint tests, migrations against real DB | Low — schema is well-specified; risk is precision/scale surprises from live data |
| M3 | Core pipeline: validation, normalization, fingerprint, identity, dedup, versioning, correction transaction | High — most complex logic; acceptance tests 1–8, 12–18 and gap-review tests A–E, J |
| M4 | Addis adapter + fixtures + end-to-end run | Medium — zero-value semantics and category of plain buying/selling unresolved |
| M5 | CBE adapter + fixtures + end-to-end run | Medium — _limit behavior and date semantics unverified |
| M6 | Dashen adapter + fixtures + end-to-end run | High — HTML scraping; three independent tables; per-table dates; partial-failure |
| M7 | Trusted view, collection runs, review workflow | Medium — freshness policy depends on measured data |
| M8 | Waves 2–5, presentation, operations, runbook | High — 29 more banks; some have no official source |

Execution follows docs/plan/execution-order.md top to bottom.

---

## 7. Decisions

### Defaults adopted unchanged
All 18 defaults from docs/decisions/defaults.md are adopted as stated. Key ones:
- Default 1: `other` category not adopted.
- Default 2: source_authority field; mirrors disabled.
- Default 3: non-collected observations out of scope; collection_run_id NOT NULL.
- Default 4: candidates in separate change_candidate table.
- Default 5: reinterpretation_of_id, not supersedes_id, for parser fixes.
- Default 7: BIGINT identity IDs.
- Default 8: NUMERIC(24,10), keep original rate text.
- Default 9: quote_currency_code and unit_multiplier fields, TO VERIFY.
- Default 10: raw capture content 90 days; hashes permanent.
- Default 11: no hardcoded freshness thresholds.
- Default 13: PostgreSQL 16 + Python 3.12 + pytest (confirmed available).
- Default 16: do not send CBE _limit until behavior confirmed.
- Default 18: Addis register updated to partially_verified.

### Defaults extended (not changed, clarified)
- Default 8 extended: add fingerprint_version SMALLINT (gap review §4).
- Default 13: databases `exchange_rates` and `exchange_rates_test` created this session.

### Gap-review items resolved
- is_current field added to observation table (gap review §1).
- version_number NULL for candidates; unique constraint scoped to committed versions (gap review §2).
- reinterpretation_of_id mechanism (gap review §3).
- fingerprint_version field (gap review §4).
- Fallback dates never participate in identity (gap review §5) — enforced by effective_date_basis check and identity logic.
- quote_currency_code and unit_multiplier added (gap review §6).
- Run overlap: partial unique index on collection_run (gap review §7).
- Non-collected observations out of scope (gap review §8, default 3).

### Decisions that need the owner
- **Zero in Addis data:** "0.0000" in buying/selling fields — does it mean "not offered" (→ NULL) or is it a data error? Cannot decide without comparing with the official Addis display. Recommendation: treat as NULL (not offered) provisionally, flag every such record with validation_status = warning, and confirm after official-display comparison.
- **Addis plain buying/selling category:** For USD/EUR/GBP these equal transactionBuying/transactionSelling. Is the plain pair a duplicate of transactional, or a distinct cash rate? Cannot decide without official-display comparison. Recommendation: do not ingest plain buying/selling as a separate observation until category is confirmed; ingest only transactionBuying/transactionSelling and weightedBuying/weightedSelling for now.
- **CBE _limit=1:** May silently truncate to one record per request. Recommendation: fetch without _limit first; if the response contains multiple records, _limit=1 is a truncation risk and should never be sent.
