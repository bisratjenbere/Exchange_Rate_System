"""
adapters/oromia/adapter.py — Oromia Bank (HTML ninja-table).

Fetch: GET https://www.oromiabanksc.com/
       Full browser headers required (88KB response).

The homepage embeds a ninja-table (id="footable_12396") with historical
exchange rate rows. Each row: Date | Currency | Buying Rate | Selling Rate.
"No Trade" values are skipped. Only the most recent date's rows are emitted.

Parse rules:
- Filter rows to max(date) found in the table.
- "No Trade" buying or selling → skip that row.
- Category: transactional (only category published).
- Date basis: source_published (date is in each row).
- Partial failure: returns (records, errors). Never raises.
"""
import re
from datetime import date
from decimal import Decimal
from typing import Optional
from bs4 import BeautifulSoup

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate
from adapters.base import HTMLTableAdapter, ParseResult

ADAPTER_KEY = "oromia_html"
SOURCE_URL = "https://www.oromiabanksc.com/"
FETCH_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


class OromiaAdapter(HTMLTableAdapter):
    """Oromia Bank adapter - ninja-table with historical data, filters to most recent date."""
    
    def get_source_url(self) -> str:
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        return ADAPTER_KEY
    
    def _process_tables(self, soup: BeautifulSoup, tables: list, **kwargs) -> ParseResult:
        """Process ninja-table from Oromia Bank, filtering to most recent date."""
        result = ParseResult()
        
        # Find specific ninja-table
        table = soup.find("table", {"id": "footable_12396"})
        if table is None:
            # Try any table with exchange rate data
            table = soup.find("table", id=re.compile(r"footable_"))
        if table is None:
            result.add_error("table_not_found")
            return result
        
        rows = table.find_all("tr")
        if len(rows) < 2:
            result.add_error("no_data_rows")
            return result
        
        # Parse all rows into (date, currency, buying, selling)
        parsed = []
        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) < 4:
                continue
            try:
                row_date = _parse_date(cells[0])
                if row_date is None:
                    continue
                currency = cells[1].strip()
                buying_text = cells[2].strip()
                selling_text = cells[3].strip()
                if not currency or buying_text == "No Trade" or selling_text == "No Trade":
                    continue
                buying = _safe_rate(buying_text)
                selling = _safe_rate(selling_text)
                if buying is None and selling is None:
                    continue
                parsed.append((row_date, currency, buying, selling, buying_text, selling_text))
            except Exception as exc:
                result.add_error(f"row:{cells}:{exc}")
        
        if not parsed:
            result.add_error("no_valid_rows")
            return result
        
        # Only emit the most recent date
        max_date = max(r[0] for r in parsed)
        for row_date, currency, buying, selling, buy_text, sell_text in parsed:
            if row_date != max_date:
                continue
            result.records.append(AdapterRecord(
                source_currency_code=currency,
                category="transactional",
                buying_rate=buying,
                selling_rate=selling,
                source_rate_text=f"{buy_text}/{sell_text}",
                effective_date=max_date,
                effective_date_basis="source_published",
                source_record_key=f"{max_date}:{currency}",
                source_publication_key=str(max_date),
                unit_multiplier=1,
                raw_excerpt={"date": str(max_date), "currency": currency,
                             "buying": buy_text, "selling": sell_text},
                mapping_notes=[],
            ))
        
        return result


def _parse_date(raw: str) -> Optional[date]:
    """Parse date from formats like 'Oct 10, 2026' or '2026-10-10'."""
    if not raw:
        return None
    # Formats seen: "Oct 10, 2026", "2026-10-10"
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            from datetime import datetime
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _safe_rate(raw) -> Optional[Decimal]:
    """Convert raw rate string to Decimal, returning None on failure."""
    if not raw or str(raw).strip() in ("", "No Trade", "-", "N/A"):
        return None
    try:
        return normalize_rate(raw)
    except ValueError:
        return None


# ============================================================================
# MODULE-LEVEL WRAPPER FUNCTIONS FOR BACKWARD COMPATIBILITY
# ============================================================================

_adapter_instance = OromiaAdapter()

def parse(raw_html: str) -> tuple:
    """Parse Oromia Bank HTML into records. Module-level wrapper."""
    result = _adapter_instance.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    """Generate schema fingerprint. Module-level wrapper."""
    return _adapter_instance.schema_fingerprint(raw_html)
