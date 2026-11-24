"""
Decision module - Record classification logic.

Extracted from scheduler/runner.py lines 118-120 (decision logic only).
Handles:
- Classifying records as zero/stale/normal
- Pure decision logic with no side effects

This module contains NO I/O, NO database access, NO transaction logic.
Just pure classification logic.
"""

from dataclasses import dataclass
from datetime import date
from typing import Literal

from domain.records import AdapterRecord


STALE_THRESHOLD_DAYS = 3


@dataclass(frozen=True)
class RecordClassification:
    """Classification of parsed records."""
    classification: Literal["zero", "stale", "normal"]
    record_count: int
    should_ingest: bool  # Whether records should be ingested
    error_code: str | None  # Error code if zero or stale
    error_summary: str | None  # Error summary if zero or stale


def classify_records(records: list[AdapterRecord]) -> RecordClassification:
    """
    Classify parsed records as zero, stale, or normal.

    Classification rules:
    1. Zero: No records returned by adapter
    2. Stale: All records are >STALE_THRESHOLD_DAYS old
    3. Normal: At least one record is fresh

    Args:
        records: List of parsed AdapterRecords from fetcher

    Returns:
        RecordClassification indicating how to handle these records

    Pure Logic:
        - No I/O
        - No database access
        - No side effects
        - Deterministic given inputs
    """
    record_count = len(records)

    # Case 1: Zero records
    if record_count == 0:
        return RecordClassification(
            classification="zero",
            record_count=0,
            should_ingest=False,
            error_code="zero_records_extracted",
            error_summary="Primary returned 0 records; fallback invoked"
        )

    # Case 2: Check if all records are stale
    all_stale = all(
        r.effective_date and (date.today() - r.effective_date).days > STALE_THRESHOLD_DAYS
        for r in records
    )

    if all_stale:
        return RecordClassification(
            classification="stale",
            record_count=record_count,
            should_ingest=True,  # Stale records ARE ingested as "standing rate"
            error_code="stale_feed",
            error_summary="Primary returned stale records; fallback invoked"
        )

    # Case 3: Normal (at least one fresh record)
    return RecordClassification(
        classification="normal",
        record_count=record_count,
        should_ingest=True,
        error_code=None,
        error_summary=None
    )
