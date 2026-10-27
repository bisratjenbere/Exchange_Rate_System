import re
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from bs4 import BeautifulSoup

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate
from adapters.base import BankAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin
from pipeline.category_normalizer import normalize_category

ADAPTER_KEY = "shabelle_html"
SOURCE_URL = "https://shabellebank.com/"

_CODE_MAP = {"usd": "USD", "euro": "EUR", "eur": "EUR", "uae": "AED"}

class ShabelleAdapter(FieldStructureMixin, BankAdapter):

    FIELD_CONFIG = {}

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def parse(self, raw_content: str, **options) -> ParseResult:
        result = ParseResult()

        soup = BeautifulSoup(raw_content, "html.parser")

        effective_date = _parse_date(soup)
        date_basis = "source_published" if effective_date else "collection_date_fallback"

        blocks = soup.find_all("div", class_="exchange-block-one")
        if not blocks:
            result.add_error("no_exchange_blocks")
            return result

        for block in blocks:
            try:
                records = _parse_block(block, effective_date, date_basis, self)
                result.records.extend(records)
            except Exception as exc:
                result.add_error(f"block:{exc}")

        return result

    def schema_fingerprint(self, raw_content: str) -> str:
        try:
            soup = BeautifulSoup(raw_content, "html.parser")
            blocks = soup.find_all("div", class_="exchange-block-one")
            codes = []
            for b in blocks:
                h4 = b.find("h4")
                if h4:
                    codes.append(h4.get_text(strip=True))
            import hashlib
            return hashlib.sha256(str({"blocks": len(blocks), "codes": codes}).encode()).hexdigest()
        except Exception:
            import hashlib
            return hashlib.sha256(b"shabelle:unparseable").hexdigest()

def _parse_block(block, effective_date, date_basis, adapter_instance) -> list:
    records = []
    for box_class, expected_category in [("upper-box", "cash"), ("lower-box", "transactional")]:
        box = block.find("div", class_=box_class)
        if not box:
            continue
        h4 = box.find("h4")
        if not h4:
            continue
        raw_code = h4.get_text(strip=True)
        code = _CODE_MAP.get(raw_code.lower(), raw_code.upper())

        buys_box = box.find("div", class_="buys-box")
        if not buys_box:
            continue
        p = buys_box.find("p")
        if not p:
            continue

        values = p.get_text(strip=True).split()
        if len(values) < 2:
            continue

        row_dict = {
            "buying": values[0],
            "selling": values[1],
        }

        detected_records = adapter_instance.detect_and_emit(
            data=row_dict,
            currency=code,
            effective_date=effective_date,
            effective_date_basis=date_basis
        )

        box_text = box.get_text(" ", strip=True)
        detected_cat = normalize_category(box_text)
        category = detected_cat if detected_cat != "UNKNOWN" else normalize_category(expected_category)

        for rec in detected_records:
            if rec.category == 'UNKNOWN':
                rec.category = category

        records.extend(detected_records)

    return records

def _parse_date(soup) -> Optional[date]:
    text = soup.get_text(" ")
    m = re.search(r"Applicable\s+on\s+([\d]{1,2})[- ]+(\w+)\s*[-]?\s*(\d{4})", text, re.I)
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y").date()
    except ValueError:
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %b %Y").date()
        except ValueError:
            return None

def _safe_rate(raw) -> Optional[Decimal]:
    if not raw or str(raw).strip().lower() in ("no trade", "no_trade", "-", ""):
        return None
    try:
        return normalize_rate(raw)
    except ValueError:
        return None

_adapter_instance = ShabelleAdapter()

def parse(raw_html: str) -> tuple:
    result = _adapter_instance.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    return _adapter_instance.schema_fingerprint(raw_html)
