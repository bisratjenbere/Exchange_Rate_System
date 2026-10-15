# Design Document: Adapter Base Classes and HTTP Abstraction

## Overview

This design introduces abstraction layers to reduce code duplication across 21 bank adapters in the Ethiopian Bank Exchange Rate system while maintaining the explicitness and maintainability that comes from having separate adapter modules.

### Problem Statement

The current system has 31 bank adapters parsing exchange rates from different formats (JSON, HTML tables, HTML text). While the decision to maintain 31 separate adapters is architecturally sound (see ADAPTER_GENERALIZATION_ANALYSIS.md), there is significant code duplication:

- JSON parsing boilerplate (~40 lines per JSON adapter)
- HTML table extraction logic (~60 lines per HTML adapter)
- HTTP fetching with retries (~50 lines when needed)
- Common utility methods (`_safe_rate`, date parsing, etc.)

### Solution Approach

Introduce three layers of abstraction:

1. **Base Adapter Interface** - Common protocol for all adapters (BankAdapter abstract class)
2. **Type-Specific Base Classes** - Format-specific parsing (JSONAdapter, HTMLTableAdapter, HTMLTextAdapter)
3. **HTTP Client Abstraction** - Injectable HTTP fetching (HttpClient interface with RequestsHttpClient, MockHttpClient, FileHttpClient)

### Benefits

- **30% code reduction** - Eliminates duplicate parsing infrastructure
- **Uniform interface** - All adapters follow Liskov Substitution Principle
- **Testability** - Mock HTTP client enables fast tests without network calls
- **Maintainability** - Bank-specific logic separated from parsing infrastructure
- **Backward compatibility** - Existing function-based API preserved

### Non-Goals

- Config-driven adapter generation
- YAML-based bank definitions
- Merging the 31 adapters into fewer modules

## Architecture

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Pipeline System                         │
│                   (ingest, normalize, etc.)                  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ Uses ParseResult
                       ↓
┌─────────────────────────────────────────────────────────────┐
│                  BankAdapter Interface                       │
│         abstract parse(raw_content) → ParseResult           │
│         abstract get_source_url() → str                     │
└──────────────────────┬──────────────────────────────────────┘
                       │
            ┌──────────┴──────────┬──────────────┐
            ↓                     ↓              ↓
┌───────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│   JSONAdapter     │  │ HTMLTableAdapter │  │ HTMLTextAdapter  │
│                   │  │                  │  │                  │
│ parse() handles   │  │ parse() extracts │  │ parse() extracts │
│ JSON decoding     │  │ HTML tables      │  │ normalized text  │
│                   │  │                  │  │                  │
│ calls abstract:   │  │ calls abstract:  │  │ calls abstract:  │
│ _process_data()   │  │ _process_tables()│  │_extract_from_text│
└─────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
          │                     │                      │
          └─────────────────────┴──────────────────────┘
                                 │
                    ┌────────────┴────────────┬──────────────┐
                    ↓                         ↓              ↓
          ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
          │   CBEAdapter     │    │   DBEAdapter     │    │  AhaduAdapter    │
          │  (Type A: JSON)  │    │ (Type F: Table)  │    │ (Type G: Text)   │
          │                  │    │                  │    │                  │
          │ implements:      │    │ implements:      │    │ implements:      │
          │ _process_data()  │    │ _process_tables()│    │_extract_from_text│
          └──────────────────┘    └──────────────────┘    └──────────────────┘
```

### HTTP Client Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Adapter / Scheduler                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ fetch(url) → HttpResponse
                       ↓
┌─────────────────────────────────────────────────────────────┐
│                  HttpClient Interface                        │
│            abstract fetch(url, **options)                    │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────┴──────────────┬──────────────┐
         ↓                            ↓              ↓
┌──────────────────┐      ┌──────────────────┐    ┌──────────────────┐
│RequestsHttpClient│      │  MockHttpClient  │    │ FileHttpClient   │
│                  │      │                  │    │                  │
│ Production impl  │      │ Testing impl     │    │ Dev/testing impl │
│ - Retries        │      │ - Pre-config     │    │ - Fixture files  │
│ - Timeout        │      │   responses      │    │ - No network     │
│ - SSL control    │      │ - Call tracking  │    │ - Real responses │
└──────────────────┘      └──────────────────┘    └──────────────────┘
```

### Data Flow

```
Raw Bank Data (JSON/HTML)
         │
         ↓
    HttpClient.fetch()
         │
         ↓
    raw_content: str
         │
         ↓
   Adapter.parse(raw_content)
         │
    ┌────┴─────┐
    │ Type-specific parsing
    │ - JSONAdapter: json.loads()
    │ - HTMLTableAdapter: BeautifulSoup + find_all("table")
    │ - HTMLTextAdapter: BeautifulSoup + get_text()
    └────┬─────┘
         │
         ↓
   Bank-specific extraction
   (_process_data, _process_tables, _extract_from_text)
         │
         ↓
   ParseResult(records, errors, warnings)
         │
         ↓
   List[AdapterRecord]
         │
         ↓
   Pipeline (normalize, deduplicate, identity, fingerprint)
```

## Components and Interfaces

### BankAdapter (Abstract Base Class)

