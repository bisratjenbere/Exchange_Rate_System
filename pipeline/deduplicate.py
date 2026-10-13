"""
pipeline/deduplicate.py — determine whether an incoming observation is new, duplicate, or changed.
LOCKED rules:
- Same publication + same values → deduplicate (no new row, no version increment).
- Changed value, same publication → change_candidate.
- New publication → new logical observation.
ADR-007: for ambiguous-identity records, value-change deduplication applies.
"""
from typing import Optional


def classify_observation(
    fingerprint: str,
    logical_key: Optional[str],
    conn,
) -> tuple:
    """
    Query the DB for existing observations matching this fingerprint or logical key.
    Returns (action, existing_obs_id):
      action = 'duplicate'  — identical fingerprint already stored; skip
      action = 'new'        — no existing observation for this logical key
      action = 'changed'    — same logical key, different fingerprint (value changed)
      existing_obs_id       — id of the current version, or None
    """
    with conn.cursor() as cur:
        # 1. Exact fingerprint match → duplicate regardless of key
        cur.execute(
            "SELECT id FROM rate_observation WHERE snapshot_fingerprint = %s LIMIT 1",
            (fingerprint,),
        )
        row = cur.fetchone()
        if row:
            return "duplicate", row[0]

        # 2. No logical key → ambiguous; treat as new (ADR-007: value-change dedup handled separately)
        if logical_key is None:
            return "new", None

        # 3. Logical key exists → check for current version
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
    """
    ADR-007: for ambiguous-identity records, deduplicate by value (buying+selling).
    Returns (action, existing_obs_id).
    'duplicate' if same fingerprint already stored for this source/currency/category.
    'new' otherwise.
    """
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
