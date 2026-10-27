from typing import Optional

class CollectionControl:

    def __init__(self, conn):
        self.conn = conn
        self._ensure_table()

    def _ensure_table(self):
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS collection_control (
                    id SERIAL PRIMARY KEY,
                    paused BOOLEAN DEFAULT FALSE,
                    paused_at TIMESTAMPTZ,
                    paused_by TEXT,
                    reason TEXT,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            cur.execute("""
                INSERT INTO collection_control (paused)
                SELECT FALSE
                WHERE NOT EXISTS (SELECT 1 FROM collection_control)
            """)

        self.conn.commit()

    def is_paused(self) -> bool:
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT paused
                FROM collection_control
                ORDER BY id DESC
                LIMIT 1
            """)
            row = cur.fetchone()
            return row[0] if row else False

    def pause(self, reason: str, paused_by: str = "system"):
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE collection_control
                SET paused = TRUE,
                    paused_at = NOW(),
                    paused_by = %s,
                    reason = %s,
                    updated_at = NOW()
                WHERE id = (SELECT id FROM collection_control ORDER BY id DESC LIMIT 1)
            """, (paused_by, reason))

            if cur.rowcount == 0:
                cur.execute("""
                    INSERT INTO collection_control
                        (paused, paused_at, paused_by, reason)
                    VALUES (TRUE, NOW(), %s, %s)
                """, (paused_by, reason))

        self.conn.commit()

    def resume(self):
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE collection_control
                SET paused = FALSE,
                    updated_at = NOW()
                WHERE id = (SELECT id FROM collection_control ORDER BY id DESC LIMIT 1)
            """)

        self.conn.commit()

    def get_pause_info(self) -> Optional[dict]:
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT paused, paused_at, paused_by, reason
                FROM collection_control
                ORDER BY id DESC
                LIMIT 1
            """)
            row = cur.fetchone()

            if not row or not row[0]:
                return None

            return {
                "paused": row[0],
                "paused_at": row[1],
                "paused_by": row[2],
                "reason": row[3]
            }
