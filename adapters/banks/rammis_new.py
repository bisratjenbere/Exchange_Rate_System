"""
Rammis Bank adapter - JSON API.

Migration notes:
- Old adapter: 108 LOC (adapters/rammis/adapter.py)
- New adapter: JSON parsing (manual, until JsonSpec implemented)
- API endpoint: https://rammisbanksc.com/api/exchange-rates
- JSON format: {"rates": [{"currency": "AED", "buying": "45.68", "selling": "46.60"}]}
- Total: 17 records (17 currencies, all transactional)

Pattern: JSON API with manual parsing (Pattern F)
"""

from adapters.core.html_table import HtmlTableAdapter, TableSpec
from adapters.core.contract import ParseContext, ParseOutcome, RowIssue, IssueCode, Severity
from adapters.transport.base import FetchKind
from adapters.core.numbers import parse_decimal
from adapters.core.currency import normalize_currency
from adapters.core.record_builder import build_record
import json


class RammisAdapter:
    """
    Rammis Bank JSON API adapter.
    
    JSON format:
      {
        "base_currency": "ETB",
        "effective_date": "2026-11-25",
        "rates": [
          {
            "id": 5,
            "currency": "AED",
            "buying": "45.683800",
            "selling": "46.597500",
            ...
          },
          ...
        ]
      }
      
    Each item creates 1 record (all transactional category).
    """
    
    key = "rammis_api"
    url = "https://rammisbanksc.com/api/exchange-rates"
    fetch_kind = FetchKind.HTTP_GET
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        if not raw or not raw.strip():
            return ParseOutcome.failed(IssueCode.EMPTY_PAYLOAD, "Empty response")
        
        # Parse JSON
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return ParseOutcome.failed(IssueCode.EMPTY_PAYLOAD, f"Invalid JSON: {e}")
        
        # Extract rates array
        items = data.get("rates", []) if isinstance(data, dict) else []
        
        if not items:
            return ParseOutcome.failed(IssueCode.NO_TABLE, "No rates in JSON response")
        
        records = []
        issues = []
        
        for item in items:
            # Extract currency code
            currency_code = str(item.get("currency", "")).strip().upper()
            if not currency_code:
                continue
            
            normalized = normalize_currency(currency_code)
            if not normalized:
                normalized = currency_code
            
            # Parse rates
            buy = None
            sell = None
            
            if item.get("buying") is not None:
                try:
                    buy = parse_decimal(str(item["buying"]))
                except ValueError:
                    issues.append(RowIssue(
                        row_ref=currency_code,
                        code=IssueCode.BAD_NUMBER,
                        detail=f"Bad buying rate: {item['buying']}",
                        severity=Severity.ERROR
                    ))
            
            if item.get("selling") is not None:
                try:
                    sell = parse_decimal(str(item["selling"]))
                except ValueError:
                    issues.append(RowIssue(
                        row_ref=currency_code,
                        code=IssueCode.BAD_NUMBER,
                        detail=f"Bad selling rate: {item['selling']}",
                        severity=Severity.ERROR
                    ))
            
            if buy is not None or sell is not None:
                rec = build_record(
                    currency_code=normalized,
                    category="transactional",
                    buying_rate=buy,
                    selling_rate=sell,
                    ctx=ctx
                )
                records.append(rec)
        
        # Sort for determinism
        records.sort(key=lambda r: (r.source_currency_code, r.category))
        
        # Compute structure hash
        import hashlib
        structure_text = f"rammis_json#{len(items)}_items"
        structure_hash = hashlib.sha256(structure_text.encode()).hexdigest()[:16]
        
        return ParseOutcome(
            records=tuple(records),
            issues=tuple(issues),
            rows_seen=len(items),
            structure_hash=structure_hash
        )


ADAPTER = RammisAdapter()
