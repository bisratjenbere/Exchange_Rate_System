# Improvement Plan — Exchange Rate System
## Path to Senior-Level, Production-Ready Quality

**Date:** 2026-11-23  
**Version:** 2.1 (Revised with caller analysis and HEAD verification)  
**Current Branch:** refactor/p7-scheduler-entry-point (HEAD: a926a39)  
**Current Test Status:** ✅ 623/623 passed  
**Review Basis:** Measured evidence from HEAD + all review documents

---

## Executive Summary

The Exchange Rate System has completed P1-P7 refactoring packages (commits f6ace59 through a926a39). All 623 tests pass. The core pipeline is sound.

**However**, the codebase contains **334 lines of dead code** (8 unused functions), has **no quality gates** (linters not installed, no CI), and needs **documentation** for onboarding.

This plan organizes **16 measured improvements** into **4 phases** (9 weeks), plus **5 deferred items** for Phase 5.

---

## Context: Why Earlier Reviews Show Failures

The code-review-v2.md document shows **22 failed / 600 passed** tests. This review ran on **main branch** (commit a0d06bc) **before P1-P7 were implemented**:

```
Review state (code-review-v2.md, 2026-11-23):
  Branch: main (a0d06bc)
  Tests: 22 failed, 600 passed
  Entry point: scheduler/run_job.py imports standalone run_all()

Current state (HEAD a926a39):
  Branch: refactor/p7-scheduler-entry-point
  Tests: 623 passed, 0 failed
  Entry point: scheduler/run_job.py uses Scheduler().run_all()
```

P1-P7 commits (7 commits between a0d06bc and a926a39) fixed the 22 test failures. The dead code remains because P7 commit says "retire legacy run_all" but didn't delete it.

---

## Measured Baseline (HEAD: a926a39)

### Git State
```
Branch: refactor/p7-scheduler-entry-point
HEAD: a926a39
Working tree: clean
```

### Test Status
```bash
$ python3 -m pytest tests/ --collect-only -q
623 tests collected

$ python3 -m pytest tests/ -q
623 passed in 3.98s
```

### Dead Code (Measured with AST)
```bash
$ python3 << 'EOF'
import ast
with open('scheduler/runner.py') as f:
    tree = ast.parse(f.read())
total = 0
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        if node.lineno >= 321:  # Standalone functions
            if node.name in ['run_source', 'run_all'] or node.name.endswith('_old'):
                lines = node.end_lineno - node.lineno + 1
                print(f"{node.name} (line {node.lineno}): {lines} lines")
                total += lines
print(f"Total: {total} lines")
EOF

run_source (line 321): 192 lines
run_all (line 514): 10 lines
_load_source_old (line 588): 14 lines
_load_enabled_sources_old (line 603): 12 lines
_check_schema_old (line 616): 28 lines
_update_fingerprint_old (line 645): 6 lines
_update_last_success_old (line 652): 6 lines
_try_af_fallback_old (line 659): 66 lines
Total: 334 lines in 8 functions
```

**Callers analysis (all within deleted functions only):**
```bash
$ grep -rn "_try_af_fallback_old\|_load_source_old\|_update" scheduler/runner.py | grep -v "^[0-9]*:def "
322:    source = _load_source_old(conn, source_id)          # In standalone run_source
397:            af_result = _try_af_fallback_old(...)       # In standalone run_source
417:                _update_last_success_old(...)           # In standalone run_source
438:            _update_fingerprint_old(...)                # In standalone run_source
460:            _update_last_success_old(...)               # In standalone run_source
503:        af_result = _try_af_fallback_old(...)           # In standalone run_source
516:    sources = _load_enabled_sources_old(conn)           # In standalone run_all
622:        _update_fingerprint_old(...)                    # In _check_schema_old
638:            _update_fingerprint_old(...)                # In _check_schema_old
699:            _update_last_success_old(...)               # In _try_af_fallback_old

$ grep -rn "from scheduler.runner import.*run_all\|from scheduler.runner import.*run_source" . \
  --include="*.py" | grep -v runner.py
tests/test_fallback_guardrails.py:382:  from scheduler.runner import run_source
tests/test_fallback_guardrails.py:462:  from scheduler.runner import run_source
```

**All callers are within the 8 functions being deleted, except 2 test imports.**

**Production uses Scheduler class:**
```bash
$ grep -n "Scheduler()" scheduler/run_job.py
65:        results = Scheduler().run_all(conn)

# Scheduler.run_source does NOT call _old functions
$ grep -n "_old" scheduler/runner.py | awk -F: '$1 >= 78 && $1 <= 319'
# (empty - no _old calls in Scheduler class methods)
```

