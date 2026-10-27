from typing import Optional

def classify_observation(
    fingerprint: str,
    logical_key: Optional[str],
    conn,
) -> tuple:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM rate_observation WHERE snapshot_fingerprint = %s LIMIT 1",
            (fingerprint,),
        )
        row = cur.fetchone()
        if row:
            return "duplicate", row[0]

        if logical_key is None:
            return "new", None

        cur.execute(
            """SELECT id FROM rate_observation
               WHERE logical_observation_key = %s AND is_current = TRUE
               LIMIT 1""",
            (logical_key,),
        )
        row = cur.fetchone()
        if row:
            return "changed", row[0]

        return "new", None

def classify_ambiguous_observation(
    fingerprint: str,
    source_id: int,
    source_currency_code: str,
    category: str,
    conn,
) -> tuple:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id FROM rate_observation
               WHERE snapshot_fingerprint = %s
                 AND source_id = %s
                 AND source_currency_code = %s
               LIMIT 1""",
            (fingerprint, source_id, source_currency_code),
        )
        row = cur.fetchone()
        if row:
            return "duplicate", row[0]
        return "new", None
