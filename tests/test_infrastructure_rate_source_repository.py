"""
Unit tests for infrastructure.rate_source_repository module.

Tests the RateSourceRepository class including:
- get_by_id() with mock connection
- get_enabled_sources() listing
- update_last_success() SQL execution
- update_schema_fingerprint() SQL execution
- Parameterized query verification
- Dict structure verification
"""
import pytest
from unittest.mock import Mock, MagicMock, call
from infrastructure.rate_source_repository import RateSourceRepository


def create_mock_conn_and_cursor():
    """Helper to create properly mocked connection and cursor."""
    mock_conn = Mock()
    mock_cursor = MagicMock()
    # Mock the context manager properly
    mock_conn.cursor.return_value = MagicMock(
        __enter__=lambda self: mock_cursor,
        __exit__=Mock()
    )
    return mock_conn, mock_cursor


class TestRateSourceRepositoryGetById:
    """Test get_by_id() method."""
    
    def test_get_by_id_returns_dict(self):
        """get_by_id() should return dict with correct keys."""
        mock_conn, mock_cursor = create_mock_conn_and_cursor()
        
        # Mock database row
        mock_cursor.fetchone.return_value = (
            1,  # id
            "cbe_api",  # adapter_key
            "https://combanketh.et/api/rates",  # source_url
            True,  # ssl_verify
            "abc123fingerprint",  # schema_fingerprint
            "FOREX",  # default_category
            0,  # consecutive_failures
            None,  # last_failure_code
        )
        
        repo = RateSourceRepository(mock_conn)
        result = repo.get_by_id(1)
        
        assert result is not None
        assert result["id"] == 1
        assert result["adapter_key"] == "cbe_api"
        assert result["source_url"] == "https://combanketh.et/api/rates"
        assert result["ssl_verify"] is True
        assert result["schema_fingerprint"] == "abc123fingerprint"
        assert result["default_category"] == "FOREX"
        assert result["consecutive_failures"] == 0
        assert result["last_failure_code"] is None
    
    def test_get_by_id_not_found_returns_none(self):
        """get_by_id() should return None when source not found."""
        mock_conn, mock_cursor = create_mock_conn_and_cursor()
        mock_cursor.fetchone.return_value = None
        
        repo = RateSourceRepository(mock_conn)
        result = repo.get_by_id(999)
        
        assert result is None
    
    def test_get_by_id_uses_parameterized_query(self):
        """get_by_id() should use parameterized query for security."""
        mock_conn, mock_cursor = create_mock_conn_and_cursor()
        mock_cursor.fetchone.return_value = None
        
        repo = RateSourceRepository(mock_conn)
        repo.get_by_id(42)
        
        # Verify execute was called with parameterized query
        execute_call = mock_cursor.execute.call_args
        assert execute_call is not None
        sql = execute_call[0][0]
        params = execute_call[0][1]
        
        assert "%s" in sql  # Parameterized placeholder
        assert params == (42,)  # Parameter tuple


class TestRateSourceRepositoryGetEnabledSources:
    """Test get_enabled_sources() method."""
    
    def test_get_enabled_sources_returns_list(self):
        """get_enabled_sources() should return list of dicts."""
        mock_conn, mock_cursor = create_mock_conn_and_cursor()
        
        # Mock three sources
        mock_cursor.fetchall.return_value = [
            (1, "cbe_api", "https://cbe.et/api", True, "fp1", "FOREX", 0, None),
            (2, "dashen_html", "https://dashen.com", True, "fp2", "FOREX", 0, None),
            (3, "boa_html", "https://boa.com", False, "fp3", None, 2, "http_failure"),
        ]
        
        repo = RateSourceRepository(mock_conn)
        results = repo.get_enabled_sources()
        
        assert len(results) == 3
        assert results[0]["adapter_key"] == "cbe_api"
        assert results[1]["adapter_key"] == "dashen_html"
        assert results[2]["adapter_key"] == "boa_html"
        assert results[2]["consecutive_failures"] == 2
        assert results[2]["last_failure_code"] == "http_failure"
    
    def test_get_enabled_sources_empty_returns_empty_list(self):
        """get_enabled_sources() should return empty list when no sources."""
        mock_conn, mock_cursor = create_mock_conn_and_cursor()
        mock_cursor.fetchall.return_value = []
        
        repo = RateSourceRepository(mock_conn)
        results = repo.get_enabled_sources()
        
        assert results == []
    
    def test_get_enabled_sources_queries_enabled_only(self):
        """get_enabled_sources() should filter by is_enabled = TRUE."""
        mock_conn, mock_cursor = create_mock_conn_and_cursor()
        mock_cursor.fetchall.return_value = []
        
        repo = RateSourceRepository(mock_conn)
        repo.get_enabled_sources()
        
        # Verify SQL contains is_enabled filter
        execute_call = mock_cursor.execute.call_args
        sql = execute_call[0][0]
        
        assert "is_enabled = TRUE" in sql or "is_enabled=TRUE" in sql


