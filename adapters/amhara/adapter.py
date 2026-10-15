"""
adapters/amhara/adapter.py — Amhara Bank.
"""
import hashlib
import re
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from bs4 import BeautifulSoup

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "amhara_html"
SOURCE_URL = "https://www.amharabank.com/daily-exchange-rate/"
SSL_VERIFY = False

_CODE_RE = re.compile(r"\(\s*([A-Z]{3})\s*\)", re.IGNORECASE)


def _parse_date(soup) -> Optional[date]:
    text = re.sub(r'\s+', ' ', soup.get_text(" "))
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
    records, errors = [], []
    if not tables:
        return [], ["table_0_cash_txn:missing", "table_1_weighted_avg:missing"]
    try:
        records.extend(_parse_cash_txn(tables[0], effective_date, date_basis))
    except Exception as exc:
        errors.append(f"table_0_cash_txn:{exc}")
    if len(tables) < 2:
        errors.append("table_1_weighted_avg:missing")
    else:
        try:
            records.extend(_parse_weighted(tables[1], effective_date, date_basis))
        except Exception as exc:
            errors.append(f"table_1_weighted_avg:{exc}")
    return records, errors


def _parse_cash_txn(table, effective_date, date_basis) -> list:
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
            records.append(_make_record(currency_code, currency_name, category, buying, selling, cells[bi], cells[si], effective_date, date_basis))
    return records


def _parse_weighted(table, effective_date, date_basis) -> list:
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
        records.append(_make_record(currency_code, currency_name, "weighted_average", buying, selling, cells[2], cells[3], effective_date, date_basis))
    return records


def _make_record(code, name, category, buying, selling, buy_text, sell_text, eff_date, date_basis):
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
        sig = [[c.get_text(strip=True) for c in t.find_all("tr")[0].find_all(["th", "td"])] for t in tables if t.find_all("tr")]
        return hashlib.sha256(str({"tables": len(tables), "headers": sig}).encode()).hexdigest()
    except Exception:
        return hashlib.sha256(b"amhara:unparseable").hexdigest()
