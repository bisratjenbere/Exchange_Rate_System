"""
adapters/nib/adapter.py — Nib International Bank (Type D multi-table HTML).

Parse rules:
- 3 tables: table[0]=date header, table[1]=cash+txn, table[2]=weighted_average.
- Table 0: single row with date text "Oct 12, 2026" → source_published for all records.
- Table 1: Country | Currency | Buying | Selling | Buying | Selling
  Two buying/selling pairs — col2/3 = cash, col4/5 = transactional (TO VERIFY).
- Table 2: Country | Currency | Buying | Selling → weighted_average.
- "No Trade" → None. Country column is empty in data rows.
- Partial failure: returns (records, errors). Never raises.
"""
import hashlib
import re
from datetime import date
from decimal import Decimal
from typing import Optional

from bs4 import BeautifulSoup

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "nib_html"
SOURCE_URL = "https://www.nibbanksc.com/exchange-rate/"

_MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
_DATE_RE = re.compile(rf"({_MONTHS})\w*\s+(\d{{1,2}}),?\s+(\d{{4}})", re.IGNORECASE)
_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse(raw_html: str) -> tuple:
    soup = BeautifulSoup(raw_html, "html.parser")
    tables = soup.find_all("table")
    records, errors = [], []

    if len(tables) < 3:
        # Try to work with what we have
        if not tables:
            return [], ["table_0_date:missing", "table_1_cash_txn:missing", "table_2_weighted:missing"]

    # Extract date from table 0
    effective_date = None
    if tables:
        try:
            effective_date = _extract_date(tables[0])
        except Exception as exc:
            errors.append(f"date_extraction:{exc}")

    date_basis = "source_published" if effective_date else "collection_date_fallback"

    # Parse table 1 — cash + transactional
    if len(tables) >= 2:
        try:
            records.extend(_parse_cash_txn(tables[1], effective_date, date_basis))
        except Exception as exc:
            errors.append(f"table_1_cash_txn:{exc}")
    else:
        errors.append("table_1_cash_txn:missing")

    # Parse table 2 — weighted average
    if len(tables) >= 3:
        try:
            records.extend(_parse_weighted(tables[2], effective_date, date_basis))
        except Exception as exc:
            errors.append(f"table_2_weighted:{exc}")
    else:
        errors.append("table_2_weighted:missing")

    return records, errors


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


def _parse_cash_txn(table, effective_date, date_basis) -> list:
    rows = [r for r in table.find_all("tr") if r.find("td")]
    records = []
    for row in rows:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 5:
            continue
        # col0=Country(empty), col1=Currency, col2=cash_buy, col3=cash_sell, col4=txn_buy, col5=txn_sell
        currency = cells[1].strip()
        if not currency:
            continue
        for category, bi, si in [("cash", 2, 3), ("transactional", 4, 5)]:
            if len(cells) <= si:
                continue
            buying = _safe_rate(cells[bi])
            selling = _safe_rate(cells[si])
            if buying is None and selling is None:
                continue
            records.append(_make_record(currency, category, buying, selling,
                                        cells[bi], cells[si], effective_date, date_basis,
                                        ["cash_txn_col_assignment:TO_VERIFY"]))
    return records


def _parse_weighted(table, effective_date, date_basis) -> list:
    rows = [r for r in table.find_all("tr") if r.find("td")]
    records = []
    for row in rows:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 4:
            continue
        currency = cells[1].strip()
        if not currency:
            continue
        buying = _safe_rate(cells[2])
        selling = _safe_rate(cells[3])
        if buying is None and selling is None:
            continue
        records.append(_make_record(currency, "weighted_average", buying, selling,
                                    cells[2], cells[3], effective_date, date_basis, []))
    return records


def _make_record(code, category, buying, selling, buy_text, sell_text, effective_date, date_basis, notes):
    return AdapterRecord(
        source_currency_code=code,
        category=category,
        buying_rate=buying,
        selling_rate=selling,
        source_rate_text=f"{buy_text}/{sell_text}",
        effective_date=effective_date,
        effective_date_basis=date_basis,
        source_record_key=None,
        source_publication_key=None,
        unit_multiplier=1,
        raw_excerpt={"currency": code, "buying": buy_text, "selling": sell_text},
        mapping_notes=notes,
    )


def _safe_rate(raw) -> Optional[Decimal]:
    try:
        return normalize_rate(raw)
    except ValueError:
        return None


def schema_fingerprint(raw_html: str) -> str:
    try:
        soup = BeautifulSoup(raw_html, "html.parser")
        tables = soup.find_all("table")
        sig = [
            [c.get_text(strip=True) for c in t.find_all("tr")[0].find_all(["th", "td"])]
            for t in tables if t.find_all("tr")
        ]
        return hashlib.sha256(str({"tables": len(tables), "headers": sig}).encode()).hexdigest()
    except Exception:
        return hashlib.sha256(b"nib:unparseable").hexdigest()
