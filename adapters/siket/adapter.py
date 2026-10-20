"""
adapters/siket/adapter.py — Siket Bank (wide HTML table).
"""
import re
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from bs4 import BeautifulSoup

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate
from adapters.base import HTMLTableAdapter, ParseResult

ADAPTER_KEY = "siket_html"
SOURCE_URL = "https://siketbank.com/exchange-rate"

_CODE_FIX = {"US": "USD"}
_CATEGORIES = [("cash", 1, 2), ("transactional", 3, 4), ("weighted_average", 5, 6)]


class SiketAdapter(HTMLTableAdapter):
    """Siket Bank adapter - wide table with cash, transactional, and weighted_average columns."""
    
    def get_source_url(self) -> str:
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        return ADAPTER_KEY
    
    def _process_tables(self, soup: BeautifulSoup, tables: list, **kwargs) -> ParseResult:
        """Process wide table from Siket Bank with date extraction."""
        result = ParseResult()
        
        effective_date = _parse_date(soup)
        date_basis = "source_published" if effective_date else "collection_date_fallback"
        
        try:
            records = _parse_table(tables[0], effective_date, date_basis)
            result.records.extend(records)
        except Exception as exc:
            result.add_error(f"table_0:{exc}")
        
        return result


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


def _parse_table(table, effective_date, date_basis) -> list:
    """Parse wide table with cash, transactional, and weighted_average columns."""
    rows = [r for r in table.find_all("tr") if r.find("td")]
    records = []
    for row in rows:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 5:
            continue
        raw_code = cells[0].strip()
        code = _CODE_FIX.get(raw_code, raw_code)
        if not code:
            continue
        for category, bi, si in _CATEGORIES:
            if len(cells) <= si:
                continue
            buying = _safe_rate(cells[bi])
            selling = _safe_rate(cells[si])
            if buying is None and selling is None:
                continue
            records.append(AdapterRecord(
                source_currency_code=code,
                category=category,
                buying_rate=buying,
                selling_rate=selling,
                source_rate_text=f"{cells[bi]}/{cells[si]}",
                effective_date=effective_date,
                effective_date_basis=date_basis,
                source_record_key=None,
                source_publication_key=str(effective_date) if effective_date else None,
                unit_multiplier=1,
                raw_excerpt={"currency": code, "buying": cells[bi], "selling": cells[si]},
                mapping_notes=[],
            ))
    return records


def _safe_rate(raw) -> Optional[Decimal]:
    """Convert raw rate string to Decimal, returning None on failure."""
    try:
        return normalize_rate(raw)
    except ValueError:
        return None


# ============================================================================
# MODULE-LEVEL WRAPPER FUNCTIONS FOR BACKWARD COMPATIBILITY
# ============================================================================

_adapter_instance = SiketAdapter()

def parse(raw_html: str) -> tuple:
    """Parse Siket Bank HTML into records. Module-level wrapper."""
    result = _adapter_instance.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    """Generate schema fingerprint. Module-level wrapper."""
    return _adapter_instance.schema_fingerprint(raw_html)
