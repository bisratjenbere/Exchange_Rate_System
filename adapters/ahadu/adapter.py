"""
adapters/ahadu/adapter.py — Ahadu Bank (Type G text extraction).

Parse rules:
- No table. Rates in page text pattern:
  "CURR : CODE Buying Rate : NNN|No Trade Selling Rate : NNN|No Trade"
- Date in text: "EXCHANGE RATE FOR : DD/MM/YYYY" → source_published.
- Single buying/selling pair — category UNKNOWN (unconfirmed).
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

ADAPTER_KEY = "ahadu_html"
SOURCE_URL = "https://ahadubank.com/"

_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_RATE_RE = re.compile(
    r"CURR\s*:\s*([A-Z]{3})\s+Buying Rate\s*:\s*([\d.]+|No Trade)\s+Selling Rate\s*:\s*([\d.]+|No Trade)",
    re.IGNORECASE,
)


def parse(raw_html: str, category: str = "UNKNOWN") -> tuple:
    soup = BeautifulSoup(raw_html, "html.parser")
    text = " ".join(soup.get_text(" ", strip=True).split())

    effective_date = _extract_date(text)
    date_basis = "source_published" if effective_date else "collection_date_fallback"

    records, errors = [], []
    for m in _RATE_RE.finditer(text):
        code = m.group(1).upper()
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
    try:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return date(year, month, day)
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
        text = " ".join(soup.get_text(" ", strip=True).split())
        markers = ["CURR", "Buying Rate", "Selling Rate"]
        present = [m for m in markers if m in text]
        return hashlib.sha256(str(present).encode()).hexdigest()
    except Exception:
        return hashlib.sha256(b"ahadu:unparseable").hexdigest()
