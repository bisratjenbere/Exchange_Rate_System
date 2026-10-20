# Implementation Plan: Adapter Base Classes and HTTP Abstraction

## Overview

This implementation refactors the Ethiopian Bank Exchange Rate system's 31 adapters to use type-specific base classes and HTTP client abstraction. The goal is to reduce code duplication by ~30% while maintaining backward compatibility and all 429 existing tests passing.

**Implementation Language**: Python (as specified in design document)

**Migration Strategy**: 4-week phased approach with backward compatibility maintained throughout

**Critical Constraints**:
- All 429 existing tests must pass after each phase
- Backward compatibility maintained via module-level function wrappers
- No database or pipeline changes
- Each adapter migration is independent

**Complete Adapter List** (31 adapters):
1. abay, 2. adib, 3. ahadu, 4. amhara, 5. anbesa, 6. awash, 7. berhan, 8. boa, 9. bunna, 10. cbe, 11. cbo, 12. dashen, 13. dbe, 14. enat, 15. gadaa, 16. global_, 17. goh_betoch, 18. hibret, 19. nib, 20. omo, 21. oromia, 22. rammis, 23. shabelle, 24. sidama, 25. siinqee, 26. siket, 27. tsedey, 28. tsehay, 29. wegagen, 30. zamzam, 31. zemen

---

## Phase 1: Foundation (Week 1)

### Task 1: Create Base Adapter Classes

- [ ] 1.1 Create adapters/base.py with core infrastructure
  - Implement BankAdapter abstract base class with parse(), get_source_url(), get_adapter_key(), schema_fingerprint(), requires_category() methods
  - Implement ParseResult dataclass with records, errors, warnings fields and is_success(), add_error(), add_warning() helper methods
  - Implement helper methods: _safe_rate(), _parse_iso_date(), _rate_text()
  - Add comprehensive docstrings explaining each method and usage patterns
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 14.1_

- [ ] 1.2 Implement JSONAdapter base class in adapters/base.py
  - Inherit from BankAdapter
  - Implement parse() method that handles JSON parsing and calls abstract _process_data()
  - Raise ValueError with descriptive message on JSON parsing failure
  - Implement default schema_fingerprint() that hashes top-level JSON keys
  - Define abstract _process_data() method for bank-specific extraction
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 14.2_

- [ ] 1.3 Implement HTMLTableAdapter base class in adapters/base.py
  - Inherit from BankAdapter
  - Implement parse() method that parses HTML, finds tables, and calls abstract _process_tables()
  - Return ParseResult with error when no tables found
  - Implement default schema_fingerprint() that hashes table count and header cells
  - Define abstract _process_tables() method accepting soup and tables list
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 14.2_

- [ ] 1.4 Implement HTMLTextAdapter base class in adapters/base.py
  - Inherit from BankAdapter
  - Implement parse() method that parses HTML, extracts normalized text, and calls abstract _extract_from_text()
  - Normalize whitespace by joining with single spaces
  - Define abstract _extract_from_text() method accepting text and soup
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 14.2_

### Task 2: Create HTTP Client Abstraction

- [ ] 2.1 Create http/client.py with HttpClient interface and HttpResponse dataclass
  - Implement HttpClient abstract interface with fetch() method
  - Implement HttpResponse dataclass with content, status_code, url, error fields
  - Add is_success() method to HttpResponse
  - Add comprehensive docstrings explaining the abstraction
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 14.3_

- [ ] 2.2 Implement RequestsHttpClient in http/client.py
  - Implement fetch() method using requests library
  - Add configurable timeout (default 15s), max_retries (default 2), retry_delay (default 2.0s)
  - Implement exponential backoff retry logic
  - Support ssl_verify, post_data, headers options
  - Set User-Agent header (default "EthiopianBankRateCollector/1.0")
  - Never raise exceptions - return HttpResponse with error field populated
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10_

- [ ] 2.3 Implement MockHttpClient in http/client.py
  - Accept dictionary mapping URL patterns to response content
  - Implement pattern matching (exact URL or substring)
  - Track fetch_count and last_url for test assertions
  - Add configure_response() method for runtime configuration
  - Return 404 HttpResponse when no pattern matches
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

