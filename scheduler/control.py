from typing import Optional
from db.repositories.base_repository import BaseRepository


class CollectionControl(BaseRepository):

    def __init__(self, conn):
        super().__init__(conn)
        self._ensure_row()

    def _ensure_row(self):
        self._execute("""
            INSERT INTO collection_control (paused)
            SELECT FALSE
            WHERE NOT EXISTS (SELECT 1 FROM collection_control)
        """)
        self.conn.commit()

    def is_paused(self) -> bool:
        row = self._fetch_one("""
            SELECT paused FROM collection_control
            ORDER BY id DESC LIMIT 1
        """)
        return row[0] if row else False

    def pause(self, reason: str, paused_by: str = "system"):
        affected = self._execute("""
            UPDATE collection_control
            SET paused = TRUE, paused_at = NOW(),
                paused_by = %s, reason = %s, updated_at = NOW()
            WHERE id = (SELECT id FROM collection_control ORDER BY id DESC LIMIT 1)
        """, (paused_by, reason))

        if affected == 0:
            self._execute("""
                INSERT INTO collection_control (paused, paused_at, paused_by, reason)
                VALUES (TRUE, NOW(), %s, %s)
            """, (paused_by, reason))

        self.conn.commit()

    def resume(self):
        self._execute("""
            UPDATE collection_control
            SET paused = FALSE, updated_at = NOW()
            WHERE id = (SELECT id FROM collection_control ORDER BY id DESC LIMIT 1)
        """)
        self.conn.commit()

    def get_pause_info(self) -> Optional[dict]:
        row = self._fetch_one("""
            SELECT paused, paused_at, paused_by, reason
            FROM collection_control
            ORDER BY id DESC LIMIT 1
        """)
        if not row or not row[0]:
            return None
        return {
            "paused": row[0],
            "paused_at": row[1],
            "paused_by": row[2],
            "reason": row[3],
        }