**Purpose**: Common interface for all bank adapters

**Location**: `adapters/base.py`

**Interface**:
```python
class BankAdapter(ABC):
    # Abstract methods (must implement)
    @abstractmethod
    def parse(self, raw_content: str, **options) -> ParseResult:
        """Convert raw bank data to AdapterRecords"""
        pass
    
    @abstractmethod
    def get_source_url(self) -> str:
        """Return bank's data source URL"""
        pass
    
    # Optional overrides
    def get_adapter_key(self) -> str:
        """Unique adapter identifier (default: class name → snake_case)"""
        pass
    
    def schema_fingerprint(self, raw_content: str) -> Optional[str]:
        """Structural hash for change detection"""
        return None
    
    def requires_category(self) -> bool:
        """Whether adapter needs category injection (Type F adapters)"""
        return False
    
    # Helper utilities
    def _safe_rate(self, raw) -> Optional[Decimal]:
        """Safely normalize rate value"""
        pass
    
    def _parse_iso_date(self, date_str: str) -> Optional[date]:
        """Parse ISO date string (YYYY-MM-DD)"""
        pass
    
    def _rate_text(self, buying, selling) -> str:
        """Format buying/selling for source_rate_text"""
        pass
```

**Design Rationale**:
- Abstract base ensures all adapters follow the same protocol (Liskov Substitution)
- Helper methods reduce duplication of common transformations
- Optional methods (`schema_fingerprint`, `requires_category`) allow adapters to opt-in to features
- No state stored in base class - purely interface + utilities

### JSONAdapter (Type-Specific Base)

**Purpose**: Common JSON parsing for JSON-based adapters

**Location**: `adapters/base.py`

**Interface**:
```python
class JSONAdapter(BankAdapter):
    def parse(self, raw_content: str, **options) -> ParseResult:
        """
        1. Parse JSON (raise ValueError if invalid)
        2. Call _process_data() with parsed data
        3. Return ParseResult
        """
        pass
    
    @abstractmethod
    def _process_data(self, data, **options) -> ParseResult:
        """Bank-specific extraction from parsed JSON"""
        pass
    
    def schema_fingerprint(self, raw_content: str) -> str:
        """Default: hash of top-level JSON keys"""
        pass
```

**Design Rationale**:
- Handles JSON parsing once in base class
- Bank adapter only implements data extraction logic
- Default schema_fingerprint covers common case (top-level keys)
- ValueError on invalid JSON makes error handling explicit

### HTMLTableAdapter (Type-Specific Base)

**Purpose**: Common HTML table extraction for table-based adapters

**Location**: `adapters/base.py`

**Interface**:
```python
class HTMLTableAdapter(BankAdapter):
    def parse(self, raw_content: str, **options) -> ParseResult:
        """
        1. Parse HTML with BeautifulSoup
        2. Find all <table> elements
        3. If no tables, return error in ParseResult
        4. Call _process_tables() with soup and tables
        5. Return ParseResult
        """
        pass
    
    @abstractmethod
    def _process_tables(self, soup: BeautifulSoup, tables: list, **options) -> ParseResult:
        """Bank-specific table row extraction"""
        pass
    
    def schema_fingerprint(self, raw_content: str) -> str:
        """Default: hash of table count + header cells"""
        pass
```

**Design Rationale**:
- HTML parsing and table finding handled once
- Bank adapter gets BeautifulSoup object for date extraction from other elements
- No tables = error in ParseResult (non-fatal, allows caller to decide)
- Default fingerprint captures table structure changes

### HTMLTextAdapter (Type-Specific Base)

**Purpose**: Common HTML text extraction for regex-based adapters

**Location**: `adapters/base.py`

**Interface**:
```python
class HTMLTextAdapter(BankAdapter):
    def parse(self, raw_content: str, **options) -> ParseResult:
        """
        1. Parse HTML with BeautifulSoup
        2. Extract text with get_text(" ", strip=True)
        3. Normalize whitespace (join with single spaces)
        4. Call _extract_from_text() with text and soup
        5. Return ParseResult
        """
        pass
    
    @abstractmethod
    def _extract_from_text(self, text: str, soup: BeautifulSoup, **options) -> ParseResult:
        """Bank-specific regex pattern matching"""
        pass
```

**Design Rationale**:
- Text extraction and normalization handled once
- Normalized text makes regex patterns simpler
- Soup object still available for structured date extraction
- Bank adapter focuses solely on regex patterns and business logic

### HttpClient (Abstract Interface)

**Purpose**: Abstraction for HTTP fetching, enabling testing

**Location**: `http/client.py`

**Interface**:
```python
class HttpClient(ABC):
    @abstractmethod
    def fetch(self, url: str, **options) -> HttpResponse:
        """
        Fetch content from URL.
        
        Options:
        - ssl_verify: bool
        - timeout: int
        - post_data: dict
        - headers: dict
        
        Returns: HttpResponse
        """
        pass

class HttpResponse:
    content: str
    status_code: int
    url: str
    error: Optional[str]
    
    def is_success(self) -> bool:
        """True if status 200 and no error"""
        pass
```

