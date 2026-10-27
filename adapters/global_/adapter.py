from decimal import Decimal
from typing import Optional
from bs4 import BeautifulSoup

from domain.records import AdapterRecord
from field_detection.mixin import FieldStructureMixin
from pipeline.category_normalizer import normalize_category
from pipeline.normalize import normalize_rate
from adapters.base import HTMLTableAdapter, ParseResult

ADAPTER_KEY = "global_html"
SOURCE_URL = "https://www.globalbankethiopia.com/remittance-forex/"

class GlobalAdapter(FieldStructureMixin, HTMLTableAdapter):

    FIELD_CONFIG = {}

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def _process_tables(self, soup: BeautifulSoup, tables: list, **kwargs) -> ParseResult:
        result = ParseResult()
        category = kwargs.get("category", "transactional")

        tables_to_process = list(tables)[:2] if len(tables) >= 2 else list(tables)

        for i, table in enumerate(tables_to_process):
            try:
                table._adapter_instance = self
                table_cat = self.extract_table_category(table, soup)
                cat = table_cat if table_cat != "UNKNOWN" else category
                records = _parse_table(table, table_index=i, category=cat)
                result.records.extend(records)
            except Exception as exc:
                result.add_error(f"table_{i}:{exc}")

        return result

def _parse_table(table, table_index: int, category: str = "transactional") -> list:
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

        notes = [f"category_unknown:table_{table_index}_unverified"]
        detected_records = table._adapter_instance.detect_and_emit(
            data=row_dict,
            currency=currency_code,
            effective_date=None,
            effective_date_basis="collection_date_fallback",
            mapping_notes=notes
        )

        for rec in detected_records:
            if rec.category == 'UNKNOWN':
                rec.category = normalize_category(category)
            rec.raw_excerpt = {"currency": currency_code, "buying": cells[1],
                              "selling": cells[2], "table": table_index}

            if rec.buying_rate is not None and rec.selling_rate is not None and rec.buying_rate > rec.selling_rate:
                if "review_signal:buying_greater_than_selling" not in rec.mapping_notes:
                    rec.mapping_notes.append("review_signal:buying_greater_than_selling")

        records.extend(detected_records)
    return records

def _safe_rate(raw) -> Optional[Decimal]:
    try:
        return normalize_rate(raw)
    except ValueError:
        return None

_adapter_instance = GlobalAdapter()

def parse(raw_html: str, category: str = "transactional") -> tuple:
    result = _adapter_instance.parse(raw_html, category=category)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    return _adapter_instance.schema_fingerprint(raw_html)
