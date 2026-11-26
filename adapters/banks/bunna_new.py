"""
Bunna Bank adapter - JSON API with cash/transactional.

Migration notes:
- Old adapter: 118 LOC (adapters/bunna/adapter.py, hybrid JSON/HTML)
- New adapter: JSON parsing (manual, until JsonSpec implemented)
- API endpoint: https://mb.bunnabanksc.com/api/v1/user/public/forex
- JSON format: {"content": [{"currencyCode": "USD", "buying": 165.69, "selling": 169.00, ...}]}
- Total: 16 records (8 currencies × 2 categories: cash + transactional)

Pattern: JSON API with manual parsing (Pattern F prototype)
"""

from adapters.core.html_table import HtmlTableAdapter, TableSpec
from adapters.core.contract import ParseContext, ParseOutcome, RowIssue, IssueCode, Severity
from adapters.transport.base import FetchKind
from adapters.core.numbers import parse_decimal
from adapters.core.currency import normalize_currency
from adapters.core.record_builder import build_record
import json


class BunnaAdapter:
    """
    Bunna Bank JSON API adapter.
    
    JSON format:
      {
        "content": [
          {
            "currencyCode": "USD",
            "currency": "US Dollar",
            "buying": 165.6915,
            "selling": 169.0053,
            "transactionBuying": 165.6915,
            "transactionSelling": 169.0053,
            "valueDate": "2026-11-25T00:00:00"
          },
          ...
        ]
      }
      
    Each item creates 2 records: cash and transactional.
    """
    
    key = "bunna_html"  # Keep original key for compatibility
    url = "https://mb.bunnabanksc.com/api/v1/user/public/forex"
    fetch_kind = FetchKind.HTTP_GET
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        if not raw or not raw.strip():
            return ParseOutcome.failed(IssueCode.EMPTY_PAYLOAD, "Empty response")
        
        # Parse JSON
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return ParseOutcome.failed(IssueCode.EMPTY_PAYLOAD, f"Invalid JSON: {e}")
        
        # Extract content array
        items = data.get("content", []) if isinstance(data, dict) else []
        
        if not items:
            return ParseOutcome.failed(IssueCode.NO_TABLE, "No content in JSON response")
        
        records = []
        issues = []
        
        for item_idx, item in enumerate(items):
            # Extract currency code
            currency_code = item.get("currencyCode", "").strip().upper()
            if not currency_code:
                continue
            
            normalized = normalize_currency(currency_code)
            if not normalized:
                normalized = currency_code
            
            # Parse cash rates (buying/selling)
            cash_buy = None
            cash_sell = None
            
            if item.get("buying") is not None:
                try:
                    cash_buy = parse_decimal(str(item["buying"]))
                except ValueError:
                    issues.append(RowIssue(
                        row_ref=f"{currency_code}_cash",
                        code=IssueCode.BAD_NUMBER,
                        detail=f"Bad cash buying: {item['buying']}",
                        severity=Severity.ERROR
                    ))
            
            if item.get("selling") is not None:
                try:
                    cash_sell = parse_decimal(str(item["selling"]))
                except ValueError:
                    issues.append(RowIssue(
                        row_ref=f"{currency_code}_cash",
                        code=IssueCode.BAD_NUMBER,
                        detail=f"Bad cash selling: {item['selling']}",
                        severity=Severity.ERROR
                    ))
            
            if cash_buy is not None or cash_sell is not None:
                rec = build_record(
                    currency_code=normalized,
                    category="cash",
                    buying_rate=cash_buy,
                    selling_rate=cash_sell,
                    ctx=ctx
                )
                records.append(rec)
            
            # Parse transactional rates
            txn_buy = None
            txn_sell = None
            
            if item.get("transactionBuying") is not None:
                try:
                    txn_buy = parse_decimal(str(item["transactionBuying"]))
                except ValueError:
                    pass
            
            if item.get("transactionSelling") is not None:
                try:
                    txn_sell = parse_decimal(str(item["transactionSelling"]))
                except ValueError:
                    pass
            
            if txn_buy is not None or txn_sell is not None:
                rec = build_record(
                    currency_code=normalized,
                    category="transactional",
                    buying_rate=txn_buy,
                    selling_rate=txn_sell,
                    ctx=ctx
                )
                records.append(rec)
        
        # Sort for determinism
        records.sort(key=lambda r: (r.source_currency_code, r.category))
        
        # Compute structure hash
        import hashlib
        structure_text = f"bunna_json#{len(items)}_items"
        structure_hash = hashlib.sha256(structure_text.encode()).hexdigest()[:16]
        
        return ParseOutcome(
            records=tuple(records),
            issues=tuple(issues),
            rows_seen=len(items),
            structure_hash=structure_hash
        )


ADAPTER = BunnaAdapter()
