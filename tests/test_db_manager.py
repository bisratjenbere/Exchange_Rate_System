import pytest
import psycopg2
from db.manager import DatabaseManager

class TestDatabaseManagerInitialization:

    def setup_method(self):
        DatabaseManager.reset()

    def teardown_method(self):
        DatabaseManager.close_all()

    def test_initialize_with_defaults(self):
        DatabaseManager.initialize(dsn="dbname=exchange_rates_test")

        assert DatabaseManager._initialized
        assert DatabaseManager._pool is not None
        assert DatabaseManager._config["min_conn"] == 2
        assert DatabaseManager._config["max_conn"] == 10

    def test_initialize_with_custom_params(self):
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
        DatabaseManager.initialize(
            min_conn=2,
            max_conn=5,
            dsn="dbname=exchange_rates_test"
        )
        pool1 = DatabaseManager._pool

        DatabaseManager.initialize(
            min_conn=3,
            max_conn=8,
            dsn="dbname=exchange_rates_test"
        )
        pool2 = DatabaseManager._pool

        assert pool1 is pool2

    def test_initialize_invalid_params(self):
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
        with DatabaseManager.connection() as conn:
            assert conn is not None
            assert isinstance(conn, psycopg2.extensions.connection)

            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()
                assert result == (1,)

    def test_connection_auto_release(self):
        conn_id = None

        with DatabaseManager.connection() as conn:
            conn_id = id(conn)

        with DatabaseManager.connection() as conn2:
            assert id(conn2) == conn_id

    def test_connection_release_on_exception(self):
        conn_id = None
        try:
            with DatabaseManager.connection() as conn:
                conn_id = id(conn)
                raise ValueError("Test exception")
        except ValueError:
            pass

        with DatabaseManager.connection() as conn2:
            assert id(conn2) == conn_id

    def test_multiple_concurrent_connections(self):
        connections = []

        for _ in range(3):
            conn = DatabaseManager._pool.getconn()
            connections.append(conn)

        conn_ids = [id(c) for c in connections]
        assert len(set(conn_ids)) == 3

        for conn in connections:
            DatabaseManager._pool.putconn(conn)

    def test_lazy_initialization(self):
        DatabaseManager.reset()

        import os
        old_dsn = os.environ.get("DATABASE_URL")
        try:
            os.environ["DATABASE_URL"] = "dbname=exchange_rates_test"

            with DatabaseManager.connection() as conn:
                assert conn is not None
                assert DatabaseManager._initialized
        finally:
            if old_dsn is not None:
                os.environ["DATABASE_URL"] = old_dsn
            else:
                os.environ.pop("DATABASE_URL", None)

class TestDatabaseManagerDSN:

    def test_normalize_postgres_scheme(self):
        dsn = "postgres://user:pass@localhost/testdb"
        normalized = DatabaseManager._normalize_dsn(dsn)

        assert normalized == "postgresql://user:pass@localhost/testdb"

    def test_normalize_already_normalized(self):
        dsn = "postgresql://user:pass@localhost/testdb"
        normalized = DatabaseManager._normalize_dsn(dsn)

        assert normalized == dsn

    def test_normalize_simple_dsn(self):
        dsn = "dbname=exchange_rates"
        normalized = DatabaseManager._normalize_dsn(dsn)

        assert normalized == dsn

class TestDatabaseManagerPoolStatus:

    def teardown_method(self):
        DatabaseManager.close_all()

    def test_status_before_initialization(self):
        DatabaseManager.reset()

        status = DatabaseManager.get_pool_status()
        assert status["initialized"] is False
        assert status["min_conn"] == 0
        assert status["max_conn"] == 0

    def test_status_after_initialization(self):
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

    def test_close_all(self):
        DatabaseManager.initialize(dsn="dbname=exchange_rates_test")
        assert DatabaseManager._pool is not None

        DatabaseManager.close_all()
        assert DatabaseManager._pool is None
        assert DatabaseManager._initialized is False

    def test_close_all_idempotent(self):
        DatabaseManager.initialize(dsn="dbname=exchange_rates_test")
        DatabaseManager.close_all()
        DatabaseManager.close_all()

    def test_reset_for_testing(self):
        DatabaseManager.initialize(dsn="dbname=exchange_rates_test")

        with DatabaseManager.connection() as conn:
            pass

        DatabaseManager.reset()

        assert DatabaseManager._pool is None
        assert not DatabaseManager._initialized
