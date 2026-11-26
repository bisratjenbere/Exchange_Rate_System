"""
Core adapter framework - S3

Provides:
- Adapter Protocol and ParseOutcome contract
- Shared helpers (numbers, currency, dates)
- Declarative specs (TableSpec, JsonSpec)
- Transport layer (HTTP, Browser)

Design principles:
- Errors as values (ParseOutcome with RowIssue), not exceptions
- Pure functions (no I/O, no DB, deterministic output)
- Structure-only fingerprints (rates don't affect schema hash)
"""

from adapters.core.contract import (
    Adapter,
    ParseOutcome,
    ParseContext,
    RowIssue,
    Severity,
    IssueCode,
)

__all__ = [
    "Adapter",
    "ParseOutcome",
    "ParseContext",
    "RowIssue",
    "Severity",
    "IssueCode",
]
