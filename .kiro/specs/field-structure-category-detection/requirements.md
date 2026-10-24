# Requirements Document: Field-Structure-Based Category Detection

## Introduction

This feature provides a systematic, reusable approach for API adapters to detect exchange rate categories (cash, transactional, weighted_average) from JSON field structures. Currently, 32 bank adapters handle category detection inconsistently—some hard-code categories, some mark rates as UNKNOWN (making data invisible), and some use custom logic. This leads to data loss and maintenance complexity.

The feature implements the No-Data-Loss Principle: when a bank API publishes structurally distinct field pairs (e.g., `buying` + `tra_buying`), the system SHALL emit one record per field pair, even if values are numerically identical. This ensures complete data capture and adapts automatically when banks change their rate publication policies.

**Key Insight**: Field structure signals publishing intent. If a bank includes both `buying` and `tra_buying` fields, they intend to publish both categories, regardless of whether the values currently happen to be equal.

## Glossary

- **Field_Detector**: Component that identifies which rate field pairs (buying/selling) exist in an API response structure
- **Category_Mapper**: Component that maps field names to canonical categories using pattern matching
- **Record_Emitter**: Component that creates one AdapterRecord per detected field pair with appropriate category
- **Field_Pair**: A tuple of (buying_field_name, selling_field_name) representing one complete rate
- **Canonical_Category**: One of four valid category codes: cash, transactional, weighted_average, indicative_reference
- **Field_Structure**: The set of field names present in an API response, independent of their values
- **Category_Normalizer**: Existing module (`pipeline/category_normalizer.py`) that normalizes category strings to canonical values
- **AdapterRecord**: Domain object representing a single exchange rate observation
- **No_Data_Loss_Principle**: Design rule that field existence determines record emission, not value equality

## Requirements

### Requirement 1: Detect All Rate Field Pairs in API Responses

**User Story:** As an adapter developer, I want to automatically identify all rate field pairs in an API response, so that I don't need to hard-code field name checks for each bank.

#### Acceptance Criteria

1. WHEN an API response contains rate fields, THE Field_Detector SHALL identify all buying/selling field pairs present in the structure
2. WHEN a field name matches a rate pattern (e.g., contains "buying", "selling", "bid", "ask", "offer"), THE Field_Detector SHALL recognize it as a potential rate field
3. THE Field_Detector SHALL return a list of detected field pairs with their field names
4. WHEN no valid field pairs are detected, THE Field_Detector SHALL return an empty list
5. THE Field_Detector SHALL operate on field structure only (field names), not field values
6. FOR ALL valid API responses with N distinct field pairs, THE Field_Detector SHALL identify exactly N pairs (completeness property)
7. FOR ALL detected field pairs, both buying and selling field names SHALL exist in the source structure (validity property)

### Requirement 2: Map Field Names to Canonical Categories

**User Story:** As an adapter developer, I want field names to be automatically mapped to canonical categories, so that category detection is consistent across all banks.

#### Acceptance Criteria

1. WHEN a field name contains "cash" prefix or pattern, THE Category_Mapper SHALL map it to "cash" category
2. WHEN a field name contains "tra", "trans", or "txn" prefix or pattern, THE Category_Mapper SHALL map it to "transactional" category
3. WHEN a field name contains "weighted", "average", or "avg" pattern, THE Category_Mapper SHALL map it to "weighted_average" category
4. WHEN a field name is ambiguous (e.g., plain "buying" with no context), THE Category_Mapper SHALL use adapter-specific default category
5. THE Category_Mapper SHALL use the existing Category_Normalizer module for pattern matching
6. THE Category_Mapper SHALL support context hints (adapter name, sibling fields) to resolve ambiguous field names
7. FOR ALL field names with explicit category indicators, mapping SHALL be deterministic (idempotence property)
8. FOR ALL field names F and categories C, IF normalize_category_with_context(F) = C THEN normalize_category_with_context(F) = C (consistency property)

### Requirement 3: Emit One Record Per Detected Field Pair

**User Story:** As a system user, I want all rate categories published by banks to be captured, so that I can track the complete picture of exchange rates even when values temporarily align.

#### Acceptance Criteria

