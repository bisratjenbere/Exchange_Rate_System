"""
adapters/amhara/adapter.py — Amhara Bank (Type E wide HTML, SSL verify=False).

Parse rules:
- Table 0: named columns Cash Buying/Selling + Transaction Buying/Selling.
  Currency format: "Name (CODE)" — extract code from parentheses.
- Table 1: Weighted Average — Currency (Name (CODE)) | Buying | Selling.
- No date in either table → collection_date_fallback → identity_status=ambiguous.
- "NO TRADE" → None. SSL verify=False (access finding recorded).
- Partial failure: returns (records, errors). Never raises.
"""
import hashlib
import re
from decimal import Decimal
from typing import Optional

from bs4 import BeautifulSoup

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "amhara_html"
SOURCE_URL = "https://www.amharabank.com/daily-exchange-rate/"
SSL_VERIFY = False

_CODE_RE = re.compile(r"\(([A-Z]{3})\)", re.IGNORECASE)


def parse(raw_html: str) -> tuple:
    soup = BeautifulSoup(raw_html, "html.parser")
    tables = soup.find_all("table")
    records, errors = [], []

    if not tables:
        return [], ["table_0_cash_txn:missing", "table_1_weighted_avg:missing"]

    try:
        records.extend(_parse_cash_txn(tables[0]))
    except Exception as exc:
        errors.append(f"table_0_cash_txn:{exc}")

    if len(tables) < 2:
        errors.append("table_1_weighted_avg:missing")
    else:
        try:
            records.extend(_parse_weighted(tables[1]))
        except Exception as exc:
            errors.append(f"table_1_weighted_avg:{exc}")

    return records, errors


def _parse_cash_txn(table) -> list:
    rows = [r for r in table.find_all("tr") if r.find("td")]
    records = []
    for row in rows:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        # Row layout: [empty, "Name (CODE)", cash_buy, cash_sell, txn_buy, txn_sell]
        if len(cells) < 6:
            continue
        currency_code, currency_name = _parse_name_code(cells[1])
        if not currency_code:
            continue
        for category, bi, si in [("cash", 2, 3), ("transactional", 4, 5)]:
            buying, selling = _safe_rate(cells[bi]), _safe_rate(cells[si])
            if buying is None and selling is None:
                continue
            records.append(_make_record(currency_code, currency_name, category, buying, selling, cells[bi], cells[si]))
    return records


def _parse_weighted(table) -> list:
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
        records.append(_make_record(currency_code, currency_name, "weighted_average", buying, selling, cells[2], cells[3]))
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
        mapping_notes=["date_ambiguous:no_source_published_date", "ssl_verify_false:access_finding_recorded"],
    )


def _parse_name_code(text: str) -> tuple:
    """'US Dollar (USD)' → ('USD', 'US Dollar'). Falls back to (text, None)."""
    m = _CODE_RE.search(text)
    if m:
        code = m.group(1).upper()
        name = text[:m.start()].strip()
        return code, name or None
    text = text.strip()
    return (text, None) if text else ("", None)


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
        return hashlib.sha256(b"amhara:unparseable").hexdigest()
