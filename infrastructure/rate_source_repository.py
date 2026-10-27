from typing import Optional
from psycopg2.extensions import connection as Connection

class RateSourceRepository:

    def __init__(self, conn: Connection):
        self.conn = conn

    def get_by_id(self, source_id: int) -> Optional[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT id, adapter_key, source_url, ssl_verify,
                          schema_fingerprint, default_category,
                          consecutive_failures, last_failure_code
                   FROM rate_source
                   WHERE id = %s""",
                (source_id,)
            )
            row = cur.fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "adapter_key": row[1],
            "source_url": row[2],
            "ssl_verify": row[3],
            "schema_fingerprint": row[4],
            "default_category": row[5],
            "consecutive_failures": row[6],
            "last_failure_code": row[7],
        }

    def get_enabled_sources(self) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT id, adapter_key, source_url, ssl_verify,
                          schema_fingerprint, default_category,
                          consecutive_failures, last_failure_code
                   FROM rate_source
                   WHERE is_enabled = TRUE
                   ORDER BY id"""
            )
            rows = cur.fetchall()

        return [
            {
                "id": row[0],
                "adapter_key": row[1],
                "source_url": row[2],
                "ssl_verify": row[3],
                "schema_fingerprint": row[4],
                "default_category": row[5],
                "consecutive_failures": row[6],
                "last_failure_code": row[7],
            }
            for row in rows
        ]

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