- [ ] 2.4 Implement FileHttpClient in http/client.py
  - Accept fixtures_dir parameter in constructor
  - Extract domain from URL and map to fixture filename (e.g., combanketh_et.json)
  - Try both .html and .json extensions
  - Return 404 HttpResponse when fixture not found
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

### Task 3: Write Unit Tests for Base Classes

- [ ]* 3.1 Create tests/test_adapter_bases.py with base class tests
  - Test JSONAdapter parses valid JSON and calls _process_data()
  - Test JSONAdapter raises ValueError for invalid JSON
  - Test HTMLTableAdapter extracts tables and calls _process_tables()
  - Test HTMLTableAdapter returns error when no tables found
  - Test HTMLTextAdapter extracts and normalizes text
  - Test BankAdapter helper methods: _safe_rate(), _parse_iso_date(), _rate_text()
  - Test ParseResult.is_success(), add_error(), add_warning()
  - Test default schema_fingerprint() implementations
  - Target 100% coverage of base class code
  - _Requirements: 13.1, 13.2, 13.5_

### Task 4: Write Unit Tests for HTTP Clients

- [ ]* 4.1 Create tests/test_http_client.py with HTTP client tests
  - Test RequestsHttpClient successful fetch returns is_success=True
  - Test RequestsHttpClient retries on timeout with exponential backoff (mock requests)
  - Test RequestsHttpClient connection error returns HttpResponse with error
  - Test RequestsHttpClient non-200 status returns is_success=False
  - Test RequestsHttpClient POST requests work with post_data
  - Test RequestsHttpClient custom headers are sent
  - Test RequestsHttpClient ssl_verify option controls SSL verification
  - Test MockHttpClient returns configured response for matching URL
  - Test MockHttpClient pattern matching (substring)
  - Test MockHttpClient tracks fetch_count and last_url
  - Test MockHttpClient returns 404 for non-configured URL
  - Test MockHttpClient configure_response() adds responses
  - Test FileHttpClient loads fixture based on URL domain
  - Test FileHttpClient tries both .html and .json extensions
  - Test FileHttpClient returns 404 when fixture not found
  - Target 100% coverage of HTTP client code
  - _Requirements: 13.1, 13.2, 13.5_

### Task 5: Refactor CBE Adapter as JSONAdapter Example

- [ ] 5.1 Create CBEAdapter class in adapters/cbe/adapter.py
  - Inherit from JSONAdapter
  - Implement _process_data() method with CBE-specific extraction logic (move existing logic from parse() function)
  - Implement get_source_url() returning "https://combanketh.et/cbeapi/daily-exchange-rates/"
  - Implement get_adapter_key() returning "cbe_api"
  - Override schema_fingerprint() with CBE-specific fingerprinting (hash publication keys + ExchangeRate item keys)
  - Keep all existing helper functions (_parse_publication, _parse_er_item, _safe_rate, _parse_date)
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [ ] 5.2 Add backward compatibility wrapper to adapters/cbe/adapter.py
  - Create module-level parse() function that instantiates CBEAdapter and calls parse()
  - Create module-level schema_fingerprint() function that instantiates CBEAdapter and calls schema_fingerprint()
  - Ensure existing code calling parse(raw_json) continues to work unchanged
  - _Requirements: 9.6, 12.1, 12.2_

- [ ]* 5.3 Verify CBE adapter backward compatibility and test equivalence
  - Run all existing CBE tests (tests/test_m5_cbe_adapter.py) without modification
  - Verify all tests pass
  - Create equivalence test comparing old function output to new class output for identical inputs
  - _Requirements: 9.7, 9.8, 15.1, 15.2, 15.3, 15.4, 15.5_

### Task 6: Refactor DBE Adapter as HTMLTableAdapter Example

- [ ] 6.1 Create DBEAdapter class in adapters/dbe/adapter.py
  - Inherit from HTMLTableAdapter
  - Implement _process_tables() method with DBE-specific table parsing logic (move existing logic from parse() function)
  - Extract category parameter from options dict
  - Implement get_source_url() returning "https://dbe.com.et/"
  - Implement get_adapter_key() returning "dbe_html"
  - Override requires_category() to return True (Type F adapter)
  - Keep existing helper functions (_parse_date_from_description, _parse_table, _safe_rate)
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [ ] 6.2 Add backward compatibility wrapper to adapters/dbe/adapter.py
  - Create module-level parse() function that instantiates DBEAdapter and calls parse(raw_html, category=category)
  - Ensure existing code calling parse(raw_html, category="UNKNOWN") continues to work
  - _Requirements: 10.6, 12.1, 12.2_