**Design Rationale**:
- Dependency inversion - adapters depend on interface, not implementation
- HttpResponse is immutable data class
- `is_success()` simplifies error checking
- Options dict allows extensibility without changing interface

### RequestsHttpClient (Production Implementation)

**Purpose**: Production HTTP client with retries and timeout

**Location**: `http/client.py`

**Key Features**:
- Automatic retries with exponential backoff (default: 2 retries, 2s delay)
- Configurable timeout (default: 15s)
- SSL verification control
- POST support
- Custom headers
- User-Agent header (default: "EthiopianBankRateCollector/1.0")

**Configuration**:
```python
RequestsHttpClient(
    user_agent="EthiopianBankRateCollector/1.0",
    timeout=15,
    max_retries=2,
    retry_delay=2.0
)
```

**Design Rationale**:
- Retries handle transient network failures
- Exponential backoff prevents overwhelming failing servers
- Configurable but sensible defaults
- All options optional - zero-config for common case

### MockHttpClient (Test Implementation)

**Purpose**: Mock HTTP client for fast tests without network

**Location**: `http/client.py`

**Key Features**:
- Pre-configured URL → response mappings
- Pattern matching (exact URL or substring)
- Call tracking (fetch_count, last_url)
- Runtime response configuration

**Usage**:
```python
mock = MockHttpClient({
    "combanketh.et": '{"Date": "2026-10-13", ...}',
    "dbe.com.et": '<table><tr>...</tr></table>'
})

response = mock.fetch("https://combanketh.et/api")
assert response.is_success()
assert mock.fetch_count == 1
```

**Design Rationale**:
- No network calls = fast tests
- Pattern matching allows flexible URL matching
- Call tracking enables test assertions
- Simple dict interface

### FileHttpClient (Development Implementation)

**Purpose**: Load responses from fixture files for development

**Location**: `http/client.py`

**Key Features**:
- Loads responses from fixtures directory
- Maps URL domain to filename (e.g., `combanketh_et.json`)
- Tries both .html and .json extensions
- Returns 404 if fixture not found

**Usage**:
```python
client = FileHttpClient(fixtures_dir="fixtures")
response = client.fetch("https://combanketh.et/api")
# Loads from: fixtures/combanketh_et.json or .html
```

**Design Rationale**:
- Test with real bank responses without network
- Fixtures committed to repo for reproducibility
- Simple domain → filename mapping
- Supports iterative development

## Data Models

### ParseResult

**Purpose**: Uniform return type from all adapters

```python
@dataclass
class ParseResult:
    records: list[AdapterRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    
    def is_success(self) -> bool:
        """True if at least one record parsed"""
        return len(self.records) > 0
    
    def add_error(self, error: str):
        """Add error message"""
        self.errors.append(error)
    
    def add_warning(self, warning: str):
        """Add warning message"""
        self.warnings.append(warning)
```

**Fields**:
- `records`: Successfully parsed AdapterRecords
- `errors`: Non-fatal error messages (e.g., "currency:USD:invalid rate")
- `warnings`: Advisory messages (e.g., "date missing, using collection_date_fallback")

**Design Rationale**:
- Replaces tuple return `(records, errors)` with structured type
- Immutable data class (safe to pass around)
- `is_success()` centralizes success check logic
- Helper methods (`add_error`, `add_warning`) improve ergonomics
- Empty lists as defaults avoid None checks

### HttpResponse

**Purpose**: Result from HTTP fetch operation

```python
@dataclass
class HttpResponse:
    content: str
    status_code: int
    url: str
    error: Optional[str] = None
    
    def is_success(self) -> bool:
        return self.status_code == 200 and self.error is None
```

**Fields**:
- `content`: Response body (empty string if error)
- `status_code`: HTTP status code (0 if connection error)
- `url`: Requested URL (for debugging)
- `error`: Error message if fetch failed (None on success)

**Design Rationale**:
- Immutable data class
- Always returns HttpResponse (never raises exceptions)
- `is_success()` checks both status and error
- Non-success responses still contain content (e.g., 404 page HTML)

### AdapterRecord (Unchanged)

The existing `AdapterRecord` data class from `domain/records.py` remains unchanged. This refactoring only changes *how* AdapterRecords are produced, not the records themselves.

**Key Fields** (for reference):
- `source_currency_code`: e.g., "USD"
- `category`: "cash" | "transactional" | "UNKNOWN"
- `buying_rate`: Decimal or None
- `selling_rate`: Decimal or None
- `effective_date`: date or None
- `effective_date_basis`: "source_published" | "collection_date_fallback"
- `source_record_key`: Stable ID from bank (if available)
- `source_publication_key`: Publication/date ID from bank (if available)
- `raw_excerpt`: Dict capturing original data
- `mapping_notes`: List of clarifications (e.g., "zero_equals_not_offered:TO_VERIFY")

## Reference Adapter Implementations

### CBE Adapter (JSONAdapter Example)

**Before** (150 lines):
```python
def parse(raw_json: str) -> list:
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"CBE: JSON parse error: {exc}")
    
    if not isinstance(data, list):
        raise ValueError(f"CBE: expected JSON array, got {type(data).__name__}")
    
    records = []
    for pub in data:
        records.extend(_parse_publication(pub))
    return records

# ... rest of parsing logic
```

