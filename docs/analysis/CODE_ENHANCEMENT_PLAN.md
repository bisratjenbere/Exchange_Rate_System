# Code Enhancement Plan
## Making the Exchange Rate System Cleaner

**Goal**: Document specific code improvements to achieve SOLID principles, better OOP structure, and cleaner code **while maintaining exact functionality**.

**Approach**: Pragmatic, incremental changes that add value without over-engineering.

---

## Table of Contents
1. [Enhancement Summary](#enhancement-summary)
2. [Phase 1: Add Adapter Interface](#phase-1-adapter-interface)
3. [Phase 2: Repository Pattern](#phase-2-repository-pattern)
4. [Phase 3: Clean Code Refinements](#phase-3-clean-code)
5. [Phase 4: Dependency Injection](#phase-4-dependency-injection)
6. [Testing Strategy](#testing-strategy)
7. [Migration Path](#migration-path)

---

## Enhancement Summary

### Priority Levels

| Priority | Enhancement | Benefit | Effort | Files Changed |
|----------|-------------|---------|--------|---------------|
| **P0** | Add Adapter Base Class | Polymorphism, Liskov | Low | 22 files |
| **P0** | Extract Constants/Enums | Type safety, clarity | Low | 5 files |
| **P1** | Repository Pattern | Testability, decoupling | Medium | 15 files |
| **P1** | Parameter Objects | Readability | Low | 8 files |
| **P2** | Factory Pattern | Simplify adapter loading | Low | 2 files |
| **P2** | Result Objects | Better error handling | Medium | 10 files |
| **P3** | Dependency Injection | Full decoupling | High | 20+ files |

### Impact Analysis

**Before**: 
- ✅ Works correctly (429 tests pass)
- ⚠️ Some SOLID violations
- ⚠️ Tight PostgreSQL coupling
- ⚠️ Hard to test without real DB

**After**:
- ✅ Works correctly (all tests still pass)
- ✅ SOLID principles satisfied
- ✅ Loosely coupled
- ✅ Easy to test (in-memory implementations)

---

## Phase 1: Add Adapter Interface

### Problem

**Current State**: Inconsistent adapter signatures
```python
# adapters/cbe/adapter.py
def parse(raw_json: str) -> list:
    return [AdapterRecord(...), ...]

# adapters/dbe/adapter.py
def parse(raw_html: str, category: str = "UNKNOWN") -> tuple:
    return records, errors  # Different return type!

# adapters/rammis/adapter.py
def parse(raw_json: str) -> list:
    return [AdapterRecord(...), ...]
```

**Issues**:
- ❌ Cannot substitute adapters (violates Liskov Substitution)
- ❌ Scheduler needs special handling for each adapter
- ❌ Adding new adapter requires changing scheduler code (violates Open/Closed)

---

### Solution: Base Class + Uniform Interface

#### **New File**: `adapters/base.py`
```python
"""
adapters/base.py — Base adapter interface.

All bank adapters must inherit from BankAdapter and implement parse().
This enforces Liskov Substitution Principle (interchangeable adapters).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from domain.records import AdapterRecord


@dataclass
class ParseResult:
    """Uniform result from all adapters."""
    records: list[AdapterRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class BankAdapter(ABC):
    """
    Base interface for all bank adapters.
    
    Subclasses must implement:
    - parse(): Convert raw bank data to AdapterRecords
    - get_source_url(): Return the bank's URL
    
    Optionally implement:
    - get_adapter_key(): Return unique adapter identifier
    - schema_fingerprint(): Return structural hash for change detection
    - requires_category(): Whether adapter needs category injection
    """
    
    @abstractmethod
    def parse(self, raw_content: str, **options) -> ParseResult:
        """
        Parse raw bank data into AdapterRecords.
        
        Args:
            raw_content: Raw response from bank (JSON/HTML/etc)
            **options: Optional parameters (e.g., category="transactional")
        
        Returns:
            ParseResult with records and any errors
        
        Raises:
            ValueError: If raw_content is fundamentally unparseable
        """
        pass
    
    @abstractmethod
    def get_source_url(self) -> str:
        """Return the bank's data source URL."""
        pass
    
    def get_adapter_key(self) -> str:
        """Return unique adapter key (default: class name in snake_case)."""
        name = self.__class__.__name__
        # Convert CBEAdapter → cbe_adapter
        import re
        return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()
    
    def schema_fingerprint(self, raw_content: str) -> Optional[str]:
        """
        Return deterministic hash of data structure.
        Used to detect when bank changes their format.
        Return None if not implemented.
        """
        return None
    
    def requires_category(self) -> bool:
        """Whether this adapter needs category parameter in parse()."""
        return False
```

---

#### **Updated**: `adapters/cbe/adapter.py`

**Before**:
```python
ADAPTER_KEY = "cbe_api"
SOURCE_URL = "https://combanketh.et/cbeapi/daily-exchange-rates/"

def parse(raw_json: str) -> list:
    # ... parsing logic ...
    return records

def schema_fingerprint(raw_json: str) -> str:
    # ... fingerprint logic ...
```

**After**:
```python
from adapters.base import BankAdapter, ParseResult
from domain.records import AdapterRecord
# ... other imports ...

class CBEAdapter(BankAdapter):
    """Commercial Bank of Ethiopia adapter (Type A: JSON with stable IDs)."""
    
    def get_source_url(self) -> str:
        return "https://combanketh.et/cbeapi/daily-exchange-rates/"
    
    def get_adapter_key(self) -> str:
        return "cbe_api"
    
    def parse(self, raw_content: str, **options) -> ParseResult:
        """Parse CBE JSON API response."""
        try:
            data = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            return ParseResult(errors=[f"JSON parse error: {exc}"])
        
        if not isinstance(data, list):
            return ParseResult(
                errors=[f"Expected JSON array, got {type(data).__name__}"]
            )
        
        records = []
        for pub in data:
            records.extend(self._parse_publication(pub))
        
        return ParseResult(records=records)
    
    def schema_fingerprint(self, raw_content: str) -> str:
        """Deterministic hash of structural signature."""
        try:
            data = json.loads(raw_content)
            if isinstance(data, list) and data:
                pub = data[0]
                pub_keys = sorted(k for k in pub.keys() if k != "ExchangeRate")
                er_keys = []
                if isinstance(pub.get("ExchangeRate"), list) and pub["ExchangeRate"]:
                    er_keys = sorted(pub["ExchangeRate"][0].keys())
                payload = json.dumps({"pub": pub_keys, "er": er_keys}, separators=(",", ":"))
                return hashlib.sha256(payload.encode()).hexdigest()
        except Exception:
            pass
        return hashlib.sha256(b"cbe:empty_or_unparseable").hexdigest()
    
    # Private helper methods stay the same
    def _parse_publication(self, pub: dict) -> list:
        # ... existing logic ...
    
    def _parse_er_item(self, item: dict, pub_id, effective_date) -> list:
        # ... existing logic ...


# Module-level convenience functions (backward compatibility)
def parse(raw_json: str) -> list:
    """Backward-compatible function wrapper."""
    adapter = CBEAdapter()
    result = adapter.parse(raw_json)
    if result.errors:
        raise ValueError(result.errors[0])
    return result.records

def schema_fingerprint(raw_json: str) -> str:
    """Backward-compatible function wrapper."""
    return CBEAdapter().schema_fingerprint(raw_json)
```

**Benefits**:
- ✅ Implements `BankAdapter` interface
- ✅ Can be substituted for any other adapter
- ✅ Backward compatible (old function API still works)
- ✅ Testable (can mock `BankAdapter`)

---

#### **Updated**: `adapters/dbe/adapter.py`

**Before**:
```python
def parse(raw_html: str, category: str = "UNKNOWN") -> tuple:
    records, errors = [], []
    # ... parsing logic ...
    return records, errors
```

**After**:
```python
from adapters.base import BankAdapter, ParseResult

class DBEAdapter(BankAdapter):
    """Development Bank of Ethiopia adapter (Type F: single table)."""
    
    def get_source_url(self) -> str:
        return "https://dbe.com.et/"
    
    def get_adapter_key(self) -> str:
        return "dbe_html"
    
    def requires_category(self) -> bool:
        return True  # Type F adapters need category injection
    
    def parse(self, raw_content: str, **options) -> ParseResult:
        """Parse DBE HTML page."""
        category = options.get('category', 'UNKNOWN')
        
        soup = BeautifulSoup(raw_content, "html.parser")
        tables = soup.find_all("table")
        
        if not tables:
            return ParseResult(errors=["table_0:missing"])
        
        effective_date = self._parse_date_from_description(tables[0])
        
        try:
            records = self._parse_table(tables[0], category, effective_date)
            return ParseResult(records=records)
        except Exception as exc:
            return ParseResult(errors=[f"table_0:{exc}"])
    
    # ... rest of implementation ...


# Backward compatibility
def parse(raw_html: str, category: str = "UNKNOWN") -> tuple:
    """Backward-compatible function wrapper."""
    adapter = DBEAdapter()
    result = adapter.parse(raw_html, category=category)
    return result.records, result.errors
```

**Benefits**:
- ✅ Now returns `ParseResult` (uniform with CBE)
- ✅ Implements same interface
- ✅ Can be used polymorphically
- ✅ Backward compatible

---

#### **Updated**: `scheduler/runner.py`

**Before**:
```python
def _parse(adapter, raw_content: str, category: str = "UNKNOWN") -> list:
    """Call adapter.parse(). Passes category if adapter accepts it."""
    import inspect
    sig = inspect.signature(adapter.parse)
    if "category" in sig.parameters:
        result = adapter.parse(raw_content, category=category)
    else:
        result = adapter.parse(raw_content)
    if isinstance(result, tuple):
        records, _errors = result
        return records
    return result
```

**After**:
```python
def _parse(adapter: BankAdapter, raw_content: str, category: str = "UNKNOWN") -> list:
    """Call adapter.parse() with uniform interface."""
    options = {}
    if adapter.requires_category():
        options['category'] = category
    
    result = adapter.parse(raw_content, **options)
    
    if result.errors:
        # Log errors but don't fail (partial success handling)
        for error in result.errors:
            print(f"Parse error: {error}")
    
    return result.records
```

**Benefits**:
- ✅ No more inspection magic
- ✅ Clean, type-safe interface
- ✅ Better error handling
- ✅ Can use type hints

---

### Migration Checklist

- [ ] Create `adapters/base.py` with `BankAdapter` and `ParseResult`
- [ ] Update CBE adapter (reference implementation)
- [ ] Update DBE adapter
- [ ] Update remaining 19 adapters
- [ ] Update scheduler to use `BankAdapter` type
- [ ] Run all tests (should still pass)
- [ ] Update adapter tests to use both old and new APIs
- [ ] Deprecate old function API (add warnings)
- [ ] After 1 release, remove backward compatibility wrappers

---

## Phase 2: Repository Pattern

### Problem

**Current State**: Direct SQL everywhere
```python
# pipeline/persist.py
def insert_observation(conn, record, source_id, run_id, ...):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO rate_observation (...)
        VALUES (...)
        RETURNING id
    """, (...))
    return cursor.fetchone()[0]

# pipeline/deduplicate.py
def classify_observation(conn, record, logical_key, fingerprint):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, snapshot_fingerprint
        FROM rate_observation
        WHERE logical_observation_key = %s AND is_current = TRUE
    """, (logical_key,))
    # ...
```

**Issues**:
- ❌ Tight coupling to PostgreSQL
- ❌ Cannot unit test without real database
- ❌ SQL scattered across multiple files
- ❌ Hard to swap database implementations

---

### Solution: Repository Classes

#### **New File**: `repositories/base.py`
```python
"""
repositories/base.py — Repository interfaces.

Repositories encapsulate all database access.
Business logic depends on repository interfaces, not concrete PostgreSQL.
"""
from abc import ABC, abstractmethod
from typing import Optional, List
from dataclasses import dataclass


@dataclass
class Observation:
    """Domain model for rate observation."""
    id: Optional[int] = None
    source_id: int = None
    currency_code: str = None
    category: str = None
    buying_rate: Optional[float] = None
    selling_rate: Optional[float] = None
    effective_date: Optional[str] = None
    logical_observation_key: Optional[str] = None
    snapshot_fingerprint: str = None
    is_current: bool = False
    version_number: Optional[int] = None
    # ... other fields


class ObservationRepository(ABC):
    """Repository for rate observations."""
    
    @abstractmethod
    def save(self, obs: Observation) -> int:
        """Insert observation, return ID."""
        pass
    
    @abstractmethod
    def find_current_by_key(self, key: str) -> Optional[Observation]:
        """Find current observation by logical key."""
        pass
    
    @abstractmethod
    def find_by_fingerprint(self, fingerprint: str, source_id: int,
                            currency: str, category: str) -> Optional[Observation]:
        """Find observation by fingerprint (ambiguous identity case)."""
        pass
    
    @abstractmethod
    def mark_superseded(self, obs_id: int, superseded_by_id: int):
        """Mark observation as superseded (set is_current=FALSE)."""
        pass
    
    @abstractmethod
    def get_next_version_number(self, key: str) -> int:
        """Get next version number for logical key."""
        pass


class SourceRepository(ABC):
    """Repository for rate sources."""
    
    @abstractmethod
    def get_by_id(self, source_id: int) -> Optional[dict]:
        """Get source by ID."""
        pass
    
    @abstractmethod
    def get_all_enabled(self) -> List[dict]:
        """Get all enabled sources."""
        pass
    
    @abstractmethod
    def update_last_success(self, source_id: int):
        """Update last_success_at timestamp."""
        pass
    
    @abstractmethod
    def update_schema_fingerprint(self, source_id: int, fingerprint: str):
        """Update schema fingerprint."""
        pass


class RunRepository(ABC):
    """Repository for collection runs."""
    
    @abstractmethod
    def start_run(self, source_id: int) -> int:
        """Start new run, return run_id."""
        pass
    
    @abstractmethod
    def finish_run(self, run_id: int, status: str, **metrics):
        """Finish run with status and metrics."""
        pass
    
    @abstractmethod
    def recover_stuck_runs(self, source_id: int):
        """Mark timed-out runs as failed."""
        pass
```

---

#### **New File**: `repositories/postgres.py`
```python
"""
repositories/postgres.py — PostgreSQL implementations.

Concrete repository implementations using psycopg2.
All SQL is encapsulated here.
"""
from typing import Optional, List
from repositories.base import (
    ObservationRepository, SourceRepository, RunRepository, Observation
)


class PostgresObservationRepository(ObservationRepository):
    """PostgreSQL implementation of ObservationRepository."""
    
    def __init__(self, conn):
        self.conn = conn
    
    def save(self, obs: Observation) -> int:
        """Insert observation, return ID."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO rate_observation (
                source_id, run_id, source_currency_code, category_id,
                buying_rate, selling_rate, effective_date, effective_date_basis,
                logical_observation_key, snapshot_fingerprint,
                validation_status, identity_status, version_number, is_current,
                fetched_at, created_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()
            )
            RETURNING id
        """, (
            obs.source_id, obs.run_id, obs.currency_code, obs.category_id,
            obs.buying_rate, obs.selling_rate, obs.effective_date, obs.effective_date_basis,
            obs.logical_observation_key, obs.snapshot_fingerprint,
            obs.validation_status, obs.identity_status, obs.version_number, obs.is_current,
            obs.fetched_at
        ))
        return cursor.fetchone()[0]
    
    def find_current_by_key(self, key: str) -> Optional[Observation]:
        """Find current observation by logical key."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, source_id, source_currency_code, snapshot_fingerprint,
                   logical_observation_key, version_number, is_current
            FROM rate_observation
            WHERE logical_observation_key = %s
              AND is_current = TRUE
        """, (key,))
        row = cursor.fetchone()
        if not row:
            return None
        return Observation(
            id=row[0],
            source_id=row[1],
            currency_code=row[2],
            snapshot_fingerprint=row[3],
            logical_observation_key=row[4],
            version_number=row[5],
            is_current=row[6],
        )
    
    def find_by_fingerprint(self, fingerprint: str, source_id: int,
                            currency: str, category: str) -> Optional[Observation]:
        """Find observation by fingerprint (ambiguous identity)."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id FROM rate_observation
            WHERE snapshot_fingerprint = %s
              AND source_id = %s
              AND source_currency_code = %s
              AND category = %s
            LIMIT 1
        """, (fingerprint, source_id, currency, category))
        row = cursor.fetchone()
        if not row:
            return None
        return Observation(id=row[0])
    
    def mark_superseded(self, obs_id: int, superseded_by_id: int):
        """Mark observation as superseded."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE rate_observation
            SET is_current = FALSE, superseded_by_id = %s
            WHERE id = %s
        """, (superseded_by_id, obs_id))
    
    def get_next_version_number(self, key: str) -> int:
        """Get next version number for logical key."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT COALESCE(MAX(version_number), 0) + 1
            FROM rate_observation
            WHERE logical_observation_key = %s
        """, (key,))
        return cursor.fetchone()[0]


class PostgresSourceRepository(SourceRepository):
    """PostgreSQL implementation of SourceRepository."""
    
    def __init__(self, conn):
        self.conn = conn
    
    def get_by_id(self, source_id: int) -> Optional[dict]:
        """Get source by ID."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, adapter_key, source_url, ssl_verify,
                   schema_fingerprint, default_category
            FROM rate_source
            WHERE id = %s
        """, (source_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return {
            'id': row[0],
            'adapter_key': row[1],
            'source_url': row[2],
            'ssl_verify': row[3],
            'schema_fingerprint': row[4],
            'default_category': row[5],
        }
    
    def get_all_enabled(self) -> List[dict]:
        """Get all enabled sources."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, adapter_key, source_url, ssl_verify,
                   schema_fingerprint, default_category
            FROM rate_source
            WHERE is_enabled = TRUE
            ORDER BY id
        """)
        return [
            {
                'id': row[0],
                'adapter_key': row[1],
                'source_url': row[2],
                'ssl_verify': row[3],
                'schema_fingerprint': row[4],
                'default_category': row[5],
            }
            for row in cursor.fetchall()
        ]
    
    def update_last_success(self, source_id: int):
        """Update last_success_at timestamp."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE rate_source
            SET last_success_at = now()
            WHERE id = %s
        """, (source_id,))
    
    def update_schema_fingerprint(self, source_id: int, fingerprint: str):
        """Update schema fingerprint."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE rate_source
            SET schema_fingerprint = %s
            WHERE id = %s
        """, (fingerprint, source_id))


class PostgresRunRepository(RunRepository):
    """PostgreSQL implementation of RunRepository."""
    
    def __init__(self, conn):
        self.conn = conn
    
    def start_run(self, source_id: int) -> int:
        """Start new run, return run_id."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO collection_run (source_id, status, started_at)
            VALUES (%s, 'running', now())
            RETURNING id
        """, (source_id,))
        return cursor.fetchone()[0]
    
    def finish_run(self, run_id: int, status: str, **metrics):
        """Finish run with status and metrics."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE collection_run
            SET status = %s,
                finished_at = now(),
                http_status = %s,
                records_found = %s,
                records_accepted = %s,
                records_flagged = %s,
                duration_ms = %s,
                error_code = %s,
                error_summary = %s
            WHERE id = %s
        """, (
            status,
            metrics.get('http_status'),
            metrics.get('records_found'),
            metrics.get('records_accepted'),
            metrics.get('records_flagged'),
            metrics.get('duration_ms'),
            metrics.get('error_code'),
            metrics.get('error_summary'),
            run_id,
        ))
    
    def recover_stuck_runs(self, source_id: int):
        """Mark timed-out runs as failed."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE collection_run
            SET status = 'failed',
                finished_at = now(),
                error_code = 'timeout',
                error_summary = 'Run timed out after 60 minutes'
            WHERE source_id = %s
              AND status = 'running'
              AND started_at < now() - interval '1 hour'
        """, (source_id,))
```

---

#### **New File**: `repositories/memory.py`
```python
"""
repositories/memory.py — In-memory implementations for testing.

Fast, simple implementations that don't require a database.
Perfect for unit tests.
"""
from typing import Optional, List, Dict
from repositories.base import (
    ObservationRepository, SourceRepository, RunRepository, Observation
)


class InMemoryObservationRepository(ObservationRepository):
    """In-memory implementation for testing."""
    
    def __init__(self):
        self.observations: Dict[int, Observation] = {}
        self.next_id = 1
    
    def save(self, obs: Observation) -> int:
        obs.id = self.next_id
        self.observations[obs.id] = obs
        self.next_id += 1
        return obs.id
    
    def find_current_by_key(self, key: str) -> Optional[Observation]:
        for obs in self.observations.values():
            if obs.logical_observation_key == key and obs.is_current:
                return obs
        return None
    
    def find_by_fingerprint(self, fingerprint: str, source_id: int,
                            currency: str, category: str) -> Optional[Observation]:
        for obs in self.observations.values():
            if (obs.snapshot_fingerprint == fingerprint
                and obs.source_id == source_id
                and obs.currency_code == currency
                and obs.category == category):
                return obs
        return None
    
    def mark_superseded(self, obs_id: int, superseded_by_id: int):
        if obs_id in self.observations:
            self.observations[obs_id].is_current = False
    
    def get_next_version_number(self, key: str) -> int:
        max_version = 0
        for obs in self.observations.values():
            if obs.logical_observation_key == key and obs.version_number:
                max_version = max(max_version, obs.version_number)
        return max_version + 1


class InMemorySourceRepository(SourceRepository):
    """In-memory implementation for testing."""
    
    def __init__(self):
        self.sources: Dict[int, dict] = {}
    
    def get_by_id(self, source_id: int) -> Optional[dict]:
        return self.sources.get(source_id)
    
    def get_all_enabled(self) -> List[dict]:
        return [s for s in self.sources.values() if s.get('is_enabled')]
    
    def update_last_success(self, source_id: int):
        if source_id in self.sources:
            self.sources[source_id]['last_success_at'] = 'now()'
    
    def update_schema_fingerprint(self, source_id: int, fingerprint: str):
        if source_id in self.sources:
            self.sources[source_id]['schema_fingerprint'] = fingerprint


class InMemoryRunRepository(RunRepository):
    """In-memory implementation for testing."""
    
    def __init__(self):
        self.runs: Dict[int, dict] = {}
        self.next_id = 1
    
    def start_run(self, source_id: int) -> int:
        run_id = self.next_id
        self.runs[run_id] = {
            'id': run_id,
            'source_id': source_id,
            'status': 'running',
            'started_at': 'now()',
        }
        self.next_id += 1
        return run_id
    
    def finish_run(self, run_id: int, status: str, **metrics):
        if run_id in self.runs:
            self.runs[run_id]['status'] = status
            self.runs[run_id]['finished_at'] = 'now()'
            self.runs[run_id].update(metrics)
    
    def recover_stuck_runs(self, source_id: int):
        for run in self.runs.values():
            if run['source_id'] == source_id and run['status'] == 'running':
                run['status'] = 'failed'
                run['error_code'] = 'timeout'
```

---

#### **Updated**: `pipeline/ingest.py`

**Before**:
```python
def ingest(conn, records: list, source_id: int, run_id: int, ...):
    for record in records:
        # Direct SQL calls
        cursor = conn.cursor()
        cursor.execute("INSERT INTO ...")
```

**After**:
```python
from repositories.base import ObservationRepository

def ingest(obs_repo: ObservationRepository, records: list, 
           source_id: int, run_id: int, ...):
    """
    Process records through pipeline and save to repository.
    
    Args:
        obs_repo: ObservationRepository implementation
        records: List of AdapterRecords to process
        ...
    """
    for record in records:
        # ... validation, fingerprinting, identity ...
        
        obs = Observation(
            source_id=source_id,
            run_id=run_id,
            currency_code=record.source_currency_code,
            # ... all fields ...
        )
        
        obs_id = obs_repo.save(obs)
        
        if action == "changed":
            existing = obs_repo.find_current_by_key(logical_key)
            if existing:
                obs_repo.mark_superseded(existing.id, obs_id)
```

**Benefits**:
- ✅ No SQL in business logic
- ✅ Testable without PostgreSQL
- ✅ Can swap database implementations
- ✅ Clear separation of concerns

---

### Testing Example

**Before**: Needs real PostgreSQL
```python
def test_ingest():
    # Requires PostgreSQL running
    conn = psycopg2.connect("postgresql://localhost/test")
    records = [AdapterRecord(...)]
    result = ingest(conn, records, source_id=1, run_id=1)
    assert result.accepted == 1
```

**After**: In-memory testing
```python
from repositories.memory import InMemoryObservationRepository

def test_ingest():
    # No database needed!
    repo = InMemoryObservationRepository()
    records = [AdapterRecord(...)]
    result = ingest(repo, records, source_id=1, run_id=1)
    assert result.accepted == 1
    assert len(repo.observations) == 1
```

---

## Phase 3: Clean Code Refinements

### Enhancement 3.1: Extract Constants

**Problem**: Magic strings scattered everywhere

**Before**:
```python
if record.effective_date_basis == "source_published":  # String literal
    ...
if validation_status == "rejected":  # String literal
    ...
```

**After**: Already done! (see `domain/enums.py`)
```python
if record.effective_date_basis == EffectiveDateBasis.SOURCE_PUBLISHED:
    ...
if validation_status == ValidationStatus.REJECTED:
    ...
```

✅ **Status**: Already implemented in current code

---

### Enhancement 3.2: Parameter Objects

**Problem**: Long parameter lists

**Before**: `pipeline/persist.py`
```python
def insert_observation(conn, record, source_id, run_id, category_id,
                       fingerprint, logical_key, identity_status,
                       validation_status, validation_messages, fetched_at,
                       version_number, is_current, change_review_status):
    # 14 parameters!
```

**After**:
```python
@dataclass
class ObservationInsertData:
    """All data needed to insert observation."""
    record: AdapterRecord
    source_id: int
    run_id: int
    category_id: Optional[int]
    fingerprint: str
    logical_key: Optional[str]
    identity_status: IdentityStatus
    validation_status: ValidationStatus
    validation_messages: list
    fetched_at: datetime
    version_number: Optional[int]
    is_current: bool
    change_review_status: ChangeReviewStatus

def insert_observation(conn, data: ObservationInsertData) -> int:
    # Single parameter, self-documenting
    cursor = conn.cursor()
    cursor.execute("""...""", (
        data.source_id,
        data.run_id,
        # ... all from data object
    ))
```

**Benefits**:
- ✅ Easy to remember (one object, not 14 params)
- ✅ Named fields (can't mix up order)
- ✅ Easier to extend (add new field without changing all call sites)
- ✅ Type-safe

---

### Enhancement 3.3: Guard Clauses (Reduce Nesting)

**Problem**: Deep nesting in `pipeline/identity.py`

**Before**:
```python
def build_identity(record, source_id, fetched_date=None):
    if record.source_record_key:
        if record.effective_date is not None:
            if record.effective_date_basis in ("source_published", "source_inferred"):
                key = f"{source_id}:{record.source_record_key}:{category}"
                return key, IdentityStatus.CONFIRMED
    
    if record.effective_date is not None:
        if record.effective_date_basis == "source_published":
            key = f"{source_id}:{currency}:{category}:{record.effective_date}"
            return key, IdentityStatus.CONFIRMED
    # ... more nesting ...
```

**After** (Early returns):
```python
def build_identity(record, source_id, fetched_date=None):
    # Strategy 1: Strongest identity (stable source key + published date)
    if (record.source_record_key
        and record.effective_date is not None
        and record.effective_date_basis in ("source_published", "source_inferred")):
        key = f"{source_id}:{record.source_record_key}:{category}"
        return key, IdentityStatus.CONFIRMED
    
    # Strategy 2: Strong identity (source-published date)
    if (record.effective_date is not None
        and record.effective_date_basis == "source_published"):
        key = f"{source_id}:{currency}:{category}:{record.effective_date}"
        return key, IdentityStatus.CONFIRMED
    
    # Strategy 3: Medium identity (source-inferred date)
    if (record.effective_date is not None
        and record.effective_date_basis == "source_inferred"):
        key = f"{source_id}:{currency}:{category}:{record.effective_date}"
        return key, IdentityStatus.DERIVED
    
    # Strategy 4: Weak identity (collection fallback)
    if (record.effective_date_basis == "collection_date_fallback"
        and fetched_date is not None):
        key = f"{source_id}:{currency}:{category}:{fetched_date}"
        return key, IdentityStatus.DERIVED
    
    # No identity possible
    return None, IdentityStatus.AMBIGUOUS
```

**Benefits**:
- ✅ Easier to read (less indentation)
- ✅ Clear strategy sequence (top = strongest, bottom = weakest)
- ✅ Each strategy is independent block
- ✅ Can add comments for each strategy

---

### Enhancement 3.4: Extract Helper Classes

**Problem**: `pipeline/ingest.py` is 150+ lines doing many things

**Solution**: Extract result tracking to helper class

**Before**:
```python
def ingest(conn, records, source_id, run_id, fetched_at):
    result = IngestResult()
    
    for record in records:
        # ... 100 lines of processing ...
        
        if val_status == ValidationStatus.REJECTED:
            result.rejected += 1
        elif action == "changed" or val_status == ValidationStatus.WARNING:
            result.flagged += 1
        else:
            result.accepted += 1
```

**After**:
```python
class RecordProcessor:
    """Handles processing and tracking for one ingest run."""
    
    def __init__(self, obs_repo, source_id, run_id):
        self.obs_repo = obs_repo
        self.source_id = source_id
        self.run_id = run_id
        self.result = IngestResult()
        self.category_map = self._load_categories()
    
    def process(self, record: AdapterRecord):
        """Process one record through pipeline."""
        val_status, messages = validate(record)
        fingerprint = compute_fingerprint(record, self.source_id)
        # ... rest of pipeline ...
        
        obs_id = self.obs_repo.save(observation)
        self._update_counts(val_status, action)
    
    def _update_counts(self, val_status, action):
        """Update result counts based on status and action."""
        if val_status == ValidationStatus.REJECTED:
            self.result.rejected += 1
        elif action == "changed":
            self.result.flagged += 1
        else:
            self.result.accepted += 1
    
    def get_result(self) -> IngestResult:
        return self.result

def ingest(obs_repo, records, source_id, run_id, fetched_at):
    processor = RecordProcessor(obs_repo, source_id, run_id)
    
    for record in records:
        try:
            processor.process(record)
        except Exception as exc:
            processor.result.errors.append((record.source_currency_code, str(exc)))
    
    return processor.get_result()
```

**Benefits**:
- ✅ Shorter main function
- ✅ Clear responsibilities (processor handles details)
- ✅ Easier to test (can test processor separately)
- ✅ Less parameter passing

---

## Phase 4: Factory Pattern

### Problem

**Current**: Complex adapter loading logic in scheduler

**Before**: `scheduler/runner.py`
```python
def _load_adapter(adapter_key: str):
    """Import adapters/<dir>/adapter.py by adapter_key."""
    parts = adapter_key.split("_")
    candidates = [adapter_key]
    for i in range(len(parts) - 1, 0, -1):
        candidates.append("_".join(parts[:i]))
    candidates.append(adapter_key.rsplit("_", 1)[0] + "_")
    
    for name in dict.fromkeys(candidates):
        try:
            return importlib.import_module(f"adapters.{name}.adapter")
        except ModuleNotFoundError:
            continue
    raise ImportError(f"No adapter module found for {adapter_key}")
```

**After**: `adapters/factory.py`
```python
"""
adapters/factory.py — Factory for creating adapters.

Centralizes adapter creation logic and discovery.
"""
from typing import Dict, Type
from adapters.base import BankAdapter

# Registry of all adapters
_ADAPTER_REGISTRY: Dict[str, Type[BankAdapter]] = {}

def register_adapter(key: str):
    """Decorator to register an adapter."""
    def decorator(adapter_class: Type[BankAdapter]):
        _ADAPTER_REGISTRY[key] = adapter_class
        return adapter_class
    return decorator

def create_adapter(adapter_key: str) -> BankAdapter:
    """
    Create adapter instance by key.
    
    Args:
        adapter_key: Adapter identifier (e.g., "cbe_api", "dbe_html")
    
    Returns:
        BankAdapter instance
    
    Raises:
        ValueError: If adapter_key not registered
    """
    adapter_class = _ADAPTER_REGISTRY.get(adapter_key)
    if not adapter_class:
        raise ValueError(
            f"Unknown adapter key: {adapter_key}. "
            f"Available: {list(_ADAPTER_REGISTRY.keys())}"
        )
    return adapter_class()

def get_all_adapters() -> Dict[str, Type[BankAdapter]]:
    """Get all registered adapters."""
    return _ADAPTER_REGISTRY.copy()
```

**Updated**: `adapters/cbe/adapter.py`
```python
from adapters.base import BankAdapter
from adapters.factory import register_adapter

@register_adapter("cbe_api")
class CBEAdapter(BankAdapter):
    # ... implementation ...
```

**Updated**: `scheduler/runner.py`
```python
from adapters.factory import create_adapter

def run_source(source_repo, source_id):
    source = source_repo.get_by_id(source_id)
    adapter = create_adapter(source['adapter_key'])  # Simple!
    # ...
```

**Benefits**:
- ✅ Centralized adapter creation
- ✅ Easy to see all available adapters
- ✅ Type-safe (returns `BankAdapter`)
- ✅ Better error messages

---

## Phase 5: Dependency Injection

### Current State

**Problem**: Hard-coded dependencies
```python
def run_source(conn, source_id):
    # Hard-coded PostgreSQL connection
    # Hard-coded adapter loading
    # Hard-coded HTTP fetching
```

**Cannot**:
- Test without real PostgreSQL
- Mock network requests
- Swap implementations

---

### Solution: Inject Dependencies

```python
@dataclass
class CollectionDependencies:
    """All dependencies for collection orchestration."""
    obs_repo: ObservationRepository
    source_repo: SourceRepository
    run_repo: RunRepository
    adapter_factory: AdapterFactory
    http_client: HttpClient

class CollectionOrchestrator:
    """Orchestrates collection runs with injected dependencies."""
    
    def __init__(self, deps: CollectionDependencies):
        self.obs_repo = deps.obs_repo
        self.source_repo = deps.source_repo
        self.run_repo = deps.run_repo
        self.adapter_factory = deps.adapter_factory
        self.http_client = deps.http_client
    
    def run_source(self, source_id: int) -> dict:
        """Run collection for one source."""
        source = self.source_repo.get_by_id(source_id)
        adapter = self.adapter_factory.create(source['adapter_key'])
        
        run_id = self.run_repo.start_run(source_id)
        
        content = self.http_client.fetch(source['source_url'])
        result = adapter.parse(content)
        
        ingest_result = ingest(self.obs_repo, result.records, source_id, run_id)
        
        self.run_repo.finish_run(run_id, "success")
        return {"status": "success"}

# Production setup
conn = psycopg2.connect(DATABASE_URL)
deps = CollectionDependencies(
    obs_repo=PostgresObservationRepository(conn),
    source_repo=PostgresSourceRepository(conn),
    run_repo=PostgresRunRepository(conn),
    adapter_factory=DefaultAdapterFactory(),
    http_client=RequestsHttpClient(),
)
orchestrator = CollectionOrchestrator(deps)
orchestrator.run_source(source_id=1)

# Test setup
deps = CollectionDependencies(
    obs_repo=InMemoryObservationRepository(),
    source_repo=InMemorySourceRepository(),
    run_repo=InMemoryRunRepository(),
    adapter_factory=MockAdapterFactory(),
    http_client=FakeHttpClient(),
)
orchestrator = CollectionOrchestrator(deps)
# Test without any real database or network!
```

**Benefits**:
- ✅ Fully testable
- ✅ All dependencies explicit
- ✅ Easy to swap implementations
- ✅ SOLID principles satisfied

---

## Testing Strategy

### Test Pyramid After Enhancements

```
                    ┌──────────────────┐
                    │   E2E Tests      │  (5%)
                    │  (Real DB + API) │
                    └──────────────────┘
                  ┌────────────────────────┐
                  │  Integration Tests     │  (15%)
                  │  (Postgres repos)      │
                  └────────────────────────┘
              ┌──────────────────────────────┐
              │     Component Tests          │  (30%)
              │  (In-memory repos)           │
              └──────────────────────────────┘
          ┌──────────────────────────────────────┐
          │        Unit Tests                    │  (50%)
          │  (Pure functions, adapters)          │
          └──────────────────────────────────────┘
```

### New Test Capabilities

**Before**: Mostly integration tests (need PostgreSQL)
```python
# 90% of tests look like this:
def test_cbe_adapter():
    conn = psycopg2.connect("postgresql://localhost/test")
    # ... setup database ...
    result = run_source(conn, source_id=1)
    assert result['accepted'] > 0
```

**After**: Mostly unit/component tests (in-memory)
```python
# Fast unit tests (no database)
def test_adapter_parsing():
    adapter = CBEAdapter()
    result = adapter.parse(mock_json)
    assert len(result.records) == 32

# Fast component tests (in-memory)
def test_ingest_pipeline():
    repo = InMemoryObservationRepository()
    result = ingest(repo, records, source_id=1, run_id=1)
    assert result.accepted == 10
    assert len(repo.observations) == 10

# Slow integration tests (real database - only when needed)
def test_postgres_repository():
    conn = psycopg2.connect("postgresql://localhost/test")
    repo = PostgresObservationRepository(conn)
    obs_id = repo.save(observation)
    found = repo.find_current_by_key(key)
    assert found.id == obs_id
```

---

## Migration Path

### Step-by-Step Implementation

#### **Phase 1: Adapter Interface** (Week 1)
- [ ] Day 1-2: Create `adapters/base.py`
- [ ] Day 3-4: Update 2 reference adapters (CBE, DBE)
- [ ] Day 5: Update scheduler to use new interface
- [ ] Week 2: Update remaining 19 adapters

**Risk**: Low (backward compatible)

---

#### **Phase 2: Repository Pattern** (Week 2-3)
- [ ] Week 2: Create repository interfaces and PostgreSQL implementations
- [ ] Week 3: Create in-memory implementations
- [ ] Week 3: Update `pipeline/ingest.py` to use repositories
- [ ] Week 3: Update `scheduler/runner.py` to use repositories

**Risk**: Medium (changes many files)

---

#### **Phase 3: Clean Code** (Week 4)
- [ ] Extract parameter objects
- [ ] Add guard clauses
- [ ] Extract helper classes
- [ ] Refactor long functions

**Risk**: Low (mostly cosmetic)

---

#### **Phase 4: Factory Pattern** (Week 5)
- [ ] Create `adapters/factory.py`
- [ ] Add `@register_adapter` decorators
- [ ] Update scheduler to use factory

**Risk**: Low (isolated change)

---

#### **Phase 5: Dependency Injection** (Week 6)
- [ ] Create `CollectionDependencies` dataclass
- [ ] Create `CollectionOrchestrator` class
- [ ] Update entry points to inject dependencies

**Risk**: Medium (architectural change)

---

### Testing at Each Phase

**After each phase**:
1. Run full test suite: `pytest tests/ -v`
2. All 429 tests must still pass
3. Add new tests for new abstractions
4. No functionality changes

**Success Criteria**:
- ✅ All existing tests pass
- ✅ Code coverage stays same or improves
- ✅ No performance regression
- ✅ Can run tests without PostgreSQL (after Phase 2)

---

## Summary

### What We're Changing

| Component | Before | After | Benefit |
|-----------|--------|-------|---------|
| **Adapters** | Inconsistent functions | Uniform `BankAdapter` interface | Polymorphism, Liskov Substitution |
| **Database** | Direct SQL everywhere | Repository pattern | Testability, decoupling |
| **Parameters** | 14-param functions | Parameter objects | Readability |
| **Nesting** | Deep conditionals | Guard clauses | Clarity |
| **Loading** | Complex import logic | Factory pattern | Simplicity |
| **Dependencies** | Hard-coded | Dependency injection | Full testability |

### What We're NOT Changing

- ✅ Functionality (system behavior identical)
- ✅ Database schema
- ✅ API endpoints
- ✅ Pipeline logic (validate, normalize, etc.)
- ✅ Test expectations (all pass)

### Final Result

**SOLID Compliance**:
- ✅ Single Responsibility (each class/module one purpose)
- ✅ Open/Closed (add adapters without changing scheduler)
- ✅ Liskov Substitution (adapters interchangeable)
- ✅ Interface Segregation (lean interfaces)
- ✅ Dependency Inversion (depend on abstractions)

**Clean Code**:
- ✅ Meaningful names
- ✅ Small functions/classes
- ✅ DRY (no duplication)
- ✅ Low coupling, high cohesion
- ✅ Testable without infrastructure

**Architecture**:
- ✅ Hybrid approach (functional pipeline + OOP boundaries)
- ✅ Repository pattern for data access
- ✅ Factory pattern for object creation
- ✅ Dependency injection for flexibility

---

## Next Steps

Want to:
1. **Start implementing?** Pick Phase 1 (Adapter Interface) - smallest, highest value
2. **See more examples?** I can show detailed before/after for any file
3. **Create a spec?** I can generate a full refactoring specification

Which would you like?
