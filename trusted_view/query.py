"""
trusted_view/query.py — trusted current-rate read model.
LOCKED rules:
- Exclude rejected observations and ambiguous identities.
- Use latest valid version of each logical observation (is_current=TRUE).
- Never select by fetched_at alone — respect version chain and effective_date.
- Never silently substitute an older rate for a missing current rate.
- Show effective_date and last fetch separately.
- Unknown category or currency excluded until reviewed.
- Provisional sources visibly labeled (gap review L).
- Pending review on a logical observation → uncertainty warning (gap review C).
Acceptance tests 19–22.
"""
from typing import Optional, List, Dict, Any
from datetime import date

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
                                            AS staleness_warning,
            (CURRENT_DATE - o.effective_date)  AS days_stale"""
    
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





def get_trusted_rates(conn, source_id: Optional[int] = None, as_of=None) -> list:
    """
    Return trusted current rates as a list of dicts.
    
    Args:
        conn: Database connection
        source_id: Optional bank source ID to filter by
        as_of: Optional date — return rates whose effective_date <= as_of
               (latest version per logical key as of that date)
    
    Returns:
        List of rate dictionaries
    
    Backward compatible facade using QueryBuilder.
    Acceptance tests 19-22. Gap review C, L.
    """
    builder = TrustedRatesQueryBuilder(conn)
    
    if source_id is not None:
        builder.with_source(source_id)
    
    if as_of is not None:
        # Note: as_of uses <= comparison, need to use date_range with None end
        # For backward compatibility, add as filter manually
        builder._filters.append("o.effective_date <= %s")
        builder._params.append(as_of)
    
    return builder.execute()


def get_trusted_rates_by_currency(conn, currency_code: str) -> list:
    """
    Return all banks' trusted rates for a single currency code.
    Ordered by buying_rate DESC (best rate first).
    
    Args:
        conn: Database connection
        currency_code: ISO currency code (e.g., "USD", "EUR")
    
    Returns:
        List of rate dictionaries ordered by buying rate descending
    """
    return (TrustedRatesQueryBuilder(conn)
            .with_currency(currency_code)
            .order_by_buying_rate(desc=True)
            .execute())


def get_best_rates_by_currency(conn, currency_code: str, category: str = None) -> list:
    """
    Compare view: one row per bank for a currency, optionally filtered by category.
    Includes day-over-day delta and industry average.
    Ordered by buying_rate DESC.
    """
    # Build category filter
    cat_clause = "AND rc.code = %s" if category else ""
    params = [currency_code.upper()]
    if category:
        params.append(category)

    # Get today's best rate per bank (highest buying across categories if no filter)
    query = f"""
        SELECT DISTINCT ON (rs.id)
            o.id, o.source_id,
            b.name AS bank_name, b.code AS bank_code,
            o.source_currency_code,
            rc.code AS category,
            o.buying_rate, o.selling_rate,
            o.effective_date, o.fetched_at,
            rs.verification_status AS source_verification_status,
            (o.fetched_at::date - o.effective_date) > 3 AS staleness_warning,
            (CURRENT_DATE - o.effective_date) AS days_stale
        FROM rate_observation o
        JOIN rate_source rs ON rs.id = o.source_id
        JOIN bank b ON b.id = rs.bank_id
        LEFT JOIN rate_category rc ON rc.id = o.category_id
        WHERE o.is_current = TRUE
          AND o.identity_status != 'ambiguous'
          AND o.validation_status != 'rejected'
          AND o.category_id IS NOT NULL
          AND rs.is_enabled = TRUE
          AND o.source_currency_code = %s
          {cat_clause}
        ORDER BY rs.id, o.buying_rate DESC NULLS LAST
    """
    with conn.cursor() as cur:
        cur.execute(query, params)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    # Compute delta vs previous effective_date per bank
    if rows:
        source_ids = [r["source_id"] for r in rows]
        prev_query = f"""
            SELECT DISTINCT ON (rs.id)
                rs.id AS source_id,
                o.buying_rate AS prev_buying,
                o.selling_rate AS prev_selling,
                o.effective_date AS prev_date
            FROM rate_observation o
            JOIN rate_source rs ON rs.id = o.source_id
            LEFT JOIN rate_category rc ON rc.id = o.category_id
            WHERE o.identity_status != 'ambiguous'
              AND o.validation_status != 'rejected'
              AND o.category_id IS NOT NULL
              AND rs.is_enabled = TRUE
              AND o.source_currency_code = %s
              AND rs.id = ANY(%s)
              {cat_clause}
              AND o.effective_date < (SELECT MAX(effective_date) FROM rate_observation o2
                                      WHERE o2.source_id = rs.id
                                        AND o2.source_currency_code = %s
                                        AND o2.is_current = TRUE)
            ORDER BY rs.id, o.effective_date DESC NULLS LAST
        """
        prev_params = [currency_code.upper(), source_ids]
        if category:
            prev_params.append(category)
        prev_params.append(currency_code.upper())
        with conn.cursor() as cur:
            cur.execute(prev_query, prev_params)
            prev_cols = [d[0] for d in cur.description]
            prev_map = {r[0]: dict(zip(prev_cols, r)) for r in cur.fetchall()}

        for r in rows:
            prev = prev_map.get(r["source_id"])
            if prev and r["buying_rate"] and prev["prev_buying"]:
                r["delta_buying"] = float(r["buying_rate"]) - float(prev["prev_buying"])
                r["prev_date"] = prev["prev_date"]
            else:
                r["delta_buying"] = None
                r["prev_date"] = None
            r["is_provisional"] = r["source_verification_status"] in ("unverified", "provisional")
            # Spread as percentage
            if r["buying_rate"] and r["selling_rate"] and r["buying_rate"] > 0:
                r["spread_pct"] = round(
                    (float(r["selling_rate"]) - float(r["buying_rate"])) / float(r["buying_rate"]) * 100, 2
                )
            else:
                r["spread_pct"] = None

    rows.sort(key=lambda r: r["buying_rate"] or 0, reverse=True)

    # Industry average
    valid = [r for r in rows if r["buying_rate"]]
    if valid:
        avg_buy = sum(float(r["buying_rate"]) for r in valid) / len(valid)
        avg_sell = sum(float(r["selling_rate"]) for r in valid if r["selling_rate"]) / max(1, sum(1 for r in valid if r["selling_rate"]))
        for r in rows:
            r["industry_avg_buying"] = round(avg_buy, 4)
            r["industry_avg_selling"] = round(avg_sell, 4)

    return rows


def get_bank_rates_pivoted(conn, source_id: int) -> dict:
    """
    By-bank view: returns {currency: {category: {buying, selling, effective_date,
    fetched_at, staleness_warning, is_provisional}}}.
    Also returns bank_name, source_id, latest effective_date, latest fetched_at.
    """
    rows = get_trusted_rates(conn, source_id=source_id)
    if not rows:
        return {}

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
    builder = TrustedRatesQueryBuilder(conn).best_per_bank()
    if major_only:
        builder.major_currencies_only()
    raw = builder.execute()

    matrix = {}
    bank_ids = {}
    bank_codes = {}
    for r in raw:
        currency = r["source_currency_code"]
        bank_name = r["bank_name"]
        bank_ids[bank_name] = r["source_id"]
        bank_codes[bank_name] = r["bank_code"]
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
        "bank_ids": bank_ids,
        "bank_codes": bank_codes,
        "matrix": matrix,
        "best_buying": best_buying,
    }


def get_available_dates(conn) -> list:
    """Return sorted list of effective_dates (desc) that have at least one trusted rate."""
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
    
    Args:
        conn: Database connection
        currency_code: ISO currency code
        effective_date: Optional date filter - if given, filter to that date only
    
    Returns:
        List of dicts with effective_date, bank_name, buying_rate, selling_rate,
        category, is_provisional. Ordered by effective_date DESC, buying_rate DESC.
    
    Note: This query intentionally excludes is_current filter to show historical data.
    Kept as manual query due to unique WHERE clause requirements.
    """
    date_clause = "AND o.effective_date = %s" if effective_date else ""
    params = [currency_code]
    if effective_date:
        params.append(effective_date)

    query = f"""
        SELECT DISTINCT ON (o.effective_date, rs.id)
            o.effective_date,
            b.name                          AS bank_name,
            rc.code                         AS category,
            o.buying_rate,
            o.selling_rate,
            rs.verification_status          AS source_verification_status
        FROM rate_observation o
        JOIN rate_source rs ON rs.id = o.source_id
        JOIN bank b ON b.id = rs.bank_id
        LEFT JOIN rate_category rc ON rc.id = o.category_id
        WHERE o.identity_status != 'ambiguous'
          AND o.validation_status != 'rejected'
          AND o.category_id IS NOT NULL
          AND rs.is_enabled = TRUE
          AND o.source_currency_code = %s
          {date_clause}
        ORDER BY o.effective_date DESC, rs.id, o.buying_rate DESC NULLS LAST
    """
    with conn.cursor() as cur:
        cur.execute(query, params)
        cols = [d[0] for d in cur.description]
        rows = []
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            d["is_provisional"] = d["source_verification_status"] in ("unverified", "provisional")
            rows.append(d)
    return rows