**After** (105 lines, -30%):
```python
class CBEAdapter(JSONAdapter):
    def get_source_url(self) -> str:
        return "https://combanketh.et/cbeapi/daily-exchange-rates/"
    
    def get_adapter_key(self) -> str:
        return "cbe_api"
    
    def _process_data(self, data, **options) -> ParseResult:
        result = ParseResult()
        
        if not isinstance(data, list):
            raise ValueError(f"CBE: Expected JSON array, got {type(data).__name__}")
        
        for publication in data:
            try:
                records = self._parse_publication(publication)
                result.records.extend(records)
            except Exception as exc:
                result.add_error(f"Publication error: {exc}")
        
        return result
    
    # ... rest of extraction logic (unchanged)
```

**Benefits**:
- JSON parsing moved to base class
- Uniform ParseResult return type
- Clearer structure (extraction logic isolated)

### DBE Adapter (HTMLTableAdapter Example)

**Before** (120 lines):
```python
def parse(raw_html: str, category: str = "UNKNOWN") -> tuple:
    soup = BeautifulSoup(raw_html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return [], ["table_0:missing"]
    
    effective_date = _parse_date_from_description(tables[0])
    records, errors = [], []
    try:
        records = _parse_table(tables[0], category, effective_date)
    except Exception as exc:
        errors.append(f"table_0:{exc}")
    return records, errors

# ... rest of parsing logic
```

**After** (85 lines, -29%):
```python
class DBEAdapter(HTMLTableAdapter):
    def get_source_url(self) -> str:
        return "https://dbe.com.et/"
    
    def get_adapter_key(self) -> str:
        return "dbe_html"
    
    def requires_category(self) -> bool:
        return True  # Type F adapters need category injection
    
    def _process_tables(self, soup: BeautifulSoup, tables: list, **options) -> ParseResult:
        result = ParseResult()
        category = options.get('category', 'UNKNOWN')
        
        effective_date = self._parse_date_from_description(tables[0])
        
        try:
            records = self._parse_table(tables[0], category, effective_date)
            result.records.extend(records)
        except Exception as exc:
            result.add_error(f"table_0: {exc}")
        
        return result
    
    # ... rest of extraction logic (unchanged)
```

**Benefits**:
- HTML parsing and table finding moved to base class
- ParseResult replaces tuple return
- Category handling explicit via `requires_category()`

### Ahadu Adapter (HTMLTextAdapter Example)

**Before** (95 lines):
```python
def parse(raw_html: str, category: str = "UNKNOWN") -> tuple:
    soup = BeautifulSoup(raw_html, "html.parser")
    text = " ".join(soup.get_text(" ", strip=True).split())
    
    effective_date = _extract_date(text)
    date_basis = "source_published" if effective_date else "collection_date_fallback"
    
    records, errors = [], []
    for m in _RATE_RE.finditer(text):
        # ... regex extraction
    
    return records, errors

# ... rest of parsing logic
```

**After** (70 lines, -26%):
```python
class AhaduAdapter(HTMLTextAdapter):
    def get_source_url(self) -> str:
        return "https://ahadubank.com/"
    
    def get_adapter_key(self) -> str:
        return "ahadu_html"
    
    def requires_category(self) -> bool:
        return True  # Type G adapters need category
    
    def _extract_from_text(self, text: str, soup: BeautifulSoup, **options) -> ParseResult:
        result = ParseResult()
        category = options.get('category', 'UNKNOWN')
        
        effective_date = self._extract_date(text)
        date_basis = "source_published" if effective_date else "collection_date_fallback"
        
        for match in _RATE_RE.finditer(text):
            # ... regex extraction (unchanged)
        
        return result
    
    # ... rest of extraction logic (unchanged)
```

**Benefits**:
- HTML parsing and text extraction moved to base class
- Whitespace normalization handled automatically
- Focus on regex patterns and business logic

## Backward Compatibility Strategy

### Module-Level Function Wrappers

To maintain backward compatibility, existing adapters provide module-level function wrappers:

```python
# In adapters/cbe/adapter.py

class CBEAdapter(JSONAdapter):
    # ... class implementation

# Backward compatibility wrapper
def parse(raw_json: str) -> list:
    """
    Old function API (for backward compatibility).
    New code should use CBEAdapter().parse()
    """
    adapter = CBEAdapter()
    result = adapter.parse(raw_json)
    
    if result.errors:
        raise ValueError(result.errors[0])
    
    return result.records

def schema_fingerprint(raw_json: str) -> str:
    """Old function API (for backward compatibility)"""
    return CBEAdapter().schema_fingerprint(raw_json)
```

### Migration Path

**Phase 1**: Add base classes, refactor 3 reference adapters with wrappers
- All existing code continues to work
- Tests pass without modification
- New adapters can use new API

**Phase 2**: Update remaining adapters one at a time
- Each adapter adds class + wrapper
- Tests continue to pass
- No big-bang migration required

**Phase 3**: Update calling code to use class API
- Gradual migration of pipeline code
- Can remove wrappers after migration complete
- Low risk (wrappers ensure correctness)



## Error Handling

### Error Classification

