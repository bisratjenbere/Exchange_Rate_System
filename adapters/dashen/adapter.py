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
"""
import re
from datetime import date
from decimal import Decimal
from typing import Optional

from bs4 import BeautifulSoup

from adapters.base import HTMLTableAdapter, ParseResult
from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "dashen_html"
SOURCE_URL = "https://dashenbanksc.com/daily-exchange-rates/"

# Table index → category
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


class DashenAdapter(HTMLTableAdapter):
    """
    Dashen Bank adapter.
    
    Type D adapter (multi-table HTML with per-table categories).
    Parses HTML with 3 tables: transactional, cash, weighted_average.
    Each table is parsed independently with its own effective date.
    """
    
    def get_source_url(self) -> str:
        """Return Dashen Bank website URL."""
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        """Return unique adapter identifier."""
        return ADAPTER_KEY
    
    def parse(self, raw_content: str, **options) -> ParseResult:
        """
        Parse HTML content, extract tables, and delegate to _process_tables().
        
        Overrides base class to provide Dashen-specific error reporting
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
        # This allows Dashen-specific error reporting for all 3 expected tables
        return self._process_tables(soup, tables, **options)
    
    def _process_tables(self, soup: BeautifulSoup, tables: list, **options) -> ParseResult:
        """
        Extract AdapterRecords from Dashen HTML tables.
        
        Args:
            soup: BeautifulSoup parsed HTML
            tables: List of table elements
            **options: Not used by Dashen adapter
            
        Returns:
            ParseResult with extracted records and any errors
        """
        result = ParseResult()
        
        # If no tables found, report all three table categories as missing
        if not tables:
            for idx, category in _TABLE_CATEGORIES.items():
                result.add_error(f"table_{idx}_{category}:missing")
            return result
        
        # Parse each table by index
        # Note: Transactional/cash tables have NO source-published date
        # Only weighted_average table has date embedded in its header
        for idx, category in _TABLE_CATEGORIES.items():
            if idx >= len(tables):
                result.add_error(f"table_{idx}_{category}:missing")
                continue
            try:
                table_records = self._parse_table(tables[idx], idx, category)
                result.records.extend(table_records)
            except Exception as exc:
                result.add_error(f"table_{idx}_{category}:{exc}")
        
        return result
    
    def _parse_table(self, table, idx: int, category: str) -> list:
        """
        Parse a single Dashen table based on its category.
        
        Args:
            table: BeautifulSoup table element
            idx: Table index (0, 1, or 2)
            category: Table category (transactional, cash, or weighted_average)
            
        Returns:
            List of AdapterRecords
        """
        rows = table.find_all("tr")
        if not rows:
            return []
        if category == "weighted_average":
            return self._parse_weighted_table(rows)
        else:
            return self._parse_standard_table(rows, category)
    
    def _parse_standard_table(self, rows, category: str) -> list:
        """
        Parse transactional or cash table.
        
        Note: These tables have NO source-published date, so effective_date=None
        and effective_date_basis=collection_date_fallback always.
        """
        header_cells = [c.get_text(strip=True).lower() for c in rows[0].find_all(["th", "td"])]
        buy_idx = _find_col(header_cells, ["transaction buying", "cash buying", "buying"])
        sell_idx = _find_col(header_cells, ["transaction selling", "cash selling", "selling"])
        if buy_idx is None or sell_idx is None:
            raise ValueError(f"Cannot find buying/selling columns in header: {header_cells}")

        # Transactional/cash tables have no source-published date
        effective_date = None
        date_basis = "collection_date_fallback"

        records = []
        for row in rows[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
            if len(cells) < max(buy_idx, sell_idx) + 1:
                continue
            currency_code = cells[0].strip()
            currency_name = cells[1].strip() if len(cells) > 1 else None
            if not currency_code:
                continue
            buying = _safe_rate(cells[buy_idx])
            selling = _safe_rate(cells[sell_idx])
            if buying is None and selling is None:
                continue
            records.append(AdapterRecord(
                source_currency_code=currency_code,
                currency_name=currency_name or None,
                category=category,
                buying_rate=buying,
                selling_rate=selling,
                source_rate_text=f"{cells[buy_idx]}/{cells[sell_idx]}",
                effective_date=effective_date,
                effective_date_basis=date_basis,
                source_record_key=None,
                source_publication_key=None,
                raw_excerpt={"currency": currency_code, "buying": cells[buy_idx], "selling": cells[sell_idx]},
                mapping_notes=[],
            ))
        return records
    
    def _parse_weighted_table(self, rows) -> list:
        """Parse weighted average table — date embedded in row 0 header cell."""
        # Row 0: merged header with date text
        # Row 1: Buying | Selling sub-header
        # Row 2+: data
        if len(rows) < 3:
            return []

        header_text = rows[0].get_text(" ", strip=True)
        effective_date = _extract_date(header_text)
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

            buying = _safe_rate(cells[2])
            selling = _safe_rate(cells[3])
            if buying is None and selling is None:
                continue

            records.append(AdapterRecord(
                source_currency_code=currency_code,
                currency_name=currency_name or None,
                category="weighted_average",
                buying_rate=buying,
                selling_rate=selling,
                source_rate_text=f"{cells[2]}/{cells[3]}",
                effective_date=effective_date,
                effective_date_basis=date_basis,
                source_record_key=None,
                source_publication_key=None,
                raw_excerpt={"currency": currency_code, "buying": cells[2], "selling": cells[3],
                             "header_text": header_text},
                mapping_notes=(
                    ["date_from_weighted_avg_header:source_published"]
                    if effective_date else
                    ["date_missing_from_weighted_avg_header:collection_date_fallback"]
                ),
            ))
        return records


def _extract_date(text: str) -> Optional[date]:
    """Extract date from 'Weighted Average Rate on October 09, 2026'."""
    m = _DATE_RE.search(text)
    if not m:
        return None
    date_str = m.group(1).strip()
    # "October 09, 2026" or "October 9, 2026"
    parts = re.split(r"[\s,]+", date_str)
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


def _find_col(headers: list, candidates: list) -> Optional[int]:
    for candidate in candidates:
        for i, h in enumerate(headers):
            if candidate in h:
                return i
    return None


def _safe_rate(raw) -> Optional[Decimal]:
    try:
        return normalize_rate(raw)
    except ValueError:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Backward Compatibility Wrappers
# ═══════════════════════════════════════════════════════════════════════════════

def parse(raw_html: str) -> tuple:
    """
    Old function API (for backward compatibility).
    
    New code should use DashenAdapter().parse().
    
    Args:
        raw_html: Raw HTML string from Dashen Bank website
        
    Returns:
        Tuple of (records, errors) for backward compatibility
    """
    adapter = DashenAdapter()
    result = adapter.parse(raw_html)
    return result.records, result.errors


def schema_fingerprint(raw_html: str) -> str:
    """
    Old function API (for backward compatibility).
    
    New code should use DashenAdapter().schema_fingerprint().
    
    Args:
        raw_html: Raw HTML string from Dashen Bank website
        
    Returns:
        SHA256 hash of table structure
    """
    return DashenAdapter().schema_fingerprint(raw_html)
