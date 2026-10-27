import re
from datetime import date
from typing import Optional
from bs4 import BeautifulSoup

from adapters.base import HTMLTextAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin
from pipeline.category_normalizer import normalize_category

ADAPTER_KEY = "sidama_html"
SOURCE_URL = "https://sidamabanksc.com/exchange-rate/"

_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_DATE_RE = re.compile(rf"({_MONTHS})\s+(\d{{1,2}}),?\s+(\d{{4}})", re.IGNORECASE)
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

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

class SidamaAdapter(FieldStructureMixin, HTMLTextAdapter):

    FIELD_CONFIG = {}

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def _extract_from_text(self, text: str, soup: BeautifulSoup, **options) -> ParseResult:
        result = ParseResult()

        effective_date = _extract_date(text)
        date_basis = "source_published" if effective_date else "collection_date_fallback"

        for m in _CURRENCY_BLOCK_RE.finditer(text):
            try:
                recs = self._parse_match(m, effective_date, date_basis)
                result.records.extend(recs)
            except Exception as exc:
                result.add_error(f"currency_block:{m.group(1)}:{exc}")

        return result

    def _parse_match(self, m, effective_date, date_basis) -> list:
        code = m.group(1).upper()
        row_dict = {
            "cash_buying": m.group(2),
            "cash_selling": m.group(3),
            "transactional_buying": m.group(4),
            "transactional_selling": m.group(5),
            "weighted_buying": m.group(6),
            "weighted_selling": m.group(7),
        }
        return self.detect_and_emit(
            data=row_dict,
            currency=code,
            effective_date=effective_date,
            effective_date_basis=date_basis,
        )

    def schema_fingerprint(self, raw_content: str) -> str:
        try:
            import hashlib
            soup = BeautifulSoup(raw_content, "html.parser")
            text = " ".join(soup.get_text(" ", strip=True).split())
            markers = ["Cash Buying", "Cash Selling", "Transactional Buying", "Prev Weighted"]
            present = [m for m in markers if m in text]
            return hashlib.sha256(str(present).encode()).hexdigest()
        except Exception:
            import hashlib
            return hashlib.sha256(b"sidama:unparseable").hexdigest()

def _extract_date(text: str) -> Optional[date]:
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

_adapter_instance = SidamaAdapter()

def parse(raw_html: str) -> tuple:
    result = _adapter_instance.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    return _adapter_instance.schema_fingerprint(raw_html)
