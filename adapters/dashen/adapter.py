import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from adapters.base import HTMLTableAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin
from pipeline.category_normalizer import normalize_category

ADAPTER_KEY = "dashen_html"
SOURCE_URL = "https://dashenbanksc.com/daily-exchange-rates/"

_DATE_RE = re.compile(
    r"on\s+([A-Za-z]+ \d{1,2},\s*\d{4})", re.IGNORECASE
)
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

class DashenAdapter(FieldStructureMixin, HTMLTableAdapter):

    FIELD_CONFIG = {}
    EXPECTED_CATEGORIES = ["transactional", "cash", "weighted_average"]

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def parse(self, raw_content: str, **options) -> ParseResult:
        soup = BeautifulSoup(raw_content, "html.parser")
        tables = soup.find_all("table")
        return self._process_tables(soup, tables, **options)

    def _process_tables(self, soup: BeautifulSoup, tables: list, **options) -> ParseResult:
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
                table_records = self._parse_table(table, idx, category)
                result.records.extend(table_records)
            except Exception as exc:
                result.add_error(f"table_{idx}_{category}:{exc}")

        for expected_category in self.EXPECTED_CATEGORIES:
            if expected_category not in found_categories:
                result.add_error(f"table_{expected_category}:missing")

        return result

    def _parse_table(self, table, idx: int, category: str) -> list:
        rows = table.find_all("tr")
        if not rows:
            return []

        if category == "weighted_average":
            return self._parse_weighted_table(rows, category)
        else:
            return self._parse_standard_table(rows, category)

    def _parse_standard_table(self, rows, category: str) -> list:
        header_row = rows[0]
        headers = [c.get_text(strip=True).lower() for c in header_row.find_all(["th", "td"])]

        buy_idx = None
        sell_idx = None
        for i, h in enumerate(headers):
            if "buy" in h:
                buy_idx = i
            elif "sell" in h:
                sell_idx = i

        if buy_idx is None or sell_idx is None:
            return []

        records = []
        for row in rows[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
            if len(cells) <= max(buy_idx, sell_idx):
                continue

            currency_code = cells[0].strip()
            currency_name = cells[1].strip() if len(cells) > 1 else None
            if not currency_code:
                continue

            row_dict = {
                "buying": cells[buy_idx],
                "selling": cells[sell_idx]
            }

            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=currency_code,
                currency_name=currency_name or None,
                effective_date=None,
                effective_date_basis="collection_date_fallback"
            )

            for rec in detected_records:
                if rec.category == 'UNKNOWN':
                    rec.category = normalize_category(category)

            records.extend(detected_records)

        return records

    def _parse_weighted_table(self, rows, category: str) -> list:
        if len(rows) < 3:
            return []

        header_text = rows[0].get_text(" ", strip=True)
        table_specific_date = _extract_date(header_text)

        effective_date = table_specific_date
        date_basis = "source_published" if effective_date else "collection_date_fallback"

        records = []
        for row in rows[2:]:
            cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
            if len(cells) < 4:
                continue

            currency_code = cells[0].strip()
            currency_name = cells[1].strip() if len(cells) > 1 else None
            if not currency_code:
                continue

            row_dict = {
                "buying": cells[2],
                "selling": cells[3],
                "header_text": header_text
            }

            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=currency_code,
                currency_name=currency_name or None,
                effective_date=effective_date,
                effective_date_basis=date_basis,
                mapping_notes=(
                    ["date_from_weighted_avg_header:source_published"]
                    if effective_date else
                    ["date_missing_from_weighted_avg_header:collection_date_fallback"]
                )
            )

            for rec in detected_records:
                if rec.category == 'UNKNOWN':
                    rec.category = normalize_category(category)

            records.extend(detected_records)

        return records

def _header_to_field_name(header: str) -> str:
    field = header.lower().strip()
    field = re.sub(r'\s+', '_', field)
    field = re.sub(r'[^\w_]', '', field)
    return field

def _extract_date(text: str) -> Optional[date]:
    m = _DATE_RE.search(text)
    if not m:
        return None
    date_str = m.group(1).strip()
    parts = re.sub(r'[\s,]+', ' ', date_str).split()
    if len(parts) < 3:
        return None
    month_name = parts[0].lower()
    month = _MONTH_MAP.get(month_name)
    if not month:
        return None
    try:
        day = int(parts[1])
        year = int(parts[2])
        return date(year, month, day)
    except (ValueError, IndexError):
        return None

def parse(raw_html: str) -> tuple:
    adapter = DashenAdapter()
    result = adapter.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    return DashenAdapter().schema_fingerprint(raw_html)