**Fatal Errors** (raise ValueError):
- Invalid JSON in JSONAdapter
- Fundamentally unparseable input
- Schema changes that break parsing logic

**Non-Fatal Errors** (added to ParseResult.errors):
- Missing or invalid rate for specific currency
- Date extraction failure
- Individual record parsing failure

**Warnings** (added to ParseResult.warnings):
- Using collection_date_fallback instead of source date
- Category defaulting to UNKNOWN
- Missing optional fields

### Error Handling Strategy

**Base Class Level**:
```python
class JSONAdapter(BankAdapter):
    def parse(self, raw_content: str, **options) -> ParseResult:
        try:
            data = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            # Fatal: JSON is fundamentally invalid
            raise ValueError(f"{self.__class__.__name__}: JSON parse error: {exc}")
        
        # Continue with bank-specific processing
        return self._process_data(data, **options)
```

**Bank Adapter Level**:
```python
class CBEAdapter(JSONAdapter):
    def _process_data(self, data, **options) -> ParseResult:
        result = ParseResult()
        
        for publication in data:
            try:
                records = self._parse_publication(publication)
                result.records.extend(records)
            except Exception as exc:
                # Non-fatal: record one publication error, continue
                result.add_error(f"Publication {pub.get('id')}: {exc}")
        
        return result
```

**Rationale**:
- Fatal errors = caller cannot proceed (raise exception)
- Non-fatal errors = some data extracted, some failed (add to errors list)
- Caller decides how to handle partial success

### HTTP Client Error Handling

**RequestsHttpClient**:
- All exceptions caught and returned in HttpResponse.error
- Never raises exceptions
- Retry logic handles transient failures
- Returns status_code=0 for connection errors

**Example**:
```python
def fetch(self, url: str, **options) -> HttpResponse:
    for attempt in range(self.max_retries + 1):
        try:
            resp = requests.get(url, ...)
            return HttpResponse(content=resp.text, status_code=resp.status_code, url=url)
        except requests.exceptions.Timeout as e:
            last_error = f"Timeout: {e}"
        except requests.exceptions.ConnectionError as e:
            last_error = f"Connection error: {e}"
    
    # All retries failed
    return HttpResponse(content="", status_code=0, url=url, error=last_error)
```

**Rationale**:
- Uniform error interface (HttpResponse always returned)
- Caller checks `is_success()` instead of catching exceptions
- Simpler control flow in calling code

### Schema Change Detection

**Purpose**: Detect when bank changes their data structure

**Implementation**:
```python
def schema_fingerprint(self, raw_content: str) -> str:
    """
    Return deterministic hash of data structure.
    Different hash = structure changed = human review needed.
    """
    try:
        data = json.loads(raw_content)
        keys = sorted(data[0].keys())  # Top-level keys
        return hashlib.sha256(json.dumps(keys).encode()).hexdigest()
    except Exception:
        return hashlib.sha256(b"adapter:unparseable").hexdigest()
```

**Rationale**:
- Banks change formats without warning
- Schema changes often break parsing logic
- Fingerprint change triggers raw data capture for investigation
- Deterministic hash enables comparison over time

## Testing Strategy

### Overview

This refactoring uses **regression testing** and **equivalence verification** rather than property-based testing. The correctness criterion is: *refactored adapters produce identical outputs to original adapters for the same inputs*.

### Why Property-Based Testing Does NOT Apply

Property-based testing (PBT) is inappropriate for this refactoring because:

1. **Not new functionality** - We're reorganizing existing code, not implementing new algorithms
2. **No input-dependent behavior** - The refactoring doesn't change how inputs map to outputs
3. **No universal properties** - The "property" is structural equivalence, not algorithmic correctness
4. **Wrong tool** - PBT tests "for all inputs X, property P(X) holds". Here, we need "for all existing tests, outputs unchanged"

The appropriate testing strategies are:
- **Regression tests** - All 429 existing tests must pass unchanged
- **Equivalence tests** - Refactored adapters produce identical outputs
- **Unit tests** - Base class functionality works correctly
- **Integration tests** - HTTP client abstraction works end-to-end

### Testing Layers

#### Layer 1: Base Class Unit Tests

**Purpose**: Verify base class infrastructure works correctly

**File**: `tests/test_adapter_bases.py`

**Test Cases**:

```python
class TestJSONAdapter:
    def test_parse_valid_json():
        """JSONAdapter parses valid JSON and calls _process_data"""
    
    def test_parse_invalid_json_raises():
        """JSONAdapter raises ValueError for invalid JSON"""
    
    def test_safe_rate_helper():
        """_safe_rate handles valid/invalid rates correctly"""
    
    def test_default_schema_fingerprint():
        """Default fingerprint hashes JSON keys"""

class TestHTMLTableAdapter:
    def test_parse_finds_tables():
        """HTMLTableAdapter extracts tables and calls _process_tables"""
    
    def test_parse_no_tables_returns_error():
        """HTMLTableAdapter returns error when no tables found"""
    
    def test_default_schema_fingerprint():
        """Default fingerprint hashes table structure"""

class TestHTMLTextAdapter:
    def test_parse_extracts_text():
        """HTMLTextAdapter extracts and normalizes text"""
    
    def test_parse_calls_extract_from_text():
        """HTMLTextAdapter calls abstract method correctly"""

class TestParseResult:
    def test_is_success():
        """is_success() returns True when records present"""
    
    def test_add_error():
        """add_error() appends to errors list"""
    
    def test_add_warning():
        """add_warning() appends to warnings list"""
```

