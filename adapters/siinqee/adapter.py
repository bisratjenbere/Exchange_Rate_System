"""
adapters/siinqee/adapter.py — Siinqee Bank (Type F single table).

Parse rules:
- Single table: Currency (code) | Buying | Selling. No category label → UNKNOWN.
- No date → collection_date_fallback → identity_status=ambiguous.
- Partial failure: returns (records, errors). Never raises.
"""
import hashlib
from decimal import Decimal
from typing import Optional

from bs4 import BeautifulSoup

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "siinqee_html"
SOURCE_URL = "https://siinqeebank.com/"


def parse(raw_html: str, category: str = "UNKNOWN") -> tuple:
    soup = BeautifulSoup(raw_html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return [], ["table_0:missing"]

    records, errors = [], []
    try:
        records = _parse_table(tables[0], category)
    except Exception as exc:
        errors.append(f"table_0:{exc}")
    return records, errors


def _parse_table(table, category: str = "UNKNOWN") -> list:
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
            effective_date=None,
            effective_date_basis="collection_date_fallback",
            source_record_key=None,
            source_publication_key=None,
            unit_multiplier=1,
            raw_excerpt={"currency": currency_code, "buying": cells[1], "selling": cells[2]},
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
        return hashlib.sha256(b"siinqee:unparseable").hexdigest()
