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
from typing import Optional

MAJOR_CURRENCIES = {
    "USD", "EUR", "GBP", "SAR", "AED", "CNY", "JPY", "CAD", "CHF", "AUD",
}

_TRUSTED_WHERE = """
    o.is_current = TRUE
    AND o.identity_status != 'ambiguous'
    AND o.validation_status != 'rejected'
    AND o.category_id IS NOT NULL
"""

_TRUSTED_SELECT = """
    SELECT
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
                                        AS staleness_warning
    FROM rate_observation o
    JOIN rate_source rs ON rs.id = o.source_id
    JOIN bank b ON b.id = rs.bank_id
    LEFT JOIN rate_category rc ON rc.id = o.category_id
"""


def _to_row(cols, row):
    d = dict(zip(cols, row))
    d["is_provisional"] = d["source_verification_status"] in ("unverified", "provisional")
    return d


def get_trusted_rates(conn, source_id: Optional[int] = None) -> list:
    """
    Return trusted current rates as a list of dicts.
    Each dict includes bank_name, bank_code plus all observation fields.
    Acceptance tests 19-22. Gap review C, L.
    """
    params = []
    extra = ""
    if source_id is not None:
        extra = "AND o.source_id = %s"
        params.append(source_id)

    query = f"{_TRUSTED_SELECT} WHERE {_TRUSTED_WHERE} {extra} ORDER BY b.name, rc.code, o.source_currency_code"

    with conn.cursor() as cur:
        cur.execute(query, params)
        cols = [d[0] for d in cur.description]
        return [_to_row(cols, row) for row in cur.fetchall()]


def get_trusted_rates_by_currency(conn, currency_code: str) -> list:
    """
    Return all banks' trusted rates for a single currency code.
    Ordered by buying_rate DESC (best rate first).
    """
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


def get_best_rates_by_currency(conn, currency_code: str) -> list:
    """
    Compare view: one row per bank showing its best buying rate for a currency.
    Best = highest buying_rate across all categories that bank offers.
    Returns list of dicts: bank_name, source_id, best_buying, best_selling,
    category, effective_date, fetched_at, is_provisional, staleness_warning.
    Ordered by best_buying DESC.
    """
    query = """
        SELECT DISTINCT ON (rs.id)
            rs.id                           AS source_id,
            b.name                          AS bank_name,
            o.source_currency_code,
            rc.code                         AS category,
            o.buying_rate,
            o.selling_rate,
            o.effective_date,
            o.fetched_at,
            rs.verification_status          AS source_verification_status,
            (o.fetched_at::date - o.effective_date) > 3
                                            AS staleness_warning
        FROM rate_observation o
        JOIN rate_source rs ON rs.id = o.source_id
        JOIN bank b ON b.id = rs.bank_id
        LEFT JOIN rate_category rc ON rc.id = o.category_id
        WHERE o.is_current = TRUE
          AND o.identity_status != 'ambiguous'
          AND o.validation_status != 'rejected'
          AND o.category_id IS NOT NULL
          AND o.source_currency_code = %s
        ORDER BY rs.id, o.buying_rate DESC NULLS LAST
    """
    with conn.cursor() as cur:
        cur.execute(query, (currency_code,))
        cols = [d[0] for d in cur.description]
        rows = []
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            d["is_provisional"] = d["source_verification_status"] in ("unverified", "provisional")
            rows.append(d)
    # sort by buying_rate DESC
    rows.sort(key=lambda r: r["buying_rate"] or 0, reverse=True)
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
    """
    All-rates matrix view.
    Returns {
      currencies: [code, ...],          # row headers, sorted
      banks: [name, ...],               # column headers, sorted
      matrix: {currency: {bank: {buying, selling, staleness_warning}}},
      best_buying: {currency: Decimal}  # best buying per currency row
    }
    """
    query = f"""
        SELECT DISTINCT ON (rs.id, o.source_currency_code)
            o.source_currency_code,
            b.name                          AS bank_name,
            o.buying_rate,
            o.selling_rate,
            (o.fetched_at::date - o.effective_date) > 3 AS staleness_warning
        FROM rate_observation o
        JOIN rate_source rs ON rs.id = o.source_id
        JOIN bank b ON b.id = rs.bank_id
        LEFT JOIN rate_category rc ON rc.id = o.category_id
        WHERE {_TRUSTED_WHERE}
        ORDER BY rs.id, o.source_currency_code, o.buying_rate DESC NULLS LAST
    """
    with conn.cursor() as cur:
        cur.execute(query)
        raw = cur.fetchall()

    matrix = {}
    for currency, bank_name, buying, selling, stale in raw:
        if major_only and currency not in MAJOR_CURRENCIES:
            continue
        if currency not in matrix:
            matrix[currency] = {}
        matrix[currency][bank_name] = {
            "buying": buying,
            "selling": selling,
            "staleness_warning": stale,
        }

    currencies = sorted(matrix.keys())
    banks = sorted({b for row in matrix.values() for b in row})
    best_buying = {
        c: max((matrix[c][b]["buying"] for b in matrix[c] if matrix[c][b]["buying"]), default=None)
        for c in currencies
    }

    return {
        "currencies": currencies,
        "banks": banks,
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
            ORDER BY o.effective_date DESC
        """)
        return [r[0] for r in cur.fetchall()]


def get_history_by_currency(conn, currency_code: str, effective_date=None) -> list:
    """
    History view: one best row per (bank, date) for a currency.
    If effective_date given, filter to that date only.
    Returns list of dicts with effective_date, bank_name, buying_rate, selling_rate,
    category, is_provisional. Ordered by effective_date DESC, buying_rate DESC.
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
    """Return {currencies: [...], banks: [{id, name}, ...]} for search datalist."""
    return {
        "currencies": get_available_currencies(conn),
        "banks": get_available_banks(conn),
    }


def get_available_currencies(conn) -> list:
    """Return sorted list of currency codes that have at least one trusted rate."""
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT DISTINCT o.source_currency_code
            FROM rate_observation o
            JOIN rate_source rs ON rs.id = o.source_id
            JOIN bank b ON b.id = rs.bank_id
            LEFT JOIN rate_category rc ON rc.id = o.category_id
            WHERE {_TRUSTED_WHERE}
            ORDER BY o.source_currency_code
        """)
        return [r[0] for r in cur.fetchall()]


def get_available_banks(conn) -> list:
    """Return list of {id, name} for banks with at least one trusted rate."""
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT DISTINCT rs.id, b.name
            FROM rate_observation o
            JOIN rate_source rs ON rs.id = o.source_id
            JOIN bank b ON b.id = rs.bank_id
            LEFT JOIN rate_category rc ON rc.id = o.category_id
            WHERE {_TRUSTED_WHERE}
            ORDER BY b.name
        """)
        return [{"id": r[0], "name": r[1]} for r in cur.fetchall()]


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