**Coverage Target**: 100% of base class code

#### Layer 2: HTTP Client Unit Tests

**Purpose**: Verify HTTP client implementations

**File**: `tests/test_http_client.py`

**Test Cases**:

```python
class TestRequestsHttpClient:
    def test_fetch_success():
        """Successful fetch returns HttpResponse with is_success=True"""
    
    def test_fetch_retry_on_timeout(mock_requests):
        """Client retries on timeout with exponential backoff"""
    
    def test_fetch_connection_error_returns_error():
        """Connection error returns HttpResponse with error message"""
    
    def test_fetch_non_200_status():
        """Non-200 status returns HttpResponse with is_success=False"""
    
    def test_fetch_post_request():
        """POST requests work when post_data provided"""
    
    def test_fetch_custom_headers():
        """Custom headers are sent correctly"""
    
    def test_fetch_ssl_verification_control():
        """ssl_verify option controls SSL verification"""

class TestMockHttpClient:
    def test_fetch_configured_response():
        """Returns configured response for matching URL"""
    
    def test_fetch_pattern_matching():
        """URL pattern matching works (substring)"""
    
    def test_fetch_tracks_calls():
        """fetch_count and last_url tracked correctly"""
    
    def test_fetch_no_match_returns_404():
        """Non-configured URL returns 404 error"""
    
    def test_configure_response_runtime():
        """configure_response() adds new mock responses"""

class TestFileHttpClient:
    def test_fetch_loads_fixture(tmp_path):
        """Loads fixture file based on URL domain"""
    
    def test_fetch_tries_html_and_json(tmp_path):
        """Tries both .html and .json extensions"""
    
    def test_fetch_missing_fixture_returns_404(tmp_path):
        """Returns 404 when fixture not found"""
```

**Coverage Target**: 100% of HTTP client code

#### Layer 3: Adapter Equivalence Tests

**Purpose**: Verify refactored adapters produce identical outputs to originals

**File**: `tests/test_adapter_equivalence.py`

**Test Strategy**:

For each refactored adapter (CBE, DBE, Ahadu):

```python
def test_cbe_adapter_equivalence():
    """CBE class adapter produces identical output to function adapter"""
    
    # Test data from real bank response
    raw_json = load_fixture("cbe_response.json")
    
    # Old function API
    old_records = cbe_adapter_old.parse(raw_json)
    
    # New class API
    new_result = CBEAdapter().parse(raw_json)
    new_records = new_result.records
    
    # Assert identical outputs
    assert len(new_records) == len(old_records)
    for new, old in zip(new_records, old_records):
        assert new.source_currency_code == old.source_currency_code
        assert new.category == old.category
        assert new.buying_rate == old.buying_rate
        assert new.selling_rate == old.selling_rate
        assert new.effective_date == old.effective_date
        assert new.source_record_key == old.source_record_key
        # ... all fields identical

def test_cbe_adapter_backward_compat():
    """CBE wrapper function maintains old API"""
    
    raw_json = load_fixture("cbe_response.json")
    
    # Old calling code should still work
    records = parse(raw_json)  # Module-level function
    
    assert len(records) > 0
    assert isinstance(records[0], AdapterRecord)
```

**Test Coverage**:
- All fields of AdapterRecord verified for equality
- Edge cases (empty response, invalid data, partial failures)
- Backward compatibility wrappers

#### Layer 4: Regression Tests (Existing)

**Purpose**: Ensure all existing functionality still works

**Strategy**: Run all 429 existing tests without modification

**Test Files**:
- `tests/test_m5_cbe_adapter.py` - CBE adapter tests (MUST pass)
- `tests/test_m4_adib_adapter.py` - ADIB adapter tests (MUST pass)
- `tests/test_m8_wave2_adapters.py` - Wave 2 adapter tests (MUST pass)
- All other adapter tests (MUST pass)

**Success Criteria**:
- 429/429 tests pass
- No test modifications required
- No new test failures introduced

#### Layer 5: Integration Tests with HTTP Client

**Purpose**: Verify adapter + HTTP client work together

**File**: `tests/test_adapter_with_http.py`

**Test Cases**:

```python
def test_cbe_adapter_with_mock_http():
    """CBE adapter + MockHttpClient integration"""
    
    # Configure mock
    mock_http = MockHttpClient()
    mock_http.configure_response("combanketh.et", load_fixture("cbe.json"))
    
    # Fetch and parse
    adapter = CBEAdapter()
    response = mock_http.fetch(adapter.get_source_url())
    
    assert response.is_success()
    
    result = adapter.parse(response.content)
    
    assert result.is_success()
    assert len(result.records) == 2  # cash + transactional for USD
    assert result.records[0].source_currency_code == "USD"

def test_dbe_adapter_with_file_http(tmp_path):
    """DBE adapter + FileHttpClient integration"""
    
    # Create fixture
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    (fixture_dir / "dbe_com_et.html").write_text(load_fixture("dbe.html"))
    
    # Fetch and parse
    file_http = FileHttpClient(fixtures_dir=str(fixture_dir))
    adapter = DBEAdapter()
    
    response = file_http.fetch(adapter.get_source_url())
    assert response.is_success()
    
    result = adapter.parse(response.content, category="transactional")
    assert result.is_success()
    assert len(result.records) > 0
```

