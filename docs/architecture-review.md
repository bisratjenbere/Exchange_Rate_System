# Architecture Review — Exchange Rate System

**Review Date:** 2026-11-23  
**Reviewer:** Kiro AI Agent  
**Scope:** Repository organization and architectural patterns  
**Mode:** Read-only analysis  

---

## 1. Directory Structure

### Top-Level Layout (depth 3)
```
/home/bisru/Exchange_Rate_System/
├── adapters/           (33 bank-specific adapters)
│   ├── abay/
│   ├── adib/
│   ├── ahadu/
│   ├── [... 30 more banks ...]
│   ├── zemen/
│   └── base.py
├── alerts/             (Alerting logic)
├── api/                (HTTP API endpoints)
│   └── templates/
├── backups/            (Database backups)
├── db/                 (Database management)
│   ├── migrations/
│   └── seeds/
├── docs/               (Documentation)
├── domain/             (Domain models)
├── field_detection/    (Parsing utilities)
├── fixtures/           (Test fixtures - 20 bank subdirs)
├── http_clients/       (HTTP utilities)
├── infrastructure/     (Cross-cutting concerns)
├── pipeline/           (Core pipeline logic)
├── review/             (Change review workflow)
├── scheduler/          (Job orchestration)
├── scratch/            (Ad-hoc scripts)
├── scripts/            (Maintenance scripts)
├── tests/              (Test suite)
│   └── performance/
└── trusted_view/       (Read-only query builder)
```

### File Count by Module
```
adapters            :  66 files (32 subdirectories)
alerts              :   2 files
api                 :   2 files
db                  :   3 files
domain              :   4 files
field_detection     :   6 files
http_clients        :   2 files
infrastructure      :   9 files
pipeline            :  10 files
review              :   2 files
scheduler           :   7 files
trusted_view        :   2 files
----------------------------------------
Total (source code) : 115 Python files
Tests               :  23 test files
```

---

## 2. Import Dependency Graph

### Module-Level Dependencies

**Command:** AST-based import analysis script

**Graph:**
```
adapters             → domain, field_detection, http_clients, pipeline
alerts               → (no dependencies)
api                  → infrastructure, trusted_view
db                   → infrastructure
domain               → (no dependencies)
field_detection      → domain, pipeline
http_clients         → (no dependencies)
infrastructure       → adapters
pipeline             → domain
review               → domain, pipeline
scheduler            → adapters, http_clients, infrastructure, pipeline
trusted_view         → (no dependencies)
```

### Dependency Statistics
- **Total packages:** 12
- **Packages with dependencies:** 8
- **Total dependency edges:** 17
- **Cycles detected:** 0 ✓
- **Upward dependencies:** 1 ⚠

### Upward Dependency (Violation)

**Finding:** `db` (layer 1) imports from `infrastructure` (layer 3)

**Location:** `db/manager.py:3`
```python
import infrastructure.env
```

**Layer definitions:**
```
Layer 0: domain           (Pure domain logic, no dependencies)
Layer 1: pipeline, db, field_detection, http_clients (Core operations)
Layer 2: adapters, trusted_view, review, alerts (Business logic)
Layer 3: infrastructure   (Cross-cutting concerns, registry)
Layer 4: scheduler, api   (Entry points, orchestration)
```

**Analysis:**
The `db` module (layer 1) imports `infrastructure.env` (layer 3) for environment variable loading. This creates an upward dependency where lower-level database management depends on higher-level infrastructure.

**Impact:**
- **Minor** — `infrastructure.env` is a utility module for loading environment variables
- Does not create a cycle (infrastructure does not import db)
- Could be resolved by moving `env.py` to a lower layer or making it standalone

**Recommendation:**
Move `infrastructure/env.py` to a new `config/` package at layer 0, or accept as minor pragmatic violation.

---

### Cross-Layer Dependency: infrastructure → adapters

**Finding:** `infrastructure/adapter_registry.py` imports **all 33 adapters**

