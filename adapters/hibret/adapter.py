"""
adapters/hibret/adapter.py — Hibret Bank.
"""
import hashlib
import re
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from bs4 import BeautifulSoup

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "hibret_html"
SOURCE_URL = "https://www.hibretbank.com.et/about/exchange-rate/"
SSL_VERIFY = False

# Non-ISO labels the bank uses on their page
_CODE_ALIASES = {
    "CHINA": "CNY",
    "CHIN": "CNY",
    "CHINESE": "CNY",
}


def _parse_date(soup) -> Optional[date]:
    text = soup.get_text(" ")
    m = re.search(r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s*\d{4}', text)
    if m:
        raw = re.sub(r'\s+', ' ', m.group(0).strip())
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y"):
            try: return datetime.strptime(raw, fmt).date()
            except ValueError: pass
    return None


def parse(raw_html: str) -> tuple:
    soup = BeautifulSoup(raw_html, "html.parser")
    effective_date = _parse_date(soup)
    date_basis = "source_published" if effective_date else "collection_date_fallback"
    tables = soup.find_all("table")
    if not tables:
        return [], ["table_0_cash_txn:missing"]
    records, errors = [], []
    try:
        records.extend(_parse_cash_txn_table(tables[0], effective_date, date_basis))
    except Exception as exc:
        errors.append(f"table_0_cash_txn:{exc}")
    return records, errors


def _parse_cash_txn_table(table, effective_date, date_basis) -> list:
    rows = table.find_all("tr")
    data_rows = [r for r in rows if r.find("td")]
    if not data_rows:
        return []
    records = []
    for row in data_rows:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 6:
            continue
        raw = cells[1].strip()
        if not raw:
            continue
        m = re.match(r'^([A-Z]{3})\b', raw, re.IGNORECASE)
        currency_code = m.group(1).upper() if m else _CODE_ALIASES.get(raw.upper())
        if not currency_code:
            continue
        for category, buy_idx, sell_idx in [("cash", 2, 3), ("transactional", 4, 5)]:
            buying = _safe_rate(cells[buy_idx])
            selling = _safe_rate(cells[sell_idx])
            if buying is None and selling is None:
                continue
            key = f"{effective_date}:{currency_code}:{category}" if effective_date else None
            records.append(AdapterRecord(
                source_currency_code=currency_code,
                category=category,
                buying_rate=buying,
                selling_rate=selling,
                source_rate_text=f"{cells[buy_idx]}/{cells[sell_idx]}",
                effective_date=effective_date,
                effective_date_basis=date_basis,
                source_record_key=None,
                source_publication_key=str(effective_date) if effective_date else None,
                unit_multiplier=1,
                raw_excerpt={"currency": currency_code, "buying": cells[buy_idx], "selling": cells[sell_idx]},
                mapping_notes=["ssl_verify_false:access_finding_recorded"],
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
        sig = [[c.get_text(strip=True) for c in t.find_all("tr")[0].find_all(["th", "td"])] for t in tables if t.find_all("tr")]
        return hashlib.sha256(str({"tables": len(tables), "headers": sig}).encode()).hexdigest()
    except Exception:
        return hashlib.sha256(b"hibret:unparseable").hexdigest()
