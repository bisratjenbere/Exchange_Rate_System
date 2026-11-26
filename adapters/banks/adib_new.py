"""
ADIB Bank API adapter - Clean architecture implementation.

Migration notes:
- Old adapter: 164 LOC with BankAdapter base class
- New adapter: ~120 LOC clean architecture
- Pattern: JSON API with explicit category fields
- Categories: transactional (from transactionBuying/transactionSelling)
- Note: Plain buying/selling fields skipped (duplicates or zeros)

API Structure:
[
    {
        "id": 2,
        "currency": "USD",
        "buying": "...",
        "selling": "...",
        "transactionBuying": "...",
        "transactionSelling": "...",
        "updatedAt": "2026-09-30T07:09:31.000Z"
    },
    ...
]
"""

import json
from datetime import date
from decimal import Decimal
from typing import Optional

from adapters.core.contract import (
    ParseContext,
    ParseOutcome,
    RowIssue,
    IssueCode,
    Severity,
)
from adapters.core.record_builder import build_record
from adapters.core.numbers import parse_decimal
from adapters.transport.base import FetchKind


ADAPTER_KEY = "adib_api"
SOURCE_URL = "https://api.adibethio.com.et/api/exchange-rate/today"
ETB_ROW_ID = 1  # Skip ETB row (ID=1)


class ADIBAdapter:
    """ADIB Bank API adapter following new architecture."""
    
    key = ADAPTER_KEY
    url = SOURCE_URL
    fetch_kind = FetchKind.HTTP_GET
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        """
        Parse ADIB API JSON response.
        
        Returns ParseOutcome with records and any issues encountered.
        """
        issues = []
        records = []
        rows_seen = 0
        
        # Parse JSON
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return ParseOutcome.failed(
                IssueCode.BAD_JSON,
                f"Invalid JSON: {e}",
            )
        
        # Validate top-level structure
        if not isinstance(data, list):
            return ParseOutcome.failed(
                IssueCode.BAD_JSON,
                f"Expected JSON array, got {type(data).__name__}",
            )
        
        if not data:
            return ParseOutcome(
                records=(),
                rows_seen=0,
                issues=(RowIssue(
                    "page",
                    IssueCode.EMPTY_PAYLOAD,
                    "API returned empty array",
                    Severity.WARNING,
                ),),
                structure_hash="empty",
            )
        
        # Process each currency record
        for row_idx, row in enumerate(data, start=1):
            if not isinstance(row, dict):
                issues.append(RowIssue(
                    f"row[{row_idx}]",
                    IssueCode.BAD_JSON,
                    "Row is not a dict",
                    Severity.WARNING,
                ))
                continue
            
            # Skip ETB row
            row_id = row.get("id")
            if row_id == ETB_ROW_ID:
                continue
            
            rows_seen += 1
            row_ref = f"row {row_idx}"
            
            # Extract currency
            currency = str(row.get("currency", "")).strip().upper()
            if not currency:
                issues.append(RowIssue(
                    row_ref,
                    IssueCode.MISSING_CURRENCY,
                    "Missing or empty currency field",
                    Severity.ERROR,
                ))
                continue
            
            # Extract effective date from updatedAt
            updated_at = row.get("updatedAt")
            effective_date = self._parse_updated_at(updated_at) if updated_at else None
            
            # Parse transactional rates
            txn_buying_text = row.get("transactionBuying")
            txn_selling_text = row.get("transactionSelling")
            
            # Try to parse rates
            try:
                txn_buying = parse_decimal(txn_buying_text) if txn_buying_text else None
                txn_selling = parse_decimal(txn_selling_text) if txn_selling_text else None
            except ValueError as e:
                issues.append(RowIssue(
                    row_ref,
                    IssueCode.BAD_NUMBER,
                    f"Invalid rate format for {currency}: {e}",
                    Severity.ERROR,
                ))
                continue
            
            # Skip if both rates are missing or zero
            if not txn_buying or not txn_selling or txn_buying == 0 or txn_selling == 0:
                issues.append(RowIssue(
                    row_ref,
                    IssueCode.MISSING_RATE,
                    f"Missing or zero transactional rates for {currency}",
                    Severity.WARNING,
                ))
                continue
            
            # Build record for transactional category
            record = build_record(
                currency_code=currency,
                category="transactional",
                buying_rate=txn_buying,
                selling_rate=txn_selling,
                effective_date=effective_date or ctx.collection_date,
                effective_date_basis="source" if effective_date else "collection",
                source_id=ctx.source_id,
                collection_date=ctx.collection_date,
            )
            
            records.append(record)
        
        # Sort records by currency
        records.sort(key=lambda r: r.source_currency_code)
        
        # Compute structure hash
        structure_hash = f"adib_api:{len(records)}"
        
        return ParseOutcome(
            records=tuple(records),
            rows_seen=rows_seen,
            issues=tuple(issues),
            structure_hash=structure_hash,
        )
    
    def _parse_updated_at(self, raw: Optional[str]) -> Optional[date]:
        """
        Parse ISO date from updatedAt field.
        
        Example: '2026-09-30T07:09:31.000Z' → date(2026, 9, 30)
        """
        if not raw:
            return None
        try:
            # Extract YYYY-MM-DD part
            date_str = str(raw).strip()[:10]
            return date.fromisoformat(date_str)
        except (ValueError, AttributeError):
            return None


ADAPTER = ADIBAdapter()
