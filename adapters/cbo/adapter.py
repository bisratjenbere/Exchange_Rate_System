"""
adapters/cbo/adapter.py — Cooperative Bank of Oromia (Type E wide HTML).

Parse rules (ADR-006 §6, mapping doc):
- Input: static HTML with 2 tables.
  Table 0: Cash + Transaction combined. Header row 0 embeds date ("Exchange RateOctober 10, 2026").
           Header row 1: Currency | Cash | Transaction
           Header row 2: Buying | Selling | Buying | Selling
  Table 1: Weighted Average. Headers: Currency | Weighted Average Rate | Buying | Selling
- Date extracted from table 0 header → applied to all records (both tables share the same date).
- effective_date_basis = source_published when date found; collection_date_fallback otherwise.
- Dash "-" = no trade → None.
- Currency format: "CODE - Name" — code extracted as first token before " - ".
- Partial failure: returns records + errors list. Never raises.

MIGRATION NOTE: Migrated to FieldStructureMixin for automatic category detection.
"""
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from adapters.base import HTMLTableAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin
from pipeline.category_normalizer import normalize_category

ADAPTER_KEY = "cbo_html"
SOURCE_URL = "https://coopbankoromia.com.et/daily-exchange-rates/"

_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_DATE_RE = re.compile(
    rf"({_MONTHS})\s+(\d{{1,2}}),?\s+(\d{{4}})", re.IGNORECASE
)
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


class CBOAdapter(FieldStructureMixin, HTMLTableAdapter):
    """
    Cooperative Bank of Oromia adapter with field detection.
    
    Type E adapter with 2 tables: cash+transactional combined, and weighted_average.
    Field Structure: Explicit category prefixes for table 0, generic for table 1
    """
    
    FIELD_CONFIG = {}
    
    def get_source_url(self) -> str:
        """Return CBO website URL."""
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        """Return unique adapter identifier."""
        return ADAPTER_KEY
    
    def _process_tables(self, soup: BeautifulSoup, tables: list, **options) -> ParseResult:
        """
        Extract AdapterRecords from CBO HTML tables using field detection.
        
        Args:
            soup: BeautifulSoup parsed HTML
            tables: List of table elements (expecting 2 tables)
            **options: Not used by CBO
            
        Returns:
            ParseResult with extracted records and any errors
        """
        result = ParseResult()
        
        if len(tables) < 1:
            result.add_error("table_0_cash_txn:missing")
            result.add_error("table_1_weighted_avg:missing")
            return result
        
        # Extract date from table 0 header
        effective_date = None
        try:
            effective_date = _extract_date_from_table(tables[0])
        except Exception as exc:
            result.add_error(f"date_extraction:{exc}")
        
        date_basis = "source_published" if effective_date else "collection_date_fallback"
        
        # Parse table 0 — cash + transactional
        try:
            records = self._parse_cash_txn_table(tables[0], effective_date, date_basis)
            result.records.extend(records)
        except Exception as exc:
            result.add_error(f"table_0_cash_txn:{exc}")
        
        # Parse table 1 — weighted average
        if len(tables) < 2:
            result.add_error("table_1_weighted_avg:missing")
        else:
            try:
                records = self._parse_weighted_table(tables[1], effective_date, date_basis)
                result.records.extend(records)
            except Exception as exc:
                result.add_error(f"table_1_weighted_avg:{exc}")
        
        return result
    
    def _parse_cash_txn_table(self, table, effective_date: Optional[date], date_basis: str) -> list:
        """Parse table 0 using field detection: multi-level header, cash cols 1-2, txn cols 3-4."""
        rows = table.find_all("tr")
        data_rows = [r for r in rows if _is_data_row(r)]
        if not data_rows:
            return []

        records = []
        for row in data_rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 5:
                continue
            currency_code, currency_name = _parse_currency_cell(cells[0])
            if not currency_code:
                continue

            # Create dict with explicit category prefixes
            row_dict = {
                "cash_buying": cells[1],
                "cash_selling": cells[2],
                "transactional_buying": cells[3],
                "transactional_selling": cells[4],
            }
            
            # Use field detection
            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=currency_code,
                currency_name=currency_name,
                effective_date=effective_date,
                effective_date_basis=date_basis,
                mapping_notes=["dash_equals_no_trade:TO_VERIFY"]
            )
            
            records.extend(detected_records)
        return records
    
    def _parse_weighted_table(self, table, effective_date: Optional[date], date_basis: str) -> list:
        """Parse table 1 using field detection: Currency | Buying | Selling."""
        rows = table.find_all("tr")
        data_rows = [r for r in rows if _is_data_row(r)]
        if not data_rows:
            return []

        records = []
        for row in data_rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 3:
                continue
            currency_code, currency_name = _parse_currency_cell(cells[0])
            if not currency_code:
                continue

            # Create dict with generic field names
            row_dict = {
                "buying": cells[1],
                "selling": cells[2],
            }
            
            # Use field detection
            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=currency_code,
                currency_name=currency_name,
                effective_date=effective_date,
                effective_date_basis=date_basis,
                mapping_notes=["dash_equals_no_trade:TO_VERIFY"]
            )
            
            # Context-based category override: this table is weighted_average
            for rec in detected_records:
                if rec.category == 'UNKNOWN':
                    rec.category = normalize_category("weighted_average")
            
            records.extend(detected_records)
        return records


def _extract_date_from_table(table) -> Optional[date]:
    """Extract date from first header row text like 'Exchange RateOctober 10, 2026'."""
    rows = table.find_all("tr")
    if not rows:
        return None
    header_text = rows[0].get_text(" ", strip=True)
    return _parse_date_text(header_text)


def _is_data_row(row) -> bool:
    """True if row has <td> cells (not header-only)."""
    return bool(row.find("td"))


def _parse_currency_cell(text: str) -> tuple:
    """Parse 'USD - US Dollar' → ('USD', 'US Dollar'). Returns ('', None) if unparseable."""
    text = text.strip()
    if " - " in text:
        parts = text.split(" - ", 1)
        return parts[0].strip(), parts[1].strip()
    if text:
        return text, None
    return "", None


def _parse_date_text(text: str) -> Optional[date]:
    """Parse date from text using month name pattern."""
    m = _DATE_RE.search(text)
    if not m:
        return None
    month = _MONTH_MAP.get(m.group(1).lower())
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
    
    New code should use CBOAdapter().parse().
    
    Args:
        raw_html: Raw HTML string from CBO website
        
    Returns:
        Tuple of (records, errors) for backward compatibility
    """
    adapter = CBOAdapter()
    result = adapter.parse(raw_html)
    return result.records, result.errors


def schema_fingerprint(raw_html: str) -> str:
    """
    Old function API (for backward compatibility).
    
    New code should use CBOAdapter().schema_fingerprint().
    
    Args:
        raw_html: Raw HTML string
        
    Returns:
        SHA256 hash of table structure
    """
    return CBOAdapter().schema_fingerprint(raw_html)
