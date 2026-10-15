# Requirements Document: Pipeline and Infrastructure Clean Code Refactoring

## Introduction

This refactoring applies SOLID principles, design patterns, and clean code practices to the pipeline and infrastructure layers of the Ethiopian Bank Exchange Rate system. This is a follow-on to the "Adapter Base Classes and HTTP Abstraction" spec and focuses on eliminating duplication, improving testability, and making the codebase more maintainable by introducing Repository Pattern, Configuration Object, Strategy Pattern, and Registry Pattern.

The refactoring builds on the HttpClient abstraction from the adapter spec, replacing duplicate HTTP logic in scheduler/runner.py and centralizing configuration, database access, and error classification.

## Glossary

- **HttpClient**: The HTTP abstraction interface from the adapter refactoring spec (RequestsHttpClient, MockHttpClient, FileHttpClient)
- **AdapterRegistry**: A central registry for explicit adapter registration and lookup, replacing importlib string manipulation
- **RateSourceRepository**: A repository pattern implementation that centralizes all database queries for the rate_source table
- **Config**: A centralized configuration object that loads settings from environment variables and provides defaults
- **ErrorClassifier**: A strategy pattern implementation for classifying exceptions into error codes and summaries
- **Pipeline_Stage**: Individual processing steps (validate → fingerprint → identity → deduplicate → persist)
- **Chain_of_Responsibility**: A design pattern where pipeline stages are linked and process records sequentially
- **Scheduler**: The scheduler/runner.py module that orchestrates collection runs for bank sources
- **Repository_Pattern**: A design pattern that encapsulates data access logic and provides a clean API for database operations
- **Strategy_Pattern**: A design pattern that encapsulates algorithms (error classification rules) and makes them interchangeable
- **Production_System**: The deployed system currently processing exchange rates with 429 passing tests

## Requirements

### Requirement 1: Integrate HttpClient into Scheduler

**User Story:** As a scheduler, I want to use the same HttpClient abstraction as adapters, so that HTTP logic is not duplicated and testing is consistent.

#### Acceptance Criteria

1. THE Scheduler SHALL accept an HttpClient instance via dependency injection with a default of RequestsHttpClient
2. WHEN the Scheduler needs to fetch bank data, THE Scheduler SHALL use HttpClient.fetch() instead of direct requests library calls
3. THE Scheduler SHALL remove the duplicate _fetch() function and use HttpClient.fetch() for all HTTP operations
4. THE Scheduler SHALL remove direct requests imports (requests.get, requests.post) from scheduler/runner.py
5. THE Scheduler SHALL pass adapter-specific configuration (post_data, extra_headers, ssl_verify) to HttpClient.fetch() via options
6. THE Scheduler SHALL handle HttpResponse.is_success() to determine fetch success
7. THE Scheduler SHALL extract content from HttpResponse.content for parsing
8. THE Scheduler SHALL extract status_code from HttpResponse.status_code for run recording
9. ALL existing scheduler tests SHALL pass without modification
10. THE Scheduler SHALL support MockHttpClient injection for testing without network calls

### Requirement 2: Create AdapterRegistry with Explicit Registration

**User Story:** As a developer, I want adapters to be registered explicitly in a central registry, so that adapter loading is type-safe and doesn't rely on string manipulation trial-and-error.

#### Acceptance Criteria

1. THE System SHALL provide an AdapterRegistry class that stores adapter instances by adapter_key
2. THE AdapterRegistry SHALL provide a register() method that accepts adapter_key and adapter_module
3. THE AdapterRegistry SHALL provide a get() method that returns an adapter by adapter_key or raises KeyError if not found
4. THE AdapterRegistry SHALL provide a list_keys() method that returns all registered adapter keys
5. THE AdapterRegistry SHALL provide an is_registered() method that checks if an adapter_key exists
6. THE System SHALL create a default registry instance and register all 31 adapters at module initialization
7. THE Scheduler SHALL use AdapterRegistry.get() instead of _load_adapter() string manipulation
8. THE AdapterRegistry SHALL raise descriptive errors when adapter_key is not registered
9. THE AdapterRegistry registration SHALL be explicit (no importlib trial-and-error or string suffix guessing)
10. ALL existing adapter loading code SHALL continue to work with the same adapter_key values

### Requirement 3: Create RateSourceRepository for Database Operations

