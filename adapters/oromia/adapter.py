import re
from datetime import date, datetime
from typing import Optional
from bs4 import BeautifulSoup

from domain.records import AdapterRecord
from pipeline.category_normalizer import normalize_category
from adapters.base import HTMLTableAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin

ADAPTER_KEY = "oromia_html"
SOURCE_URL = "https://www.oromiabanksc.com/"
FETCH_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

class OromiaAdapter(FieldStructureMixin, HTMLTableAdapter):

    FIELD_CONFIG = {}

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def _process_tables(self, soup: BeautifulSoup, tables: list, **kwargs) -> ParseResult:
        result = ParseResult()

        table = soup.find("table", {"id": "footable_12396"})
        if table is None:
            table = soup.find("table", id=re.compile(r"footable_"))
        if table is None:
            result.add_error("table_not_found")
            return result

        rows = table.find_all("tr")
        if len(rows) < 2:
            result.add_error("no_data_rows")
            return result

        parsed = []
        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) < 4:
                continue
            try:
                row_date = _parse_date(cells[0])
                if row_date is None:
                    continue
                currency = cells[1].strip()
                buying_text = cells[2].strip()
                selling_text = cells[3].strip()
                if not currency or buying_text == "No Trade" or selling_text == "No Trade":
                    continue

                row_dict = {
                    "buying_rate": buying_text,
                    "selling_rate": selling_text,
                    "date": str(row_date),
                    "currency": currency
                }
                parsed.append((row_date, currency, row_dict))

            except Exception as exc:
                result.add_error(f"row:{cells}:{exc}")

        if not parsed:
            result.add_error("no_valid_rows")
            return result

        table_cat = self.extract_table_category(table, soup)
        if table_cat == "UNKNOWN":
            table_cat = normalize_category(kwargs.get("category", "transactional"))

        max_date = max(r[0] for r in parsed)
        for row_date, currency, row_dict in parsed:
            if row_date != max_date:
                continue

            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=currency,
                effective_date=max_date,
                effective_date_basis="source_published",
                source_record_id=f"{max_date}:{currency}",
                source_publication_id=str(max_date)
            )

            for rec in detected_records:
                if rec.category == 'UNKNOWN':
                    rec.category = table_cat

            result.records.extend(detected_records)

        return result

def _parse_date(raw: str) -> Optional[date]:
    if not raw:
        return None
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None

_adapter_instance = OromiaAdapter()

def parse(raw_html: str) -> tuple:
    result = _adapter_instance.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    return _adapter_instance.schema_fingerprint(raw_html)
