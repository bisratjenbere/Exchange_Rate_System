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

MIGRATION NOTE: Migrated to use FieldStructureMixin for automatic category detection.
Converts HTML table cells into dict structure with field names for field detection.
"""
import re
from datetime import date, datetime
from typing import Optional
from bs4 import BeautifulSoup

from domain.records import AdapterRecord
from pipeline.category_normalizer import normalize_category
from adapters.base import HTMLTableAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin

ADAPTER_KEY = "oromia_html"
SOURCE_URL = "https://www.oromiabanksc.com/"
FETCH_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


class OromiaAdapter(FieldStructureMixin, HTMLTableAdapter):
    """
    Oromia Bank adapter - ninja-table with historical data.
    
    Field Structure: HTML table converted to dict
    - Buying Rate column → buying_rate field
    - Selling Rate column → selling_rate field
    - Field detection auto-discovers and assigns category (transactional)
    """
    
    # Empty config - field detection will discover buying_rate/selling_rate
    FIELD_CONFIG = {}
    
    def get_source_url(self) -> str:
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        return ADAPTER_KEY
    
    def _process_tables(self, soup: BeautifulSoup, tables: list, **kwargs) -> ParseResult:
        """Process ninja-table from Oromia Bank using field detection."""
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
        
        # Parse all rows into structured data
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
                
                # Convert table cells to dict for field detection
                row_dict = {
                    "buying_rate": buying_text,
                    "selling_rate": selling_text,
                    "date": str(row_date),
                    "currency": currency
                }
                parsed.append((row_date, currency, row_dict))
                
            except Exception as exc:
                result.add_error(f"row:{cells}:{exc}")
        
        if not parsed:
            result.add_error("no_valid_rows")
            return result
        
        # Only emit the most recent date
        max_date = max(r[0] for r in parsed)
        for row_date, currency, row_dict in parsed:
            if row_date != max_date:
                continue
            
            # Use field detection to automatically discover and emit records
            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=currency,
                effective_date=max_date,
                effective_date_basis="source_published",
                source_record_id=f"{max_date}:{currency}",
                source_publication_id=str(max_date)
            )
            
            # Post-process: Oromia only publishes transactional rates
            for rec in detected_records:
                if rec.category == 'UNKNOWN':
                    rec.category = normalize_category("transactional")
            
            result.records.extend(detected_records)
        
        return result


def _parse_date(raw: str) -> Optional[date]:
    """Parse date from formats like 'Oct 10, 2026' or '2026-10-10'."""
    if not raw:
        return None
    # Formats seen: "Oct 10, 2026", "2026-10-10"
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
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

