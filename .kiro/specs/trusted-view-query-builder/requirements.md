# Requirements: Trusted View Query Builder

**Feature Name:** trusted-view-query-builder  
**Spec Type:** Feature (New)  
**Status:** Draft  
**Created:** 2026-10-14

---

## Overview

Implement a composable query builder pattern for trusted rate queries to eliminate massive SQL duplication, enforce LOCKED rules consistently, and improve maintainability of the critical trusted view layer.

**Current Problem:**
- **150+ lines of duplicate SQL** across 12 query functions
- Same WHERE clause (`_TRUSTED_WHERE`) repeated 10+ times
- Same JOIN pattern repeated in 8 different functions
- Same SELECT columns with minor variations
- Row transformation logic (`_to_row`, `is_provisional`) scattered across functions
- Manual SQL composition with string concatenation (f-strings)
- LOCKED rules scattered across multiple functions (hard to audit)
- Difficult to add new filters or modify existing criteria

**Expected Benefits:**
- **35% code reduction** in `trusted_view/query.py` (eliminate 150+ lines)
- Single source of truth for "trusted" criteria (LOCKED rules)
- Composable query building (add filters incrementally)
- Type-safe query construction
- Easier to maintain acceptance tests 19-22
- Better enforcement of LOCKED rules
- Consistent row transformation across all queries

---

## Business Context

### User Impact
- **API consumers** - No functional changes (backward compatible)
- **Developers** - Easier to add new query patterns
- **QA team** - Clearer enforcement of LOCKED rules for acceptance testing
- **Future features** - Foundation for advanced filtering, pagination, sorting

### Technical Debt
This addresses critical maintainability debt in the most important query module:
- **High duplication:** 150+ lines of repeated SQL code
- **LOCKED rules scattered:** Trusted criteria duplicated across 12 functions
- **Manual SQL composition:** Error-prone string concatenation
- **Testing difficulty:** Hard to verify all functions enforce same rules

### Dependencies
- **None** - This is isolated to `trusted_view/query.py`
- **Enhanced by Spec 3:** Connection pooling will improve query performance
- **Complements Spec 2:** RateSourceRepository handles different concerns

---

## Functional Requirements

### FR-1: LOCKED Rules Enforcement (REQUIRED)
**Priority:** CRITICAL  
**User Story:** As a system, I need consistent enforcement of trusted rate criteria across all queries.

**LOCKED Rules (from current implementation):**
1. Exclude rejected observations: `validation_status != 'rejected'`
2. Exclude ambiguous identities: `identity_status != 'ambiguous'`
3. Use latest valid version: `is_current = TRUE`
4. Require categorization: `category_id IS NOT NULL`
5. Only enabled sources: `rs.is_enabled = TRUE`
6. Never select by `fetched_at` alone — respect version chain
7. Show `effective_date` and `fetched_at` separately
8. Provisional sources labeled (gap review L)
9. Pending review shows uncertainty warning (gap review C)

**Acceptance Criteria:**
1. Single source of truth for trusted rate criteria (no duplication)
2. All 12 existing query functions enforce same LOCKED rules
3. Builder enforces rules automatically (cannot be bypassed)
4. Acceptance tests 19-22 continue to pass
5. New queries automatically inherit LOCKED rules

**Testing:**
- Verify all builder queries exclude rejected observations
- Verify all queries enforce `is_current = TRUE`
- Verify provisional sources flagged consistently
- Run acceptance tests 19-22 (must pass)

---

### FR-2: Composable Query Building (REQUIRED)
**Priority:** HIGH  
**User Story:** As a developer, I need to build complex queries incrementally with a fluent API.

**Acceptance Criteria:**
1. Fluent API with method chaining
2. Filters composable in any order
3. Each filter method returns `self` for chaining
4. Builder validates filter combinations
5. Query built only when `execute()` called

**Example Usage:**
```python
# Simple query
rates = (TrustedRatesQueryBuilder(conn)
         .with_currency("USD")
         .execute())

# Complex query
rates = (TrustedRatesQueryBuilder(conn)
         .with_currency("USD")
         .with_source(source_id=5)
         .best_per_bank()
         .order_by_buying_rate(desc=True)
         .execute())
```

