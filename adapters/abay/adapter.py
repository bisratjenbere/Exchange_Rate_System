"""
adapters/abay/adapter.py — Abay Bank (3-table HTML).

Parse rules:
- Table 0: WEIGHTED AVERAGE RATE — CURRENCY | BUYING | SELLING
- Table 1: CASH RATE             — CURRENCY | BUYING | SELLING
- Table 2: TRANSACTION RATE      — CURRENCY | BUYING | SELLING
- Date in page text: "October 13, 2026" → source_published.
- Empty selling cell → None.
- Partial failure: returns (records, errors). Never raises.
"""
import re
from datetime import date
from decimal import Decimal
from typing import Optional

from bs4 import BeautifulSoup

from adapters.base import HTMLTableAdapter, ParseResult
from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "abay_html"
SOURCE_URL = "https://www.abaybanksc.com/"

_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_DATE_RE = re.compile(rf"({_MONTHS})\s+(\d{{1,2}}),?\s+(\d{{4}})", re.IGNORECASE)
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

_TABLE_CATEGORIES = {0: "weighted_average", 1: "cash", 2: "transactional"}


class AbayAdapter(HTMLTableAdapter):
    """
    Abay Bank adapter.
    
    Parses 3 HTML tables with different rate categories:
    - Table 0: weighted_average
    - Table 1: cash
    - Table 2: transactional
    
    Extracts effective date from page text (e.g., "October 13, 2026").
    """
    
    def get_source_url(self) -> str:
        """Return Abay Bank website URL."""
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        """Return unique adapter identifier."""
        return ADAPTER_KEY
    
    def _process_tables(self, soup: BeautifulSoup, tables: list, **options) -> ParseResult:
        """
        Extract AdapterRecords from Abay Bank HTML tables.
        
        Args:
            soup: BeautifulSoup parsed HTML
            tables: List of table elements (expecting 3 tables)
            **options: Not used for Abay
            
        Returns:
            ParseResult with extracted records and any errors
        """
        result = ParseResult()
        
        # Extract date from page text
        text = soup.get_text(" ", strip=True)
        effective_date = self._extract_date(text)
        date_basis = "source_published" if effective_date else "collection_date_fallback"
        
        # Process each table with its corresponding category
        for idx, category in _TABLE_CATEGORIES.items():
            if idx >= len(tables):
                result.add_error(f"table_{idx}_{category}:missing")
                continue
            try:
                records = self._parse_table(tables[idx], category, effective_date, date_basis)
                result.records.extend(records)
            except Exception as exc:
                result.add_error(f"table_{idx}_{category}:{exc}")
        
        return result
    
    def _extract_date(self, text: str) -> Optional[date]:
        """Return the most recent date found in text (avoids old news article dates)."""
        best = None
        for m in _DATE_RE.finditer(text):
            month = _MONTH_MAP.get(m.group(1).lower())
            if not month:
                continue
            try:
                d = date(int(m.group(3)), month, int(m.group(2)))
                if d.year >= 2020 and (best is None or d > best):
                    best = d
            except ValueError:
                continue
        return best
    
    def _parse_table(self, table, category: str, effective_date: Optional[date], date_basis: str) -> list:
        """
        Parse Abay exchange rate table.
        
        Args:
            table: BeautifulSoup table element
            category: Exchange rate category (weighted_average, cash, transactional)
            effective_date: Extracted effective date or None
            date_basis: "source_published" or "collection_date_fallback"
            
        Returns:
            List of AdapterRecords
        """
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 3:
                continue
            currency_code = cells[0].strip()
            if not currency_code:
                continue
            buying = _safe_rate(cells[1])
            selling = _safe_rate(cells[2])
            if buying is None and selling is None:
                continue
            records.append(AdapterRecord(
                source_currency_code=currency_code,
                category=category,
                buying_rate=buying,
                selling_rate=selling,
                source_rate_text=f"{cells[1]}/{cells[2]}",
                effective_date=effective_date,
                effective_date_basis=date_basis,
                source_record_key=None,
                source_publication_key=None,
                unit_multiplier=1,
                raw_excerpt={"currency": currency_code, "buying": cells[1], "selling": cells[2]},
                mapping_notes=[],
            ))
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

def parse(raw_html: str) -> tuple:
    """
    Old function API (for backward compatibility).
    
    New code should use AbayAdapter().parse().
    
    Args:
        raw_html: Raw HTML string from Abay Bank website
        
    Returns:
        Tuple of (records, errors) for backward compatibility
    """
    adapter = AbayAdapter()
    result = adapter.parse(raw_html)
    return result.records, result.errors


def schema_fingerprint(raw_html: str) -> str:
    """
    Old function API (for backward compatibility).
    
    New code should use AbayAdapter().schema_fingerprint().
    
    Args:
        raw_html: Raw HTML string from Abay Bank website
        
    Returns:
        SHA256 hash of table structure
    """
    return AbayAdapter().schema_fingerprint(raw_html)