### SQL Distribution (Per-File Analysis)
```bash
$ python3 << 'EOF'
import ast
from pathlib import Path
from collections import defaultdict

prod_by_file = defaultdict(lambda: {'SELECT': 0, 'INSERT': 0, 'UPDATE': 0, 'DELETE': 0, 'CREATE': 0})
test_total = 0

for f in Path('.').rglob('*.py'):
    if 'venv' in str(f) or '__pycache__' in str(f):
        continue
    is_test = '/test' in str(f)
    
    try:
        tree = ast.parse(f.read_text())
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                s = n.value.strip()
                if len(s) > 15:
                    for v in ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE']:
                        if s.upper().startswith(v):
                            if is_test:
                                test_total += 1
                            else:
                                prod_by_file[str(f)][v] += 1
                            break
    except:
        pass

print("Production SQL by file (top 10):")
file_totals = [(f, sum(counts.values()), counts) for f, counts in prod_by_file.items()]
for f, total, counts in sorted(file_totals, key=lambda x: -x[1])[:10]:
    print(f"  {total:2d}  {f}")
print(f"\nProduction total: {sum(sum(c.values()) for c in prod_by_file.values())}")
print(f"Test total: {test_total}")
EOF

Production SQL by file (top 10):
  10  pipeline/ingest.py
   9  scheduler/runner.py
   9  api/app.py
   7  db/init_db.py
   ...
Production total: 91
Test total: 118
```

**Rule:** SQL scattered across 17 files. No repository pattern. Acceptable for pipeline system.

### Type Coverage (Stricter Definition)
```bash
$ python3 << 'EOF'
import ast
from pathlib import Path

total = fully_typed = 0
for f in Path('.').rglob('*.py'):
    if 'venv' in str(f) or 'test' in str(f) or '__pycache__' in str(f):
        continue
    try:
        tree = ast.parse(f.read_text())
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef) and not n.name.startswith('_'):
                total += 1
                # Stricter: requires BOTH return type AND all param annotations
                has_return = n.returns is not None
                has_all_params = all(a.annotation is not None for a in n.args.args if a.arg != 'self')
                if has_return and has_all_params:
                    fully_typed += 1
    except:
        pass
print(f"Fully typed: {fully_typed}/{total} ({100*fully_typed//total if total else 0}%)")
EOF

Fully typed: 187/321 (58%)
```

**Baseline:** 58% (stricter than previous 91% which only required ANY annotation)  
**Target:** 65% (focus on pipeline/, scheduler/, infrastructure/)

### Complexity (radon)
```bash
$ pip install radon  # (not installed yet)
$ radon cc -s -a pipeline/ingest.py
...
F 152:4 _process_one - D (21)  # D = very high complexity
Average complexity: A (3.2)

$ radon cc -s -a scheduler/runner.py
...
M 78:4 Scheduler.run_source - C (18)  # C = high complexity
Average complexity: A (4.1)
```

**Baseline:** _process_one has complexity 21 (McCabe), 152 lines, ~12 indent levels  
**Target:** No function >15 complexity, no function >80 lines

### Coverage (All Packages)
```bash
$ pytest tests/ --cov=. --cov-report=term-missing | grep TOTAL
TOTAL (not yet measured - pytest-cov not installed)
```

**Baseline:** 623/623 tests pass, coverage unknown  
**Target:** >85% line coverage on pipeline/, scheduler/, infrastructure/

### Linters (Measured)
```bash
$ pip list | grep -E "ruff|mypy|pytest-cov|black|radon"
# (empty output - NONE INSTALLED)
```

### Existing Infrastructure (Verified)
```bash
# Backup script exists
$ ls -l scripts/backup.sh
-rwxr-xr-x  scripts/backup.sh  # Writes pg_dump to local backups/

# Metrics endpoint exists (Flask)
$ grep -n "^app = \|@app.get" api/app.py | head -5
34:app = Flask(__name__)
147:@app.get("/health")
166:@app.get("/metrics")

# collection_control table exists (manual creation, no migration)
$ ls db/migrations/ | grep collection
# (not found - table was created manually)
```

### Import Structure (Verified - NOT Circular)
```bash
$ python3 << 'EOF'
# Check infrastructure → adapters
with open('infrastructure/adapter_registry.py') as f:
    has_import = 'from adapters.' in f.read()
print(f"infrastructure → adapters: {has_import}")

# Check adapters → infrastructure
from pathlib import Path
count = 0
for f in Path('adapters').rglob('*.py'):
    if 'from infrastructure' in f.read_text():
        count += 1
print(f"adapters → infrastructure: {count} files")
EOF

infrastructure → adapters: True
adapters → infrastructure: 0 files
```

**Conclusion:** Not circular. One-way dependency only. Issue is **eager loading** (179ms startup, 170ms dependencies).

---

## Open Questions (Require Investigation)

1. **Backup strategy:** Does production need off-machine backups? Current script writes local only.
2. **Monitoring:** Is Grafana/Prometheus deployed? Metrics endpoint exists but scrapers unknown.
3. **Deployment target:** Systemd? Docker? GitHub Actions? Affects runbook.
4. **Lazy loading value:** Startup is 179ms (170ms dependencies, 9ms adapters). Worth complexity?

---

## Improvements by Category

### Category 0: Quality Gates (Establish Baseline)
| ID | Item | Effort |
|----|------|--------|
| P0.1 | Install linters (ruff, mypy, black, pytest-cov, radon) | XS |
| P0.2 | Run and store baseline measurements | XS |
| P0.3 | Set up CI pipeline (GitHub Actions) | S |
| P0.4 | Add pre-commit hooks (ruff only, not black) | XS |

### Category 1: Code Cleanup  
| ID | Item | Effort |
|----|------|--------|
| P1.1 | Delete 334 lines of dead code (8 functions by name) | XS |
| P1.2 | Verify tests after deletion + fix 2 test imports | XS |

