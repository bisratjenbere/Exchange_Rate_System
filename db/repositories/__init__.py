"""
Data access layer - Repository pattern implementation.

Repositories centralize database queries and provide a clean interface
for business logic to interact with persistent data.
"""

from db.repositories.base_repository import BaseRepository
from db.repositories.rate_observation_repository import RateObservationRepository

__all__ = [
    'BaseRepository',
    'RateObservationRepository',
]
