"""
adapters/boa/adapter.py — Bank of Abyssinia (Type E, SSL verify=False).

Parse rules:
- Single table. Row 0 contains date ("October 12, 2026") → source_published.
- Section headers "Cash Rates" / "Transactional Rates" divide the table into sections.
- Each section has a sub-header row then data rows.
- Currency code only (no name). Columns: Currency type | Buying Rate | Selling Rate.
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

ADAPTER_KEY = "boa_html"
SOURCE_URL = "https://www.bankofabyssinia.com/exchange-rate-2/"
SSL_VERIFY = False

_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_DATE_RE = re.compile(rf"({_MONTHS})\s+(\d{{1,2}}),?\s+(\d{{4}})", re.IGNORECASE)
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

_SECTION_MAP = {
    "cash": "cash",
    "transactional": "transactional",
}


def parse(raw_html: str) -> tuple:
    soup = BeautifulSoup(raw_html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return [], ["table_0:missing"]

    records, errors = [], []
    try:
        records, errors = _parse_table(tables[0])
    except Exception as exc:
        errors.append(f"table_0:{exc}")
    return records, errors


def _parse_table(table) -> tuple:
    rows = table.find_all("tr")
    effective_date = None
    current_category = None
    records, errors = [], []

    for row in rows:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if not cells or all(c == "" for c in cells):
            continue

        text = " ".join(cells).strip()

        # Date row
        if effective_date is None:
            d = _parse_date(text)
            if d:
                effective_date = d
                continue

        # Section header row
        cat = _detect_section(text)
        if cat:
            current_category = cat
            continue

        # Sub-header row (contains "Buying" / "Selling" labels)
        if any("buying" in c.lower() or "selling" in c.lower() for c in cells):
            continue

        # Data row
        if current_category is None:
            continue
        currency = cells[0].strip()
        if not currency or len(cells) < 3:
            continue
        buying = _safe_rate(cells[1])
        selling = _safe_rate(cells[2])
        if buying is None and selling is None:
            continue

        date_basis = "source_published" if effective_date else "collection_date_fallback"
        records.append(AdapterRecord(
            source_currency_code=currency,
            category=current_category,
            buying_rate=buying,
            selling_rate=selling,
            source_rate_text=f"{cells[1]}/{cells[2]}",
            effective_date=effective_date,
            effective_date_basis=date_basis,
            source_record_key=None,
            source_publication_key=None,
            unit_multiplier=1,
            raw_excerpt={"currency": currency, "buying": cells[1], "selling": cells[2]},
            mapping_notes=["ssl_verify_false:access_finding_recorded"],
        ))

    return records, errors


def _detect_section(text: str) -> Optional[str]:
    t = text.lower()
    for key, cat in _SECTION_MAP.items():
        if key in t and "rate" in t:
            return cat
    return None


def _parse_date(text: str) -> Optional[date]:
    m = _DATE_RE.search(text)
    if not m:
        return None
    month = _MONTH_MAP.get(m.group(1).lower())
    if not month:
        return None
    try:
        return date(int(m.group(3)), month, int(m.group(2)))
    except ValueError:
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
        rows = tables[0].find_all("tr") if tables else []
        first_cells = [c.get_text(strip=True) for c in rows[0].find_all(["td", "th"])] if rows else []
        payload = str({"tables": len(tables), "first_row": first_cells})
        return hashlib.sha256(payload.encode()).hexdigest()
    except Exception:
        return hashlib.sha256(b"boa:unparseable").hexdigest()
