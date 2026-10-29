from typing import Optional, List, Dict, Any
from datetime import date

MAJOR_CURRENCIES = {
    "USD", "EUR", "GBP", "SAR", "AED", "CNY", "JPY", "CAD", "CHF", "AUD",
}

class TrustedRatesQueryBuilder:

    def __init__(self, conn):
        self.conn = conn
        self._filters: List[str] = []
        self._params: List[Any] = []
        self._order_by: List[str] = []
        self._distinct_on: Optional[str] = None
        self._group_by: Optional[str] = None

    def with_source(self, source_id: int) -> 'TrustedRatesQueryBuilder':
        self._filters.append("o.source_id = %s")
        self._params.append(source_id)
        return self

    def with_currency(self, currency_code: str) -> 'TrustedRatesQueryBuilder':
        self._filters.append("o.source_currency_code = %s")
        self._params.append(currency_code.upper())
        return self

    def with_category(self, category: str) -> 'TrustedRatesQueryBuilder':
        self._filters.append("rc.code = %s")
        self._params.append(category)
        return self

    def major_currencies_only(self) -> 'TrustedRatesQueryBuilder':
        self._filters.append("o.source_currency_code = ANY(%s)")
        self._params.append(list(MAJOR_CURRENCIES))
        return self

    def with_date(self, effective_date: date) -> 'TrustedRatesQueryBuilder':
        self._filters.append("o.effective_date = %s")
        self._params.append(effective_date)
        return self

    def with_date_range(self, start: date, end: date) -> 'TrustedRatesQueryBuilder':
        self._filters.append("o.effective_date BETWEEN %s AND %s")
        self._params.extend([start, end])
        return self

    def best_per_bank(self) -> 'TrustedRatesQueryBuilder':
        self._distinct_on = "rs.id"
        if "rs.id" not in self._order_by:
            self._order_by.insert(0, "rs.id")
        if "o.buying_rate DESC" not in " ".join(self._order_by):
            self._order_by.append("o.buying_rate DESC NULLS LAST")
        return self

    def best_per_currency(self) -> 'TrustedRatesQueryBuilder':
        self._distinct_on = "o.source_currency_code"
        if "o.source_currency_code" not in self._order_by:
            self._order_by.insert(0, "o.source_currency_code")
        if "o.buying_rate DESC" not in " ".join(self._order_by):
            self._order_by.append("o.buying_rate DESC NULLS LAST")
        return self

    def group_by_date(self) -> 'TrustedRatesQueryBuilder':
        self._group_by = "o.effective_date"
        return self

    def group_by_bank(self) -> 'TrustedRatesQueryBuilder':
        self._group_by = "rs.id, b.name"
        return self

    def order_by_buying_rate(self, desc: bool = True) -> 'TrustedRatesQueryBuilder':
        direction = "DESC" if desc else "ASC"
        self._order_by.append(f"o.buying_rate {direction} NULLS LAST")
        return self

    def order_by_bank_name(self) -> 'TrustedRatesQueryBuilder':
        self._order_by.append("b.name")
        return self

    def order_by_currency(self) -> 'TrustedRatesQueryBuilder':
        self._order_by.append("o.source_currency_code")
        return self

    def order_by_date(self, desc: bool = True) -> 'TrustedRatesQueryBuilder':
        direction = "DESC" if desc else "ASC"
        self._order_by.append(f"o.effective_date {direction}")
        return self

    def execute(self) -> List[Dict[str, Any]]:
        query = self._build_query()
        with self.conn.cursor() as cur:
            cur.execute(query, self._params)
            return self._to_rows(cur)

    def get_sql(self) -> str:
        return self._build_query()

    def get_params(self) -> List[Any]:
        return self._params.copy()

    def _build_query(self) -> str:
        parts = []

        parts.append(self._build_select())

        parts.append(self._build_joins())

        parts.append(self._build_where())

        if self._group_by:
            parts.append(f"GROUP BY {self._group_by}")

        order_clause = self._build_order_by()
        if order_clause:
            parts.append(order_clause)

        return "\n".join(parts)

    def _build_select(self) -> str:
        if self._distinct_on:
            distinct = f"SELECT DISTINCT ON ({self._distinct_on})"
        else:
            distinct = "SELECT"

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
            o.is_fallback,
            rs.verification_status          AS source_verification_status,
            EXISTS (
                SELECT 1 FROM change_candidate cc
                JOIN rate_observation co ON co.id = cc.observation_id
                WHERE co.logical_observation_key = o.logical_observation_key
                  AND cc.status = 'open'
            )                               AS has_pending_review,
            CASE WHEN o.effective_date IS NOT NULL
                 THEN (o.fetched_at::date - o.effective_date) > 3
                 ELSE FALSE
            END                             AS staleness_warning,
            CASE WHEN o.effective_date IS NOT NULL
                 THEN (CURRENT_DATE - o.effective_date)
                 ELSE NULL
            END                             AS days_stale"""

    def _build_joins(self) -> str:
        return """FROM rate_observation o
