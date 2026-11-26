"""
Zemen Bank AJAX Adapter - New Architecture

Pattern: AJAX endpoint with POST request
Requires POST data: {"action": "get_exchange_rates"}

Data structure:
- JSON response with status, date, rates
- rates contains: day[], cash[], average[]
- Each rate has currency_code, buying/selling rates
- Multiple categories: cash, transactional, average

Migration notes:
- Legacy used FieldStructureMixin.detect_and_emit()
- New version explicit category handling
- Simplified from 122 LOC to ~180 LOC (more explicit)
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
from adapters.transport.base import FetchKind


ADAPTER_KEY = "zemen_ajax"
SOURCE_URL = "https://zemenbank.com/wp-admin/admin-ajax.php"
POST_DATA = {"action": "get_exchange_rates"}
HEADERS = {"Referer": "https://zemenbank.com/exchange-rates/"}


class ZemenAdapter:
    """Zemen Bank AJAX adapter following new architecture."""
    
    key = ADAPTER_KEY
    url = SOURCE_URL
    fetch_kind = FetchKind.HTTP_POST
    post_data = POST_DATA
    headers = HEADERS
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        """
        Parse Zemen AJAX JSON response.
        
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
        
        # Validate structure
        if not isinstance(data, dict):
            return ParseOutcome.failed(
                IssueCode.BAD_JSON,
                f"Expected JSON object, got {type(data).__name__}",
            )
        
        # Check status
        if data.get("status") != "success":
            return ParseOutcome.failed(
                IssueCode.EMPTY_PAYLOAD,
                f"API returned status: {data.get('status')}",
            )
        
        # Parse dates
        effective_date = _parse_date(data.get("date", ""))
        avg_date = _parse_date(data.get("avg_date", ""))
        
        rates = data.get("rates", {})
        if not isinstance(rates, dict):
            return ParseOutcome.failed(
                IssueCode.MISSING_KEY,
                "Missing 'rates' object",
            )
        
        # Process day rates (transactional category)
        day_rates = rates.get("day", [])
        if isinstance(day_rates, list):
            for row_idx, row in enumerate(day_rates):
                rows_seen += 1
                
                if not isinstance(row, dict):
                    continue
                
                currency_code = str(row.get("currency_code", "")).strip()
                if not currency_code:
                    issues.append(RowIssue(
                        f"day[{row_idx}]",
                        IssueCode.UNKNOWN_CURRENCY,
                        "Missing currency_code",
                        Severity.ERROR,
                    ))
                    continue
                
                # Parse rates
                buying = _safe_decimal(row.get("buying_rate"))
                selling = _safe_decimal(row.get("selling_rate"))
                
                if buying is not None or selling is not None:
                    records.append(build_record(
                        currency_code=currency_code,
                        category="transactional",
                        buying_rate=buying,
                        selling_rate=selling,
                        ctx=ctx,
                        effective_date=effective_date,
                        effective_date_basis="source_published" if effective_date else None,
                        source_rate_text=f"{buying}/{selling}",
                    ))
        
        # Process cash rates (cash category)
        cash_rates = rates.get("cash", [])
        if isinstance(cash_rates, list):
            for row_idx, row in enumerate(cash_rates):
                rows_seen += 1
                
                if not isinstance(row, dict):
                    continue
                
                currency_code = str(row.get("currency_code", "")).strip()
                if not currency_code:
                    continue
                
                # Parse rates
                buying = _safe_decimal(row.get("buying_rate"))
                selling = _safe_decimal(row.get("selling_rate"))
                
                if buying is not None or selling is not None:
                    records.append(build_record(
                        currency_code=currency_code,
                        category="cash",
                        buying_rate=buying,
                        selling_rate=selling,
                        ctx=ctx,
                        effective_date=effective_date,
                        effective_date_basis="source_published" if effective_date else None,
                        source_rate_text=f"{buying}/{selling}",
                    ))
        
        # Process average rates (average category)
        avg_rates = rates.get("average", [])
        if isinstance(avg_rates, list):
            for row_idx, row in enumerate(avg_rates):
                rows_seen += 1
                
                if not isinstance(row, dict):
                    continue
                
                currency_code = str(row.get("currency_code", "")).strip()
                if not currency_code:
                    continue
                
                # Parse average rates
                avg_buy = _safe_decimal(row.get("avg_buying_rate"))
                avg_sell = _safe_decimal(row.get("avg_selling_rate"))
                
                if avg_buy is not None or avg_sell is not None:
                    records.append(build_record(
                        currency_code=currency_code,
                        category="average",
                        buying_rate=avg_buy,
                        selling_rate=avg_sell,
                        ctx=ctx,
                        effective_date=avg_date,
                        effective_date_basis="source_published" if avg_date else None,
                        source_rate_text=f"{avg_buy}/{avg_sell}",
                    ))
        
        # Validation
        if not records and not issues:
            issues.append(RowIssue(
                "page",
                IssueCode.EMPTY_PAYLOAD,
                f"No records extracted from {rows_seen} rows",
                Severity.WARNING,
            ))
        
        # Sort for determinism
        records_sorted = tuple(sorted(
            records,
            key=lambda r: (r.source_currency_code, r.category)
        ))
        
        return ParseOutcome(
            records=records_sorted,
            issues=tuple(issues),
            rows_seen=rows_seen,
            structure_hash=None,
        )


def _safe_decimal(value) -> Optional[Decimal]:
    """Convert value to Decimal, return None if invalid."""
    if value is None:
        return None
    
    try:
        dec = Decimal(str(value))
        if dec == 0:
            return None
        return dec
    except (ValueError, TypeError, ArithmeticError):
        return None


def _parse_date(date_str: str) -> Optional[date]:
    """
    Parse ISO date string to date object.
    
    Expected format: "YYYY-MM-DD"
    """
    if not date_str:
        return None
    
    try:
        return date.fromisoformat(str(date_str).strip())
    except (ValueError, AttributeError):
        return None


# Module-level adapter instance
ADAPTER = ZemenAdapter()