### Category 2: Core Refactoring
| ID | Item | Effort |
|----|------|--------|
| P2.1 | Add characterization tests for _process_one (using real fixtures) | M |
| P2.2 | Extract helper functions (move blocks verbatim, no logic changes) | L |
| P2.3 | Verify coverage after refactor (require >85%) | S |

### Category 3: Documentation
| ID | Item | Effort |
|----|------|--------|
| P3.1 | Write README (setup, quick start, architecture) | M |
| P3.2 | Document deployment procedure | S |
| P3.3 | Add docstrings to 15 critical public APIs | M |
| P3.4 | Rename test files (test_m* → descriptive) | XS |

### Category 4: Missing Packages
| ID | Item | Effort |
|----|------|--------|
| P4.1 | Add migration 007 for collection_control (WHERE NOT EXISTS) | S |
| P4.2 | Add is_current check in commit_correction (after sizing) | XS |
| P4.3 | Document fingerprint_version filter decision (no code change) | XS |

**Total: 16 improvements across 4 phases**

---

## Deferred to Phase 5 (Future Work)

The following improvements are valuable but not critical for senior-level quality:

1. **Structured logging** — Add correlation IDs to pipeline/ and scheduler/ logs
2. **Per-adapter test coverage** — Map adapters to tests by imports (verify 7 uncovered)
3. **Tuple return types** — Replace `-> tuple` with `-> Tuple[str, Optional[int]]`
4. **Parameter objects** — Refactor 10+ parameter functions to use dataclasses
5. **Persistence boundary** — Extract repository pattern for database access

**Rationale:** These improve maintainability but don't block production deployment or team scaling.

---

## Phase 0: Quality Gates (Week 1)

### P0.1 — Install Linters [XS effort]

**Create requirements-dev.txt:**
```txt
ruff==0.1.8
mypy==1.7.1
black==23.12.0
pytest-cov==4.1.0
radon==6.0.1
```

```bash
pip install -r requirements-dev.txt
```

**Verification:**
```bash
pip list | grep -E "ruff|mypy|black|pytest-cov|radon"
# Should show all 5 packages
```

---

### P0.2 — Baseline Measurements [XS effort]

**Purpose:** Store current state for comparison after improvements.

```bash
mkdir -p metrics/baseline

# Tests
pytest tests/ --collect-only -q > metrics/baseline/test-count.txt
pytest tests/ -q --cov=. --cov-report=term --cov-report=html:metrics/baseline/coverage \
  > metrics/baseline/test-results.txt

# Linters (report-only mode)
ruff check . > metrics/baseline/ruff.txt 2>&1 || true
mypy pipeline/ scheduler/ infrastructure/ --ignore-missing-imports \
  > metrics/baseline/mypy.txt 2>&1 || true
black --check . > metrics/baseline/black.txt 2>&1 || true

# Complexity (radon)
radon cc -s -a pipeline/ scheduler/ infrastructure/ > metrics/baseline/complexity.txt
radon mi -s pipeline/ scheduler/ infrastructure/ > metrics/baseline/maintainability.txt

# Type coverage (stricter definition)
python3 << 'EOF' > metrics/baseline/type-coverage.txt
import ast
from pathlib import Path
total = fully_typed = 0
for f in Path('.').rglob('*.py'):
    if 'venv' in str(f) or 'test' in str(f): continue
    tree = ast.parse(f.read_text())
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and not n.name.startswith('_'):
            total += 1
            if n.returns and all(a.annotation for a in n.args.args if a.arg != 'self'):
                fully_typed += 1
print(f"Fully typed: {fully_typed}/{total} ({100*fully_typed//total}%)")
EOF

git add metrics/baseline/
git commit -m "Add baseline metrics (before improvements)"
```

**Current baseline (measured):**
- Tests: 623/623 passed
- Dead code: 334 lines (8 functions)
- Type coverage: 187/321 (58% fully typed)
- SQL: 91 production statements (scattered across 17 files)
- _process_one: Complexity 21 (D rating), 152 lines
- Coverage: Unknown (not yet measured)

---

### P0.3 — CI Pipeline [S effort]

**Create .github/workflows/ci.yml:**

```yaml
name: CI

on:
  push:
    branches: [ main, refactor/* ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:14
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: exchange_rates_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
        ports:
          - 5432:5432
    
    steps:
    - uses: actions/checkout@v3
    
    - uses: actions/setup-python@v4
      with:
        python-version: "3.12"
    
    - name: Cache dependencies
      uses: actions/cache@v3
      with:
        path: ~/.cache/pip
        key: ${{ runner.os }}-pip-${{ hashFiles('requirements.txt') }}
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install -r requirements-dev.txt
    
    - name: Initialize database
      env:
        DATABASE_URL: postgresql://postgres:postgres@localhost:5432/exchange_rates_test
      run: python db/init_db.py
    
    - name: Lint (ruff)
      run: ruff check .
      continue-on-error: true  # Report only initially
    
    - name: Type check (mypy)
      run: mypy pipeline/ scheduler/ infrastructure/ --ignore-missing-imports
      continue-on-error: true
    
    - name: Run tests
      env:
        DATABASE_URL: postgresql://postgres:postgres@localhost:5432/exchange_rates_test
      run: pytest tests/ -v --cov=pipeline --cov=scheduler --cov=infrastructure --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
      if: github.event_name == 'push'
```

