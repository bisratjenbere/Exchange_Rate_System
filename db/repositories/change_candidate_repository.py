"""
Repository for change_candidate table operations.

This repository centralizes SQL queries for the change_candidate table,
which tracks observations flagged for review due to anomalous rate changes.
"""

from datetime import datetime, timezone
from typing import Optional
from db.repositories.base_repository import BaseRepository


class ChangeCandidateRepository(BaseRepository):
    """Repository for change_candidate table operations."""
    
    def insert(
        self,
        observation_id: int,
        prior_version_id: int,
        source_id: int,
        status: str = 'open'
    ) -> int:
        """
        Insert a new change candidate.
        
        Args:
            observation_id: ID of the new observation flagged for review
            prior_version_id: ID of the prior observation being superseded
            source_id: ID of the rate source
            status: Initial status (default: 'open')
            
        Returns:
            ID of inserted change candidate
        """
        query = """
            INSERT INTO change_candidate
                (observation_id, prior_version_id, source_id, status)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """
        return self._execute_returning(query, (observation_id, prior_version_id, source_id, status))
    
    def get_by_id(self, candidate_id: int) -> Optional[dict]:
        """
        Get change candidate by ID.
        
        Args:
            candidate_id: Change candidate ID
            
        Returns:
            Dict with candidate data or None if not found
        """
        query = """
            SELECT 
                id, 
                observation_id, 
                prior_version_id, 
                source_id, 
                detected_at,
                status, 
                decision_reason, 
                decided_at, 
                decided_by
            FROM change_candidate
            WHERE id = %s
        """
        return self._fetch_one(query, (candidate_id,))
    
    def update_status(
        self,
        candidate_id: int,
        status: str,
        decision_reason: Optional[str] = None,
        decided_by: Optional[str] = None,
        decided_at: Optional[datetime] = None
    ) -> int:
        """
        Update change candidate status and decision info.
        
        Args:
            candidate_id: Change candidate ID
            status: New status
            decision_reason: Reason for decision
            decided_by: User or system making decision
            decided_at: Decision timestamp (defaults to now)
            
        Returns:
            Number of rows updated
        """
        if decided_at is None:
            decided_at = datetime.now(timezone.utc)
        
        query = """
            UPDATE change_candidate
            SET status = %s,
                decision_reason = %s,
                decided_at = %s,
                decided_by = %s
            WHERE id = %s
        """
        return self._execute(
            query,
            (status, decision_reason, decided_at, decided_by, candidate_id)
        )
    
    def dismiss_superseded_by_date(
        self,
        source_id: int,
        currency_code: str,
        category_id: Optional[int],
        effective_date,
        decided_at: Optional[datetime] = None,
        decided_by: str = 'system'
    ) -> int:
        """
        Dismiss change candidates superseded by a newer publication.
        
        When a newer rate is published, any pending candidates for older
        observations of the same currency/category should be dismissed.
        
        Args:
            source_id: Rate source ID
            currency_code: Currency code
            category_id: Category ID
            effective_date: Effective date of newer publication
            decided_at: Decision timestamp (defaults to now)
            decided_by: User or system (default: 'system')
            
        Returns:
            Number of candidates dismissed
        """
        if decided_at is None:
            decided_at = datetime.now(timezone.utc)
        
        query = """
            UPDATE change_candidate cc
            SET status = 'dismissed',
                decision_reason = 'superseded_by_newer_publication',
                decided_at = %s,
                decided_by = %s
            FROM rate_observation ro
            WHERE cc.observation_id = ro.id
              AND ro.source_id = %s
              AND ro.source_currency_code = %s
              AND ro.category_id IS NOT DISTINCT FROM %s
              AND cc.status = 'open'
              AND ro.effective_date < %s
        """
        return self._execute(
            query,
            (decided_at, decided_by, source_id, currency_code, category_id, effective_date)
        )
    
    def count_open_by_prior(self, prior_version_id: int) -> int:
        """
        Count open change candidates for a prior observation.
        
        Used to check if there are pending candidates before creating new ones.
        
        Args:
            prior_version_id: Prior observation ID
            
        Returns:
            Count of open candidates
        """
        query = """
            SELECT COUNT(*)
            FROM change_candidate
            WHERE prior_version_id = %s AND status = 'open'
        """
        result = self._fetch_one(query, (prior_version_id,))
        return result['count'] if result else 0
    
    def has_pending_for_logical_key(self, logical_key: str) -> bool:
        """
        Check if there are any pending candidates for a logical observation key.
        
        Used in trusted view queries to flag observations with pending reviews.
        
        Args:
            logical_key: Logical observation key
            
        Returns:
            True if pending candidates exist
        """
        query = """
            SELECT EXISTS (
                SELECT 1 
                FROM change_candidate cc
                JOIN rate_observation co ON co.id = cc.observation_id
                WHERE co.logical_observation_key = %s
                  AND cc.status = 'open'
            )
        """
        result = self._fetch_one(query, (logical_key,))
        return result['exists'] if result else False
