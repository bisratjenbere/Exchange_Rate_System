import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from adapters.base import HTMLTableAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin
from pipeline.category_normalizer import normalize_category

ADAPTER_KEY = "nib_html"
SOURCE_URL = "https://www.nibbanksc.com/exchange-rate/"

_MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
_DATE_RE = re.compile(rf"({_MONTHS})\w*\s+(\d{{1,2}}),?\s+(\d{{4}})", re.IGNORECASE)
_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

class NIBAdapter(FieldStructureMixin, HTMLTableAdapter):

    FIELD_CONFIG = {}

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
            result.add_error("table_0_date:missing")
            result.add_error("table_1_cash_txn:missing")
            result.add_error("table_2_weighted:missing")
            return result

        effective_date = None
        try:
            effective_date = _extract_date(tables[0])
        except Exception as exc:
            result.add_error(f"date_extraction:{exc}")

        date_basis = "source_published" if effective_date else "collection_date_fallback"

        if len(tables) >= 2:
            try:
                records = self._parse_cash_txn(tables[1], effective_date, date_basis)
                result.records.extend(records)
            except Exception as exc:
                result.add_error(f"table_1_cash_txn:{exc}")
        else:
            result.add_error("table_1_cash_txn:missing")

        if len(tables) >= 3:
            try:
                records = self._parse_weighted(tables[2], effective_date, date_basis, **options)
                result.records.extend(records)
            except Exception as exc:
                result.add_error(f"table_2_weighted:{exc}")
        else:
            result.add_error("table_2_weighted:missing")

        return result

    def _parse_cash_txn(self, table, effective_date, date_basis) -> list:
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 5:
                continue
            currency = cells[0].strip()
            if not currency:
                continue

            row_dict = {
                "cash_buying": cells[1],
                "cash_selling": cells[2],
                "transactional_buying": cells[3],
                "transactional_selling": cells[4],
            }

            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=currency,
                effective_date=effective_date,
                effective_date_basis=date_basis,
                mapping_notes=["website_structure_updated:2026-10-21"]
            )

            records.extend(detected_records)
        return records

    def _parse_weighted(self, table, effective_date, date_basis, **options) -> list:
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        cat = self.extract_table_category(table)
        if cat == "UNKNOWN":
            cat = normalize_category(options.get("category", "weighted_average"))

        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 4:
                continue
            currency = cells[1].strip()
            if not currency:
                continue

            row_dict = {
                "buying": cells[2],
                "selling": cells[3],
            }

            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=currency,
                effective_date=effective_date,
                effective_date_basis=date_basis
            )

            for rec in detected_records:
                if rec.category == 'UNKNOWN':
                    rec.category = cat

            records.extend(detected_records)
        return records

def _extract_date(table) -> Optional[date]:
    text = table.get_text(" ", strip=True)
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

def parse(raw_html: str) -> tuple:
    adapter = NIBAdapter()
    result = adapter.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    return NIBAdapter().schema_fingerprint(raw_html)