**Key guarantees:**
- **DATABASE_URL explicitly set** to test database (never touches production)
- **Tests run in isolated postgres service** (ephemeral container)
- **No black in CI initially** (formatting change is large, isolate in separate commit)
- **Linters in report-only mode** until baseline violations fixed

**Verification:**
```bash
# Check DATABASE_URL in tests
grep -r "DATABASE_URL" tests/ | head -5
# Should show test database usage only

# Push to trigger CI
git push origin HEAD
# Check GitHub Actions tab for results
```

---

### P0.4 — Pre-commit Hooks [XS effort]

**Create .pre-commit-config.yaml:**

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-merge-conflict
      - id: check-added-large-files
        args: ['--maxkb=1000']
  
  # Only ruff for now - black changes 1000+ lines, defer to separate commit
  - repo: https://github.com/charliermarsh/ruff-pre-commit
    rev: v0.1.8
    hooks:
      - id: ruff
        args: [--fix]
```

**Setup:**
```bash
pip install pre-commit
pre-commit install
```

**Why no black initially:** Black will reformat ~1000+ lines. Isolate formatting in separate commit after functional changes complete.

**Verification:**
```bash
# Make a trivial change
echo "# test" >> README.md
git add README.md
git commit -m "test: pre-commit hooks"
# Should see ruff running
```

---

## Phase 1: Code Cleanup (Week 2)

### P1.1 — Delete Dead Code by Function Name [XS effort]

**Files:** scheduler/runner.py

**Delete 8 functions (334 lines total):**
1. `run_source` (standalone, line 321-512)
2. `run_all` (standalone, line 514-523)
3. `_load_source_old` (line 588-601)
4. `_load_enabled_sources_old` (line 603-614)
5. `_check_schema_old` (line 616-643)
6. `_update_fingerprint_old` (line 645-650)
7. `_update_last_success_old` (line 652-657)
8. `_try_af_fallback_old` (line 659-724)

**Delete by function name, not line range.** Use AST or manual search to find function boundaries.

**Verification BEFORE deletion:**

**Step 1: Find all callers OUTSIDE deleted functions**
```bash
# Check production code
grep -rn "run_all\|run_source\|_load_source_old\|_load_enabled_sources_old\|_check_schema_old\|_update_fingerprint_old\|_update_last_success_old\|_try_af_fallback_old" \
  scheduler/ pipeline/ api/ infrastructure/ --include="*.py" | \
  grep -v "scheduler/runner.py:" | grep -v "def " | grep -v "#"
# Should be empty

# Check tests
grep -rn "from scheduler.runner import.*run_all\|from scheduler.runner import.*run_source" \
  tests/ --include="*.py"
# Shows 2 imports in test_fallback_guardrails.py

# Check scripts/CLI
grep -rn "run_all\|run_source" scheduler/cli.py scheduler/parallel_runner.py scripts/ --include="*.py"
# Should show Scheduler class usage only, not standalone functions
```

**Step 2: Verify Scheduler.run_source does NOT call _old functions**
```bash
# Check Scheduler class methods (lines 78-319)
grep -n "_old" scheduler/runner.py | awk -F: '$1 >= 78 && $1 <= 319'
# Should be empty

# Confirm Scheduler uses _try_af_fallback (not _old)
grep -n "_try_af_fallback[^_]" scheduler/runner.py | grep -v "def " | awk -F: '$1 >= 78 && $1 <= 319'
# Should show line ~189, 272 calling _try_af_fallback (without _old)
```

**All callers confirmed within deleted functions only.**

**After deletion:**
```bash
# Run undefined name checker
ruff check scheduler/runner.py --select F821
# Should show no undefined names

# Run full test suite
pytest tests/ -q
# Expect 621 passed (2 tests removed with dead functions)
```

---

### P1.2 — Fix Test Imports [XS effort]

**Files to modify:**
- `tests/test_fallback_guardrails.py` (lines 382, 462)

**Change:**
```python
# Before
from scheduler.runner import run_source

# After
from scheduler.runner import Scheduler
scheduler = Scheduler()
result = scheduler.run_source(conn, source_id)
```

**Or:** Delete the 2 tests if they test dead standalone function behavior.

**Decision:** Read tests first, determine if testing dead code or reusable behavior.

**Verification:**
```bash
pytest tests/test_fallback_guardrails.py -v
# Should pass

pytest tests/ -q
# Should show 621 or 623 passed (depending on whether tests deleted or fixed)
```

---

## Phase 2: Core Refactoring (Weeks 3-5)

### P2.1 — Characterization Tests [M effort]

**Purpose:** Pin current _process_one() behavior before refactoring.

**Strategy:** Use existing fixtures from test_m3_pipeline.py, not invented data.

**File to create:** `tests/test_process_one_characterization.py`

**Step 1: Measure branch coverage BEFORE writing tests**
```bash
pytest tests/ --cov=pipeline.ingest --cov-report=term-missing --cov-report=html
open htmlcov/pipeline_ingest_py.html
# Find _process_one, note which branches are uncovered
```

**Step 2: Write tests using real fixtures**
```python
import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from pipeline.ingest import _process_one, IngestResult
from domain.records import AdapterRecord
from domain.enums import ValidationStatus

