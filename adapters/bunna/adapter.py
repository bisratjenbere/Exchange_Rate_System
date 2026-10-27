from bs4 import BeautifulSoup

from adapters.base import HTMLTableAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin

ADAPTER_KEY = "bunna_html"
SOURCE_URL = "https://bunnabanksc.com/foreign-exchange/"

class BunnaAdapter(FieldStructureMixin, HTMLTableAdapter):

    FIELD_CONFIG = {}

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def _process_tables(self, soup: BeautifulSoup, tables: list, **options) -> ParseResult:
        result = ParseResult()

        if not tables:
            result.add_error("table_0:missing")
            return result

        try:
            records = self._parse_wide_table(tables[0])
            result.records.extend(records)
        except Exception as exc:
            result.add_error(f"table_0:{exc}")

        return result

    def _parse_wide_table(self, table) -> list:
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 6:
                continue
            currency_name = cells[0].strip()
            currency_code = cells[1].strip()
            if not currency_code:
                continue

            row_dict = {
                "cash_buying": cells[2],
                "cash_selling": cells[3],
                "transactional_buying": cells[4],
                "transactional_selling": cells[5],
            }
            if len(cells) > 7:
                row_dict["weighted_average_buying"] = cells[6]
                row_dict["weighted_average_selling"] = cells[7]

            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=currency_code,
                currency_name=currency_name or None,
                effective_date=None,
                effective_date_basis="collection_date_fallback",
                mapping_notes=["date_ambiguous:no_source_published_date", "avg_cols_may_be_js_rendered:TO_VERIFY"]
            )

            records.extend(detected_records)
        return records

def parse(raw_html: str) -> tuple:
    adapter = BunnaAdapter()
    result = adapter.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    return BunnaAdapter().schema_fingerprint(raw_html)
