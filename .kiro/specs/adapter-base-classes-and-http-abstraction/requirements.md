# Requirements Document: Adapter Base Classes and HTTP Abstraction

## Introduction

This refactoring improves the Ethiopian Bank Exchange Rate system by introducing abstraction layers to reduce code duplication across 31 bank adapters. The system currently parses exchange rates from banks using different formats (JSON, HTML tables, text). While 31 separate adapters is the correct architectural choice (see ADAPTER_GENERALIZATION_ANALYSIS.md), we can reduce duplication through type-specific base classes and HTTP client abstraction without losing the explicitness and maintainability of individual adapters.

## Glossary

- **Adapter**: A module that parses raw bank data (JSON/HTML/text) into AdapterRecords
- **Type-Specific Base Class**: An abstract class providing common parsing infrastructure for adapters of the same format type (e.g., JSONAdapter, HTMLTableAdapter)
- **HttpClient**: An injectable interface for fetching HTTP content from bank URLs
- **ParseResult**: A structured return type containing successfully parsed records, errors, and warnings
- **Backward Compatibility**: The requirement that existing code continues to work without modification after the refactoring
- **Reference Adapter**: One of three adapters (CBE, DBE, Ahadu) refactored as implementation examples
- **Production System**: The deployed system currently processing exchange rates with 429 passing tests

## Requirements

### Requirement 1: Create Base Adapter Interface

**User Story:** As a developer, I want a common interface for all bank adapters, so that adapters are consistent and follow the Liskov Substitution Principle.

#### Acceptance Criteria

1. THE System SHALL define a BankAdapter abstract base class with an abstract parse() method that returns ParseResult
2. THE BankAdapter class SHALL provide a get_source_url() abstract method that returns the bank's data URL
3. THE BankAdapter class SHALL provide a get_adapter_key() method with a default implementation that converts class name to snake_case
4. THE BankAdapter class SHALL provide an optional schema_fingerprint() method that returns a deterministic hash of data structure
5. THE BankAdapter class SHALL provide an optional requires_category() method that returns False by default
6. THE BankAdapter class SHALL provide helper methods _safe_rate(), _parse_iso_date(), and _rate_text() for common transformations
7. THE ParseResult class SHALL contain records list, errors list, and warnings list
8. THE ParseResult class SHALL provide is_success() method that returns True if at least one record was parsed
9. WHEN an adapter cannot parse fundamentally invalid input, THE Adapter SHALL raise ValueError
10. WHEN an adapter encounters non-fatal errors during parsing, THE Adapter SHALL add errors to ParseResult.errors and continue processing

### Requirement 2: Create JSONAdapter Base Class

**User Story:** As a developer implementing a JSON-based adapter, I want common JSON parsing infrastructure, so that I only write bank-specific extraction logic.

#### Acceptance Criteria

1. THE System SHALL provide a JSONAdapter abstract base class that inherits from BankAdapter
2. WHEN parse() is called on JSONAdapter, THE JSONAdapter SHALL parse the raw content as JSON
3. IF JSON parsing fails, THEN THE JSONAdapter SHALL raise ValueError with a descriptive error message
4. WHEN JSON is successfully parsed, THE JSONAdapter SHALL call abstract method _process_data() with the parsed data
5. THE JSONAdapter SHALL provide a default schema_fingerprint() implementation that hashes top-level keys of JSON structure
6. THE _process_data() abstract method SHALL accept parsed data and optional keyword arguments and return ParseResult

### Requirement 3: Create HTMLTableAdapter Base Class

**User Story:** As a developer implementing an HTML table-based adapter, I want common HTML parsing and table extraction, so that I only write bank-specific row parsing logic.

#### Acceptance Criteria

1. THE System SHALL provide an HTMLTableAdapter abstract base class that inherits from BankAdapter
2. WHEN parse() is called on HTMLTableAdapter, THE HTMLTableAdapter SHALL parse HTML and extract all table elements
3. IF no tables are found, THEN THE HTMLTableAdapter SHALL return ParseResult with an error message
4. WHEN tables are found, THE HTMLTableAdapter SHALL call abstract method _process_tables() with BeautifulSoup object and table list
5. THE HTMLTableAdapter SHALL provide a default schema_fingerprint() implementation that hashes table count and header cells
6. THE _process_tables() abstract method SHALL accept soup, tables list, and optional keyword arguments and return ParseResult

### Requirement 4: Create HTMLTextAdapter Base Class

**User Story:** As a developer implementing a text extraction adapter, I want common HTML text extraction, so that I only write bank-specific regex pattern matching logic.

#### Acceptance Criteria

1. THE System SHALL provide an HTMLTextAdapter abstract base class that inherits from BankAdapter
2. WHEN parse() is called on HTMLTextAdapter, THE HTMLTextAdapter SHALL parse HTML and extract normalized text content
3. THE HTMLTextAdapter SHALL normalize whitespace in extracted text by joining with single spaces
4. WHEN text is extracted, THE HTMLTextAdapter SHALL call abstract method _extract_from_text() with normalized text and BeautifulSoup object
5. THE _extract_from_text() abstract method SHALL accept text string, soup object, and optional keyword arguments and return ParseResult

