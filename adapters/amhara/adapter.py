"""
adapters/amhara/adapter.py — Amhara Bank.
"""
import re
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from bs4 import BeautifulSoup

from adapters.base import HTMLTableAdapter, ParseResult
from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "amhara_html"
SOURCE_URL = "https://www.amharabank.com/daily-exchange-rate/"
SSL_VERIFY = False

_CODE_RE = re.compile(r"\(\s*([A-Z]{3})\s*\)", re.IGNORECASE)


class AmharaAdapter(HTMLTableAdapter):
    """
    Amhara Bank adapter.
    
    Type D adapter (2-table HTML with shared date).
    Parses HTML with 2 tables: cash+transactional, weighted_average.
    All tables share the same effective date extracted from page text.
    """
    
    def get_source_url(self) -> str:
        """Return Amhara Bank website URL."""
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        """Return unique adapter identifier."""
        return ADAPTER_KEY
    
    def _process_tables(self, soup: BeautifulSoup, tables: list, **options) -> ParseResult:
        """
        Extract AdapterRecords from Amhara Bank HTML tables.
        
        Args:
            soup: BeautifulSoup parsed HTML
            tables: List of table elements (expecting 2 tables)
            **options: Not used for Amhara
            
        Returns:
            ParseResult with extracted records and any errors
        """
        result = ParseResult()
        
        # Extract date from page text
        effective_date = _parse_date(soup)
        date_basis = "source_published" if effective_date else "collection_date_fallback"
        
        if not tables:
            result.add_error("table_0_cash_txn:missing")
            result.add_error("table_1_weighted_avg:missing")
            return result
        
        # Parse table 0 — cash + transactional
        try:
            records = _parse_cash_txn(tables[0], effective_date, date_basis)
            result.records.extend(records)
        except Exception as exc:
            result.add_error(f"table_0_cash_txn:{exc}")
        
        # Parse table 1 — weighted average
        if len(tables) < 2:
            result.add_error("table_1_weighted_avg:missing")
        else:
            try:
                records = _parse_weighted(tables[1], effective_date, date_basis)
                result.records.extend(records)
            except Exception as exc:
                result.add_error(f"table_1_weighted_avg:{exc}")
        
        return result


def _parse_date(soup) -> Optional[date]:
    """Extract date from page text."""
    text = re.sub(r'\s+', ' ', soup.get_text(" "))
    m = re.search(r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s*\d{4}', text)
    if m:
        raw = re.sub(r'\s+', ' ', m.group(0).strip())
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                pass
    return None


def _parse_cash_txn(table, effective_date, date_basis) -> list:
    """Parse cash + transactional table (table 0)."""
    rows = [r for r in table.find_all("tr") if r.find("td")]
    records = []
    for row in rows:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 6:
            continue
        currency_code, currency_name = _parse_name_code(cells[1])
        if not currency_code:
            continue
        for category, bi, si in [("cash", 2, 3), ("transactional", 4, 5)]:
            buying, selling = _safe_rate(cells[bi]), _safe_rate(cells[si])
            if buying is None and selling is None:
                continue
            records.append(_make_record(currency_code, currency_name, category, buying, selling, 
                                       cells[bi], cells[si], effective_date, date_basis))
    return records


def _parse_weighted(table, effective_date, date_basis) -> list:
    """Parse weighted average table (table 1)."""
    rows = [r for r in table.find_all("tr") if r.find("td")]
    records = []
    for row in rows:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 4:
            continue
        currency_code, currency_name = _parse_name_code(cells[1])
        if not currency_code:
            continue
        buying, selling = _safe_rate(cells[2]), _safe_rate(cells[3])
        if buying is None and selling is None:
            continue
        records.append(_make_record(currency_code, currency_name, "weighted_average", buying, selling,
                                    cells[2], cells[3], effective_date, date_basis))
    return records


def _make_record(code, name, category, buying, selling, buy_text, sell_text, eff_date, date_basis):
    """Create AdapterRecord from extracted data."""
    return AdapterRecord(
        source_currency_code=code, currency_name=name, category=category,
        buying_rate=buying, selling_rate=selling,
        source_rate_text=f"{buy_text}/{sell_text}",
        effective_date=eff_date, effective_date_basis=date_basis,
        source_record_key=None,
        source_publication_key=str(eff_date) if eff_date else None,
        unit_multiplier=1,
        raw_excerpt={"currency": code, "buying": buy_text, "selling": sell_text},
        mapping_notes=["ssl_verify_false:access_finding_recorded"],
    )


def _parse_name_code(text: str) -> tuple:
    """Extract currency code from 'Currency Name (USD)' format."""
    m = _CODE_RE.search(text)
    if m:
        code = m.group(1).upper()
        name = text[:m.start()].strip()
        return code, name or None
    text = text.strip()
    return (text, None) if text else ("", None)


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
    
    New code should use AmharaAdapter().parse().
    
    Args:
        raw_html: Raw HTML string from Amhara Bank website
        
    Returns:
        Tuple of (records, errors) for backward compatibility
    """
    adapter = AmharaAdapter()
    result = adapter.parse(raw_html)
    return result.records, result.errors


def schema_fingerprint(raw_html: str) -> str:
    """
    Old function API (for backward compatibility).
    
    New code should use AmharaAdapter().schema_fingerprint().
    
    Args:
        raw_html: Raw HTML string from Amhara Bank website
        
    Returns:
        SHA256 hash of table structure
    """
    return AmharaAdapter().schema_fingerprint(raw_html)