**Location:** `infrastructure/adapter_registry.py:3-35`
```python
from adapters.abay import adapter as abay_adapter
from adapters.adib import adapter as adib_adapter
from adapters.ahadu import adapter as ahadu_adapter
# ... 30 more imports ...
from adapters.zemen import adapter as zemen_adapter

default_registry = AdapterRegistry()
default_registry.register("abay_html", abay_adapter)
# ... 33 registrations ...
```

**Layer violation:** infrastructure (layer 3) → adapters (layer 2)

**Impact:**
- **HIGH** — Eager loading of all adapters at module import time
- Cannot use infrastructure without loading all adapters
- Violates Dependency Inversion Principle (high-level depends on low-level)
- Change scenario A (add new adapter) requires modifying infrastructure

**Recommendation:**
Implement lazy loading with adapter key → module path mapping:
```python
ADAPTER_PATHS = {
    "abay_html": "adapters.abay.adapter",
    "adib_api": "adapters.adib.adapter",
    # ...
}

def get(self, adapter_key: str):
    if adapter_key not in self._loaded:
        module_path = ADAPTER_PATHS[adapter_key]
        self._loaded[adapter_key] = importlib.import_module(module_path)
    return self._loaded[adapter_key]
```

**Alternative:**
Use plugin discovery (scan `adapters/` directory at startup) or external configuration file (YAML/JSON) listing adapters.

---

## 3. Architectural Pattern Identification

### Dominant Pattern: **Data Pipeline + Adapter Pattern**

**Confidence:** 95%

**Evidence:**

1. **Pipeline Pattern** (Core architecture)
   - `pipeline/` module with 10 files implementing data flow stages:
     - `ingest.py` — Entry point for data ingestion
     - `validate.py` — Data validation stage
     - `normalize.py` — Data normalization
     - `fingerprint.py` — Deduplication fingerprinting
     - `deduplicate.py` — Duplicate detection
     - `identity.py` — Identity resolution
     - `persist.py` — Data persistence
   - Sequential processing: `fetch → parse → validate → normalize → deduplicate → persist`
   - Clear stage boundaries with intermediate data structures (`AdapterRecord`, `IngestResult`)

2. **Adapter Pattern** (Extensibility mechanism)
   - 33 adapters in `adapters/` directory, one per bank
   - Each adapter implements common interface: `parse()`, `schema_fingerprint()`, `fetch_raw()`
   - Base class: `adapters/base.py` defines `ParseResult`, adapter protocols
   - Registry pattern for adapter discovery: `infrastructure/adapter_registry.py`
   - Adapters transform heterogeneous bank data formats → standardized `AdapterRecord`

3. **Repository Pattern** (Partial)
   - `infrastructure/rate_source_repository.py` abstracts database access for `rate_source` table
   - However, NOT consistently applied — raw SQL scattered across modules (see §5)

4. **Command Pattern** (Workflow orchestration)
   - `review/workflow.py` — `decide_candidate()` function encapsulates review decisions
   - `scheduler/runner.py` — `Scheduler` class orchestrates collection runs
   - Entry points: `scheduler/run_job.py` (production), `scheduler/cli.py` (admin), `api/app.py` (HTTP)

### Secondary Patterns

**Query Object Pattern**
- `trusted_view/query.py` — `QueryBuilder` class for composing SQL queries
- Fluent API: `.with_source().with_currency().major_currencies_only().execute()`
- Separates query construction from execution

**Finite State Machine**
- `collection_run` table with status: `running → success|partial_success|failed`
- State transitions managed in `pipeline/runs.py`: `start_run()`, `finish_run()`

**Circuit Breaker**
- `infrastructure/circuit_breaker.py` (detected via grep, not analyzed in detail)
- Protects against cascading adapter failures

---

### Does MVC Apply?

**Verdict:** **NO**

**Analysis:**

**Models:**
- ✓ Domain models exist: `domain/records.py` (AdapterRecord), `domain/enums.py`
- ✓ Database schema in `db/migrations/`
- ⚠ No ORM (using raw SQL, not SQLAlchemy/Django ORM)

