# Implementation Plan: Field-Structure-Based Category Detection

## Overview

This implementation plan converts the field-structure-based category detection design into discrete coding tasks. The solution provides reusable components for automatically detecting exchange rate categories from JSON field structures, following the No-Data-Loss Principle: when a bank API publishes structurally distinct field pairs, the system emits one record per field pair.

**Core Components**:
- **FieldDetector**: Identifies buying/selling field pairs in JSON structures
- **CategoryMapper**: Maps field names to canonical categories using existing `category_normalizer.py`
- **RecordEmitter**: Creates AdapterRecord objects from field pairs
- **FieldStructureMixin**: Composition mixin for adapters requiring minimal integration code

**Implementation Language**: Python (matching existing codebase)

**Integration Approach**: Composition over inheritance using mixins that work with existing `JSONAdapter` base class.

---

## Tasks

### Phase 1: Core Component Implementation

- [x] 1. Implement FieldDetector component
  - Create `field_detection/detector.py` module in appropriate location
  - Implement `FieldDetector` class with regex-based pattern matching
  - Implement `detect_field_pairs()` method that identifies buying/selling field pairs
  - Implement `FieldPair` dataclass to represent detected pairs
  - Support explicit category prefixes (cash_, tra_, trans_, weighted_)
  - Support camelCase patterns (cashBuying, transactionalBuying)
  - Support generic patterns (buying/selling as fallback)
  - Return pairs in confidence order (explicit categories first, generic last)
  - Skip incomplete pairs (only buying or only selling present)
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

- [ ]* 1.1 Write unit tests for FieldDetector
  - Test explicit category field names (CBE pattern: cashBuying/transactionalBuying)
  - Test prefix conventions (Wegagen pattern: buying/tra_buying)
  - Test single pairs (Rammis pattern: buying/selling only)
  - Test wide-row structures (Addis pattern: cashBuying/transBuying)
  - Test incomplete pairs (only buying, only selling → skip)
  - Test empty data (return empty list)
  - Test confidence ordering (explicit > generic)
  - _Requirements: 1.6, 1.7, 5.1, 5.2, 5.3, 5.4_

- [ ]* 1.2 Write property test for FieldDetector completeness
  - **Property 1: Completeness**
  - **Validates: Requirements 1.6, 9.2**
  - Generate random API responses with N field pairs
  - Verify detector identifies exactly N pairs
  - Use hypothesis library for property-based testing
  - _Requirements: 1.6, 9.2_

- [ ]* 1.3 Write property test for FieldDetector validity
  - **Property 2: Validity**
  - **Validates: Requirements 1.7, 9.3**
  - For all detected pairs, verify both field names exist in source
  - Ensure no hallucinated fields
  - _Requirements: 1.7, 9.3_

- [ ]* 1.4 Write property test for structure independence
  - **Property 3: Structure Independence**
  - **Validates: Requirements 1.5, 9.2**
  - Verify detection based on field names, not values
  - Change values, verify same pairs detected
  - _Requirements: 1.5, 9.2_

- [x] 2. Implement CategoryMapper component
  - Create `field_detection/mapper.py` module
  - Implement `CategoryMapper` class that delegates to existing `category_normalizer.py`
  - Implement `map_field_to_category()` method using `normalize_category_with_context()`
  - Implement `map_field_pair()` method (uses buying field as representative)
  - Support explicit field mappings configuration (highest priority)
  - Support default category fallback for ambiguous fields
  - Support adapter context hints for disambiguation
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 7.1, 7.2_

- [ ]* 2.1 Write unit tests for CategoryMapper
  - Test explicit category field names (cashBuying → cash)
  - Test prefix patterns (tra_buying → transactional)
  - Test ambiguous fields with default category
  - Test explicit field mappings override defaults
  - Test context-aware normalization
  - Test all four canonical categories (cash, transactional, weighted_average, indicative_reference)
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.7, 2.8_

- [ ]* 2.2 Write property test for CategoryMapper idempotence
  - **Property 4: Idempotence**
  - **Validates: Requirements 2.7, 9.5**
  - For all field names F, verify map(F) is idempotent
  - _Requirements: 2.7, 9.5_

