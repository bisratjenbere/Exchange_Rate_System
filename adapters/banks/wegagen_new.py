"""
Wegagen Bank - Strapi v4 API adapter.

Fetches exchange rates from Wegagen Bank's Strapi CMS API endpoint.

API Structure (Strapi v4):
{
  "data": [
    {
      "id": 1,
      "attributes": {
        "date": "2026-11-25",
        "code": "USD",
        "unit": 1,
        "buying": 162.5068,
        "selling": 165.7569,
        "tra_buying": 162.5068,
        "tra_selling": 165.7569,
        ...
      }
    },
    ...
  ]
}

Notes:
- Strapi v4 wraps data in {"data": [...], "attributes": {...}} structure
- Each record has both cash rates (buying/selling) and transactional rates (tra_buying/tra_selling)
- As per ADR-011: "buying==tra_buying for all records"
- Date format: YYYY-MM-DD
"""

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation

from adapters.core.contract import (
    ParseContext,
    ParseOutcome,
    RowIssue,
    IssueCode,
    Severity,
)
from adapters.core.record_builder import build_record
from adapters.transport.base import FetchKind


ADAPTER_KEY = "wegagen_api"
SOURCE_URL = "https://weg.back.strapi.wegagen.com/api/exchange-rates?populate=*"


class WegagenAdapter:
    """Wegagen Bank Strapi API adapter following new architecture."""
    
    key = ADAPTER_KEY
    url = SOURCE_URL
    fetch_kind = FetchKind.HTTP_GET
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        """
        Parse Strapi v4 API response from Wegagen Bank.
        
        Args:
            raw: JSON string from Strapi API
            ctx: Parsing context with metadata
            
        Returns:
            ParseOutcome with records and any issues
        """
        records = []
        issues = []
        
        # Parse JSON
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            issues.append(RowIssue(
                row_ref="page",
                code=IssueCode.BAD_JSON,
                detail=f"Invalid JSON: {e}",
                severity=Severity.ERROR,
            ))
            return ParseOutcome(records=tuple(), issues=tuple(issues), rows_seen=0, structure_hash=None)
        
        # Validate structure
        if not isinstance(data, dict) or "data" not in data:
            issues.append(RowIssue(
                row_ref="page",
                code=IssueCode.MISSING_KEY,
                detail="Missing 'data' key in API response",
                severity=Severity.ERROR,
            ))
            return ParseOutcome(records=tuple(), issues=tuple(issues), rows_seen=0, structure_hash=None)
        
        items = data.get("data", [])
        if not isinstance(items, list):
            issues.append(RowIssue(
                row_ref="page",
                code=IssueCode.MISSING_KEY,
                detail="'data' is not a list",
                severity=Severity.ERROR,
            ))
            return ParseOutcome(records=tuple(), issues=tuple(issues), rows_seen=0, structure_hash=None)
        
        # Parse each item
        for idx, item in enumerate(items):
            row_ref = f"item[{idx}]"
            
            try:
                # Validate Strapi v4 structure
                if not isinstance(item, dict) or "attributes" not in item:
                    issues.append(RowIssue(
                        row_ref=row_ref,
                        code=IssueCode.MISSING_KEY,
                        detail="Missing 'attributes' in item",
                        severity=Severity.WARNING,
                    ))
                    continue
                
                attrs = item["attributes"]
                currency_code = attrs.get("code")
                
                if not currency_code:
                    issues.append(RowIssue(
                        row_ref=row_ref,
                        code=IssueCode.UNKNOWN_CURRENCY,
                        detail="Missing currency code",
                        severity=Severity.WARNING,
                    ))
                    continue
                
                # Parse date
                date_str = attrs.get("date")
                effective_date = None
                if date_str:
                    try:
                        effective_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    except (ValueError, TypeError):
                        issues.append(RowIssue(
                            row_ref=row_ref,
                            code=IssueCode.BAD_NUMBER,
                            detail=f"Invalid date format: {date_str}",
                            severity=Severity.WARNING,
                        ))
                
                # Parse rates
                buying = attrs.get("buying")
                selling = attrs.get("selling")
                tra_buying = attrs.get("tra_buying")
                tra_selling = attrs.get("tra_selling")
                
                # Cash rates (always present)
                if buying is not None and selling is not None:
                    try:
                        buying_dec = Decimal(str(buying))
                        selling_dec = Decimal(str(selling))
                        
                        record = build_record(
                            currency_code=currency_code,
                            category="cash",
                            buying_rate=buying_dec,
                            selling_rate=selling_dec,
                            ctx=ctx,
                            effective_date=effective_date,
                            effective_date_basis="source_published" if effective_date else None,
                            source_rate_text=f"{buying_dec}/{selling_dec}",
                        )
                        records.append(record)
                    except (InvalidOperation, ValueError, TypeError) as e:
                        issues.append(RowIssue(
                            row_ref=row_ref,
                            code=IssueCode.BAD_NUMBER,
                            detail=f"Invalid cash rate value: {e}",
                            severity=Severity.WARNING,
                        ))
                
                # Transactional rates (if present and different from cash)
                if tra_buying is not None and tra_selling is not None:
                    try:
                        tra_buying_dec = Decimal(str(tra_buying))
                        tra_selling_dec = Decimal(str(tra_selling))
                        
                        # Only add if different from cash (ADR-011 says they're equal)
                        if tra_buying_dec != buying or tra_selling_dec != selling:
                            record = build_record(
                                currency_code=currency_code,
                                category="transactional",
                                buying_rate=tra_buying_dec,
                                selling_rate=tra_selling_dec,
                                ctx=ctx,
                                effective_date=effective_date,
                                effective_date_basis="source_published" if effective_date else None,
                                source_rate_text=f"{tra_buying_dec}/{tra_selling_dec}",
                            )
                            records.append(record)
                    except (InvalidOperation, ValueError, TypeError) as e:
                        issues.append(RowIssue(
                            row_ref=row_ref,
                            code=IssueCode.BAD_NUMBER,
                            detail=f"Invalid transactional rate value: {e}",
                            severity=Severity.WARNING,
                        ))
                
            except Exception as e:
                issues.append(RowIssue(
                    row_ref=row_ref,
                    code=IssueCode.BAD_NUMBER,
                    detail=f"Unexpected error: {e}",
                    severity=Severity.WARNING,
                ))
        
        return ParseOutcome(
            records=tuple(records),
            issues=tuple(issues),
            rows_seen=len(items),
            structure_hash=None
        )


# Export singleton
ADAPTER = WegagenAdapter()
