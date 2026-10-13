"""
adapters/cbo/adapter.py — Cooperative Bank of Oromia (Type E wide HTML).

Parse rules (ADR-006 §6, mapping doc):
- Input: static HTML with 2 tables.
  Table 0: Cash + Transaction combined. Header row 0 embeds date ("Exchange RateOctober 10, 2026").
           Header row 1: Currency | Cash | Transaction
           Header row 2: Buying | Selling | Buying | Selling
  Table 1: Weighted Average. Headers: Currency | Weighted Average Rate | Buying | Selling
- Date extracted from table 0 header → applied to all records (both tables share the same date).
- effective_date_basis = source_published when date found; collection_date_fallback otherwise.
- Dash "-" = no trade → None.
- Currency format: "CODE - Name" — code extracted as first token before " - ".
- Partial failure: returns records + errors list. Never raises.
"""
import hashlib
import re
from datetime import date
from decimal import Decimal
from typing import Optional

from bs4 import BeautifulSoup

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "cbo_html"
SOURCE_URL = "https://coopbankoromia.com.et/daily-exchange-rates/"

_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_DATE_RE = re.compile(
    rf"({_MONTHS})\s+(\d{{1,2}}),?\s+(\d{{4}})", re.IGNORECASE
)
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def parse(raw_html: str) -> tuple:
    """
    Returns (records: list[AdapterRecord], errors: list[str]).
    Partial failure: errors non-empty when a table could not be parsed.
    Never raises.
    """
    soup = BeautifulSoup(raw_html, "html.parser")
    tables = soup.find_all("table")

    records = []
    errors = []
    effective_date = None

    if len(tables) < 1:
        errors.append("table_0_cash_txn:missing")
        errors.append("table_1_weighted_avg:missing")
        return records, errors

    # Extract date from table 0 header
    try:
        effective_date = _extract_date_from_table(tables[0])
    except Exception as exc:
        errors.append(f"date_extraction:{exc}")

    date_basis = "source_published" if effective_date else "collection_date_fallback"

    # Parse table 0 — cash + transactional
    try:
        records.extend(_parse_cash_txn_table(tables[0], effective_date, date_basis))
    except Exception as exc:
        errors.append(f"table_0_cash_txn:{exc}")

    # Parse table 1 — weighted average
    if len(tables) < 2:
        errors.append("table_1_weighted_avg:missing")
    else:
        try:
            records.extend(_parse_weighted_table(tables[1], effective_date, date_basis))
        except Exception as exc:
            errors.append(f"table_1_weighted_avg:{exc}")

    return records, errors


def _extract_date_from_table(table) -> Optional[date]:
    """Extract date from first header row text like 'Exchange RateOctober 10, 2026'."""
    rows = table.find_all("tr")
    if not rows:
        return None
    header_text = rows[0].get_text(" ", strip=True)
    return _parse_date_text(header_text)


def _parse_cash_txn_table(table, effective_date: Optional[date], date_basis: str) -> list:
    """Parse table 0: multi-level header, cash cols 1-2, txn cols 3-4."""
    rows = table.find_all("tr")
    # Skip header rows (rows 0, 1, 2) — data starts at row 3
    data_rows = [r for r in rows if _is_data_row(r)]
    if not data_rows:
        return []

    records = []
    for row in data_rows:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 5:
            continue
        currency_code, currency_name = _parse_currency_cell(cells[0])
        if not currency_code:
            continue

        for category, buy_idx, sell_idx in [("cash", 1, 2), ("transactional", 3, 4)]:
            buying = _safe_rate(cells[buy_idx])
            selling = _safe_rate(cells[sell_idx])
            if buying is None and selling is None:
                continue
            records.append(AdapterRecord(
                source_currency_code=currency_code,
                currency_name=currency_name,
                category=category,
                buying_rate=buying,
                selling_rate=selling,
                source_rate_text=f"{cells[buy_idx]}/{cells[sell_idx]}",
                effective_date=effective_date,
                effective_date_basis=date_basis,
                source_record_key=None,
                source_publication_key=None,
                unit_multiplier=1,
                raw_excerpt={"currency": cells[0], "buying": cells[buy_idx], "selling": cells[sell_idx]},
                mapping_notes=["dash_equals_no_trade:TO_VERIFY"],
            ))
    return records


def _parse_weighted_table(table, effective_date: Optional[date], date_basis: str) -> list:
    """Parse table 1: Currency | Buying | Selling."""
    rows = table.find_all("tr")
    data_rows = [r for r in rows if _is_data_row(r)]
    if not data_rows:
        return []

    records = []
    for row in data_rows:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        currency_code, currency_name = _parse_currency_cell(cells[0])
        if not currency_code:
            continue

        buying = _safe_rate(cells[1])
        selling = _safe_rate(cells[2])
        if buying is None and selling is None:
            continue
        records.append(AdapterRecord(
            source_currency_code=currency_code,
            currency_name=currency_name,
            category="weighted_average",
            buying_rate=buying,
            selling_rate=selling,
            source_rate_text=f"{cells[1]}/{cells[2]}",
            effective_date=effective_date,
            effective_date_basis=date_basis,
            source_record_key=None,
            source_publication_key=None,
            unit_multiplier=1,
            raw_excerpt={"currency": cells[0], "buying": cells[1], "selling": cells[2]},
            mapping_notes=["dash_equals_no_trade:TO_VERIFY"],
        ))
    return records


def _is_data_row(row) -> bool:
    """True if row has <td> cells (not header-only)."""
    return bool(row.find("td"))


def _parse_currency_cell(text: str) -> tuple:
    """Parse 'USD - US Dollar' → ('USD', 'US Dollar'). Returns ('', None) if unparseable."""
    text = text.strip()
    if " - " in text:
        parts = text.split(" - ", 1)
        return parts[0].strip(), parts[1].strip()
    if text:
        return text, None
    return "", None


def _parse_date_text(text: str) -> Optional[date]:
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
    """Hash of table count + per-table header structure."""
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
        return hashlib.sha256(b"cbo:unparseable").hexdigest()
