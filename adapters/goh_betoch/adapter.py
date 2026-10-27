import re
from datetime import datetime, date
from typing import Optional
from bs4 import BeautifulSoup

from adapters.base import HTMLTableAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin

ADAPTER_KEY = "goh_betoch_html"
SOURCE_URL = "https://www.gohbetbank.com/todays-exchange-rate/"

class GohBetochAdapter(FieldStructureMixin, HTMLTableAdapter):

    FIELD_CONFIG = {}

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def _process_tables(self, soup: BeautifulSoup, tables: list, **kwargs) -> ParseResult:
        result = ParseResult()

        effective_date = _parse_date(soup)
        date_basis = "source_published" if effective_date else "collection_date_fallback"

        try:
            records = self._parse_table(tables[0], effective_date, date_basis, **kwargs)
            result.records.extend(records)
        except Exception as exc:
            result.add_error(f"table_0:{exc}")

        return result

    def _parse_table(self, table, effective_date, date_basis, **kwargs) -> list:
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 4:
                continue
            currency_code = cells[0].strip()
            currency_name = cells[1].strip() if len(cells) > 1 else None
            if not currency_code:
                continue

            row_dict = {
                "transactional_buying": cells[2],
                "transactional_selling": cells[3],
            }
            if len(cells) > 5:
                row_dict["weighted_average_buying"] = cells[4]
                row_dict["weighted_average_selling"] = cells[5]

            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=currency_code,
                currency_name=currency_name,
                effective_date=effective_date,
                effective_date_basis=date_basis
            )

            if kwargs.get("category") and kwargs.get("category") != "UNKNOWN":
                cash_dict = {
                    "cash_buying": cells[2],
                    "cash_selling": cells[3],
                }
                cash_records = self.detect_and_emit(
                    data=cash_dict,
                    currency=currency_code,
                    currency_name=currency_name,
                    effective_date=effective_date,
                    effective_date_basis=date_basis
                )
                detected_records.extend(cash_records)

            records.extend(detected_records)
        return records

def _parse_date(soup) -> Optional[date]:
    text = soup.get_text(" ")
    m = re.search(r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s*\d{4}', text)
    if m:
        raw = re.sub(r'\s+', ' ', m.group(0).strip())
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                pass
    return None

_adapter_instance = GohBetochAdapter()

def parse(raw_html: str, category: str = "UNKNOWN") -> tuple:
    result = _adapter_instance.parse(raw_html, category=category)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    return _adapter_instance.schema_fingerprint(raw_html)