1. WHEN Field_Detector identifies N field pairs, THE Record_Emitter SHALL create exactly N AdapterRecords
2. WHEN two field pairs have identical values, THE Record_Emitter SHALL still create separate records (No_Data_Loss_Principle)
3. WHEN a field pair has null or missing values for both buying and selling, THE Record_Emitter SHALL skip that pair
4. THE Record_Emitter SHALL assign category to each record based on Category_Mapper output
5. THE Record_Emitter SHALL populate all required AdapterRecord fields (currency code, rates, date, category, keys)
6. THE Record_Emitter SHALL include field structure metadata in raw_excerpt for debugging
7. FOR ALL source responses with field pairs (B1, S1) and (B2, S2), WHERE B1 ≠ B2 OR S1 ≠ S2, THE Record_Emitter SHALL create 2 records even IF values are equal (No_Data_Loss_Principle property)
8. FOR ALL emitted records R1 and R2 from the same source response, R1.source_record_key ≠ R2.source_record_key (uniqueness property)

### Requirement 4: Provide Reusable Base Components for Adapters

**User Story:** As an adapter developer, I want reusable base classes or mixins that handle field detection, so that I can implement new adapters with minimal code.

#### Acceptance Criteria

1. THE System SHALL provide a base class or mixin with detect_field_pairs() method
2. THE System SHALL provide a base class or mixin with emit_records_from_pairs() method
3. WHEN an adapter inherits from the base component, THE adapter SHALL access field detection with 1-2 lines of code
4. THE base components SHALL work with existing JSONAdapter base class
5. THE base components SHALL support adapter-specific field name mappings via configuration
6. THE base components SHALL maintain backward compatibility with existing adapters
7. THE base components SHALL follow composition-over-inheritance principle
8. FOR ALL adapters A1 and A2 using base components, implementation patterns SHALL be structurally similar (reusability property)

### Requirement 5: Handle Five Common Field Structure Patterns

**User Story:** As a system maintainer, I want the system to handle all observed field structure patterns, so that it works across 32 different bank APIs without special cases.

#### Acceptance Criteria

1. WHEN API response has explicit category field names (e.g., "cashBuying", "transactionalBuying"), THE System SHALL detect multiple categories (Pattern A: CBE)
2. WHEN API response has prefix convention (e.g., "buying" + "tra_buying"), THE System SHALL detect both field pairs (Pattern B: Wegagen)
3. WHEN API response has only one field pair (e.g., "buying", "selling"), THE System SHALL emit one record with default category (Pattern C: Rammis)
4. WHEN API response has wide-row structure with multiple rate columns, THE System SHALL detect all field pairs (Pattern D: Addis)
5. WHEN API response has dynamic field names requiring runtime discovery, THE System SHALL use introspection to detect fields (Pattern E: Dynamic)
6. THE System SHALL document which pattern each adapter uses for maintainability
7. FOR ALL five patterns P1..P5, THE System SHALL emit correct number of records per currency (correctness property)

### Requirement 6: Parse and Pretty-Print Field Structure Configurations

**User Story:** As an adapter developer, I want to configure field mappings declaratively, so that I can define adapter behavior without writing procedural code.

#### Acceptance Criteria

1. THE System SHALL support declarative field mapping configuration (e.g., JSON or Python dict)
2. WHEN a configuration defines field-to-category mappings, THE System SHALL apply those mappings during detection
3. THE System SHALL provide a configuration parser that validates field mapping syntax
4. THE System SHALL provide a pretty printer that formats field configurations for readability
5. FOR ALL valid configurations C, parsing then printing then parsing SHALL produce an equivalent configuration (round-trip property)
6. WHEN an invalid configuration is provided, THE Parser SHALL return a descriptive error message

### Requirement 7: Centralize Category String Mapping

**User Story:** As a system maintainer, I want all category string normalization centralized, so that there are no hard-coded category strings scattered across 32 adapters.

#### Acceptance Criteria

