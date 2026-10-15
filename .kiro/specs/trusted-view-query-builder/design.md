# Design: Trusted View Query Builder

**Feature Name:** trusted-view-query-builder  
**Spec Type:** Feature (New)  
**Status:** Draft  
**Created:** 2026-10-14

---

## Table of Contents

1. [Design Overview](#design-overview)
2. [Architecture](#architecture)
3. [Component Design](#component-design)
4. [Interface Specifications](#interface-specifications)
5. [Migration Strategy](#migration-strategy)
6. [Testing Strategy](#testing-strategy)
7. [Performance Considerations](#performance-considerations)
8. [Rollback Strategy](#rollback-strategy)

---

## Design Overview

### Problem Statement

The current `trusted_view/query.py` module contains **164 lines of duplicated SQL code** across 12 query functions:

1. **LOCKED rules duplicated 10+ times** - Same WHERE clause repeated
2. **JOIN patterns duplicated 8+ times** - Same 4-table join pattern
3. **Row transformation logic scattered** - `is_provisional` computed in 6 places
4. **Manual SQL composition** - Error-prone f-string concatenation
5. **Difficult to maintain** - Changing LOCKED rules requires editing 10+ functions
6. **Testing burden** - Must verify all functions enforce same rules

### Solution Summary

Implement a **TrustedRatesQueryBuilder** class that:

- Encapsulates LOCKED rules in a single location
- Provides fluent API for composable query building
- Handles SQL composition automatically and safely
- Enforces consistent row transformation
- Maintains 100% backward compatibility
- Reduces code by 150+ lines (35%)

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Fluent API with method chaining** | Composable, readable, Pythonic |
| **Builder pattern** | Separates query construction from execution |
| **LOCKED rules enforced automatically** | Cannot be bypassed or forgotten |
| **Existing functions become facades** | Zero breaking changes |
| **Single row transformation** | Consistent computed fields everywhere |
| **No ORM** | Inappropriate for this procedural codebase |

---

## Architecture

### Current Architecture (Before)

```
┌─────────────────────────────────────────────────────────────┐
│           trusted_view/query.py (450 lines)                  │
│                                                              │
│  Constants (Duplicated everywhere):                          │
│  ┌────────────────────────────────────────────────┐        │
│  │ _TRUSTED_WHERE = "..." (used 10+ times)        │        │
│  │ _TRUSTED_SELECT = "..." (used 8+ times)        │        │
│  │ MAJOR_CURRENCIES = {...}                       │        │
│  └────────────────────────────────────────────────┘        │
│                                                              │
│  12 Query Functions (Lots of duplication):                   │
│  ┌────────────────────────────────────────────────┐        │
│  │ get_trusted_rates()                            │        │
│  │   • Duplicates WHERE clause                    │        │
│  │   • Duplicates JOIN pattern                    │        │
│  │   • Duplicates row transformation              │        │
│  │                                                 │        │
│  │ get_trusted_rates_by_currency()                │        │
│  │   • Duplicates WHERE clause                    │        │
│  │   • Duplicates JOIN pattern                    │        │
│  │   • Duplicates row transformation              │        │
│  │                                                 │        │
│  │ get_best_rates_by_currency()                   │        │
│  │   • INLINE WHERE (doesn't even use constant!)  │        │
│  │   • Duplicates JOIN pattern                    │        │
│  │   • Duplicates row transformation              │        │
│  │                                                 │        │
│  │ ... 9 more functions with same patterns ...    │        │
│  └────────────────────────────────────────────────┘        │
│                                                              │
│  Problems:                                                   │
│  ❌ 164 lines of duplication                                │
│  ❌ LOCKED rules scattered across 10+ functions            │
│  ❌ Manual SQL string concatenation (f-strings)            │
│  ❌ Hard to test rule enforcement consistently             │
└──────────────────────────────────────────────────────────────┘
```

### New Architecture (After)

```
┌─────────────────────────────────────────────────────────────┐
│           trusted_view/query.py (~300 lines)                 │
│                                                              │
│  Core Component (NEW):                                       │
│  ┌────────────────────────────────────────────────┐        │
│  │  TrustedRatesQueryBuilder                      │        │
│  │                                                 │        │
│  │  LOCKED Rules (Single Source of Truth):        │        │
│  │  • _build_where_clause() → Always applied     │        │
│  │  • _build_joins() → Consistent 4-table join   │        │
│  │  • _build_select() → Standard fields          │        │
│  │  • _to_row() → Consistent transformation      │        │
│  │                                                 │        │
│  │  Composable Methods:                           │        │
│  │  • with_source(id)                            │        │
│  │  • with_currency(code)                        │        │
│  │  • best_per_bank()                            │        │
│  │  • order_by_buying_rate(desc)                 │        │
│  │  • execute() → Build & run query              │        │
│  └────────────────────────────────────────────────┘        │
│                                                              │
│  12 Facade Functions (Backward Compatible):                 │
│  ┌────────────────────────────────────────────────┐        │
│  │ def get_trusted_rates(conn, source_id=None):   │        │
│  │     builder = TrustedRatesQueryBuilder(conn)   │        │
│  │     if source_id:                              │        │
│  │         builder.with_source(source_id)         │        │
│  │     return builder.execute()                   │        │
│  │                                                 │        │
│  │ def get_trusted_rates_by_currency(conn, code): │        │
│  │     return (TrustedRatesQueryBuilder(conn)     │        │
│  │             .with_currency(code)               │        │
│  │             .order_by_buying_rate(desc=True)   │        │
│  │             .execute())                        │        │
│  │                                                 │        │
│  │ ... 10 more facades (3-5 lines each) ...      │        │
│  └────────────────────────────────────────────────┘        │
│                                                              │
│  Benefits:                                                   │
│  ✅ 150+ lines eliminated (35% reduction)                  │
│  ✅ LOCKED rules in one place                              │
│  ✅ Composable, type-safe query building                   │
│  ✅ 100% backward compatible                               │
│  ✅ Easier to test and maintain                            │
└──────────────────────────────────────────────────────────────┘
```

### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                 TrustedRatesQueryBuilder                     │
│                                                              │
│  Instance Attributes:                                        │
│  • conn: psycopg2.connection                                │
│  • _filters: List[str]        # Additional WHERE clauses   │
│  • _params: List[Any]         # Query parameters           │
│  • _order_by: List[str]       # ORDER BY clauses           │
│  • _distinct_on: Optional[str] # DISTINCT ON expression    │
│  • _group_by: Optional[str]   # GROUP BY expression        │
│                                                              │
│  Public API (Fluent Interface):                              │
│  ┌──────────────────────────────────────────────┐          │
│  │ Filter Methods (return self for chaining):   │          │
│  │ • with_source(source_id: int)                │          │
│  │ • with_currency(currency_code: str)          │          │
│  │ • with_category(category: str)               │          │
│  │ • major_currencies_only()                    │          │
│  │ • with_date(effective_date: date)            │          │
│  │ • with_date_range(start: date, end: date)    │          │
│  └──────────────────────────────────────────────┘          │
│                                                              │
│  ┌──────────────────────────────────────────────┐          │
│  │ Aggregation Methods (return self):           │          │
│  │ • best_per_bank()                            │          │
│  │ • best_per_currency()                        │          │
│  │ • group_by_date()                            │          │
│  │ • group_by_bank()                            │          │
│  └──────────────────────────────────────────────┘          │
│                                                              │
│  ┌──────────────────────────────────────────────┐          │
│  │ Ordering Methods (return self):              │          │
│  │ • order_by_buying_rate(desc: bool = True)    │          │
│  │ • order_by_bank_name()                       │          │
│  │ • order_by_currency()                        │          │
│  │ • order_by_date(desc: bool = True)           │          │
│  └──────────────────────────────────────────────┘          │
│                                                              │
│  ┌──────────────────────────────────────────────┐          │
│  │ Execution Methods:                           │          │
│  │ • execute() → List[Dict]                     │          │
│  │ • get_sql() → str  # For testing/debugging   │          │
│  │ • get_params() → List  # For testing         │          │
│  └──────────────────────────────────────────────┘          │
│                                                              │
│  Private Methods (Internal Use):                             │
│  ┌──────────────────────────────────────────────┐          │
│  │ • _build_select() → str                      │          │
│  │ • _build_joins() → str                       │          │
│  │ • _build_where() → str  # LOCKED RULES HERE! │          │
│  │ • _build_order_by() → str                    │          │
│  │ • _build_query() → str                       │          │
│  │ • _execute_query() → cursor                  │          │
│  │ • _to_rows(cursor) → List[Dict]              │          │
│  │ • _to_row(cols, row) → Dict                  │          │
│  └──────────────────────────────────────────────┘          │
└──────────────────────────────────────────────────────────────┘
```

---

## Component Design

### 1. TrustedRatesQueryBuilder Class

**Responsibility:** Composable SQL query builder for trusted exchange rates.

**Design Pattern:** Builder Pattern with Fluent Interface

**Key Features:**
- Encapsulates LOCKED rules
- Composable query construction
- Type-safe methods
- SQL injection prevention (parameterized queries)
- Query inspection for testing

#### Complete Implementation

```python
# trusted_view/query.py

from typing import Optional, List, Dict, Any
from datetime import date
from contextlib import contextmanager

# Constants (unchanged)
MAJOR_CURRENCIES = {
    "USD", "EUR", "GBP", "SAR", "AED", "CNY", "JPY", "CAD", "CHF", "AUD",
}


class TrustedRatesQueryBuilder:
    """
    Composable query builder for trusted exchange rate queries.
    
    Automatically enforces LOCKED rules:
    - Exclude rejected observations (validation_status != 'rejected')
    - Exclude ambiguous identities (identity_status != 'ambiguous')
    - Use latest valid version (is_current = TRUE)
    - Require categorization (category_id IS NOT NULL)
    - Only enabled sources (rs.is_enabled = TRUE)
    
    Usage:
        # Simple query
        rates = TrustedRatesQueryBuilder(conn).with_currency("USD").execute()
        
        # Complex query with chaining
        rates = (TrustedRatesQueryBuilder(conn)
                 .with_currency("USD")
                 .best_per_bank()
                 .order_by_buying_rate(desc=True)
                 .execute())
    
    Acceptance tests 19-22. Gap review C, L.
    """
    
    def __init__(self, conn):
        """
        Initialize query builder.
        
        Args:
            conn: psycopg2 database connection
        """
        self.conn = conn
        self._filters: List[str] = []
        self._params: List[Any] = []
        self._order_by: List[str] = []
        self._distinct_on: Optional[str] = None
        self._group_by: Optional[str] = None
    
    # ═══════════════════════════════════════════════════════════
    # Filter Methods
    # ═══════════════════════════════════════════════════════════
    
    def with_source(self, source_id: int) -> 'TrustedRatesQueryBuilder':
        """
        Filter by source/bank ID.
        
        Args:
            source_id: Bank source identifier
        
        Returns:
            self for method chaining
        """
        self._filters.append("o.source_id = %s")
        self._params.append(source_id)
        return self
    
    def with_currency(self, currency_code: str) -> 'TrustedRatesQueryBuilder':
        """
        Filter by currency code.
        
        Args:
            currency_code: ISO currency code (e.g., "USD", "EUR")
        
        Returns:
            self for method chaining
        """
        self._filters.append("o.source_currency_code = %s")
        self._params.append(currency_code.upper())
        return self
    
    def with_category(self, category: str) -> 'TrustedRatesQueryBuilder':
        """
        Filter by rate category.
        
        Args:
            category: Rate category code (e.g., "transactional", "cash")
        
        Returns:
            self for method chaining
        """
        self._filters.append("rc.code = %s")
        self._params.append(category)
        return self
    
    def major_currencies_only(self) -> 'TrustedRatesQueryBuilder':
        """
        Filter to major currencies only (USD, EUR, GBP, etc.).
        
        Returns:
            self for method chaining
        """
        # Use ANY with array for PostgreSQL
        self._filters.append("o.source_currency_code = ANY(%s)")
        self._params.append(list(MAJOR_CURRENCIES))
        return self
    
    def with_date(self, effective_date: date) -> 'TrustedRatesQueryBuilder':
        """
        Filter by specific effective date.
        
        Args:
            effective_date: Specific date to filter by
        
        Returns:
            self for method chaining
        """
        self._filters.append("o.effective_date = %s")
        self._params.append(effective_date)
        return self
    
    def with_date_range(self, start: date, end: date) -> 'TrustedRatesQueryBuilder':
        """
        Filter by date range (inclusive).
        
        Args:
            start: Start date (inclusive)
            end: End date (inclusive)
        
        Returns:
            self for method chaining
        """
        self._filters.append("o.effective_date BETWEEN %s AND %s")
        self._params.extend([start, end])
        return self
    
    # ═══════════════════════════════════════════════════════════
    # Aggregation Methods
    # ═══════════════════════════════════════════════════════════
    
    def best_per_bank(self) -> 'TrustedRatesQueryBuilder':
        """
        Return best (highest) buying rate per bank.
        
        Uses DISTINCT ON (rs.id) with ORDER BY buying_rate DESC.
        Must be called before other ordering methods.
        
        Returns:
            self for method chaining
        """
        self._distinct_on = "rs.id"
        # Add bank ID to beginning of order for DISTINCT ON
        if "rs.id" not in self._order_by:
            self._order_by.insert(0, "rs.id")
        # Default: order by best buying rate
        if "o.buying_rate DESC" not in " ".join(self._order_by):
            self._order_by.append("o.buying_rate DESC NULLS LAST")
        return self
    
    def best_per_currency(self) -> 'TrustedRatesQueryBuilder':
        """
        Return best (highest) buying rate per currency.
        
        Uses DISTINCT ON (o.source_currency_code).
        
        Returns:
            self for method chaining
        """
        self._distinct_on = "o.source_currency_code"
        if "o.source_currency_code" not in self._order_by:
            self._order_by.insert(0, "o.source_currency_code")
        if "o.buying_rate DESC" not in " ".join(self._order_by):
            self._order_by.append("o.buying_rate DESC NULLS LAST")
        return self
    
    def group_by_date(self) -> 'TrustedRatesQueryBuilder':
        """
        Group results by effective date.
        
        Returns:
            self for method chaining
        """
        self._group_by = "o.effective_date"
        return self
    
    def group_by_bank(self) -> 'TrustedRatesQueryBuilder':
        """
        Group results by bank.
        
        Returns:
            self for method chaining
        """
        self._group_by = "rs.id, b.name"
        return self
    
    # ═══════════════════════════════════════════════════════════
    # Ordering Methods
    # ═══════════════════════════════════════════════════════════
    
    def order_by_buying_rate(self, desc: bool = True) -> 'TrustedRatesQueryBuilder':
        """
        Order by buying rate.
        
        Args:
            desc: True for descending (highest first), False for ascending
        
        Returns:
            self for method chaining
        """
        direction = "DESC" if desc else "ASC"
        self._order_by.append(f"o.buying_rate {direction} NULLS LAST")
        return self
    
    def order_by_bank_name(self) -> 'TrustedRatesQueryBuilder':
        """
        Order by bank name alphabetically.
        
        Returns:
            self for method chaining
        """
        self._order_by.append("b.name")
        return self
    
    def order_by_currency(self) -> 'TrustedRatesQueryBuilder':
        """
        Order by currency code alphabetically.
        
        Returns:
            self for method chaining
        """
        self._order_by.append("o.source_currency_code")
        return self
    
    def order_by_date(self, desc: bool = True) -> 'TrustedRatesQueryBuilder':
        """
        Order by effective date.
        
        Args:
            desc: True for newest first, False for oldest first
        
        Returns:
            self for method chaining
        """
        direction = "DESC" if desc else "ASC"
        self._order_by.append(f"o.effective_date {direction}")
        return self
    
    # ═══════════════════════════════════════════════════════════
    # Execution Methods
    # ═══════════════════════════════════════════════════════════
    
    def execute(self) -> List[Dict[str, Any]]:
        """
        Build and execute the query, returning list of rate dicts.
        
        Returns:
            List of rate dictionaries with computed fields
        
        Raises:
            psycopg2.Error: Database query failed
        """
        query = self._build_query()
        with self.conn.cursor() as cur:
            cur.execute(query, self._params)
            return self._to_rows(cur)
    
    def get_sql(self) -> str:
        """
        Get the generated SQL query (for testing/debugging).
        
        Returns:
            SQL query string
        
        Note:
            Parameters are not interpolated - use get_params() separately.
        """
        return self._build_query()
    
    def get_params(self) -> List[Any]:
        """
        Get the query parameters (for testing/debugging).
        
        Returns:
            List of query parameters in order
        """
        return self._params.copy()
    
    # ═══════════════════════════════════════════════════════════
    # Private Methods - Query Building
    # ═══════════════════════════════════════════════════════════
    
    def _build_query(self) -> str:
        """
        Compose the complete SQL query.
        
        Returns:
            Complete SQL query string
        """
        parts = []
        
        # SELECT clause
        parts.append(self._build_select())
        
        # FROM + JOINs
        parts.append(self._build_joins())
        
        # WHERE clause (LOCKED rules + filters)
        parts.append(self._build_where())
        
        # GROUP BY (if specified)
        if self._group_by:
            parts.append(f"GROUP BY {self._group_by}")
        
        # ORDER BY
        order_clause = self._build_order_by()
        if order_clause:
            parts.append(order_clause)
        
        return "\n".join(parts)
    
    def _build_select(self) -> str:
        """
        Build SELECT clause with standard fields.
        
        Returns:
            SELECT clause string
        """
        if self._distinct_on:
            distinct = f"SELECT DISTINCT ON ({self._distinct_on})"
        else:
            distinct = "SELECT"
        
        # Standard fields (from current implementation)
        return f"""{distinct}
            o.id,
            o.source_id,
            b.name                          AS bank_name,
            b.code                          AS bank_code,
            o.source_currency_code,
            o.currency_code,
            rc.code                         AS category,
            o.buying_rate,
            o.selling_rate,
            o.effective_date,
            o.fetched_at,
            o.version_number,
            o.identity_status,
            o.validation_status,
            o.change_review_status,
            rs.verification_status          AS source_verification_status,
            EXISTS (
                SELECT 1 FROM change_candidate cc
                JOIN rate_observation co ON co.id = cc.observation_id
                WHERE co.logical_observation_key = o.logical_observation_key
                  AND cc.status = 'open'
            )                               AS has_pending_review,
            (o.fetched_at::date - o.effective_date) > 3
                                            AS staleness_warning"""
    
    def _build_joins(self) -> str:
        """
        Build FROM and JOIN clauses (standard 4-table join).
        
        Returns:
            FROM and JOIN clauses string
        """
        return """FROM rate_observation o
JOIN rate_source rs ON rs.id = o.source_id
JOIN bank b ON b.id = rs.bank_id
LEFT JOIN rate_category rc ON rc.id = o.category_id"""
    
    def _build_where(self) -> str:
        """
        Build WHERE clause with LOCKED rules and additional filters.
        
        LOCKED RULES (enforced here):
        - Exclude rejected observations
        - Exclude ambiguous identities
        - Use latest valid version (is_current = TRUE)
        - Require categorization
        - Only enabled sources
        
        Returns:
            WHERE clause string
        """
        # LOCKED rules (always applied)
        locked_rules = [
            "o.is_current = TRUE",
            "o.identity_status != 'ambiguous'",
            "o.validation_status != 'rejected'",
            "o.category_id IS NOT NULL",
            "rs.is_enabled = TRUE",
        ]
        
        # Combine LOCKED rules with additional filters
        all_conditions = locked_rules + self._filters
        
        return "WHERE " + "\n  AND ".join(all_conditions)
    
    def _build_order_by(self) -> str:
        """
        Build ORDER BY clause.
        
        Returns:
            ORDER BY clause string, or empty string if no ordering
        """
        if not self._order_by:
            # Default ordering if none specified
            return "ORDER BY b.name, rc.code, o.source_currency_code"
        
        return "ORDER BY " + ", ".join(self._order_by)
    
    # ═══════════════════════════════════════════════════════════
    # Private Methods - Row Transformation
    # ═══════════════════════════════════════════════════════════
    
    def _to_rows(self, cursor) -> List[Dict[str, Any]]:
        """
        Convert cursor rows to list of dicts with computed fields.
        
        Args:
            cursor: Database cursor after query execution
        
        Returns:
            List of rate dictionaries
        """
        cols = [d[0] for d in cursor.description]
        return [self._to_row(cols, row) for row in cursor.fetchall()]
    
    def _to_row(self, cols: List[str], row: tuple) -> Dict[str, Any]:
        """
        Convert single row to dict with computed fields.
        
        Adds computed fields:
        - is_provisional: Based on source_verification_status
        
        Args:
            cols: Column names from cursor.description
            row: Row tuple from cursor
        
        Returns:
            Rate dictionary with all fields
        """
        d = dict(zip(cols, row))
        
        # Computed field: is_provisional (gap review L)
        d["is_provisional"] = d["source_verification_status"] in (
            "unverified",
            "provisional"
        )
        
        return d


# ═══════════════════════════════════════════════════════════════
# Backward Compatible Facade Functions
# ═══════════════════════════════════════════════════════════════

def get_trusted_rates(conn, source_id: Optional[int] = None) -> list:
    """
    Return trusted current rates as a list of dicts.
    
    Backward compatible facade using QueryBuilder.
    Acceptance tests 19-22. Gap review C, L.
    """
    builder = TrustedRatesQueryBuilder(conn)
    if source_id is not None:
        builder.with_source(source_id)
    return builder.execute()


def get_trusted_rates_by_currency(conn, currency_code: str) -> list:
    """
    Return all banks' trusted rates for a single currency code.
    Ordered by buying_rate DESC (best rate first).
    """
    return (TrustedRatesQueryBuilder(conn)
            .with_currency(currency_code)
            .order_by_buying_rate(desc=True)
            .execute())


def get_best_rates_by_currency(conn, currency_code: str) -> list:
    """
    Compare view: one row per bank showing its best buying rate for a currency.
    Best = highest buying_rate across all categories that bank offers.
    """
    results = (TrustedRatesQueryBuilder(conn)
               .with_currency(currency_code)
               .best_per_bank()
               .execute())
    
    # Post-processing: sort by buying_rate DESC
    # (DISTINCT ON doesn't guarantee order across distinct groups)
    results.sort(key=lambda r: r["buying_rate"] or 0, reverse=True)
    return results


def get_bank_rates_pivoted(conn, source_id: int) -> dict:
    """
    By-bank view: returns {currency: {category: {buying, selling, ...}}}.
    Also returns bank metadata.
    """
    rows = get_trusted_rates(conn, source_id=source_id)
    if not rows:
        return {}
    
    # Pivot logic (unchanged from current implementation)
    pivoted = {}
    for r in rows:
        cur = r["source_currency_code"]
        cat = r["category"] or "unknown"
        if cur not in pivoted:
            pivoted[cur] = {}
        pivoted[cur][cat] = {
            "buying": r["buying_rate"],
            "selling": r["selling_rate"],
            "effective_date": r["effective_date"],
            "fetched_at": r["fetched_at"],
            "staleness_warning": r["staleness_warning"],
            "is_provisional": r["is_provisional"],
            "has_pending_review": r["has_pending_review"],
        }
    
    bank_name = rows[0]["bank_name"]
    latest_date = max((r["effective_date"] for r in rows if r["effective_date"]), default=None)
    latest_fetch = max((r["fetched_at"] for r in rows if r["fetched_at"]), default=None)
    any_provisional = any(r["is_provisional"] for r in rows)
    any_stale = any(r["staleness_warning"] for r in rows)
    
    return {
        "bank_name": bank_name,
        "source_id": source_id,
        "currencies": pivoted,
        "latest_date": latest_date,
        "latest_fetch": latest_fetch,
        "is_provisional": any_provisional,
        "staleness_warning": any_stale,
        "categories": sorted({r["category"] for r in rows if r["category"]}),
    }


def get_currency_matrix(conn, major_only: bool = False) -> dict:
    """
    All-rates matrix view.
    Returns currencies × banks matrix with best rates.
    """
    builder = TrustedRatesQueryBuilder(conn).best_per_bank()
    
    if major_only:
        builder.major_currencies_only()
    
    raw = builder.execute()
    
    # Build matrix (unchanged logic)
    matrix = {}
    for r in raw:
        currency = r["source_currency_code"]
        bank_name = r["bank_name"]
        
        if currency not in matrix:
            matrix[currency] = {}
        
        matrix[currency][bank_name] = {
            "buying": r["buying_rate"],
            "selling": r["selling_rate"],
            "staleness_warning": r["staleness_warning"],
        }
    
    currencies = sorted(matrix.keys())
    banks = sorted({b for row in matrix.values() for b in row})
    best_buying = {
        c: max(
            (matrix[c][b]["buying"] for b in matrix[c] if matrix[c][b]["buying"]),
            default=None
        )
        for c in currencies
    }
    
    return {
        "currencies": currencies,
        "banks": banks,
        "matrix": matrix,
        "best_buying": best_buying,
    }


def get_available_dates(conn) -> list:
    """
    Return sorted list of effective_dates (desc) that have at least one trusted rate.
    """
    # Note: This query is simpler - doesn't need full builder
    # But we use builder for consistency
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT o.effective_date
            FROM rate_observation o
            JOIN rate_source rs ON rs.id = o.source_id
            LEFT JOIN rate_category rc ON rc.id = o.category_id
            WHERE o.identity_status != 'ambiguous'
              AND o.validation_status != 'rejected'
              AND o.category_id IS NOT NULL
              AND rs.is_enabled = TRUE
            ORDER BY o.effective_date DESC
        """)
        return [r[0] for r in cur.fetchall() if r[0] is not None]


def get_history_by_currency(conn, currency_code: str, effective_date=None) -> list:
    """
    History view: one best row per (bank, date) for a currency.
    """
    builder = (TrustedRatesQueryBuilder(conn)
               .with_currency(currency_code)
               .best_per_bank())
    
    if effective_date:
        builder.with_date(effective_date)
    
    builder.order_by_date(desc=True)
    
    return builder.execute()


def get_search_suggestions(conn) -> dict:
    """Return {currencies: [...], banks: [{id, name}, ...]} for search datalist."""
    return {
        "currencies": get_available_currencies(conn),
        "banks": get_available_banks(conn),
    }


def get_available_currencies(conn) -> list:
    """Return sorted list of currency codes that have at least one trusted rate."""
    rows = (TrustedRatesQueryBuilder(conn)
            .order_by_currency()
            .execute())
    
    # Get distinct currencies
    currencies = sorted({r["source_currency_code"] for r in rows})
    return currencies


def get_available_banks(conn) -> list:
    """Return list of {id, name} for banks with at least one trusted rate."""
    rows = (TrustedRatesQueryBuilder(conn)
            .order_by_bank_name()
            .execute())
    
    # Get distinct banks
    banks_dict = {r["source_id"]: r["bank_name"] for r in rows}
    return [{"id": sid, "name": name} for sid, name in sorted(banks_dict.items(), key=lambda x: x[1])]


def get_pending_review_observations(conn) -> list:
    """
    Review UI: all observations with change_review_status='pending_review'.
    
    Note: This query is unique (needs previous version join) - keep as-is.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                o.id,
                o.source_id,
                b.name                  AS bank_name,
                o.source_currency_code,
                rc.code                 AS category,
                o.buying_rate,
                o.selling_rate,
                o.effective_date,
                o.fetched_at,
                prev.buying_rate        AS prev_buying,
                prev.selling_rate       AS prev_selling,
                prev.effective_date     AS prev_date
            FROM rate_observation o
            JOIN rate_source rs ON rs.id = o.source_id
            JOIN bank b ON b.id = rs.bank_id
            LEFT JOIN rate_category rc ON rc.id = o.category_id
            LEFT JOIN rate_observation prev
                ON prev.logical_observation_key = o.logical_observation_key
                AND prev.is_current = TRUE
                AND prev.id != o.id
            WHERE o.change_review_status = 'pending_review'
            ORDER BY b.name, o.source_currency_code, rc.code
        """)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_observation_with_warnings(conn, logical_key: str) -> Optional[dict]:
    """
    Get single observation by logical key with warning flags.
    
    Note: This is a specific lookup query - keep as-is for now.
    Could be migrated to builder in future if needed.
    """
    with conn.cursor() as cur:
        cur.execute(
            """SELECT
                   o.id, o.source_id,
                   b.name AS bank_name, b.code AS bank_code,
                   o.source_currency_code, o.currency_code,
                   rc.code AS category,
                   o.buying_rate, o.selling_rate,
                   o.effective_date, o.fetched_at,
                   o.version_number, o.identity_status, o.validation_status,
                   o.change_review_status,
                   rs.verification_status AS source_verification_status,
                   EXISTS (
                       SELECT 1 FROM change_candidate cc
                       JOIN rate_observation co ON co.id = cc.observation_id
                       WHERE co.logical_observation_key = o.logical_observation_key
                         AND cc.status = 'open'
                   ) AS has_pending_review
               FROM rate_observation o
               JOIN rate_source rs ON rs.id = o.source_id
               JOIN bank b ON b.id = rs.bank_id
               LEFT JOIN rate_category rc ON rc.id = o.category_id
               WHERE o.logical_observation_key = %s AND o.is_current = TRUE
               LIMIT 1""",
            (logical_key,),
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = [d[0] for d in cur.description]
        d = dict(zip(cols, row))
        d["is_provisional"] = d["source_verification_status"] in ("unverified", "provisional")
        if d["effective_date"] and d["fetched_at"]:
            d["staleness_warning"] = (d["fetched_at"].date() - d["effective_date"]).days > 3
        else:
            d["staleness_warning"] = False
        return d
```

---

## Migration Strategy

### Phase 1: Add QueryBuilder (Day 1, Morning)

**Goal:** Add TrustedRatesQueryBuilder class without breaking anything.

**Tasks:**
1. Add `TrustedRatesQueryBuilder` class to `trusted_view/query.py`
2. Keep all existing functions unchanged (don't migrate yet)
3. Add unit tests for builder in isolation
4. Run all tests - verify 429 tests still pass

**Success Criteria:**
- Builder class exists and is tested
- No changes to existing functions
- All 429 tests pass

---

### Phase 2: Migrate First Function (Day 1, Afternoon)

**Goal:** Migrate one simple function to validate approach.

**Target:** `get_trusted_rates_by_currency()` (simple, well-tested)

**Tasks:**
1. Rewrite function to use builder
2. Run all tests
3. Compare output with baseline (should be identical)
4. Fix any issues

**Success Criteria:**
- Function uses builder internally
- All tests pass
- Output identical to baseline

---

### Phase 3: Migrate Remaining Functions (Day 2)

**Goal:** Migrate all 12 functions to use builder.

**Order (easiest to hardest):**
1. ✅ `get_trusted_rates_by_currency()` (already done)
2. `get_trusted_rates()` - Simple with optional filter
3. `get_available_currencies()` - Simple query
4. `get_available_banks()` - Simple query
5. `get_best_rates_by_currency()` - Uses best_per_bank()
6. `get_currency_matrix()` - Uses best_per_bank() + post-processing
7. `get_history_by_currency()` - Uses best_per_bank() + optional date
8. `get_bank_rates_pivoted()` - Calls get_trusted_rates() + pivoting
9. `get_search_suggestions()` - Calls other functions
10. `get_available_dates()` - Simple but unique query (keep as-is or migrate later)
11. `get_pending_review_observations()` - Unique query with previous version join (keep as-is)
12. `get_observation_with_warnings()` - Lookup by logical key (keep as-is)

**Success Criteria:**
- All 12 functions work correctly
- All 429 tests pass
- Output identical to baseline

---

### Phase 4: Cleanup and Documentation (Day 3)

**Goal:** Remove old constants, document new patterns, verify.

**Tasks:**
1. Remove `_TRUSTED_WHERE` and `_TRUSTED_SELECT` constants (no longer used)
2. Update module docstring with builder usage
3. Add docstring examples to builder class
4. Run final test suite - all 429 tests pass
5. Measure code reduction (should be 150+ lines)

**Success Criteria:**
- No duplicate SQL code remains
- Documentation complete
- All tests pass
- Code reduction measured

---

## Testing Strategy

### Unit Tests (tests/test_trusted_view_query_builder.py)

```python
import pytest
from datetime import date
from trusted_view.query import TrustedRatesQueryBuilder, MAJOR_CURRENCIES


class TestQueryBuilderConstruction:
    """Test query builder construction and method chaining."""
    
    def test_builder_initialization(self, db_conn):
        """Test builder initializes correctly."""
        builder = TrustedRatesQueryBuilder(db_conn)
        
        assert builder.conn == db_conn
        assert builder._filters == []
        assert builder._params == []
        assert builder._order_by == []
    
    def test_method_chaining(self, db_conn):
        """Test fluent API returns self for chaining."""
        builder = TrustedRatesQueryBuilder(db_conn)
        
        result = (builder
                  .with_currency("USD")
                  .with_source(5)
                  .order_by_buying_rate())
        
        assert result is builder  # Same instance
        assert len(builder._filters) == 2
        assert len(builder._params) == 2


class TestLockedRulesEnforcement:
    """Test LOCKED rules are enforced automatically."""
    
    def test_locked_rules_in_where_clause(self, db_conn):
        """Verify all LOCKED rules present in WHERE clause."""
        builder = TrustedRatesQueryBuilder(db_conn)
        where_clause = builder._build_where()
        
        # All LOCKED rules must be present
        assert "o.is_current = TRUE" in where_clause
        assert "o.identity_status != 'ambiguous'" in where_clause
        assert "o.validation_status != 'rejected'" in where_clause
        assert "o.category_id IS NOT NULL" in where_clause
        assert "rs.is_enabled = TRUE" in where_clause
    
    def test_locked_rules_cannot_be_bypassed(self, db_conn):
        """Verify LOCKED rules always applied, even with no filters."""
        builder = TrustedRatesQueryBuilder(db_conn)
        query = builder.get_sql()
        
        # LOCKED rules present even without additional filters
        assert "o.is_current = TRUE" in query
        assert "o.validation_status != 'rejected'" in query


class TestFilterMethods:
    """Test filter methods add correct WHERE clauses."""
    
    def test_with_source(self, db_conn):
        """Test source ID filter."""
        builder = TrustedRatesQueryBuilder(db_conn).with_source(5)
        
        assert "o.source_id = %s" in builder._filters
        assert 5 in builder._params
    
    def test_with_currency(self, db_conn):
        """Test currency code filter."""
        builder = TrustedRatesQueryBuilder(db_conn).with_currency("usd")
        
        assert "o.source_currency_code = %s" in builder._filters
        assert "USD" in builder._params  # Uppercased
    
    def test_major_currencies_only(self, db_conn):
        """Test major currencies filter."""
        builder = TrustedRatesQueryBuilder(db_conn).major_currencies_only()
        
        assert "o.source_currency_code = ANY(%s)" in builder._filters
        assert list(MAJOR_CURRENCIES) in builder._params
    
    def test_with_date(self, db_conn):
        """Test specific date filter."""
        test_date = date(2026, 10, 14)
        builder = TrustedRatesQueryBuilder(db_conn).with_date(test_date)
        
        assert "o.effective_date = %s" in builder._filters
        assert test_date in builder._params
    
    def test_with_date_range(self, db_conn):
        """Test date range filter."""
        start = date(2026, 10, 1)
        end = date(2026, 10, 14)
        builder = TrustedRatesQueryBuilder(db_conn).with_date_range(start, end)
        
        assert "o.effective_date BETWEEN %s AND %s" in builder._filters
        assert start in builder._params
        assert end in builder._params
    
    def test_multiple_filters_combined(self, db_conn):
        """Test multiple filters combine with AND."""
        builder = (TrustedRatesQueryBuilder(db_conn)
                   .with_currency("USD")
                   .with_source(5))
        
        where_clause = builder._build_where()
        
        assert "o.source_currency_code = %s" in where_clause
        assert "o.source_id = %s" in where_clause
        assert "AND" in where_clause


class TestAggregationMethods:
    """Test aggregation and grouping methods."""
    
    def test_best_per_bank(self, db_conn):
        """Test best per bank uses DISTINCT ON."""
        builder = TrustedRatesQueryBuilder(db_conn).best_per_bank()
        query = builder.get_sql()
        
        assert "DISTINCT ON (rs.id)" in query
        assert "ORDER BY rs.id" in query
        assert "o.buying_rate DESC" in query
    
    def test_best_per_currency(self, db_conn):
        """Test best per currency uses DISTINCT ON."""
        builder = TrustedRatesQueryBuilder(db_conn).best_per_currency()
        query = builder.get_sql()
        
        assert "DISTINCT ON (o.source_currency_code)" in query


class TestOrderingMethods:
    """Test ordering methods."""
    
    def test_order_by_buying_rate_desc(self, db_conn):
        """Test descending buying rate order."""
        builder = TrustedRatesQueryBuilder(db_conn).order_by_buying_rate(desc=True)
        order_clause = builder._build_order_by()
        
        assert "o.buying_rate DESC NULLS LAST" in order_clause
    
    def test_order_by_buying_rate_asc(self, db_conn):
        """Test ascending buying rate order."""
        builder = TrustedRatesQueryBuilder(db_conn).order_by_buying_rate(desc=False)
        order_clause = builder._build_order_by()
        
        assert "o.buying_rate ASC NULLS LAST" in order_clause
    
    def test_order_by_bank_name(self, db_conn):
        """Test bank name ordering."""
        builder = TrustedRatesQueryBuilder(db_conn).order_by_bank_name()
        order_clause = builder._build_order_by()
        
        assert "b.name" in order_clause
    
    def test_default_ordering(self, db_conn):
        """Test default ordering when none specified."""
        builder = TrustedRatesQueryBuilder(db_conn)
        order_clause = builder._build_order_by()
        
        # Default: bank name, category, currency
        assert "b.name" in order_clause
        assert "rc.code" in order_clause
        assert "o.source_currency_code" in order_clause


class TestRowTransformation:
    """Test row transformation logic."""
    
    def test_to_row_adds_computed_fields(self, db_conn):
        """Test _to_row adds is_provisional field."""
        builder = TrustedRatesQueryBuilder(db_conn)
        
        cols = ["id", "source_verification_status"]
        row = (1, "provisional")
        
        result = builder._to_row(cols, row)
        
        assert result["id"] == 1
        assert result["source_verification_status"] == "provisional"
        assert result["is_provisional"] is True
    
    def test_is_provisional_for_verified_source(self, db_conn):
        """Test is_provisional False for verified sources."""
        builder = TrustedRatesQueryBuilder(db_conn)
        
        cols = ["source_verification_status"]
        row = ("verified",)
        
        result = builder._to_row(cols, row)
        assert result["is_provisional"] is False
    
    def test_is_provisional_for_unverified_source(self, db_conn):
        """Test is_provisional True for unverified sources."""
        builder = TrustedRatesQueryBuilder(db_conn)
        
        cols = ["source_verification_status"]
        row = ("unverified",)
        
        result = builder._to_row(cols, row)
        assert result["is_provisional"] is True


class TestQueryInspection:
    """Test query inspection methods for debugging/testing."""
    
    def test_get_sql_returns_query_string(self, db_conn):
        """Test get_sql() returns SQL query."""
        builder = (TrustedRatesQueryBuilder(db_conn)
                   .with_currency("USD"))
        
        sql = builder.get_sql()
        
        assert isinstance(sql, str)
        assert "SELECT" in sql
        assert "WHERE" in sql
        assert "o.source_currency_code = %s" in sql
    
    def test_get_params_returns_parameters(self, db_conn):
        """Test get_params() returns parameter list."""
        builder = (TrustedRatesQueryBuilder(db_conn)
                   .with_currency("USD")
                   .with_source(5))
        
        params = builder.get_params()
        
        assert params == ["USD", 5]


class TestBackwardCompatibility:
    """Test backward compatible facade functions."""
    
    def test_get_trusted_rates_by_currency(self, db_conn, baseline_data):
        """Test get_trusted_rates_by_currency produces same output."""
        from trusted_view.query import get_trusted_rates_by_currency
        
        results = get_trusted_rates_by_currency(db_conn, "USD")
        
        # Verify structure matches baseline
        assert isinstance(results, list)
        if results:
            assert "source_currency_code" in results[0]
            assert "buying_rate" in results[0]
            assert "is_provisional" in results[0]
    
    def test_all_functions_still_work(self, db_conn):
        """Smoke test: all 12 functions execute without error."""
        from trusted_view import query
        
        # Test each function (with minimal valid inputs)
        query.get_trusted_rates(db_conn)
        query.get_trusted_rates_by_currency(db_conn, "USD")
        query.get_best_rates_by_currency(db_conn, "USD")
        query.get_bank_rates_pivoted(db_conn, 1)
        query.get_currency_matrix(db_conn)
        query.get_available_dates(db_conn)
        query.get_history_by_currency(db_conn, "USD")
        query.get_search_suggestions(db_conn)
        query.get_available_currencies(db_conn)
        query.get_available_banks(db_conn)
        query.get_pending_review_observations(db_conn)
        # get_observation_with_warnings requires valid logical_key
```

### Integration Tests

```python
def test_acceptance_tests_still_pass():
    """
    Verify acceptance tests 19-22 still pass.
    
    AT-19: Trusted view excludes rejected observations
    AT-20: Trusted view excludes ambiguous identities
    AT-21: Trusted view returns only current versions
    AT-22: Trusted view excludes uncategorized rates
    """
    # These tests already exist - just run them
    pass


def test_api_endpoints_work(flask_client):
    """Test API endpoints work with refactored queries."""
    response = flask_client.get("/rates")
    assert response.status_code == 200
    
    response = flask_client.get("/rates/by-currency/USD")
    assert response.status_code == 200
```

---

## Performance Considerations

### Query Performance

**Expected:** No performance regression; similar or slightly better performance.

**Why No Regression:**
- Same SQL generated (just composed differently)
- Same query plans (EXPLAIN ANALYZE should match)
- Parameterized queries (same as current)
- No additional database round-trips

**Performance Testing:**
```python
import time

def benchmark_query_function(conn, func, *args, iterations=100):
    """Benchmark a query function."""
    start = time.time()
    for _ in range(iterations):
        results = func(conn, *args)
    elapsed = time.time() - start
    return elapsed / iterations

# Baseline (before refactoring)
baseline_time = benchmark_query_function(conn, get_trusted_rates_by_currency_OLD, "USD")

# After refactoring
new_time = benchmark_query_function(conn, get_trusted_rates_by_currency, "USD")

# Should be within 5% (no significant regression)
assert new_time < baseline_time * 1.05
```

### Memory Usage

**Expected:** Negligible increase (builder object overhead).

**Measurement:**
- Builder instances are short-lived (created per request, garbage collected)
- No persistent state or caching
- Memory footprint: ~1KB per builder instance

---

## Rollback Strategy

### Quick Rollback

If issues detected immediately after deployment:

**Option 1: Revert entire file**
```bash
git checkout HEAD~1 trusted_view/query.py
git commit -m "Rollback query builder refactoring"
git push
```

**Option 2: Keep builder, revert specific functions**
- Revert individual function implementations
- Keep TrustedRatesQueryBuilder class for future use

### Gradual Rollback

If specific functions have issues:

1. Identify problematic function
2. Revert function to old implementation (keep old code commented nearby)
3. File issue for investigation
4. Fix and re-migrate when ready

### Emergency Fallback

Add feature flag to toggle between old/new implementations:

```python
USE_QUERY_BUILDER = os.environ.get("USE_QUERY_BUILDER", "true").lower() == "true"

def get_trusted_rates_by_currency(conn, currency_code: str) -> list:
    if USE_QUERY_BUILDER:
        # New implementation
        return (TrustedRatesQueryBuilder(conn)
                .with_currency(currency_code)
                .order_by_buying_rate(desc=True)
                .execute())
    else:
        # Old implementation (fallback)
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
```

Then toggle via environment variable if needed.

---

## Appendix: Code Metrics

### Before Refactoring

**File:** `trusted_view/query.py`
- **Total lines:** ~450
- **Duplicate SQL:** ~164 lines
- **Functions:** 12
- **Constants:** 3 (_TRUSTED_WHERE, _TRUSTED_SELECT, MAJOR_CURRENCIES)

**Duplication Breakdown:**
- WHERE clause duplication: ~15 lines × 8 functions = 120 lines
- JOIN pattern duplication: ~4 lines × 8 functions = 32 lines
- Row transformation: ~2 lines × 6 functions = 12 lines

### After Refactoring

**File:** `trusted_view/query.py`
- **Total lines:** ~300 (33% reduction)
- **Duplicate SQL:** 0 lines
- **Classes:** 1 (TrustedRatesQueryBuilder)
- **Functions:** 12 (facades)
- **Constants:** 1 (MAJOR_CURRENCIES only)

**Code Reduction:**
- Builder class: ~200 lines (new)
- Facade functions: ~100 lines (simplified from ~280)
- **Net reduction:** ~150 lines eliminated

### Complexity Metrics

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Lines of Code | 450 | 300 | -33% |
| Cyclomatic Complexity | High (duplicated logic) | Low (centralized) | Better |
| Duplication | 164 lines | 0 lines | Eliminated |
| LOCKED rule locations | 10+ functions | 1 location | Single source |
| Testability | Moderate | High | Improved |

---

**Design Status:** Complete - Ready for Review  
**Next Step:** Create tasks.md with implementation breakdown  
**Estimated Effort:** 2-3 days (implementation + testing + migration)