- [ ]* 2.3 Write property test for CategoryMapper determinism
  - **Property 5: Determinism**
  - **Validates: Requirements 2.8, 9.5**
  - For all field names F, verify map(F) called twice returns same result
  - _Requirements: 2.8, 9.5_

- [x] 3. Implement RecordEmitter component
  - Create `field_detection/emitter.py` module
  - Implement `RecordEmitter` class with `emit_records_from_fields()` method
  - Create one AdapterRecord per field pair
  - Extract buying/selling rates from data using field names
  - Generate unique source_record_key with category suffix when multiple pairs from same source
  - Skip pairs where both buying and selling are None
  - Include field structure metadata in raw_excerpt for debugging
  - Add detection metadata to mapping_notes for traceability
  - Use existing `normalize_rate()` for rate conversion
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 11.1, 11.2, 11.3, 11.4_

- [ ]* 3.1 Write unit tests for RecordEmitter
  - Test multiple categories from same source item (verify N records created)
  - Test source_record_key uniqueness with category suffix (format: "id:category")
  - Test single category (no category suffix in key)
  - Test skip pairs with no rates (both None)
  - Test metadata in raw_excerpt and mapping_notes
  - Test rate normalization using normalize_rate()
  - _Requirements: 3.1, 3.2, 3.3, 3.7, 3.8, 11.1, 11.2, 11.3_

- [ ]* 3.2 Write property test for No-Data-Loss Principle
  - **Property 6: No-Data-Loss**
  - **Validates: Requirements 3.2, 3.7, 9.4**
  - Generate pairs with different field names but identical values
  - Verify 2+ records emitted (distinct field structure → multiple records)
  - Core principle verification
  - _Requirements: 3.2, 3.7, 9.4_

- [ ]* 3.3 Write property test for source_record_key uniqueness
  - **Property 7: Key Uniqueness**
  - **Validates: Requirements 3.8, 11.5, 9.4**
  - For all records from same source, verify keys are distinct
  - No collisions allowed
  - _Requirements: 3.8, 11.5, 9.4_

- [ ]* 3.4 Write property test for source_record_key stability
  - **Property 8: Key Stability**
  - **Validates: Requirements 11.6, 9.4**
  - Parse same data twice, verify same keys generated
  - Ensures consistent identity across collections
  - _Requirements: 11.6, 9.4_

- [x] 4. Checkpoint - Core components complete
  - Ensure all core component tests pass
  - Verify FieldDetector, CategoryMapper, RecordEmitter work independently
  - Review code for adherence to design patterns
  - Ask the user if questions arise

### Phase 2: Configuration and Integration Layer

- [x] 5. Implement configuration parser and validator
  - Create `field_detection/config.py` module
  - Implement `parse_field_config()` function that validates configuration dictionaries
  - Validate field_mappings (dict of field_name → category)
  - Validate default_category is a valid canonical category or UNKNOWN
  - Validate all mapped categories are canonical using `validate_category()`
  - Raise ValueError with descriptive messages for invalid configurations
  - Implement `print_field_config()` function for pretty-printing configurations
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.6_

- [ ]* 5.1 Write unit tests for configuration parser
  - Test valid configuration parsing
  - Test invalid category rejection (descriptive error messages)
  - Test field_mappings validation
  - Test default_category validation
  - Test pretty-printer formatting
  - _Requirements: 6.2, 6.3, 6.4, 6.6_

- [ ]* 5.2 Write property test for configuration round-trip
  - **Property 9: Round-Trip**
  - **Validates: Requirements 6.5, 9.7**
  - For all valid configs C, verify parse(print(C)) == C
  - Essential for configuration reliability
  - _Requirements: 6.5, 9.7_

- [x] 6. Implement FieldStructureMixin for adapter composition
  - Create `field_detection/mixin.py` module (or integrate into `adapters/base.py`)
  - Implement `FieldStructureMixin` class providing field detection functionality
  - Implement lazy-initialized properties: `field_detector`, `category_mapper`, `record_emitter`
  - Implement `detect_and_emit()` method as one-line entry point for adapters
  - Support FIELD_CONFIG class attribute for declarative configuration
  - Use composition pattern (mixin) to avoid modifying base class hierarchy
  - Integrate with existing `JSONAdapter` base class
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.6, 4.7, 4.8, 10.1, 10.2_

