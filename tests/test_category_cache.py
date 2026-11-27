import time
import pytest
from unittest.mock import MagicMock, patch

import pipeline.ingest as ingest_module


@pytest.fixture
def mock_conn():
    return MagicMock()


@pytest.fixture
def mock_category_map():
    return {'cash': 1, 'transactional': 2, 'weighted_average': 3}


@pytest.fixture(autouse=True)
def reset_cache():
    ingest_module._cache.reset()
    yield
    ingest_module._cache.reset()


class TestCategoryCache:

    def test_cache_miss_on_first_call(self, mock_conn, mock_category_map):
        with patch('pipeline.ingest.RateCategoryRepository') as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_active_categories_map.return_value = mock_category_map
            mock_repo_class.return_value = mock_repo

            result = ingest_module._load_category_map(mock_conn)

            assert mock_repo.get_active_categories_map.call_count == 1
            assert result == mock_category_map

    def test_cache_hit_on_second_call(self, mock_conn, mock_category_map):
        with patch('pipeline.ingest.RateCategoryRepository') as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_active_categories_map.return_value = mock_category_map
            mock_repo_class.return_value = mock_repo

            result1 = ingest_module._load_category_map(mock_conn)
            result2 = ingest_module._load_category_map(mock_conn)

            assert mock_repo.get_active_categories_map.call_count == 1
            assert result1 == result2 == mock_category_map

    def test_cache_expiry_after_ttl(self, mock_conn, mock_category_map):
        with patch('pipeline.ingest.RateCategoryRepository') as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_active_categories_map.return_value = mock_category_map
            mock_repo_class.return_value = mock_repo

            ingest_module._load_category_map(mock_conn)
            assert mock_repo.get_active_categories_map.call_count == 1

            # Force expiry by backdating the timestamp
            ingest_module._cache._timestamp = time.time() - (ingest_module.CATEGORY_CACHE_TTL + 1)

            ingest_module._load_category_map(mock_conn)
            assert mock_repo.get_active_categories_map.call_count == 2

    def test_cache_ttl_default_value(self):
        assert ingest_module.CATEGORY_CACHE_TTL == 300

    def test_multiple_calls_within_ttl(self, mock_conn, mock_category_map):
        with patch('pipeline.ingest.RateCategoryRepository') as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_active_categories_map.return_value = mock_category_map
            mock_repo_class.return_value = mock_repo

            for _ in range(11):
                result = ingest_module._load_category_map(mock_conn)
                assert result == mock_category_map

            assert mock_repo.get_active_categories_map.call_count == 1

    def test_cache_starts_empty(self, mock_conn, mock_category_map):
        with patch('pipeline.ingest.RateCategoryRepository') as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_active_categories_map.return_value = mock_category_map
            mock_repo_class.return_value = mock_repo

            # First call must always hit the DB
            ingest_module._load_category_map(mock_conn)
            assert mock_repo.get_active_categories_map.call_count == 1

    def test_cache_refreshes_timestamp_on_expiry(self, mock_conn, mock_category_map):
        with patch('pipeline.ingest.RateCategoryRepository') as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_active_categories_map.return_value = mock_category_map
            mock_repo_class.return_value = mock_repo

            ingest_module._load_category_map(mock_conn)
            first_ts = ingest_module._cache._timestamp

            ingest_module._cache._timestamp = time.time() - (ingest_module.CATEGORY_CACHE_TTL + 1)

            ingest_module._load_category_map(mock_conn)
            second_ts = ingest_module._cache._timestamp

            assert second_ts > first_ts


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
