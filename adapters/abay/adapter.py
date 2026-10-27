import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from adapters.base import HTMLTableAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin
from pipeline.category_normalizer import normalize_category

ADAPTER_KEY = "abay_html"
SOURCE_URL = "https://www.abaybanksc.com/"

_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_DATE_RE = re.compile(rf"({_MONTHS})\s+(\d{{1,2}}),?\s+(\d{{4}})", re.IGNORECASE)
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

class AbayAdapter(FieldStructureMixin, HTMLTableAdapter):

    FIELD_CONFIG = {}
    EXPECTED_CATEGORIES = ["weighted_average", "cash", "transactional"]

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def _process_tables(self, soup: BeautifulSoup, tables: list, **options) -> ParseResult:
        result = ParseResult()

        if not tables:
            for expected in self.EXPECTED_CATEGORIES:
                result.add_error(f"table_{expected}:missing")
            return result

        text = soup.get_text(" ", strip=True)
        effective_date = self._extract_date(text)
        date_basis = "source_published" if effective_date else "collection_date_fallback"

        found_categories = set()
        for idx, table in enumerate(tables):
            category = self.extract_table_category(table, soup)
            if category == "UNKNOWN":
                continue
            found_categories.add(category)
            try:
                records = self._parse_table(table, category, effective_date, date_basis)
                result.records.extend(records)
            except Exception as exc:
                result.add_error(f"table_{idx}_{category}:{exc}")

        for expected in self.EXPECTED_CATEGORIES:
            if expected not in found_categories:
                result.add_error(f"table_{expected}:missing")

        return result

    def _extract_date(self, text: str) -> Optional[date]:
        best = None
        for m in _DATE_RE.finditer(text):
            month = _MONTH_MAP.get(m.group(1).lower())
            if not month:
                continue
            try:
                d = date(int(m.group(3)), month, int(m.group(2)))
                if d.year >= 2020 and (best is None or d > best):
                    best = d
            except ValueError:
                continue
        return best

    def _parse_table(self, table, expected_category: str, effective_date: Optional[date], date_basis: str) -> list:
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 3:
                continue
            currency_code = cells[0].strip()
            if not currency_code:
                continue

            row_dict = {
                "buying": cells[1],
                "selling": cells[2],
            }

            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=currency_code,
                effective_date=effective_date,
                effective_date_basis=date_basis
            )

            for rec in detected_records:
                if rec.category == 'UNKNOWN':
                    rec.category = normalize_category(expected_category)

            records.extend(detected_records)
        return records

def parse(raw_html: str) -> tuple:
    adapter = AbayAdapter()
    result = adapter.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    return AbayAdapter().schema_fingerprint(raw_html)
