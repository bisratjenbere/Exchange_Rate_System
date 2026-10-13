"""
adapters/goh_betoch/adapter.py — Goh Betoch Bank (Type F-like single table).

Parse rules:
- Single table: Currency cODE | Currency Name | buying | SELLING |
                Weighted Average Buying Rate | Weighted Average Selling Rate
- Columns: col0=code, col1=name, col2=plain_buy, col3=plain_sell,
           col4=weighted_buy, col5=weighted_sell
- Plain buying/selling category UNKNOWN (unconfirmed). Weighted average emitted.
- No date → collection_date_fallback → identity_status=ambiguous.
- Partial failure: returns (records, errors). Never raises.
"""
import hashlib
from decimal import Decimal
from typing import Optional

from bs4 import BeautifulSoup

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "goh_betoch_html"
SOURCE_URL = "https://www.gohbetbank.com/todays-exchange-rate/"


def parse(raw_html: str) -> tuple:
    soup = BeautifulSoup(raw_html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return [], ["table_0:missing"]

    records, errors = [], []
    try:
        records = _parse_table(tables[0])
    except Exception as exc:
        errors.append(f"table_0:{exc}")
    return records, errors


def _parse_table(table) -> list:
    rows = [r for r in table.find_all("tr") if r.find("td")]
    records = []
    for row in rows:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 4:
            continue
        currency_code = cells[0].strip()
        currency_name = cells[1].strip() if len(cells) > 1 else None
        if not currency_code:
            continue

        # Plain pair — transactional
        plain_buy = _safe_rate(cells[2])
        plain_sell = _safe_rate(cells[3])
        if plain_buy is not None or plain_sell is not None:
            records.append(_make_record(currency_code, currency_name, "transactional",
                                        plain_buy, plain_sell, cells[2], cells[3],
                                        ["date_ambiguous:no_source_published_date"]))

        # Weighted average
        if len(cells) >= 6:
            w_buy = _safe_rate(cells[4])
            w_sell = _safe_rate(cells[5])
            if w_buy is not None or w_sell is not None:
                records.append(_make_record(currency_code, currency_name, "weighted_average",
                                            w_buy, w_sell, cells[4], cells[5],
                                            ["date_ambiguous:no_source_published_date"]))
    return records


def _make_record(code, name, category, buying, selling, buy_text, sell_text, notes):
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
        mapping_notes=notes,
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
        return hashlib.sha256(b"goh_betoch:unparseable").hexdigest()