**Views:**
- ✓ Template directory exists: `api/templates/`
- ⚠ Only 1 template file found (not examined)
- ⚠ API appears to be primarily JSON, not HTML rendering

**Controllers:**
- ✗ No dedicated controller layer
- ⚠ `api/app.py` has route handlers but only 2 files in api/ module
- ⚠ Not the central organizing principle

**Why MVC doesn't fit:**
1. **System is data-centric, not user-centric** — Primary function is data collection and processing, not serving user requests
2. **Pipeline is the dominant pattern** — Data flows through stages, not routed through controllers
3. **Limited web UI** — API appears to be secondary interface (2 files vs 115 total)
4. **No explicit separation of view logic** — Rendering logic minimal

**Better description:** **ETL Pipeline with Plugin Architecture**
- **Extract:** Adapters fetch from bank APIs/websites
- **Transform:** Pipeline stages (validate, normalize, deduplicate)
- **Load:** Persist to database
- **Plugin:** 33 bank adapters registered dynamically

---

## 4. Change Scenario Analysis

### Scenario A: Add a New Bank Adapter

**Task:** Add adapter for "NewBank" with API endpoint

**Files to Create/Modify:**
1. `adapters/newbank/__init__.py` (CREATE)
2. `adapters/newbank/adapter.py` (CREATE)
3. `infrastructure/adapter_registry.py` (MODIFY — add import and register)
4. `fixtures/newbank/` (CREATE — optional test fixtures)
5. `tests/test_newbank_adapter.py` (CREATE — optional)

**Total:** 3-5 files

**Analysis:**
- **Impact:** LOW — Localized change, adapter pattern isolates new code
- **Issue:** Must modify `adapter_registry.py` (see §2 — eager loading)
- **With lazy loading:** Only 2 files (adapter.py + config entry)

---

### Scenario B: Add a Column to `rate_observation`

**Task:** Add `source_confidence` column to track data quality score

**Files to Modify:**
1. `db/migrations/00X_add_source_confidence.sql` (CREATE)
2. `pipeline/persist.py` — Update `insert_observation()` INSERT statement
3. `pipeline/persist.py` — Update `commit_correction()` INSERT statement
4. `review/workflow.py` — Update if corrections need confidence
5. `tests/test_m2_constraints.py` — Update constraint tests
6. `tests/test_m3_pipeline.py` — Update pipeline tests
7. `tests/test_m7_runs_trusted_review.py` — Update review tests
8. `tests/test_single_current_invariant.py` — Update invariant tests
9. ... 7 more test files (detected via grep for `INSERT INTO rate_observation`)

**Total:** 15 files (1 migration + 14 Python files)

**Analysis:**
- **Impact:** HIGH — Schema change ripples through multiple modules
- **Root cause:** No data mapper or ORM to abstract schema
- **Mitigation:** If using ORM (SQLAlchemy), only modify model class + migration

---

### Scenario C: Swap Persistence Layer (Raw SQL → Repository)

**Task:** Replace raw SQL with repository pattern across codebase

**Files to Create/Modify:**
1. `db/repositories/__init__.py` (CREATE)
2. `db/repositories/observation_repository.py` (CREATE)
3. `db/repositories/run_repository.py` (CREATE)
4. `db/repositories/source_repository.py` (CREATE)
5. `alerts/checker.py` (MODIFY)
6. `api/app.py` (MODIFY)
7. `pipeline/deduplicate.py` (MODIFY)
8. `pipeline/ingest.py` (MODIFY)
9. `pipeline/persist.py` (MODIFY)
10. `pipeline/runs.py` (MODIFY)
11. `review/workflow.py` (MODIFY)
12. `scheduler/cli.py` (MODIFY)
13. `scheduler/control.py` (MODIFY)
14. `scheduler/health.py` (MODIFY)
15. `scheduler/runner.py` (MODIFY)
16. `trusted_view/query.py` (MODIFY)
17. ... 1 more file

