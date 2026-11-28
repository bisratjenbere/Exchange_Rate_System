from typing import Optional
from psycopg2.extensions import connection as Connection

from domain.source import RateSource


class RateSourceRepository:

    def __init__(self, conn: Connection):
        self.conn = conn

    def get_by_id(self, source_id: int) -> Optional[RateSource]:
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT id, adapter_key, source_url, ssl_verify,
                          schema_fingerprint, default_category,
                          consecutive_failures, last_failure_code,
                          last_failure_at, last_success_at, adapter_config,
                          is_enabled
                   FROM rate_source
                   WHERE id = %s""",
                (source_id,)
            )
            row = cur.fetchone()

        if not row:
            return None

        return self._row_to_source(row)

    def get_enabled_sources(self) -> list[RateSource]:
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT id, adapter_key, source_url, ssl_verify,
                          schema_fingerprint, default_category,
                          consecutive_failures, last_failure_code,
                          last_failure_at, last_success_at, adapter_config,
                          is_enabled
                   FROM rate_source
                   WHERE is_enabled = TRUE
                   ORDER BY id"""
            )
            rows = cur.fetchall()

        return [self._row_to_source(row) for row in rows]

    def get_all_sources(self) -> list[RateSource]:
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT id, adapter_key, source_url, ssl_verify,
                          schema_fingerprint, default_category,
                          consecutive_failures, last_failure_code,
                          last_failure_at, last_success_at, adapter_config,
                          is_enabled
                   FROM rate_source
                   ORDER BY id"""
            )
            rows = cur.fetchall()

        return [self._row_to_source(row) for row in rows]

    def update_last_success(self, source_id: int) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE rate_source SET last_success_at = now() WHERE id = %s",
                (source_id,)
            )

    def update_schema_fingerprint(self, source_id: int, fingerprint: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE rate_source SET schema_fingerprint = %s WHERE id = %s",
                (fingerprint, source_id)
            )

    def reset_failure_counter(self, source_id: int) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """UPDATE rate_source
                   SET consecutive_failures = 0, last_failure_code = NULL
                   WHERE id = %s""",
                (source_id,),
            )

    def increment_failure_counter(self, source_id: int, error_code: str) -> tuple:
        """
        Increment consecutive_failures and return (consecutive, alert_sent_at).
        Returns (0, None) if source not found.
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """UPDATE rate_source
                   SET consecutive_failures = consecutive_failures + 1,
                       last_failure_at = now(),
                       last_failure_code = %s
                   WHERE id = %s
                   RETURNING consecutive_failures, alert_sent_at""",
                (error_code, source_id),
            )
            row = cur.fetchone()
            return row if row else (0, None)

    def write_alert(self, source_id: int, error_code: str, error_summary: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO source_alert (source_id, error_code, summary, created_at)
                   VALUES (%s, %s, %s, now())""",
                (source_id, error_code, (error_summary or "")[:500]),
            )
            cur.execute(
                "UPDATE rate_source SET alert_sent_at = now() WHERE id = %s",
                (source_id,),
            )

    @staticmethod
    def _row_to_source(row) -> RateSource:
        return RateSource(
            id=row[0],
            adapter_key=row[1],
            source_url=row[2],
            ssl_verify=row[3],
            schema_fingerprint=row[4],
            default_category=row[5],
            consecutive_failures=row[6] or 0,
            last_failure_code=row[7],
            last_failure_at=row[8] if len(row) > 8 else None,
            last_success_at=row[9] if len(row) > 9 else None,
            adapter_config=row[10] if len(row) > 10 else None,
            is_enabled=row[11] if len(row) > 11 else True,
        )
