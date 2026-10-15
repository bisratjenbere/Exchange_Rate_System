## Data Models

### Configuration Data

```python
@dataclass(frozen=True)
class Config:
    USER_AGENT: str
    REQUEST_TIMEOUT: int       # seconds
    RATE_LIMIT_DELAY: float    # seconds
    MAX_RETRIES: int
    DATABASE_URL: str
```

### Rate Source Data

```python
# Returned by RateSourceRepository methods
{
    "id": int,                          # Primary key
    "adapter_key": str,                 # e.g., "cbe_api", "dashen_html"
    "source_url": str,                  # Bank data endpoint
    "ssl_verify": bool,                 # SSL verification flag
    "schema_fingerprint": Optional[str], # SHA-256 of schema structure
    "default_category": Optional[str]   # "cash", "transactional", or None
}
```

### HTTP Response Data

```python
@dataclass
class HttpResponse:
    content: str              # Response body (empty if error)
    status_code: int          # HTTP status (0 if connection error)
    url: str                  # Requested URL
    error: Optional[str]      # Error message (None on success)
```

### Error Classification Data

```python
# Tuple returned by ErrorClassifier.classify()
(error_code: str, error_summary: str)

# Error codes:
# - "schema_change"   : Schema fingerprint changed
# - "parse_failure"   : ValueError, KeyError, AttributeError
# - "http_failure"    : ConnectionError, Timeout
# - "suspicious_data" : Buying rate > selling rate
```

## Sequence Diagrams

### Sequence 1: Successful Collection Run

```
┌──────────┐     ┌───────────┐     ┌────────────┐     ┌──────────┐     ┌─────────┐
│ Caller   │     │ Scheduler │     │Repository  │     │HttpClient│     │ Adapter │
└────┬─────┘     └─────┬─────┘     └──────┬─────┘     └────┬─────┘     └────┬────┘
     │                 │                   │                │                │
     │ run_source(conn, source_id)        │                │                │
     │────────────────>│                   │                │                │
     │                 │                   │                │                │
     │                 │ get_by_id(source_id)              │                │
     │                 │──────────────────>│                │                │
     │                 │                   │                │                │
     │                 │ source dict       │                │                │
     │                 │<──────────────────│                │                │
     │                 │                   │                │                │
     │                 │ adapter = registry.get(adapter_key)                │
     │                 │────────────────────────────────────────────────────>│
     │                 │                   │                │                │
     │                 │                   │    fetch(url, ssl_verify=True) │
     │                 │────────────────────────────────────>│                │
     │                 │                   │                │                │
     │                 │                   │    HttpResponse(content, 200)  │
     │                 │<────────────────────────────────────│                │
     │                 │                   │                │                │
     │                 │ adapter.parse(content, category="transactional")   │
     │                 │────────────────────────────────────────────────────>│
     │                 │                   │                │                │
     │                 │                   │                │  List[AdapterRecord]
     │                 │<────────────────────────────────────────────────────│
     │                 │                   │                │                │
     │                 │ ingest(conn, records, source_id, run_id)           │
     │                 │──────────────────>│                │                │
     │                 │                   │                │                │
     │                 │ IngestResult(accepted=10, flagged=0, ...)          │
     │                 │<──────────────────│                │                │
     │                 │                   │                │                │
     │                 │ repo.update_last_success(source_id)                │
     │                 │──────────────────>│                │                │
     │                 │                   │                │                │
     │                 │ UPDATE rate_source SET last_success_at = now()     │
     │                 │                   │──────────>     │                │
     │                 │                   │                │                │
     │ summary dict    │                   │                │                │
     │<────────────────│                   │                │                │
     │                 │                   │                │                │
```

### Sequence 2: Error Handling Flow