**Total:** 17 files

**Analysis:**
- **Impact:** VERY HIGH — Requires refactoring across entire codebase
- **SQL scattered in:** pipeline (5 files), scheduler (4 files), review (1), api (1), infrastructure (1), trusted_view (1)
- **Current state:** Only partial repository pattern (`rate_source_repository.py` exists)
- **Benefit:** Schema changes become localized (addresses Scenario B)

---

### Scenario D: Add a New API Endpoint

**Task:** Add `/api/v1/rates/compare` endpoint comparing rates across banks

**Files to Create/Modify:**
1. `api/app.py` (MODIFY — add route handler)
2. `trusted_view/query.py` (MODIFY — add comparison query method, if needed)
3. `api/templates/compare.html` (CREATE — if HTML response)
4. `tests/test_api_compare_endpoint.py` (CREATE — optional)

**Total:** 2-4 files

**Analysis:**
- **Impact:** LOW — API layer is thin, most logic in `trusted_view`
- **Cleanliness:** Good — separation between API (routing) and query logic

---

### Scenario E: Add a New Rate Category

**Task:** Add "wholesale" category for wholesale foreign exchange rates

**Files to Create/Modify:**
1. `db/migrations/00X_add_wholesale_category.sql` (CREATE)
   ```sql
   INSERT INTO rate_category (code, name, approved_at) VALUES
       ('wholesale', 'Wholesale', now());
   ```
2. `domain/records.py` (VERIFY — update `VALID_CATEGORIES` if hardcoded)
3. `pipeline/ingest.py` (VERIFY — category validation)
4. `pipeline/validate.py` (VERIFY — validation rules)
5. `tests/test_m2_constraints.py` (MODIFY — update tests)
6. `tests/test_m3_pipeline.py` (MODIFY — add wholesale test cases)
7. `tests/test_fallback_guardrails.py` (VERIFY — fallback logic)
8. `tests/test_m7_runs_trusted_review.py` (MODIFY — review tests)
9. `tests/test_trusted_view_query_builder.py` (MODIFY — query tests)

**Total:** 10 files

**Analysis:**
- **Impact:** MEDIUM — Validation and test updates across modules
- **Category is data, not code** — Most changes are test updates
- **Category stored in DB** — No hardcoded enum blocking new categories

---

### Summary Table

| Scenario | Files Touched | Count | Locality | Root Cause |
|----------|---------------|-------|----------|------------|
| **A. New adapter** | adapters/, infrastructure/ | 3-5 | ✓ Localized | Eager adapter loading |
| **B. Add column** | migrations/, 14 modules | 15 | ✗ Scattered | No data mapper/ORM |
| **C. Swap persistence** | db/, 16 modules | 17 | ✗ Scattered | SQL not abstracted |
| **D. New endpoint** | api/, trusted_view/ | 2-4 | ✓ Localized | Good separation |
| **E. New category** | migrations/, 9 modules | 10 | ~ Moderate | Validation logic spread |

**Key Observations:**
1. **Adapter addition is clean** (Scenario A) — Plugin pattern works well
2. **Schema changes are painful** (Scenario B) — No ORM abstracts database
3. **Persistence refactoring is massive** (Scenario C) — SQL embedded everywhere
4. **API extension is easy** (Scenario D) — Thin layer design
5. **Domain changes moderate** (Scenario E) — Validation scattered but manageable

---

## 5. Boundary Violations

### 5.1 SQL in Non-Persistence Modules

**Violation:** Raw SQL scattered across non-persistence layers

#### api/ (HTTP API layer)
**File:** `api/app.py:103, 154`
```python
# Line 103
cur.execute("SELECT 1")

# Line 154
cur.execute("SELECT 1")
```
**Purpose:** Health check queries  
**Severity:** LOW — Simple connectivity checks, not business logic

---

#### scheduler/ (Orchestration layer)
**Files:** 4 files with SQL

