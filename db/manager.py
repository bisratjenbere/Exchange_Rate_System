import os
import logging
from contextlib import contextmanager
from typing import Optional
import psycopg2
from psycopg2 import pool

logger = logging.getLogger(__name__)

class DatabaseManager:

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
        if cls._initialized:
            logger.debug("DatabaseManager already initialized, skipping")
            return

        if min_conn < 1:
            raise ValueError("min_conn must be >= 1")
        if max_conn < min_conn:
            raise ValueError("max_conn must be >= min_conn")

        if dsn is None:
            dsn = os.environ.get("DATABASE_URL", "dbname=exchange_rates")

        dsn = cls._normalize_dsn(dsn)

        cls._config = {
            "dsn": dsn,
            "min_conn": min_conn,
            "max_conn": max_conn,
            "timeout": timeout,
        }

        try:
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
        if not cls._initialized:
            logger.warning("DatabaseManager not initialized, initializing with defaults")
            cls.initialize()

        if cls._pool is None:
            raise RuntimeError("Database pool is None (initialization may have failed)")

        conn = None
        try:
            conn = cls._pool.getconn()

            if conn is None:
                raise RuntimeError("Pool returned None connection")

            logger.debug(f"Connection acquired from pool (id: {id(conn)})")
            yield conn

        except pool.PoolError as e:
            logger.error(f"Pool error acquiring connection: {e}")
            raise

        finally:
            if conn is not None and cls._pool is not None:
                try:
                    cls._pool.putconn(conn)
                    logger.debug(f"Connection returned to pool (id: {id(conn)})")
                except pool.PoolError as e:
                    logger.error(f"Error returning connection to pool: {e}")

    @classmethod
    def get_pool_status(cls) -> dict:
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
        cls.close_all()

    @classmethod
    def _normalize_dsn(cls, dsn: str) -> str:
        if dsn.startswith("postgres://"):
            dsn = dsn.replace("postgres://", "postgresql://", 1)
            logger.debug("Normalized postgres:// to postgresql:// in DSN")

        return dsn
