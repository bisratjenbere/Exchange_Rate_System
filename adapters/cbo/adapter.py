import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from adapters.base import HTMLTableAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin
from pipeline.category_normalizer import normalize_category

ADAPTER_KEY = "cbo_html"
SOURCE_URL = "https://coopbankoromia.com.et/daily-exchange-rates/"

_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_DATE_RE = re.compile(
    rf"({_MONTHS})\s+(\d{{1,2}}),?\s+(\d{{4}})", re.IGNORECASE
)
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

class CBOAdapter(FieldStructureMixin, HTMLTableAdapter):

    FIELD_CONFIG = {}

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def _process_tables(self, soup: BeautifulSoup, tables: list, **options) -> ParseResult:
        result = ParseResult()

        if len(tables) < 1:
            result.add_error("table_0_cash_txn:missing")
            result.add_error("table_1_weighted_avg:missing")
            return result

        effective_date = None
        try:
            effective_date = _extract_date_from_table(tables[0])
        except Exception as exc:
            result.add_error(f"date_extraction:{exc}")

        date_basis = "source_published" if effective_date else "collection_date_fallback"

        try:
            records = self._parse_cash_txn_table(tables[0], effective_date, date_basis)
            result.records.extend(records)
        except Exception as exc:
            result.add_error(f"table_0_cash_txn:{exc}")

        if len(tables) < 2:
            result.add_error("table_1_weighted_avg:missing")
        else:
            try:
                records = self._parse_weighted_table(tables[1], effective_date, date_basis)
                result.records.extend(records)
            except Exception as exc:
                result.add_error(f"table_1_weighted_avg:{exc}")

        return result

    def _parse_cash_txn_table(self, table, effective_date: Optional[date], date_basis: str) -> list:
        rows = table.find_all("tr")
        data_rows = [r for r in rows if _is_data_row(r)]
        if not data_rows:
            return []

        records = []
        for row in data_rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 5:
                continue
            currency_code, currency_name = _parse_currency_cell(cells[0])
            if not currency_code:
                continue

            row_dict = {
                "cash_buying": cells[1],
                "cash_selling": cells[2],
                "transactional_buying": cells[3],
                "transactional_selling": cells[4],
            }

            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=currency_code,
                currency_name=currency_name,
                effective_date=effective_date,
                effective_date_basis=date_basis,
                mapping_notes=["dash_equals_no_trade:TO_VERIFY"]
            )

            records.extend(detected_records)
        return records

    def _parse_weighted_table(self, table, effective_date: Optional[date], date_basis: str) -> list:
        rows = table.find_all("tr")
        data_rows = [r for r in rows if _is_data_row(r)]
        if not data_rows:
            return []

        table_category = self.extract_table_category(table)

        records = []
        for row in data_rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 3:
                continue
            currency_code, currency_name = _parse_currency_cell(cells[0])
            if not currency_code:
                continue

            row_dict = {
                "buying": cells[1],
                "selling": cells[2],
            }

            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=currency_code,
                currency_name=currency_name,
                effective_date=effective_date,
                effective_date_basis=date_basis,
                mapping_notes=["dash_equals_no_trade:TO_VERIFY"]
            )

            for rec in detected_records:
                if rec.category == 'UNKNOWN':
                    rec.category = table_category

            records.extend(detected_records)
        return records

def _extract_date_from_table(table) -> Optional[date]:
    rows = table.find_all("tr")
    if not rows:
        return None
    header_text = rows[0].get_text(" ", strip=True)
    return _parse_date_text(header_text)

def _is_data_row(row) -> bool:
    return bool(row.find("td"))

def _parse_currency_cell(text: str) -> tuple:
    text = text.strip()
    if " - " in text:
        parts = text.split(" - ", 1)
        return parts[0].strip(), parts[1].strip()
    if text:
        return text, None
    return "", None

def _parse_date_text(text: str) -> Optional[date]:
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

def parse(raw_html: str) -> tuple:
    adapter = CBOAdapter()
    result = adapter.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    return CBOAdapter().schema_fingerprint(raw_html)
