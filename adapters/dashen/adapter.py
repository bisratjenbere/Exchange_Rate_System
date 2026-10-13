"""
adapters/dashen/adapter.py — Dashen Bank (Type D, multi-table HTML).

Parse rules (ADR-006 §6, mapping doc):
- Input: static HTML page with exactly 3 <table> elements.
  Table 0 = transactional, Table 1 = cash, Table 2 = weighted_average.
- Each table is parsed independently. Per-table dates are never shared.
- Table 2 header embeds the effective date: "Weighted Average Rate on <Month DD, YYYY>".
- Tables 0 and 1 have no source-published date → effective_date_basis=collection_date_fallback
  → identity_status=ambiguous (fallback dates never participate in identity, LOCKED rule).
- Table 2 date parsed → effective_date_basis=source_published → identity_status=derived.
- Spread column (last column) is ignored.
- "No Trade" / "-" / empty → None. No zeros observed but sentinel rule applies.
- Partial failure: if one table is missing/malformed, emit what was parsed and record the error.
  Never apply values from one table to another.
"""
import hashlib
import re
from datetime import date
from decimal import Decimal
from typing import Optional

from bs4 import BeautifulSoup

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "dashen_html"
SOURCE_URL = "https://dashenbanksc.com/daily-exchange-rates/"

# Table index → category
_TABLE_CATEGORIES = {0: "transactional", 1: "cash", 2: "weighted_average"}

# Regex to extract date from weighted average header
_DATE_RE = re.compile(
    r"on\s+([A-Za-z]+ \d{1,2},\s*\d{4})", re.IGNORECASE
)
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def parse(raw_html: str) -> tuple:
    """
    Parse the Dashen HTML page.
    Returns (records: list[AdapterRecord], errors: list[str]).
    Partial failure: errors are non-empty when a table could not be parsed.
    Never raises — errors are collected and returned.
    """
    soup = BeautifulSoup(raw_html, "html.parser")
    tables = soup.find_all("table")

    records = []
    errors = []

    for idx, category in _TABLE_CATEGORIES.items():
        if idx >= len(tables):
            errors.append(f"table_{idx}_{category}:missing")
            continue
        try:
            table_records = _parse_table(tables[idx], idx, category)
            records.extend(table_records)
        except Exception as exc:
            errors.append(f"table_{idx}_{category}:{exc}")

    return records, errors


def _parse_table(table, idx: int, category: str) -> list:
    rows = table.find_all("tr")
    if not rows:
        return []

    if category == "weighted_average":
        return _parse_weighted_table(rows)
    else:
        return _parse_standard_table(rows, category)


def _parse_standard_table(rows, category: str) -> list:
    """Parse transactional or cash table (no date in header)."""
    # Row 0 is header — identify buying/selling column indices
    header_cells = [c.get_text(strip=True).lower() for c in rows[0].find_all(["th", "td"])]
    buy_idx = _find_col(header_cells, ["transaction buying", "cash buying", "buying"])
    sell_idx = _find_col(header_cells, ["transaction selling", "cash selling", "selling"])
    if buy_idx is None or sell_idx is None:
        raise ValueError(f"Cannot find buying/selling columns in header: {header_cells}")

    records = []
    for row in rows[1:]:
        cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
        if len(cells) < max(buy_idx, sell_idx) + 1:
            continue
        currency_code = cells[0].strip()
        currency_name = cells[1].strip() if len(cells) > 1 else None
        if not currency_code:
            continue

        buying = _safe_rate(cells[buy_idx])
        selling = _safe_rate(cells[sell_idx])
        if buying is None and selling is None:
            continue

        records.append(AdapterRecord(
            source_currency_code=currency_code,
            currency_name=currency_name or None,
            category=category,
            buying_rate=buying,
            selling_rate=selling,
            source_rate_text=f"{cells[buy_idx]}/{cells[sell_idx]}",
            effective_date=None,
            effective_date_basis="collection_date_fallback",
            source_record_key=None,
            source_publication_key=None,
            raw_excerpt={"currency": currency_code, "buying": cells[buy_idx], "selling": cells[sell_idx]},
            mapping_notes=["date_ambiguous:no_source_published_date_in_table"],
        ))
    return records


def _parse_weighted_table(rows) -> list:
    """Parse weighted average table — date embedded in row 0 header cell."""
    # Row 0: merged header with date text
    # Row 1: Buying | Selling sub-header
    # Row 2+: data
    if len(rows) < 3:
        return []

    header_text = rows[0].get_text(" ", strip=True)
    effective_date = _extract_date(header_text)
    date_basis = "source_published" if effective_date else "collection_date_fallback"

    records = []
    for row in rows[2:]:
        cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
        if len(cells) < 4:
            continue
        currency_code = cells[0].strip()
        currency_name = cells[1].strip() if len(cells) > 1 else None
        if not currency_code:
            continue

        buying = _safe_rate(cells[2])
        selling = _safe_rate(cells[3])
        if buying is None and selling is None:
            continue

        records.append(AdapterRecord(
            source_currency_code=currency_code,
            currency_name=currency_name or None,
            category="weighted_average",
            buying_rate=buying,
            selling_rate=selling,
            source_rate_text=f"{cells[2]}/{cells[3]}",
            effective_date=effective_date,
            effective_date_basis=date_basis,
            source_record_key=None,
            source_publication_key=None,
            raw_excerpt={"currency": currency_code, "buying": cells[2], "selling": cells[3],
                         "header_text": header_text},
            mapping_notes=(
                ["date_from_weighted_avg_header:source_published"]
                if effective_date else
                ["date_missing_from_weighted_avg_header:collection_date_fallback"]
            ),
        ))
    return records


def _extract_date(text: str) -> Optional[date]:
    """Extract date from 'Weighted Average Rate on October 09, 2026'."""
    m = _DATE_RE.search(text)
    if not m:
        return None
    date_str = m.group(1).strip()
    # "October 09, 2026" or "October 9, 2026"
    parts = re.split(r"[\s,]+", date_str)
    if len(parts) < 3:
        return None
    month_name = parts[0].lower()
    month = _MONTH_MAP.get(month_name)
    if not month:
        return None
    try:
        day = int(parts[1])
        year = int(parts[2])
        return date(year, month, day)
    except (ValueError, IndexError):
        return None


def _find_col(headers: list, candidates: list) -> Optional[int]:
    for candidate in candidates:
        for i, h in enumerate(headers):
            if candidate in h:
                return i
    return None


def _safe_rate(raw) -> Optional[Decimal]:
    try:
        return normalize_rate(raw)
    except ValueError:
        return None


def schema_fingerprint(raw_html: str) -> str:
    """
    Deterministic hash of structural signature:
    number of tables + per-table header texts.
    """
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
        return hashlib.sha256(b"dashen:unparseable").hexdigest()