```
┌──────────┐     ┌───────────┐     ┌──────────────┐     ┌─────────┐
│ Scheduler│     │HttpClient │     │ErrorClassifier│     │Repository│
└────┬─────┘     └─────┬─────┘     └──────┬───────┘     └────┬─────┘
     │                 │                   │                  │
     │ fetch(url)      │                   │                  │
     │────────────────>│                   │                  │
     │                 │                   │                  │
     │                 │  X  Timeout       │                  │
     │                 │                   │                  │
     │ HttpResponse(content="", status=0, error="Timeout")   │
     │<────────────────│                   │                  │
     │                 │                   │                  │
     │  raise RuntimeError("HTTP 0: Timeout")                │
     │                 │                   │                  │
     │ except Exception as exc:            │                  │
     │                 │                   │                  │
     │ classifier.classify(exc)            │                  │
     │────────────────────────────────────>│                  │
     │                 │                   │                  │
     │                 │  HttpFailureClassifier.classify()    │
     │                 │                   │──────────>       │
     │                 │                   │                  │
     │                 │  ("http_failure", "Timeout: ...")    │
     │                 │                   │<──────────       │
     │                 │                   │                  │
     │ ("http_failure", "Timeout...")      │                  │
     │<────────────────────────────────────│                  │
     │                 │                   │                  │
     │ finish_run(conn, run_id, "failed",  error_code="http_failure")
     │────────────────────────────────────────────────────────────>│
     │                 │                   │                  │
     │ conn.commit()   │                   │                  │
     │─────────────────────────────────────────────────────>  │
     │                 │                   │                  │
```

### Sequence 3: Adapter Registry Lookup

```
┌──────────┐     ┌──────────────────┐     ┌───────────────┐
│ Scheduler│     │ AdapterRegistry  │     │ Adapter Module│
└────┬─────┘     └────────┬─────────┘     └───────┬───────┘
     │                    │                        │
     │ registry.get("cbe_api")                     │
     │───────────────────>│                        │
     │                    │                        │
     │                    │  _adapters["cbe_api"]  │
     │                    │────────>               │
     │                    │                        │
     │                    │  cbe_adapter module    │
     │                    │<────────               │
     │                    │                        │
     │  cbe_adapter       │                        │
     │<───────────────────│                        │
     │                    │                        │
     │ cbe_adapter.parse(raw_json)                 │
     │────────────────────────────────────────────>│
     │                    │                        │
     │                    │        List[AdapterRecord]
     │<────────────────────────────────────────────│
     │                    │                        │

Compare to OLD (importlib trial-and-error):
┌──────────┐     ┌─────────────────────────────────┐
│ Scheduler│     │ _load_adapter() importlib logic │
└────┬─────┘     └────────┬────────────────────────┘
     │                    │
     │ _load_adapter("cbe_api")
     │───────────────────>│
     │                    │
     │                    │ try: importlib("adapters.cbe_api.adapter")
     │                    │────────> ModuleNotFoundError
     │                    │
     │                    │ try: importlib("adapters.cbe.adapter")
     │                    │────────> SUCCESS
     │                    │
     │  cbe_adapter       │
     │<───────────────────│
     │                    │
```

### Sequence 4: Schema Fingerprint Check

```
┌──────────┐     ┌────────────┐     ┌────────────┐     ┌────────────┐
│ Scheduler│     │  Adapter   │     │ Repository │     │raw_capture │
└────┬─────┘     └──────┬─────┘     └──────┬─────┘     └──────┬─────┘
     │                  │                   │                  │
     │ adapter.schema_fingerprint(raw_content)                 │
     │─────────────────>│                   │                  │
     │                  │                   │                  │
     │  current_fp      │                   │                  │
     │<─────────────────│                   │                  │
     │                  │                   │                  │
     │  source["schema_fingerprint"] = stored_fp (from DB)     │
     │                  │                   │                  │
     │  if current_fp != stored_fp:        │                  │
     │                  │                   │                  │
     │  _store_raw_capture(conn, run_id, "schema_change", raw)│
     │─────────────────────────────────────────────────────────>│
     │                  │                   │                  │
     │  raise ValueError("Schema fingerprint changed")         │
     │                  │                   │                  │
     │                  │                   │                  │
     │  if not stored_fp (first run):      │                  │
     │                  │                   │                  │
     │  repo.update_schema_fingerprint(source_id, current_fp)  │
     │─────────────────────────────────────>│                  │
     │                  │                   │                  │
     │                  │ UPDATE rate_source SET schema_fingerprint = %s
     │                  │                   │───────────>      │
     │                  │                   │                  │
```

