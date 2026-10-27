import hashlib
import json
from datetime import date
from typing import Optional

from adapters.base import JSONAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin

ADAPTER_KEY = "zemen_ajax"
SOURCE_URL = "https://zemenbank.com/wp-admin/admin-ajax.php"
COLLECTION_METHOD = "ajax_endpoint"
FETCH_POST_DATA = {"action": "get_exchange_rates"}
FETCH_HEADERS = {"Referer": "https://zemenbank.com/exchange-rates/"}

class ZemenAdapter(FieldStructureMixin, JSONAdapter):

    FIELD_CONFIG = {}

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def _process_data(self, data, **kwargs) -> ParseResult:
        result = ParseResult()

        if data.get("status") != "success":
            result.add_error(f"status:{data.get('status')}")
            return result

        effective_date = self._parse_iso_date(data.get("date", ""))
        avg_date = self._parse_iso_date(data.get("avg_date", ""))
        date_basis = "source_published" if effective_date else "collection_date_fallback"
        avg_basis = "source_published" if avg_date else "collection_date_fallback"

        rates = data.get("rates", {})

        day_category = normalize_category(kwargs.get("category", "transactional"))
        avg_category = normalize_category("average")

        for row in rates.get("day", []):
            try:
                code = str(row.get("currency_code", "")).strip()
                if not code:
                    continue

                detected_records = self.detect_and_emit(
                    data=row,
                    currency=code,
                    effective_date=effective_date,
                    effective_date_basis=date_basis,
                    source_record_id=str(row.get("exchange_id")) if row.get("exchange_id") else None
                )

                for rec in detected_records:
                    if rec.category == 'UNKNOWN':
                        rec.category = day_category
                    if isinstance(rec.raw_excerpt, dict):
                        rec.raw_excerpt["post_date"] = row.get("post_date")

                result.records.extend(detected_records)

            except Exception as exc:
                result.add_error(f"day_row:{row.get('currency_code')}:{exc}")

        for row in rates.get("average", []):
            try:
                code = str(row.get("currency_code", "")).strip()
                if not code:
                    continue

                detected_records = self.detect_and_emit(
                    data=row,
                    currency=code,
                    effective_date=avg_date,
                    effective_date_basis=avg_basis,
                    source_record_id=str(row.get("exchange_id")) if row.get("exchange_id") else None
                )

                for rec in detected_records:
                    if rec.category == 'UNKNOWN':
                        rec.category = avg_category
                    if isinstance(rec.raw_excerpt, dict):
                        rec.raw_excerpt["post_date"] = row.get("post_date")

                result.records.extend(detected_records)

            except Exception as exc:
                result.add_error(f"avg_row:{row.get('currency_code')}:{exc}")

        return result

    def schema_fingerprint(self, raw_content: str) -> str:
        try:
            data = json.loads(raw_content)
            keys = sorted(data.get("rates", {}).keys())
            row_keys = sorted(data["rates"]["day"][0].keys()) if data.get("rates", {}).get("day") else []
            return hashlib.sha256(str({"rate_keys": keys, "row_keys": row_keys}).encode()).hexdigest()
        except Exception:
            return hashlib.sha256(b"zemen:unparseable").hexdigest()

_adapter = ZemenAdapter()

def parse(raw_json: str) -> tuple:
    result = _adapter.parse(raw_json)
    return result.records, result.errors

def schema_fingerprint(raw_json: str) -> str:
    return _adapter.schema_fingerprint(raw_json)
