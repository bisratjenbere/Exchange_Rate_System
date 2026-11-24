"""
Repository for rate_category table operations.

Centralizes all queries related to rate categories.
"""

from typing import Dict
from .base_repository import BaseRepository


class RateCategoryRepository(BaseRepository):
    """Repository for rate_category table operations."""

    def get_active_categories_map(self) -> Dict[str, int]:
        """
        Get a mapping of active category codes to their IDs.

        Returns:
            Dictionary mapping category code to category ID
        """
        query = """
            SELECT code, id
            FROM rate_category
            WHERE is_active = TRUE
        """
        rows = self._fetch_all(query)
        return {row[0]: row[1] for row in rows}
