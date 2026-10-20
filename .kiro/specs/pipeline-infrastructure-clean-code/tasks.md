# Implementation Plan: Pipeline Infrastructure Clean Code Refactoring

## Overview

This implementation applies SOLID principles, design patterns, and clean code practices to refactor the scheduler and infrastructure layers. The refactoring eliminates code duplication, improves testability, and centralizes configuration, database access, and error classification while maintaining complete backward compatibility with all 429 existing tests.

**Key Objectives**:
- Integrate HttpClient from adapter spec to eliminate duplicate HTTP logic
- Create AdapterRegistry for type-safe adapter registration (31 adapters)
- Implement RateSourceRepository pattern for centralized database operations
- Build Config class for environment-driven configuration
- Apply Strategy Pattern with ErrorClassifier for extensible error handling
- Achieve 35% code reduction in scheduler while maintaining 100% backward compatibility

**Implementation Language**: Python

## Tasks

- [ ] 1. Create infrastructure directory and Config class
  - Create `infrastructure/` directory with `__init__.py`
  - Implement `infrastructure/config.py` with Config dataclass
  - Add environment variable loading (REQUEST_TIMEOUT, RATE_LIMIT_DELAY, MAX_RETRIES, DATABASE_URL)
  - Add validation in `__post_init__` method
  - Use `frozen=True` for immutability
  - Provide sensible defaults: REQUEST_TIMEOUT=15, RATE_LIMIT_DELAY=2.0, MAX_RETRIES=2
  - Add comprehensive docstrings explaining environment variables
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

- [ ]* 1.1 Write unit tests for Config class
  - Test default values when environment variables not set
  - Test environment variable override with monkeypatch
  - Test validation errors for invalid values (negative timeout, negative delay)
  - Test Config immutability (frozen dataclass)
  - Test DATABASE_URL loading
  - _Requirements: 6.3, 6.4_

- [ ] 2. Implement AdapterRegistry with explicit registration
  - Create `infrastructure/adapter_registry.py`
  - Implement AdapterRegistry class with `_adapters` dict
  - Add `register(adapter_key, adapter_module)` method
  - Add `get(adapter_key)` method with descriptive KeyError
  - Add `list_keys()` method
  - Add `is_registered(adapter_key)` method
  - Create `default_registry` instance
  - Explicitly register all 31 adapters (cbe, dashen, dbe, etc.)
  - Import all adapter modules at top of file
  - Add comprehensive docstrings
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.9_

- [ ]* 2.1 Write unit tests for AdapterRegistry
  - Test register() and get() with mock adapters
  - Test duplicate registration raises ValueError
  - Test get() with unregistered key raises descriptive KeyError
  - Test list_keys() returns all registered keys
  - Test is_registered() returns correct boolean
  - Test default_registry has all 31 adapters registered
  - _Requirements: 6.1_

- [ ] 3. Implement RateSourceRepository for database operations
  - Create `infrastructure/rate_source_repository.py`
  - Implement RateSourceRepository class with conn parameter
  - Add `get_by_id(source_id)` returning dict or None
  - Add `get_enabled_sources()` returning list of dicts
  - Add `update_last_success(source_id)` method
  - Add `update_schema_fingerprint(source_id, fingerprint)` method
  - Use parameterized queries for SQL injection prevention
  - Return dicts with keys: id, adapter_key, source_url, ssl_verify, schema_fingerprint, default_category
  - Add comprehensive docstrings
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.8, 3.9_

- [ ]* 3.1 Write unit tests for RateSourceRepository
  - Test get_by_id() with mock connection and cursor
  - Test get_by_id() returns None when not found
  - Test get_enabled_sources() returns list of source dicts
  - Test update_last_success() executes correct UPDATE SQL
  - Test update_schema_fingerprint() executes correct UPDATE SQL
  - Verify parameterized queries are used (check execute call args)
  - Verify dict structure matches expected keys
  - _Requirements: 6.2_

