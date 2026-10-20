"""
Rate Source Repository for centralized database operations.

This module provides the Repository Pattern for the rate_source table,
centralizing all SQL queries and providing a clean API for database
operations.
"""
from typing import Optional
from psycopg2.extensions import connection as Connection


class RateSourceRepository:
    """
    Repository pattern for rate_source table operations.
    
    Centralizes all SQL queries for the rate_source table, providing
    a clean API for database operations. Replaces inline SQL scattered
    throughout scheduler/runner.py.
    
    Benefits:
        - Single Responsibility: All rate_source queries in one place
        - Testability: Can mock repository for unit tests
        - Consistency: All queries return same dict structure
        - Security: Parameterized queries prevent SQL injection
        - Maintainability: Schema changes only require updates here
    
    Example:
        >>> repo = RateSourceRepository(conn)
        >>> source = repo.get_by_id(1)
        >>> print(source['adapter_key'])
        'cbe_api'
        
        >>> sources = repo.get_enabled_sources()
        >>> for source in sources:
        ...     print(source['adapter_key'])
        
        >>> repo.update_last_success(1)
        >>> repo.update_schema_fingerprint(1, "abc123...")
    """
    
    def __init__(self, conn: Connection):
        """
        Initialize repository with database connection.
        
        Args:
            conn: PostgreSQL connection (psycopg2)
        """
        self.conn = conn
    
    def get_by_id(self, source_id: int) -> Optional[dict]:
        """
        Get rate_source by ID.
        
        Returns all columns needed by the scheduler including:
        - Basic info: id, adapter_key, source_url, ssl_verify
        - Schema: schema_fingerprint
        - Category: default_category
        - Failure tracking: consecutive_failures, last_failure_code
        
        Args:
            source_id: Primary key
        
        Returns:
            Dict with keys: id, adapter_key, source_url, ssl_verify,
                           schema_fingerprint, default_category,
                           consecutive_failures, last_failure_code
            None if not found
        
        Example:
            >>> source = repo.get_by_id(1)
            >>> if source:
            ...     print(f"Adapter: {source['adapter_key']}")
            ...     print(f"URL: {source['source_url']}")
        """
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
        """
        Get all enabled rate sources.
        
        Returns only sources where is_enabled = TRUE, ordered by ID.
        
        Returns:
            List of dicts with same keys as get_by_id()
        
        Example:
            >>> sources = repo.get_enabled_sources()
            >>> print(f"Found {len(sources)} enabled sources")
            >>> for source in sources:
            ...     print(f"  {source['adapter_key']}")
        """
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
        """
        Update last_success_at timestamp to now().
        
        Called after a successful collection run to record when
        the source last successfully provided data.
        
        Args:
            source_id: Primary key
        
        Example:
            >>> repo.update_last_success(1)
            >>> conn.commit()
        """
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE rate_source SET last_success_at = now() WHERE id = %s",
                (source_id,)
            )
    
    def update_schema_fingerprint(self, source_id: int, fingerprint: str) -> None:
        """
        Update schema_fingerprint for a source.
        
        Called when the adapter's schema fingerprint changes to store
        the new fingerprint hash (SHA-256 of schema structure).
        
        Args:
            source_id: Primary key
            fingerprint: SHA-256 hash of schema structure
        
        Example:
            >>> new_fp = adapter.schema_fingerprint(raw_html)
            >>> repo.update_schema_fingerprint(1, new_fp)
            >>> conn.commit()
        """
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE rate_source SET schema_fingerprint = %s WHERE id = %s",
                (fingerprint, source_id)
            )
