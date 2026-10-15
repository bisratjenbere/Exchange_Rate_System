"""
adapters/abay/adapter.py — Abay Bank (3-table HTML).

Parse rules:
- Table 0: WEIGHTED AVERAGE RATE — CURRENCY | BUYING | SELLING
- Table 1: CASH RATE             — CURRENCY | BUYING | SELLING
- Table 2: TRANSACTION RATE      — CURRENCY | BUYING | SELLING
- Date in page text: "October 13, 2026" → source_published.
- Empty selling cell → None.
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

ADAPTER_KEY = "abay_html"
SOURCE_URL = "https://www.abaybanksc.com/"

_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_DATE_RE = re.compile(rf"({_MONTHS})\s+(\d{{1,2}}),?\s+(\d{{4}})", re.IGNORECASE)
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

_TABLE_CATEGORIES = {0: "weighted_average", 1: "cash", 2: "transactional"}


def parse(raw_html: str) -> tuple:
    soup = BeautifulSoup(raw_html, "html.parser")
    tables = soup.find_all("table")
    text = soup.get_text(" ", strip=True)

    effective_date = _extract_date(text)
    date_basis = "source_published" if effective_date else "collection_date_fallback"

    records, errors = [], []
    for idx, category in _TABLE_CATEGORIES.items():
        if idx >= len(tables):
            errors.append(f"table_{idx}_{category}:missing")
            continue
        try:
            records.extend(_parse_table(tables[idx], category, effective_date, date_basis))
        except Exception as exc:
            errors.append(f"table_{idx}_{category}:{exc}")
    return records, errors


def _parse_table(table, category: str, effective_date, date_basis: str) -> list:
    rows = [r for r in table.find_all("tr") if r.find("td")]
    records = []
    for row in rows:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        currency_code = cells[0].strip()
        if not currency_code:
            continue
        buying = _safe_rate(cells[1])
        selling = _safe_rate(cells[2])
        if buying is None and selling is None:
            continue
        records.append(AdapterRecord(
            source_currency_code=currency_code,
            category=category,
            buying_rate=buying,
            selling_rate=selling,
            source_rate_text=f"{cells[1]}/{cells[2]}",
            effective_date=effective_date,
            effective_date_basis=date_basis,
            source_record_key=None,
            source_publication_key=None,
            unit_multiplier=1,
            raw_excerpt={"currency": currency_code, "buying": cells[1], "selling": cells[2]},
            mapping_notes=[],
        ))
    return records


def _extract_date(text: str) -> Optional[date]:
    """Return the most recent date found in text (avoids old news article dates)."""
    best = None
    for m in _DATE_RE.finditer(text):
        month = _MONTH_MAP.get(m.group(1).lower())
        if not month:
            continue
        try:
            d = date(int(m.group(3)), month, int(m.group(2)))
            if d.year >= 2020 and (best is None or d > best):
                best = d
        except ValueError:
            continue
    return best


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
        return hashlib.sha256(b"abay:unparseable").hexdigest()
