"""
Addis Fortune adapter - Clean architecture implementation.

Migration notes:
- Old adapter: 165 LOC with FieldStructureMixin and BankAdapter
- New adapter: ~140 LOC clean architecture
- Pattern: Livewire JSON extraction from HTML (wire:snapshot)
- Universal adapter: Can fetch any bank's rates from Addis Fortune website
- Requires slug parameter (e.g., "oromia-international-bank-sc")

Data structure in HTML:
<div wire:snapshot='{"data":{"exchanges":[[row1, row2, ...]]},...}'></div>

Each row contains:
- currency: "USD"
- currency_name: "United States Dollar"
- applicable_date: "Jan 15, 2024"
- buying/selling rates (auto-detected by field structure)
"""

import json
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from bs4 import BeautifulSoup

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


ADAPTER_KEY = "addis_fortune"
BASE_URL = "https://exchange.addisfortune.news/bank/{slug}"
STALENESS_DAYS = 2  # Skip rates older than 2 days

# Month name to number mapping
_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


class AddisFortuneAdapter:
    """
    Addis Fortune universal adapter following new architecture.
    
    This adapter can fetch exchange rates for any bank from the
    Addis Fortune website by providing the bank's slug.
    """
    
    key = ADAPTER_KEY
    # URL is dynamic based on slug, set in __init__
    fetch_kind = FetchKind.HTTP_GET
    
    def __init__(self, slug: str):
        """
        Initialize adapter with bank slug.
        
        Args:
            slug: Bank slug from Addis Fortune URL (e.g., "oromia-international-bank-sc")
        """
        self.slug = slug
        self.url = BASE_URL.format(slug=slug)
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        """
        Parse Addis Fortune HTML with embedded Livewire JSON.
        
        Returns ParseOutcome with records and any issues encountered.
        """
        issues = []
        records = []
        rows_seen = 0
        
        # Parse HTML
        soup = BeautifulSoup(raw, "lxml")
        
        # Find Livewire snapshot
        snaps = soup.find_all(attrs={"wire:snapshot": True})
        if not snaps:
            return ParseOutcome.failed(
                IssueCode.NO_TABLE,
                "No wire:snapshot found in HTML - Livewire data missing"
            )
        
        # Extract JSON from wire:snapshot attribute
        try:
            snapshot_json = snaps[0]["wire:snapshot"]
            snapshot = json.loads(snapshot_json)
        except (json.JSONDecodeError, KeyError) as e:
            return ParseOutcome.failed(
                IssueCode.BAD_JSON,
                f"Failed to parse wire:snapshot JSON: {e}"
            )
        
        # Extract exchanges data
        data = snapshot.get("data", {})
        exchanges = data.get("exchanges", [])
        
        if not exchanges or not isinstance(exchanges, list) or len(exchanges) == 0:
            return ParseOutcome.failed(
                IssueCode.NO_TABLE,
                "No exchanges data found in Livewire snapshot"
            )
        
        # Exchanges is nested: [[row1, row2, ...]]
        if not isinstance(exchanges[0], list):
            return ParseOutcome.failed(
                IssueCode.NO_TABLE,
                "Unexpected exchanges structure - expected nested list"
            )
        
        rows = exchanges[0]
        
        # Process each row
        for row_idx, row_data in enumerate(rows, start=1):
            # Row might be wrapped in another list: [row_dict] or just row_dict
            row = row_data[0] if isinstance(row_data, list) else row_data
            
            if not isinstance(row, dict):
                issues.append(RowIssue(
                    f"row {row_idx}",
                    IssueCode.BAD_JSON,
                    "Row is not a dict",
                    Severity.WARNING,
                ))
                continue
            
            rows_seen += 1
            row_ref = f"row {row_idx}"
            
            # Extract currency
            currency = str(row.get("currency", "")).strip().upper()
            if not currency:
                issues.append(RowIssue(
                    row_ref,
                    IssueCode.MISSING_CURRENCY,
                    "Missing currency code",
                    Severity.WARNING,
                ))
                continue
            
            # Parse applicable date
            applicable_date_str = row.get("applicable_date", "")
            applicable_date = self._parse_af_date(applicable_date_str)
            
            # Check staleness
            if applicable_date:
                days_old = (ctx.collection_date - applicable_date).days
                if days_old > STALENESS_DAYS:
                    issues.append(RowIssue(
                        row_ref,
                        IssueCode.STALE_DATE,
                        f"{currency}: rate is {days_old} days old (applicable_date: {applicable_date_str})",
                        Severity.WARNING,
                    ))
                    continue  # Skip stale data
            
            # Extract rates - try common field names
            # Addis Fortune typically has: buying, selling, cash_buying, cash_selling, etc.
            buying_rate = None
            selling_rate = None
            category = ctx.category or "transactional"
            
            buy_fields = (
                ["cashBuying", "transBuying", "buying", "cash_buying", "buying_rate"]
                if category == "cash"
                else ["transBuying", "cashBuying", "buying", "cash_buying", "buying_rate"]
            )
            for buy_field in buy_fields:
                if buy_field in row:
                    try:
                        buying_rate = parse_decimal(row[buy_field])
                        if buying_rate and buying_rate > 0:
                            break
                    except (ValueError, TypeError):
                        pass
            
            sell_fields = (
                ["cashSelling", "transSelling", "selling", "cash_selling", "selling_rate"]
                if category == "cash"
                else ["transSelling", "cashSelling", "selling", "cash_selling", "selling_rate"]
            )
            for sell_field in sell_fields:
                if sell_field in row:
                    try:
                        selling_rate = parse_decimal(row[sell_field])
                        if selling_rate and selling_rate > 0:
                            break
                    except (ValueError, TypeError):
                        pass
            
            # Validate rates
            if not buying_rate or not selling_rate:
                issues.append(RowIssue(
                    row_ref,
                    IssueCode.EMPTY_RATE,
                    f"{currency}: missing or invalid rates (buying={buying_rate}, selling={selling_rate})",
                    Severity.WARNING,
                ))
                continue
            
            # Build record
            record = build_record(
                currency_code=currency,
                category=category,
                buying_rate=buying_rate,
                selling_rate=selling_rate,
                ctx=ctx,
                effective_date=applicable_date or ctx.collection_date,
                effective_date_basis="source_published" if applicable_date else "collection_date_fallback",
                currency_name=row.get("currency_name"),
            )
            
            records.append(record)
        
        # Sort records by currency
        records.sort(key=lambda r: r.source_currency_code)
        
        # Compute structure hash
        structure_hash = f"addis_fortune:{self.slug}:{len(records)}"
        
        return ParseOutcome(
            records=tuple(records),
            rows_seen=rows_seen,
            issues=tuple(issues),
            structure_hash=structure_hash,
        )
    
    def _parse_af_date(self, date_str: str) -> Optional[date]:
        """
        Parse Addis Fortune date format: "Jan 15, 2024"
        
        Returns date object or None if parsing fails.
        """
        if not date_str:
            return None
        
        try:
            # Remove comma and split
            parts = date_str.replace(",", "").split()
            if len(parts) != 3:
                return None
            
            # Map month name to number
            month = _MONTH_MAP.get(parts[0].lower()[:3])
            if not month:
                return None
            
            # Build date: year, month, day
            return date(int(parts[2]), month, int(parts[1]))
        except (IndexError, ValueError):
            return None


# Default instance (can be overridden with slug)
ADAPTER = AddisFortuneAdapter(slug="default")