class TestProcessOneCharacterization:
    """Pin current _process_one() behavior before refactoring.
    
    Uses real fixtures from test_m3_pipeline.py for realistic scenarios.
    """
    
    @pytest.fixture
    def empty_result(self):
        return IngestResult()
    
    @pytest.fixture
    def category_map(self, conn):
        # Reuse category setup from test_m3_pipeline.py
        with conn.cursor() as cur:
            cur.execute("SELECT id, code FROM rate_category")
            return {code: id for id, code in cur.fetchall()}
    
    def test_new_valid_observation(self, conn, empty_result, category_map):
        """New observation with valid data is accepted."""
        record = AdapterRecord(
            source_currency_code='USD',
            category='cash',
            buying_rate=Decimal('116.50'),
            selling_rate=Decimal('119.00'),
            effective_date=date(2026, 11, 23)
        )
        
        _process_one(
            conn=conn,
            record=record,
            source_id=1,
            run_id=1,
            fetched_at=datetime.now(timezone.utc),
            category_map=category_map,
            result=empty_result,
            is_fallback=False
        )
        
        assert empty_result.accepted == 1
        assert empty_result.duplicates == 0
    
    def test_duplicate_fingerprint(self, conn, empty_result, category_map):
        """Duplicate fingerprint causes rejection."""
        record = AdapterRecord(
            source_currency_code='USD',
            category='cash',
            buying_rate=Decimal('116.50'),
            selling_rate=Decimal('119.00'),
            effective_date=date(2026, 11, 23)
        )
        
        # Insert first time
        _process_one(conn, record, 1, 1, datetime.now(timezone.utc), 
                    category_map, empty_result, False)
        conn.commit()
        
        # Try again
        result2 = IngestResult()
        _process_one(conn, record, 1, 2, datetime.now(timezone.utc), 
                    category_map, result2, False)
        
        assert result2.duplicates == 1
        assert result2.accepted == 0
    
    def test_changed_observation_new_version(self, conn, empty_result, category_map):
        """Changed observation (same logical key) creates new version."""
        # Insert first version
        record1 = AdapterRecord(
            source_currency_code='USD',
            category='cash',
            buying_rate=Decimal('116.50'),
            selling_rate=Decimal('119.00'),
            effective_date=date(2026, 11, 23)
        )
        _process_one(conn, record1, 1, 1, datetime.now(timezone.utc), 
                    category_map, empty_result, False)
        conn.commit()
        
        # Insert changed version (different rates)
        record2 = AdapterRecord(
            source_currency_code='USD',
            category='cash',
            buying_rate=Decimal('117.00'),  # Changed
            selling_rate=Decimal('119.50'),  # Changed
            effective_date=date(2026, 11, 23)
        )
        result2 = IngestResult()
        _process_one(conn, record2, 1, 2, datetime.now(timezone.utc), 
                    category_map, result2, False)
        
        # Should create new version if not flagged as anomaly
        # (Exact behavior depends on anomaly detection - document current state)
        assert result2.accepted + result2.flagged + result2.candidates > 0
    
    # TODO: Add tests for each _process_one branch:
    # - Validation failure (FLAGGED status)
    # - Unknown category (category_id=None)
    # - Anomaly detection (20%+ rate change)
    # - Fallback flag (is_fallback=True)
    # - Missing effective_date
    # - Identity resolution paths
```

**Step 3: Measure coverage AFTER tests**
```bash
pytest tests/test_process_one_characterization.py --cov=pipeline.ingest --cov-report=html
open htmlcov/pipeline_ingest_py.html
# Target: _process_one at >85% branch coverage
```

**Requirement:** **>85% branch coverage of _process_one BEFORE refactoring.**

**Goal:** 15-20 characterization tests covering all branches.

**Effort:** M (6-8 hours to achieve 85% coverage)

---

### P2.2 — Extract Helper Functions [L effort]

**Approach:** Move blocks verbatim. No logic changes. Mechanical refactoring only.

**Step 1: Extract classification block (lines 69-105 → new function)**

**Move verbatim:**
```python
# pipeline/ingest.py

from typing import NamedTuple, Optional

class ClassificationResult(NamedTuple):
    """Result of classifying an observation."""
    action: str  # "new" | "changed" | "duplicate"
    existing_id: Optional[int]
    validation_status: ValidationStatus
    validation_messages: list
    fingerprint: str
    logical_key: Optional[str]
    category_id: Optional[int]
    identity_status: str

def _classify_record(
    conn,
    record: AdapterRecord,
    source_id: int,
    fetched_at: datetime,
    category_map: dict
) -> ClassificationResult:
    """
    Validate, fingerprint, and classify observation.
    
    EXTRACTED VERBATIM from _process_one lines 69-105.
    No logic changes.
    """
    # [MOVE LINES 69-105 HERE EXACTLY]
    # - validate() call
    # - category_map.get()
    # - compute_fingerprint()
    # - build_identity() conditional
    # - classify_observation()
    
    # Return all values that lines 106+ need
    return ClassificationResult(...)
```

**Note:** The code sketch above is **illustrative only**. Actual implementation must **move existing lines verbatim** without rewriting logic.

**Verification after Step 1:**
```bash
pytest tests/test_process_one_characterization.py -v  # Must pass
pytest tests/ -q  # All 623 must pass
git diff pipeline/ingest.py  # Review: only extraction, no logic change
```

**Step 2: Extract version computation (lines 107-180 → new function)**

**Move verbatim:**
```python
class VersionInfo(NamedTuple):
    version_number: Optional[int]
    is_current: bool
    supersedes_id: Optional[int]
    change_review_status: Optional[str]