## Class Diagrams

### Infrastructure Components Class Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                          <<dataclass>>                            │
│                             Config                                │
├──────────────────────────────────────────────────────────────────┤
│ + USER_AGENT: str                                                │
│ + REQUEST_TIMEOUT: int                                           │
│ + RATE_LIMIT_DELAY: float                                        │
│ + MAX_RETRIES: int                                               │
│ + DATABASE_URL: str                                              │
├──────────────────────────────────────────────────────────────────┤
│ + __post_init__() -> None                                        │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                       AdapterRegistry                             │
├──────────────────────────────────────────────────────────────────┤
│ - _adapters: dict[str, Any]                                      │
├──────────────────────────────────────────────────────────────────┤
│ + register(adapter_key: str, adapter_module: Any) -> None        │
│ + get(adapter_key: str) -> Any                                   │
│ + list_keys() -> list[str]                                       │
│ + is_registered(adapter_key: str) -> bool                        │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                    RateSourceRepository                           │
├──────────────────────────────────────────────────────────────────┤
│ - conn: Connection                                               │
├──────────────────────────────────────────────────────────────────┤
│ + get_by_id(source_id: int) -> Optional[dict]                    │
│ + get_enabled_sources() -> list[dict]                            │
│ + update_last_success(source_id: int) -> None                    │
│ + update_schema_fingerprint(source_id: int, fp: str) -> None     │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                    <<abstract>> ErrorClassifier                   │
├──────────────────────────────────────────────────────────────────┤
│ + classify(exc: Exception) -> Optional[Tuple[str, str]]  <<abstract>>
└──────────────────────────────────────────────────────────────────┘
                              △
                              │
       ┌──────────────────────┼──────────────────────┐
       │                      │                      │
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ SchemaChange     │  │ ParseFailure     │  │ HttpFailure      │
│ Classifier       │  │ Classifier       │  │ Classifier       │
├──────────────────┤  ├──────────────────┤  ├──────────────────┤
│ + classify(...)  │  │ + classify(...)  │  │ + classify(...)  │
└──────────────────┘  └──────────────────┘  └──────────────────┘
       
┌──────────────────────────────────────────────────────────────────┐
│              CompositeErrorClassifier                             │
├──────────────────────────────────────────────────────────────────┤
│ - classifiers: list[ErrorClassifier]                             │
│ - fallback_code: str                                             │
├──────────────────────────────────────────────────────────────────┤
│ + classify(exc: Exception) -> Tuple[str, str]                    │
└──────────────────────────────────────────────────────────────────┘
                  │
                  │ contains
                  ↓
       ┌──────────────────────┐
       │  ErrorClassifier      │
       │  (multiple instances) │
       └──────────────────────┘
```

### Scheduler with Dependencies

```
┌──────────────────────────────────────────────────────────────────┐
│                          Scheduler                                │
├──────────────────────────────────────────────────────────────────┤
│ - config: Config                                                 │
│ - http_client: HttpClient                                        │
│ - adapter_registry: AdapterRegistry                              │
│ - error_classifier: ErrorClassifier                              │
├──────────────────────────────────────────────────────────────────┤
│ + __init__(config, http_client, adapter_registry,                │
│            error_classifier)                                      │
│ + run_source(conn: Connection, source_id: int) -> dict           │
│ + run_all(conn: Connection) -> list[dict]                        │
│ - _build_url(base_url: str, adapter_key: str) -> str             │
│ - _parse(adapter, raw_content: str, category: str) -> list       │
│ - _check_schema(conn, run_id, source, adapter, raw, repo)        │
│ - _store_raw_capture(conn, run_id, reason, raw)                  │
│ - _run_status(result: IngestResult) -> str                       │
└──────────────────────────────────────────────────────────────────┘
         │              │                  │                │
         │ depends on   │ depends on       │ depends on     │ depends on
         ↓              ↓                  ↓                ↓
   ┌─────────┐    ┌──────────┐   ┌────────────────┐  ┌───────────────┐
   │ Config  │    │HttpClient│   │AdapterRegistry │  │ErrorClassifier│
   └─────────┘    └──────────┘   └────────────────┘  └───────────────┘