1. THE System SHALL use existing Category_Normalizer for all category string operations
2. WHEN an adapter needs to assign a category, THE adapter SHALL call Category_Normalizer instead of using string literals
3. THE System SHALL provide adapter migration guidelines to replace hard-coded strings with normalizer calls
4. WHEN a new category pattern is discovered, THE pattern SHALL be added to Category_Normalizer only (single point of change)
5. THE System SHALL flag any remaining hard-coded category strings in adapters (linting rule)
6. FOR ALL adapters A, category assignment SHALL use normalize_category() or normalize_category_with_context() (standardization property)

### Requirement 8: Maintain Backward Compatibility

**User Story:** As a system operator, I want existing adapters to continue working after field detection is introduced, so that we can deploy incrementally without breaking changes.

#### Acceptance Criteria

1. WHEN field detection components are added, THE existing adapter implementations SHALL continue to function
2. THE System SHALL support both new field-detection-based adapters and legacy hard-coded adapters simultaneously
3. WHEN an adapter is migrated to use field detection, THE database records SHALL have the same structure as before
4. THE System SHALL preserve existing adapter interfaces (parse(), get_source_url(), etc.)
5. THE System SHALL provide a migration path for each of the 32 adapters
6. FOR ALL existing adapters E, introducing field detection SHALL NOT change E's output unless E is explicitly migrated (non-regression property)

### Requirement 9: Verify Field Detection with Property-Based Tests

**User Story:** As a quality assurance engineer, I want comprehensive tests that verify field detection works correctly for arbitrary field structures, so that edge cases are caught before production.

#### Acceptance Criteria

1. THE System SHALL include property-based tests that generate random API response structures
2. FOR ALL generated responses with N field pairs, THE Field_Detector SHALL identify exactly N pairs (completeness property test)
3. FOR ALL detected field pairs, both field names SHALL exist in the source structure (validity property test)
4. FOR ALL field pairs with buying/selling values, THE Record_Emitter SHALL create a record (coverage property test)
5. FOR ALL pairs of field names (F1, F2) WHERE F1 ≠ F2, category mapping SHALL be deterministic (consistency property test)
6. THE tests SHALL include examples from all five field structure patterns
7. WHEN a property test fails, THE test framework SHALL provide a minimal failing example

### Requirement 10: Support Adapter-Specific Field Overrides

**User Story:** As an adapter developer, I want to override field detection for banks with non-standard structures, so that I can handle edge cases without modifying the core detection logic.

#### Acceptance Criteria

1. THE System SHALL support adapter-specific field name mappings that override default detection
2. WHEN an adapter defines a field override, THE Field_Detector SHALL use the override mapping
3. THE override mechanism SHALL support mapping ambiguous field names to specific categories (e.g., "buying" → "cash" for Wegagen)
4. THE System SHALL document which adapters use overrides and why
5. WHEN an override is defined, THE System SHALL validate that override fields exist in the API response
6. FOR ALL adapters with overrides O, field detection behavior SHALL match the override specification (configurability property)

### Requirement 11: Generate Unique Source Record Keys for Multiple Categories

**User Story:** As a database administrator, I want each emitted record to have a unique source_record_key, so that records from the same source item but different categories don't collide.

#### Acceptance Criteria

1. WHEN multiple records are emitted from the same source item, THE System SHALL append category suffix to source_record_key
2. THE source_record_key format SHALL be "{original_id}:{category}" for multi-category sources
3. WHEN only one record is emitted per source item, THE source_record_key SHALL be the original ID without suffix
4. THE System SHALL preserve original source IDs in raw_excerpt for traceability
5. FOR ALL records R1 and R2 from the same collection, R1.source_record_key ≠ R2.source_record_key (uniqueness property)
6. FOR ALL records R with source_record_key K, subsequent collections with the same source item SHALL generate the same K (stability property)

### Requirement 12: Document Field Structure Patterns for Each Bank

**User Story:** As a system maintainer, I want documentation showing which field structure pattern each bank uses, so that I can understand adapter behavior without reading code.

#### Acceptance Criteria

1. THE System SHALL maintain a field structure pattern registry documenting each bank's pattern
2. THE documentation SHALL include example API responses for each pattern
3. THE documentation SHALL list which adapters use each pattern
4. WHEN a new adapter is added, THE adapter SHALL declare its field structure pattern
5. THE System SHALL provide a tool to validate that adapter implementation matches its declared pattern
6. THE documentation SHALL be co-located with adapter code for maintainability

