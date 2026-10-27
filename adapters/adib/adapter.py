import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Optional

from adapters.base import JSONAdapter, ParseResult
from domain.records import AdapterRecord
from field_detection.mixin import FieldStructureMixin
from pipeline.category_normalizer import normalize_category
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "adib_api"
SOURCE_URL = "https://api.addisbanksc.com/api/exchange-rates"
ETB_ROW_ID = 1

class ADIBAdapter(FieldStructureMixin, JSONAdapter):

    FIELD_CONFIG = {}

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def _process_data(self, data, **options) -> ParseResult:
        if not isinstance(data, list):
            raise ValueError(
                f"ADIB: expected JSON array at top level, got {type(data).__name__}"
            )

        result = ParseResult()

        for row in data:
            if not isinstance(row, dict) or row.get("id") == ETB_ROW_ID:
                continue

            currency = str(row.get("currency", "")).strip()
            if not currency:
                continue

            effective_date = _parse_updated_at(row.get("updatedAt"))
            date_basis = "source_inferred" if effective_date else "collection_date_fallback"

            detected_records = self.detect_and_emit(
                data=row,
                currency=currency,
                source_record_id=str(row.get("id")) if row.get("id") is not None else None,
                effective_date=effective_date,
                effective_date_basis=date_basis,
                mapping_notes=[
                    "plain_buying_selling_skipped:category_unconfirmed",
                    "updatedAt_as_source_inferred:ADR-013"
                ]
            )

            confirmed_records = [r for r in detected_records if r.category != 'UNKNOWN']
            result.records.extend(confirmed_records)

            skipped = len(detected_records) - len(confirmed_records)
            if skipped > 0:
                result.add_warning(f"{currency}: skipped {skipped} UNKNOWN category record(s)")

        return result

    def schema_fingerprint(self, raw_content: str) -> str:
        try:
            data = json.loads(raw_content)
            if isinstance(data, list):
                for row in data:
                    if isinstance(row, dict) and row.get("id") != ETB_ROW_ID:
                        keys = sorted(row.keys())
                        payload = json.dumps(keys, separators=(",", ":"))
                        return hashlib.sha256(payload.encode()).hexdigest()
        except Exception:
            pass
        return hashlib.sha256(b"adib:empty_or_unparseable").hexdigest()

def parse(raw_json: str) -> list:
    adapter = ADIBAdapter()
    result = adapter.parse(raw_json)

    if result.errors:
        raise ValueError(result.errors[0])

    return result.records

def _parse_updated_at(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw).strip()[:10])
    except (ValueError, AttributeError):
        return None

def _safe_rate(raw) -> Optional[Decimal]:
    try:
        return normalize_rate(raw)
    except ValueError:
        return None

def _rate_text(buying, selling) -> str:
    return f"{buying}/{selling}"

def schema_fingerprint(raw_json: str) -> str:
    return ADIBAdapter().schema_fingerprint(raw_json)