```

## Error Handling

### Error Classification Matrix

| Exception Type | Classifier | Error Code | Retryable? | Action |
|----------------|------------|------------|-----------|---------|
| requests.Timeout | HttpFailureClassifier | http_failure | Yes | Auto-retry in HttpClient |
| requests.ConnectionError | HttpFailureClassifier | http_failure | Yes | Auto-retry in HttpClient |
| ValueError (parse) | ParseFailureClassifier | parse_failure | No | Capture raw, flag for review |
| KeyError (parse) | ParseFailureClassifier | parse_failure | No | Capture raw, flag for review |
| AttributeError (parse) | ParseFailureClassifier | parse_failure | No | Capture raw, flag for review |
| "Schema fingerprint..." | SchemaChangeClassifier | schema_change | No | Capture raw, halt processing |
| Unknown | CompositeClassifier | parse_failure (fallback) | No | Log and investigate |

### Error Handling Flow

```
Exception Raised
       │
       ↓
ErrorClassifier.classify(exc)
       │
       ├─> SchemaChangeClassifier.classify(exc)
       │   ├─> Match? → ("schema_change", msg)
       │   └─> No match → None
       │
       ├─> ParseFailureClassifier.classify(exc)
       │   ├─> Match? → ("parse_failure", msg)
       │   └─> No match → None
       │
       ├─> HttpFailureClassifier.classify(exc)
       │   ├─> Match? → ("http_failure", msg)
       │   └─> No match → None
       │
       └─> No matches → Fallback
           └─> ("parse_failure", "UnknownError: ...")

Error Code
       │
       ├─> "schema_change"
       │   ├─> Capture raw content
       │   ├─> Halt processing
       │   └─> Manual review required
       │
       ├─> "parse_failure"
       │   ├─> Capture raw content
       │   ├─> Mark run failed
       │   └─> Continue other sources
       │
       └─> "http_failure"
           ├─> No raw content captured
           ├─> Mark run failed
           └─> Auto-retry next run
```

### Error Recovery Strategy

**Schema Changes**:
1. Detect via schema_fingerprint() hash
2. Capture raw content to raw_capture table
3. Halt processing for that source
4. Alert developer for adapter update
5. After fix, update stored fingerprint

**Parse Failures**:
1. Capture raw content to raw_capture table
2. Log specific error (currency, field, reason)
3. Continue processing other sources
4. Developer investigates from captured raw

**HTTP Failures**:
1. Automatic retry (up to MAX_RETRIES)
2. Exponential backoff (RATE_LIMIT_DELAY * attempt)
3. If all retries fail, mark run failed
4. Next scheduled run will retry

## Testing Strategy

### Testing Philosophy

This refactoring uses **unit testing** and **integration testing**, NOT property-based testing. The goal is to verify that:

1. Each infrastructure component works correctly in isolation
2. Components integrate correctly
3. All existing 429 tests continue to pass
4. Scheduler behavior is unchanged

Property-based testing is inappropriate because:
- We're refactoring structure, not implementing new algorithms
- There are no universal properties to test (no "for all inputs X, property P holds")
- The correctness criterion is behavioral equivalence, not algorithmic correctness

### Testing Layers

#### Layer 1: Infrastructure Unit Tests

**File**: `tests/test_infrastructure.py`

```python
class TestConfig:
    def test_default_values():
        """Config uses defaults when env vars not set"""
        config = Config()
        assert config.REQUEST_TIMEOUT == 15
        assert config.RATE_LIMIT_DELAY == 2.0
        assert config.MAX_RETRIES == 2
    
    def test_environment_override():
        """Config reads from environment variables"""
        os.environ['REQUEST_TIMEOUT'] = '30'
        config = Config()
        assert config.REQUEST_TIMEOUT == 30
    
    def test_validation():
        """Config validates values"""
        os.environ['REQUEST_TIMEOUT'] = '-1'
        with pytest.raises(ValueError, match="REQUEST_TIMEOUT must be > 0"):
            Config()


