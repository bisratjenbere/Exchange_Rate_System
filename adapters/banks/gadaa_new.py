"""
Gadaa Bank adapter - JSON API.

Migration notes:
- Old adapter: 92 LOC (adapters/gadaa/adapter.py)
- New adapter: JSON parsing (manual, until JsonSpec implemented)
- API endpoint: https://gadaabank.com.et/api/v1/exchange-rates
- JSON format: {"data": [{"currency": "EUR", "buy_rate": 185.80, "sell_rate": 189.52, "market_type": "transaction"}]}
- Total: 6 records (3 currencies × 2 market_types: cash + transaction)

Pattern: JSON API with manual parsing (Pattern F)
"""

from adapters.core.html_table import HtmlTableAdapter, TableSpec
from adapters.core.contract import ParseContext, ParseOutcome, RowIssue, IssueCode, Severity
from adapters.transport.base import FetchKind
from adapters.core.numbers import parse_decimal
from adapters.core.currency import normalize_currency
from adapters.core.record_builder import build_record
import json
import hashlib


class GadaaAdapter:
    """
    Gadaa Bank JSON API adapter.
    
    JSON format:
      {
        "data": [
          {
            "id": 10003,
            "currency": "EUR",
            "buy_rate": 185.8039,
            "sell_rate": 189.52,
            "market_type": "transaction",
            "is_active": true,
            ...
          },
          ...
        ]
      }
      
    Each item creates 1 record with category based on market_type.
    """
    
    key = "gadaa_api"
    url = "https://gadaabank.com.et/api/v1/exchange-rates"
    fetch_kind = FetchKind.HTTP_GET
    
    # Category mapping
    _CATEGORY_MAP = {
        "cash": "cash",
        "transaction": "transactional",
        "transactional": "transactional",
    }
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        if not raw or not raw.strip():
            return ParseOutcome.failed(IssueCode.EMPTY_PAYLOAD, "Empty response")
        
        # Parse JSON
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return ParseOutcome.failed(IssueCode.EMPTY_PAYLOAD, f"Invalid JSON: {e}")
        
        # Extract data array
        items = data.get("data", []) if isinstance(data, dict) else []
        
        if not items:
            return ParseOutcome.failed(IssueCode.NO_TABLE, "No data in JSON response")
        
        records = []
        issues = []
        
        for item in items:
            # Skip inactive records
            if not item.get("is_active", True):
                continue
            
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
            
            if item.get("buy_rate") is not None:
                try:
                    buy = parse_decimal(str(item["buy_rate"]))
                except ValueError:
                    issues.append(RowIssue(
                        row_ref=currency_code,
                        code=IssueCode.BAD_NUMBER,
                        detail=f"Bad buy_rate: {item['buy_rate']}",
                        severity=Severity.ERROR
                    ))
            
            if item.get("sell_rate") is not None:
                try:
                    sell = parse_decimal(str(item["sell_rate"]))
                except ValueError:
                    issues.append(RowIssue(
                        row_ref=currency_code,
                        code=IssueCode.BAD_NUMBER,
                        detail=f"Bad sell_rate: {item['sell_rate']}",
                        severity=Severity.ERROR
                    ))
            
            # Determine category from market_type
            market_type = str(item.get("market_type", "")).strip().lower()
            category = self._CATEGORY_MAP.get(market_type, "transactional")
            
            if buy is not None or sell is not None:
                rec = build_record(
                    currency_code=normalized,
                    category=category,
                    buying_rate=buy,
                    selling_rate=sell,
                    ctx=ctx
                )
                records.append(rec)
        
        records.sort(key=lambda r: (r.source_currency_code, r.category))
        
        structure_text = f"gadaa_json#{len(items)}_items"
        structure_hash = hashlib.sha256(structure_text.encode()).hexdigest()[:16]
        
        return ParseOutcome(
            records=tuple(records),
            issues=tuple(issues),
            rows_seen=len(items),
            structure_hash=structure_hash
        )


ADAPTER = GadaaAdapter()