- [ ]* 6.1 Write unit tests for FieldStructureMixin
  - Test lazy initialization of components
  - Test FIELD_CONFIG parsing
  - Test one-line detect_and_emit() usage
  - Test composition with JSONAdapter (multiple inheritance)
  - Test configuration-driven behavior
  - _Requirements: 4.1, 4.2, 4.3, 4.7, 4.8_

- [x] 7. Checkpoint - Configuration and mixin complete
  - Ensure all configuration and mixin tests pass
  - Verify mixin works with existing JSONAdapter base class
  - Verify configuration parsing and round-trip property
  - Ask the user if questions arise

### Phase 3: Adapter Migration and Integration

- [x] 8. Migrate CBE adapter to use FieldStructureMixin (Pattern A)
  - Modify `adapters/cbe/adapter.py` to inherit from FieldStructureMixin
  - Define empty FIELD_CONFIG (field names are self-describing)
  - Replace `_parse_er_item()` hard-coded category loop with `detect_and_emit()` call
  - Remove hard-coded `_CATEGORY_FIELDS` dictionary
  - Preserve all AdapterRecord field values (currency, dates, keys, metadata)
  - Maintain backward compatibility (module-level `parse()` function)
  - Update schema_fingerprint if needed
  - _Requirements: 5.1, 7.2, 7.3, 7.4, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [ ]* 8.1 Write integration test for CBE adapter field detection
  - Use real fixture data (fixtures/cbe/2026-10-21.json or similar)
  - Verify 2 records per currency (cash + transactional)
  - Verify categories detected correctly from field names
  - Verify source_record_key uniqueness (contains category suffix)
  - Verify all required AdapterRecord fields populated
  - _Requirements: 5.1, 8.3, 9.6_

- [x] 9. Migrate Wegagen adapter to use FieldStructureMixin (Pattern B)
  - Modify `adapters/wegagen/adapter.py` to inherit from FieldStructureMixin
  - Define FIELD_CONFIG with explicit field_mappings:
    - "buying" → "cash"
    - "tra_buying" → "transactional"
    - "selling" → "cash"
    - "tra_selling" → "transactional"
  - Set default_category to "transactional"
  - Replace `_parse_item()` single-record creation with `detect_and_emit()` call
  - Preserve all AdapterRecord field values (unit_multiplier, dates, metadata)
  - Maintain backward compatibility (module-level `parse()` function)
  - _Requirements: 5.2, 7.2, 7.3, 7.4, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 10.3_

- [ ]* 9.1 Write integration test for Wegagen adapter field detection
  - Use real fixture data (fixtures/wegagen/ or create test data)
  - Verify 2 records per currency (cash + transactional) emitted
  - Verify category mapping from field_mappings configuration
  - Verify source_record_key uniqueness with category suffix
  - Compare output before/after migration (should emit more records)
  - _Requirements: 5.2, 8.3, 9.6_

- [x] 10. Migrate Rammis adapter to use FieldStructureMixin (Pattern C)
  - Modify `adapters/rammis/adapter.py` to inherit from FieldStructureMixin
  - Define FIELD_CONFIG with default_category set to "transactional"
  - Replace `_parse_row()` category parameter with `detect_and_emit()` call
  - Remove hard-coded category="UNKNOWN" (now uses default from config)
  - Preserve all AdapterRecord field values (dates, keys, metadata)
  - Maintain backward compatibility (module-level `parse()` function signature)
  - _Requirements: 5.3, 7.2, 7.3, 7.4, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [ ]* 10.1 Write integration test for Rammis adapter field detection
  - Use real fixture data (fixtures/rammis/ or create test data)
  - Verify 1 record per currency (single pair pattern)
  - Verify category is "transactional" (not UNKNOWN)
  - Verify records now visible in trusted view (category != UNKNOWN)
  - Verify no category suffix in source_record_key (single pair)
  - _Requirements: 5.3, 8.3, 9.6_

- [x] 11. Migrate Addis Fortune adapter to use FieldStructureMixin (Pattern D)
  - Modify `adapters/addis_fortune/adapter.py` to use FieldStructureMixin
  - Define empty FIELD_CONFIG (field names are explicit: cashBuying/transBuying)
  - Replace duplicate record creation code with single `detect_and_emit()` call
  - Remove hard-coded category strings and field pair references
  - Preserve staleness check logic and applicable_date handling
  - Maintain all AdapterRecord field values (currency_name, dates, metadata)
  - _Requirements: 5.4, 7.2, 7.3, 7.4, 8.1, 8.2, 8.3, 8.4_

