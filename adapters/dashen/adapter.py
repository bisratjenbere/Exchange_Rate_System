"""
adapters/dashen/adapter.py — Dashen Bank (Type D, multi-table HTML).

Parse rules (ADR-006 §6, mapping doc):
- Input: static HTML page with exactly 3 <table> elements.
  Table 0 = transactional, Table 1 = cash, Table 2 = weighted_average.
- Each table is parsed independently. Per-table dates are never shared.
- Table 2 header embeds the effective date: "Weighted Average Rate on <Month DD, YYYY>".
- Tables 0 and 1 have no source-published date → effective_date_basis=collection_date_fallback
  → identity_status=ambiguous (fallback dates never participate in identity, LOCKED rule).
- Table 2 date parsed → effective_date_basis=source_published → identity_status=derived.
- Spread column (last column) is ignored.
- "No Trade" / "-" / empty → None. No zeros observed but sentinel rule applies.
- Partial failure: if one table is missing/malformed, emit what was parsed and record the error.
  Never apply values from one table to another.

MIGRATION NOTE: Migrated to use FieldStructureMixin for automatic category detection.
Column headers are converted to field names, then field detection discovers pairs.
Table position determines category context for field override.
"""
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from adapters.base import HTMLTableAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin
from pipeline.category_normalizer import normalize_category

ADAPTER_KEY = "dashen_html"
SOURCE_URL = "https://dashenbanksc.com/daily-exchange-rates/"

# Table index → category (for context-based override)
_TABLE_CATEGORIES = {0: "transactional", 1: "cash", 2: "weighted_average"}

# Regex to extract date from weighted average header
_DATE_RE = re.compile(
    r"on\s+([A-Za-z]+ \d{1,2},\s*\d{4})", re.IGNORECASE
)
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


