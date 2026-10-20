# Spec 3: Pipeline Infrastructure Clean Code Refactoring - Current Status

**Date**: 2026-10-20  
**Overall Status**: ~40% Complete (Tasks 1-5 done, Tasks 6-11 remaining)

---

## ✅ Completed Tasks (Tasks 1-5)

### Task 1: Infrastructure Directory and Config Class ✅
**Status**: COMPLETE

**Created Files**:
- `infrastructure/__init__.py` - Package initialization with exports
- `infrastructure/config.py` - Config dataclass with environment variable loading

**Features Implemented**:
- Environment variable loading (REQUEST_TIMEOUT, RATE_LIMIT_DELAY, MAX_RETRIES, DATABASE_URL)
- Validation in `__post_init__`
- Immutable (`frozen=True`)
- Comprehensive docstrings
- Sensible defaults

**Tests**: `tests/test_infrastructure_config.py` exists

---

### Task 2: AdapterRegistry ✅
**Status**: COMPLETE

**Created Files**:
- `infrastructure/adapter_registry.py` - AdapterRegistry class with explicit registration

**Features Implemented**:
- `register()`, `get()`, `list_keys()`, `is_registered()` methods
- `default_registry` with all 31 adapters explicitly registered
- Descriptive KeyError messages showing available adapters
- Type-safe (no importlib trial-and-error)

**Registered Adapters** (31 total):
- abay_html, adib_api, ahadu_html, amhara_html, anbesa_browser
- awash_ajax, berhan_html, boa_html, bunna_html, cbe_api
- cbo_html, dashen_html, dbe_html, enat_html, gadaa_api
- global_html, goh_betoch_html, hibret_html, nib_html, omo_html
- oromia_html, rammis_api, shabelle_html, sidama_html, siinqee_html
- siket_html, tsedey_html, tsehay_html, wegagen_api, zamzam_html
- zemen_ajax

**Tests**: `tests/test_infrastructure_adapter_registry.py` exists

---

### Task 3: RateSourceRepository ✅
**Status**: COMPLETE

**Created Files**:
- `infrastructure/rate_source_repository.py` - Repository pattern for rate_source table

**Features Implemented**:
- `get_by_id()` - Returns source dict or None
- `get_enabled_sources()` - Returns list of enabled sources
- `update_last_success()` - Updates last_success_at timestamp
- `update_schema_fingerprint()` - Updates schema fingerprint
- Parameterized queries (SQL injection protection)
- Consistent dict structure with all required fields

**Dict Structure**:
```python
{
    "id": int,
    "adapter_key": str,
    "source_url": str,
    "ssl_verify": bool,
    "schema_fingerprint": Optional[str],
    "default_category": Optional[str],
    "consecutive_failures": int,
    "last_failure_code": Optional[str],
}
```

**Tests**: `tests/test_infrastructure_rate_source_repository.py` exists

---

### Task 4: ErrorClassifier with Strategy Pattern ✅
**Status**: COMPLETE

**Created Files**:
- `infrastructure/error_classifier.py` - Strategy pattern for error classification

**Features Implemented**:
- `ErrorClassifier` abstract base class
- `SchemaChangeClassifier` - Detects "Schema fingerprint" or "schema" keywords
- `ParseFailureClassifier` - Detects ValueError, KeyError, AttributeError
- `HttpFailureClassifier` - Detects ConnectionError, Timeout
- `CompositeErrorClassifier` - Chains classifiers with fallback
- `default_classifier` - Pre-configured composite with all strategies

**Error Codes**:
- `schema_change` - Schema fingerprint changed
- `parse_failure` - Parsing error (ValueError, KeyError, AttributeError)
- `http_failure` - Network error (ConnectionError, Timeout)

**Tests**: `tests/test_infrastructure_error_classifier.py` exists

---

### Task 5: Checkpoint - Infrastructure Components ✅
**Status**: PASSED

All infrastructure components created and tested. Ready for scheduler refactoring.

---

## 🔄 Remaining Tasks (Tasks 6-11)

### Task 6: Refactor scheduler/runner.py to use Scheduler class
**Status**: NOT STARTED

