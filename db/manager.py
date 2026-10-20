"""
Database connection manager with connection pooling.

Provides a centralized, thread-safe connection pool for efficient database access.
"""

import os
import logging
from contextlib import contextmanager
from typing import Optional
import psycopg2
from psycopg2 import pool

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Centralized database connection management with pooling.
    
    Provides thread-safe connection pooling using psycopg2.pool.ThreadedConnectionPool.
    Handles DSN normalization for compatibility with different PostgreSQL URI schemes.
    
    Usage:
        # Initialize pool (typically at application startup)
        DatabaseManager.initialize(min_conn=2, max_conn=10)
        
        # Get connection from pool
        with DatabaseManager.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM rate_source")
                rows = cur.fetchall()
        
        # Shutdown (typically at application exit)
        DatabaseManager.close_all()
    
    Thread Safety:
        All methods are thread-safe. Multiple threads can safely acquire
        connections from the pool concurrently.
    
    Testing:
        Use DatabaseManager.reset() to clear pool between tests.
        Mock connections can be injected for unit testing.
    """
    
    # Class-level attributes (singleton pattern)
    _pool: Optional[pool.ThreadedConnectionPool] = None
    _config: Optional[dict] = None
    _initialized: bool = False
    
    @classmethod
    def initialize(
        cls,
        min_conn: int = 2,
        max_conn: int = 10,
        dsn: Optional[str] = None,
        timeout: int = 30
    ) -> None:
        """
        Initialize the connection pool.
        
        Args:
            min_conn: Minimum number of connections to maintain in pool
            max_conn: Maximum number of connections allowed in pool
            dsn: Database connection string. If None, reads from DATABASE_URL env var
            timeout: Connection timeout in seconds
        
        Raises:
            psycopg2.OperationalError: If unable to connect to database
            ValueError: If min_conn > max_conn or invalid parameters
        
        Note:
            Safe to call multiple times - subsequent calls are no-ops if already initialized.
        """
        if cls._initialized:
            logger.debug("DatabaseManager already initialized, skipping")
            return
        
        if min_conn < 1:
            raise ValueError("min_conn must be >= 1")
        if max_conn < min_conn:
            raise ValueError("max_conn must be >= min_conn")
        
        # Get and normalize DSN
        if dsn is None:
            dsn = os.environ.get("DATABASE_URL", "dbname=exchange_rates")
        
        dsn = cls._normalize_dsn(dsn)
        
        # Store configuration
        cls._config = {
            "dsn": dsn,
            "min_conn": min_conn,
            "max_conn": max_conn,
            "timeout": timeout,
        }
        
        try:
            # Create connection pool
            cls._pool = pool.ThreadedConnectionPool(
                minconn=min_conn,
                maxconn=max_conn,
                dsn=dsn,
                connect_timeout=timeout
            )
            cls._initialized = True
            
            logger.info(
                f"Database connection pool initialized: "
                f"{min_conn}-{max_conn} connections, timeout={timeout}s"
            )
            
        except psycopg2.OperationalError as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise
    
    @classmethod
    @contextmanager
    def connection(cls):
        """
        Get a database connection from the pool.
        
        Yields:
            psycopg2.connection: Database connection from pool
        
        Raises:
            RuntimeError: If pool not initialized
            pool.PoolError: If connection acquisition failed
        
        Usage:
            with DatabaseManager.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
        
        Note:
            Connection is automatically returned to pool when context exits,
            even if an exception occurs.
        """
        # Lazy initialization if not already done
        if not cls._initialized:
            logger.warning("DatabaseManager not initialized, initializing with defaults")
            cls.initialize()
        
        if cls._pool is None:
            raise RuntimeError("Database pool is None (initialization may have failed)")
        
        conn = None
        try:
            # Get connection from pool (blocks if pool exhausted)
            conn = cls._pool.getconn()
            
            if conn is None:
                raise RuntimeError("Pool returned None connection")
            
            logger.debug(f"Connection acquired from pool (id: {id(conn)})")
            yield conn
            
        except pool.PoolError as e:
            logger.error(f"Pool error acquiring connection: {e}")
            raise
            
        finally:
            # Always return connection to pool
            if conn is not None and cls._pool is not None:
                try:
                    cls._pool.putconn(conn)
                    logger.debug(f"Connection returned to pool (id: {id(conn)})")
                except pool.PoolError as e:
                    logger.error(f"Error returning connection to pool: {e}")
    
    @classmethod
    def get_pool_status(cls) -> dict:
        """
        Get current connection pool status.
        
        Returns:
            dict with keys:
                - initialized: bool
                - min_conn: int
                - max_conn: int
                - config: dict
        
        Note:
            psycopg2.pool doesn't expose detailed connection stats.
        """
        if not cls._initialized or cls._pool is None:
            return {
                "initialized": False,
                "min_conn": 0,
                "max_conn": 0,
            }
        
        return {
            "initialized": True,
            "min_conn": cls._config["min_conn"],
            "max_conn": cls._config["max_conn"],
            "config": cls._config,
        }
    
    @classmethod
    def close_all(cls) -> None:
        """
        Close all connections in the pool and reset state.
        
        Should be called at application shutdown.
        Safe to call multiple times.
        """
        if cls._pool is not None:
            try:
                cls._pool.closeall()
                logger.info("All database connections closed")
            except Exception as e:
                logger.error(f"Error closing connection pool: {e}")
            finally:
                cls._pool = None
                cls._config = None
                cls._initialized = False
    
    @classmethod
    def reset(cls) -> None:
        """
        Reset the connection pool (for testing).
        
        Closes all connections and clears state.
        Typically used between test cases to ensure isolation.
        """
        cls.close_all()
    
    @classmethod
    def _normalize_dsn(cls, dsn: str) -> str:
        """
        Normalize DSN to handle different PostgreSQL URI schemes.
        
        Render.com provides DATABASE_URL with postgres:// scheme,
        but psycopg2 requires postgresql:// scheme.
        
        Args:
            dsn: Database connection string
        
        Returns:
            Normalized DSN string
        
        Examples:
            postgres://user:pass@host/db -> postgresql://user:pass@host/db
            postgresql://user:pass@host/db -> postgresql://user:pass@host/db
            dbname=exchange_rates -> dbname=exchange_rates
        """
        if dsn.startswith("postgres://"):
            dsn = dsn.replace("postgres://", "postgresql://", 1)
            logger.debug("Normalized postgres:// to postgresql:// in DSN")
        
        return dsn
