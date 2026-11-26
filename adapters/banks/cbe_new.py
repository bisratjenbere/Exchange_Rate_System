"""
CBE (Commercial Bank of Ethiopia) API Adapter - New Architecture

Pattern: JSON API with multi-category rates (cash + transactional)
API returns array of publications, each with exchange rates for multiple currencies.

Data structure:
- Array of publications (100+ items) 
- Each publication has Date and ExchangeRate array
- Each ExchangeRate has: cashBuying, cashSelling, transactionalBuying, transactionalSelling
- Currency info nested in currency object with CurrencyCode and CurrencyName

Migration notes:
- Legacy used FieldStructureMixin.detect_and_emit() for auto-detection
- New version explicitly handles both cash and transactional categories
- Simplified from 136 LOC to ~150 LOC (more explicit, less magic)
- Better error handling and validation
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


ADAPTER_KEY = "cbe_api"
SOURCE_URL = "https://combanketh.et/cbeapi/daily-exchange-rates/"


class CBEAdapter:
    """CBE API adapter following new architecture."""
    
    key = ADAPTER_KEY
    url = SOURCE_URL
    fetch_kind = FetchKind.HTTP_GET
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        """
        Parse CBE API JSON response.
        
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
                ),)
            )
        
        # Process each publication
        for pub_idx, publication in enumerate(data):
            if not isinstance(publication, dict):
                issues.append(RowIssue(
                    f"pub[{pub_idx}]",
                    IssueCode.BAD_JSON,
                    "Publication is not a dict",
                    Severity.WARNING,
                ))
                continue
            
            # Extract publication metadata
            pub_id = publication.get("_id") or publication.get("id")
            date_str = publication.get("Date", "")
            effective_date = _parse_date(date_str)
            
            # Process exchange rates
            exchange_rates = publication.get("ExchangeRate")
            if not isinstance(exchange_rates, list):
                issues.append(RowIssue(
                    f"pub[{pub_id}]",
                    IssueCode.MISSING_KEY,
                    "Missing ExchangeRate array",
                    Severity.WARNING,
                ))
                continue
            
            for er_idx, er_item in enumerate(exchange_rates):
                if not isinstance(er_item, dict):
                    continue
                
                rows_seen += 1
                
                # Extract currency info
                currency_obj = er_item.get("currency", {})
                if not isinstance(currency_obj, dict):
                    issues.append(RowIssue(
                        f"pub[{pub_id}].er[{er_idx}]",
                        IssueCode.MISSING_KEY,
                        "Missing or invalid currency object",
                        Severity.ERROR,
                    ))
                    continue
                
                currency_code = str(currency_obj.get("CurrencyCode", "")).strip()
                currency_name = str(currency_obj.get("CurrencyName", "")).strip() or None
                
                if not currency_code:
                    issues.append(RowIssue(
                        f"pub[{pub_id}].er[{er_idx}]",
                        IssueCode.UNKNOWN_CURRENCY,
                        "Missing CurrencyCode",
                        Severity.ERROR,
                    ))
                    continue
                
                # Parse cash rates
                cash_buying = _safe_decimal(er_item.get("cashBuying"))
                cash_selling = _safe_decimal(er_item.get("cashSelling"))
                
                if cash_buying is not None or cash_selling is not None:
                    records.append(build_record(
                        currency_code=currency_code,
                        category="cash",
                        buying_rate=cash_buying,
                        selling_rate=cash_selling,
                        ctx=ctx,
                        effective_date=effective_date,
                        effective_date_basis="source_published" if effective_date else "collection_date_fallback",
                        currency_name=currency_name,
                        source_rate_text=f"{cash_buying}/{cash_selling}",
                        mapping_notes=["zero_equals_not_offered"],
                    ))
                
                # Parse transactional rates
                txn_buying = _safe_decimal(er_item.get("transactionalBuying"))
                txn_selling = _safe_decimal(er_item.get("transactionalSelling"))
                
                if txn_buying is not None or txn_selling is not None:
                    records.append(build_record(
                        currency_code=currency_code,
                        category="transactional",
                        buying_rate=txn_buying,
                        selling_rate=txn_selling,
                        ctx=ctx,
                        effective_date=effective_date,
                        effective_date_basis="source_published" if effective_date else "collection_date_fallback",
                        currency_name=currency_name,
                        source_rate_text=f"{txn_buying}/{txn_selling}",
                        mapping_notes=["zero_equals_not_offered"],
                    ))
        
        # Final validation
        if not records and not issues:
            issues.append(RowIssue(
                "page",
                IssueCode.EMPTY_PAYLOAD,
                f"No records extracted from {len(data)} publications",
                Severity.WARNING,
            ))
        
        # Sort records for determinism
        records_sorted = tuple(sorted(
            records,
            key=lambda r: (r.source_currency_code, r.category)
        ))
        
        return ParseOutcome(
            records=records_sorted,
            issues=tuple(issues),
            rows_seen=rows_seen,
            structure_hash=None,  # TODO: Implement if needed
        )


def _safe_decimal(value) -> Optional[Decimal]:
    """
    Convert value to Decimal, return None if invalid.
    
    Handles: int, float, str, None
    Returns None for 0 (CBE uses 0 to indicate "not offered")
    """
    if value is None:
        return None
    
    try:
        dec = Decimal(str(value))
        # CBE uses 0 to mean "not offered"
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
ADAPTER = CBEAdapter()
