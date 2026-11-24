"""
Base repository class with common patterns.

Provides reusable methods for all repositories.
"""

from typing import Optional, List, Dict, Any
from psycopg2.extensions import connection as Connection


class BaseRepository:
    """Base class for all repositories with common database operations."""
    
    def __init__(self, conn: Connection):
        """
        Initialize repository with database connection.
        
        Args:
            conn: PostgreSQL connection (must be managed by caller)
        """
        self.conn = conn
    
    def _fetch_one(self, query: str, params: tuple = None) -> Optional[tuple]:
        """
        Execute query and fetch one row.
        
        Args:
            query: SQL query string
            params: Query parameters
            
        Returns:
            Single row as tuple, or None if no results
        """
        with self.conn.cursor() as cur:
            cur.execute(query, params or ())
            return cur.fetchone()
    
    def _fetch_all(self, query: str, params: tuple = None) -> List[tuple]:
        """
        Execute query and fetch all rows.
        
        Args:
            query: SQL query string
            params: Query parameters
            
        Returns:
            List of rows as tuples
        """
        with self.conn.cursor() as cur:
            cur.execute(query, params or ())
            return cur.fetchall()
    
    def _execute(self, query: str, params: tuple = None) -> int:
        """
        Execute query and return affected row count.
        
        Args:
            query: SQL query string (INSERT, UPDATE, DELETE)
            params: Query parameters
            
        Returns:
            Number of rows affected
        """
        with self.conn.cursor() as cur:
            cur.execute(query, params or ())
            return cur.rowcount
    
    def _execute_returning(self, query: str, params: tuple = None) -> Any:
        """
        Execute query with RETURNING clause and fetch result.
        
        Args:
            query: SQL query with RETURNING clause
            params: Query parameters
            
        Returns:
            Value from RETURNING clause
        """
        with self.conn.cursor() as cur:
            cur.execute(query, params or ())
            row = cur.fetchone()
            return row[0] if row else None
    
    def _row_to_dict(self, row: tuple, columns: List[str]) -> Optional[Dict[str, Any]]:
        """
        Convert row tuple to dictionary.
        
        Args:
            row: Row tuple from query
            columns: List of column names
            
        Returns:
            Dictionary mapping column names to values, or None if row is None
        """
        if row is None:
            return None
        return dict(zip(columns, row))
