import re
from datetime import datetime, date
from typing import Optional

from bs4 import BeautifulSoup

from adapters.base import HTMLTextAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin
from pipeline.category_normalizer import normalize_category

ADAPTER_KEY = "ahadu_html"
SOURCE_URL = "https://ahadubank.com/"

_DATE_SLASH_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_DATE_TEXT_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s*-\s*(\d{1,2})\s*-\s*(\d{4})",
    re.IGNORECASE,
)
_RATE_RE = re.compile(
    r"CURR\s*:\s*([A-Z]{3})\s+Buying Rate\s*:\s*([\d.]+|No Trade)\s+Selling Rate\s*:\s*([\d.]+|No Trade)",
    re.IGNORECASE,
)
_SLIDE_RATE_RE = re.compile(r"^(.*?)\s+Buying:\s*([\d.]+)\s+Selling:\s*([\d.]+)", re.IGNORECASE)

_CURRENCY_MAP = {
    "US - DOLLAR": "USD",
    "US DOLLAR": "USD",
    "USD": "USD",
    "POUND STERLING": "GBP",
    "GBP": "GBP",
    "EURO": "EUR",
    "EUR": "EUR",
    "CANADIAN DOLLAR": "CAD",
    "CAD": "CAD",
    "SAUDI RIYAL": "SAR",
    "SAR": "SAR",
    "UAE DIRHAM": "AED",
    "AED": "AED",
    "SWISS FRANC": "CHF",
    "CHF": "CHF",
    "JAPANESE YEN": "JPY",
    "JPY": "JPY",
}

class AhaduAdapter(FieldStructureMixin, HTMLTextAdapter):

    FIELD_CONFIG = {}

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def requires_category(self) -> bool:
        return False

    def _extract_from_text(self, text: str, soup: BeautifulSoup, **options) -> ParseResult:
        result = ParseResult()

        effective_date = _extract_date(text)
        date_basis = "source_published" if effective_date else "collection_date_fallback"

        category = normalize_category(options.get("category", "transactional"))

        seen_slide_currencies = set()
        slides = soup.find_all("div", class_="swiper-slide") if soup else []
        for s in slides:
            stext = " ".join(s.get_text(" ", strip=True).split())
            m = _SLIDE_RATE_RE.search(stext)
            if not m:
                continue
            cname = m.group(1).strip().upper()
            code = _CURRENCY_MAP.get(cname)
            if not code or code in seen_slide_currencies:
                continue
            seen_slide_currencies.add(code)

            try:
                row_dict = {
                    "buying": m.group(2),
                    "selling": m.group(3),
                }

                cats_to_assign = ["cash", "transactional"] if category != "UNKNOWN" else ["cash"]
                for cat_name in cats_to_assign:
                    detected_records = self.detect_and_emit(
                        data=row_dict,
                        currency=code,
                        effective_date=effective_date,
                        effective_date_basis=date_basis,
                        mapping_notes=["ahadu:carousel_rates"]
                    )
                    for rec in detected_records:
                        rec.category = cat_name
                    result.records.extend(detected_records)
            except Exception as exc:
                result.add_error(f"slide_currency:{code}:{exc}")

        is_weighted_section = "WEIGHTED AVERAGE RATE" in text.upper()
        ticker_category = "weighted_average" if is_weighted_section else category

        for m in _RATE_RE.finditer(text):
            code = m.group(1).upper()
            try:
                row_dict = {
                    "buying": m.group(2),
                    "selling": m.group(3),
                }

                detected_records = self.detect_and_emit(
                    data=row_dict,
                    currency=code,
                    effective_date=effective_date,
                    effective_date_basis=date_basis,
                    mapping_notes=["single_field_pair:transactional_default"]
                )

                for rec in detected_records:
                    if rec.category == 'UNKNOWN':
                        rec.category = ticker_category

                result.records.extend(detected_records)

            except Exception as exc:
                result.add_error(f"currency:{code}:{exc}")

        return result

    def schema_fingerprint(self, raw_content: str) -> str:
        try:
            import hashlib
            soup = BeautifulSoup(raw_content, "html.parser")
            text = " ".join(soup.get_text(" ", strip=True).split())
            markers = ["CURR", "Buying Rate", "Selling Rate"]
            present = [m for m in markers if m in text]
            return hashlib.sha256(str(present).encode()).hexdigest()
        except Exception:
            import hashlib
            return hashlib.sha256(b"ahadu:unparseable").hexdigest()

def _extract_date(text: str) -> Optional[date]:
    m = _DATE_SLASH_RE.search(text)
    if m:
        try:
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return date(year, month, day)
        except ValueError:
            pass

    m_txt = _DATE_TEXT_RE.search(text)
    if m_txt:
        try:
            raw = f"{m_txt.group(1)} {m_txt.group(2)} {m_txt.group(3)}"
            return datetime.strptime(raw, "%B %d %Y").date()
        except ValueError:
            pass

    return None

_adapter = AhaduAdapter()

def parse(raw_html: str, category: str = None) -> tuple:
    result = _adapter.parse(raw_html, category=category) if category else _adapter.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    return _adapter.schema_fingerprint(raw_html)
