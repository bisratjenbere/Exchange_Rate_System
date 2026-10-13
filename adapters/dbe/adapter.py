"""
adapters/dbe/adapter.py — Development Bank of Ethiopia (Type F single table).

Parse rules:
- Table 0: Currency (name) | Code | Buying | Selling. No category label → UNKNOWN.
- Table 1: same structure but empty (JS-rendered) — skip.
- Date from tablepress-table-description span → source_published → CONFIRMED identity.
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

ADAPTER_KEY = "dbe_html"
SOURCE_URL = "https://dbe.com.et/"


def parse(raw_html: str, category: str = "UNKNOWN") -> tuple:
    soup = BeautifulSoup(raw_html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return [], ["table_0:missing"]

    effective_date = _parse_date_from_description(tables[0])
    records, errors = [], []
    try:
        records = _parse_table(tables[0], category, effective_date)
    except Exception as exc:
        errors.append(f"table_0:{exc}")
    return records, errors


_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _parse_date_from_description(table) -> Optional[date]:
    """Read the tablepress-table-description span that precedes the table."""
    parent = table.parent
    span = parent.find("span", class_="tablepress-table-description") if parent else None
    if not span:
        return None
    text = span.get_text(" ", strip=True)
    m = re.search(r'(\w+)\s+(\d{1,2}),?\s+(\d{4})', text)
    if not m:
        return None
    month = _MONTHS.get(m.group(1).lower())
    if not month:
        return None
    try:
        return date(int(m.group(3)), month, int(m.group(2)))
    except ValueError:
        return None


def _parse_table(table, category: str = "UNKNOWN", effective_date: Optional[date] = None) -> list:
    date_basis = "source_published" if effective_date else "collection_date_fallback"
    rows = [r for r in table.find_all("tr") if r.find("td")]
    records = []
    for row in rows:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        # col0=name(empty), col1=code, col2=buying, col3=selling
        if len(cells) < 4:
            continue
        currency_code = cells[1].strip()
        if not currency_code:
            continue
        buying = _safe_rate(cells[2])
        selling = _safe_rate(cells[3])
        if buying is None and selling is None:
            continue
        records.append(AdapterRecord(
            source_currency_code=currency_code,
            category=category,
            buying_rate=buying,
            selling_rate=selling,
            source_rate_text=f"{cells[2]}/{cells[3]}",
            effective_date=effective_date,
            effective_date_basis=date_basis,
            source_record_key=None,
            source_publication_key=None,
            unit_multiplier=1,
            raw_excerpt={"currency": currency_code, "buying": cells[2], "selling": cells[3]},
            mapping_notes=["category_unknown:single_pair_no_label"],
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
        return hashlib.sha256(b"dbe:unparseable").hexdigest()
