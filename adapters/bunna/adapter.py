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

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "bunna_html"
SOURCE_URL = "https://bunnabanksc.com/foreign-exchange/"

_CATEGORIES = [
    ("cash", 2, 3),
    ("transactional", 4, 5),
    ("weighted_average", 6, 7),
]


def parse(raw_html: str) -> tuple:
    soup = BeautifulSoup(raw_html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return [], ["table_0:missing"]

    records, errors = [], []
    try:
        records = _parse_wide_table(tables[0])
    except Exception as exc:
        errors.append(f"table_0:{exc}")
    return records, errors


def _parse_wide_table(table) -> list:
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
        return hashlib.sha256(b"bunna:unparseable").hexdigest()