- [ ]* 6.3 Verify DBE adapter backward compatibility and test equivalence
  - Run all existing DBE tests without modification
  - Verify all tests pass
  - Create equivalence test comparing old function output to new class output for identical inputs
  - _Requirements: 10.7, 15.1, 15.2, 15.3, 15.4, 15.5_

### Task 7: Refactor Ahadu Adapter as HTMLTextAdapter Example

- [ ] 7.1 Create AhaduAdapter class in adapters/ahadu/adapter.py
  - Inherit from HTMLTextAdapter
  - Implement _extract_from_text() method with Ahadu-specific regex patterns (move existing logic from parse() function)
  - Extract category parameter from options dict
  - Implement get_source_url() returning "https://ahadubank.com/"
  - Implement get_adapter_key() returning "ahadu_html"
  - Override requires_category() to return True (Type G adapter)
  - Keep existing regex patterns (_DATE_RE, _RATE_RE) and helper functions (_extract_date, _safe_rate)
  - _Requirements: 11.1, 11.2, 11.3, 11.4_

- [ ] 7.2 Add backward compatibility wrapper to adapters/ahadu/adapter.py
  - Create module-level parse() function that instantiates AhaduAdapter and calls parse(raw_html, category=category)
  - Ensure existing code calling parse(raw_html, category="UNKNOWN") continues to work
  - _Requirements: 11.5, 12.1, 12.2_

- [x]* 7.3 Verify Ahadu adapter backward compatibility and test equivalence
  - Run all existing Ahadu tests without modification
  - Verify all tests pass
  - Create equivalence test comparing old function output to new class output for identical inputs
  - _Requirements: 11.6, 15.1, 15.2, 15.3, 15.4, 15.5_

### Task 8: Write Adapter Equivalence Tests

- [ ]* 8.1 Create tests/test_adapter_equivalence.py with comprehensive equivalence tests
  - Test CBE adapter class produces identical AdapterRecords to function for same inputs (verify all fields: source_currency_code, category, buying_rate, selling_rate, effective_date, source_record_key, source_publication_key, raw_excerpt, mapping_notes)
  - Test DBE adapter class produces identical AdapterRecords to function for same inputs
  - Test Ahadu adapter class produces identical AdapterRecords to function for same inputs
  - Test edge cases: empty responses, invalid data, partial failures
  - Test schema_fingerprint() produces identical hashes for same inputs
  - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

### Task 9: Phase 1 Checkpoint - Verify All Tests Pass

- [x] 9.1 Run complete test suite and verify 429 tests pass
  - Run pytest tests/ -v and confirm all 429 existing tests pass
  - Run new unit tests for base classes (tests/test_adapter_bases.py)
  - Run new unit tests for HTTP clients (tests/test_http_client.py)
  - Run new equivalence tests (tests/test_adapter_equivalence.py)
  - Verify code coverage maintained at ≥85%
  - Ensure all tests pass, ask the user if questions arise
  - _Requirements: 12.4, 13.1, 13.6_

---

## Phase 2: Remaining Adapters (Weeks 2-3)

### Task 10: Refactor Batch 1 - JSON Adapters (Days 1-2)

- [x] 10.1 Refactor Rammis adapter (adapters/rammis/adapter.py)
  - Create RammisAdapter class inheriting from JSONAdapter
  - Implement _process_data() method with Rammis-specific extraction logic
  - Implement get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper (module-level parse() function)
  - Verify existing tests pass
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.6, 12.1, 12.3_

- [x] 10.2 Refactor ADIB adapter (adapters/adib/adapter.py)
  - Create ADIBAdapter class inheriting from JSONAdapter
  - Implement _process_data() method with ADIB-specific extraction logic
  - Implement get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper (module-level parse() function)
  - Verify existing tests pass
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.6, 12.1, 12.3_

- [x]* 10.3 Verify Batch 1 tests pass
  - Run tests for Rammis and ADIB adapters
  - Verify no regressions introduced
  - _Requirements: 12.4_

### Task 11: Refactor Batch 2 - HTML Table Adapters Group A (Days 3-4)