## Special Requirements Guidance

### Parser and Round-Trip Properties

This system includes configuration parsing for field mappings. The following requirements ensure correctness:

**Configuration Parser**: Parses declarative field mapping configurations (Requirement 6).

**Round-Trip Property**: FOR ALL valid configurations C, `parse(print(C))` SHALL produce an equivalent configuration. This is ESSENTIAL for configuration reliability.

**Pretty Printer**: Formats configurations for human readability while preserving semantic content.

**Example Configuration**:
```python
{
    "field_mappings": {
        "buying": "cash",
        "tra_buying": "transactional",
        "selling": "cash",
        "tra_selling": "transactional"
    },
    "default_category": "transactional"
}
```

**Round-Trip Test**:
```python
original_config = parse_field_config(config_json)
printed = print_field_config(original_config)
reparsed_config = parse_field_config(printed)
assert original_config == reparsed_config  # Round-trip property
```

## Correctness Properties Summary

The following correctness properties apply across requirements:

1. **Completeness Property** (Req 1, 9): FOR ALL API responses with N field pairs, detection SHALL identify exactly N pairs
2. **Validity Property** (Req 1, 9): FOR ALL detected pairs, both field names SHALL exist in source
3. **Idempotence Property** (Req 2, 9): FOR ALL field names F, `map_category(F) == map_category(map_category(F))`
4. **No_Data_Loss_Property** (Req 3, 9): FOR ALL structurally distinct field pairs, emit separate records regardless of value equality
5. **Uniqueness Property** (Req 3, 11): FOR ALL records from same source, source_record_keys SHALL be distinct
6. **Stability Property** (Req 11): FOR ALL records R, re-collecting the same source data SHALL produce the same source_record_key
7. **Round-Trip Property** (Req 6): FOR ALL configurations C, `parse(print(C))` SHALL equal C
8. **Non-Regression Property** (Req 8): FOR ALL existing adapters, introducing field detection SHALL NOT change output unless explicitly migrated
9. **Reusability Property** (Req 4): FOR ALL adapters using base components, implementation patterns SHALL be structurally similar
10. **Standardization Property** (Req 7): FOR ALL adapters, category assignment SHALL use Category_Normalizer

These properties SHALL be verified through property-based tests (Requirement 9) with random input generation covering edge cases.

## Integration with Existing Systems

### Use Existing Category_Normalizer Module

The system SHALL use `pipeline/category_normalizer.py` for all category string operations. This module is already implemented and provides:
- Pattern-based normalization (cash, transactional, weighted_average patterns)
- Context-aware normalization with field name hints
- Consistent handling of variations (CASH, Cash, cash_buying, etc.)

### Use Existing AdapterRecord Contract

The system SHALL emit standard `AdapterRecord` objects with all required fields:
- `source_currency_code`: Currency code (e.g., "USD")
- `category`: Canonical category code
- `buying_rate`, `selling_rate`: Normalized Decimal rates
- `effective_date`, `effective_date_basis`: Date information
- `source_record_key`, `source_publication_key`: Identity keys
- `raw_excerpt`: Field structure metadata
- `mapping_notes`: Detection logic documentation

### Work with Existing Adapter Base Classes

The system SHALL integrate with existing `adapters/base.py` classes:
- `JSONAdapter`: Base class for JSON API adapters
- `BankAdapter`: Abstract base with common interface
- `ParseResult`: Standard result container

Field detection components SHALL use composition (mixins) rather than modifying base class hierarchy.

## Success Criteria

✅ Any adapter can detect field structure with 1-2 lines of code  
✅ Field-to-category mapping centralized in Category_Normalizer  
✅ Emits correct number of records based on field structure, not value equality  
✅ No hard-coded category strings remain in adapters  
✅ Property-based tests verify correctness properties for arbitrary inputs  
✅ Backward compatible with existing 32 adapters  
✅ Works for all 5 observed field structure patterns (CBE, Wegagen, Rammis, Addis, Dynamic)  
✅ Documentation shows which pattern each bank uses  
✅ Well-tested with real bank API examples
