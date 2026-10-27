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

ADAPTER_KEY = "gadaa_api"
SOURCE_URL = "https://gadaabank.com.et/api/v1/exchange-rates"

class GadaaAdapter(FieldStructureMixin, JSONAdapter):

    FIELD_CONFIG = {}

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def _process_data(self, data, **options) -> ParseResult:
        result = ParseResult()

        rows = data.get("data", [])
        if not isinstance(rows, list):
            result.add_error("data_not_array")
            return result

        for row in rows:
            try:
                code = str(row.get("currency", "")).strip()
                if not code or not row.get("is_active", True):
                    continue

                effective_date = _parse_date(row.get("updated_at"))
                if effective_date and (date.today() - effective_date).days > 3:
                    result.add_warning(f"{code}:{row.get('market_type')}: stale date {effective_date}, skipped")
                    continue
                date_basis = "source_inferred" if effective_date else "collection_date_fallback"

                detected_records = self.detect_and_emit(
                    data=row,
                    currency=code,
                    source_record_id=str(row.get("id")) if row.get("id") else None,
                    effective_date=effective_date,
                    effective_date_basis=date_basis
                )

                market_type = str(row.get("market_type", "")).lower()
                explicit_category = normalize_category(market_type) if market_type else normalize_category(options.get("category", "transactional"))

                for rec in detected_records:
                    if rec.category == 'UNKNOWN':
                        rec.category = explicit_category

                    if isinstance(rec.raw_excerpt, dict):
                        rec.raw_excerpt["market_type"] = row.get("market_type")
                        rec.raw_excerpt["updated_at"] = row.get("updated_at")

                result.records.extend(detected_records)

            except Exception as exc:
                result.add_error(f"row:{row.get('currency')}:{exc}")

        return result

    def schema_fingerprint(self, raw_content: str) -> str:
        try:
            data = json.loads(raw_content)
            rows = data.get("data", [])
            keys = sorted(rows[0].keys()) if rows else []
            return hashlib.sha256(str({"keys": keys}).encode()).hexdigest()
        except Exception:
            return hashlib.sha256(b"gadaa:unparseable").hexdigest()

def parse(raw_json: str) -> tuple:
    adapter = GadaaAdapter()
    result = adapter.parse(raw_json)
    return result.records, result.errors

def _parse_date(raw) -> Optional[date]:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw).strip()[:10])
    except ValueError:
        return None

def schema_fingerprint(raw_json: str) -> str:
    return GadaaAdapter().schema_fingerprint(raw_json)
