import json
from datetime import datetime
from bs4 import BeautifulSoup

from adapters.base import JSONAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin

ADAPTER_KEY = "bunna_html"
SOURCE_URL = "https://mb.bunnabanksc.com/api/v1/user/public/forex"

class BunnaAdapter(FieldStructureMixin, JSONAdapter):

    FIELD_CONFIG = {}

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def parse(self, raw_content: str, **options) -> ParseResult:
        if raw_content and raw_content.strip().startswith("<"):
            soup = BeautifulSoup(raw_content, "html.parser")
            tables = soup.find_all("table")
            result = ParseResult()
            if not tables:
                result.add_error("No tables found in HTML")
                return result
            try:
                records = self._parse_wide_table(tables[0])
                result.records.extend(records)
            except Exception as exc:
                result.add_error(f"table_0:{exc}")
            return result
        return super().parse(raw_content, **options)

    def _process_data(self, data, **options) -> ParseResult:
        result = ParseResult()
        items = data.get("content", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        if not items:
            result.add_error("empty_content")
            return result

        for item in items:
            code = item.get("currencyCode", "").strip().upper()
            if not code:
                continue
            name = item.get("currency")
            eff_date = None
            val_date_str = item.get("valueDate")
            if val_date_str:
                try:
                    eff_date = datetime.fromisoformat(val_date_str).date()
                except Exception:
                    eff_date = None

            basis = "source_published" if eff_date else "collection_date_fallback"

            row_dict = {
                "cash_buying": str(item.get("buying")) if item.get("buying") is not None else None,
                "cash_selling": str(item.get("selling")) if item.get("selling") is not None else None,
                "transactional_buying": str(item.get("transactionBuying")) if item.get("transactionBuying") is not None else None,
                "transactional_selling": str(item.get("transactionSelling")) if item.get("transactionSelling") is not None else None,
            }

            detected = self.detect_and_emit(
                data=row_dict,
                currency=code,
                currency_name=name,
                effective_date=eff_date,
                effective_date_basis=basis,
                mapping_notes=["source=bunna_mb_api"],
            )
            result.records.extend(detected)

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
                mapping_notes=["date_ambiguous:no_source_published_date"],
            )

            records.extend(detected_records)
        return records

def parse(raw_html: str) -> tuple:
    adapter = BunnaAdapter()
    result = adapter.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    return BunnaAdapter().schema_fingerprint(raw_html)