**Testing:**
- Verify method chaining works
- Verify filters applied correctly
- Verify order of chaining doesn't matter (where appropriate)

---

### FR-3: Standard Trusted Rate Fields (REQUIRED)
**Priority:** HIGH  
**User Story:** As a developer, I need consistent field selection across all queries.

**Standard Fields (from current implementation):**
- `id`, `source_id`
- `bank_name`, `bank_code`
- `source_currency_code`, `currency_code`
- `category`
- `buying_rate`, `selling_rate`
- `effective_date`, `fetched_at`
- `version_number`, `identity_status`, `validation_status`, `change_review_status`
- `source_verification_status`
- `has_pending_review` (computed)
- `staleness_warning` (computed)
- `is_provisional` (computed in row transformation)

**Acceptance Criteria:**
1. Standard SELECT includes all required fields
2. Computed fields (warnings, flags) calculated consistently
3. Field selection customizable for specific queries
4. Row transformation applies `is_provisional` logic
5. Backward compatible with existing query return types

**Testing:**
- Verify all standard fields present in results
- Verify computed fields calculated correctly
- Verify row transformation consistent

---

### FR-4: Standard JOIN Patterns (REQUIRED)
**Priority:** HIGH  
**User Story:** As a developer, I need consistent table joins across all queries.

**Standard JOINs (from current implementation):**
```sql
FROM rate_observation o
JOIN rate_source rs ON rs.id = o.source_id
JOIN bank b ON b.id = rs.bank_id
LEFT JOIN rate_category rc ON rc.id = o.category_id
```

**Acceptance Criteria:**
1. Base JOIN pattern included in all queries
2. Additional JOINs composable for specific needs
3. JOINs optimized (no unnecessary joins)
4. JOIN order consistent for query plan optimization

**Testing:**
- Verify all queries use standard JOINs
- Verify query plans efficient
- Verify no duplicate joins

---

### FR-5: Filter Methods (REQUIRED)
**Priority:** HIGH  
**User Story:** As a developer, I need common filtering methods for trusted rates.

**Required Filter Methods:**
1. `with_source(source_id: int)` - Filter by source/bank
2. `with_currency(currency_code: str)` - Filter by currency
3. `with_category(category: str)` - Filter by category
4. `major_currencies_only()` - Filter to major currencies (USD, EUR, GBP, etc.)
5. `with_date(effective_date: date)` - Filter by effective date
6. `with_date_range(start: date, end: date)` - Filter by date range

