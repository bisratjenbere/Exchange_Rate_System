"""
Adapter contract - the ONE interface all adapters must implement.

Design decisions (from ADRs):
- Errors as values: ParseOutcome contains issues, never raises on bad rows
- Frozen dataclasses: Immutable for safety
- Severity levels: ERROR (row dropped) vs WARNING (row kept)
- Deterministic output: Records sorted by (currency_code, category)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from domain.records import AdapterRecord


class Severity(str, Enum):
    """Severity of a parse issue."""
    WARNING = "warning"   # Row kept, something odd (e.g., buy > sell)
    ERROR = "error"       # Row dropped (e.g., bad number, missing column)


class IssueCode(str, Enum):
    """Standardized issue codes for parse problems."""
    # Page-level failures
    EMPTY_PAYLOAD = "empty_payload"
    BAD_JSON = "bad_json"
    NO_TABLE = "no_table"              # HTML: no table with expected headers
    
    # Row-level failures
    MISSING_COLUMN = "missing_column"   # HTML: row too short
    MISSING_KEY = "missing_key"         # JSON: required key absent
    BAD_NUMBER = "bad_number"           # Rate value not parseable as Decimal
    UNKNOWN_CURRENCY = "unknown_currency"
    STALE_DATE = "stale_date"           # Date too old (e.g., >2 days for addis_fortune)
    
    # Warnings (row kept)
    BUY_ABOVE_SELL = "buy_above_sell"   # Suspicious but kept
    EMPTY_RATE = "empty_rate"           # Blank cell, converted to None


@dataclass(frozen=True)
class RowIssue:
    """
    A problem encountered while parsing a single row.
    
    Attributes:
        row_ref: Human-readable identifier (e.g., "USD", "row 7", "$.rates[3]")
        code: Standardized issue code
        detail: Human-readable description
        severity: ERROR (row dropped) or WARNING (row kept)
    """
    row_ref: str
    code: IssueCode
    detail: str
    severity: Severity


@dataclass(frozen=True)
class ParseContext:
    """
    Context injected into adapter.parse() by scheduler.
    
    Provides:
    - category: Default category if adapter cannot detect ("cash", "transactional", etc.)
    - collection_date: Business date in Africa/Addis_Ababa timezone
    - source_id: For logging/debugging
    
    Future extensions (not in S3):
    - clock: Injected clock for testing
    - logger: Structured logging
    """
    category: str           # "cash" | "transactional" | "weighted" | "UNKNOWN"
    collection_date: date   # Computed in Africa/Addis_Ababa by caller
    source_id: int


@dataclass(frozen=True)
class ParseOutcome:
    """
    Result of parsing raw content.
    
    Rules:
    - records: Successfully parsed records (sorted deterministically)
    - issues: Problems encountered (errors + warnings)
    - rows_seen: Total rows adapter attempted to parse (for error_ratio)
    - structure_hash: Schema fingerprint (structure ONLY, not rate values)
    
    Contract:
    - Never empty records AND empty issues (must report why no records)
    - structure_hash stable across rate changes (ADR-005)
    - Output deterministic (same input → same output, same order)
    """
    records: tuple['AdapterRecord', ...] = ()
    issues: tuple[RowIssue, ...] = ()
    rows_seen: int = 0
    structure_hash: str | None = None
    
    @property
    def error_count(self) -> int:
        """Count of ERROR-severity issues."""
        return sum(1 for i in self.issues if i.severity is Severity.ERROR)
    
    @property
    def warning_count(self) -> int:
        """Count of WARNING-severity issues."""
        return sum(1 for i in self.issues if i.severity is Severity.WARNING)
    
    @property
    def error_ratio(self) -> float:
        """Fraction of rows that had errors (for alerting thresholds)."""
        return self.error_count / self.rows_seen if self.rows_seen else 0.0
    
    @classmethod
    def failed(cls, code: IssueCode, detail: str) -> 'ParseOutcome':
        """
        Factory for page-level failures.
        
        Use when entire page is unparseable (empty, bad JSON, no table).
        """
        return cls(
            records=(),
            rows_seen=0,
            issues=(RowIssue("page", code, detail, Severity.ERROR),)
        )


class Adapter(Protocol):
    """
    Adapter contract - the ONE interface.
    
    Rules:
    1. Pure: No I/O, no DB access, no clock (except via ParseContext)
    2. Never raises on bad ROWS: Return RowIssue instead
    3. Deterministic: Same input → same output, same order
    4. Structure-only fingerprints: Rate changes don't alter structure_hash
    
    May raise on:
    - Structural failures (empty payload is debatable, prefer ParseOutcome.failed())
    - Configuration errors (missing required parameter)
    
    Example:
        class MyAdapter:
            key = "mybank_html"
            url = "https://mybank.com/rates"
            fetch_kind = FetchKind.HTTP_GET
            
            def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
                # ... parsing logic ...
                return ParseOutcome(records=(...), issues=(...), rows_seen=10, structure_hash="abc123")
    """
    key: str
    url: str
    # fetch_kind: FetchKind  # Defined in transport/base.py, deferred to avoid circular import
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        """
        Parse raw content into records.
        
        Args:
            raw: Raw HTML/JSON/text from bank website
            ctx: Parsing context (category, collection_date, source_id)
        
        Returns:
            ParseOutcome with records, issues, rows_seen, structure_hash
        
        Rules:
        - Bad rows become RowIssue entries, NOT exceptions
        - Records sorted by (currency_code, category) for determinism
        - structure_hash depends ONLY on structure (headers, keys), not values
        """
        ...
