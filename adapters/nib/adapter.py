"""
adapters/nib/adapter.py — Nib International Bank (Type D multi-table HTML).

Parse rules:
- 3 tables: table[0]=date header, table[1]=cash+txn, table[2]=weighted_average.
- Table 0: single row with date text "Oct 12, 2026" → source_published for all records.
- Table 1: Currency | Buying | Selling | Buying | Selling
  Two buying/selling pairs — col1/2 = cash, col3/4 = transactional.
  NOTE: Website structure updated 2026-10-21 - Country column removed.
- Table 2: Country(empty) | Currency | Buying | Selling → weighted_average.
- "No Trade" → None. Country column is empty in data rows.
- Partial failure: returns (records, errors). Never raises.

MIGRATION NOTE: Migrated to FieldStructureMixin for automatic category detection.
"""
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from adapters.base import HTMLTableAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin
from pipeline.category_normalizer import normalize_category

ADAPTER_KEY = "nib_html"
SOURCE_URL = "https://www.nibbanksc.com/exchange-rate/"

_MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
_DATE_RE = re.compile(rf"({_MONTHS})\w*\s+(\d{{1,2}}),?\s+(\d{{4}})", re.IGNORECASE)
_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


class NIBAdapter(FieldStructureMixin, HTMLTableAdapter):
    """
    Nib International Bank adapter with field detection.
    
    Type D adapter (multi-table HTML with shared date).
    Field Structure: Table cells → dict with category prefixes
    - Table 1: cash_buying/cash_selling + transactional_buying/transactional_selling
    - Table 2: buying/selling → weighted_average (context-based)
    """
    
    FIELD_CONFIG = {}
    
    def get_source_url(self) -> str:
        """Return NIB website URL."""
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        """Return unique adapter identifier."""
        return ADAPTER_KEY
    
    def parse(self, raw_content: str, **options) -> ParseResult:
        """
        Parse HTML content, extract tables, and delegate to _process_tables().
        
        Overrides base class to provide NIB-specific error reporting
        when no tables are found (reports all 3 expected tables as missing).
        
        Args:
            raw_content: Raw HTML string
            **options: Additional options passed to _process_tables()
            
        Returns:
            ParseResult from _process_tables()
        """
        soup = BeautifulSoup(raw_content, "html.parser")
        tables = soup.find_all("table")
        
        # Always call _process_tables even if no tables found
        # This allows NIB-specific error reporting for all 3 expected tables
        return self._process_tables(soup, tables, **options)
    
    def _process_tables(self, soup: BeautifulSoup, tables: list, **options) -> ParseResult:
        """
        Extract AdapterRecords from NIB HTML tables using field detection.
        
        Args:
            soup: BeautifulSoup parsed HTML
            tables: List of table elements
            **options: Not used by NIB adapter
            
        Returns:
            ParseResult with extracted records and any errors
        """
        result = ParseResult()
        
        # If no tables found, report all three table categories as missing
        if not tables:
            result.add_error("table_0_date:missing")
            result.add_error("table_1_cash_txn:missing")
            result.add_error("table_2_weighted:missing")
            return result
        
        # Extract date from table 0
        effective_date = None
        try:
            effective_date = _extract_date(tables[0])
        except Exception as exc:
            result.add_error(f"date_extraction:{exc}")
        
        date_basis = "source_published" if effective_date else "collection_date_fallback"
        
        # Parse table 1 — cash + transactional
        if len(tables) >= 2:
            try:
                records = self._parse_cash_txn(tables[1], effective_date, date_basis)
                result.records.extend(records)
            except Exception as exc:
                result.add_error(f"table_1_cash_txn:{exc}")
        else:
            result.add_error("table_1_cash_txn:missing")
        
        # Parse table 2 — weighted average
        if len(tables) >= 3:
            try:
                records = self._parse_weighted(tables[2], effective_date, date_basis)
                result.records.extend(records)
            except Exception as exc:
                result.add_error(f"table_2_weighted:{exc}")
        else:
            result.add_error("table_2_weighted:missing")
        
        return result
    
    def _parse_cash_txn(self, table, effective_date, date_basis) -> list:
        """Parse cash+transactional table using field detection."""
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 5:
                continue
            currency = cells[0].strip()
            if not currency:
                continue
            
            # Create dict with category prefixes
            row_dict = {
                "cash_buying": cells[1],
                "cash_selling": cells[2],
                "transactional_buying": cells[3],
                "transactional_selling": cells[4],
            }
            
            # Use field detection
            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=currency,
                effective_date=effective_date,
                effective_date_basis=date_basis,
                mapping_notes=["website_structure_updated:2026-10-21"]
            )
            
            records.extend(detected_records)
        return records
    
    def _parse_weighted(self, table, effective_date, date_basis) -> list:
        """Parse weighted average table using field detection."""
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 4:
                continue
            currency = cells[1].strip()
            if not currency:
                continue
            
            # Create dict with generic field names
            row_dict = {
                "buying": cells[2],
                "selling": cells[3],
            }
            
            # Use field detection
            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=currency,
                effective_date=effective_date,
                effective_date_basis=date_basis
            )
            
            # Context-based category override: this table is weighted_average
            for rec in detected_records:
                if rec.category == 'UNKNOWN':
                    rec.category = normalize_category("weighted_average")
            
            records.extend(detected_records)
        return records


def _extract_date(table) -> Optional[date]:
    text = table.get_text(" ", strip=True)
    m = _DATE_RE.search(text)
    if not m:
        return None
    month = _MONTH_MAP.get(m.group(1).lower()[:3])
    if not month:
        return None
    try:
        return date(int(m.group(3)), month, int(m.group(2)))
    except ValueError:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Backward Compatibility Wrappers
# ═══════════════════════════════════════════════════════════════════════════════

def parse(raw_html: str) -> tuple:
    """
    Old function API (for backward compatibility).
    
    New code should use NIBAdapter().parse().
    
    Args:
        raw_html: Raw HTML string from NIB website
        
    Returns:
        Tuple of (records, errors) for backward compatibility
    """
    adapter = NIBAdapter()
    result = adapter.parse(raw_html)
    return result.records, result.errors


def schema_fingerprint(raw_html: str) -> str:
    """
    Old function API (for backward compatibility).
    
    New code should use NIBAdapter().schema_fingerprint().
    
    Args:
        raw_html: Raw HTML string from NIB website
        
    Returns:
        SHA256 hash of table structure
    """
    return NIBAdapter().schema_fingerprint(raw_html)