class TestAdapterRegistry:
    def test_register_and_get():
        """Can register and retrieve adapters"""
        registry = AdapterRegistry()
        mock_adapter = Mock()
        registry.register("test_adapter", mock_adapter)
        assert registry.get("test_adapter") is mock_adapter
    
    def test_duplicate_registration_raises():
        """Registering same key twice raises ValueError"""
        registry = AdapterRegistry()
        registry.register("test", Mock())
        with pytest.raises(ValueError, match="already registered"):
            registry.register("test", Mock())
    
    def test_get_unregistered_raises():
        """Getting unregistered adapter raises KeyError"""
        registry = AdapterRegistry()
        with pytest.raises(KeyError, match="not registered"):
            registry.get("nonexistent")
    
    def test_list_keys():
        """list_keys returns all registered keys"""
        registry = AdapterRegistry()
        registry.register("adapter1", Mock())
        registry.register("adapter2", Mock())
        assert set(registry.list_keys()) == {"adapter1", "adapter2"}


class TestRateSourceRepository:
    def test_get_by_id(mock_conn):
        """get_by_id returns source dict"""
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (1, "cbe_api", "https://...", True, "abc123", "cash")
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        repo = RateSourceRepository(mock_conn)
        source = repo.get_by_id(1)
        
        assert source["id"] == 1
        assert source["adapter_key"] == "cbe_api"
    
    def test_get_by_id_not_found(mock_conn):
        """get_by_id returns None if not found"""
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        repo = RateSourceRepository(mock_conn)
        source = repo.get_by_id(999)
        
        assert source is None
    
    def test_update_last_success(mock_conn):
        """update_last_success executes UPDATE query"""
        mock_cursor = Mock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        repo = RateSourceRepository(mock_conn)
        repo.update_last_success(1)
        
        mock_cursor.execute.assert_called_once()
        sql = mock_cursor.execute.call_args[0][0]
        assert "UPDATE rate_source" in sql
        assert "last_success_at" in sql


class TestErrorClassifiers:
    def test_schema_change_classifier():
        """SchemaChangeClassifier matches schema errors"""
        classifier = SchemaChangeClassifier()
        exc = ValueError("Schema fingerprint changed")
        
        result = classifier.classify(exc)
        
        assert result == ("schema_change", "Schema fingerprint changed")
    
    def test_parse_failure_classifier():
        """ParseFailureClassifier matches parse errors"""
        classifier = ParseFailureClassifier()
        exc = ValueError("Invalid JSON")
        
        result = classifier.classify(exc)
        
        assert result == ("parse_failure", "Invalid JSON")
    
    def test_http_failure_classifier():
        """HttpFailureClassifier matches network errors"""
        classifier = HttpFailureClassifier()
        exc = requests.exceptions.Timeout("Timeout after 15s")
        
        result = classifier.classify(exc)
        
        assert result == ("http_failure", "Timeout after 15s")
    
    def test_composite_classifier_first_match():
        """CompositeClassifier returns first match"""
        classifiers = [
            SchemaChangeClassifier(),
            ParseFailureClassifier(),
        ]
        composite = CompositeErrorClassifier(classifiers)
        exc = ValueError("Schema fingerprint changed")
        
        result = composite.classify(exc)
        
        assert result[0] == "schema_change"  # SchemaChange matched first
    
    def test_composite_classifier_fallback():
        """CompositeClassifier uses fallback if no match"""
        classifiers = [SchemaChangeClassifier()]
        composite = CompositeErrorClassifier(classifiers, fallback_code="unknown")
        exc = RuntimeError("Unexpected error")
        
        result = composite.classify(exc)
        
        assert result[0] == "unknown"  # Fallback used
