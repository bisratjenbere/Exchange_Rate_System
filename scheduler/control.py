"""
scheduler/control.py — Collection pause/resume control.

Provides a database-backed mechanism to pause and resume collection execution.
Useful for maintenance windows, emergency stops, or manual intervention.

Usage:
    from scheduler.control import CollectionControl
    
    control = CollectionControl(conn)
    
    # Check if paused
    if control.is_paused():
        print("Collection is paused")
        return
    
    # Pause collection
    control.pause("Maintenance window", paused_by="admin")
    
    # Resume collection
    control.resume()
"""
from typing import Optional


class CollectionControl:
    """
    Control collection state (pause/resume).
    
    Uses a database table to coordinate pause state across multiple processes.
    This ensures that pausing collection affects all running instances.
    """
    
    def __init__(self, conn):
        """
        Initialize collection control.
        
        Args:
            conn: Database connection
        """
        self.conn = conn
        self._ensure_table()
    
    def _ensure_table(self):
        """Create control table if it doesn't exist."""
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
            
            # Insert initial row if table is empty
            cur.execute("""
                INSERT INTO collection_control (paused)
                SELECT FALSE
                WHERE NOT EXISTS (SELECT 1 FROM collection_control)
            """)
        
        self.conn.commit()
    
    def is_paused(self) -> bool:
        """
        Check if collection is paused.
        
        Returns:
            True if collection is paused, False otherwise
        """
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
        """
        Pause collection.
        
        Args:
            reason: Reason for pausing (for audit trail)
            paused_by: Who/what is pausing (default "system")
        """
        with self.conn.cursor() as cur:
            # Update or insert
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
                # No existing row, insert
                cur.execute("""
                    INSERT INTO collection_control 
                        (paused, paused_at, paused_by, reason)
                    VALUES (TRUE, NOW(), %s, %s)
                """, (paused_by, reason))
        
        self.conn.commit()
    
    def resume(self):
        """
        Resume collection.
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE collection_control
                SET paused = FALSE,
                    updated_at = NOW()
                WHERE id = (SELECT id FROM collection_control ORDER BY id DESC LIMIT 1)
            """)
        
        self.conn.commit()
    
    def get_pause_info(self) -> Optional[dict]:
        """
        Get detailed pause information.
        
        Returns:
            Dict with pause details if paused, None otherwise
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT paused, paused_at, paused_by, reason
                FROM collection_control
                ORDER BY id DESC
                LIMIT 1
            """)
            row = cur.fetchone()
            
            if not row or not row[0]:  # Not paused
                return None
            
            return {
                "paused": row[0],
                "paused_at": row[1],
                "paused_by": row[2],
                "reason": row[3]
            }
