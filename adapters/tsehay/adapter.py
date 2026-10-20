"""
adapters/tsehay/adapter.py — Tsehay Bank.

Parse rules:
- Date from "Daily Exchange Rate: Month DD, YYYY" heading.
- Table 0: CURRENCY | CASH (Buying/Selling) | TRANSACTION (Buying/Selling)
- Table 1: Currency (name) | Code | Buying | Selling → weighted_average.
- "No Trade" → None.
- Partial failure: returns (records, errors). Never raises.
"""
import re
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from bs4 import BeautifulSoup

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate
from adapters.base import HTMLTableAdapter, ParseResult

ADAPTER_KEY = "tsehay_html"
SOURCE_URL = "https://tsehaybank.com.et/exchange-rate/"


class TsehayAdapter(HTMLTableAdapter):
    """Tsehay Bank adapter - 2 tables (cash/transactional + weighted_average)."""
    
    def get_source_url(self) -> str:
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        return ADAPTER_KEY
    
    def _process_tables(self, soup: BeautifulSoup, tables: list, **kwargs) -> ParseResult:
        """Process 2 tables from Tsehay Bank with date extraction."""
        result = ParseResult()
        
        effective_date = _parse_date(soup)
        date_basis = "source_published" if effective_date else "collection_date_fallback"
        
        if len(tables) < 1:
            result.add_error("table_0_cash_txn:missing")
            result.add_error("table_1_weighted:missing")
            return result
        
        try:
            records = _parse_cash_txn(tables[0], effective_date, date_basis)
            result.records.extend(records)
        except Exception as exc:
            result.add_error(f"table_0_cash_txn:{exc}")
        
        if len(tables) < 2:
            result.add_error("table_1_weighted:missing")
        else:
            try:
                records = _parse_weighted(tables[1], effective_date, date_basis)
                result.records.extend(records)
            except Exception as exc:
                result.add_error(f"table_1_weighted:{exc}")
        
        return result


def _parse_date(soup) -> Optional[date]:
    """Extract date from 'Daily Exchange Rate: October 14, 2026' heading."""
    text = soup.get_text(" ")
    m = re.search(r'Daily Exchange Rate[:\s]+([A-Za-z]+ \d{1,2},?\s*\d{4})', text)
    if m:
        for fmt in ("%B %d, %Y", "%B %d %Y", "%b %d, %Y"):
            try:
                return datetime.strptime(m.group(1).strip(), fmt).date()
            except ValueError:
                continue
    return None


def _parse_cash_txn(table, effective_date, date_basis) -> list:
    """Parse table 0 with cash and transactional columns."""
    rows = table.find_all("tr")
    # Skip header rows (rows without <td>)
    data_rows = [r for r in rows if r.find("td")]
    records = []
    for row in data_rows:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 5:
            continue
        currency_code = cells[0].strip()
        if not currency_code:
            continue
        for category, bi, si in [("cash", 1, 2), ("transactional", 3, 4)]:
            buying = _safe_rate(cells[bi])
            selling = _safe_rate(cells[si])
            if buying is None and selling is None:
                continue
            records.append(_make_record(currency_code, None, category, buying, selling, cells[bi], cells[si], effective_date, date_basis))
    return records


def _parse_weighted(table, effective_date, date_basis) -> list:
    """Parse table 1 with weighted_average columns."""
    rows = [r for r in table.find_all("tr") if r.find("td")]
    records = []
    for row in rows:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 4:
            continue
        currency_name = cells[0].strip()
        currency_code = cells[1].strip()
        if not currency_code:
            continue
        buying = _safe_rate(cells[2])
        selling = _safe_rate(cells[3])
        if buying is None and selling is None:
            continue
        records.append(_make_record(currency_code, currency_name or None, "weighted_average",
                                    buying, selling, cells[2], cells[3], effective_date, date_basis))
    return records


def _make_record(code, name, category, buying, selling, buy_text, sell_text, effective_date, date_basis):
    """Create AdapterRecord from extracted data."""
    return AdapterRecord(
        source_currency_code=code,
        currency_name=name,
        category=category,
        buying_rate=buying,
        selling_rate=selling,
        source_rate_text=f"{buy_text}/{sell_text}",
        effective_date=effective_date,
        effective_date_basis=date_basis,
        source_record_key=None,
        source_publication_key=str(effective_date) if effective_date else None,
        unit_multiplier=1,
        raw_excerpt={"currency": code, "buying": buy_text, "selling": sell_text},
        mapping_notes=[] if effective_date else ["date_ambiguous:no_source_published_date"],
    )


def _safe_rate(raw) -> Optional[Decimal]:
    """Convert raw rate string to Decimal, returning None on failure."""
    try:
        return normalize_rate(raw)
    except ValueError:
        return None


# ============================================================================
# MODULE-LEVEL WRAPPER FUNCTIONS FOR BACKWARD COMPATIBILITY
# ============================================================================

_adapter_instance = TsehayAdapter()

def parse(raw_html: str) -> tuple:
    """Parse Tsehay Bank HTML into records. Module-level wrapper."""
    result = _adapter_instance.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    """Generate schema fingerprint. Module-level wrapper."""
    return _adapter_instance.schema_fingerprint(raw_html)
