"""
Tsedey Bank adapter - Clean architecture implementation.

Migration notes:
- Old adapter: 116 LOC with FieldStructureMixin and BankAdapter
- New adapter: ~150 LOC clean architecture
- Pattern: JSON records embedded in HTML (regex extraction)
- Categories: Extracted from JSON "category" field + weighted_average
- Unique approach: Uses regex to find JSON objects in HTML

Data structure in HTML:
{"id":2,"name":"US DOLLAR","code":"USD","category":"non-cash",
 "buying_rate":"162.2930","selling_rate":"164.6594",
 "weighted_average_buying":"161.8795","weighted_average_selling":"164.2311",
 "updated_at":"2024-11-26T06:30:03.000000Z"}
"""

import json
import re
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
from adapters.core.currency import normalize_currency
from adapters.transport.base import FetchKind


ADAPTER_KEY = "tsedey_html"
SOURCE_URL = "https://www.tsedeybank.com.et/"

# Regex to find JSON objects in HTML
_RECORD_RE = re.compile(r'\{"id":\d+,"name":"[^"]+","code":"[A-Z]{3}"[^}]+\}')

# Category normalization
_CATEGORY_MAP = {
    "cash": "cash",
    "non-cash": "transactional",
    "noncash": "transactional",
    "transactional": "transactional",
}


class TsedeyAdapter:
    """Tsedey Bank adapter following new architecture."""
    
    key = ADAPTER_KEY
    url = SOURCE_URL
    fetch_kind = FetchKind.HTTP_GET
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        """
        Parse Tsedey HTML with embedded JSON records.
        
        Returns ParseOutcome with records and any issues encountered.
        """
        issues = []
        records = []
        rows_seen = 0
        seen_keys = set()  # Deduplication: (currency, category)
        
        # Find all JSON records using regex
        matches = _RECORD_RE.finditer(raw)
        
        for match_idx, match in enumerate(matches, start=1):
            rows_seen += 1
            row_ref = f"record {match_idx}"
            
            # Parse JSON
            try:
                row = json.loads(match.group())
            except json.JSONDecodeError as e:
                issues.append(RowIssue(
                    row_ref,
                    IssueCode.BAD_JSON,
                    f"Invalid JSON: {e}",
                    Severity.ERROR,
                ))
                continue
            
            # Extract fields
            row_id = row.get("id")
            code = str(row.get("code", "")).strip().upper()
            category_raw = str(row.get("category", "")).strip().lower()
            
            # Normalize category
            category = _CATEGORY_MAP.get(category_raw, "transactional")
            
            # Validate currency
            if not code:
                issues.append(RowIssue(
                    row_ref,
                    IssueCode.MISSING_CURRENCY,
                    "Missing currency code",
                    Severity.ERROR,
                ))
                continue
            
            # Extract effective date from updated_at
            updated_at = row.get("updated_at", "")
            effective_date = self._parse_iso_date(updated_at) if updated_at else None
            
            # === Primary rates (buying_rate, selling_rate) ===
            buying_text = row.get("buying_rate")
            selling_text = row.get("selling_rate")
            
            if buying_text and selling_text:
                dedup_key = f"{code}:{category}"
                
                if dedup_key not in seen_keys:
                    seen_keys.add(dedup_key)
                    
                    try:
                        buying_rate = parse_decimal(buying_text)
                        selling_rate = parse_decimal(selling_text)
                        
                        if buying_rate and selling_rate and buying_rate > 0 and selling_rate > 0:
                            record = build_record(
                                currency_code=code,
                                category=category,
                                buying_rate=buying_rate,
                                selling_rate=selling_rate,
                                ctx=ctx,
                                effective_date=effective_date,
                                effective_date_basis="source_published" if effective_date else "collection_date_fallback",
                            )
                            records.append(record)
                        else:
                            issues.append(RowIssue(
                                row_ref,
                                IssueCode.BAD_NUMBER,
                                f"Invalid rates for {code}:{category} - {buying_text}/{selling_text}",
                                Severity.WARNING,
                            ))
                    except (ValueError, TypeError) as e:
                        issues.append(RowIssue(
                            row_ref,
                            IssueCode.BAD_NUMBER,
                            f"Failed to parse rates: {e}",
                            Severity.ERROR,
                        ))
            
            # === Weighted average rates (optional) ===
            w_buy_text = row.get("weighted_average_buying")
            w_sell_text = row.get("weighted_average_selling")
            
            if w_buy_text and w_sell_text:
                w_dedup_key = f"{code}:weighted_average"
                
                if w_dedup_key not in seen_keys:
                    seen_keys.add(w_dedup_key)
                    
                    try:
                        w_buying_rate = parse_decimal(w_buy_text)
                        w_selling_rate = parse_decimal(w_sell_text)
                        
                        if w_buying_rate and w_selling_rate and w_buying_rate > 0 and w_selling_rate > 0:
                            w_record = build_record(
                                currency_code=code,
                                category="weighted_average",
                                buying_rate=w_buying_rate,
                                selling_rate=w_selling_rate,
                                ctx=ctx,
                                effective_date=effective_date,
                                effective_date_basis="source_published" if effective_date else "collection_date_fallback",
                            )
                            records.append(w_record)
                    except (ValueError, TypeError):
                        # Silently skip invalid weighted average rates
                        pass
        
        if rows_seen == 0:
            return ParseOutcome.failed(
                IssueCode.NO_TABLE,
                "No JSON records found in HTML"
            )
        
        # Sort records by (currency, category)
        records.sort(key=lambda r: (r.source_currency_code, r.category))
        
        # Compute structure hash
        structure_hash = f"tsedey_html:{len(records)}:{rows_seen}"
        
        return ParseOutcome(
            records=tuple(records),
            rows_seen=rows_seen,
            issues=tuple(issues),
            structure_hash=structure_hash,
        )
    
    def _parse_iso_date(self, date_str: str) -> Optional[date]:
        """
        Parse ISO date from updated_at field.
        
        Example: '2024-11-26T06:30:03.000000Z' → date(2024, 11, 26)
        """
        if not date_str:
            return None
        try:
            # Extract YYYY-MM-DD part
            date_part = date_str.strip().split('T')[0]
            return date.fromisoformat(date_part)
        except (ValueError, AttributeError, IndexError):
            return None


ADAPTER = TsedeyAdapter()
