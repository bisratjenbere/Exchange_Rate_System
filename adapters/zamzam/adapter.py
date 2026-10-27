import re
from datetime import date
from typing import Optional
from bs4 import BeautifulSoup

from adapters.base import HTMLTableAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin
from pipeline.category_normalizer import normalize_category

ADAPTER_KEY = "zamzam_html"
SOURCE_URL = "https://zamzambank.com/exchange-rates/"

_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_DATE_RE = re.compile(rf"({_MONTHS})\s+(\d{{1,2}}),?\s+(\d{{4}})", re.IGNORECASE)
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

class ZamzamAdapter(FieldStructureMixin, HTMLTableAdapter):

    FIELD_CONFIG = {}

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def _process_tables(self, soup: BeautifulSoup, tables: list, **kwargs) -> ParseResult:
        result = ParseResult()

        text = soup.get_text(" ", strip=True)
        effective_date = _extract_date(text)
        date_basis = "source_published" if effective_date else "collection_date_fallback"

        if len(tables) < 1:
            result.add_error("table_0:missing")
            result.add_error("table_1:missing")
            return result

        try:
            records = self._parse_cash_txn(tables[0], effective_date, date_basis)
            result.records.extend(records)
        except Exception as exc:
            result.add_error(f"table_0_cash_txn:{exc}")

        if len(tables) < 2:
            result.add_error("table_1_weighted:missing")
        else:
            try:
                records = self._parse_weighted(tables[1], effective_date, date_basis, **kwargs)
                result.records.extend(records)
            except Exception as exc:
                result.add_error(f"table_1_weighted:{exc}")

        return result

    def _parse_cash_txn(self, table, effective_date, date_basis: str) -> list:
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 5:
                continue
            code = _parse_code(cells[0])
            if not code:
                continue

            row_dict = {
                "cash_buying": cells[1],
                "cash_selling": cells[2],
                "transactional_buying": cells[3],
                "transactional_selling": cells[4],
            }

            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=code,
                effective_date=effective_date,
                effective_date_basis=date_basis
            )

            records.extend(detected_records)
        return records

    def _parse_weighted(self, table, effective_date, date_basis: str, **kwargs) -> list:
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        table_category = self.extract_table_category(table)
        if table_category == "UNKNOWN":
            table_category = normalize_category(kwargs.get("category", "weighted_average"))

        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 3:
                continue
            code = _parse_code(cells[0])
            if not code:
                continue

            row_dict = {
                "buying": cells[1],
                "selling": cells[2],
            }

            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=code,
                effective_date=effective_date,
                effective_date_basis=date_basis
            )

            for rec in detected_records:
                if rec.category == 'UNKNOWN':
                    rec.category = table_category

            records.extend(detected_records)
        return records

def _parse_code(text: str) -> str:
    text = text.strip()
    for sep in [" –", " -", " —"]:
        if sep in text:
            return text.split(sep)[0].strip()
    return text.split()[0] if text else ""

def _extract_date(text: str) -> Optional[date]:
    for m in _DATE_RE.finditer(text):
        month = _MONTH_MAP.get(m.group(1).lower())
        if not month:
            continue
        try:
            d = date(int(m.group(3)), month, int(m.group(2)))
            if d.year >= 2020:
                return d
        except ValueError:
            continue
    return None

_adapter_instance = ZamzamAdapter()

def parse(raw_html: str) -> tuple:
    result = _adapter_instance.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    return _adapter_instance.schema_fingerprint(raw_html)
