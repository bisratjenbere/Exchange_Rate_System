"""
Repository for rate_observation table operations.

Centralizes all database queries for rate observations, providing a clean
interface for business logic while hiding SQL implementation details.
"""

import json
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from decimal import Decimal

from db.repositories.base_repository import BaseRepository
from domain.records import AdapterRecord
from domain.enums import ValidationStatus, IdentityStatus, ChangeReviewStatus
from domain.exceptions import StaleObservationError
from pipeline.fingerprint import FINGERPRINT_VERSION
from pipeline.normalize import normalize_currency_code


class RateObservationRepository(BaseRepository):
    """Handles all rate_observation table operations."""
    
    # INSERT statement template with named parameters
    _INSERT_SQL = """
        INSERT INTO rate_observation (
            source_id, collection_run_id, category_id,
            currency_code, source_currency_code, currency_name,
            buying_rate, selling_rate, source_rate_text, source_excerpt,
            quote_currency_code, unit_multiplier,
            effective_date, effective_date_basis,
            fetched_at, snapshot_fingerprint, fingerprint_version,
            version_number, is_current, identity_status,
            validation_status, validation_messages,
            change_review_status, logical_observation_key,
            supersedes_id, is_fallback
        ) VALUES (
            %(source_id)s, %(run_id)s, %(category_id)s,
            %(currency_code)s, %(source_currency_code)s, %(currency_name)s,
            %(buying_rate)s, %(selling_rate)s, %(source_rate_text)s, %(source_excerpt)s,
            %(quote_currency_code)s, %(unit_multiplier)s,
            %(effective_date)s, %(effective_date_basis)s,
            %(fetched_at)s, %(fingerprint)s, %(fingerprint_version)s,
            %(version_number)s, %(is_current)s, %(identity_status)s,
            %(validation_status)s, %(validation_messages)s,
            %(change_review_status)s, %(logical_key)s,
            %(supersedes_id)s, %(is_fallback)s
        ) RETURNING id
    """
    
    def insert(
        self,
        record: AdapterRecord,
        source_id: int,
        run_id: int,
        category_id: Optional[int],
        fingerprint: str,
        logical_key: Optional[str],
        identity_status: IdentityStatus,
        validation_status: ValidationStatus,
        validation_messages: list,
        fetched_at: datetime,
        version_number: Optional[int],
        is_current: bool,
        change_review_status: ChangeReviewStatus = ChangeReviewStatus.NOT_REQUIRED,
        supersedes_id: Optional[int] = None,
        is_fallback: bool = False,
    ) -> int:
        """
        Insert new rate observation.
        
        Args:
            record: Adapter record with rate data
            source_id: Rate source ID
            run_id: Collection run ID
            category_id: Category ID (can be None for UNKNOWN)
            fingerprint: Computed fingerprint
            logical_key: Logical observation key
            identity_status: Identity classification
            validation_status: Validation result
            validation_messages: Validation messages list
            fetched_at: Timestamp when data was fetched
            version_number: Version number (for versioned observations)
            is_current: Whether this is the current observation
            change_review_status: Review status
            supersedes_id: ID of observation this supersedes
            is_fallback: Whether this is fallback data
            
        Returns:
            ID of inserted observation
        """
        params = {
            'source_id': source_id,
            'run_id': run_id,
            'category_id': category_id,
            'currency_code': normalize_currency_code(record.source_currency_code),
            'source_currency_code': record.source_currency_code,
            'currency_name': record.currency_name,
            'buying_rate': record.buying_rate,
            'selling_rate': record.selling_rate,
            'source_rate_text': record.source_rate_text,
            'source_excerpt': json.dumps(record.raw_excerpt) if record.raw_excerpt else None,
            'quote_currency_code': record.quote_currency_code,
            'unit_multiplier': record.unit_multiplier,
            'effective_date': record.effective_date,
            'effective_date_basis': record.effective_date_basis,
            'fetched_at': fetched_at,
            'fingerprint': fingerprint,
            'fingerprint_version': FINGERPRINT_VERSION,
            'version_number': version_number,
            'is_current': is_current,
            'identity_status': identity_status.value,
            'validation_status': validation_status.value,
            'validation_messages': json.dumps(validation_messages) if validation_messages else None,
            'change_review_status': change_review_status.value,
            'logical_key': logical_key,
            'supersedes_id': supersedes_id,
            'is_fallback': is_fallback,
        }
        
        return self._execute_returning(self._INSERT_SQL, params)
    
    def get_by_id(self, observation_id: int) -> Optional[Dict[str, Any]]:
        """
        Get observation by ID.
        
        Args:
            observation_id: Observation ID
            
        Returns:
            Dictionary with observation data, or None if not found
        """
        query = """
            SELECT id, source_id, collection_run_id, category_id,
                   currency_code, source_currency_code, currency_name,
                   buying_rate, selling_rate, source_rate_text,
                   effective_date, effective_date_basis,
                   fetched_at, snapshot_fingerprint, fingerprint_version,
                   version_number, is_current, identity_status,
                   validation_status, change_review_status,
                   logical_observation_key, supersedes_id, is_fallback
            FROM rate_observation
            WHERE id = %s
        """
        
        row = self._fetch_one(query, (observation_id,))
        
        if row is None:
            return None
        
        columns = [
            'id', 'source_id', 'collection_run_id', 'category_id',
            'currency_code', 'source_currency_code', 'currency_name',
            'buying_rate', 'selling_rate', 'source_rate_text',
            'effective_date', 'effective_date_basis',
            'fetched_at', 'snapshot_fingerprint', 'fingerprint_version',
            'version_number', 'is_current', 'identity_status',
            'validation_status', 'change_review_status',
            'logical_observation_key', 'supersedes_id', 'is_fallback'
        ]
        
        return self._row_to_dict(row, columns)
    
    def get_active_observation(
        self,
        source_id: int,
        currency_code: str,
        category_id: Optional[int]
    ) -> Optional[Dict[str, Any]]:
        """
        Get current active observation for given criteria.
        
        Args:
            source_id: Rate source ID
            currency_code: Currency code (e.g., "USD")
            category_id: Category ID (can be None)
            
        Returns:
            Dictionary with observation data, or None if no current observation
        """
        query = """
            SELECT id, effective_date, is_fallback, buying_rate, selling_rate
            FROM rate_observation
            WHERE source_id = %s
              AND source_currency_code = %s
              AND category_id IS NOT DISTINCT FROM %s
              AND is_current = TRUE
            LIMIT 1
        """
        
        row = self._fetch_one(query, (source_id, currency_code, category_id))
        
        if row is None:
            return None
        
        return self._row_to_dict(row, ['id', 'effective_date', 'is_fallback', 'buying_rate', 'selling_rate'])
    
    def retire_current_observations(
        self,
        source_id: int,
        currency_code: str,
        category_id: Optional[int]
    ) -> int:
        """
        Mark all current observations as not current for given criteria.
        
        Args:
            source_id: Rate source ID
            currency_code: Currency code
            category_id: Category ID (can be None)
            
        Returns:
            Number of observations retired
        """
        query = """
            UPDATE rate_observation
            SET is_current = FALSE
            WHERE source_id = %s
              AND source_currency_code = %s
              AND category_id IS NOT DISTINCT FROM %s
              AND is_current = TRUE
        """
        
        return self._execute(query, (source_id, currency_code, category_id))
    
    def retire_prior_fallback_observations(
        self,
        source_id: int,
        currency_code: str,
        category_id: Optional[int],
        effective_date: date,
        is_fallback: bool = False
    ) -> int:
        """
        Retire fallback observations with older effective dates.
        
        If is_fallback=True (fallback caller): only retires is_fallback=TRUE rows.
        If is_fallback=False (non-fallback caller): retires fallback rows AND
            same-category non-fallback rows with older effective_date.
        
        Args:
            source_id: Rate source ID
            currency_code: Currency code
            category_id: Category ID
            effective_date: Effective date threshold
            is_fallback: Whether caller is fallback path
            
        Returns:
            Number of observations retired
        """
        if effective_date is None:
            return 0
        
        if is_fallback:
            # Fallback caller: retire only prior fallback rows
            query = """
                UPDATE rate_observation
                SET is_current = FALSE
                WHERE source_id = %s
                  AND source_currency_code = %s
                  AND is_current = TRUE
                  AND is_fallback = TRUE
                  AND (effective_date IS NULL OR effective_date < %s)
            """
            params = (source_id, currency_code, effective_date)
        else:
            # Non-fallback caller: retire fallback rows (all categories) + same-category non-fallback
            query = """
                UPDATE rate_observation
                SET is_current = FALSE
                WHERE source_id = %s
                  AND source_currency_code = %s
                  AND is_current = TRUE
                  AND (is_fallback = TRUE OR (category_id IS NOT DISTINCT FROM %s AND effective_date < %s))
            """
            params = (source_id, currency_code, category_id, effective_date)
        
        return self._execute(query, params)
    
    def expire_stale_fallback_current(self, source_id: int, fallback_ttl_days: int) -> int:
        """
        Expire stale fallback observations for a source.
        
        Two expiry rules:
        1. Fallback observations older than fallback_ttl_days
        2. Any observation older than 7 days if newer (3-day) observations exist
        
        Args:
            source_id: Rate source ID
            fallback_ttl_days: Number of days before fallback expires
            
        Returns:
            Total number of observations expired
        """
        expired_count = 0
        
        # Rule 1: Expire old fallback observations
        query1 = """
            UPDATE rate_observation
            SET is_current = FALSE
            WHERE source_id = %s
              AND is_fallback = TRUE
              AND is_current = TRUE
              AND effective_date < CURRENT_DATE - %s
        """
        expired_count += self._execute(query1, (source_id, fallback_ttl_days))
        
        # Rule 2: Expire any old observation if fresh ones exist
        query2 = """
            UPDATE rate_observation
            SET is_current = FALSE
            WHERE source_id = %s
              AND is_current = TRUE
              AND effective_date < CURRENT_DATE - INTERVAL '7 days'
              AND EXISTS (
                  SELECT 1 FROM rate_observation
                  WHERE source_id = %s
                    AND is_current = TRUE
                    AND effective_date >= CURRENT_DATE - INTERVAL '3 days'
              )
        """
        expired_count += self._execute(query2, (source_id, source_id))
        
        return expired_count
    
    def promote_observation(
        self,
        observation_id: int,
        change_review_status: Optional[str] = None
    ) -> None:
        """
        Mark observation as current, optionally updating review status.
        
        Args:
            observation_id: Observation ID to promote
            change_review_status: Optional review status to set
        """
        if change_review_status:
            query = """
                UPDATE rate_observation
                SET is_current = TRUE, change_review_status = %s
                WHERE id = %s
            """
            self._execute(query, (change_review_status, observation_id))
        else:
            query = """
                UPDATE rate_observation
                SET is_current = TRUE
                WHERE id = %s
            """
            self._execute(query, (observation_id,))
    
    def demote_observation(
        self,
        observation_id: int,
        change_review_status: Optional[str] = None
    ) -> None:
        """
        Mark observation as not current, optionally updating review status.
        
        Args:
            observation_id: Observation ID to demote
            change_review_status: Optional review status to set
        """
        if change_review_status:
            query = """
                UPDATE rate_observation
                SET is_current = FALSE, change_review_status = %s
                WHERE id = %s
            """
            self._execute(query, (change_review_status, observation_id))
        else:
            query = """
                UPDATE rate_observation
                SET is_current = FALSE
                WHERE id = %s
            """
            self._execute(query, (observation_id,))
    
    def promote_fallback_to_non_fallback(self, observation_id: int) -> int:
        """
        Promote existing fallback observation to non-fallback and current.
        
        Used when duplicate non-fallback data arrives for existing fallback observation.
        
        Args:
            observation_id: ID of fallback observation to promote
            
        Returns:
            Number of rows updated (0 or 1)
        """
        query = """
            UPDATE rate_observation
            SET is_fallback = FALSE, is_current = TRUE
            WHERE id = %s AND is_fallback = TRUE
        """
        
        return self._execute(query, (observation_id,))
    
    def get_next_version_number(self, logical_key: str) -> int:
        """
        Get next version number for a logical observation.
        
        Args:
            logical_key: Logical observation key
            
        Returns:
            Next version number (current max + 1)
        """
        query = """
            SELECT COALESCE(MAX(version_number), 0)
            FROM rate_observation
            WHERE logical_observation_key = %s
              AND version_number IS NOT NULL
        """
        
        row = self._fetch_one(query, (logical_key,))
        return (row[0] if row else 0) + 1
    
    def lock_and_get_version(self, observation_id: int, logical_key: str) -> int:
        """
        Lock observation and get its version number for correction.
        
        Args:
            observation_id: Observation ID to lock
            logical_key: Expected logical key (for validation)
            
        Returns:
            Version number of locked observation
            
        Raises:
            StaleObservationError: If observation not found or already superseded
            ValueError: If logical key doesn't match
        """
        query = """
            SELECT id, logical_observation_key, version_number
            FROM rate_observation
            WHERE id = %s
            FOR UPDATE
        """
        
        row = self._fetch_one(query, (observation_id,))
        
        if row is None:
            raise StaleObservationError(
                f"Prior observation {observation_id} not found or already superseded"
            )
        
        if row[1] != logical_key:
            raise ValueError(
                "Logical key mismatch — cannot correct across different observations"
            )
        
        return row[2] if row[2] is not None else 1
    
    def insert_correction(
        self,
        prior_obs_id: int,
        record: AdapterRecord,
        source_id: int,
        run_id: int,
        category_id: Optional[int],
        fingerprint: str,
        logical_key: str,
        validation_status: ValidationStatus,
        validation_messages: list,
        fetched_at: datetime,
        new_version: int,
    ) -> int:
        """
        Insert corrected observation (used by commit_correction workflow).
        
        Args:
            prior_obs_id: ID of observation being corrected
            record: New adapter record with corrected data
            source_id: Rate source ID
            run_id: Collection run ID
            category_id: Category ID
            fingerprint: Computed fingerprint
            logical_key: Logical observation key
            validation_status: Validation result
            validation_messages: Validation messages
            fetched_at: Fetch timestamp
            new_version: New version number
            
        Returns:
            ID of inserted corrected observation
        """
        params = {
            'source_id': source_id,
            'run_id': run_id,
            'category_id': category_id,
            'currency_code': normalize_currency_code(record.source_currency_code),
            'source_currency_code': record.source_currency_code,
            'currency_name': record.currency_name,
            'buying_rate': record.buying_rate,
            'selling_rate': record.selling_rate,
            'source_rate_text': record.source_rate_text,
            'source_excerpt': json.dumps(record.raw_excerpt) if record.raw_excerpt else None,
            'quote_currency_code': record.quote_currency_code,
            'unit_multiplier': record.unit_multiplier,
            'effective_date': record.effective_date,
            'effective_date_basis': record.effective_date_basis,
            'fetched_at': fetched_at,
            'fingerprint': fingerprint,
            'fingerprint_version': FINGERPRINT_VERSION,
            'version_number': new_version,
            'is_current': False,  # Initially FALSE, promoted separately
            'identity_status': 'confirmed',  # Corrections are always confirmed
            'validation_status': validation_status.value,
            'validation_messages': json.dumps(validation_messages) if validation_messages else None,
            'change_review_status': 'confirmed_correction',
            'logical_key': logical_key,
            'supersedes_id': prior_obs_id,
            'is_fallback': False,  # Corrections are never fallback
        }
        
        return self._execute_returning(self._INSERT_SQL, params)

    def update_change_review_status(self, observation_id: int, status: str) -> None:
        """
        Update the change review status of an observation.

        Args:
            observation_id: ID of the observation
            status: New review status
        """
        query = """
            UPDATE rate_observation
            SET change_review_status = %s
            WHERE id = %s
        """
        self._execute(query, (status, observation_id))

    def compare_rates(self, obs_id_1: int, obs_id_2: int) -> bool:
        """
        Compare two observations to check if they have identical rates.

        Args:
            obs_id_1: First observation ID
            obs_id_2: Second observation ID

        Returns:
            True if buying_rate and selling_rate are identical
        """
        query = """
            SELECT
                (a.buying_rate IS NOT DISTINCT FROM b.buying_rate)
                AND (a.selling_rate IS NOT DISTINCT FROM b.selling_rate)
            FROM rate_observation a, rate_observation b
            WHERE a.id = %s AND b.id = %s
        """
        row = self._fetch_one(query, (obs_id_1, obs_id_2))
        return bool(row and row[0])

    def has_fresh_observation_today(self, source_id: int) -> bool:
        """
        Return True if this source already has a non-fallback is_current observation
        with effective_date = today.  Used to skip re-fetching banks that already
        published their daily rate.
        """
        query = """
            SELECT 1 FROM rate_observation
            WHERE source_id = %s
              AND is_current = TRUE
              AND is_fallback = FALSE
              AND effective_date = CURRENT_DATE
            LIMIT 1
        """
        return self._fetch_one(query, (source_id,)) is not None

    def get_rates_for_comparison(self, observation_id: int) -> Optional[tuple]:
        """
        Get buying and selling rates for an observation.

        Args:
            observation_id: Observation ID

        Returns:
            Tuple of (buying_rate, selling_rate) or None if not found
        """
        query = """
            SELECT buying_rate, selling_rate
            FROM rate_observation
            WHERE id = %s
        """
        return self._fetch_one(query, (observation_id,))