JOIN rate_source rs ON rs.id = o.source_id
JOIN bank b ON b.id = rs.bank_id
LEFT JOIN rate_category rc ON rc.id = o.category_id"""

    def _build_where(self) -> str:
        locked_rules = [
            "o.is_current = TRUE",
            "o.identity_status != 'ambiguous'",
            "o.validation_status != 'rejected'",
            "o.category_id IS NOT NULL",
            "rs.is_enabled = TRUE",
        ]

        all_conditions = locked_rules + self._filters

        return "WHERE " + "\n  AND ".join(all_conditions)

    def _build_order_by(self) -> str:
        if not self._order_by:
            return "ORDER BY b.name, rc.code, o.source_currency_code, o.effective_date DESC NULLS LAST, o.id DESC"

        return "ORDER BY " + ", ".join(self._order_by)

    def _to_rows(self, cursor) -> List[Dict[str, Any]]:
        cols = [d[0] for d in cursor.description]
        return [self._to_row(cols, row) for row in cursor.fetchall()]

    def _to_row(self, cols: List[str], row: tuple) -> Dict[str, Any]:
        d = dict(zip(cols, row))

        d["is_provisional"] = d["source_verification_status"] in (
            "unverified",
            "provisional"
        )

        return d

def get_trusted_rates(conn, source_id: Optional[int] = None, as_of=None) -> list:
    builder = TrustedRatesQueryBuilder(conn)

    if source_id is not None:
        builder.with_source(source_id)

    if as_of is not None:
        builder._filters.append("o.effective_date <= %s")
        builder._params.append(as_of)

    return builder.execute()

def get_trusted_rates_by_currency(conn, currency_code: str) -> list:
    return (TrustedRatesQueryBuilder(conn)
            .with_currency(currency_code)
            .order_by_buying_rate(desc=True)
            .execute())

def get_best_rates_by_currency(conn, currency_code: str, category: str = None) -> list:
    cat_clause = "AND rc.code = %s" if category else ""
    params = [currency_code.upper()]
    if category:
        params.append(category)

    query = f"""
        SELECT DISTINCT ON (rs.id)
            o.id, o.source_id,
            b.name AS bank_name, b.code AS bank_code,
            o.source_currency_code,
            rc.code AS category,
            o.buying_rate, o.selling_rate,
            o.effective_date, o.fetched_at,
            rs.verification_status AS source_verification_status,
            CASE WHEN o.effective_date IS NOT NULL
                 THEN (o.fetched_at::date - o.effective_date) > 3
                 ELSE FALSE
            END AS staleness_warning,
            CASE WHEN o.effective_date IS NOT NULL
                 THEN (CURRENT_DATE - o.effective_date)
                 ELSE NULL
            END AS days_stale
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
            if r["buying_rate"] and r["selling_rate"] and r["buying_rate"] > 0:
                r["spread_pct"] = round(
                    (float(r["selling_rate"]) - float(r["buying_rate"])) / float(r["buying_rate"]) * 100, 2
                )
            else:
                r["spread_pct"] = None

    rows.sort(key=lambda r: r["buying_rate"] or 0, reverse=True)

    valid = [r for r in rows if r["buying_rate"]]
    if valid:
        avg_buy = sum(float(r["buying_rate"]) for r in valid) / len(valid)
        avg_sell = sum(float(r["selling_rate"]) for r in valid if r["selling_rate"]) / max(1, sum(1 for r in valid if r["selling_rate"]))
        for r in rows:
            r["industry_avg_buying"] = round(avg_buy, 4)
            r["industry_avg_selling"] = round(avg_sell, 4)

    return rows

def get_bank_rates_pivoted(conn, source_id: int) -> dict:
    rows = get_trusted_rates(conn, source_id=source_id)
    if not rows:
        return {}

    pivoted = {}
    for r in rows:
        cur = r["source_currency_code"]
        cat = r["category"] or "unknown"
        if cur not in pivoted:
            pivoted[cur] = {}
        existing = pivoted[cur].get(cat)
        if existing and existing.get("effective_date") and r.get("effective_date"):
            if existing["effective_date"] > r["effective_date"]:
                continue
            elif existing["effective_date"] == r["effective_date"]:
                existing_fetch = existing.get("fetched_at")
                current_fetch = r.get("fetched_at")
                if existing_fetch and current_fetch and existing_fetch >= current_fetch:
                    continue
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
    any_provisional = any(bool(r.get("is_provisional")) for r in rows)
    any_stale = any(bool(r.get("staleness_warning")) for r in rows)

    return {
        "bank_name": bank_name,
        "source_id": source_id,
        "currencies": pivoted,
        "latest_date": latest_date,
        "latest_fetch": latest_fetch,
        "is_provisional": any_provisional,
        "staleness_warning": any_stale,
        "categories": sorted({str(r["category"]) for r in rows if r.get("category")}),
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
    return {
        "currencies": get_available_currencies(conn),
        "banks": get_available_banks(conn),
    }

def get_available_currencies(conn) -> list:
    rows = (TrustedRatesQueryBuilder(conn)
            .order_by_currency()
            .execute())

    currencies = sorted({r["source_currency_code"] for r in rows})
    return currencies

def get_available_banks(conn) -> list:
    rows = (TrustedRatesQueryBuilder(conn)
            .order_by_bank_name()
            .execute())

    banks_dict = {r["source_id"]: r["bank_name"] for r in rows}
    return [{"id": sid, "name": name} for sid, name in sorted(banks_dict.items(), key=lambda x: x[1])]

def get_pending_review_observations(conn) -> list:
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
