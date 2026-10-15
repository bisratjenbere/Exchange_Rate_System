"""
adapters/berhan/adapter.py — Berhan Bank (hidden input JSON).

Parse rules:
- Rates in hidden <input type="hidden"> tags with JSON values:
  {"buying":"161.7225","selling":"164.9570","currency":"USD","currencyText":"1_USD_($)"}
- Date in page text: "Oct 13, 2026" → source_published.
- Single buying/selling pair per currency — category: transactional.
- 6 currencies: USD, EUR, GBP, CAD, AED, YUA.
- Partial failure: returns (records, errors). Never raises.
"""
import hashlib
import json
import re
from datetime import date
from decimal import Decimal
from typing import Optional

from bs4 import BeautifulSoup

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "berhan_html"
SOURCE_URL = "https://berhanbanksc.com/exchange-rates/"

_MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
_DATE_RE = re.compile(rf"({_MONTHS})\w*\s+(\d{{1,2}}),?\s+(\d{{4}})", re.IGNORECASE)
_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse(raw_html: str) -> tuple:
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(" ", strip=True)

    effective_date = _extract_date(text)
    date_basis = "source_published" if effective_date else "collection_date_fallback"

    inputs = [i for i in soup.find_all("input", type="hidden")
              if i.get("value", "").startswith("{")]

    records, errors = [], []
    for inp in inputs:
        try:
            row = json.loads(inp["value"])
            code = str(row.get("currency", "")).strip()
            if not code:
                continue
            buying = _safe_rate(row.get("buying"))
            selling = _safe_rate(row.get("selling"))
            if buying is None and selling is None:
                continue
            records.append(AdapterRecord(
                source_currency_code=code,
                category="transactional",
                buying_rate=buying,
                selling_rate=selling,
                source_rate_text=f"{row.get('buying')}/{row.get('selling')}",
                effective_date=effective_date,
                effective_date_basis=date_basis,
                source_record_key=None,
                source_publication_key=None,
                unit_multiplier=1,
                raw_excerpt={"currency": code, "buying": row.get("buying"),
                             "selling": row.get("selling")},
                mapping_notes=[],
            ))
        except Exception as exc:
            errors.append(f"input:{inp.get('id')}:{exc}")

    return records, errors


def _extract_date(text: str) -> Optional[date]:
    m = _DATE_RE.search(text)
    if not m:
        return None
    month = _MONTH_MAP.get(m.group(1).lower()[:3])
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
        inputs = [i for i in soup.find_all("input", type="hidden")
                  if i.get("value", "").startswith("{")]
        ids = sorted(i.get("id", "") for i in inputs)
        return hashlib.sha256(str({"input_ids": ids}).encode()).hexdigest()
    except Exception:
        return hashlib.sha256(b"berhan:unparseable").hexdigest()