**Coverage**: All HTTP client + adapter combinations

### Test Execution Strategy

**Pre-commit**:
```bash
# Run fast unit tests
pytest tests/test_adapter_bases.py tests/test_http_client.py -v
# ~5 seconds
```

**CI Pipeline**:
```bash
# Run all tests
pytest tests/ -v
# ~60 seconds

# Check coverage
pytest tests/ --cov=adapters --cov=http --cov-report=term-missing
# Target: maintain current coverage (~85%)
```

**Deployment Gate**:
```bash
# All 429 tests must pass
pytest tests/ -v | grep "429 passed"
```

### Testing Anti-Patterns to Avoid

❌ **Don't**: Write property-based tests for refactored code
- This is structure refactoring, not algorithm design
- PBT adds complexity without value here

❌ **Don't**: Modify existing tests to use new API
- Tests should verify backward compatibility
- Old API must continue to work

❌ **Don't**: Skip equivalence tests
- "The tests pass" doesn't verify identical outputs
- Subtle differences could break downstream code

✅ **Do**: Use snapshot testing for ParseResult equality
✅ **Do**: Test error paths (invalid JSON, missing tables, etc.)
✅ **Do**: Verify backward compatibility wrappers work

### Test Data Strategy

**Fixtures** (committed to repo):
- `fixtures/cbe_response.json` - Real CBE API response
- `fixtures/dbe_page.html` - Real DBE website HTML
- `fixtures/ahadu_page.html` - Real Ahadu website HTML

**Test Data Principles**:
1. Use real bank responses (anonymize if needed)
2. Include edge cases (empty rates, missing dates, malformed data)
3. Commit fixtures to repo (reproducibility)
4. Update fixtures when bank formats change

### Performance Testing

**Requirement**: Refactored adapters have equivalent or better performance

**Test**:
```python
import time

def test_cbe_adapter_performance():
    """Refactored adapter is not slower than original"""
    
    raw_json = load_large_fixture("cbe_100_records.json")
    
    # Benchmark old implementation
    start = time.time()
    old_records = old_parse(raw_json)
    old_time = time.time() - start
    
    # Benchmark new implementation
    start = time.time()
    new_result = CBEAdapter().parse(raw_json)
    new_time = time.time() - start
    
    # New should be equal or faster
    assert new_time <= old_time * 1.1  # 10% tolerance
```

**Target**: < 1ms overhead for base class method calls

## Migration and Deployment

### Migration Phases

#### Phase 1: Foundation (Week 1)

**Day 1-2**: Create base classes
- Write `adapters/base.py` with all base classes
- Write unit tests for base classes
- Verify tests pass

**Day 3**: Create HTTP client abstraction
- Write `http/client.py` with all implementations
- Write unit tests for HTTP clients
- Verify tests pass

**Day 4-5**: Refactor 3 reference adapters
- CBE (JSONAdapter)
- DBE (HTMLTableAdapter)
- Ahadu (HTMLTextAdapter)
- Add backward compatibility wrappers
- Verify all existing tests still pass (429/429)
- Write equivalence tests

**Verification**:
```bash
pytest tests/ -v | grep "passed"  # Must show 429+ passed
```

#### Phase 2: Remaining Adapters (Week 2)

**Batch 1** (Day 1-2): JSON adapters
- Rammis, ADIB, other JSON-based adapters
- ~5 adapters

**Batch 2** (Day 3-4): HTML table adapters
- Dashen, NIB, other table-based adapters
- ~10 adapters

**Batch 3** (Day 5): Text extraction adapters
- Remaining text-based adapters
- ~3 adapters

**After each batch**:
```bash
pytest tests/ -v  # All tests must pass
```

#### Phase 3: Integration (Week 3)

**Day 1-2**: Update pipeline to use HttpClient
- Inject HttpClient into adapter runner
- Update scheduler to use dependency injection
- Keep old code path as fallback

**Day 3-4**: Production testing
- Deploy to staging
- Run against real bank endpoints
- Verify outputs identical to production

**Day 5**: Production deployment
- Deploy new code
- Monitor for errors
- Keep old code ready for rollback

### Rollback Strategy

**Instant Rollback**: Backward compatibility ensures safe revert

```bash
# If issues found, revert Git commit
git revert <commit-sha>

# Or revert specific adapter
git checkout HEAD~1 -- adapters/cbe/adapter.py

# Tests still pass because wrappers maintained
pytest tests/test_m5_cbe_adapter.py -v
```

**Why rollback is safe**:
- Backward compatibility wrappers ensure old API works
- Each adapter migrated independently
- Can revert individual adapters without affecting others
- Database schema unchanged
- Pipeline logic unchanged

### Deployment Checklist

