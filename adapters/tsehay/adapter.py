import re
from datetime import datetime, date
from typing import Optional
from bs4 import BeautifulSoup

from adapters.base import HTMLTableAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin
from pipeline.category_normalizer import normalize_category

ADAPTER_KEY = "tsehay_html"
SOURCE_URL = "https://tsehaybank.com.et/exchange-rate/"

class TsehayAdapter(FieldStructureMixin, HTMLTableAdapter):

    FIELD_CONFIG = {}

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def _process_tables(self, soup: BeautifulSoup, tables: list, **kwargs) -> ParseResult:
        result = ParseResult()

        effective_date = _parse_date(soup)
        date_basis = "source_published" if effective_date else "collection_date_fallback"

        if len(tables) < 1:
            result.add_error("table_0_cash_txn:missing")
            result.add_error("table_1_weighted:missing")
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

    def _parse_cash_txn(self, table, effective_date, date_basis) -> list:
        rows = table.find_all("tr")
        data_rows = [r for r in rows if r.find("td")]
        records = []
        for row in data_rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 5:
                continue
            currency_code = cells[0].strip()
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
                effective_date=effective_date,
                effective_date_basis=date_basis
            )

            records.extend(detected_records)
        return records

    def _parse_weighted(self, table, effective_date, date_basis, **kwargs) -> list:
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        table_category = self.extract_table_category(table)
        if table_category == "UNKNOWN":
            table_category = normalize_category(kwargs.get("category", "weighted_average"))

        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 4:
                continue
            currency_name = cells[0].strip()
            currency_code = cells[1].strip()
            if not currency_code:
                continue

            row_dict = {
                "buying": cells[2],
                "selling": cells[3],
            }

            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=currency_code,
                currency_name=currency_name or None,
                effective_date=effective_date,
                effective_date_basis=date_basis,
                mapping_notes=[] if effective_date else ["date_ambiguous:no_source_published_date"]
            )

            for rec in detected_records:
                if rec.category == 'UNKNOWN':
                    rec.category = table_category

            records.extend(detected_records)
        return records

def _parse_date(soup) -> Optional[date]:
    text = soup.get_text(" ")
    m = re.search(r'Daily Exchange Rate[:\s]+([A-Za-z]+ \d{1,2},?\s*\d{4})', text)
    if m:
        for fmt in ("%B %d, %Y", "%B %d %Y", "%b %d, %Y"):
            try:
                return datetime.strptime(m.group(1).strip(), fmt).date()
            except ValueError:
                continue
    return None

_adapter_instance = TsehayAdapter()

def parse(raw_html: str) -> tuple:
    result = _adapter_instance.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    return _adapter_instance.schema_fingerprint(raw_html)