**User Story:** As a data access layer, I want all rate_source table queries centralized in a repository, so that database logic is not scattered and can be tested independently.

#### Acceptance Criteria

1. THE System SHALL provide a RateSourceRepository class that encapsulates all rate_source table operations
2. THE RateSourceRepository SHALL provide a get_by_id() method that returns a source dict or None
3. THE RateSourceRepository SHALL provide a get_enabled_sources() method that returns a list of enabled source dicts
4. THE RateSourceRepository SHALL provide an update_last_success() method that sets last_success_at timestamp
5. THE RateSourceRepository SHALL provide an update_schema_fingerprint() method that stores schema fingerprint
6. THE RateSourceRepository SHALL accept a database connection in its constructor
7. THE Scheduler SHALL use RateSourceRepository methods instead of inline SQL queries
8. THE RateSourceRepository SHALL return dicts with keys matching current implementation (id, adapter_key, source_url, ssl_verify, schema_fingerprint, default_category)
9. THE RateSourceRepository methods SHALL use parameterized queries to prevent SQL injection
10. THE RateSourceRepository SHALL be testable with mock database connections

### Requirement 4: Create Centralized Configuration Object

**User Story:** As a configuration management system, I want all constants and environment variables centralized in a Config class, so that configuration is not hardcoded throughout the codebase.

#### Acceptance Criteria

1. THE System SHALL provide a Config class that loads configuration from environment variables with sensible defaults
2. THE Config class SHALL provide USER_AGENT property with default "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
3. THE Config class SHALL provide REQUEST_TIMEOUT property with default 15 seconds, overridable via REQUEST_TIMEOUT environment variable
4. THE Config class SHALL provide RATE_LIMIT_DELAY property with default 2.0 seconds, overridable via RATE_LIMIT_DELAY environment variable
5. THE Config class SHALL provide MAX_RETRIES property with default 2, overridable via MAX_RETRIES environment variable
6. THE Config class SHALL provide DATABASE_URL property loaded from DATABASE_URL environment variable
7. THE Config class SHALL validate that integer environment variables parse correctly or raise descriptive errors
8. THE Config class SHALL validate that float environment variables parse correctly or raise descriptive errors
9. THE Scheduler SHALL accept a Config instance via dependency injection with a default instance
10. THE Scheduler SHALL remove hardcoded constants (USER_AGENT, REQUEST_TIMEOUT, RATE_LIMIT_DELAY, MAX_RETRIES)

### Requirement 5: Create ErrorClassifier with Strategy Pattern

**User Story:** As an error handling system, I want error classification rules encapsulated in strategies, so that if-else chains are eliminated and new error types can be added without modifying core logic.

#### Acceptance Criteria

1. THE System SHALL provide an ErrorClassifier abstract base class with an abstract classify() method
2. THE classify() method SHALL accept an Exception and return a tuple of (error_code, error_summary)
3. THE System SHALL provide SchemaChangeClassifier that detects schema fingerprint changes
4. THE System SHALL provide ParseFailureClassifier that detects ValueError, KeyError, AttributeError
5. THE System SHALL provide HttpFailureClassifier that detects ConnectionError and Timeout
6. THE System SHALL provide CompositeErrorClassifier that tries classifiers in order until one matches
7. THE CompositeErrorClassifier SHALL return "parse_failure" as fallback when no classifier matches
8. THE Scheduler SHALL use ErrorClassifier instead of _classify_error() if-else chain
9. THE ErrorClassifier strategies SHALL be registered in order of specificity (schema change → parse → http → fallback)
10. THE ErrorClassifier SHALL be injectable for testing with mock classifiers

### Requirement 6: Add Comprehensive Unit Tests for New Components

**User Story:** As a quality assurance requirement, I want comprehensive unit tests for all new infrastructure components, so that refactoring doesn't introduce untested code paths.

#### Acceptance Criteria

1. THE System SHALL provide unit tests for AdapterRegistry.register(), get(), list_keys(), is_registered()
2. THE System SHALL provide unit tests for RateSourceRepository get_by_id(), get_enabled_sources(), update methods
3. THE System SHALL provide unit tests for Config property loading from environment variables
4. THE System SHALL provide unit tests for Config default value fallback when environment variables are not set
5. THE System SHALL provide unit tests for ErrorClassifier strategies (SchemaChangeClassifier, ParseFailureClassifier, HttpFailureClassifier)
6. THE System SHALL provide unit tests for CompositeErrorClassifier fallback behavior
7. THE System SHALL provide integration tests for Scheduler with MockHttpClient injection
8. THE System SHALL provide integration tests for Scheduler with mock RateSourceRepository
9. THE System SHALL maintain or improve code coverage percentage after refactoring
10. ALL existing 429 tests SHALL pass without modification