def get_search_suggestions(conn) -> dict:
    """
    Return {currencies: [...], banks: [{id, name}, ...]} for search datalist.
    
    Args:
        conn: Database connection
    
    Returns:
        Dict with 'currencies' and 'banks' keys
    """
    return {
        "currencies": get_available_currencies(conn),
        "banks": get_available_banks(conn),
    }


def get_available_currencies(conn) -> list:
    """
    Return sorted list of currency codes that have at least one trusted rate.
    
    Args:
        conn: Database connection
    
    Returns:
        Sorted list of currency codes
    """
    rows = (TrustedRatesQueryBuilder(conn)
            .order_by_currency()
            .execute())
    
    # Get distinct currencies
    currencies = sorted({r["source_currency_code"] for r in rows})
    return currencies


def get_available_banks(conn) -> list:
    """
    Return list of {id, name} for banks with at least one trusted rate.
    
    Args:
        conn: Database connection
    
    Returns:
        List of dicts with 'id' and 'name' keys, sorted by name
    """
    rows = (TrustedRatesQueryBuilder(conn)
            .order_by_bank_name()
            .execute())
    
    # Get distinct banks
    banks_dict = {r["source_id"]: r["bank_name"] for r in rows}
    return [{"id": sid, "name": name} for sid, name in sorted(banks_dict.items(), key=lambda x: x[1])]


def get_pending_review_observations(conn) -> list:
    """
    Review UI: all observations with change_review_status='pending_review',
    joined with their prior version for rate comparison.
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