**Acceptance Criteria:**
1. Each filter method adds WHERE clause
2. Multiple filters combined with AND
3. Parameters validated (type checking)
4. SQL injection prevented (parameterized queries)
5. Filters idempotent (calling twice doesn't break query)

**Testing:**
- Test each filter method individually
- Test filter combinations
- Test parameter validation
- Test SQL injection prevention

---

### FR-6: Aggregation and Grouping (REQUIRED)
**Priority:** MEDIUM  
**User Story:** As a developer, I need aggregation patterns for summary queries.

**Required Aggregation Methods:**
1. `best_per_bank()` - DISTINCT ON (rs.id) with best buying rate
2. `best_per_currency()` - DISTINCT ON (currency) with best buying rate
3. `group_by_date()` - Group results by effective_date
4. `group_by_bank()` - Group results by bank

**Acceptance Criteria:**
1. Aggregations use DISTINCT ON or GROUP BY appropriately
2. Best rate selection uses correct ORDER BY
3. Aggregations compatible with filters
4. Results correctly ordered after aggregation

**Testing:**
- Verify best rate selection accurate
- Verify grouping produces correct results
- Compare with current implementation output

---

### FR-7: Ordering Methods (REQUIRED)
**Priority:** MEDIUM  
**User Story:** As a developer, I need flexible ordering of query results.

**Required Ordering Methods:**
1. `order_by_buying_rate(desc=True)` - Order by buying rate
2. `order_by_bank_name()` - Order by bank name
3. `order_by_currency()` - Order by currency code
4. `order_by_date(desc=True)` - Order by effective date

**Acceptance Criteria:**
1. Multiple orderings composable
2. Order specified affects DISTINCT ON correctly
3. NULL handling (NULLS LAST) applied automatically
4. Default ordering maintained if none specified

**Testing:**
- Verify ordering produces correct results
- Verify NULLS LAST applied
- Verify multiple order criteria work together

---

### FR-8: Row Transformation (REQUIRED)
**Priority:** HIGH  
**User Story:** As a developer, I need consistent row transformation across all queries.

**Row Transformation Logic:**
1. Convert cursor rows to dict with column names as keys
2. Add computed `is_provisional` field based on verification status
3. Handle NULL values appropriately
4. Preserve data types (Decimal, date, datetime)

**Acceptance Criteria:**
1. Single `_to_row()` method used by all queries
2. Computed fields added consistently
3. Type preservation (no unintended conversions)
4. Backward compatible with current row format

**Testing:**
- Verify row format matches current implementation
- Verify computed fields calculated correctly
- Verify type preservation

---

### FR-9: Backward Compatibility (REQUIRED)
**Priority:** CRITICAL  
**User Story:** As a developer, I need existing query functions to continue working unchanged.

**Acceptance Criteria:**
1. All 12 existing query functions remain unchanged (facades)
2. Existing functions delegate to QueryBuilder internally
3. Return types identical to current implementation
4. All 429 existing tests pass without modification
5. API module (`api/app.py`) works without changes

**Existing Functions (must remain):**
- `get_trusted_rates(conn, source_id=None)`
- `get_trusted_rates_by_currency(conn, currency_code)`
- `get_best_rates_by_currency(conn, currency_code)`
- `get_bank_rates_pivoted(conn, source_id)`
- `get_currency_matrix(conn, major_only=False)`
- `get_available_dates(conn)`
- `get_history_by_currency(conn, currency_code, effective_date=None)`
- `get_search_suggestions(conn)`
- `get_available_currencies(conn)`
- `get_available_banks(conn)`
- `get_pending_review_observations(conn)`
- `get_observation_with_warnings(conn, logical_key)`

**Testing:**
- Run all 429 existing tests (must pass)
- Verify API endpoints work correctly
- Compare output with current implementation

---

### FR-10: Testing Support (REQUIRED)
**Priority:** MEDIUM  
**User Story:** As a test writer, I need easy testing of query builder logic.

**Acceptance Criteria:**
1. Builder can return SQL string without executing (for inspection)
2. Builder can return parameters array for verification
3. Mock-friendly design (no hard dependencies)
4. Clear error messages for invalid query construction

**Testing:**
- Unit tests for builder methods
- Query inspection tests
- Parameter validation tests

---

## Non-Functional Requirements

### NFR-1: Code Reduction
**Requirement:** Reduce code duplication by 35% (eliminate 150+ lines).

**Metrics:**
- Current: ~450 lines in `trusted_view/query.py`
- Target: ~300 lines (150 line reduction)
- Measure: Line count after refactoring

**Testing:**
```bash
# Before
wc -l trusted_view/query.py
# 450 lines

# After
wc -l trusted_view/query.py
# ~300 lines
```

---

### NFR-2: Maintainability
**Requirement:** Single source of truth for trusted rate criteria.

**Metrics:**
- LOCKED rules defined in one place (not 10+)
- TRUSTED_WHERE clause appears once (not 10+ times)
- JOIN pattern defined once (not 8+ times)

**Testing:**
```bash
# Verify no duplication
grep -c "_TRUSTED_WHERE" trusted_view/query.py
# Should be 1 (in QueryBuilder only)
```

---

### NFR-3: Performance
**Requirement:** No performance regression; similar or better query performance.

**Metrics:**
- Query execution time unchanged or improved
- Query plans remain efficient (verify with EXPLAIN)
- No N+1 query problems introduced

**Testing:**
- Benchmark current implementation
- Benchmark with QueryBuilder
- Compare query plans with EXPLAIN ANALYZE

---

### NFR-4: Type Safety
**Requirement:** Builder methods provide type hints and validation.

**Metrics:**
- All builder methods type-hinted
- Parameter validation on invalid inputs
- IDE autocomplete works correctly

**Testing:**
- MyPy type checking passes
- Invalid parameters raise appropriate errors

---

### NFR-5: Testability
**Requirement:** Builder logic easily testable in isolation.

**Metrics:**
- Unit tests for each builder method
- Query inspection possible without database
- Mock-friendly design

**Testing:**
- Achieve 90%+ code coverage on builder
- Unit tests run without database connection

---

## Success Criteria

### Minimum Viable Product (MVP)
To consider this feature complete, we must have:

1. ✅ **TrustedRatesQueryBuilder class** with core methods
2. ✅ **All 429 tests passing** with no modifications
3. ✅ **Code reduction** of 150+ lines measured
4. ✅ **LOCKED rules** enforced in single location
5. ✅ **Backward compatibility** - all existing functions work
6. ✅ **Documentation** with builder usage examples

### Full Success
For complete success, additionally:

7. ✅ **Query inspection** methods for testing
8. ✅ **Type hints** on all builder methods
9. ✅ **Unit tests** with 90%+ coverage
10. ✅ **Performance validation** - no regression

---

## Out of Scope

The following are explicitly **NOT** part of this spec:

1. **Pagination support** - Future enhancement
2. **Cursor-based iteration** - Future enhancement
3. **Query caching** - Separate concern
4. **Database write operations** - Query builder is read-only
5. **ORM adoption** (SQLAlchemy, etc.) - Not appropriate for this codebase
6. **Query optimization** beyond current state - Maintain existing performance
7. **Dynamic field selection** - All queries return standard fields
8. **Subquery support** - Current queries don't need it
9. **Raw SQL passthrough** - Builder enforces structure
10. **Migration to different query patterns** - Maintain current API

---

## User Stories Summary

### Epic: Trusted View Query Simplification

**As a developer**, I want a composable query builder so that I can construct trusted rate queries without duplicating SQL.

**As a QA engineer**, I want LOCKED rules enforced consistently so that acceptance tests verify correct behavior everywhere.

**As a maintainer**, I want a single source of truth for trusted criteria so that I can audit and modify rules easily.

**As a code reviewer**, I want reduced duplication so that I can focus on business logic instead of SQL patterns.

---

## Constraints and Assumptions

### Constraints
1. **Must maintain backward compatibility** - All 429 tests pass unchanged
2. **Must enforce LOCKED rules** - No queries bypass trusted criteria
3. **Must support existing query patterns** - All 12 current functions supported
4. **No schema changes** - Pure code refactoring
5. **No new dependencies** - Use standard library and psycopg2 only

### Assumptions
1. PostgreSQL-specific SQL is acceptable (DISTINCT ON, etc.)
2. Current query patterns are correct and should be preserved
3. Performance is acceptable and should not regress
4. All queries return lists of dicts (current pattern)
5. Connection management handled separately (Spec 3)

### Risks
1. **Risk:** Breaking existing queries during refactoring
   - **Mitigation:** Test after each function migration; keep facades
   
2. **Risk:** Performance regression from query builder overhead
   - **Mitigation:** Benchmark before/after; optimize builder
   
3. **Risk:** Incomplete LOCKED rule enforcement
   - **Mitigation:** Comprehensive unit tests; acceptance test verification
   
4. **Risk:** Complex queries difficult to express with builder
   - **Mitigation:** Support escape hatches for edge cases

---

## Related Work

### Depends On
- **Spec 3 (Database Infrastructure)** - Optional but recommended (connection pooling)

### Enables
- Future: Advanced filtering (pagination, full-text search)
- Future: Query performance monitoring
- Future: Dynamic report generation

### Related Specs
- **Spec 2:** RateSourceRepository handles different query concerns
- **Spec 3:** DatabaseManager provides connections to QueryBuilder

---

## Appendix A: Current Duplication Analysis

### SQL Duplication Count

**_TRUSTED_WHERE clause** (appears 10+ times):
```sql
o.is_current = TRUE
AND o.identity_status != 'ambiguous'
AND o.validation_status != 'rejected'
AND o.category_id IS NOT NULL
AND rs.is_enabled = TRUE
```

**Functions using _TRUSTED_WHERE:**
1. `get_trusted_rates()` - Uses f-string interpolation
2. `get_trusted_rates_by_currency()` - Uses f-string interpolation
3. `get_currency_matrix()` - Uses f-string interpolation
4. `get_available_currencies()` - Uses f-string interpolation
5. `get_available_banks()` - Uses f-string interpolation
6. `get_best_rates_by_currency()` - Inline duplication (doesn't use constant!)
7. `get_available_dates()` - Inline partial duplication
8. `get_history_by_currency()` - Inline partial duplication

**JOIN pattern** (repeated 8+ times):
```sql
FROM rate_observation o
JOIN rate_source rs ON rs.id = o.source_id
JOIN bank b ON b.id = rs.bank_id
LEFT JOIN rate_category rc ON rc.id = o.category_id
```

**is_provisional logic** (repeated 6+ times):
```python
d["is_provisional"] = d["source_verification_status"] in ("unverified", "provisional")
```

**Total Duplication:**
- SQL WHERE clause: ~15 lines × 8 occurrences = 120 lines
- JOIN pattern: ~4 lines × 8 occurrences = 32 lines
- Row transformation: ~2 lines × 6 occurrences = 12 lines
- **Total: ~164 lines of duplication**

---

## Appendix B: Current vs. Desired State

### Current State (Anti-pattern)

```python
# Problem 1: Duplicated WHERE clause
_TRUSTED_WHERE = """
    o.is_current = TRUE
    AND o.identity_status != 'ambiguous'
    AND o.validation_status != 'rejected'
    AND o.category_id IS NOT NULL
    AND rs.is_enabled = TRUE
"""

# Problem 2: Duplicated SELECT
_TRUSTED_SELECT = """
    SELECT o.id, o.source_id, b.name AS bank_name, ...
    FROM rate_observation o
    JOIN rate_source rs ON rs.id = o.source_id
    JOIN bank b ON b.id = rs.bank_id
    LEFT JOIN rate_category rc ON rc.id = o.category_id
"""

# Problem 3: Manual SQL composition
def get_trusted_rates_by_currency(conn, currency_code: str) -> list:
    query = f"""
        {_TRUSTED_SELECT}
        WHERE {_TRUSTED_WHERE}
          AND o.source_currency_code = %s
        ORDER BY o.buying_rate DESC NULLS LAST
    """
    with conn.cursor() as cur:
        cur.execute(query, (currency_code,))
        cols = [d[0] for d in cur.description]
        return [_to_row(cols, row) for row in cur.fetchall()]

# Problem 4: Same pattern repeated 12 times!
```

### Desired State (Clean pattern)

```python
# Solution: Composable QueryBuilder

class TrustedRatesQueryBuilder:
    """
    Composable query builder for trusted exchange rates.
    Enforces LOCKED rules automatically.
    """
    
    def __init__(self, conn):
        self.conn = conn
        self._filters = []
        self._params = []
        self._order_by = []
    
    def with_currency(self, currency_code: str):
        """Filter by currency code."""
        self._filters.append("o.source_currency_code = %s")
        self._params.append(currency_code)
        return self
    
    def order_by_buying_rate(self, desc=True):
        """Order by buying rate."""
        direction = "DESC" if desc else "ASC"
        self._order_by.append(f"o.buying_rate {direction} NULLS LAST")
        return self
    
    def execute(self) -> list:
        """Build and execute query."""
        query = self._build_query()
        with self.conn.cursor() as cur:
            cur.execute(query, self._params)
            return self._to_rows(cur)
    
    def _build_query(self) -> str:
        """Compose final SQL query."""
        # SELECT + standard JOINs + LOCKED WHERE + filters + ORDER BY
        pass
    
    def _to_rows(self, cursor) -> list:
        """Transform rows to dicts with computed fields."""
        pass

# Usage - clean and composable!
def get_trusted_rates_by_currency(conn, currency_code: str) -> list:
    """Return all banks' trusted rates for a currency."""
    return (TrustedRatesQueryBuilder(conn)
            .with_currency(currency_code)
            .order_by_buying_rate(desc=True)
            .execute())
```

**Benefits:**
- ✅ Single definition of LOCKED rules (in builder)
- ✅ Composable filters (add incrementally)
- ✅ Type-safe method calls
- ✅ No SQL string concatenation
- ✅ Consistent row transformation
- ✅ Easy to test (inspect query without executing)
- ✅ Easy to extend (add new filter methods)

---

## Appendix C: LOCKED Rules Reference

From the module docstring, these rules must be enforced consistently:

### LOCKED Rules
1. **Exclude rejected observations** - `validation_status != 'rejected'`
2. **Exclude ambiguous identities** - `identity_status != 'ambiguous'`
3. **Use latest valid version** - `is_current = TRUE`
4. **Never select by fetched_at alone** - Respect version chain and effective_date
5. **Show effective_date and fetched_at separately** - Both fields in SELECT
6. **Require categorization** - `category_id IS NOT NULL`
7. **Only enabled sources** - `rs.is_enabled = TRUE`
8. **Provisional sources labeled** - Gap review L (compute `is_provisional`)
9. **Pending review warning** - Gap review C (compute `has_pending_review`)
10. **Never substitute older rates** - No fallback to non-current rows

### Acceptance Tests
- **AT-19:** Trusted view excludes rejected observations
- **AT-20:** Trusted view excludes ambiguous identities
- **AT-21:** Trusted view returns only current versions
- **AT-22:** Trusted view excludes uncategorized rates

---

## Acceptance Tests

### AT-1: LOCKED Rules Enforced
```python
def test_locked_rules_enforced():
    """Verify builder enforces all LOCKED rules."""
    builder = TrustedRatesQueryBuilder(conn)
    query = builder._build_query()
    
    # Verify required WHERE clauses
    assert "o.is_current = TRUE" in query
    assert "o.identity_status != 'ambiguous'" in query
    assert "o.validation_status != 'rejected'" in query
    assert "o.category_id IS NOT NULL" in query
    assert "rs.is_enabled = TRUE" in query
```

### AT-2: Filter Composition
```python
def test_filter_composition():
    """Verify filters compose correctly."""
    results = (TrustedRatesQueryBuilder(conn)
               .with_currency("USD")
               .with_source(5)
               .execute())
    
    # Verify all results match filters
    assert all(r["source_currency_code"] == "USD" for r in results)
    assert all(r["source_id"] == 5 for r in results)
```

### AT-3: Backward Compatibility
```python
def test_backward_compatibility():
    """Verify existing functions produce same results."""
    # Old way
    old_results = get_trusted_rates_by_currency(conn, "USD")
    
    # New way (internally using builder)
    new_results = get_trusted_rates_by_currency(conn, "USD")
    
    # Should be identical
    assert old_results == new_results
```

### AT-4: Row Transformation Consistency
```python
def test_row_transformation():
    """Verify row transformation consistent."""
    results = (TrustedRatesQueryBuilder(conn)
               .with_currency("USD")
               .execute())
    
    # Verify computed fields present
    for row in results:
        assert "is_provisional" in row
        assert isinstance(row["is_provisional"], bool)
        assert "staleness_warning" in row
```

### AT-5: Existing Acceptance Tests
```python
def test_acceptance_tests_pass():
    """Verify AT-19 through AT-22 still pass."""
    # These tests already exist in the test suite
    # They must continue to pass after refactoring
    pass
```

---

## Definitions

- **LOCKED Rules:** Immutable business rules for trusted rate queries (from gap review)
- **Query Builder:** Composable object for constructing SQL queries programmatically
- **Fluent API:** Method chaining pattern where methods return `self`
- **DISTINCT ON:** PostgreSQL-specific SQL for selecting one row per group
- **Gap Review:** Documented data integrity concerns (labeled A-L in gap-review.md)
- **Provisional Source:** Unverified or provisional verification status
- **Trusted Rate:** Current, validated rate that passes all LOCKED rule checks

---

**Requirements Status:** Draft - Ready for Review  
**Next Step:** Design phase (QueryBuilder class design, method specifications)  
**Estimated Effort:** 2-3 days implementation + testing