- [x] 11.1 Refactor Dashen adapter (adapters/dashen/adapter.py)
  - Create DashenAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables() method with Dashen-specific table parsing logic
  - Implement get_source_url(), get_adapter_key() methods
  - Override requires_category() if needed
  - Add backward compatibility wrapper (module-level parse() function)
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [x] 11.2 Refactor NIB adapter (adapters/nib/adapter.py)
  - Create NIBAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables(), get_source_url(), get_adapter_key() methods
  - Override requires_category() if needed
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [x] 11.3 Refactor Abay adapter (adapters/abay/adapter.py)
  - Create AbayAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables(), get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [ ] 11.4 Refactor Amhara adapter (adapters/amhara/adapter.py)
  - Create AmharaAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables(), get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [x] 11.5 Refactor Awash adapter (adapters/awash/adapter.py)
  - Create AwashAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables(), get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [x]* 11.6 Verify Batch 2 tests pass
  - Run tests for all Batch 2 adapters (Dashen, NIB, Abay, Amhara, Awash)
  - Verify no regressions introduced
  - _Requirements: 12.4_

### Task 12: Refactor Batch 3 - HTML Table Adapters Group B (Days 5-6)

- [x] 12.1 Refactor Berhan adapter (adapters/berhan/adapter.py)
  - Create BerhanAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables(), get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [x] 12.2 Refactor BOA adapter (adapters/boa/adapter.py)
  - Create BOAAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables(), get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [x] 12.3 Refactor Bunna adapter (adapters/bunna/adapter.py)
  - Create BunnaAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables(), get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [x] 12.4 Refactor CBO adapter (adapters/cbo/adapter.py)
  - Create CBOAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables(), get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [x] 12.5 Refactor Enat adapter (adapters/enat/adapter.py)
  - Create EnatAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables(), get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [x]* 12.6 Verify Batch 3 tests pass
  - Run tests for all Batch 3 adapters (Berhan, BOA, Bunna, CBO, Enat)
  - Verify no regressions introduced
  - _Requirements: 12.4_

### Task 13: Refactor Batch 4 - HTML Table Adapters Group C (Days 7-8)

- [x] 13.1 Refactor Gadaa adapter (adapters/gadaa/adapter.py)
  - Create GadaaAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables(), get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [x] 13.2 Refactor Global adapter (adapters/global_/adapter.py)
  - Create GlobalAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables(), get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [ ] 13.3 Refactor Goh Betoch adapter (adapters/goh_betoch/adapter.py)
  - Create GohBetochAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables(), get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [ ] 13.4 Refactor Hibret adapter (adapters/hibret/adapter.py)
  - Create HibretAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables(), get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [ ] 13.5 Refactor Omo adapter (adapters/omo/adapter.py)
  - Create OmoAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables(), get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [ ]* 13.6 Verify Batch 4 tests pass
  - Run tests for all Batch 4 adapters (Gadaa, Global, Goh Betoch, Hibret, Omo)
  - Verify no regressions introduced
  - _Requirements: 12.4_

### Task 14: Refactor Batch 5 - HTML Table Adapters Group D (Days 9-10)

- [ ] 14.1 Refactor Oromia adapter (adapters/oromia/adapter.py)
  - Create OromiaAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables(), get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [ ] 14.2 Refactor Shabelle adapter (adapters/shabelle/adapter.py)
  - Create ShabelleAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables(), get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [ ] 14.3 Refactor Sidama adapter (adapters/sidama/adapter.py)
  - Create SidamaAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables(), get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [ ] 14.4 Refactor Siinqee adapter (adapters/siinqee/adapter.py)
  - Create SiinqeeAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables(), get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [ ] 14.5 Refactor Siket adapter (adapters/siket/adapter.py)
  - Create SiketAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables(), get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [ ]* 14.6 Verify Batch 5 tests pass
  - Run tests for all Batch 5 adapters (Oromia, Shabelle, Sidama, Siinqee, Siket)
  - Verify no regressions introduced
  - _Requirements: 12.4_

### Task 15: Refactor Batch 6 - Final Adapters (Days 11-12)