### Requirement 7: Maintain Complete Backward Compatibility

**User Story:** As the production system, I want all existing code and tests to continue working without modification, so that the refactoring is safe and can be deployed incrementally.

#### Acceptance Criteria

1. THE Scheduler public API (run_source, run_all) SHALL remain unchanged
2. THE Scheduler SHALL continue to accept database connection as first parameter
3. THE Scheduler return values (summary dicts) SHALL remain unchanged
4. THE Scheduler error codes SHALL remain unchanged (http_failure, parse_failure, schema_change, suspicious_data)
5. THE rate_source table schema SHALL not be modified
6. THE database query results SHALL remain unchanged (same columns, same data types)
7. THE pipeline logic behavior SHALL not change (same validation, fingerprinting, deduplication)
8. ALL 429 existing tests SHALL pass without modification
9. THE refactoring SHALL NOT require updates to scheduler/run_job.py or other calling code
10. THE refactoring SHALL be deployable without database migrations

### Requirement 8: Refactor Scheduler to Use New Components

**User Story:** As a scheduler implementation, I want to use the new infrastructure components, so that code duplication is eliminated and testing is easier.

#### Acceptance Criteria

1. THE Scheduler SHALL accept Config, HttpClient, RateSourceRepository, ErrorClassifier via constructor dependency injection
2. THE Scheduler constructor SHALL provide sensible defaults (RequestsHttpClient, Config(), etc.) when dependencies are not provided
3. THE Scheduler SHALL use Config properties instead of module-level constants
4. THE Scheduler SHALL use HttpClient.fetch() instead of _fetch() function
5. THE Scheduler SHALL use RateSourceRepository.get_by_id() instead of _load_source() inline SQL
6. THE Scheduler SHALL use RateSourceRepository.get_enabled_sources() instead of _load_enabled_sources() inline SQL
7. THE Scheduler SHALL use RateSourceRepository.update_last_success() instead of _update_last_success() inline SQL
8. THE Scheduler SHALL use RateSourceRepository.update_schema_fingerprint() instead of inline UPDATE in _check_schema()
9. THE Scheduler SHALL use ErrorClassifier.classify() instead of _classify_error() if-else chain
10. THE Scheduler SHALL use AdapterRegistry.get() instead of _load_adapter() string manipulation

### Requirement 9: Document Infrastructure Patterns

**User Story:** As a developer, I want clear documentation of infrastructure patterns, so that I understand how to use and extend the new components.

#### Acceptance Criteria

1. THE AdapterRegistry SHALL have docstrings explaining registration and lookup patterns
2. THE RateSourceRepository SHALL have docstrings explaining repository pattern and method usage
3. THE Config class SHALL have docstrings explaining environment variable names and default values
4. THE ErrorClassifier SHALL have docstrings explaining strategy pattern and how to add new classifiers
5. THE Scheduler refactored code SHALL have comments explaining dependency injection points
6. THE System SHALL provide example code showing how to test with mock dependencies
7. THE System SHALL provide migration guide explaining how other modules can adopt these patterns
8. THE Config class SHALL document which environment variables are read and their formats
9. THE RateSourceRepository SHALL document expected dict structure for return values
10. THE ErrorClassifier SHALL document error_code values and their meanings

### Requirement 10: (Optional) Refactor Pipeline to Chain of Responsibility

**User Story:** As a pipeline orchestration system, I want pipeline stages linked using Chain of Responsibility pattern, so that stage sequencing is explicit and stages can be added/removed without changing orchestration code.

#### Acceptance Criteria

1. THE System SHALL provide a PipelineStage abstract base class with process() and set_next() methods
2. THE System SHALL provide ValidateStage, FingerprintStage, IdentityStage, DeduplicateStage, PersistStage implementations
3. WHEN a stage completes processing, THE Stage SHALL call next_stage.process() if next_stage exists
4. THE Pipeline SHALL be constructed by chaining stages: validate → fingerprint → identity → deduplicate → persist
5. THE ingest() function SHALL initialize the pipeline chain and invoke the first stage
6. THE Pipeline stages SHALL pass record context through the chain without global state
7. THE Pipeline SHALL continue to return IngestResult with correct counts
8. THE Pipeline stages SHALL be testable in isolation by mocking next_stage
9. ALL existing pipeline tests SHALL pass without modification
10. THE Pipeline behavior SHALL remain identical (same validation, fingerprinting, deduplication logic)

