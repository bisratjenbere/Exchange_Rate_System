# Senior Engineering Principles Analysis
## Ethiopian Bank Exchange Rate System

**Purpose**: Analyze how this codebase demonstrates (or violates) SOLID principles, OOP concepts, Design Patterns, and Clean Code practices.

**Status**: Read-only analysis - NO code changes

---

## Table of Contents
1. [SOLID Principles Analysis](#solid-principles)
2. [OOP Concepts](#oop-concepts)
3. [Design Patterns](#design-patterns)
4. [Clean Code Principles](#clean-code)
5. [What's Done Well](#strengths)
6. [What Could Improve](#improvement-opportunities)
7. [Learning Roadmap](#learning-path)

---

## SOLID Principles

### ✅ **S - Single Responsibility Principle**

**Definition**: A class/module should have only one reason to change.

#### **Where It's Applied Well:**

**1. Pipeline Modules** (`pipeline/*.py`)
```python
# Each module does ONE thing:
validate.py      # → ONLY validates records
normalize.py     # → ONLY normalizes data
fingerprint.py   # → ONLY computes hashes
identity.py      # → ONLY determines identity
deduplicate.py   # → ONLY detects duplicates
```

**Why this is good:**
- If validation rules change → only touch `validate.py`
- If fingerprint algorithm changes → only touch `fingerprint.py`
- Each module is testable in isolation

**2. Adapters** (`adapters/*/adapter.py`)
```python
# Each adapter has ONE job: convert bank format → AdapterRecord
cbe/adapter.py   # → ONLY parses CBE JSON
dbe/adapter.py   # → ONLY parses DBE HTML
```

**Analysis**: ✅ **EXCELLENT** - Clear separation of concerns

---

### ⚠️ **O - Open/Closed Principle**

**Definition**: Open for extension, closed for modification.

#### **Where It's Applied:**

**1. Adapter System**
```python
# To add a new bank:
# ✅ ADD new adapter (extension)
# ❌ DON'T modify existing adapters (closed for modification)

# Example: Adding "Awash Bank"
adapters/awash/adapter.py  # NEW FILE
# No changes to cbe/adapter.py, dbe/adapter.py, etc.
```

#### **Where It Could Improve:**

**1. Pipeline Stages** - Currently procedural
```python
# Current: pipeline/ingest.py
def ingest(conn, records, source_id, run_id, fetched_at):
    for record in records:
        status, messages = validate(record)      # Function call
        fp = compute_fingerprint(record, ...)    # Function call
        identity_status, key = build_identity(...)
        # etc.
```

**Better (Open/Closed):**
```python
# Define a Pipeline interface
class PipelineStage(ABC):
    @abstractmethod
    def process(self, record: AdapterRecord) -> ProcessResult:
        pass

# Each stage implements the interface
class ValidationStage(PipelineStage):
    def process(self, record):
        # validation logic

class FingerprintStage(PipelineStage):
    def process(self, record):
        # fingerprint logic

# Pipeline runner
class Pipeline:
    def __init__(self, stages: list[PipelineStage]):
        self.stages = stages
    
    def run(self, record):
        for stage in self.stages:
            result = stage.process(record)
            if result.should_stop:
                return result
        return result

# Now you can ADD new stages without modifying existing code:
pipeline = Pipeline([
    ValidationStage(),
    NormalizationStage(),
    FingerprintStage(),
    IdentityStage(),
    DeduplicationStage(),
    # NEW: AnomalyDetectionStage() ← just add it!
])
```

**Analysis**: ⚠️ **PARTIAL** - Good for adapters, could improve for pipeline

---

### ❌ **L - Liskov Substitution Principle**

**Definition**: Subtypes must be substitutable for their base types.

#### **Current State:**

**Problem**: No formal adapter interface
```python
# adapters/cbe/adapter.py
def parse(raw_json: str) -> list:
    # returns list[AdapterRecord]

# adapters/dbe/adapter.py  
def parse(raw_html: str, category: str = "UNKNOWN") -> tuple:
    # returns (list[AdapterRecord], list[str])  ← DIFFERENT signature!
```

**Issue**: You cannot substitute `dbe.parse()` for `cbe.parse()` because:
- Different return types (`list` vs `tuple`)
- Different parameters (`category` parameter in dbe)

**Better (Liskov Substitution):**
```python
# Define base interface
class BankAdapter(ABC):
    @abstractmethod
    def parse(self, raw_content: str, **options) -> ParseResult:
        """
        Returns ParseResult with:
        - records: list[AdapterRecord]
        - errors: list[str]
        """
        pass

# All adapters implement same interface
class CBEAdapter(BankAdapter):
    def parse(self, raw_content: str, **options) -> ParseResult:
        try:
            records = self._parse_json(raw_content)
            return ParseResult(records=records, errors=[])
        except Exception as e:
            return ParseResult(records=[], errors=[str(e)])

class DBEAdapter(BankAdapter):
    def parse(self, raw_content: str, **options) -> ParseResult:
        category = options.get('category', 'UNKNOWN')
        records, errors = self._parse_html(raw_content, category)
        return ParseResult(records=records, errors=errors)

# Now you can substitute:
adapter: BankAdapter = CBEAdapter()  # or DBEAdapter()
result = adapter.parse(content)  # Same interface!
```

**Analysis**: ❌ **NEEDS IMPROVEMENT** - No formal base class, inconsistent signatures

---

### ✅ **I - Interface Segregation Principle**

**Definition**: Clients shouldn't depend on interfaces they don't use.

#### **Where It's Applied:**

**1. AdapterRecord** - Only required fields
```python
@dataclass
class AdapterRecord:
    # REQUIRED (all adapters must provide)
    source_currency_code: str
    effective_date_basis: str
    category: str
    
    # OPTIONAL (adapters provide if available)
    currency_name: Optional[str] = None
    buying_rate: Optional[Decimal] = None
    selling_rate: Optional[Decimal] = None
    source_record_key: Optional[str] = None
    # ...
```

**Why this is good:**
- Type A adapters (CBE) provide stable IDs → use `source_record_key`
- Type F adapters (DBE) don't have IDs → leave `source_record_key = None`
- Each adapter only implements what it can provide

**2. Pipeline Functions** - Small, focused interfaces
```python
# Each function has minimal interface
def validate(record: AdapterRecord) -> tuple[ValidationStatus, list]:
    # Only needs record

def compute_fingerprint(record: AdapterRecord, source_id: int) -> str:
    # Only needs record + source_id

# Not: validate(record, source_id, run_id, conn, config, ...)  ← BAD
```

**Analysis**: ✅ **GOOD** - Interfaces are lean and focused

---

### ⚠️ **D - Dependency Inversion Principle**

**Definition**: Depend on abstractions, not concretions.

#### **Where It's Violated:**

**1. Direct Database Access**
```python
# scheduler/runner.py
import psycopg2

def run_source(conn, source_id):  # conn is psycopg2 connection
    cursor = conn.cursor()
    cursor.execute("SELECT ...")  # Direct SQL
```

**Problem**: Tightly coupled to PostgreSQL. Cannot:
- Swap to MySQL, SQLite for testing
- Mock database for unit tests
- Use ORM if needed later

**Better (Dependency Inversion):**
```python
# Define abstraction
class RateRepository(ABC):
    @abstractmethod
    def get_current_rates(self, source_id: int) -> list[Rate]:
        pass
    
    @abstractmethod
    def save_observation(self, obs: Observation) -> int:
        pass

# Concrete implementation
class PostgresRateRepository(RateRepository):
    def __init__(self, conn):
        self.conn = conn
    
    def get_current_rates(self, source_id: int):
        cursor = self.conn.cursor()
        cursor.execute("SELECT ...")
        return [self._map_row(r) for r in cursor.fetchall()]

# Now depend on abstraction:
def run_source(repo: RateRepository, source_id: int):
    rates = repo.get_current_rates(source_id)  # Abstraction!

# Testing:
class InMemoryRateRepository(RateRepository):
    def __init__(self):
        self.rates = []
    
    def get_current_rates(self, source_id):
        return [r for r in self.rates if r.source_id == source_id]
```

**2. Pipeline Functions** - Hard to test
```python
# pipeline/deduplicate.py
def classify_observation(conn, record, ...):  # Needs real DB connection
    cursor = conn.cursor()
    cursor.execute("SELECT ...")  # Direct SQL
```

**Problem**: Cannot unit test without real PostgreSQL

**Analysis**: ⚠️ **NEEDS IMPROVEMENT** - Tightly coupled to PostgreSQL

---

## OOP Concepts

### 📊 **Current State: Procedural with Data Classes**

This codebase is **mostly procedural** with dataclasses for structure:

```python
# Functional/Procedural style
@dataclass
class AdapterRecord:  # Data structure (no behavior)
    source_currency_code: str
    buying_rate: Optional[Decimal]

def validate(record: AdapterRecord) -> tuple:  # Function operates on data
    # validation logic
```

vs **Object-Oriented style**:
```python
class ExchangeRate:  # Data + Behavior together
    def __init__(self, currency_code, buying_rate):
        self.currency_code = currency_code
        self.buying_rate = buying_rate
    
    def validate(self) -> ValidationResult:  # Method (behavior)
        # validation logic
    
    def is_valid(self) -> bool:
        return self.validate().status == "valid"
```

### ✅ **What's Present:**

**1. Encapsulation** (via modules)
```python
# pipeline/validate.py
def _check_rate(value, field_name, messages):  # Private function (by convention)
    # internal helper

def validate(record):  # Public API
    # uses _check_rate internally
```

**2. Data Abstraction** (via dataclasses)
```python
@dataclass
class AdapterRecord:
    source_currency_code: str
    buying_rate: Optional[Decimal]
    # Clean interface to complex data
```

### ❌ **What's Missing:**

**1. No Inheritance Hierarchy**
```python
# Could have:
class BankAdapter(ABC):
    @abstractmethod
    def parse(self, content: str) -> ParseResult:
        pass
    
    def fetch(self, url: str) -> str:  # Common behavior
        # shared fetching logic

class JSONAdapter(BankAdapter):  # Inheritance
    def parse(self, content: str):
        data = json.loads(content)
        return self._parse_json(data)

class HTMLAdapter(BankAdapter):
    def parse(self, content: str):
        soup = BeautifulSoup(content)
        return self._parse_html(soup)
```

**2. No Polymorphism**
```python
# Could have:
adapters: list[BankAdapter] = [
    CBEAdapter(),
    DBEAdapter(),
    RammisAdapter(),
]

for adapter in adapters:
    result = adapter.parse(content)  # Polymorphic call
```

**3. Limited Encapsulation** (data + behavior separated)
```python
# Current: Data and behavior separate
record = AdapterRecord(...)  # Data
status, msgs = validate(record)  # Behavior is external

# Could be:
rate = ExchangeRate(...)  # Data + behavior
status, msgs = rate.validate()  # Behavior is internal
```

**Analysis**: ⚠️ **FUNCTIONAL/PROCEDURAL** - Not wrong, but not OOP-heavy

---

## Design Patterns

### ✅ **Patterns Currently Used**

#### **1. Adapter Pattern** 🎯
```python
# Problem: 32 banks, 7 different formats
# Solution: Each bank adapter converts to common AdapterRecord

# Target interface (what system expects)
AdapterRecord(
    source_currency_code="USD",
    buying_rate=Decimal("160.23"),
    ...
)

# Adaptee 1: CBE JSON
{"id": "...", "ExchangeRate": [...]}
→ cbe/adapter.parse() → AdapterRecord

# Adaptee 2: DBE HTML
<table><tr><td>USD</td><td>160.23</td></tr></table>
→ dbe/adapter.parse() → AdapterRecord

# All 32 banks → same AdapterRecord interface
```

**Where**: `adapters/*/adapter.py`

---

#### **2. Pipeline Pattern** 🔄
```python
# Sequential stages, each transforms data
Input (AdapterRecord)
  ↓
Validate → (status, messages)
  ↓
Normalize → (clean values)
  ↓
Fingerprint → (hash)
  ↓
Identity → (key, status)
  ↓
Deduplicate → (action)
  ↓
Persist → (observation_id)
```

**Where**: `pipeline/*.py`, orchestrated in `pipeline/ingest.py`

---

#### **3. Strategy Pattern** (implicit)
```python
# Different strategies for identity determination
def build_identity(record, source_id):
    if record.source_record_key and record.source_published_date:
        return confirmed_identity_strategy()  # Strongest
    elif record.source_published_date:
        return published_date_strategy()      # Medium
    elif record.collection_date_fallback:
        return fallback_strategy()            # Weak
    else:
        return ambiguous_strategy()           # Cannot identify
```

**Where**: `pipeline/identity.py`

---

#### **4. Template Method Pattern** (informal)
```python
# All adapters follow same template:
def parse(raw_content):
    # 1. Parse format (varies by adapter)
    data = _parse_format(raw_content)
    
    # 2. Extract records (varies)
    records = _extract_records(data)
    
    # 3. Map to AdapterRecord (same structure)
    return [AdapterRecord(...) for r in records]

# Each adapter implements steps differently, but structure is same
```

**Where**: All adapters in `adapters/*/adapter.py`

---

### ⚠️ **Patterns That Could Be Added**

#### **1. Factory Pattern**
```python
# Current: Manual adapter selection
if source_key == "cbe_api":
    import adapters.cbe.adapter as adapter
elif source_key == "dbe_html":
    import adapters.dbe.adapter as adapter

# Better: Factory
class AdapterFactory:
    _adapters = {
        "cbe_api": CBEAdapter,
        "dbe_html": DBEAdapter,
        "rammis_api": RammisAdapter,
    }
    
    @classmethod
    def create(cls, source_key: str) -> BankAdapter:
        adapter_class = cls._adapters.get(source_key)
        if not adapter_class:
            raise ValueError(f"Unknown adapter: {source_key}")
        return adapter_class()

# Usage:
adapter = AdapterFactory.create("cbe_api")
result = adapter.parse(content)
```

---

#### **2. Repository Pattern**
```python
# Current: Direct SQL everywhere
cursor = conn.cursor()
cursor.execute("INSERT INTO rate_observation ...")

# Better: Repository
class RateObservationRepository:
    def save(self, observation: Observation) -> int:
        # SQL logic here
    
    def find_current_by_key(self, key: str) -> Optional[Observation]:
        # SQL logic here
    
    def find_by_source(self, source_id: int) -> list[Observation]:
        # SQL logic here

# Usage:
repo = RateObservationRepository(conn)
obs_id = repo.save(observation)  # Clean API, no SQL in business logic
```

---

#### **3. Observer Pattern** (for alerting)
```python
# Current: Manual alert checking
def check_alerts(conn):
    failed = check_failed_runs(conn)
    stale = check_stale_rates(conn)
    # etc.

# Better: Observer pattern
class AlertObserver(ABC):
    @abstractmethod
    def on_collection_failed(self, event: CollectionFailedEvent):
        pass

class EmailAlertObserver(AlertObserver):
    def on_collection_failed(self, event):
        send_email(f"Source {event.source_id} failed")

class SlackAlertObserver(AlertObserver):
    def on_collection_failed(self, event):
        post_to_slack(f"🚨 {event.source_id} failed")

# System publishes events:
class CollectionRunner:
    def __init__(self):
        self.observers: list[AlertObserver] = []
    
    def run_source(self, source_id):
        try:
            # collection logic
        except Exception as e:
            event = CollectionFailedEvent(source_id, e)
            self._notify(event)
    
    def _notify(self, event):
        for observer in self.observers:
            observer.on_collection_failed(event)
```

---

#### **4. Command Pattern** (for change management)
```python
# Current: Direct commits
def commit_correction(conn, old_id, new_id, actor, reason):
    # SQL to update is_current, set supersedes_id, etc.

# Better: Command pattern
class Command(ABC):
    @abstractmethod
    def execute(self):
        pass
    
    @abstractmethod
    def undo(self):
        pass

class ApplyCorrectionCommand(Command):
    def __init__(self, repo, old_id, new_id, actor, reason):
        self.repo = repo
        self.old_id = old_id
        self.new_id = new_id
        self.actor = actor
        self.reason = reason
    
    def execute(self):
        self.repo.supersede_observation(self.old_id, self.new_id)
        self.repo.log_correction(self.actor, self.reason)
    
    def undo(self):
        self.repo.restore_observation(self.old_id)

# Usage:
command = ApplyCorrectionCommand(repo, old_id, new_id, "admin", "typo fix")
command.execute()  # Apply
command.undo()     # Rollback if needed
```

---

## Clean Code Principles

### ✅ **What's Done Well**

#### **1. Meaningful Names**
```python
# GOOD: Clear, descriptive names
def compute_fingerprint(record, source_id):
    # I know exactly what this does

def normalize_currency_code(raw):
    # Clear transformation

VALID_CATEGORIES = frozenset({"cash", "transactional", ...})
# Constant naming convention (SCREAMING_SNAKE_CASE)
```

#### **2. Small Functions**
```python
# GOOD: Each function does ONE thing
def _check_rate(value, field_name, messages):
    """Returns True if value is valid (positive Decimal or None)."""
    if value is None:
        return True
    if not isinstance(value, Decimal):
        messages.append(...)
        return False
    if value == Decimal(0):
        messages.append(...)
        return False
    if value < Decimal(0):
        messages.append(...)
        return False
    return True
# ~15 lines, single responsibility
```

#### **3. Comments Explain WHY, Not WHAT**
```python
# GOOD: Comments explain reasoning
# ADR-007: For ambiguous observations, dedupe on value equality only
if identity_status == IdentityStatus.AMBIGUOUS:
    return _dedupe_by_fingerprint(conn, fingerprint)

# GOOD: Docstring explains contract
"""
Returns (logical_observation_key: str | None, identity_status: IdentityStatus).

Key structure (when identifiable):
    "<source_id>:<source_currency_code>:<category>:<effective_date>"
"""
```

#### **4. DRY (Don't Repeat Yourself)**
```python
# GOOD: Reusable normalization
def normalize_rate(raw):
    # Used by ALL adapters
    # Single source of truth for rate normalization

# Adapters just call it:
buying = normalize_rate(item.get("cashBuying"))
selling = normalize_rate(item.get("cashSelling"))
```

#### **5. Error Handling**
```python
# GOOD: Explicit error cases
def normalize_rate(raw) -> Optional[Decimal]:
    if raw is None:
        return None
    # ...
    try:
        d = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"Cannot parse rate value: {raw!r}")
    if d < Decimal(0):
        raise ValueError(f"Negative rate value: {raw!r}")
    return d
```

---

### ⚠️ **What Could Improve**

#### **1. Magic Numbers/Strings**
```python
# CURRENT: Magic strings
if record.effective_date_basis == "source_published":  # String literal repeated
    ...

# BETTER: Constants
class DateBasis(Enum):
    SOURCE_PUBLISHED = "source_published"
    SOURCE_INFERRED = "source_inferred"
    COLLECTION_FALLBACK = "collection_date_fallback"

if record.effective_date_basis == DateBasis.SOURCE_PUBLISHED:
    # Type-safe, autocomplete works
```

#### **2. Long Parameter Lists**
```python
# CURRENT: Many parameters
def insert_observation(conn, source_id, run_id, currency_code, category, 
                       buying, selling, effective_date, date_basis, 
                       validation_status, identity_status, logical_key, 
                       fingerprint, source_key, pub_key):
    # 14 parameters! Hard to remember order

# BETTER: Parameter object
@dataclass
class ObservationData:
    source_id: int
    run_id: int
    currency_code: str
    category: str
    # ... all fields

def insert_observation(conn, data: ObservationData):
    # Single parameter, self-documenting
```

#### **3. God Objects/Functions**
```python
# CURRENT: pipeline/ingest.py does too much
def ingest(conn, records, source_id, run_id, fetched_at):
    # 100+ lines
    # Validates, normalizes, fingerprints, identifies, deduplicates, persists
    # Handles candidates, counts, errors
    # Too many responsibilities

# BETTER: Smaller, focused functions
def ingest(conn, records, source_id, run_id, fetched_at):
    processor = RecordProcessor(conn, source_id, run_id)
    for record in records:
        processor.process(record)
    return processor.get_results()
```

#### **4. Nested Conditionals**
```python
# CURRENT: Deep nesting
if record.source_record_key:
    if record.effective_date is not None:
        if record.effective_date_basis in ("source_published", "source_inferred"):
            key = f"{source_id}:{record.source_record_key}:{category}"
            return key, IdentityStatus.CONFIRMED

# BETTER: Early returns (guard clauses)
if not record.source_record_key:
    return _try_next_strategy(record)

if record.effective_date is None:
    return _try_next_strategy(record)

if record.effective_date_basis not in ("source_published", "source_inferred"):
    return _try_next_strategy(record)

# Happy path at top level (less indentation)
key = f"{source_id}:{record.source_record_key}:{category}"
return key, IdentityStatus.CONFIRMED
```

---

## Strengths

### 🏆 **What This Codebase Does Exceptionally Well**

1. **Separation of Concerns**
   - Clear boundaries: adapters, pipeline, database, API
   - Each module has single purpose

2. **Pure Functions** (pipeline stages)
   - No side effects
   - Easy to test
   - Predictable behavior

3. **Immutability** (data model)
   - Never overwrite observations
   - Audit trail preserved

4. **Documentation**
   - ADRs explain WHY
   - Docstrings explain contracts
   - Comments explain tricky logic

5. **Testing**
   - 429 tests
   - Good coverage of edge cases
   - Fixtures for reproducibility

6. **Database as Enforcer**
   - Constraints prevent invalid states
   - Business rules in schema

---

## Improvement Opportunities

### 🎯 **Areas for Refactoring (Keeping Same Functionality)**

#### **Priority 1: Add Abstractions (SOLID violations)**
- [ ] Define `BankAdapter` base class (Liskov Substitution)
- [ ] Define `RateRepository` interface (Dependency Inversion)
- [ ] Define `PipelineStage` interface (Open/Closed)

#### **Priority 2: Reduce Coupling**
- [ ] Extract database access to repositories
- [ ] Remove direct `psycopg2` dependencies from business logic
- [ ] Use dependency injection

#### **Priority 3: Improve Testability**
- [ ] Make pipeline stages classes (easier to mock)
- [ ] Add in-memory repository for tests
- [ ] Reduce reliance on real PostgreSQL

#### **Priority 4: Clean Code Refinements**
- [ ] Extract constants for magic strings
- [ ] Use parameter objects for long argument lists
- [ ] Break up large functions (e.g., `ingest()`)
- [ ] Add more type hints

---

## Learning Path

### 📚 **How to Use This Codebase to Learn**

#### **Phase 1: Understand Current Design (2 weeks)**
1. Trace one request end-to-end (bank → adapter → pipeline → DB → API)
2. Read all ADRs in `docs/decisions/`
3. Run tests and see what breaks when you change things
4. Draw architecture diagrams

#### **Phase 2: Identify Patterns (1 week)**
1. Find all uses of Adapter Pattern
2. Identify where SOLID is applied
3. Identify where SOLID is violated
4. List all design patterns (actual + missing)

#### **Phase 3: Propose Refactorings (2 weeks)**
1. Create refactoring plan for ONE pattern violation
2. Write tests to lock in current behavior
3. Refactor step-by-step (small commits)
4. Verify tests still pass

#### **Phase 4: Practice (ongoing)**
1. Add new bank adapter (follow existing patterns)
2. Add new pipeline stage (extend system)
3. Implement missing patterns (Factory, Repository)
4. Measure improvement (cyclomatic complexity, test coverage)

---

## Summary

### ✅ **Strengths**
- Excellent separation of concerns
- Pure, testable functions
- Good documentation
- Strong database design

### ⚠️ **Improvement Areas**
- Lacks formal abstractions (interfaces, base classes)
- Procedural rather than OOP
- Tight coupling to PostgreSQL
- Some SOLID violations (Liskov, Dependency Inversion)

### 🎯 **Key Takeaway**
This codebase demonstrates **functional/procedural** style well, but could be refactored to demonstrate **object-oriented** principles more clearly **without changing functionality**.

**Perfect for learning**: You can see both what works and what could improve!

---

## Next Steps

Want to dive deeper into any section? I can:
1. Create a refactoring plan for a specific pattern
2. Show before/after examples for SOLID violations
3. Create a learning exercise for a specific principle
4. Generate a checklist for improving code quality

**Which area interests you most?**
