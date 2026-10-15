"""
adapters/zamzam/adapter.py — ZamZam Bank (2-table HTML).

Parse rules:
- Table 0: Cash + Transaction — multi-level header
  Row 0: Currency | Cash | Transaction
  Row 1: Buying | Selling | Buying | Selling
  Data: "CODE – Name" | cash_buy | cash_sell | txn_buy | txn_sell
- Table 1: Weighted Average — "CODE – Name" | Buying | Selling
  Header row 0: "Currency Code | Weighted Average Daily Exchange Rates"
  Header row 1: Buying | Selling
- Date in page text: "October 13, 2026" → source_published.
- "No Trade" → None.
- Currency format: "CODE – Name" → extract code as first token before " –".
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

ADAPTER_KEY = "zamzam_html"
SOURCE_URL = "https://zamzambank.com/exchange-rates/"

_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_DATE_RE = re.compile(rf"({_MONTHS})\s+(\d{{1,2}}),?\s+(\d{{4}})", re.IGNORECASE)
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def parse(raw_html: str) -> tuple:
    soup = BeautifulSoup(raw_html, "html.parser")
    tables = soup.find_all("table")
    text = soup.get_text(" ", strip=True)

    effective_date = _extract_date(text)
    date_basis = "source_published" if effective_date else "collection_date_fallback"

    records, errors = [], []

    if not tables:
        return [], ["table_0:missing", "table_1:missing"]

    try:
        records.extend(_parse_cash_txn(tables[0], effective_date, date_basis))
    except Exception as exc:
        errors.append(f"table_0_cash_txn:{exc}")

    if len(tables) < 2:
        errors.append("table_1_weighted:missing")
    else:
        try:
            records.extend(_parse_weighted(tables[1], effective_date, date_basis))
        except Exception as exc:
            errors.append(f"table_1_weighted:{exc}")

    return records, errors


def _parse_cash_txn(table, effective_date, date_basis: str) -> list:
    rows = [r for r in table.find_all("tr") if r.find("td")]
    records = []
    for row in rows:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 5:
            continue
        code = _parse_code(cells[0])
        if not code:
            continue
        for category, bi, si in [("cash", 1, 2), ("transactional", 3, 4)]:
            buying = _safe_rate(cells[bi])
            selling = _safe_rate(cells[si])
            if buying is None and selling is None:
                continue
            records.append(_make_record(code, category, buying, selling,
                                        cells[bi], cells[si], effective_date, date_basis))
    return records


def _parse_weighted(table, effective_date, date_basis: str) -> list:
    rows = [r for r in table.find_all("tr") if r.find("td")]
    records = []
    for row in rows:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        code = _parse_code(cells[0])
        if not code:
            continue
        buying = _safe_rate(cells[1])
        selling = _safe_rate(cells[2])
        if buying is None and selling is None:
            continue
        records.append(_make_record(code, "weighted_average", buying, selling,
                                    cells[1], cells[2], effective_date, date_basis))
    return records


def _make_record(code, category, buying, selling, buy_text, sell_text, effective_date, date_basis):
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
        mapping_notes=[],
    )


def _parse_code(text: str) -> str:
    """'USD – Us Dollar' → 'USD'. Returns '' if unparseable."""
    text = text.strip()
    for sep in [" –", " -", " —"]:
        if sep in text:
            return text.split(sep)[0].strip()
    return text.split()[0] if text else ""


def _extract_date(text: str) -> Optional[date]:
    for m in _DATE_RE.finditer(text):
        month = _MONTH_MAP.get(m.group(1).lower())
        if not month:
            continue
        try:
            d = date(int(m.group(3)), month, int(m.group(2)))
            if d.year >= 2020:
                return d
        except ValueError:
            continue
    return None


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
        return hashlib.sha256(b"zamzam:unparseable").hexdigest()