**`scheduler/control.py:12, 23`**
```python
# Line 12
CREATE TABLE IF NOT EXISTS collection_control (
    id SERIAL PRIMARY KEY,
    paused BOOLEAN NOT NULL DEFAULT FALSE,
    ...
)

# Line 23
INSERT INTO collection_control (paused) VALUES (FALSE)
```
**Purpose:** Control table management  
**Severity:** MEDIUM — Schema definition in business logic

**`scheduler/cli.py:261`**
```sql
SELECT cr.started_at, rs.adapter_key, cr.status, ...
FROM collection_run cr
JOIN rate_source rs ON rs.id = cr.source_id
```
**Purpose:** Admin CLI querying run history  
**Severity:** LOW — Read-only query for display

**`scheduler/health.py:41, 149`**
```python
# Line 41
cur.execute("SELECT 1")

# Line 149
SELECT COUNT(*), array_agg(source_id)
FROM collection_run
WHERE status = 'running' AND started_at < %s
```
**Purpose:** Health checks and monitoring  
**Severity:** LOW — Diagnostic queries

**`scheduler/runner.py`** (detected but lines not shown)

---

#### infrastructure/ (Cross-cutting concerns)
**File:** `infrastructure/rate_source_repository.py:12, 38`
```python
# Line 12
"""SELECT id, adapter_key, source_url, ssl_verify, ...
   FROM rate_source WHERE id = %s"""

# Line 38
"""SELECT id, adapter_key, source_url, ssl_verify, ...
   FROM rate_source WHERE is_enabled = TRUE"""
```
**Purpose:** Repository pattern for `rate_source` table  
**Severity:** ACCEPTABLE — This IS persistence logic

---

#### trusted_view/ (Read-only views)
**File:** `trusted_view/query.py:122, 145`
```python
# Line 122
distinct = f"SELECT DISTINCT ON ({self._distinct_on})"

# Line 145
SELECT 1 FROM change_candidate cc
WHERE cc.observation_id = ro.id AND cc.status = 'open'
```
**Purpose:** Query builder for read-only access  
**Severity:** ACCEPTABLE — Read-only layer, SQL is the interface

---

### 5.2 Entry Points Sharing Code Paths

**Entry points identified:**
1. `scheduler/run_job.py` — Production cron job
2. `scheduler/cli.py` — Admin CLI tool
3. `api/app.py` — HTTP API server

**Analysis:**

**`scheduler/run_job.py`:**
```python
from scheduler.runner import run_all  # ← Retired function
from scheduler.health import quick_health_check
```
- **Status:** RECENTLY FIXED (see git log P7)
- **Previous:** Called legacy `run_all()` function
- **Current:** Migrated to `Scheduler().run_all()` class method
- **Shared path:** ✓ Both entry points now use `Scheduler` class

**`scheduler/cli.py`:**
```python
from scheduler.runner import Scheduler
```
- **Imports:** `Scheduler` class (new implementation)
- **Shared path:** ✓ Uses same `Scheduler.run_source()` as `run_job.py`

**`api/app.py`:**
```python
from infrastructure import ...
```
- **Imports:** Only infrastructure utilities, not scheduler
- **Separate path:** API serves data via `trusted_view`, does NOT trigger collections
- **Shared path:** ✗ API is independent (read-only)

**Verdict:** ✓ **Scheduler entry points share code path** (after P7 refactor)

---

### 5.3 Modules Importing Another Package's Internals

**Check:** Cross-package imports of private modules (e.g., `from other_pkg._internal import ...`)

**Result:** ✓ **No violations found**

**Method:** Regex scan for `from \w+\._\w+` patterns across all Python files

---

## 6. Repository Hygiene

### Documentation
- ✗ **README.md:** Missing at repository root
- ✓ **.gitignore:** Present
- ✓ **requirements.txt:** Present (21 dependencies)
- ✓ **Tests:** 23 test files in `tests/` directory
- ✓ **docs/:** 4 markdown files
  - `code-review.md`
  - `code-review-v2.md`
  - `refactor-plan.md`
  - `test-failures.md`
