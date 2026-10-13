"""
adapters/hibret/adapter.py — Hibret Bank (Type E wide HTML).

Parse rules (ADR-006 §6, mapping doc):
- Input: static HTML with 1 table.
  Header row 0: | | CASH | | TRANSACTION |
  Header row 1: CURRENCY | BUYING | SELLING | BUYING | SELLING
- No date in table → effective_date_basis=collection_date_fallback → identity_status=ambiguous.
- SSL certificate verification fails — fetch() must use verify=False (access finding recorded).
- "No Trade" / "-" / empty → None.
- Partial failure: returns records + errors list. Never raises.
"""
import hashlib
from datetime import date
from decimal import Decimal
from typing import Optional

from bs4 import BeautifulSoup

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "hibret_html"
SOURCE_URL = "https://www.hibretbank.com.et/about/exchange-rate/"
SSL_VERIFY = False  # SSL cert error — access finding recorded in mapping doc


def parse(raw_html: str) -> tuple:
    """
    Returns (records: list[AdapterRecord], errors: list[str]).
    Never raises.
    """
    soup = BeautifulSoup(raw_html, "html.parser")
    tables = soup.find_all("table")

    if not tables:
        return [], ["table_0_cash_txn:missing"]

    records = []
    errors = []
    try:
        records.extend(_parse_cash_txn_table(tables[0]))
    except Exception as exc:
        errors.append(f"table_0_cash_txn:{exc}")

    return records, errors


def _parse_cash_txn_table(table) -> list:
    """Parse single table: cash cols 1-2, txn cols 3-4."""
    rows = table.find_all("tr")
    data_rows = [r for r in rows if r.find("td")]
    if not data_rows:
        return []

    records = []
    for row in data_rows:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 5:
            continue
        currency_code = cells[0].strip()
        if not currency_code:
            continue

        for category, buy_idx, sell_idx in [("cash", 1, 2), ("transactional", 3, 4)]:
            buying = _safe_rate(cells[buy_idx])
            selling = _safe_rate(cells[sell_idx])
            if buying is None and selling is None:
                continue
            records.append(AdapterRecord(
                source_currency_code=currency_code,
                category=category,
                buying_rate=buying,
                selling_rate=selling,
                source_rate_text=f"{cells[buy_idx]}/{cells[sell_idx]}",
                effective_date=None,
                effective_date_basis="collection_date_fallback",
                source_record_key=None,
                source_publication_key=None,
                unit_multiplier=1,
                raw_excerpt={"currency": currency_code, "buying": cells[buy_idx], "selling": cells[sell_idx]},
                mapping_notes=[
                    "date_ambiguous:no_source_published_date",
                    "ssl_verify_false:access_finding_recorded",
                ],
            ))
    return records


def _safe_rate(raw) -> Optional[Decimal]:
    try:
        return normalize_rate(raw)
    except ValueError:
        return None


def schema_fingerprint(raw_html: str) -> str:
    """Hash of table count + first table header structure."""
    try:
        soup = BeautifulSoup(raw_html, "html.parser")
        tables = soup.find_all("table")
        sig = []
        for t in tables:
            rows = t.find_all("tr")
            if rows:
                sig.append([c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])])
        payload = str({"tables": len(tables), "headers": sig})
        return hashlib.sha256(payload.encode()).hexdigest()
    except Exception:
        return hashlib.sha256(b"hibret:unparseable").hexdigest()
