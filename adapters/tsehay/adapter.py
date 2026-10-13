"""
adapters/tsehay/adapter.py — Tsehay Bank (Type E-like, no date).

Parse rules:
- Table 0: CURRENCY | CASH (Buying/Selling) | TRANSACTION (Buying/Selling)
  Multi-level header: row 0 = category spans, row 1 = Buying/Selling labels.
  Data rows start at row 2. col0=code, col1=cash_buy, col2=cash_sell, col3=txn_buy, col4=txn_sell.
- Table 1: Currency (name) | Code | Buying | Selling → weighted_average.
- No date → collection_date_fallback → identity_status=ambiguous.
- "No Trade" → None.
- Partial failure: returns (records, errors). Never raises.
"""
import hashlib
from decimal import Decimal
from typing import Optional

from bs4 import BeautifulSoup

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "tsehay_html"
SOURCE_URL = "https://tsehaybank.com.et/exchange-rate/"


def parse(raw_html: str) -> tuple:
    soup = BeautifulSoup(raw_html, "html.parser")
    tables = soup.find_all("table")
    records, errors = [], []

    if not tables:
        return [], ["table_0_cash_txn:missing", "table_1_weighted:missing"]

    try:
        records.extend(_parse_cash_txn(tables[0]))
    except Exception as exc:
        errors.append(f"table_0_cash_txn:{exc}")

    if len(tables) < 2:
        errors.append("table_1_weighted:missing")
    else:
        try:
            records.extend(_parse_weighted(tables[1]))
        except Exception as exc:
            errors.append(f"table_1_weighted:{exc}")

    return records, errors


def _parse_cash_txn(table) -> list:
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
            records.append(_make_record(currency_code, None, category, buying, selling, cells[bi], cells[si]))
    return records


def _parse_weighted(table) -> list:
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
                                    buying, selling, cells[2], cells[3]))
    return records


def _make_record(code, name, category, buying, selling, buy_text, sell_text):
    return AdapterRecord(
        source_currency_code=code,
        currency_name=name,
        category=category,
        buying_rate=buying,
        selling_rate=selling,
        source_rate_text=f"{buy_text}/{sell_text}",
        effective_date=None,
        effective_date_basis="collection_date_fallback",
        source_record_key=None,
        source_publication_key=None,
        unit_multiplier=1,
        raw_excerpt={"currency": code, "buying": buy_text, "selling": sell_text},
        mapping_notes=["date_ambiguous:no_source_published_date"],
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
        return hashlib.sha256(b"tsehay:unparseable").hexdigest()
