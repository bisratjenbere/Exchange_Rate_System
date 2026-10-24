"""
adapters/hibret/adapter.py — Hibret Bank.

MIGRATION NOTE: Migrated to FieldStructureMixin for automatic category detection.
"""
import re
from datetime import datetime, date
from typing import Optional
from bs4 import BeautifulSoup

from adapters.base import HTMLTableAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin
from pipeline.category_normalizer import normalize_category

ADAPTER_KEY = "hibret_html"
SOURCE_URL = "https://www.hibretbank.com.et/about/exchange-rate/"
SSL_VERIFY = False

# Non-ISO labels the bank uses on their page
_CODE_ALIASES = {
    "CHINA": "CNY",
    "CHIN": "CNY",
    "CHINESE": "CNY",
}


class HibretAdapter(FieldStructureMixin, HTMLTableAdapter):
    """Hibret Bank adapter with field detection - single table with cash and transactional columns."""
    
    FIELD_CONFIG = {}
    
    def get_source_url(self) -> str:
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        return ADAPTER_KEY
    
    def _process_tables(self, soup: BeautifulSoup, tables: list, **kwargs) -> ParseResult:
        """Process single table from Hibret Bank with date extraction."""
        result = ParseResult()
        
        effective_date = _parse_date(soup)
        date_basis = "source_published" if effective_date else "collection_date_fallback"
        
        try:
            records = self._parse_cash_txn_table(tables[0], effective_date, date_basis)
            result.records.extend(records)
        except Exception as exc:
            result.add_error(f"table_0_cash_txn:{exc}")
        
        return result
    
    def _parse_cash_txn_table(self, table, effective_date, date_basis) -> list:
        """Parse table with cash and transactional columns using field detection."""
        rows = table.find_all("tr")
        data_rows = [r for r in rows if r.find("td")]
        if not data_rows:
            return []
        records = []
        for row in data_rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 6:
                continue
            raw = cells[1].strip()
            if not raw:
                continue
            m = re.match(r'^([A-Z]{3})\b', raw, re.IGNORECASE)
            currency_code = m.group(1).upper() if m else _CODE_ALIASES.get(raw.upper())
            if not currency_code:
                continue
            
            # Create dict with category prefixes
            row_dict = {
                "cash_buying": cells[2],
                "cash_selling": cells[3],
                "transactional_buying": cells[4],
                "transactional_selling": cells[5],
            }
            
            # Use field detection
            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=currency_code,
                effective_date=effective_date,
                effective_date_basis=date_basis,
                mapping_notes=["ssl_verify_false:access_finding_recorded"]
            )
            
            records.extend(detected_records)
        return records


def _parse_date(soup) -> Optional[date]:
    """Extract date from page text in format like 'Jan 15, 2024'."""
    text = soup.get_text(" ")
    m = re.search(r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s*\d{4}', text)
    if m:
        raw = re.sub(r'\s+', ' ', m.group(0).strip())
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y"):
            try: 
                return datetime.strptime(raw, fmt).date()
            except ValueError: 
                pass
    return None


# ============================================================================
# MODULE-LEVEL WRAPPER FUNCTIONS FOR BACKWARD COMPATIBILITY
# ============================================================================

_adapter_instance = HibretAdapter()

def parse(raw_html: str) -> tuple:
    """Parse Hibret Bank HTML into records. Module-level wrapper."""
    result = _adapter_instance.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    """Generate schema fingerprint. Module-level wrapper."""
    return _adapter_instance.schema_fingerprint(raw_html)