- [ ]* 11.1 Write integration test for Addis Fortune adapter field detection
  - Use real fixture or test data
  - Verify correct number of records per currency (based on field structure)
  - Verify categories detected from field names (cashBuying → cash, transBuying → transactional)
  - Verify staleness check still works
  - Verify metadata preserved in raw_excerpt
  - _Requirements: 5.4, 8.3, 9.6_

- [x] 12. Checkpoint - Adapter migrations complete
  - Ensure all 4 adapted patterns pass integration tests
  - Verify backward compatibility with existing tests
  - Verify no regression in existing adapter behavior
  - Confirm source_record_key uniqueness across all adapted adapters
  - Ask the user if questions arise

### Phase 4: Documentation and Validation

- [ ] 13. Create field structure pattern registry documentation
  - Create `docs/field_detection/patterns.md` documentation file
  - Document all 5 field structure patterns (A-E) with examples
  - List which adapters use each pattern
  - Include example API responses for each pattern
  - Document configuration requirements for each pattern
  - Provide migration guide for remaining adapters
  - _Requirements: 5.5, 5.6, 5.7, 12.1, 12.2, 12.3, 12.4, 12.5_

- [ ] 14. Create adapter migration guide
  - Create `docs/field_detection/migration_guide.md` documentation
  - Document step-by-step migration process for each pattern
  - Include before/after code examples
  - Document common pitfalls and solutions
  - Provide configuration templates for each pattern
  - List remaining adapters to migrate (28 remaining banks)
  - _Requirements: 7.3, 8.5, 12.6_

- [ ] 15. Update ADR-010 or create new ADR for field detection
  - Document architectural decision to use composition over inheritance
  - Document No-Data-Loss Principle and field structure philosophy
  - Document configuration-driven approach
  - Link to pattern registry and migration guide
  - Explain integration with existing category_normalizer.py
  - _Requirements: 4.7, 7.1, 7.4, 12.5_

- [ ]* 16. Verify backward compatibility with existing adapter tests
  - Run full test suite for all 32 adapters
  - Verify unmigrated adapters still work (no regression)
  - Verify migrated adapters produce correct output
  - Verify database records have same structure before/after migration
  - Test mixed environment (some migrated, some not)
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.6_

- [ ] 17. Create linting rule for hard-coded category strings
  - Add linting check to flag hard-coded category strings in adapters
  - Exempt category_normalizer.py and test files
  - Document linting rule in development guidelines
  - Run linter on all adapter files and report violations
  - _Requirements: 7.5, 7.6_

- [ ] 18. Final checkpoint - Feature complete
  - All core components implemented and tested
  - All property-based tests passing
  - 4 adapters successfully migrated (CBE, Wegagen, Rammis, Addis Fortune)
  - Documentation complete (patterns, migration guide, ADR)
  - Backward compatibility verified
  - Linting rule in place
  - Ask the user if questions arise

---

## Notes

- **Tasks marked with `*` are optional** and can be skipped for faster MVP
- **Property-based tests** use the hypothesis library to verify correctness properties across random inputs
- **Integration tests** use real fixture data to verify end-to-end behavior
- **Migration tasks** preserve backward compatibility by maintaining module-level functions
- **Configuration approach** uses class-level FIELD_CONFIG attribute for declarative setup
- **Composition pattern** allows mixing FieldStructureMixin with existing JSONAdapter without modifying base classes
- **28 adapters remaining** after initial 4 migrations - migration guide enables incremental rollout
- **No-Data-Loss Principle**: Field existence determines record emission, not value equality
- All tasks reference specific requirements for traceability
- Checkpoints ensure incremental validation throughout implementation

## Task Execution Order

1. **Phase 1** (Tasks 1-4): Implement and test core components in isolation
2. **Phase 2** (Tasks 5-7): Add configuration layer and mixin for adapter integration
3. **Phase 3** (Tasks 8-12): Migrate 4 representative adapters covering all patterns
4. **Phase 4** (Tasks 13-18): Complete documentation, validation, and tooling

Each phase builds on the previous phase. Complete all tasks in a phase before moving to the next phase.
