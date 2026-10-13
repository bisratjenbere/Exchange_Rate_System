#!/bin/bash
# execute_atomic_commits.sh - Create production-ready atomic commit sequence
# Ethiopian Bank Exchange Rate Intelligence System

set -e  # Exit on any error

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  Ethiopian Bank Exchange Rate Intelligence System              ║"
echo "║  Atomic Commit Initialization                                  ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check if already initialized
if [ -d ".git" ]; then
    echo "⚠️  Warning: Git repository already exists!"
    read -p "Continue and add commits? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 1
    fi
else
    git init
    echo "✓ Repository initialized"
fi

echo ""
echo "Creating 14 atomic commits..."
echo ""

# Commit 1: Infrastructure
echo "[1/14] Infrastructure and security..."
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
echo "[2/14] Project documentation..."
git add README.md CLAUDE.md docs/plan/ docs/decisions/defaults.md docs/decisions/ADR-index.md 2>/dev/null || true
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
echo "[3/14] Architecture decision records..."
git add docs/decisions/ADR-*.md docs/review/
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
echo "[4/14] Database schema..."
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
echo "[5/14] Domain model..."
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
echo "[6/14] Processing pipeline..."
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
echo "[7/14] Bank source registry..."
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
echo "[8/14] Evidence and fixtures..."
git add docs/evidence/ docs/mapping/*.md fixtures/
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
echo "[9/14] Wave 1-2 API adapters..."
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
echo "✓ Commit 9: API Adapters (Wave 1-2)"

# Commit 10: HTML Adapters
echo "[10/14] Wave 3-4 HTML adapters..."
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
echo "✓ Commit 10: HTML Adapters (Wave 3-4)"

# Commit 11: Scheduler
echo "[11/14] Scheduler and alerting..."
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
echo "[12/14] REST API and trusted view..."
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
echo "[13/14] Test suite..."
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
echo "[14/14] Operational tooling..."
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
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  ✓ Atomic Commit Sequence Complete                             ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Show summary
echo "Repository Summary:"
echo "-------------------"
git log --oneline --decorate
echo ""

# Show stats
TOTAL_COMMITS=$(git log --oneline | wc -l)
TOTAL_FILES=$(git ls-files | wc -l)
echo "Statistics:"
echo "  Total commits: $TOTAL_COMMITS"
echo "  Total files tracked: $TOTAL_FILES"
echo ""

# Verify no secrets
echo "Security Check:"
if git log -p | grep -qiE "password.*=|api_key.*=|BEGIN.*PRIVATE"; then
    echo "  ⚠️  WARNING: Potential secrets detected in commits!"
    echo "  Review with: git log -p | grep -iE 'password|api_key|secret'"
else
    echo "  ✓ No obvious secrets detected"
fi
echo ""

# Next steps
echo "Next Steps:"
echo "-----------"
echo "1. Review commits:     git log --oneline"
echo "2. Set up remote:      git remote add origin <url>"
echo "3. Push to remote:     git push -u origin main"
echo "4. Create branches:    git checkout -b develop"
echo "5. Run tests:          pytest tests/ -v"
echo "6. Seed database:      python seed_and_run.py"
echo ""
echo "Documentation:"
echo "  - System design:     cat CLAUDE.md"
echo "  - Commit plan:       cat ATOMIC_COMMIT_PLAN.md"
echo "  - Status tracking:   cat docs/plan/STATUS.md"
echo ""
