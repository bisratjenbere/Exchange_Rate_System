"""
adapters/sidama/adapter.py — Sidama Bank (Type G text extraction).

Parse rules:
- No table. Rates embedded in page text per currency block.
- Date in text: "Daily Rates October 10, 2026" → source_published.
- Per-currency block pattern:
  "CODE Name Cash Buying NNN Birr Cash Selling NNN Birr
   Transactional Buying NNN Birr Transactional Selling NNN Birr
   Prev Weighted Buying NNN|No Trade Birr Prev Weighted Selling NNN|No Trade Birr"
- "No Trade" → None. "Prev Weighted" = weighted_average (previous period — TO VERIFY date).
- No source_record_key. identity_status = derived (source_published date).
- Schema change detection: if expected labels absent → raises ValueError.
- Partial failure: returns (records, errors). Never raises on parse.
"""
import re
from datetime import date
from decimal import Decimal
from typing import Optional
from bs4 import BeautifulSoup

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate
from adapters.base import HTMLTextAdapter, ParseResult

ADAPTER_KEY = "sidama_html"
SOURCE_URL = "https://sidamabanksc.com/exchange-rate/"

_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_DATE_RE = re.compile(rf"({_MONTHS})\s+(\d{{1,2}}),?\s+(\d{{4}})", re.IGNORECASE)
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

# Matches: "USD United States Dollar Cash Buying 161.7237 Birr Cash Selling ..."
# "No Trade" values are NOT followed by "Birr" — Birr is only after numeric values.
_CURRENCY_BLOCK_RE = re.compile(
    r"(?<![A-Za-z])([A-Z]{3})(?![A-Za-z])\s+[A-Za-z ]+?"
    r"Cash Buying\s+([\d.]+|No Trade)(?:\s+Birr)?\s+"
    r"Cash Selling\s+([\d.]+|No Trade)(?:\s+Birr)?\s+"
    r"Transactional Buying\s+([\d.]+|No Trade)(?:\s+Birr)?\s+"
    r"Transactional Selling\s+([\d.]+|No Trade)(?:\s+Birr)?\s+"
    r"Prev Weighted Buying\s+([\d.]+|No Trade)(?:\s+Birr)?\s+"
    r"Prev Weighted Selling\s+([\d.]+|No Trade)(?:\s+Birr)?",
    re.IGNORECASE,
)


class SidamaAdapter(HTMLTextAdapter):
    """Sidama Bank adapter - text extraction with regex patterns."""
    
    def get_source_url(self) -> str:
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        return ADAPTER_KEY
    
    def _extract_from_text(self, text: str, soup: BeautifulSoup, **options) -> ParseResult:
        """Extract exchange rates from normalized text using regex patterns."""
        result = ParseResult()
        
        effective_date = _extract_date(text)
        date_basis = "source_published" if effective_date else "collection_date_fallback"
        
        for m in _CURRENCY_BLOCK_RE.finditer(text):
            try:
                recs = _parse_match(m, effective_date, date_basis)
                result.records.extend(recs)
            except Exception as exc:
                result.add_error(f"currency_block:{m.group(1)}:{exc}")
        
        return result
    
    def schema_fingerprint(self, raw_content: str) -> str:
        """Generate fingerprint based on presence of text markers."""
        try:
            soup = BeautifulSoup(raw_content, "html.parser")
            text = " ".join(soup.get_text(" ", strip=True).split())
            markers = ["Cash Buying", "Cash Selling", "Transactional Buying", "Prev Weighted"]
            present = [m for m in markers if m in text]
            import hashlib
            return hashlib.sha256(str(present).encode()).hexdigest()
        except Exception:
            import hashlib
            return hashlib.sha256(b"sidama:unparseable").hexdigest()


def _parse_match(m, effective_date, date_basis) -> list:
    """Parse a single currency block match into AdapterRecords."""
    code = m.group(1).upper()
    values = {
        "cash": (m.group(2), m.group(3)),
        "transactional": (m.group(4), m.group(5)),
        "weighted_average": (m.group(6), m.group(7)),
    }
    records = []
    for category, (buy_raw, sell_raw) in values.items():
        buying = _safe_rate(buy_raw)
        selling = _safe_rate(sell_raw)
        if buying is None and selling is None:
            continue
        records.append(AdapterRecord(
            source_currency_code=code,
            category=category,
            buying_rate=buying,
            selling_rate=selling,
            source_rate_text=f"{buy_raw}/{sell_raw}",
            effective_date=effective_date,
            effective_date_basis=date_basis,
            source_record_key=None,
            source_publication_key=None,
            unit_multiplier=1,
            raw_excerpt={"currency": code, "buying": buy_raw, "selling": sell_raw},
            mapping_notes=["prev_weighted_date_semantics:TO_VERIFY"] if category == "weighted_average" else [],
        ))
    return records


def _extract_date(text: str) -> Optional[date]:
    """Extract date from text in format like 'October 10, 2026'."""
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


def _safe_rate(raw: str) -> Optional[Decimal]:
    """Convert raw rate string to Decimal, returning None on failure."""
    if not raw or raw.strip().lower() == "no trade":
        return None
    try:
        return normalize_rate(raw.strip())
    except ValueError:
        return None


# ============================================================================
# MODULE-LEVEL WRAPPER FUNCTIONS FOR BACKWARD COMPATIBILITY
# ============================================================================

_adapter_instance = SidamaAdapter()

def parse(raw_html: str) -> tuple:
    """Parse Sidama Bank HTML into records. Module-level wrapper."""
    result = _adapter_instance.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    """Generate schema fingerprint. Module-level wrapper."""
    return _adapter_instance.schema_fingerprint(raw_html)