**Note:** This requirement is marked optional and lower priority. It may be deferred to a future refactoring cycle if higher-priority requirements take longer than expected.

## Non-Functional Requirements

### Performance

- Refactored scheduler SHALL have equivalent or better performance compared to original implementation
- Dependency injection SHALL add negligible overhead (< 1ms per run_source() call)
- Repository queries SHALL generate identical SQL to original inline queries
- Configuration object property access SHALL be O(1) constant time

### Maintainability

- Infrastructure components SHALL eliminate duplicate code (HTTP logic, SQL queries, error classification)
- New bank adapters SHALL use AdapterRegistry.register() for explicit registration
- Database schema changes for rate_source SHALL only require changes in RateSourceRepository
- Configuration changes SHALL only require changes in Config class
- New error classification rules SHALL only require adding new ErrorClassifier strategies

### Testability

- All infrastructure components SHALL be testable in isolation with mock dependencies
- Scheduler SHALL be testable with MockHttpClient, mock RateSourceRepository, mock ErrorClassifier
- Tests SHALL NOT require database connections when using mock repositories
- Tests SHALL NOT require network access when using MockHttpClient
- Configuration SHALL be testable by setting environment variables or injecting Config instances

### Safety

- The refactoring SHALL NOT modify database schema
- The refactoring SHALL NOT change pipeline logic behavior
- The refactoring SHALL NOT change scheduler return values or error codes
- The refactoring SHALL NOT require updates to calling code (scheduler/run_job.py, seed_and_run.py)
- The refactoring SHALL be deployable without database migrations
- The refactoring SHALL be reversible by keeping original functions as thin wrappers around new components

## Success Criteria

1. HttpClient integration eliminates duplicate _fetch() logic in scheduler/runner.py
2. AdapterRegistry provides explicit, type-safe adapter registration for all 31 adapters
3. RateSourceRepository centralizes all rate_source table queries
4. Config class centralizes all configuration constants and environment variable loading
5. ErrorClassifier eliminates if-else chains with strategy pattern
6. All 429 existing tests pass without modification
7. New infrastructure components have comprehensive unit tests
8. Code coverage maintained at ≥85%
9. Scheduler code is approximately 20-30% shorter and more readable
10. Documentation allows new developers to understand and extend infrastructure patterns
11. (Optional) Pipeline refactored to Chain of Responsibility if time permits

## Special Notes

### Parser and Serializer Guidance

This refactoring does not introduce parsers or serializers beyond what exists in the adapter layer. The existing adapter parsing logic remains unchanged. Future refactoring cycles may consider parser-specific patterns if needed.

### Integration with Adapter Refactoring

This spec builds directly on the adapter refactoring spec:

- **Reuses HttpClient**: scheduler/runner.py will use RequestsHttpClient, MockHttpClient, FileHttpClient from adapters/http_client.py
- **Reuses AdapterRegistry pattern**: The registry pattern introduced here mirrors the base class pattern from adapter refactoring
- **Maintains consistency**: Both specs follow SOLID principles and prioritize testability

### Deployment Strategy

1. Phase 1: Create infrastructure components (AdapterRegistry, RateSourceRepository, Config, ErrorClassifier)
2. Phase 2: Add comprehensive unit tests for new components
3. Phase 3: Refactor scheduler to use new components with backward compatibility
4. Phase 4: Verify all 429 tests pass
5. Phase 5: Deploy to production with monitoring
6. Phase 6 (Optional): Refactor pipeline to Chain of Responsibility if time permits

### Configuration Environment Variables

The Config class reads these environment variables:

- `REQUEST_TIMEOUT`: HTTP request timeout in seconds (default: 15)
- `RATE_LIMIT_DELAY`: Delay between requests in seconds (default: 2.0)
- `MAX_RETRIES`: Maximum HTTP retry attempts (default: 2)
- `DATABASE_URL`: PostgreSQL connection string (required for production)

All variables have sensible defaults except DATABASE_URL which must be set in production.