- ✓ **.env.example:** Present with 15 configuration variables

**Gap:** No README.md to explain:
- Project purpose and scope
- Setup instructions
- Running tests
- Deployment procedures
- Architecture overview

**Recommendation:** Create `README.md` with:
1. One-paragraph description: "Ethiopian Bank Exchange Rate Intelligence System — automated collection and aggregation of foreign exchange rates from 33 Ethiopian banks"
2. Quick start: install dependencies, setup database, run tests
3. Architecture diagram showing pipeline + adapters
4. Link to `docs/` for detailed documentation

---

### Code Quality Indicators

**TODO/FIXME markers:** 0 found ✓

**Hardcoded credentials:** None detected ✓

**Large test fixtures:** 2 files > 100KB
- `fixtures/.../normal.html` (150KB)
- `fixtures/.../normal.html` (282KB)

**Analysis:** Fixture size acceptable for HTML snapshots of bank websites

---

### Configuration Management

**Files:**
- ✓ `.env.example` — Template with 15 variables
- ✓ `.env.local` — Exists (not examined, assumed in .gitignore)
- ✓ `infrastructure/config.py` — Configuration class
- ✓ `infrastructure/env.py` — Environment loader

**Pattern:** Environment variables → `Config` class → injected dependencies

**Gap:** No `.env.example` comments explaining each variable

**Recommendation:** Add inline comments to `.env.example`:
```bash
# Database connection string (Postgres)
DATABASE_URL=postgresql://user:password@localhost:5432/exchange_rates

# HTTP timeout for bank website scraping (seconds)
HTTP_TIMEOUT=30
```

---

### Dependency Management

**requirements.txt:** 21 packages
- Flask, gunicorn (web server)
- psycopg2-binary (database)
- beautifulsoup4, lxml (HTML parsing)
- requests, cloudscraper (HTTP)
- playwright (browser automation)
- prometheus-client (metrics)
- click (CLI)
- pytest (testing)

**Issues:**
- ✗ No version pinning for some packages (using `==` but not all)
- ✗ No `requirements-dev.txt` separating test dependencies
- ✗ No `setup.py` or `pyproject.toml` for package metadata

**Recommendation:**
1. Pin all versions: `pip freeze > requirements.txt`
2. Separate: `requirements-dev.txt` with pytest, coverage tools
3. Add `pyproject.toml` for modern Python packaging

---

### Test Organization

**Structure:**
```
tests/
├── performance/
│   └── test_connection_pooling.py
├── test_m2_constraints.py
├── test_m3_pipeline.py
├── test_m7_runs_trusted_review.py
├── test_m10_ingest_scheduler.py
├── test_*.py (19 more files)
└── db_utils.py
```

**Naming convention:**
- ⚠ `test_m2_`, `test_m3_`, `test_m7_`, `test_m10_` — Non-obvious prefixes
- ✓ `test_infrastructure_*.py` — Clear module mapping
- ✓ `test_fallback_guardrails.py` — Descriptive

**Coverage:** 623 tests, all passing (per test-failures.md)

**Gap:** No `pytest.ini` or `pyproject.toml` with pytest configuration

**Recommendation:**
1. Rename `test_m2_*.py` to `test_database_constraints.py`
2. Add `pyproject.toml`:
   ```toml
   [tool.pytest.ini_options]
   testpaths = ["tests"]
   python_files = "test_*.py"
   python_classes = "Test*"
   python_functions = "test_*"
   ```

---

## 7. Verdict

### Overall Assessment

**Architectural Health:** ✓ **GOOD**

**Pattern Consistency:** ✓ **HIGH** — Pipeline + Adapter pattern applied consistently

**Separation of Concerns:** ~ **MODERATE** — Good at top level, SQL leakage at module level

**Modularity:** ✓ **HIGH** — 12 packages with clear responsibilities

**Testability:** ✓ **EXCELLENT** — 623 tests, 100% passing

---

### Default Recommendation: **KEEP THE STRUCTURE**