**Current State**:
- `scheduler/runner.py` still uses old patterns:
  - Inline SQL queries (`_load_source()`, `_load_enabled_sources()`, `_update_last_success()`)
  - Duplicate `_fetch()` function with HTTP logic
  - `_load_adapter()` with importlib trial-and-error
  - `_classify_error()` if-else chain
  - Module-level constants (USER_AGENT, REQUEST_TIMEOUT, etc.)

**Required Changes**:
1. Create `Scheduler` class with dependency injection constructor
2. Replace inline SQL with `RateSourceRepository` methods
3. Replace `_fetch()` with `HttpClient.fetch()`
4. Replace `_load_adapter()` with `AdapterRegistry.get()`
5. Replace `_classify_error()` with `ErrorClassifier.classify()`
6. Remove module-level constants, use `Config` properties
7. Update `_check_schema()` to accept repo parameter

**Dependencies Needed**:
- `Config` (from Task 1)
- `HttpClient` (from Spec 2 - `http_clients/http_client.py`)
- `AdapterRegistry` (from Task 2)
- `RateSourceRepository` (from Task 3)
- `ErrorClassifier` (from Task 4)

---

### Task 7: Add backward compatibility wrappers
**Status**: NOT STARTED

**Required**:
- Keep module-level `run_source(conn, source_id)` function
- Keep module-level `run_all(conn)` function
- Implement as thin wrappers: `return Scheduler().run_source(conn, source_id)`

---

### Task 7.1-7.3: Write integration and backward compatibility tests
**Status**: NOT STARTED

**Required Tests**:
- Integration tests with mocked dependencies
- Tests with real HttpClient implementations (MockHttpClient, FileHttpClient)
- Backward compatibility tests for module-level functions

---

### Task 8: Checkpoint - Verify all 429 existing tests pass
**Status**: PENDING

Must verify: `pytest tests/ -v` shows 429 tests passing

---

### Task 9: Add documentation and docstrings
**Status**: PARTIALLY DONE

**Done**:
- Infrastructure components all have comprehensive docstrings

**Remaining**:
- Scheduler class docstrings
- Error code documentation
- Mock testing examples

---

### Task 10: Create migration guide and update documentation
**Status**: NOT STARTED

**Required**:
- Migration guide explaining refactoring
- ADR (Architecture Decision Record)
- Update README if needed
- Document environment variables

---

### Task 11: Final checkpoint and code review
**Status**: PENDING

---

### Task 12 (Optional): Pipeline Chain of Responsibility
**Status**: DEFERRED

This task is explicitly marked optional and lower priority. Should only be attempted if core refactoring completes quickly.

---

## Summary

**Progress**: 5 of 11 core tasks complete (45%)

**Completed**:
- ✅ All infrastructure components (Config, AdapterRegistry, RateSourceRepository, ErrorClassifier)
- ✅ All infrastructure unit tests
- ✅ Infrastructure checkpoint passed

**Remaining**:
- ⏳ Scheduler class refactoring with dependency injection
- ⏳ Backward compatibility wrappers
- ⏳ Integration tests
- ⏳ Documentation and migration guide
- ⏳ Final verification (429 tests passing)

**Next Steps**:
1. Start Task 6: Refactor scheduler to use Scheduler class
2. Integrate all infrastructure components via dependency injection
3. Replace inline SQL, HTTP logic, adapter loading, error classification
4. Add backward compatibility wrappers
5. Verify all tests pass

---

## Key Files

**Infrastructure** (Complete):
- `infrastructure/config.py`
- `infrastructure/adapter_registry.py`
- `infrastructure/rate_source_repository.py`
- `infrastructure/error_classifier.py`

**Scheduler** (Needs Refactoring):
- `scheduler/runner.py` - Contains old patterns, needs Scheduler class

**Tests** (Infrastructure Complete, Scheduler Pending):
- `tests/test_infrastructure_*.py` - All complete
- `tests/test_scheduler_refactored.py` - Needs to be created

**HttpClient** (From Spec 2 - Ready to Use):
- `http_clients/http_client.py` - RequestsHttpClient, MockHttpClient, FileHttpClient

---

**Date**: 2026-10-20  
**Ready for**: Task 6 (Scheduler refactoring)