- [ ] 4. Implement ErrorClassifier with Strategy Pattern
  - Create `infrastructure/error_classifier.py`
  - Create ErrorClassifier abstract base class with abstract `classify(exc)` method
  - Implement SchemaChangeClassifier detecting "Schema fingerprint" or "schema" keyword
  - Implement ParseFailureClassifier detecting ValueError, KeyError, AttributeError
  - Implement HttpFailureClassifier detecting ConnectionError and Timeout
  - Implement CompositeErrorClassifier with list of classifiers and fallback
  - Create `default_classifier` instance with all strategies registered
  - Register classifiers in order: SchemaChange → ParseFailure → HttpFailure
  - Add comprehensive docstrings explaining strategy pattern
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.9_

- [ ]* 4.1 Write unit tests for ErrorClassifier strategies
  - Test SchemaChangeClassifier matches schema errors
  - Test ParseFailureClassifier matches ValueError, KeyError, AttributeError
  - Test HttpFailureClassifier matches ConnectionError and Timeout
  - Test CompositeErrorClassifier returns first match in order
  - Test CompositeErrorClassifier fallback when no classifier matches
  - Test default_classifier includes all strategies
  - _Requirements: 6.5, 6.6_

- [ ] 5. Checkpoint - Verify infrastructure components
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Refactor scheduler/runner.py to use Scheduler class
  - Import all infrastructure components (Config, AdapterRegistry, RateSourceRepository, ErrorClassifier)
  - Import HttpClient from adapters.http.client (RequestsHttpClient, MockHttpClient)
  - Create Scheduler class with dependency injection constructor
  - Add constructor parameters: config, http_client, adapter_registry, error_classifier
  - Provide sensible defaults in constructor (Config(), RequestsHttpClient, default_registry, default_classifier)
  - Create RequestsHttpClient from config values in constructor
  - Move run_source() logic into Scheduler.run_source() method
  - Replace `_load_source()` with `RateSourceRepository(conn).get_by_id()`
  - Replace `_load_adapter()` with `self.adapter_registry.get()`
  - Replace `_fetch()` with `self.http_client.fetch()`
  - Replace `_classify_error()` with `self.error_classifier.classify()`
  - Replace `_update_last_success()` with `repo.update_last_success()`
  - Update `_check_schema()` to accept repo parameter and use `repo.update_schema_fingerprint()`
  - Move run_all() logic into Scheduler.run_all() method
  - Replace `_load_enabled_sources()` with `RateSourceRepository(conn).get_enabled_sources()`
  - Remove all hardcoded constants (USER_AGENT, REQUEST_TIMEOUT, RATE_LIMIT_DELAY, MAX_RETRIES)
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 4.9, 4.10_

- [x] 7. Add backward compatibility wrappers
  - Keep module-level `run_source(conn, source_id)` function
  - Implement as wrapper: `return Scheduler().run_source(conn, source_id)`
  - Keep module-level `run_all(conn)` function
  - Implement as wrapper: `return Scheduler().run_all(conn)`
  - Add docstrings noting backward compatibility
  - Comment old helper functions for reference (do not delete yet)
  - _Requirements: 7.1, 7.2, 7.3, 7.9_

- [ ]* 7.1 Write integration tests for Scheduler with mocks
  - Test Scheduler.run_source() with all mocked dependencies
  - Test successful collection run with MockHttpClient
  - Test HTTP failure handling with mock error response
  - Test parse failure handling with adapter raising ValueError
  - Test schema change detection
  - Test run_all() with multiple sources
  - Use fixtures for mock dependencies (config, http_client, registry, classifier, connection)
  - _Requirements: 6.7, 6.8_

- [ ]* 7.2 Write integration tests with real HttpClient implementations
  - Test Scheduler with MockHttpClient and real adapter (cbe)
  - Test Scheduler with FileHttpClient and real adapter
  - Use real adapter.parse() with mock HTTP responses
  - Verify end-to-end integration
  - _Requirements: 1.10_

