"""
adapters/bunna/adapter.py — Bunna Bank (Type E wide HTML).

Parse rules:
- Single wide table. Header row 0: | CASH | TRANSACTION | AVERAGE
  Header row 1: Currency | Code | Buying | Selling | Buying | Selling | Buying | Selling
- Columns: col0=name, col1=code, col2=cash_buy, col3=cash_sell,
           col4=txn_buy, col5=txn_sell, col6=avg_buy, col7=avg_sell
- AVERAGE columns may contain "..." (JS-rendered) → treated as None.
- No date → collection_date_fallback → identity_status=ambiguous.
- Partial failure: returns (records, errors). Never raises.
"""
import hashlib
from decimal import Decimal
from typing import Optional

from bs4 import BeautifulSoup

from adapters.base import HTMLTableAdapter, ParseResult
from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "bunna_html"
SOURCE_URL = "https://bunnabanksc.com/foreign-exchange/"

_CATEGORIES = [
    ("cash", 2, 3),
    ("transactional", 4, 5),
    ("weighted_average", 6, 7),
]


class BunnaAdapter(HTMLTableAdapter):
    """
    Bunna Bank adapter using HTMLTableAdapter base class.
    
    Type E adapter with wide table containing all three categories (cash, transactional, weighted_average).
    """
    
    def get_source_url(self) -> str:
        """Return Bunna Bank website URL."""
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        """Return unique adapter identifier."""
        return ADAPTER_KEY
    
    def _process_tables(self, soup: BeautifulSoup, tables: list, **options) -> ParseResult:
        """
        Extract AdapterRecords from Bunna HTML table.
        
        Args:
            soup: BeautifulSoup parsed HTML
            tables: List of table elements (expecting 1 table)
            **options: Not used by Bunna
            
        Returns:
            ParseResult with extracted records and any errors
        """
        result = ParseResult()
        
        if not tables:
            result.add_error("table_0:missing")
            return result
        
        try:
            records = _parse_wide_table(tables[0])
            result.records.extend(records)
        except Exception as exc:
            result.add_error(f"table_0:{exc}")
        
        return result


def _parse_wide_table(table) -> list:
    """Parse Bunna's wide table with all three categories in columns."""
    rows = [r for r in table.find_all("tr") if r.find("td")]
    records = []
    for row in rows:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 6:
            continue
        currency_name = cells[0].strip()
        currency_code = cells[1].strip()
        if not currency_code:
            continue
        for category, bi, si in _CATEGORIES:
            if len(cells) <= si:
                continue
            buying = _safe_rate(cells[bi])
            selling = _safe_rate(cells[si])
            if buying is None and selling is None:
                continue
            records.append(AdapterRecord(
                source_currency_code=currency_code,
                currency_name=currency_name or None,
                category=category,
                buying_rate=buying,
                selling_rate=selling,
                source_rate_text=f"{cells[bi]}/{cells[si]}",
                effective_date=None,
                effective_date_basis="collection_date_fallback",
                source_record_key=None,
                source_publication_key=None,
                unit_multiplier=1,
                raw_excerpt={"currency": currency_code, "buying": cells[bi], "selling": cells[si]},
                mapping_notes=["date_ambiguous:no_source_published_date", "avg_cols_may_be_js_rendered:TO_VERIFY"],
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
    
    New code should use BunnaAdapter().parse().
    
    Args:
        raw_html: Raw HTML string from Bunna Bank
        
    Returns:
        Tuple of (records, errors) for backward compatibility
    """
    adapter = BunnaAdapter()
    result = adapter.parse(raw_html)
    return result.records, result.errors


def schema_fingerprint(raw_html: str) -> str:
    """
    Old function API (for backward compatibility).
    
    New code should use BunnaAdapter().schema_fingerprint().
    
    Args:
        raw_html: Raw HTML string
        
    Returns:
        SHA256 hash of table structure
    """
    return BunnaAdapter().schema_fingerprint(raw_html)
