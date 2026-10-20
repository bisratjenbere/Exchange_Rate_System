"""
Unit tests for DatabaseManager.

Tests connection pooling, DSN normalization, and lifecycle management.
"""

import pytest
import psycopg2
from db.manager import DatabaseManager


class TestDatabaseManagerInitialization:
    """Test pool initialization."""
    
    def setup_method(self):
        """Reset pool before each test."""
        DatabaseManager.reset()
    
    def teardown_method(self):
        """Cleanup after each test."""
        DatabaseManager.close_all()
    
    def test_initialize_with_defaults(self):
        """Test default initialization parameters."""
        DatabaseManager.initialize(dsn="dbname=exchange_rates_test")
        
        assert DatabaseManager._initialized
        assert DatabaseManager._pool is not None
        assert DatabaseManager._config["min_conn"] == 2
        assert DatabaseManager._config["max_conn"] == 10
    
    def test_initialize_with_custom_params(self):
        """Test custom initialization parameters."""
        DatabaseManager.initialize(
            min_conn=3,
            max_conn=15,
            dsn="dbname=exchange_rates_test",
            timeout=60
        )
        
        status = DatabaseManager.get_pool_status()
        assert status["min_conn"] == 3
        assert status["max_conn"] == 15
        assert status["config"]["timeout"] == 60
    
    def test_initialize_idempotent(self):
        """Test multiple initialize calls are safe."""
        DatabaseManager.initialize(
            min_conn=2,
            max_conn=5,
            dsn="dbname=exchange_rates_test"
        )
        pool1 = DatabaseManager._pool
        
        # Should be no-op
        DatabaseManager.initialize(
            min_conn=3,
            max_conn=8,
            dsn="dbname=exchange_rates_test"
        )
        pool2 = DatabaseManager._pool
        
        assert pool1 is pool2  # Same pool instance
    
    def test_initialize_invalid_params(self):
        """Test validation of initialization parameters."""
        with pytest.raises(ValueError, match="min_conn must be >= 1"):
            DatabaseManager.initialize(
                min_conn=0,
                dsn="dbname=exchange_rates_test"
            )
        
        with pytest.raises(ValueError, match="max_conn must be >= min_conn"):
            DatabaseManager.initialize(
                min_conn=10,
                max_conn=5,
                dsn="dbname=exchange_rates_test"
            )


class TestDatabaseManagerConnections:
    """Test connection acquisition and release."""
    
    def setup_method(self):
        DatabaseManager.reset()
        DatabaseManager.initialize(
            min_conn=1,
            max_conn=3,
            dsn="dbname=exchange_rates_test"
        )
    
    def teardown_method(self):
        DatabaseManager.close_all()
    
    def test_connection_context_manager(self):
        """Test basic connection acquisition."""
        with DatabaseManager.connection() as conn:
            assert conn is not None
            assert isinstance(conn, psycopg2.extensions.connection)
            
            # Verify connection works
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()
                assert result == (1,)
    
    def test_connection_auto_release(self):
        """Test connection automatically returned to pool."""
        conn_id = None
        
        with DatabaseManager.connection() as conn:
            conn_id = id(conn)
        
        # Get another connection - should reuse the same one
        with DatabaseManager.connection() as conn2:
            assert id(conn2) == conn_id  # Same connection reused
    
    def test_connection_release_on_exception(self):
        """Test connection returned even if exception occurs."""
        conn_id = None
        try:
            with DatabaseManager.connection() as conn:
                conn_id = id(conn)
                raise ValueError("Test exception")
        except ValueError:
            pass
        
        # Connection should still be returned - verify by reusing
        with DatabaseManager.connection() as conn2:
            assert id(conn2) == conn_id
    
    def test_multiple_concurrent_connections(self):
        """Test pool handles multiple connections."""
        connections = []
        
        # Acquire multiple connections (within pool limit)
        for _ in range(3):
            conn = DatabaseManager._pool.getconn()
            connections.append(conn)
        
        # Verify all are different
        conn_ids = [id(c) for c in connections]
        assert len(set(conn_ids)) == 3
        
        # Return all to pool
        for conn in connections:
            DatabaseManager._pool.putconn(conn)
    
    def test_lazy_initialization(self):
        """Test pool auto-initializes on first connection."""
        DatabaseManager.reset()  # Clear initialization
        
        # Don't call initialize() - should auto-initialize with test DSN needed
        # We need to set the env var for this to work with test database
        import os
        old_dsn = os.environ.get("DATABASE_URL")
        try:
            os.environ["DATABASE_URL"] = "dbname=exchange_rates_test"
            
            with DatabaseManager.connection() as conn:
                assert conn is not None
                assert DatabaseManager._initialized
        finally:
            # Restore original DSN
            if old_dsn is not None:
                os.environ["DATABASE_URL"] = old_dsn
            else:
                os.environ.pop("DATABASE_URL", None)


class TestDatabaseManagerDSN:
    """Test DSN normalization."""
    
    def test_normalize_postgres_scheme(self):
        """Test postgres:// converted to postgresql://."""
        dsn = "postgres://user:pass@localhost/testdb"
        normalized = DatabaseManager._normalize_dsn(dsn)
        
        assert normalized == "postgresql://user:pass@localhost/testdb"
    
    def test_normalize_already_normalized(self):
        """Test postgresql:// left unchanged."""
        dsn = "postgresql://user:pass@localhost/testdb"
        normalized = DatabaseManager._normalize_dsn(dsn)
        
        assert normalized == dsn
    
    def test_normalize_simple_dsn(self):
        """Test simple DSN left unchanged."""
        dsn = "dbname=exchange_rates"
        normalized = DatabaseManager._normalize_dsn(dsn)
        
        assert normalized == dsn


class TestDatabaseManagerPoolStatus:
    """Test pool status reporting."""
    
    def teardown_method(self):
        DatabaseManager.close_all()
    
    def test_status_before_initialization(self):
        """Test status when pool not initialized."""
        DatabaseManager.reset()
        
        status = DatabaseManager.get_pool_status()
        assert status["initialized"] is False
        assert status["min_conn"] == 0
        assert status["max_conn"] == 0
    
    def test_status_after_initialization(self):
        """Test status when pool initialized."""
        DatabaseManager.initialize(
            min_conn=3,
            max_conn=12,
            dsn="dbname=exchange_rates_test"
        )
        
        status = DatabaseManager.get_pool_status()
        assert status["initialized"] is True
        assert status["min_conn"] == 3
        assert status["max_conn"] == 12


class TestDatabaseManagerCleanup:
    """Test cleanup and shutdown."""
    
    def test_close_all(self):
        """Test closing all connections."""
        DatabaseManager.initialize(dsn="dbname=exchange_rates_test")
        assert DatabaseManager._pool is not None
        
        DatabaseManager.close_all()
        assert DatabaseManager._pool is None
        assert DatabaseManager._initialized is False
    
    def test_close_all_idempotent(self):
        """Test close_all safe to call multiple times."""
        DatabaseManager.initialize(dsn="dbname=exchange_rates_test")
        DatabaseManager.close_all()
        DatabaseManager.close_all()  # Should not raise
    
    def test_reset_for_testing(self):
        """Test reset() clears state for testing."""
        DatabaseManager.initialize(dsn="dbname=exchange_rates_test")
        
        with DatabaseManager.connection() as conn:
            pass
        
        DatabaseManager.reset()
        
        assert DatabaseManager._pool is None
        assert not DatabaseManager._initialized