class DashenAdapter(FieldStructureMixin, HTMLTableAdapter):
    """
    Dashen Bank adapter with field detection.
    
    Field Structure: Table columns → dict fields
    - Column headers converted to field names (e.g., "Transaction Buying" → "transaction_buying")
    - Field detection discovers buying/selling pairs
    - Table position provides category context for UNKNOWN override
    """
    
    # Empty config - field detection will discover from column headers
    FIELD_CONFIG = {}
    
    def get_source_url(self) -> str:
        """Return Dashen Bank website URL."""
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        """Return unique adapter identifier."""
        return ADAPTER_KEY
    
    def parse(self, raw_content: str, **options) -> ParseResult:
        """Parse HTML content and extract tables."""
        soup = BeautifulSoup(raw_content, "html.parser")
        tables = soup.find_all("table")
        return self._process_tables(soup, tables, **options)
    
    def _process_tables(self, soup: BeautifulSoup, tables: list, **options) -> ParseResult:
        """Extract AdapterRecords from Dashen HTML tables using field detection."""
        result = ParseResult()
        
        # Extract global "Applicable on" date (applies to all tables)
        global_date = self._extract_global_date(soup)
        
        # If no tables found, report all three table categories as missing
        if not tables:
            for idx, category in _TABLE_CATEGORIES.items():
                result.add_error(f"table_{idx}_{category}:missing")
            return result
        
        # Parse each table by index
        for idx, expected_category in _TABLE_CATEGORIES.items():
            if idx >= len(tables):
                result.add_error(f"table_{idx}_{expected_category}:missing")
                continue
            try:
                table_records = self._parse_table(tables[idx], idx, expected_category, global_date)
                result.records.extend(table_records)
            except Exception as exc:
                result.add_error(f"table_{idx}_{expected_category}:{exc}")
        
        return result
    
    def _extract_global_date(self, soup: BeautifulSoup) -> Optional[date]:
        """
        Extract global 'Applicable on October 24, 2026' date from page.
        
        This date applies to all tables on the page.
        """
        # Search for h4 tag containing "Applicable on"
        for tag in soup.find_all(['h4', 'h3', 'h2', 'p', 'div']):
            text = tag.get_text(strip=True)
            if 'applicable on' in text.lower():
                # Extract date from "Applicable on October 24, 2026"
                match = re.search(r'([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})', text)
                if match:
                    try:
                        month_name, day, year = match.groups()
                        month = _MONTH_MAP.get(month_name.lower())  # Use full month name
                        if month:
                            return date(int(year), month, int(day))
                    except (ValueError, KeyError):
                        pass
        return None
    
    def _parse_table(self, table, idx: int, expected_category: str, global_date: Optional[date] = None) -> list:
        """Parse a single Dashen table using field detection."""
        rows = table.find_all("tr")
        if not rows:
            return []
        
        if expected_category == "weighted_average":
            return self._parse_weighted_table(rows, expected_category, global_date)
        else:
            return self._parse_standard_table(rows, expected_category, global_date)
    
    def _parse_standard_table(self, rows, expected_category: str, global_date: Optional[date] = None) -> list:
        """
        Parse transactional or cash table using field detection.
        
        Uses global_date if available, otherwise falls back to collection_date_fallback.
        """
        # Extract header and create field name mapping
        header_row = rows[0]
        headers = [c.get_text(strip=True) for c in header_row.find_all(["th", "td"])]
        
        # Convert headers to field names
        field_names = [_header_to_field_name(h) for h in headers]
        
        # Use global date if available
        effective_date = global_date
        date_basis = "source_published" if effective_date else "collection_date_fallback"
        
        records = []
        for row in rows[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
            if len(cells) < 2:
                continue
            
            currency_code = cells[0].strip()
            currency_name = cells[1].strip() if len(cells) > 1 else None
            if not currency_code:
                continue
            
            # Create dict from cells using field names
            row_dict = {}
            for i, cell_value in enumerate(cells):
                if i < len(field_names) and field_names[i]:
                    row_dict[field_names[i]] = cell_value
            
            # Use field detection
            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=currency_code,
                currency_name=currency_name or None,
                effective_date=effective_date,
                effective_date_basis=date_basis
            )
            
            # Context-based category override
            for rec in detected_records:
                if rec.category == 'UNKNOWN':
                    rec.category = normalize_category(expected_category)
            
            records.extend(detected_records)
        
        return records
    
    def _parse_weighted_table(self, rows, expected_category: str, global_date: Optional[date] = None) -> list:
        """Parse weighted average table — date embedded in header, or use global_date."""
        if len(rows) < 3:
            return []
        
        # Row 0: merged header with date
        # Row 1: Buying | Selling sub-header (only 2 columns)
        # Row 2+: Currency Code | Currency Name | Buying | Selling (4 columns)
        header_text = rows[0].get_text(" ", strip=True)
        
        # Try to extract date from weighted average header first
        table_specific_date = _extract_date(header_text)
        
        # Prefer table-specific date, fall back to global date
        effective_date = table_specific_date or global_date
        date_basis = "source_published" if effective_date else "collection_date_fallback"
        
        records = []
        for row in rows[2:]:
            cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
            if len(cells) < 4:
                continue
            
            currency_code = cells[0].strip()
            currency_name = cells[1].strip() if len(cells) > 1 else None
            if not currency_code:
                continue
            
            # Create dict with explicit field names based on table structure
            # Columns: 0=Currency Code, 1=Currency Name, 2=Buying, 3=Selling
            row_dict = {
                "buying": cells[2],
                "selling": cells[3],
                "header_text": header_text
            }
            
            # Use field detection
            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=currency_code,
                currency_name=currency_name or None,
                effective_date=effective_date,
                effective_date_basis=date_basis,
                mapping_notes=(
                    ["date_from_weighted_avg_header:source_published"]
                    if effective_date else
                    ["date_missing_from_weighted_avg_header:collection_date_fallback"]
                )
            )
            
            # Context-based category override
            for rec in detected_records:
                if rec.category == 'UNKNOWN':
                    rec.category = normalize_category(expected_category)
            
            records.extend(detected_records)
        
        return records


def _header_to_field_name(header: str) -> str:
    """
    Convert column header to field name for detection.
    
    Examples:
        "Transaction Buying" → "transaction_buying"
        "Cash Selling" → "cash_selling"
        "Buying" → "buying"
        "Selling" → "selling"
    """
    # Normalize: lowercase, replace spaces with underscores
    field = header.lower().strip()
    field = re.sub(r'\s+', '_', field)
    # Remove special characters except underscores
    field = re.sub(r'[^\w_]', '', field)
    return field


def _extract_date(text: str) -> Optional[date]:
    """Extract date from 'Weighted Average Rate on October 09, 2026'."""
    m = _DATE_RE.search(text)
    if not m:
        return None
    date_str = m.group(1).strip()
    parts = re.sub(r'[\s,]+', ' ', date_str).split()
    if len(parts) < 3:
        return None
    month_name = parts[0].lower()
    month = _MONTH_MAP.get(month_name)
    if not month:
        return None
    try:
        day = int(parts[1])
        year = int(parts[2])
        return date(year, month, day)
    except (ValueError, IndexError):
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Backward Compatibility Wrappers
# ═══════════════════════════════════════════════════════════════════════════════

def parse(raw_html: str) -> tuple:
    """Old function API (for backward compatibility)."""
    adapter = DashenAdapter()
    result = adapter.parse(raw_html)
    return result.records, result.errors


def schema_fingerprint(raw_html: str) -> str:
    """Old function API (for backward compatibility)."""
    return DashenAdapter().schema_fingerprint(raw_html)

