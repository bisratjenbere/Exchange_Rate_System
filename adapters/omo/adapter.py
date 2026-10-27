import re
from datetime import date
from typing import Optional
from bs4 import BeautifulSoup

from adapters.base import HTMLTableAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin

ADAPTER_KEY = "omo_html"
SOURCE_URL = "https://omobanksc.com/"

_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")

class OmoAdapter(FieldStructureMixin, HTMLTableAdapter):

    FIELD_CONFIG = {}
    EXPECTED_CATEGORIES = ["cash", "transactional", "weighted_average"]

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def _process_tables(self, soup: BeautifulSoup, tables: list, **kwargs) -> ParseResult:
        result = ParseResult()

        if not tables:
            for category in self.EXPECTED_CATEGORIES:
                result.add_error(f"table_{category}:missing")
            return result

        found_categories = set()
        for idx, table in enumerate(tables):
            category = self.extract_table_category(table, soup)
            if category == "UNKNOWN":
                continue
            found_categories.add(category)
            try:
                records = _parse_table(self, table, category)
                result.records.extend(records)
            except Exception as exc:
                result.add_error(f"table_{idx}_{category}:{exc}")

        for expected in self.EXPECTED_CATEGORIES:
            if expected not in found_categories:
                result.add_error(f"table_{expected}:missing")

        return result

def _parse_table(adapter, table, category: str) -> list:
    rows = table.find_all("tr")
    if not rows:
        return []

    header_text = rows[0].get_text(" ", strip=True)
    effective_date = _parse_date(header_text)
    date_basis = "source_published" if effective_date else "collection_date_fallback"

    records = []
    for row in rows[1:]:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 4:
            continue
        currency_code, currency_name = _parse_currency(cells[1])
        if not currency_code:
            continue

        row_dict = {"buying": cells[2], "selling": cells[3]}
        detected_records = adapter.detect_and_emit(
            data=row_dict,
            currency=currency_code,
            currency_name=currency_name,
            effective_date=effective_date,
            effective_date_basis=date_basis
        )

        for rec in detected_records:
            if rec.category == 'UNKNOWN':
                rec.category = category

        records.extend(detected_records)
    return records

def _parse_currency(text: str) -> tuple:
    for sep in (" \u2013 ", " - "):
        if sep in text:
            parts = text.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    text = text.strip()
    return (text, None) if text else ("", None)

def _parse_date(text: str) -> Optional[date]:
    m = _DATE_RE.search(text)
    if not m:
        return None
    try:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return date(year, month, day)
    except ValueError:
        return None

_adapter_instance = OmoAdapter()

def parse(raw_html: str) -> tuple:
    result = _adapter_instance.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    return _adapter_instance.schema_fingerprint(raw_html)
