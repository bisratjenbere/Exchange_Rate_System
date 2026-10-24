"""
adapters/boa/adapter.py — Bank of Abyssinia (Type E, SSL verify=False).

Parse rules:
- Single table. Row 0 contains date ("October 12, 2026") → source_published.
- Section headers "Cash Rates" / "Transactional Rates" divide the table into sections.
- Each section has a sub-header row then data rows.
- Currency code only (no name). Columns: Currency type | Buying Rate | Selling Rate.
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

ADAPTER_KEY = "boa_html"
SOURCE_URL = "https://www.bankofabyssinia.com/exchange-rate-2/"
SSL_VERIFY = False

_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_DATE_RE = re.compile(rf"({_MONTHS})\s+(\d{{1,2}}),?\s+(\d{{4}})", re.IGNORECASE)
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


class BOAAdapter(FieldStructureMixin, HTMLTableAdapter):
    """
    Bank of Abyssinia adapter with field detection.
    
    Type E adapter with section headers dividing a single table into cash and transactional sections.
    Field Structure: Generic fields + section-based category context
    """
    
    FIELD_CONFIG = {}
    
    def get_source_url(self) -> str:
        """Return BOA website URL."""
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        """Return unique adapter identifier."""
        return ADAPTER_KEY
    
    def _process_tables(self, soup: BeautifulSoup, tables: list, **options) -> ParseResult:
        """
        Extract AdapterRecords from BOA HTML table using field detection.
        
        Args:
            soup: BeautifulSoup parsed HTML
            tables: List of table elements (expecting 1 table)
            **options: Not used by BOA
            
        Returns:
            ParseResult with extracted records and any errors
        """
        result = ParseResult()
        
        if not tables:
            result.add_error("table_0:missing")
            return result
        
        try:
            records = self._parse_table(tables[0])
            result.records.extend(records)
        except Exception as exc:
            result.add_error(f"table_0:{exc}")
        
        return result
    
    def _parse_table(self, table) -> list:
        """Parse BOA single table with section headers using field detection."""
        rows = table.find_all("tr")
        effective_date = None
        current_category = None
        records = []

        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if not cells or all(c == "" for c in cells):
                continue

            text = " ".join(cells).strip()

            # Date row
            if effective_date is None:
                d = _parse_date(text)
                if d:
                    effective_date = d
                    continue

            # Section header row
            cat = _detect_section(text)
            if cat:
                current_category = cat
                continue

            # Sub-header row (contains "Buying" / "Selling" labels)
            if any("buying" in c.lower() or "selling" in c.lower() for c in cells):
                continue

            # Data row
            if current_category is None:
                continue
            currency = cells[0].strip()
            if not currency or len(cells) < 3:
                continue
            
            # Create dict with generic field names
            row_dict = {
                "buying": cells[1],
                "selling": cells[2],
            }
            
            # Use field detection
            date_basis = "source_published" if effective_date else "collection_date_fallback"
            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=currency,
                effective_date=effective_date,
                effective_date_basis=date_basis,
                mapping_notes=["ssl_verify_false:access_finding_recorded"]
            )
            
            # Context-based category override: section header determines category
            for rec in detected_records:
                if rec.category == 'UNKNOWN':
                    rec.category = normalize_category(current_category)
            
            records.extend(detected_records)

        return records


def _detect_section(text: str) -> Optional[str]:
    """
    Detect section header using category normalizer.
    
    Handles variations like:
    - "Cash Rates" → cash
    - "Transaction Rates" → transactional  
    - "Transactional Rates" → transactional
    """
    if not text or "rate" not in text.lower():
        return None
    
    # Try to normalize the text to get a category
    category = normalize_category(text)
    
    # Only return if it's a recognized category (not UNKNOWN)
    if category and category != "UNKNOWN":
        return category
    
    return None


def _parse_date(text: str) -> Optional[date]:
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
    
    New code should use BOAAdapter().parse().
    
    Args:
        raw_html: Raw HTML string from BOA website
        
    Returns:
        Tuple of (records, errors) for backward compatibility
    """
    adapter = BOAAdapter()
    result = adapter.parse(raw_html)
    return result.records, result.errors


def schema_fingerprint(raw_html: str) -> str:
    """
    Old function API (for backward compatibility).
    
    New code should use BOAAdapter().schema_fingerprint().
    
    Args:
        raw_html: Raw HTML string
        
    Returns:
        SHA256 hash of table structure
    """
    return BOAAdapter().schema_fingerprint(raw_html)
