"""
Tests for category map caching (Phase 3E optimization).
"""
import time
import pytest
from unittest.mock import MagicMock, patch

# Import the cache module
import pipeline.ingest as ingest_module


@pytest.fixture
def mock_conn():
    """Mock database connection."""
    return MagicMock()


@pytest.fixture
def mock_category_map():
    """Sample category map data."""
    return {
        'BUYING': 1,
        'SELLING': 2,
        'MEAN': 3,
    }


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset cache before each test."""
    ingest_module._category_map_cache = None
    ingest_module._cache_timestamp = None
    yield
    # Clean up after test
    ingest_module._category_map_cache = None
    ingest_module._cache_timestamp = None


class TestCategoryCache:
    """Test category map caching behavior."""

    def test_cache_miss_on_first_call(self, mock_conn, mock_category_map):
        """First call should fetch from database (cache miss)."""
        with patch('pipeline.ingest.RateCategoryRepository') as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_active_categories_map.return_value = mock_category_map
            mock_repo_class.return_value = mock_repo
            
            result = ingest_module._load_category_map(mock_conn)
            
            # Should have called repository
            assert mock_repo.get_active_categories_map.called
            assert result == mock_category_map
            
            # Cache should be populated
            assert ingest_module._category_map_cache == mock_category_map
            assert ingest_module._cache_timestamp is not None

    def test_cache_hit_on_second_call(self, mock_conn, mock_category_map):
        """Second call within TTL should use cache (cache hit)."""
        with patch('pipeline.ingest.RateCategoryRepository') as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_active_categories_map.return_value = mock_category_map
            mock_repo_class.return_value = mock_repo
            
            # First call - cache miss
            result1 = ingest_module._load_category_map(mock_conn)
            call_count_after_first = mock_repo.get_active_categories_map.call_count
            
            # Second call - should be cache hit
            result2 = ingest_module._load_category_map(mock_conn)
            call_count_after_second = mock_repo.get_active_categories_map.call_count
            
            # Repository should only be called once (first time)
            assert call_count_after_first == 1
            assert call_count_after_second == 1  # No additional call
            assert result1 == result2 == mock_category_map

    def test_cache_expiry_after_ttl(self, mock_conn, mock_category_map):
        """Cache should expire after TTL and fetch fresh data."""
        with patch('pipeline.ingest.RateCategoryRepository') as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_active_categories_map.return_value = mock_category_map
            mock_repo_class.return_value = mock_repo
            
            # First call - cache miss
            result1 = ingest_module._load_category_map(mock_conn)
            assert mock_repo.get_active_categories_map.call_count == 1
            
            # Simulate time passing beyond TTL
            original_ttl = ingest_module.CATEGORY_CACHE_TTL
            ingest_module.CATEGORY_CACHE_TTL = 0.1  # 100ms for testing
            time.sleep(0.15)  # Wait for cache to expire
            
            # Second call - should be cache miss due to expiry
            result2 = ingest_module._load_category_map(mock_conn)
            assert mock_repo.get_active_categories_map.call_count == 2
            
            # Restore original TTL
            ingest_module.CATEGORY_CACHE_TTL = original_ttl

    def test_cache_ttl_default_value(self):
        """Verify cache TTL is set to 5 minutes (300 seconds)."""
        assert ingest_module.CATEGORY_CACHE_TTL == 300

    def test_multiple_calls_within_ttl(self, mock_conn, mock_category_map):
        """Multiple calls within TTL should all be cache hits."""
        with patch('pipeline.ingest.RateCategoryRepository') as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_active_categories_map.return_value = mock_category_map
            mock_repo_class.return_value = mock_repo
            
            # First call
            ingest_module._load_category_map(mock_conn)
            
            # Multiple subsequent calls
            for _ in range(10):
                result = ingest_module._load_category_map(mock_conn)
                assert result == mock_category_map
            
            # Repository should only be called once (first call)
            assert mock_repo.get_active_categories_map.call_count == 1

    def test_cache_initialization(self):
        """Verify cache variables are initialized correctly."""
        # Cache should start as None
        assert ingest_module._category_map_cache is None
        assert ingest_module._cache_timestamp is None

    def test_cache_timestamp_updates_on_refresh(self, mock_conn, mock_category_map):
        """Timestamp should update when cache is refreshed."""
        with patch('pipeline.ingest.RateCategoryRepository') as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_active_categories_map.return_value = mock_category_map
            mock_repo_class.return_value = mock_repo
            
            # First call
            ingest_module._load_category_map(mock_conn)
            first_timestamp = ingest_module._cache_timestamp
            
            # Force expiry and call again
            ingest_module._cache_timestamp = time.time() - 400  # 400 seconds ago
            
            ingest_module._load_category_map(mock_conn)
            second_timestamp = ingest_module._cache_timestamp
            
            # Timestamp should have been updated
            assert second_timestamp > first_timestamp


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
