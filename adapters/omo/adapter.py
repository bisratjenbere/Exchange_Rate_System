"""
adapters/omo/adapter.py — Omo Bank (Type D multi-table HTML, DD/MM/YYYY dates).

Parse rules:
- 3 tables, each with date in header row 0 (DD/MM/YYYY format).
  Table 0: Cash. Table 1: Transactional. Table 2: Weighted Average.
- Currency format: "CODE – Name" — split on " – " or " - " to get code.
- Per-table dates parsed independently. Never share dates between tables.
- "No Trade" → None.
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

ADAPTER_KEY = "omo_html"
SOURCE_URL = "https://omobanksc.com/"

_TABLE_CATEGORIES = {0: "cash", 1: "transactional", 2: "weighted_average"}
_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


class OmoAdapter(HTMLTableAdapter):
    """Omo Bank adapter - 3 tables with per-table dates in DD/MM/YYYY format."""
    
    def get_source_url(self) -> str:
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        return ADAPTER_KEY
    
    def _process_tables(self, soup: BeautifulSoup, tables: list, **kwargs) -> ParseResult:
        """Process 3 tables from Omo Bank with per-table dates."""
        result = ParseResult()
        
        for idx, category in _TABLE_CATEGORIES.items():
            if idx >= len(tables):
                result.add_error(f"table_{idx}_{category}:missing")
                continue
            try:
                records = _parse_table(tables[idx], category)
                result.records.extend(records)
            except Exception as exc:
                result.add_error(f"table_{idx}_{category}:{exc}")
        
        return result


def _parse_table(table, category: str) -> list:
    """Parse a single table with date in header row."""
    rows = table.find_all("tr")
    if not rows:
        return []
    
    # Row 0: date header
    header_text = rows[0].get_text(" ", strip=True)
    effective_date = _parse_date(header_text)
    date_basis = "source_published" if effective_date else "collection_date_fallback"
    
    records = []
    for row in rows[1:]:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        # col0=empty, col1="CODE – Name", col2=buying, col3=selling
        if len(cells) < 4:
            continue
        currency_code, currency_name = _parse_currency(cells[1])
        if not currency_code:
            continue
        buying = _safe_rate(cells[2])
        selling = _safe_rate(cells[3])
        if buying is None and selling is None:
            continue
        records.append(AdapterRecord(
            source_currency_code=currency_code,
            currency_name=currency_name,
            category=category,
            buying_rate=buying,
            selling_rate=selling,
            source_rate_text=f"{cells[2]}/{cells[3]}",
            effective_date=effective_date,
            effective_date_basis=date_basis,
            source_record_key=None,
            source_publication_key=None,
            unit_multiplier=1,
            raw_excerpt={"currency": cells[1], "buying": cells[2], "selling": cells[3]},
            mapping_notes=[],
        ))
    return records


def _parse_currency(text: str) -> tuple:
    """'USD – US Dollar' → ('USD', 'US Dollar')."""
    for sep in (" \u2013 ", " - "):
        if sep in text:
            parts = text.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    text = text.strip()
    return (text, None) if text else ("", None)


def _parse_date(text: str) -> Optional[date]:
    """Parse date from DD/MM/YYYY format."""
    m = _DATE_RE.search(text)
    if not m:
        return None
    try:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return date(year, month, day)
    except ValueError:
        return None


def _safe_rate(raw) -> Optional[Decimal]:
    """Convert raw rate string to Decimal, returning None on failure."""
    try:
        return normalize_rate(raw)
    except ValueError:
        return None


# ============================================================================
# MODULE-LEVEL WRAPPER FUNCTIONS FOR BACKWARD COMPATIBILITY
# ============================================================================

_adapter_instance = OmoAdapter()

def parse(raw_html: str) -> tuple:
    """Parse Omo Bank HTML into records. Module-level wrapper."""
    result = _adapter_instance.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    """Generate schema fingerprint. Module-level wrapper."""
    return _adapter_instance.schema_fingerprint(raw_html)
