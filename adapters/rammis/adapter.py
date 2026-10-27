import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Optional

from adapters.base import JSONAdapter, ParseResult
from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate
from field_detection.mixin import FieldStructureMixin

ADAPTER_KEY = "rammis_api"
SOURCE_URL = "https://rammisbank.et/api/v1/exchange-rates/latest?base_currency=ETB"

class RammisAdapter(JSONAdapter, FieldStructureMixin):

    FIELD_CONFIG = {
        "default_category": "transactional"
    }

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def _process_data(self, data, **options) -> ParseResult:
        if not isinstance(data, dict):
            raise ValueError(
                f"Rammis: expected JSON object at top level, got {type(data).__name__}"
            )

        rates = data.get("rates")
        if rates is None:
            raise ValueError("Rammis: missing 'rates' key — schema changed")
        if not isinstance(rates, list):
            raise ValueError(f"Rammis: 'rates' must be an array, got {type(rates).__name__}")

        records = []
        for row in rates:
            parsed_records = self._parse_row(row)
            records.extend(parsed_records)

        result = ParseResult()
        result.records = records
        return result

    def _parse_row(self, row: dict) -> list:
        if not isinstance(row, dict):
            return []

        currency = str(row.get("currency", "")).strip()
        if not currency:
            return []

        row_id = row.get("id")
        effective_date = self._parse_iso_date(row.get("effective_date", ""))
        date_basis = "source_published" if effective_date else "collection_date_fallback"

        records = self.detect_and_emit(
            row,
            currency=currency,
            effective_date=effective_date,
            effective_date_basis=date_basis,
            source_record_id=str(row_id) if row_id is not None else None,
            mapping_notes=["id_stability:TO_VERIFY"]
        )

        return records

    def schema_fingerprint(self, raw_content: str) -> str:
        try:
            data = json.loads(raw_content)
            if isinstance(data, dict):
                env_keys = sorted(k for k in data.keys() if k != "rates")
                rate_keys = []
                rates = data.get("rates", [])
                if isinstance(rates, list) and rates and isinstance(rates[0], dict):
                    rate_keys = sorted(rates[0].keys())
                payload = json.dumps({"env": env_keys, "rate": rate_keys}, separators=(",", ":"))
                return hashlib.sha256(payload.encode()).hexdigest()
        except Exception:
            pass
        return hashlib.sha256(b"rammis:empty_or_unparseable").hexdigest()

def parse(raw_json: str, category: str = "UNKNOWN") -> list:
    adapter = RammisAdapter()
    result = adapter.parse(raw_json)

    if result.errors:
        raise ValueError(result.errors[0])

    return result.records

def _safe_rate(raw) -> Optional[Decimal]:
    try:
        return normalize_rate(raw)
    except ValueError:
        return None

def _parse_date(date_str: str) -> Optional[date]:
    try:
        return date.fromisoformat(str(date_str).strip())
    except (ValueError, AttributeError):
        return None

def schema_fingerprint(raw_json: str) -> str:
    return RammisAdapter().schema_fingerprint(raw_json)