- [ ]* 7.3 Write backward compatibility tests
  - Test module-level run_source() function still works
  - Test module-level run_all() function still works
  - Verify return value structure unchanged
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 8. Checkpoint - Verify all 429 existing tests pass
  - Run complete test suite: `pytest tests/ -v`
  - Verify 429/429 tests pass without modification
  - Ensure all tests pass, ask the user if questions arise.
  - _Requirements: 6.10, 7.6, 7.8_

- [ ] 9. Add documentation and docstrings
  - Add docstrings to AdapterRegistry explaining registration pattern
  - Add docstrings to RateSourceRepository explaining repository pattern
  - Add docstrings to Config explaining environment variables
  - Add docstrings to ErrorClassifier explaining strategy pattern
  - Add comments to Scheduler explaining dependency injection
  - Document error_code values and meanings
  - Add example code showing how to test with mocks
  - Document dict structure returned by RateSourceRepository
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.8, 9.9_

- [ ] 10. Create migration guide and update documentation
  - Create migration guide explaining refactoring changes
  - Document how other modules can adopt infrastructure patterns
  - Update README if needed
  - Document environment variables in deployment guide
  - Add ADR (Architecture Decision Record) for refactoring
  - _Requirements: 9.7_

- [ ] 11. Final checkpoint and code review
  - Verify all requirements met (Requirements 1-9)
  - Verify 35% code reduction in scheduler achieved
  - Verify 100% testability (no I/O in tests)
  - Verify complete backward compatibility
  - Verify code coverage maintained at ≥85%
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. (Optional) Refactor pipeline to Chain of Responsibility
  - Create PipelineStage abstract base class with process() and set_next() methods
  - Implement ValidateStage, FingerprintStage, IdentityStage, DeduplicateStage, PersistStage
  - Chain stages: validate → fingerprint → identity → deduplicate → persist
  - Update ingest() function to use pipeline chain
  - Ensure record context passed through chain
  - Maintain same IngestResult return value
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_

- [ ]* 12.1 (Optional) Write tests for pipeline Chain of Responsibility
  - Test each stage in isolation with mock next_stage
  - Test complete pipeline chain integration
  - Verify existing pipeline tests still pass
  - Verify pipeline behavior unchanged
  - _Requirements: 10.8, 10.9, 10.10_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP (test tasks are recommended but not required for core implementation)
- Requirement 10 (Pipeline Chain of Responsibility) is explicitly marked optional and lower priority - defer if needed
- Each task references specific requirements from requirements.md for traceability
- All 429 existing tests must pass throughout the refactoring
- No database schema changes required
- Complete backward compatibility maintained via module-level function wrappers
- Checkpoints ensure incremental validation at key milestones
- Implementation uses Python with type hints, dataclasses, and pytest
- Target: 35% code reduction in scheduler, 100% testability, ≥85% code coverage

## Implementation Strategy

**Phase 1 (Week 1, Days 1-2)**: Tasks 1-4 - Create all infrastructure components
**Phase 2 (Week 1, Days 3-4)**: Task 5 checkpoint, then Tasks 6-7 - Refactor scheduler with dependency injection
**Phase 3 (Week 1, Day 5)**: Task 8 checkpoint - Verify all 429 tests pass
**Phase 4 (Week 2, Days 1-2)**: Tasks 9-10 - Documentation and migration guide
**Phase 5 (Week 2, Day 3)**: Task 11 - Final review and verification
**Phase 6 (Optional)**: Task 12 - Pipeline Chain of Responsibility if time permits

## Success Criteria

✓ All 429 existing tests pass without modification
✓ Infrastructure components have comprehensive unit tests (100% coverage)
✓ Scheduler is 35% shorter and fully testable with mocks
✓ Zero code duplication (HTTP, SQL, error classification)
✓ Complete backward compatibility maintained
✓ Code coverage ≥85%
✓ Environment-driven configuration (12-factor app)
✓ Type-safe adapter registry (no importlib trial-and-error)