- [ ] 15.1 Refactor Tsedey adapter (adapters/tsedey/adapter.py)
  - Create TsedeyAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables(), get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [ ] 15.2 Refactor Tsehay adapter (adapters/tsehay/adapter.py)
  - Create TsehayAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables(), get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [ ] 15.3 Refactor Wegagen adapter (adapters/wegagen/adapter.py)
  - Create WegagenAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables(), get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [ ] 15.4 Refactor Zamzam adapter (adapters/zamzam/adapter.py)
  - Create ZamzamAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables(), get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [ ] 15.5 Refactor Zemen adapter (adapters/zemen/adapter.py)
  - Create ZemenAdapter class inheriting from HTMLTableAdapter
  - Implement _process_tables(), get_source_url(), get_adapter_key() methods
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 12.1, 12.3_

- [ ] 15.6 Refactor Anbesa adapter (adapters/anbesa/adapter.py)
  - Create AnbesaAdapter class inheriting from appropriate base class (identify type first)
  - Implement required methods based on adapter type
  - Add backward compatibility wrapper
  - Verify existing tests pass
  - _Requirements: 9.1-11.6, 12.1, 12.3_

- [ ]* 15.7 Verify Batch 6 tests pass
  - Run tests for all Batch 6 adapters (Tsedey, Tsehay, Wegagen, Zamzam, Zemen, Anbesa)
  - Verify no regressions introduced
  - _Requirements: 12.4_

### Task 16: Phase 2 Checkpoint - Verify All 31 Adapters Refactored

- [ ] 16.1 Run complete test suite after all adapter migrations
  - Run pytest tests/ -v and confirm all 429 tests pass
  - Verify all 31 adapters migrated (3 in Phase 1 + 28 in Phase 2)
  - Check that all adapters now inherit from base classes
  - Verify code coverage maintained at ≥85%
  - Generate migration completion report
  - Ensure all tests pass, ask the user if questions arise
  - _Requirements: 12.4, 12.5, 13.1_

---

## Phase 3: Integration and Documentation (Week 4)

### Task 17: Update Documentation

- [ ] 17.1 Create ADR document for adapter base classes
  - Create docs/decisions/ADR-010-adapter-base-classes.md
  - Document context: 31 adapters with ~30% code duplication
  - Document decision: type-specific base classes (JSONAdapter, HTMLTableAdapter, HTMLTextAdapter)
  - Document alternatives considered: config-driven adapters (rejected), single generic base (rejected), no abstraction (rejected)
  - Document consequences: positive (30% less code, uniform interface, better testability), negative (adds abstraction layer), risks (must maintain backward compatibility)
  - _Requirements: 14.1, 14.2, 14.3, 14.4_

- [ ] 17.2 Update developer guide with adapter implementation instructions
  - Create docs/guides/adapter-development.md or update existing guide
  - Provide new adapter checklist: choose base class, implement required methods, override optional methods, add backward compatibility wrapper, write tests
  - Include example template for new adapters
  - Document when to use each base class (JSONAdapter for JSON APIs, HTMLTableAdapter for HTML tables, HTMLTextAdapter for text extraction)
  - _Requirements: 14.5_

- [x] 17.3 Document HTTP client abstraction usage
  - Add section to developer guide explaining HttpClient interface
  - Document RequestsHttpClient for production (with retry configuration)
  - Document MockHttpClient for testing (with pattern matching)
  - Document FileHttpClient for development (with fixture files)
  - Provide examples of dependency injection patterns
  - _Requirements: 14.3_

### Task 18: Create Deployment Checklist

- [ ] 18.1 Create deployment checklist document
  - Create docs/deployment/adapter-refactoring-checklist.md
  - Document pre-deployment steps: all 429 tests pass, code coverage ≥85%, equivalence tests pass, performance tests pass, documentation updated
  - Document deployment steps: deploy to staging, run full test suite in staging, manually verify adapter outputs, deploy to production, monitor error logs for 24 hours
  - Document post-deployment steps: verify production adapters running, check database for new rates, verify no regression in data quality, update runbook
  - Document rollback procedure: git revert command, verification steps, communication plan
  - _Requirements: 12.4, 13.1_

### Task 19: Run Performance Benchmarks

- [ ]* 19.1 Create performance benchmark tests
  - Create tests/test_adapter_performance.py
  - Benchmark CBE adapter: old implementation vs new class (use large fixture with 100+ records)
  - Benchmark DBE adapter: old implementation vs new class
  - Benchmark Ahadu adapter: old implementation vs new class
  - Assert new implementation is equal or faster (≤10% tolerance)
  - Target: base class overhead < 1ms per adapter invocation
  - _Requirements: 13.5_