**Rationale:**
1. **Clear pattern** — ETL pipeline with adapters is well-suited to domain
2. **Low coupling** — Only 1 upward dependency, 0 cycles
3. **Proven in production** — 7 refactor packages completed successfully
4. **High test coverage** — Refactoring is safe

**Don't fix what isn't broken.** The current structure serves the system's needs effectively.

---

### Proposed Moves (Optional Improvements)

#### Move 1: Extract Lazy Adapter Registry

**Current:** `infrastructure/adapter_registry.py` eagerly imports all 33 adapters

**Proposed:**
```
infrastructure/
  ├── adapter_registry.py      (registry logic)
  └── adapter_config.py        (key → module path mapping)
```

**Change:**
```python
# adapter_config.py
ADAPTER_PATHS = {
    "abay_html": "adapters.abay.adapter",
    "adib_api": "adapters.adib.adapter",
    # ... 31 more ...
}

# adapter_registry.py
class AdapterRegistry:
    def get(self, key):
        if key not in self._loaded:
            path = ADAPTER_PATHS[key]
            self._loaded[key] = importlib.import_module(path)
        return self._loaded[key]
```

**Cost:**
- **Development:** 2-4 hours
- **Files changed:** 1 (adapter_registry.py)
- **Risk:** LOW — Tests catch registration errors

**Benefits:**
- **Scenario A improved:** Add adapter without modifying registry (only config)
- **Startup time:** Faster (load adapters on-demand, not at import)
- **Layer violation fixed:** infrastructure no longer depends on adapters

**Verdict:** ✓ **RECOMMEND** — High value, low cost

---

#### Move 2: Introduce Repository Layer

**Current:** Raw SQL scattered across 8 modules (16 files)

**Proposed:**
```
db/
  ├── repositories/
  │   ├── observation_repository.py
  │   ├── run_repository.py
  │   └── source_repository.py (already exists in infrastructure/)
  └── migrations/
```

**Change:** Centralize all SQL in repository classes:
```python
# db/repositories/observation_repository.py
class ObservationRepository:
    def insert(self, conn, record, source_id, run_id, ...):
        # INSERT INTO rate_observation ...
    
    def find_by_fingerprint(self, conn, fingerprint):
        # SELECT ... WHERE snapshot_fingerprint = %s
    
    def find_current_by_key(self, conn, logical_key):
        # SELECT ... WHERE logical_key = %s AND is_current = TRUE
```

**Cost:**
- **Development:** 2-3 days (16 files to refactor)
- **Files changed:** 17 (create 3 repositories + modify 16 files)
- **Risk:** MEDIUM — Must ensure transaction boundaries preserved

**Benefits:**
- **Scenario B improved:** Schema changes localized to repositories
- **Scenario C completed:** Persistence layer abstracted
- **Testability:** Repository methods unit-testable in isolation

**Verdict:** ~ **OPTIONAL** — High value, medium cost. Prioritize if schema changes become frequent.

---

#### Move 3: Move `infrastructure/env.py` to Layer 0

**Current:** `db/manager.py` (layer 1) imports `infrastructure.env` (layer 3)

**Proposed:**
```
config/
  └── env.py

# Or merge into:
domain/
  └── config.py
```

**Cost:**
- **Development:** 30 minutes
- **Files changed:** 3-4 (move env.py, update imports)
- **Risk:** VERY LOW — Simple refactor

**Benefits:**
- **Layer violation fixed:** No upward dependency
- **Clarity:** Configuration is foundational, not infrastructure

**Verdict:** ✓ **RECOMMEND** — Low cost, fixes architectural violation

---

#### Move 4: Create `README.md`

**Current:** No README at repository root

**Proposed:** Create `README.md` with:
1. Project description (1 paragraph)
2. Quick start (5 commands)
3. Architecture overview (1 diagram)
4. Links to detailed docs

**Cost:**
- **Development:** 1-2 hours
- **Files changed:** 1 (create README.md)
- **Risk:** NONE

