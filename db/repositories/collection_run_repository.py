"""
Repository for collection_run and raw_capture tables.

Centralizes all queries related to collection run lifecycle management.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import psycopg2

from .base_repository import BaseRepository

class CollectionRunRepository(BaseRepository):
    """Repository for collection_run table operations."""

    def start_run(self, source_id: int) -> int:
        """
        Start a new collection run for the given source.

        Args:
            source_id: ID of the rate source

        Returns:
            ID of the newly created collection run
        """
        query = """
            INSERT INTO collection_run (source_id, started_at, status)
            VALUES (%s, now(), 'running')
            RETURNING id
        """
        return self._execute_returning(query, (source_id,))

    def finish_run(
        self,
        run_id: int,
        status: str,
        http_status: Optional[int] = None,
        records_found: int = 0,
        records_accepted: int = 0,
        records_flagged: int = 0,
        error_code: Optional[str] = None,
        error_summary: Optional[str] = None,
        duration_ms: Optional[int] = None,
        records_duplicated: int = 0,
        is_fallback: bool = False,
        fallback_adapter: Optional[str] = None,
    ) -> None:
        """
        Mark a collection run as finished with final metrics.

        Args:
            run_id: ID of the collection run
            status: Final status ('success', 'partial_success', 'failed')
            http_status: HTTP status code if applicable
            records_found: Number of records found
            records_accepted: Number of records accepted
            records_flagged: Number of records flagged for review
            error_code: Error code if failed
            error_summary: Error description if failed
            duration_ms: Duration in milliseconds
            records_duplicated: Number of duplicate records found
            is_fallback: Whether this run used fallback adapter
            fallback_adapter: Name of fallback adapter if used

        Raises:
            ValueError: If status is not valid
        """
        if status not in ("success", "partial_success", "failed"):
            raise ValueError(f"Invalid finish status: {status!r}")

        query = """
            UPDATE collection_run
            SET finished_at        = now(),
                status             = %s,
                http_status        = %s,
                records_found      = %s,
                records_accepted   = %s,
                records_flagged    = %s,
                records_duplicated = %s,
                is_fallback        = %s,
                fallback_adapter   = %s,
                error_code         = %s,
                error_summary      = %s,
                duration_ms        = %s
            WHERE id = %s
        """
        self._execute(
            query,
            (
                status,
                http_status,
                records_found,
                records_accepted,
                records_flagged,
                records_duplicated,
                is_fallback,
                fallback_adapter,
                error_code,
                error_summary,
                duration_ms,
                run_id,
            ),
        )

    def reap_stuck_runs(self, threshold_minutes: int = 5) -> int:
        """
        Mark runs stuck in 'running' state as failed.

        Args:
            threshold_minutes: Minutes before a run is considered stuck

        Returns:
            Number of runs that were reaped
        """
        threshold = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)
        query = """
            UPDATE collection_run
            SET finished_at   = now(),
                status        = 'failed',
                error_code    = 'timeout_reaped',
                error_summary = 'Run stuck in running state exceeded threshold'
            WHERE status = 'running'
              AND started_at < %s
            RETURNING id
        """
        rows = self._fetch_all(query, (threshold,))
        return len(rows)

    def recover_stuck_run(self, source_id: int, threshold_minutes: int = 5) -> Optional[int]:
        """
        Find and recover a specific stuck run for a source.

        Args:
            source_id: ID of the rate source
            threshold_minutes: Minutes before a run is considered stuck

        Returns:
            ID of the recovered run, or None if no stuck run found
        """
        threshold = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)

        # First, check if there's a stuck run
        select_query = """
            SELECT id
            FROM collection_run
            WHERE source_id = %s
              AND status = 'running'
              AND started_at < %s
            LIMIT 1
        """
        row = self._fetch_one(select_query, (source_id, threshold))
        if not row:
            return None

        stuck_id = row[0]

        # Mark it as failed
        update_query = """
            UPDATE collection_run
            SET finished_at   = now(),
                status        = 'failed',
                error_code    = 'stuck_run_recovered',
                error_summary = 'Run exceeded threshold and was recovered automatically'
            WHERE id = %s
        """
        self._execute(update_query, (stuck_id,))
        return stuck_id

    def get_running_run(self, source_id: int) -> Optional[int]:
        """
        Get the ID of a currently running collection run for a source.

        Args:
            source_id: ID of the rate source

        Returns:
            ID of the running collection run, or None if no run is running
        """
        query = """
            SELECT id
            FROM collection_run
            WHERE source_id = %s
              AND status = 'running'
            LIMIT 1
        """
        row = self._fetch_one(query, (source_id,))
        return row[0] if row else None

    def get_recent_runs_summary(self, since) -> Optional[tuple]:
        """Return (total, succeeded) run counts since a given timestamp."""
        query = """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status IN ('success', 'partial_success')) AS succeeded
            FROM collection_run
            WHERE started_at >= %s
        """
        return self._fetch_one(query, (since,))

    def get_stuck_runs(self, since) -> Optional[tuple]:
        """Return (count, source_ids) of runs stuck in 'running' state since threshold."""
        query = """
            SELECT COUNT(*), array_agg(source_id)
            FROM collection_run
            WHERE status = 'running' AND started_at < %s
        """
        return self._fetch_one(query, (since,))

    def get_failed_runs_since(self, since) -> list:
        """Return failed runs since a given timestamp."""
        query = """
            SELECT id, source_id, finished_at, error_code, error_summary
            FROM collection_run
            WHERE status = 'failed' AND finished_at >= %s
            ORDER BY finished_at DESC
        """
        return self._fetch_all(query, (since,))

    def get_schema_changes_since(self, since) -> list:
        """Return schema change captures since a given timestamp."""
        query = """
            SELECT rc.id, cr.source_id, rc.captured_at, rc.content_hash
            FROM raw_capture rc
            JOIN collection_run cr ON cr.id = rc.collection_run_id
            WHERE rc.capture_reason = 'schema_change' AND rc.captured_at >= %s
            ORDER BY rc.captured_at DESC
        """
        return self._fetch_all(query, (since,))

    def get_last_successful_run_per_source(self) -> list:
        """Return the most recent successful run per enabled source."""
        query = """
            SELECT DISTINCT ON (cr.source_id)
                cr.source_id, cr.id, cr.finished_at, cr.records_found
            FROM collection_run cr
            JOIN rate_source rs ON rs.id = cr.source_id
            WHERE rs.is_enabled = TRUE
              AND cr.status IN ('success', 'partial_success')
              AND cr.finished_at IS NOT NULL
            ORDER BY cr.source_id, cr.finished_at DESC
        """
        return self._fetch_all(query)

    def get_recent_runs(self, limit: int = 10) -> list:
        """Return the most recent collection runs across all sources."""
        query = """
            SELECT cr.started_at, rs.adapter_key, cr.status,
                   cr.records_accepted, cr.duration_ms
            FROM collection_run cr
            JOIN rate_source rs ON rs.id = cr.source_id
            ORDER BY cr.started_at DESC
            LIMIT %s
        """
        return self._fetch_all(query, (limit,))

    def finish_stale_run(
        self,
        run_id: int,
        records_found: int,
        records_accepted: int,
        records_flagged: int,
        records_duplicated: int,
        duration_ms: int,
    ) -> None:
        """Mark a stale-feed run as success with a fixed error_code."""
        query = """
            UPDATE collection_run
            SET status = 'success', finished_at = now(),
                records_found = %s, records_accepted = %s,
                records_flagged = %s, records_duplicated = %s,
                error_code = 'stale_feed',
                error_summary = 'Primary returned stale records; retained as standing rate',
                duration_ms = %s
            WHERE id = %s
        """
        self._execute(query, (
            records_found, records_accepted, records_flagged,
            records_duplicated, duration_ms, run_id,
        ))

    def insert_raw_capture(
        self,
        run_id: int,
        capture_reason: str,
        content_hash: str,
        storage_reference: Optional[str] = None,
        retention_days: int = 90,
    ) -> int:
        """
        Insert a raw capture record for debugging/forensics.

        Args:
            run_id: ID of the collection run
            capture_reason: Reason for capture ('http_failure', 'parse_failure', 'schema_change', 'suspicious_data')
            content_hash: SHA-256 hash of captured content
            storage_reference: Reference to stored content (e.g., S3 key)
            retention_days: Days to retain the content (default 90)

        Returns:
            ID of the newly created raw_capture record

        Raises:
            ValueError: If capture_reason is not valid
        """
        valid_reasons = {"http_failure", "parse_failure", "schema_change", "suspicious_data"}
        if capture_reason not in valid_reasons:
            raise ValueError(f"Invalid capture_reason: {capture_reason!r}")

        query = """
            INSERT INTO raw_capture
                (collection_run_id, capture_reason, content_hash,
                 storage_reference, retention_until)
            VALUES (%s, %s, %s, %s, now()::date + %s)
            RETURNING id
        """
        return self._execute_returning(
            query, (run_id, capture_reason, content_hash, storage_reference, retention_days)
        )