- [ ]* 19.2 Run benchmarks and document results
  - Execute performance benchmark tests
  - Record results: old time, new time, overhead percentage
  - Document findings in performance-results.md or deployment checklist
  - Verify no slowdown introduced by base classes
  - _Requirements: 13.5_

### Task 20: Final Verification

- [ ] 20.1 Run complete test suite one final time
  - Run pytest tests/ -v --cov=adapters --cov=http --cov-report=term-missing
  - Verify all 429 existing tests pass
  - Verify all new tests pass (base classes, HTTP clients, equivalence, performance)
  - Verify code coverage ≥85%
  - Generate coverage report for review
  - _Requirements: 12.4, 13.1, 13.6_

- [ ] 20.2 Manual verification of adapter outputs
  - Run scheduler against staging environment
  - Verify each of 31 adapters produces exchange rate records
  - Check database for new rates from all adapters
  - Compare outputs to production baseline (spot check 8-10 adapters)
  - Verify effective_date, effective_date_basis, source_record_key, source_publication_key unchanged
  - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

- [ ] 20.3 Code review and final approval
  - Review all code changes for quality and consistency
  - Verify ~30% code reduction achieved in refactored adapters
  - Confirm backward compatibility maintained throughout
  - Verify documentation is complete and accurate
  - Obtain approval to deploy to production
  - Ensure all checks pass, ask the user if questions arise
  - _Requirements: 12.4, 12.5, 13.1, 13.6, 14.1, 14.2, 14.3, 14.4, 14.5_

---

## Notes

### Task Marking
- Tasks marked with `*` are optional testing tasks that can be skipped for faster MVP
- All core implementation tasks (1.1-2.4, 5.1-7.2, 10.1-12.1, 14.1-15.1, 17.1-17.3) are required
- Test tasks (3.1, 4.1, 5.3, 6.3, 7.3, 8.1, 10.4, 11.4, 12.2, 16.1-16.2) are optional but strongly recommended

### Traceability
- Each task references specific requirements from requirements.md for traceability
- Requirements are numbered (e.g., 1.1 = Requirement 1, Acceptance Criterion 1)
- Cross-reference requirements to verify complete coverage

### Checkpoints
- Phase 1 checkpoint (Task 9.1): Verify foundation is solid before proceeding (3 reference adapters done)
- Phase 2 checkpoint (Task 16.1): Verify all 31 adapters migrated successfully
- Final verification (Task 20.1-20.3): Ensure production-ready quality

### Backward Compatibility
- Every refactored adapter maintains module-level function wrappers
- Existing code calling parse(raw_content) continues to work unchanged
- Tests pass without modification throughout all phases
- Safe incremental rollout with instant rollback capability

### Phase 2 Batching Strategy
**Total: 28 remaining adapters (31 total - 3 done in Phase 1)**
- Batch 1 (Days 1-2): 2 JSON adapters (Rammis, ADIB)
- Batch 2 (Days 3-4): 5 HTML table adapters (Dashen, NIB, Abay, Amhara, Awash)
- Batch 3 (Days 5-6): 5 HTML table adapters (Berhan, BOA, Bunna, CBO, Enat)
- Batch 4 (Days 7-8): 5 HTML table adapters (Gadaa, Global, Goh Betoch, Hibret, Omo)
- Batch 5 (Days 9-10): 5 HTML table adapters (Oromia, Shabelle, Sidama, Siinqee, Siket)
- Batch 6 (Days 11-12): 6 final adapters (Tsedey, Tsehay, Wegagen, Zamzam, Zemen, Anbesa)

**Verification after each batch** ensures no regressions accumulate

### Success Criteria
- ✅ All 429 existing tests pass without modification
- ✅ Code coverage maintained at ≥85%
- ✅ ~30% code reduction in refactored adapters
- ✅ Base classes documented with comprehensive docstrings
- ✅ HTTP client abstraction working with production, mock, and file implementations
- ✅ Three reference adapters (CBE, DBE, Ahadu) successfully refactored
- ✅ All 31 adapters migrated to use base classes
- ✅ Documentation updated (ADR, developer guide, deployment checklist)
- ✅ Performance benchmarks confirm no slowdown
- ✅ Production deployment successful with no regressions

