"""
adapters/omo/adapter.py — Omo Bank (Type D multi-table HTML, DD/MM/YYYY dates).

Parse rules:
- 3 tables, each with date in header row 0 (DD/MM/YYYY format).
  Table 0: Cash. Table 1: Transactional. Table 2: Weighted Average.
- Currency format: "CODE – Name" — split on " – " or " - " to get code.
- Per-table dates parsed independently. Never share dates between tables.
- "No Trade" → None.
- Partial failure: returns (records, errors). Never raises.

MIGRATION NOTE: Migrated to FieldStructureMixin for automatic category detection.
"""
import re
from datetime import date
from typing import Optional
from bs4 import BeautifulSoup

from adapters.base import HTMLTableAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin

ADAPTER_KEY = "omo_html"
SOURCE_URL = "https://omobanksc.com/"

_TABLE_CATEGORIES = {0: "cash", 1: "transactional", 2: "weighted_average"}
_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


class OmoAdapter(FieldStructureMixin, HTMLTableAdapter):
    """Omo Bank adapter with field detection - 3 tables with per-table dates."""
    
    FIELD_CONFIG = {}
    
    def get_source_url(self) -> str:
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        return ADAPTER_KEY
    
    def _process_tables(self, soup: BeautifulSoup, tables: list, **kwargs) -> ParseResult:
        """Process 3 tables from Omo Bank using field detection."""
        result = ParseResult()
        
        for idx, category in _TABLE_CATEGORIES.items():
            if idx >= len(tables):
                result.add_error(f"table_{idx}_{category}:missing")
                continue
            try:
                records = _parse_table(self, tables[idx], category)
                result.records.extend(records)
            except Exception as exc:
                result.add_error(f"table_{idx}_{category}:{exc}")
        
        return result


def _parse_table(adapter, table, category: str) -> list:
    """Parse a single table with date in header row using field detection."""
    rows = table.find_all("tr")
    if not rows:
        return []
    
    header_text = rows[0].get_text(" ", strip=True)
    effective_date = _parse_date(header_text)
    date_basis = "source_published" if effective_date else "collection_date_fallback"
    
    records = []
    for row in rows[1:]:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 4:
            continue
        currency_code, currency_name = _parse_currency(cells[1])
        if not currency_code:
            continue
        
        row_dict = {"buying": cells[2], "selling": cells[3]}
        detected_records = adapter.detect_and_emit(
            data=row_dict,
            currency=currency_code,
            currency_name=currency_name,
            effective_date=effective_date,
            effective_date_basis=date_basis
        )
        
        for rec in detected_records:
            if rec.category == 'UNKNOWN':
                rec.category = category
        
        records.extend(detected_records)
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
