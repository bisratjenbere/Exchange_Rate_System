"""
adapters/berhan/adapter.py — Berhan Bank (Type G text extraction).

Parse rules:
- No table. Rates in page text: "1 CODE (symbol) buying selling".
- Date in text: "Oct 12, 2026" → source_published.
- Pattern: "1 USD ($) 161.7225 164.9570"
- Single buying/selling pair — category UNKNOWN (unconfirmed).
- unit_multiplier = 1 (confirmed from "1 CODE" prefix).
- "No Trade" → None.
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

ADAPTER_KEY = "berhan_html"
SOURCE_URL = "https://berhanbanksc.com/exchange-rates/"

_MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
_DATE_RE = re.compile(rf"({_MONTHS})\w*\s+(\d{{1,2}}),?\s+(\d{{4}})", re.IGNORECASE)
_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Matches: "1 USD ($) 161.7225 164.9570" or "1 AED 44.0325 44.9131"
_RATE_RE = re.compile(
    r"1\s+([A-Z]{3})\s*(?:\([^)]*\))?\s+([\d.]+|No Trade)\s+([\d.]+|No Trade)",
    re.IGNORECASE,
)


def parse(raw_html: str, category: str = "UNKNOWN") -> tuple:
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(" ", strip=True)

    effective_date = _extract_date(text)
    date_basis = "source_published" if effective_date else "collection_date_fallback"

    records, errors = [], []
    seen = set()
    for m in _RATE_RE.finditer(text):
        code = m.group(1).upper()
        if code in seen:
            continue
        seen.add(code)
        try:
            buying = _safe_rate(m.group(2))
            selling = _safe_rate(m.group(3))
            if buying is None and selling is None:
                continue
            records.append(AdapterRecord(
                source_currency_code=code,
                category=category,
                buying_rate=buying,
                selling_rate=selling,
                source_rate_text=f"{m.group(2)}/{m.group(3)}",
                effective_date=effective_date,
                effective_date_basis=date_basis,
                source_record_key=None,
                source_publication_key=None,
                unit_multiplier=1,
                raw_excerpt={"currency": code, "buying": m.group(2), "selling": m.group(3)},
                mapping_notes=["category_unknown:single_pair_unconfirmed"],
            ))
        except Exception as exc:
            errors.append(f"currency:{code}:{exc}")

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


def _safe_rate(raw: str) -> Optional[Decimal]:
    if not raw or raw.strip().lower() == "no trade":
        return None
    try:
        return normalize_rate(raw.strip())
    except ValueError:
        return None


def schema_fingerprint(raw_html: str) -> str:
    try:
        soup = BeautifulSoup(raw_html, "html.parser")
        text = soup.get_text(" ", strip=True)
        markers = ["Currency", "Buying", "Selling"]
        present = [m for m in markers if m in text]
        return hashlib.sha256(str(present).encode()).hexdigest()
    except Exception:
        return hashlib.sha256(b"berhan:unparseable").hexdigest()
