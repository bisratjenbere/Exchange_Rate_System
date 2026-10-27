import copy
from typing import Optional
from bs4 import BeautifulSoup

from adapters.base import HTMLTableAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin

ADAPTER_KEY = "siinqee_html"
SOURCE_URL = "https://siinqeebank.com/"

class SiinqeeAdapter(FieldStructureMixin, HTMLTableAdapter):

    FIELD_CONFIG = {}

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def _process_tables(self, soup: BeautifulSoup, tables: list, **kwargs) -> ParseResult:
        result = ParseResult()
        table_cat = self.extract_table_category(tables[0], soup)
        category = table_cat if table_cat != "UNKNOWN" else kwargs.get("category")

        try:
            records = _parse_table(self, tables[0], category)
            result.records.extend(records)
        except Exception as exc:
            result.add_error(f"table_0:{exc}")

        return result

def _parse_table(adapter, table, category: Optional[str] = None) -> list:
    rows = [r for r in table.find_all("tr") if r.find("td")]
    records = []
    for row in rows:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        currency_code = cells[0].strip()
        if not currency_code:
            continue

        row_dict = {"buying": cells[1], "selling": cells[2]}
        detected_records = adapter.detect_and_emit(
            data=row_dict,
            currency=currency_code,
            effective_date=None,
            effective_date_basis="collection_date_fallback",
            mapping_notes=["category_unknown:single_pair_no_label"]
        )

        cats_to_assign = ["transactional"] if category is None else ["cash", "transactional"]
        for cat_name in cats_to_assign:
            for rec in detected_records:
                r_copy = copy.copy(rec)
                r_copy.category = cat_name
                records.append(r_copy)
    return records

_adapter_instance = SiinqeeAdapter()

def parse(raw_html: str, category: Optional[str] = None) -> tuple:
    result = _adapter_instance.parse(raw_html, category=category)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    return _adapter_instance.schema_fingerprint(raw_html)