class TestRateSourceRepositoryUpdateLastSuccess:
    """Test update_last_success() method."""
    
    def test_update_last_success_executes_update(self):
        """update_last_success() should execute UPDATE statement."""
        mock_conn, mock_cursor = create_mock_conn_and_cursor()
        
        repo = RateSourceRepository(mock_conn)
        repo.update_last_success(5)
        
        # Verify execute was called
        assert mock_cursor.execute.called
        execute_call = mock_cursor.execute.call_args
        sql = execute_call[0][0]
        params = execute_call[0][1]
        
        assert "UPDATE" in sql.upper()
        assert "rate_source" in sql
        assert "last_success_at" in sql
        assert params == (5,)
    
    def test_update_last_success_uses_parameterized_query(self):
        """update_last_success() should use parameterized query."""
        mock_conn, mock_cursor = create_mock_conn_and_cursor()
        
        repo = RateSourceRepository(mock_conn)
        repo.update_last_success(42)
        
        execute_call = mock_cursor.execute.call_args
        sql = execute_call[0][0]
        params = execute_call[0][1]
        
        assert "%s" in sql
        assert params == (42,)


class TestRateSourceRepositoryUpdateSchemaFingerprint:
    """Test update_schema_fingerprint() method."""
    
    def test_update_schema_fingerprint_executes_update(self):
        """update_schema_fingerprint() should execute UPDATE statement."""
        mock_conn, mock_cursor = create_mock_conn_and_cursor()
        
        repo = RateSourceRepository(mock_conn)
        repo.update_schema_fingerprint(3, "new_fingerprint_hash")
        
        assert mock_cursor.execute.called
        execute_call = mock_cursor.execute.call_args
        sql = execute_call[0][0]
        params = execute_call[0][1]
        
        assert "UPDATE" in sql.upper()
        assert "rate_source" in sql
        assert "schema_fingerprint" in sql
        assert params == ("new_fingerprint_hash", 3)
    
    def test_update_schema_fingerprint_uses_parameterized_query(self):
        """update_schema_fingerprint() should use parameterized query."""
        mock_conn, mock_cursor = create_mock_conn_and_cursor()
        
        repo = RateSourceRepository(mock_conn)
        repo.update_schema_fingerprint(10, "abc123def456")
        
        execute_call = mock_cursor.execute.call_args
        sql = execute_call[0][0]
        params = execute_call[0][1]
        
        # Should have two parameters
        assert "%s" in sql
        assert params == ("abc123def456", 10)


class TestRateSourceRepositoryDictStructure:
    """Test that returned dicts have correct structure."""
    
    def test_get_by_id_dict_has_all_keys(self):
        """get_by_id() dict should have all expected keys."""
        mock_conn, mock_cursor = create_mock_conn_and_cursor()
        
        mock_cursor.fetchone.return_value = (
            1, "key", "url", True, "fp", "cat", 0, None
        )
        
        repo = RateSourceRepository(mock_conn)
        result = repo.get_by_id(1)
        
        expected_keys = [
            "id",
            "adapter_key",
            "source_url",
            "ssl_verify",
            "schema_fingerprint",
            "default_category",
            "consecutive_failures",
            "last_failure_code",
        ]
        
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"
    
    def test_get_enabled_sources_dicts_have_all_keys(self):
        """get_enabled_sources() dicts should have all expected keys."""
        mock_conn, mock_cursor = create_mock_conn_and_cursor()
        
        mock_cursor.fetchall.return_value = [
            (1, "key", "url", True, "fp", "cat", 0, None),
        ]
        
        repo = RateSourceRepository(mock_conn)
        results = repo.get_enabled_sources()
        
        expected_keys = [
            "id",
            "adapter_key",
            "source_url",
            "ssl_verify",
            "schema_fingerprint",
            "default_category",
            "consecutive_failures",
            "last_failure_code",
        ]
        
        for key in expected_keys:
            assert key in results[0], f"Missing key: {key}"
