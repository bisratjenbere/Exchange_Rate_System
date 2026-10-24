"""
adapters/dbe/adapter.py — Development Bank of Ethiopia (Type F single table).

Parse rules:
- Table 0: Currency (name) | Code | Buying | Selling. No category label → UNKNOWN.
- Table 1: same structure but empty (JS-rendered) — skip.
- Date from tablepress-table-description span → source_published → CONFIRMED identity.
- Partial failure: returns (records, errors). Never raises.

MIGRATION NOTE: Migrated to FieldStructureMixin for automatic category detection.
"""
import re
from datetime import date
from decimal import Decimal
from typing import Optional

from bs4 import BeautifulSoup

from adapters.base import HTMLTableAdapter, ParseResult
from domain.records import AdapterRecord
from field_detection.mixin import FieldStructureMixin
from pipeline.category_normalizer import normalize_category
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "dbe_html"
SOURCE_URL = "https://dbe.com.et/"

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


class DBEAdapter(FieldStructureMixin, HTMLTableAdapter):
    """
    Development Bank of Ethiopia adapter.
    
    Type F adapter (requires category parameter).
    Uses field detection for automatic category discovery.
    """
    
    FIELD_CONFIG = {}
    
    def get_source_url(self) -> str:
        """Return DBE website URL."""
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        """Return unique adapter identifier."""
        return ADAPTER_KEY
    
    def requires_category(self) -> bool:
        """Type F adapter requires category injection."""
        return True
    
    def _process_tables(self, soup: BeautifulSoup, tables: list, **options) -> ParseResult:
        """
        Extract AdapterRecords from DBE HTML tables.
        
        Args:
            soup: BeautifulSoup parsed HTML
            tables: List of table elements
            **options: Must include 'category' parameter
            
        Returns:
            ParseResult with extracted records and any errors
        """
        result = ParseResult()
        category = options.get('category', 'UNKNOWN')
        
        # Extract date from description span
        effective_date = self._parse_date_from_description(tables[0])
        
        # Parse first table (second table is JS-rendered and empty)
        try:
            # Pass self reference to helper via table object
            tables[0]._adapter_instance = self
            records = self._parse_table(tables[0], category, effective_date)
            result.records.extend(records)
        except Exception as exc:
            result.add_error(f"table_0:{exc}")
        
        return result
    
    def _parse_date_from_description(self, table) -> Optional[date]:
        """Read the tablepress-table-description span that precedes the table."""
        parent = table.parent
        span = parent.find("span", class_="tablepress-table-description") if parent else None
        if not span:
            return None
        text = span.get_text(" ", strip=True)
        m = re.search(r'(\w+)\s+(\d{1,2}),?\s+(\d{4})', text)
        if not m:
            return None
        month = _MONTHS.get(m.group(1).lower())
        if not month:
            return None
        try:
            return date(int(m.group(3)), month, int(m.group(2)))
        except ValueError:
            return None
    
    def _parse_table(self, table, category: str = "UNKNOWN", effective_date: Optional[date] = None) -> list:
        """
        Parse DBE exchange rate table.
        
        Args:
            table: BeautifulSoup table element
            category: Exchange rate category (typically "UNKNOWN" for DBE)
            effective_date: Extracted effective date or None
            
        Returns:
            List of AdapterRecords
        """
        date_basis = "source_published" if effective_date else "collection_date_fallback"
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            # col0=name(empty), col1=code, col2=buying, col3=selling
            if len(cells) < 4:
                continue
            currency_code = cells[1].strip()
            if not currency_code:
                continue
            
            # Create dict with generic field names
            row_dict = {
                "buying": cells[2],
                "selling": cells[3],
            }
            
            # Use field detection (self is passed through table parameter)
            detected_records = table._adapter_instance.detect_and_emit(
                data=row_dict,
                currency=currency_code,
                effective_date=effective_date,
                effective_date_basis=date_basis,
                mapping_notes=["category_unknown:single_pair_no_label"]
            )
            
            # Context-based category override: parameter-provided category
            for rec in detected_records:
                if rec.category == 'UNKNOWN':
                    rec.category = normalize_category(category)
            
            records.extend(detected_records)
        return records


def _safe_rate(raw) -> Optional[Decimal]:
    """Safely convert raw value to normalized Decimal rate."""
    try:
        return normalize_rate(raw)
    except ValueError:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Backward Compatibility Wrappers
# ═══════════════════════════════════════════════════════════════════════════════

def parse(raw_html: str, category: str = "UNKNOWN") -> tuple:
    """
    Old function API (for backward compatibility).
    
    New code should use DBEAdapter().parse().
    
    Args:
        raw_html: Raw HTML string from DBE website
        category: Exchange rate category (default "UNKNOWN")
        
    Returns:
        Tuple of (records, errors) for backward compatibility
    """
    adapter = DBEAdapter()
    result = adapter.parse(raw_html, category=category)
    return result.records, result.errors


def schema_fingerprint(raw_html: str) -> str:
    """
    Old function API (for backward compatibility).
    
    New code should use DBEAdapter().schema_fingerprint().
    
    Args:
        raw_html: Raw HTML string from DBE website
        
    Returns:
        SHA256 hash of table structure
    """
    return DBEAdapter().schema_fingerprint(raw_html)