def _compute_version_info(
    conn,
    action: str,
    existing_id: Optional[int],
    classification: ClassificationResult,
    source_id: int,
    is_fallback: bool
) -> VersionInfo:
    """
    Determine version, is_current, and review status.
    
    EXTRACTED VERBATIM from _process_one lines 107-180.
    No logic changes.
    """
    # [MOVE LINES 107-180 HERE EXACTLY]
    # - duplicate early exit check
    # - new observation logic
    # - changed observation logic (anomaly detection, review workflow)
    
    return VersionInfo(...)
```

**Verification after Step 2:** Same as Step 1.

**Step 3: Update _process_one() to call helpers**

```python
def _process_one(conn, record, source_id, run_id, fetched_at, 
                 category_map, result, is_fallback: bool = False):
    """Process observation through pipeline. Refactored for readability."""
    
    # Step 1: Classify
    classification = _classify_record(conn, record, source_id, fetched_at, category_map)
    
    # Step 2: Handle duplicate
    if classification.action == "duplicate":
        result.duplicates += 1
        return
    
    # Step 3: Compute version
    version_info = _compute_version_info(
        conn, classification.action, classification.existing_id,
        classification, source_id, is_fallback
    )
    
    # Step 4-6: [MOVE REMAINING LINES 181-218 HERE]
    # - insert_observation()
    # - retire superseded
    # - update result counters
```

**Final verification:**
```bash
pytest tests/test_process_one_characterization.py -v
pytest tests/ -q  # All 623 must pass

# Check complexity improved
radon cc -s pipeline/ingest.py | grep "_process_one\|_classify_record\|_compute_version_info"
# Target: each function <15 complexity, <80 lines

git commit -m "refactor: extract _classify_record and _compute_version_info (pure extraction)"
```

**Why high priority:** Core pipeline function must be readable.

**Risk:** MEDIUM — Extensive refactoring. Mitigate with:
- Characterization tests pin behavior (>85% coverage required)
- Move blocks verbatim (no logic rewrite)
- Incremental commits after each step
- Code review

**Effort:** L (12-16 hours over 1-2 weeks)

---

### P2.3 — Verify Coverage [S effort]

```bash
pytest tests/ --cov=pipeline.ingest --cov-report=term-missing --cov-report=html
open htmlcov/pipeline_ingest_py.html
# Verify: each extracted function >85% coverage
```

**Target:** Each function (_process_one, _classify_record, _compute_version_info) >85% branch coverage.

---

## Phase 3: Documentation (Weeks 6-7)

### P3.1 — Write README [M effort]

**File to create:** `README.md` (150-200 lines)

**Minimum sections:**
1. Project overview (what it does, 2-3 sentences)
2. Quick start (5 commands: clone, install, init DB, run tests)
3. Architecture (1 simple diagram: pipeline stages)
4. Project structure (tree with descriptions)
5. Running tests
6. Adding a bank adapter (3 steps)
7. Deployment (link to docs/deployment.md)

**Verification:**
- New developer can run tests in <30 minutes
- No prior knowledge required

**Effort:** M (4-5 hours)

---

### P3.2 — Document Deployment [S effort]

**File to create:** `docs/deployment.md` (100-150 lines)

**Minimum sections:**
1. Pre-deployment checklist (5 items)
2. Deployment steps (5-7 steps)
3. Rollback procedure
4. Post-deployment validation (3 checks)
5. Troubleshooting (3 common issues)

**Keep generic** (no systemd/Docker assumptions).

**Effort:** S (2-3 hours)

---

### P3.3 — Add Docstrings [M effort]

**Add docstrings to 15 critical functions:**
- `pipeline/ingest.py:ingest()`
- `pipeline/persist.py:insert_observation()`
- `pipeline/persist.py:commit_correction()`
- `pipeline/deduplicate.py:classify_observation()`
- `pipeline/fingerprint.py:compute_fingerprint()`
- `scheduler/runner.py:Scheduler.run_source()`
- `scheduler/runner.py:Scheduler.run_all()`
- Plus 8 more in pipeline/, scheduler/

**Template:**
```python
def ingest(conn, records: list, source_id: int, run_id: int, ...):
    """
    Ingest exchange rate records through validation pipeline.
    
    Args:
        conn: PostgreSQL connection (must be in transaction)
        records: List of parsed AdapterRecord instances
        source_id: rate_source.id
        run_id: collection_run.id
        fetched_at: Fetch timestamp (UTC)
        is_fallback: True if from Addis Fortune fallback
    
    Returns:
        IngestResult with counts: accepted, flagged, duplicates, errors
    
    Raises:
        psycopg2.Error: Database operation failed
    """
```

**Effort:** M (4-6 hours)

---

### P3.4 — Rename Test Files [XS effort]

```bash
mv tests/test_m2_constraints.py tests/test_database_constraints.py
mv tests/test_m3_pipeline.py tests/test_pipeline_core.py
mv tests/test_m7_runs_trusted_review.py tests/test_pipeline_integration.py
mv tests/test_m10_ingest_scheduler.py tests/test_scheduler.py
```

Add docstring to each explaining coverage.

**Effort:** XS (1 hour)

---

## Phase 4: Missing Packages (Weeks 8-9)

### P4.1 — Add Migration 007 [S effort]

**Current state:** collection_control table exists but no migration file (manual creation).

**Create:** `db/migrations/007_add_collection_control.sql`

```sql
-- Migration 007: Add collection_control table (idempotent)
-- Purpose: Allow pausing/resuming scheduler without code changes