**Pre-deployment**:
- [ ] All 429 tests pass
- [ ] Code coverage maintained (≥85%)
- [ ] Equivalence tests pass for all refactored adapters
- [ ] Performance tests pass (no slowdown)
- [ ] Documentation updated

**Deployment**:
- [ ] Deploy to staging environment
- [ ] Run full test suite in staging
- [ ] Manually verify adapter outputs in staging
- [ ] Deploy to production
- [ ] Monitor error logs for 24 hours

**Post-deployment**:
- [ ] Verify production adapters running successfully
- [ ] Check database for new exchange rates
- [ ] Verify no regression in data quality
- [ ] Update runbook with new architecture

### Risk Mitigation

**Risk**: Refactored adapter produces different outputs

**Mitigation**:
- Equivalence tests verify identical outputs
- Backward compatibility wrappers ensure old API works
- Gradual rollout (3 adapters → batch → all)

**Risk**: HTTP client abstraction breaks existing fetch logic

**Mitigation**:
- MockHttpClient tested thoroughly
- Integration tests verify adapter + HTTP client
- Production RequestsHttpClient has same retry logic as before

**Risk**: Base class method adds performance overhead

**Mitigation**:
- Performance tests enforce no slowdown
- Base classes are thin wrappers (minimal overhead)
- Benchmark before/after on large responses

## Documentation and Knowledge Transfer

### Code Documentation

**Base Classes** (`adapters/base.py`):
- Comprehensive docstrings for all classes and methods
- Usage examples in docstrings
- Design rationale in comments

**HTTP Client** (`http/client.py`):
- Interface documentation
- Configuration examples
- Error handling patterns

**Reference Adapters**:
- Comments explaining base class usage
- Examples of overriding optional methods
- Migration notes for future adapters

### Developer Guide

**New Adapter Checklist**:

1. Choose base class (JSONAdapter, HTMLTableAdapter, or HTMLTextAdapter)
2. Implement required methods:
   - `_process_data()` OR `_process_tables()` OR `_extract_from_text()`
   - `get_source_url()`
   - `get_adapter_key()`
3. Override optional methods if needed:
   - `schema_fingerprint()`
   - `requires_category()`
4. Add backward compatibility wrapper (if migrating existing adapter)
5. Write tests (or verify existing tests pass)

**Example Template**:

```python
from adapters.base import JSONAdapter, ParseResult

class NewBankAdapter(JSONAdapter):
    """New Bank adapter (Type A: JSON)."""
    
    def get_source_url(self) -> str:
        return "https://newbank.et/api"
    
    def get_adapter_key(self) -> str:
        return "newbank_api"
    
    def _process_data(self, data, **options) -> ParseResult:
        result = ParseResult()
        
        # Extract records from data
        for item in data:
            # ... bank-specific logic
            result.records.append(record)
        
        return result

# Backward compatibility (if needed)
def parse(raw_json: str) -> list:
    adapter = NewBankAdapter()
    result = adapter.parse(raw_json)
    return result.records
```

### Architecture Decision Record

**ADR-010: Introduce Adapter Base Classes**

**Context**: 31 bank adapters have significant code duplication (~30%)

**Decision**: Introduce type-specific base classes (JSONAdapter, HTMLTableAdapter, HTMLTextAdapter) to reduce duplication while maintaining 31 separate adapter modules

**Alternatives Considered**:
1. Config-driven adapters (rejected: loses explicitness, hard to debug)
2. Single adapter with bank-specific config (rejected: violates separation of concerns)
3. No abstraction (rejected: high maintenance burden)

**Consequences**:
- Positive: 30% less code, uniform interface, better testability
- Negative: Adds abstraction layer (complexity)
- Risk: Must maintain backward compatibility

**Status**: Approved

## Summary

### Key Design Decisions

1. **Type-specific base classes** over single generic base - Matches natural adapter groupings (JSON, HTML table, HTML text)

2. **ParseResult data class** over tuple returns - Structured error handling, clearer semantics

3. **HTTP client abstraction** - Enables testing without network, production-ready retry logic

4. **Backward compatibility wrappers** - Safe incremental migration, no big-bang deployment

5. **No property-based testing** - Refactoring verification uses regression tests and equivalence tests

### Success Metrics

| Metric | Target | Verification |
|--------|--------|--------------|
| Code reduction | 30% | Line count before/after |
| Test coverage | ≥85% (maintained) | `pytest --cov` |
| Test pass rate | 429/429 (100%) | `pytest tests/ -v` |
| Performance | ≤1ms overhead | Benchmark tests |
| Backward compat | 100% | Existing code runs unchanged |

### Implementation Timeline

- **Week 1**: Base classes + 3 reference adapters + tests
- **Week 2**: Remaining 18 adapters
- **Week 3**: Integration + production deployment

**Total effort**: ~3 weeks for complete migration

### Long-term Benefits

1. **Onboarding**: New developers learn pattern once, apply to all adapters
2. **Maintenance**: Bug fixes in base classes benefit all adapters
3. **Evolution**: New adapter types can be added as new base classes
4. **Testing**: Mock HTTP client enables comprehensive test suite without network

This design achieves the goal of reducing duplication while preserving the architectural decision to keep bank-specific logic explicit and maintainable.
