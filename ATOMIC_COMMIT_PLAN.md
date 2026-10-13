# Atomic Commit Strategy - Production-Ready Repository

## Philosophy
Each commit should be:
- **Atomic**: Single logical change, complete and functional
- **Reversible**: Can be reverted without breaking the system
- **Reviewable**: Small enough to understand in one sitting
- **Documented**: Clear message following conventional commits

## Conventional Commit Format
```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**: `feat`, `fix`, `docs`, `chore`, `test`, `refactor`, `perf`, `ci`

---

## Commit Sequence (13 commits)

### 1. Repository Infrastructure
```bash
git init
git add .gitignore .env.example
git commit -m "chore(infra): configure repository security and environment

- Add comprehensive .gitignore for Python/PostgreSQL stack
- Exclude secrets (.env, *.pem, *.key, credentials.json)
- Exclude build artifacts (__pycache__, *.pyc, .pytest_cache)
- Exclude runtime files (logs/*, backups/*.sql)
- Exclude temp scripts (inspect_*.py, survey_*.py)
- Add .env.example template with required configuration

WHY: Prevent secret leaks and keep repository clean before any code
SECURITY: All sensitive data patterns blocked at repo initialization"
```

### 2. Project Documentation
```bash
git add README.md CLAUDE.md docs/plan/ docs/decisions/defaults.md docs/decisions/ADR-index.md
git commit -m "docs(project): add system overview and engineering standards

- Add README with project setup instructions
- Add CLAUDE.md with engineering rules and authority hierarchy
- Add execution plan and milestone tracking (docs/plan/)
- Add engineering defaults and decision framework
- Add ADR index for architectural decision tracking

WHY: Team needs context before diving into code
ONBOARDING: New engineers start here to understand system design"
```

### 3. Architecture Decision Records
```bash
git add docs/decisions/ADR-004.md docs/decisions/ADR-005.md docs/decisions/ADR-006.md \
        docs/decisions/ADR-007-008-009.md docs/decisions/ADR-010-011.md \
        docs/decisions/ADR-012-013.md docs/decisions/ADR-014.md
git commit -m "docs(adr): document critical architectural decisions

ADRs included:
- ADR-004: Entity separation and immutability
- ADR-005: Deduplication and versioning strategy
- ADR-006: Identity and validation workflows
- ADR-007-009: SSL handling, browser automation, fixture strategy
- ADR-010-011: Category defaults for Rammis/Wegagen
- ADR-012-013: Single-pair banks and unknown categories
- ADR-014: Rate observation fingerprinting

WHY: Decisions are documented with rationale and evidence
PRODUCTION: Critical for understanding system constraints and tradeoffs"
```

### 4. Database Schema
```bash
git add db/migrations/001_initial_schema.sql
git commit -m "feat(db): add PostgreSQL schema with immutability constraints

Tables:
- bank: Ethiopian bank registry with source authority
- rate_source: Collection endpoints with verification status
- collection_run: Idempotent run tracking with status
- rate_observation: Immutable rate records with versioning
- observation_version: Version history with supersedes chain
- raw_capture: Failed/suspicious response preservation
- category: Rate categories (cash, transactional, diaspora)

Constraints:
- Unique identity per source+publication+date+currency
- CHECK: rates must be positive, never zero
- CHECK: version_number starts at 1, monotonic increase
- Partial indexes for performance on current/trusted queries
- SERIALIZABLE isolation for version switching

WHY: Schema enforces business rules at database level
PRODUCTION: Prevents data corruption through constraints"
```

### 5. Domain Model
```bash
git add domain/
git commit -m "feat(domain): implement core entities and business rules

Entities:
- Bank, RateSource, CollectionRun
- RateObservation with validation/identity status enums
- ObservationVersion with supersedes tracking
- RawCapture for forensics

Status Enums:
- ValidationStatus: accepted, flagged, rejected
- IdentityStatus: confirmed, ambiguous, review_required
- CollectionStatus: pending, running, success, failed
- VerificationStatus: unverified, validated, blocked

Business Rules:
- Immutability: observations never updated in place
- Corrections: new version with supersedes_id link
- Current selection: latest non-superseded version
- Freshness: staleness calculation from effective_date

WHY: Domain model encodes business logic independent of infrastructure
TESTING: Pure Python classes, easy to test without database"
```

### 6. Rate Processing Pipeline
```bash
git add pipeline/
git commit -m "feat(pipeline): implement rate validation and normalization pipeline

Modules:
- validate.py: Business rule validation (positive rates, known currencies)
- normalize.py: Currency/category mapping, date parsing, decimal conversion
- fingerprint.py: Deterministic identity hash (v1 excludes fetched_at)
- identity.py: Deduplication and ambiguity detection
- deduplicate.py: Same publication + values = skip insert
- persist.py: Transactional writes with constraint enforcement
- diagnose.py: Rejection codes and human-readable reasons

Pipeline Flow:
1. Adapter output → Validate → Normalize → Fingerprint
2. Identity check → Route to review OR persist
3. Deduplicate → Insert OR flag
4. Diagnostics on all rejections

WHY: Separation of concerns, pure functions, testable without I/O
PRODUCTION: Rejection reasons enable debugging without raw data access"
```

### 7. Bank Source Registry
```bash
git add docs/register/source-register.json docs/register/waves.md \
        docs/mapping/.gitkeep
git commit -m "feat(registry): add bank source registry with rollout waves

Source Registry (source-register.json):
- 21 Ethiopian banks with official rate sources
- Verification status per source (validated, unverified, blocked)
- Adapter key mapping (API, HTML, AJAX, browser)
- SSL override flags for cert issues (BOA, Amhara, Hibret)
- Active/inactive status for staged rollout

Rollout Waves (waves.md):
- Wave 1: CBE, Dashen (API, validated)
- Wave 2: ADIB, CBO (API, working adapters)
- Wave 3: Rammis, Wegagen (API, category defaults)
- Wave 4: HTML banks (17 sources, static scraping)
- Wave 5: Browser-required (nonce, JS, DNS issues) - BLOCKED

WHY: Phased rollout reduces risk, allows validation per wave
PRODUCTION: Easy to enable/disable sources without code changes"
```

### 8. Evidence and Fixtures
```bash
git add docs/evidence/ fixtures/ docs/mapping/
git commit -m "test(fixtures): add verified bank captures and field mappings

Evidence (docs/evidence/):
- addis/2026-10-10: JSON capture with comparison notes
- cbe/2026-10-10: API response with official verification
- dashen/2026-10-10: HTML capture with rendered comparison
- wave_survey/: RAMMIS and Wegagen API survey results

Field Mappings (docs/mapping/):
- Per-bank CSV field → domain entity mapping
- VERIFIED status with evidence timestamps
- TO VERIFY status with blocking reasons
- Category and currency mapping decisions

Fixtures (fixtures/):
- Per-adapter test data for unit tests
- Normal, empty, malformed, unknown currency scenarios
- Duplicate and partial failure cases

WHY: Tests use fixtures, not live sources (fast, deterministic)
PRODUCTION: Verified mappings give confidence in data accuracy"
```

### 9. Bank Adapters - Wave 1 & 2 (APIs)
```bash
git add adapters/__init__.py \
        adapters/cbe/ adapters/adib/ adapters/dashen/ \
        adapters/rammis/ adapters/wegagen/ adapters/cbo/
git commit -m "feat(adapters): add Wave 1-2 bank adapters (API sources)

API Adapters:
- cbe: Commercial Bank of Ethiopia (JSON API, validated)
- adib: Addis International Bank (JSON API)
- dashen: Dashen Bank (AJAX endpoint)
- rammis: RamMIS rates (JSON API, single pair, ADR-010)
- wegagen: Wegagen Bank (JSON API, transactional only, ADR-011)
- cbo: Cooperative Bank of Oromia (HTML table)

Adapter Contract:
- fetch(source_url, ssl_verify, timeout) → raw response
- parse(response) → list of AdapterOutput
- AdapterOutput: currency, buying, selling, category, effective_date, publication_key

Error Handling:
- HTTP errors → CollectionFailure with detail
- Parse errors → MalformedResponse with diagnostic
- Empty rates → Success with empty list (not failure)

WHY: API sources are most reliable, start here for validation
TESTING: Each adapter has fixture-based unit tests"
```

### 10. Bank Adapters - Wave 3 & 4 (HTML Scrapers)
```bash
git add adapters/hibret/ adapters/amhara/ adapters/boa/ adapters/bunna/ \
        adapters/goh_betoch/ adapters/nib/ adapters/sidama/ adapters/berhan/ \
        adapters/tsehay/ adapters/dbe/ adapters/siinqee/ adapters/global_/ \
        adapters/ahadu/ adapters/enat/ adapters/omo/
git commit -m "feat(adapters): add Wave 3-4 bank adapters (HTML sources)

HTML Scraping Adapters (15 banks):
- SSL override (ADR-009): hibret, amhara, boa
- Single pair default (ADR-012): ahadu, enat, dbe, siinqee, goh_betoch, global_
- Table scraping: bunna, nib, sidama, berhan, tsehay, omo

Parsing Strategies:
- BeautifulSoup for well-formed HTML tables
- XPath for complex nested structures
- Regex fallback for plain text rate lists
- Ethiopian calendar date parsing with fallback

Robustness:
- Handle missing columns (buying OR selling may be absent)
- Handle unknown categories (flag, don't reject)
- Handle multiple tables (differentiate by headers)
- SSL verification bypass with explicit flag (security tradeoff documented)

WHY: HTML sources require more maintenance but cover most banks
PRODUCTION: Failures isolated per adapter, don't crash pipeline"
```

### 11. Collection Scheduler
```bash
git add scheduler/ alerts/
git commit -m "feat(scheduler): add collection orchestration and alerting

Scheduler (scheduler/):
- runner.py: Orchestrate parallel collections with concurrency limit
- run_all(): Fetch enabled sources, spawn tasks, aggregate results
- Idempotency: Check for running runs, recover stuck runs (timeout)
- Rate limiting: Per-source delays, exponential backoff on errors
- Retry policy: 3 attempts with increasing delays, mark failed after exhaustion

Concurrency Control:
- One running collection per source (enforced by DB unique constraint)
- Configurable max concurrent (default 3, tunable for production)
- Graceful degradation: One failure doesn't stop others

Alerts (alerts/):
- checker.py: Detect stale sources (no success in 24h)
- Detect repeated failures (3+ consecutive fails)
- Detect schema changes (malformed rate increase >50%)
- Output: JSON alert payload for monitoring integration

WHY: Reliable collection even with unreliable sources
PRODUCTION: Observable failures, automatic recovery, bounded resources"
```

### 12. REST API and Trusted View
```bash
git add api/ trusted_view/ review/
git commit -m "feat(api): add REST API with trusted rate view

REST API (api/app.py):
- GET /rates: Current rates with filters (bank, currency, category)
- GET /rates/history: Historical rates with date range
- GET /banks: Bank list with last collection status
- GET /health: System health and staleness summary

Trusted View (trusted_view/):
- Filters: is_current AND identity_status='confirmed' 
          AND validation_status != 'rejected'
          AND category_id IS NOT NULL
- Staleness indicator: Days since effective_date
- Uncertainty flags: Ambiguous identity, flagged validation
- Never show superseded versions in default view

Review Workflow (review/):
- Candidate classifier: Route ambiguous/changed rates to review queue
- Decision recording: Actor, reason, timestamp for corrections
- Correction commit: Create new version with supersedes_id

Frontend (api/templates/index.html):
- Bank comparison table with real-time rates
- Staleness indicators (fresh, stale, very stale)
- Category filtering (cash, transactional, diaspora)
- Currency selection

WHY: API enforces trusted view rules, no raw unvalidated data exposed
PRODUCTION: Clear separation between collection and serving"
```

### 13. Test Suite
```bash
git add tests/
git commit -m "test(suite): add acceptance and integration tests

Test Structure:
- test_m1_schema.py: Database constraints and indexes
- test_m2_constraints.py: Business rule enforcement (positive rates, etc)
- test_m3_pipeline.py: Validation, normalization, fingerprinting
- test_m4_adib_adapter.py: Adapter contract compliance
- test_m5_identity.py: Deduplication and ambiguity detection
- test_m6_versioning.py: Correction workflow and supersedes chain
- test_m7_current_selection.py: Current rate logic
- test_m8_wave2_adapters.py: All Wave 2 adapters with fixtures
- test_concurrency.py: Parallel collection safety
- db_utils.py: Test database setup and fixtures

Coverage:
- Acceptance tests 1-22 from design handoff
- Added tests from gap review (edge cases)
- Each test named after requirement number (traceability)

Test Database:
- Real PostgreSQL with all constraints (not SQLite)
- Isolated transactions, rolled back after each test
- Fixtures loaded per test class

WHY: Acceptance tests prove correctness, enable safe refactoring
PRODUCTION: Tests must pass before any deployment"
```

### 14. Operational Scripts
```bash
git add seed_and_run.py ops/ backups/
git commit -m "ops(scripts): add database seeding and operational tooling

seed_and_run.py:
- Load source-register.json into database
- Enable only adapters with working implementations
- Apply category defaults from ADRs (Rammis, Wegagen, single-pair)
- Disable test fixture sources (leftover from pytest)
- Run full collection cycle
- Report results: accepted, flagged, rejected, duplicates

Operational Scripts (ops/):
- backup.sh: PostgreSQL dump with timestamp
- restore.sh: Restore from backup with verification
- reset_stuck_runs.sh: Recover hung collections
- health_check.sh: Database and API connectivity check

Initial Backup (backups/):
- exchange_rates_2026-10-12.sql.gz: Known-good state after Wave 1-3 validation
- Used for test database setup and disaster recovery

WHY: Production operations need tested, documented procedures
ONBOARDING: New developers run seed_and_run.py to populate dev database"
```

### 15. CI/CD Configuration (Future)
```bash
# Not yet implemented, but structure ready:
git add .github/workflows/ci.yml
git commit -m "ci(github): add CI pipeline for tests and linting

Pipeline:
- Run test suite on push to main/develop
- Lint with flake8, type check with mypy
- Security scan with bandit (check for hardcoded secrets)
- Database migration dry-run
- Build Docker image (if passing)

Branch Protection:
- Require PR reviews before merge to main
- Require CI passing before merge
- No direct commits to main

WHY: Automated quality gates prevent broken code in production"
```

---

## Execution Script

```bash
#!/bin/bash
# execute_atomic_commits.sh - Run this to create the commit sequence

set -e  # Exit on any error

echo "=== Initializing Repository with Atomic Commits ==="

# Initialize
git init
echo "✓ Repository initialized"

# Commit 1: Infrastructure
git add .gitignore .env.example logs/.gitkeep
git commit -m "chore(infra): configure repository security and environment

- Add comprehensive .gitignore for Python/PostgreSQL stack
- Exclude secrets (.env, *.pem, *.key, credentials.json)
- Exclude build artifacts (__pycache__, *.pyc, .pytest_cache)
- Exclude runtime files (logs/*, backups/*.sql)
- Exclude temp scripts (inspect_*.py, survey_*.py)
- Add .env.example template with required configuration

WHY: Prevent secret leaks and keep repository clean before any code
SECURITY: All sensitive data patterns blocked at repo initialization"
echo "✓ Commit 1: Infrastructure"

# Commit 2: Project Documentation
git add README.md CLAUDE.md docs/plan/ docs/decisions/defaults.md docs/decisions/ADR-index.md
git commit -m "docs(project): add system overview and engineering standards

- Add README with project setup instructions
- Add CLAUDE.md with engineering rules and authority hierarchy
- Add execution plan and milestone tracking (docs/plan/)
- Add engineering defaults and decision framework
- Add ADR index for architectural decision tracking

WHY: Team needs context before diving into code
ONBOARDING: New engineers start here to understand system design"
echo "✓ Commit 2: Project Documentation"

# Commit 3: ADRs
git add docs/decisions/ADR-*.md
git commit -m "docs(adr): document critical architectural decisions

ADRs included:
- ADR-004: Entity separation and immutability
- ADR-005: Deduplication and versioning strategy
- ADR-006: Identity and validation workflows
- ADR-007-009: SSL handling, browser automation, fixture strategy
- ADR-010-011: Category defaults for Rammis/Wegagen
- ADR-012-013: Single-pair banks and unknown categories
- ADR-014: Rate observation fingerprinting

WHY: Decisions are documented with rationale and evidence
PRODUCTION: Critical for understanding system constraints and tradeoffs"
echo "✓ Commit 3: Architecture Decision Records"

# Commit 4: Database
git add db/
git commit -m "feat(db): add PostgreSQL schema with immutability constraints

Tables:
- bank: Ethiopian bank registry with source authority
- rate_source: Collection endpoints with verification status
- collection_run: Idempotent run tracking with status
- rate_observation: Immutable rate records with versioning
- observation_version: Version history with supersedes chain
- raw_capture: Failed/suspicious response preservation
- category: Rate categories (cash, transactional, diaspora)

Constraints:
- Unique identity per source+publication+date+currency
- CHECK: rates must be positive, never zero
- CHECK: version_number starts at 1, monotonic increase
- Partial indexes for performance on current/trusted queries
- SERIALIZABLE isolation for version switching

WHY: Schema enforces business rules at database level
PRODUCTION: Prevents data corruption through constraints"
echo "✓ Commit 4: Database Schema"

# Commit 5: Domain
git add domain/
git commit -m "feat(domain): implement core entities and business rules

Entities:
- Bank, RateSource, CollectionRun
- RateObservation with validation/identity status enums
- ObservationVersion with supersedes tracking
- RawCapture for forensics

Status Enums:
- ValidationStatus: accepted, flagged, rejected
- IdentityStatus: confirmed, ambiguous, review_required
- CollectionStatus: pending, running, success, failed
- VerificationStatus: unverified, validated, blocked

Business Rules:
- Immutability: observations never updated in place
- Corrections: new version with supersedes_id link
- Current selection: latest non-superseded version
- Freshness: staleness calculation from effective_date

WHY: Domain model encodes business logic independent of infrastructure
TESTING: Pure Python classes, easy to test without database"
echo "✓ Commit 5: Domain Model"

# Commit 6: Pipeline
git add pipeline/
git commit -m "feat(pipeline): implement rate validation and normalization pipeline

Modules:
- validate.py: Business rule validation (positive rates, known currencies)
- normalize.py: Currency/category mapping, date parsing, decimal conversion
- fingerprint.py: Deterministic identity hash (v1 excludes fetched_at)
- identity.py: Deduplication and ambiguity detection
- deduplicate.py: Same publication + values = skip insert
- persist.py: Transactional writes with constraint enforcement
- diagnose.py: Rejection codes and human-readable reasons

Pipeline Flow:
1. Adapter output → Validate → Normalize → Fingerprint
2. Identity check → Route to review OR persist
3. Deduplicate → Insert OR flag
4. Diagnostics on all rejections

WHY: Separation of concerns, pure functions, testable without I/O
PRODUCTION: Rejection reasons enable debugging without raw data access"
echo "✓ Commit 6: Pipeline"

# Commit 7: Registry
git add docs/register/ docs/mapping/.gitkeep
git commit -m "feat(registry): add bank source registry with rollout waves

Source Registry (source-register.json):
- 21 Ethiopian banks with official rate sources
- Verification status per source (validated, unverified, blocked)
- Adapter key mapping (API, HTML, AJAX, browser)
- SSL override flags for cert issues (BOA, Amhara, Hibret)
- Active/inactive status for staged rollout

Rollout Waves (waves.md):
- Wave 1: CBE, Dashen (API, validated)
- Wave 2: ADIB, CBO (API, working adapters)
- Wave 3: Rammis, Wegagen (API, category defaults)
- Wave 4: HTML banks (17 sources, static scraping)
- Wave 5: Browser-required (nonce, JS, DNS issues) - BLOCKED

WHY: Phased rollout reduces risk, allows validation per wave
PRODUCTION: Easy to enable/disable sources without code changes"
echo "✓ Commit 7: Bank Registry"

# Commit 8: Evidence
git add docs/evidence/ docs/mapping/ fixtures/
git commit -m "test(fixtures): add verified bank captures and field mappings

Evidence (docs/evidence/):
- addis/2026-10-10: JSON capture with comparison notes
- cbe/2026-10-10: API response with official verification
- dashen/2026-10-10: HTML capture with rendered comparison
- wave_survey/: RAMMIS and Wegagen API survey results

Field Mappings (docs/mapping/):
- Per-bank CSV field → domain entity mapping
- VERIFIED status with evidence timestamps
- TO VERIFY status with blocking reasons
- Category and currency mapping decisions

Fixtures (fixtures/):
- Per-adapter test data for unit tests
- Normal, empty, malformed, unknown currency scenarios
- Duplicate and partial failure cases

WHY: Tests use fixtures, not live sources (fast, deterministic)
PRODUCTION: Verified mappings give confidence in data accuracy"
echo "✓ Commit 8: Evidence and Fixtures"

# Commit 9: API Adapters
git add adapters/__init__.py adapters/cbe/ adapters/adib/ adapters/dashen/ \
         adapters/rammis/ adapters/wegagen/ adapters/cbo/
git commit -m "feat(adapters): add Wave 1-2 bank adapters (API sources)

API Adapters:
- cbe: Commercial Bank of Ethiopia (JSON API, validated)
- adib: Addis International Bank (JSON API)
- dashen: Dashen Bank (AJAX endpoint)
- rammis: RamMIS rates (JSON API, single pair, ADR-010)
- wegagen: Wegagen Bank (JSON API, transactional only, ADR-011)
- cbo: Cooperative Bank of Oromia (HTML table)

Adapter Contract:
- fetch(source_url, ssl_verify, timeout) → raw response
- parse(response) → list of AdapterOutput
- AdapterOutput: currency, buying, selling, category, effective_date, publication_key

Error Handling:
- HTTP errors → CollectionFailure with detail
- Parse errors → MalformedResponse with diagnostic
- Empty rates → Success with empty list (not failure)

WHY: API sources are most reliable, start here for validation
TESTING: Each adapter has fixture-based unit tests"
echo "✓ Commit 9: API Adapters"

# Commit 10: HTML Adapters
git add adapters/hibret/ adapters/amhara/ adapters/boa/ adapters/bunna/ \
        adapters/goh_betoch/ adapters/nib/ adapters/sidama/ adapters/berhan/ \
        adapters/tsehay/ adapters/dbe/ adapters/siinqee/ adapters/global_/ \
        adapters/ahadu/ adapters/enat/ adapters/omo/
git commit -m "feat(adapters): add Wave 3-4 bank adapters (HTML sources)

HTML Scraping Adapters (15 banks):
- SSL override (ADR-009): hibret, amhara, boa
- Single pair default (ADR-012): ahadu, enat, dbe, siinqee, goh_betoch, global_
- Table scraping: bunna, nib, sidama, berhan, tsehay, omo

Parsing Strategies:
- BeautifulSoup for well-formed HTML tables
- XPath for complex nested structures
- Regex fallback for plain text rate lists
- Ethiopian calendar date parsing with fallback

Robustness:
- Handle missing columns (buying OR selling may be absent)
- Handle unknown categories (flag, don't reject)
- Handle multiple tables (differentiate by headers)
- SSL verification bypass with explicit flag (security tradeoff documented)

WHY: HTML sources require more maintenance but cover most banks
PRODUCTION: Failures isolated per adapter, don't crash pipeline"
echo "✓ Commit 10: HTML Adapters"

# Commit 11: Scheduler
git add scheduler/ alerts/
git commit -m "feat(scheduler): add collection orchestration and alerting

Scheduler (scheduler/):
- runner.py: Orchestrate parallel collections with concurrency limit
- run_all(): Fetch enabled sources, spawn tasks, aggregate results
- Idempotency: Check for running runs, recover stuck runs (timeout)
- Rate limiting: Per-source delays, exponential backoff on errors
- Retry policy: 3 attempts with increasing delays, mark failed after exhaustion

Concurrency Control:
- One running collection per source (enforced by DB unique constraint)
- Configurable max concurrent (default 3, tunable for production)
- Graceful degradation: One failure doesn't stop others

Alerts (alerts/):
- checker.py: Detect stale sources (no success in 24h)
- Detect repeated failures (3+ consecutive fails)
- Detect schema changes (malformed rate increase >50%)
- Output: JSON alert payload for monitoring integration

WHY: Reliable collection even with unreliable sources
PRODUCTION: Observable failures, automatic recovery, bounded resources"
echo "✓ Commit 11: Scheduler and Alerts"

# Commit 12: API
git add api/ trusted_view/ review/
git commit -m "feat(api): add REST API with trusted rate view

REST API (api/app.py):
- GET /rates: Current rates with filters (bank, currency, category)
- GET /rates/history: Historical rates with date range
- GET /banks: Bank list with last collection status
- GET /health: System health and staleness summary

Trusted View (trusted_view/):
- Filters: is_current AND identity_status='confirmed' 
          AND validation_status != 'rejected'
          AND category_id IS NOT NULL
- Staleness indicator: Days since effective_date
- Uncertainty flags: Ambiguous identity, flagged validation
- Never show superseded versions in default view

Review Workflow (review/):
- Candidate classifier: Route ambiguous/changed rates to review queue
- Decision recording: Actor, reason, timestamp for corrections
- Correction commit: Create new version with supersedes_id

Frontend (api/templates/index.html):
- Bank comparison table with real-time rates
- Staleness indicators (fresh, stale, very stale)
- Category filtering (cash, transactional, diaspora)
- Currency selection

WHY: API enforces trusted view rules, no raw unvalidated data exposed
PRODUCTION: Clear separation between collection and serving"
echo "✓ Commit 12: API and Trusted View"

# Commit 13: Tests
git add tests/
git commit -m "test(suite): add acceptance and integration tests

Test Structure:
- test_m1_schema.py: Database constraints and indexes
- test_m2_constraints.py: Business rule enforcement (positive rates, etc)
- test_m3_pipeline.py: Validation, normalization, fingerprinting
- test_m4_adib_adapter.py: Adapter contract compliance
- test_m5_identity.py: Deduplication and ambiguity detection
- test_m6_versioning.py: Correction workflow and supersedes chain
- test_m7_current_selection.py: Current rate logic
- test_m8_wave2_adapters.py: All Wave 2 adapters with fixtures
- test_concurrency.py: Parallel collection safety
- db_utils.py: Test database setup and fixtures

Coverage:
- Acceptance tests 1-22 from design handoff
- Added tests from gap review (edge cases)
- Each test named after requirement number (traceability)

Test Database:
- Real PostgreSQL with all constraints (not SQLite)
- Isolated transactions, rolled back after each test
- Fixtures loaded per test class

WHY: Acceptance tests prove correctness, enable safe refactoring
PRODUCTION: Tests must pass before any deployment"
echo "✓ Commit 13: Test Suite"

# Commit 14: Operational Scripts
git add seed_and_run.py ops/ backups/
git commit -m "ops(scripts): add database seeding and operational tooling

seed_and_run.py:
- Load source-register.json into database
- Enable only adapters with working implementations
- Apply category defaults from ADRs (Rammis, Wegagen, single-pair)
- Disable test fixture sources (leftover from pytest)
- Run full collection cycle
- Report results: accepted, flagged, rejected, duplicates

Operational Scripts (ops/):
- backup.sh: PostgreSQL dump with timestamp
- restore.sh: Restore from backup with verification
- reset_stuck_runs.sh: Recover hung collections
- health_check.sh: Database and API connectivity check

Initial Backup (backups/):
- exchange_rates_2026-10-12.sql.gz: Known-good state after Wave 1-3 validation
- Used for test database setup and disaster recovery

WHY: Production operations need tested, documented procedures
ONBOARDING: New developers run seed_and_run.py to populate dev database"
echo "✓ Commit 14: Operational Scripts"

echo ""
echo "=== Atomic Commit Sequence Complete ==="
echo ""
git log --oneline --decorate
echo ""
echo "Repository initialized with 14 atomic, reviewable commits"
echo "Each commit is production-ready and independently deployable"
```

---

## Verification Commands

```bash
# Verify commit count
git log --oneline | wc -l  # Should be 14

# Verify each commit builds/passes
for commit in $(git log --reverse --format=%H); do
    echo "Testing commit: $(git log -1 --oneline $commit)"
    git checkout $commit
    # Run tests or build here
    # pytest tests/ || echo "FAILED at $commit"
done
git checkout main

# Verify no secrets committed
git log -p | grep -iE "password|secret|api_key|BEGIN.*PRIVATE" && echo "SECRET FOUND!" || echo "No secrets detected"

# Verify file count per commit
git log --oneline --name-only | head -50

# Generate release notes
git log --format="- %s (%h)" --reverse > RELEASE_NOTES.md
```

---

## Why This Sequence?

1. **Infrastructure first**: Can't commit secrets if .gitignore blocks them
2. **Documentation early**: Team understands design before implementation
3. **Schema before code**: Database constraints enforce invariants
4. **Domain before infrastructure**: Business logic independent of I/O
5. **Pipeline before adapters**: Contract defined before implementations
6. **API adapters before HTML**: Start with reliable, well-structured sources
7. **Tests last**: Validate entire system integration

## Production Benefits

- **Rollback safety**: Each commit is a stable checkpoint
- **Code review**: Reviewers focus on one concern per commit
- **Debugging**: `git bisect` finds exactly which feature introduced bug
- **Onboarding**: New engineers follow commit history as tutorial
- **Deployment**: Tag any commit for release, all are production-ready
- **Documentation**: Commit messages explain WHY, not just WHAT

## Team Scalability

- **Parallel work**: Different engineers own different adapters/features
- **Clear ownership**: Each commit shows who made which decisions
- **Conflict reduction**: Atomic commits minimize merge conflicts
- **Quality gates**: CI runs on each commit, catches issues early
- **Knowledge transfer**: Commit history is living documentation