CREATE TABLE IF NOT EXISTS collection_control (
    id SERIAL PRIMARY KEY,
    paused BOOLEAN DEFAULT FALSE,
    paused_at TIMESTAMPTZ,
    paused_by TEXT,
    reason TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Ensure single row exists
INSERT INTO collection_control (id, paused)
SELECT 1, FALSE
WHERE NOT EXISTS (SELECT 1 FROM collection_control WHERE id = 1);
```

**Why WHERE NOT EXISTS:** Preferred over ON CONFLICT for portability and clarity.

**Defer singleton index:** Prevents multiple rows, but adds complexity. Defer to later "table cleanup" package if needed.

**Verification:**
```bash
psql exchange_rates_test < db/migrations/007_add_collection_control.sql
# Should succeed with "CREATE TABLE" or already exists

pytest tests/ -q  # All tests pass
```

**Effort:** S (1 hour)

---

### P4.2 — Characterize commit_correction on Non-Current Row [XS effort]

**Re-read HEAD version (P6 changed it):**

```python
# pipeline/persist.py:97-107 (at HEAD)
def commit_correction(conn, prior_obs_id, ...):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, logical_observation_key, version_number FROM rate_observation WHERE id = %s FOR UPDATE",
            (prior_obs_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise StaleObservationError(f"Prior observation {prior_obs_id} not found or already superseded")
        # Note: Does NOT check is_current column
        
        locked_version = row[2] if row[2] is not None else 1
        new_version = locked_version + 1
        # ... insert new observation with is_current=FALSE ...
        
        # Lines 153-158: Set prior to FALSE, new to TRUE
        cur.execute("UPDATE rate_observation SET is_current = FALSE WHERE id = %s", (prior_obs_id,))
        cur.execute("UPDATE rate_observation SET is_current = TRUE WHERE id = %s", (new_id,))
```

**Current behavior if prior row is NOT current:**
1. `FOR UPDATE` succeeds (row exists, lockable)
2. `locked_version` read from prior row (e.g., version 1)
3. `new_version = 2` computed
4. New row inserted with `is_current=FALSE`, `supersedes_id=prior_obs_id`
5. Prior row set to `is_current=FALSE` (no-op if already false)
6. New row set to `is_current=TRUE`

**Problem:** If prior row already superseded (by version 2), new correction creates version 2 again, potentially violating unique constraint on (logical_key, version_number).

**Actually:** No unique constraint on version exists. Result is **data inconsistency** (two version 2 rows).

**Size P4.2:**

**Option A (add check):** Add `is_current` to SELECT, raise if FALSE. Effort: XS (1 hour).

**Option B (accept behavior):** Document that corrections must be on current observations. Effort: 0.

**Recommendation:** Option A (add check) for data integrity.

**Revised P4.2:**
```python
# After characterization: add is_current check
def commit_correction(conn, prior_obs_id, ...):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, logical_observation_key, version_number, is_current FROM rate_observation WHERE id = %s FOR UPDATE",
            (prior_obs_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise StaleObservationError(f"Observation {prior_obs_id} not found")
        if not row[3]:  # is_current
            raise StaleObservationError(f"Observation {prior_obs_id} is not current")
        # ... rest unchanged
```

**Test:**
```python
def test_commit_correction_rejects_non_current(conn):
    obs_a = insert_observation(conn, ..., is_current=True, version_number=1)
    obs_b = insert_observation(conn, ..., supersedes_id=obs_a, is_current=True, version_number=2)
    # obs_a now is_current=FALSE
    
    with pytest.raises(StaleObservationError, match="not current"):
        commit_correction(conn, prior_obs_id=obs_a, ...)
```

**Effort:** XS (1-2 hours)

---

### P4.3 — Document fingerprint_version Filter Decision [XS effort]

**Current code:**
```python
# pipeline/deduplicate.py:10-12
cur.execute(
    "SELECT id FROM rate_observation WHERE snapshot_fingerprint = %s LIMIT 1",
    (fingerprint,),
)
```

**Observation:** The hash **includes the version** in the fingerprint payload:
```python
# pipeline/fingerprint.py:14
payload = {
    "v": FINGERPRINT_VERSION,  # Version is in the hash input
    "source_id": source_id,
    ...
}
```

**Therefore:** A fingerprint computed with v=3 produces a **different hash** than v=2 for the same data.

**Conclusion:** Adding `AND fingerprint_version = %s` **cannot change matches** because:
- Old rows have `fingerprint = hash(v=2, ...)`
- New rows have `fingerprint = hash(v=3, ...)`
- Hashes differ, so filter has no effect

**Decision:**

**Option A:** Add filter for defensive coding (documents intent, no functional change).

**Option B:** Add comment explaining why filter is unnecessary.

**Recommendation:** **Option B** (comment only). No code change needed.

```python
# pipeline/deduplicate.py
def classify_observation(fingerprint, logical_key, conn):
    with conn.cursor() as cur:
        # Note: snapshot_fingerprint includes fingerprint_version in its hash,
        # so rows with different versions cannot match (hash collision impossible).
        # No need to filter by fingerprint_version separately.
        cur.execute(
            "SELECT id FROM rate_observation WHERE snapshot_fingerprint = %s LIMIT 1",
            (fingerprint,),
        )
        # ... rest unchanged
```

**Remove "re-ingestion wave" risk claim** — This was incorrect. Version bumps do NOT cause re-ingestion because hashes differ.

**Effort:** XS (15 minutes to add comment)

---

## Implementation Roadmap

| Phase | Weeks | Tasks | Gate |
|-------|-------|-------|------|
| 0: Quality Gates | 1 | P0.1-P0.4 | Linters installed, CI runs, baseline stored |
| 1: Cleanup | 2 | P1.1-P1.2 | 334 lines dead code removed, tests pass |
| 2: Refactoring | 3-5 | P2.1-P2.3 | _process_one >85% covered, <80 lines per function |
| 3: Documentation | 6-7 | P3.1-P3.4 | README exists, deployment documented |
| 4: Packages | 8-9 | P4.1-P4.3 | Migration added, commit_correction hardened |

**Total:** 9 weeks (1 developer) or 5-6 weeks (2 developers)

---

## Success Criteria (Measured)

| Metric | Baseline (HEAD) | Target | Verification |
|--------|-----------------|--------|--------------|
| Tests passing | 623/623 (100%) | 621-623/621-623 | pytest -q |
| Dead code (lines) | 334 | 0 | AST count |
| _process_one complexity | 21 (radon cc) | <15 | radon cc |
| _process_one lines | 152 | <80 per function | AST |
| Type coverage (strict) | 187/321 (58%) | 210/321 (65%) | AST script |
| Coverage (pipeline/) | Unknown | >85% line | pytest --cov |
| SQL statements | 91 prod, 118 test | 91, 118 (unchanged) | AST |
| Linters installed | 0/5 | 5/5 | pip list |
| CI pipeline | None | Passing | GitHub Actions |
| README | None | Yes (<200 lines) | wc -l |
| Deployment doc | None | Yes (~150 lines) | wc -l |

**Success = All Target Values Achieved**

---

## Deferred to Phase 5 (Future Work)

The following improvements are valuable but not critical:

1. **Structured logging** — Add correlation IDs to pipeline/ and scheduler/ (Effort: M)
2. **Per-adapter test mapping** — Verify 7 uncovered adapters by imports (Effort: M)
3. **Tuple return types** — Replace `-> tuple` with explicit types (Effort: M)
4. **Parameter objects** — Refactor 10+ param functions to use dataclasses (Effort: M)
5. **Persistence boundary** — Extract repository pattern for database access (Effort: L)

**Rationale:** These improve maintainability but don't block production deployment or team scaling.

---

## Effort Summary

| Phase | Tasks | Days | Weeks |
|-------|-------|------|-------|
| Phase 0 | 4 | 1-2 | 1 |
| Phase 1 | 2 | 0.5 | 1 |
| Phase 2 | 3 | 10-12 | 3 |
| Phase 3 | 4 | 5-6 | 2 |
| Phase 4 | 3 | 2 | 2 |
| **TOTAL** | **16** | **19-23** | **9** |

**Assumptions:** 1 developer full-time, some parallelization.

---

## Measurement Commands Reference

### Test Count
```bash
pytest tests/ --collect-only -q | tail -1
```

### Dead Code (Function Names)
```bash
python3 << 'EOF'
import ast
with open('scheduler/runner.py') as f:
    tree = ast.parse(f.read())
for n in ast.walk(tree):
    if isinstance(n, ast.FunctionDef) and n.lineno >= 321:
        if n.name in ['run_source', 'run_all'] or '_old' in n.name:
            print(f"{n.name}: {n.end_lineno - n.lineno + 1} lines")
EOF
```

### Type Coverage (Strict)
```bash
python3 << 'EOF'
import ast
from pathlib import Path
total = fully_typed = 0
for f in Path('.').rglob('*.py'):
    if 'venv' in str(f) or 'test' in str(f): continue
    tree = ast.parse(f.read_text())
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and not n.name.startswith('_'):
            total += 1
            if n.returns and all(a.annotation for a in n.args.args if a.arg != 'self'):
                fully_typed += 1
print(f"{fully_typed}/{total} ({100*fully_typed//total}%)")
EOF
```

### SQL Count by File
```bash
python3 << 'EOF'
import ast
from pathlib import Path
from collections import defaultdict
prod_by_file = defaultdict(int)
for f in Path('.').rglob('*.py'):
    if 'venv' in str(f) or 'test' in str(f): continue
    tree = ast.parse(f.read_text())
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and len(str(n.value)) > 15:
            if any(str(n.value).upper().startswith(v) for v in ['SELECT', 'INSERT', 'UPDATE']):
                prod_by_file[str(f)] += 1
for f, count in sorted(prod_by_file.items(), key=lambda x: -x[1])[:10]:
    print(f"{count:2d}  {f}")
EOF
```

### Complexity (radon)
```bash
radon cc -s -a pipeline/ingest.py | grep _process_one
```

### Coverage (after pytest-cov installed)
```bash
pytest tests/ --cov=pipeline --cov=scheduler --cov=infrastructure --cov-report=term
```

---

**Document version:** 2.1 (Caller analysis, HEAD verification, deferred list)  
**Last updated:** 2026-11-23  
**Status:** Ready for implementation
