import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from adapters.base import HTMLTextAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin
from pipeline.category_normalizer import normalize_category

ADAPTER_KEY = "enat_html"
SOURCE_URL = "https://www.enatbanksc.com/"

_MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
_DATE_RE = re.compile(rf"({_MONTHS})\w*\s+(\d{{1,2}}),?\s+(\d{{4}})", re.IGNORECASE)
_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_RATE_RE = re.compile(r"([A-Z]{3})\s+([\d.]+)\s+([\d.]+)")

_BLOCK_START = re.compile(r"Currency\s+Buying\s+Selling", re.IGNORECASE)

class EnatAdapter(FieldStructureMixin, HTMLTextAdapter):

    FIELD_CONFIG = {}

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def requires_category(self) -> bool:
        return True

    def _extract_from_text(self, text: str, soup: BeautifulSoup, **options) -> ParseResult:
        result = ParseResult()

        category = normalize_category(options.get("category", "UNKNOWN"))

        effective_date = _extract_date(text)
        date_basis = "source_published" if effective_date else "collection_date_fallback"

        m_start = _BLOCK_START.search(text)
        if not m_start:
            return result

        rate_text = text[m_start.end():]
        seen = set()

        for m in _RATE_RE.finditer(rate_text):
            code = m.group(1).upper()
            if code in seen:
                break
            seen.add(code)
            try:
                row_dict = {
                    "buying": m.group(2),
                    "selling": m.group(3),
                }

                cats_to_assign = ["cash", "transactional"] if category != "UNKNOWN" else ["UNKNOWN"]
                for cat_name in cats_to_assign:
                    detected_records = self.detect_and_emit(
                        data=row_dict,
                        currency=code,
                        effective_date=effective_date,
                        effective_date_basis=date_basis,
                        mapping_notes=["enat:cash_and_transaction_published"]
                    )
                    for rec in detected_records:
                        rec.category = cat_name
                    result.records.extend(detected_records)

            except Exception as exc:
                result.add_error(f"currency:{code}:{exc}")

        return result

    def schema_fingerprint(self, raw_content: str) -> str:
        try:
            import hashlib
            soup = BeautifulSoup(raw_content, "html.parser")
            text = " ".join(soup.get_text(" ", strip=True).split())
            markers = ["Currency Buying Selling", "Swift"]
            present = [m for m in markers if m in text]
            return hashlib.sha256(str(present).encode()).hexdigest()
        except Exception:
            import hashlib
            return hashlib.sha256(b"enat:unparseable").hexdigest()

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

def parse(raw_html: str, category: str = "UNKNOWN") -> tuple:
    adapter = EnatAdapter()
    result = adapter.parse(raw_html, category=category)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    return EnatAdapter().schema_fingerprint(raw_html)