```

**Coverage Target**: 100% of infrastructure code

#### Layer 2: Scheduler Integration Tests

**File**: `tests/test_scheduler_refactored.py`

```python
class TestSchedulerIntegration:
    def test_run_source_with_mocks():
        """Scheduler integrates all dependencies correctly"""
        # Mock all dependencies
        mock_http = MockHttpClient()
        mock_http.configure_response("bank.et", '{"rates": [...]}')
        
        mock_adapter = Mock()
        mock_adapter.parse.return_value = [Mock(spec=AdapterRecord)]
        mock_adapter.schema_fingerprint.return_value = "abc123"
        
        mock_registry = Mock()
        mock_registry.get.return_value = mock_adapter
        
        mock_conn = create_mock_connection()
        
        # Create scheduler with mocks
        scheduler = Scheduler(
            config=Config(),
            http_client=mock_http,
            adapter_registry=mock_registry,
            error_classifier=default_classifier
        )
        
        # Run
        result = scheduler.run_source(mock_conn, source_id=1)
        
        # Verify
        assert result["status"] == "success"
        assert mock_http.fetch_count == 1
        mock_adapter.parse.assert_called_once()
    
    def test_run_source_http_error():
        """Scheduler handles HTTP errors correctly"""
        mock_http = MockHttpClient()
        mock_http.configure_response("bank.et", "", status_code=500)
        
        scheduler = Scheduler(http_client=mock_http)
        result = scheduler.run_source(mock_conn, source_id=1)
        
        assert result["status"] == "failed"
        assert result["error_code"] == "http_failure"
    
    def test_run_source_parse_error():
        """Scheduler handles parse errors correctly"""
        mock_adapter = Mock()
        mock_adapter.parse.side_effect = ValueError("Invalid format")
        
        mock_registry = Mock()
        mock_registry.get.return_value = mock_adapter
        
        scheduler = Scheduler(adapter_registry=mock_registry)
        result = scheduler.run_source(mock_conn, source_id=1)
        
        assert result["status"] == "failed"
        assert result["error_code"] == "parse_failure"
```

**Coverage Target**: All scheduler code paths

#### Layer 3: Regression Tests

**Strategy**: Run all 429 existing tests without modification

```bash
# All existing tests must pass
pytest tests/ -v

# Specific adapter tests
pytest tests/test_m5_cbe_adapter.py -v
pytest tests/test_m4_adib_adapter.py -v
pytest tests/test_m8_wave2_adapters.py -v

# Success criteria: 429/429 passed
```

**Critical**: If any existing test fails, the refactoring has introduced a regression.

#### Layer 4: Backward Compatibility Tests

**File**: `tests/test_backward_compatibility.py`

```python
def test_module_level_run_source_still_works():
    """Module-level run_source() function still works"""
    from scheduler.runner import run_source
    
    mock_conn = create_mock_connection()
    result = run_source(mock_conn, source_id=1)
    
    assert "status" in result
    assert "source_id" in result


def test_module_level_run_all_still_works():
    """Module-level run_all() function still works"""
    from scheduler.runner import run_all
    
    mock_conn = create_mock_connection()
    results = run_all(mock_conn)
    
    assert isinstance(results, list)
```

### Test Execution

**Pre-commit**:
```bash
pytest tests/test_infrastructure.py -v  # ~2 seconds
```

**CI Pipeline**:
```bash
pytest tests/ -v --cov=infrastructure --cov=scheduler --cov-report=term-missing
# Target: maintain ≥85% coverage
```

**Deployment Gate**:
```bash
# ALL 429 tests must pass
pytest tests/ -v | grep "429 passed"
```

## Migration and Deployment

### Phase 1: Create Infrastructure Components (Week 1, Days 1-2)

**Deliverables**:
- `infrastructure/config.py` with Config class
- `infrastructure/adapter_registry.py` with AdapterRegistry + default_registry
- `infrastructure/rate_source_repository.py` with RateSourceRepository
- `infrastructure/error_classifier.py` with all classifiers
- Unit tests for all components

**Verification**:
```bash
pytest tests/test_infrastructure.py -v
# All infrastructure tests pass
```

### Phase 2: Refactor Scheduler (Week 1, Days 3-4)

**Deliverables**:
- `scheduler/runner.py` refactored to Scheduler class
- Dependency injection in __init__
- Backward compatibility wrappers (module-level functions)
- Integration tests

**Verification**:
```bash
pytest tests/test_scheduler_refactored.py -v
# Integration tests pass

pytest tests/ -v
# ALL 429 tests still pass
```

###