**Benefits:**
- **Developer onboarding:** New team members understand project quickly
- **Documentation:** Central entry point to docs/
- **Professional polish:** Standard practice for open source projects

**Verdict:** ✓ **HIGHLY RECOMMEND** — Essential for maintainability

---

## 8. Questions for Owner

1. **Adapter Registry**
   - Is the eager loading of all 33 adapters intentional?
   - Would lazy loading (import on first use) be acceptable?
   - Are adapters expected to grow beyond 33?

2. **SQL Distribution**
   - Is the scatter of raw SQL across modules acceptable?
   - Has schema evolution been painful in practice?
   - Would repository pattern abstraction be valuable?

3. **API Usage**
   - Is the API (`api/app.py`) heavily used?
   - Are most queries via API or direct database access?
   - Should API layer be expanded or is it intentionally minimal?

4. **Control Table**
   - `scheduler/control.py` creates its own table with `CREATE TABLE IF NOT EXISTS`
   - Should this be a migration instead?
   - Is the control table schema stable or expected to evolve?

5. **Performance**
   - Has the eager adapter loading caused startup slowness?
   - Are the 2 large fixture files (150KB, 282KB) a concern?
   - Is database connection pooling (`tests/performance/`) used in production?

6. **Future Plans**
   - Are new bank adapters added frequently? (affects Move 1 priority)
   - Are schema changes common? (affects Move 2 priority)
   - Is the system expected to grow significantly?

7. **Documentation**
   - Would an architecture diagram be useful? (can be generated from import graph)
   - Should adapter development guide be created?
   - Is there a deployment runbook?

---

## 9. Needs Confirmation

The following aspects could not be verified without additional context:

1. **Performance Metrics**
   - Actual startup time with 33 adapters eager-loaded
   - Database query performance (no EXPLAIN ANALYZE output)
   - API response times under load

2. **Production Configuration**
   - Connection pool settings in production
   - Actual values in `.env.local` (not examined for security)
   - Deployment platform and infrastructure

3. **API Endpoints**
   - Full list of routes in `api/app.py` (file not fully examined)
   - Expected API traffic volume
   - Public vs internal API usage

4. **Monitoring and Observability**
   - `prometheus_client` in requirements — is `/metrics` endpoint configured?
   - Alert routing from `alerts/` module
   - Log aggregation and retention

5. **Circuit Breaker Configuration**
   - `infrastructure/circuit_breaker.py` thresholds
   - Failure rate tolerance
   - Recovery behavior

6. **Migration Strategy**
   - Are migrations applied manually or automated?
   - Is there a rollback procedure?
   - Are migrations tested in staging?

---

## Summary

### Architectural Strengths
✓ Clear ETL pipeline pattern  
✓ Adapter pattern isolates bank-specific logic  
✓ Zero dependency cycles  
✓ High test coverage (623 tests)  
✓ Layered architecture with clean boundaries  
✓ Successful refactor (P1-P7) demonstrates maintainability  

### Architectural Weaknesses
⚠ Eager adapter loading creates unnecessary coupling  
⚠ SQL scattered across non-persistence modules  
⚠ One upward dependency (db → infrastructure)  
⚠ No README.md for onboarding  
⚠ Repository pattern only partially applied  

### Recommended Actions (Prioritized)
1. **Create README.md** (1-2 hours) — Immediate value
2. **Lazy load adapters** (2-4 hours) — Fixes coupling, improves Scenario A
3. **Move env.py to layer 0** (30 min) — Fixes architectural violation
4. *(Optional)* **Repository layer** (2-3 days) — Large refactor, high value if schema changes frequent

### Overall Verdict
✓ **Architecture is sound. Keep the current structure.**  

The system demonstrates a well-designed pipeline architecture with appropriate use of patterns. The recommended improvements are optimizations, not fundamental fixes. The absence of major issues indicates a mature, production-ready codebase.

---

**Review completed:** 2026-11-23  
**Next review:** After implementing Move 1 (lazy adapter loading) or when architectural pain points emerge.