### Requirement 5: Create HttpClient Interface

**User Story:** As a developer, I want an abstraction for HTTP fetching, so that adapters can be tested without real network calls.

#### Acceptance Criteria

1. THE System SHALL define an HttpClient abstract interface with an abstract fetch() method
2. THE fetch() method SHALL accept a URL string and optional keyword arguments
3. THE fetch() method SHALL return an HttpResponse object containing content, status_code, url, and optional error
4. THE HttpResponse SHALL provide an is_success() method that returns True when status_code is 200 and error is None

### Requirement 6: Implement RequestsHttpClient

**User Story:** As a production system, I want a production HTTP client with retries and timeout handling, so that temporary network issues don't cause failures.

#### Acceptance Criteria

1. THE System SHALL provide a RequestsHttpClient implementation of HttpClient
2. THE RequestsHttpClient SHALL use the requests library for HTTP operations
3. THE RequestsHttpClient SHALL support configurable timeout with a default of 15 seconds
4. THE RequestsHttpClient SHALL support automatic retries with exponential backoff with a default of 2 retries
5. THE RequestsHttpClient SHALL support configurable User-Agent header with a sensible default
6. THE RequestsHttpClient SHALL support SSL verification control via ssl_verify option
7. THE RequestsHttpClient SHALL support POST requests when post_data option is provided
8. THE RequestsHttpClient SHALL support custom headers via headers option
9. WHEN a request succeeds with status 200, THE RequestsHttpClient SHALL return HttpResponse with is_success True
10. WHEN a request fails after all retries, THE RequestsHttpClient SHALL return HttpResponse with error message and is_success False

### Requirement 7: Implement MockHttpClient for Testing

**User Story:** As a test suite, I want a mock HTTP client that returns pre-configured responses, so that tests don't make real network calls.

#### Acceptance Criteria

1. THE System SHALL provide a MockHttpClient implementation of HttpClient
2. THE MockHttpClient SHALL accept a dictionary mapping URL patterns to response content in its constructor
3. WHEN fetch() is called, THE MockHttpClient SHALL match the URL against configured patterns
4. WHEN a matching pattern is found, THE MockHttpClient SHALL return HttpResponse with the configured content and status 200
5. WHEN no matching pattern is found, THE MockHttpClient SHALL return HttpResponse with status 404 and error message
6. THE MockHttpClient SHALL track fetch_count and last_url for test assertions
7. THE MockHttpClient SHALL provide a configure_response() method to add mock responses after construction

### Requirement 8: Implement FileHttpClient for Development

**User Story:** As a developer, I want an HTTP client that loads responses from fixture files, so that I can test with real bank responses without making network calls.

#### Acceptance Criteria

1. THE System SHALL provide a FileHttpClient implementation of HttpClient
2. THE FileHttpClient SHALL accept a fixtures directory path in its constructor
3. WHEN fetch() is called, THE FileHttpClient SHALL extract the domain from the URL
4. THE FileHttpClient SHALL attempt to load a fixture file named {domain}.html or {domain}.json
5. WHEN a fixture file is found, THE FileHttpClient SHALL return HttpResponse with file content and status 200
6. WHEN no fixture file is found, THE FileHttpClient SHALL return HttpResponse with status 404 and error message

### Requirement 9: Refactor CBE Adapter as JSONAdapter Example

**User Story:** As a reference implementation, I want the CBE adapter refactored using JSONAdapter, so that developers can see how to use the base class.

#### Acceptance Criteria

1. THE CBE Adapter SHALL inherit from JSONAdapter instead of using standalone functions
2. THE CBE Adapter SHALL implement _process_data() method containing CBE-specific extraction logic
3. THE CBE Adapter SHALL override schema_fingerprint() with CBE-specific fingerprinting logic
4. THE CBE Adapter SHALL implement get_source_url() returning the CBE API URL
5. THE CBE Adapter SHALL implement get_adapter_key() returning "cbe_api"
6. THE CBE Adapter SHALL maintain backward compatibility by providing parse() and schema_fingerprint() module-level functions
7. ALL existing CBE adapter tests SHALL pass without modification
8. THE CBE Adapter code SHALL be approximately 30% shorter than the original implementation

### Requirement 10: Refactor DBE Adapter as HTMLTableAdapter Example

**User Story:** As a reference implementation, I want the DBE adapter refactored using HTMLTableAdapter, so that developers can see how to use HTML table base classes.

#### Acceptance Criteria

1. THE DBE Adapter SHALL inherit from HTMLTableAdapter instead of using standalone functions
2. THE DBE Adapter SHALL implement _process_tables() method containing DBE-specific table parsing logic
3. THE DBE Adapter SHALL override requires_category() to return True since DBE is Type F
4. THE DBE Adapter SHALL implement get_source_url() returning the DBE website URL
5. THE DBE Adapter SHALL implement get_adapter_key() returning "dbe_html"
6. THE DBE Adapter SHALL maintain backward compatibility by providing parse() module-level function
7. ALL existing DBE adapter tests SHALL pass without modification

### Requirement 11: Refactor Ahadu Adapter as HTMLTextAdapter Example

**User Story:** As a reference implementation, I want the Ahadu adapter refactored using HTMLTextAdapter, so that developers can see how to use text extraction base classes.

#### Acceptance Criteria

1. THE Ahadu Adapter SHALL inherit from HTMLTextAdapter instead of using standalone functions
2. THE Ahadu Adapter SHALL implement _extract_from_text() method containing Ahadu-specific regex patterns
3. THE Ahadu Adapter SHALL implement get_source_url() returning the Ahadu website URL
4. THE Ahadu Adapter SHALL implement get_adapter_key() returning "ahadu_html"
5. THE Ahadu Adapter SHALL maintain backward compatibility by providing parse() module-level function
6. ALL existing Ahadu adapter tests SHALL pass without modification

### Requirement 12: Maintain Complete Backward Compatibility

**User Story:** As the production system, I want all existing code to continue working without modification, so that the refactoring is safe and can be deployed incrementally.

#### Acceptance Criteria

1. WHEN existing code calls module-level parse() functions, THE System SHALL continue to work without modification
2. WHEN existing code calls module-level schema_fingerprint() functions, THE System SHALL continue to work without modification
3. THE System SHALL continue to support the existing function-based adapter API for all non-refactored adapters
4. ALL 429 existing tests SHALL pass without modification
5. THE System SHALL allow gradual migration of adapters one at a time without breaking non-migrated adapters

### Requirement 13: Maintain Test Coverage

**User Story:** As a quality assurance requirement, I want test coverage maintained or improved, so that the refactoring doesn't introduce untested code paths.

#### Acceptance Criteria

1. THE System SHALL maintain or improve code coverage percentage after refactoring
2. THE Base adapter classes SHALL have unit tests for common functionality
3. THE HttpClient implementations SHALL have unit tests verifying their behavior
4. THE Refactored reference adapters SHALL continue to pass all existing tests
5. WHEN base class functionality is tested, THE Tests SHALL verify correct behavior for edge cases

### Requirement 14: Provide Documentation for Base Classes

**User Story:** As a developer adding a new bank adapter, I want clear documentation on how to use base classes, so that I can implement adapters efficiently.

#### Acceptance Criteria

1. THE BankAdapter interface SHALL have docstrings explaining each abstract and optional method
2. THE Type-specific base classes SHALL have docstrings with usage examples
3. THE HttpClient interface SHALL have docstrings explaining the abstraction and its purpose
4. THE ParseResult class SHALL have docstrings explaining fields and methods
5. THE Refactored reference adapters SHALL serve as working examples in comments

### Requirement 15: Verify No Functionality Changes

**User Story:** As a safety requirement, I want to verify that adapter behavior is unchanged, so that the refactoring doesn't alter production data processing.

#### Acceptance Criteria

1. THE Refactored adapters SHALL produce identical AdapterRecords for the same input as the original implementations
2. THE Refactored adapters SHALL raise ValueError for the same invalid inputs as the original implementations
3. THE Refactored adapters SHALL return identical ParseResult.errors for partial failures as the original implementations
4. THE Refactored adapters SHALL generate identical schema fingerprints for the same inputs as the original implementations
5. THE Refactored adapters SHALL maintain identical effective_date, effective_date_basis, source_record_key, and source_publication_key values

## Non-Functional Requirements

### Performance

- Refactored adapters SHALL have equivalent or better performance compared to original implementations
- Base class method calls SHALL add negligible overhead (< 1ms per adapter invocation)

### Maintainability

- Base classes SHALL reduce code duplication by approximately 30%
- New bank adapters SHALL require less boilerplate code when using base classes
- Each base class SHALL be under 200 lines of code

### Safety

- The refactoring SHALL NOT modify database schema
- The refactoring SHALL NOT change pipeline logic
- The refactoring SHALL NOT require updates to all 31 adapters immediately
- The refactoring SHALL NOT create config-driven adapters (keep bank logic as code)

## Success Criteria

1. Base classes created and documented with comprehensive docstrings
2. HTTP client abstraction working with production, mock, and file implementations
3. Three reference adapters (CBE, DBE, Ahadu) successfully refactored
4. All 429 existing tests passing without modification
5. Backward compatibility verified by running production system against refactored code
6. Code coverage maintained at current level or improved
7. Code review confirms approximately 30% reduction in duplication for refactored adapters
8. Documentation allows new developers to use base classes without additional guidance
