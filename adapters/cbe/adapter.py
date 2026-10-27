import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Optional

from adapters.base import JSONAdapter, ParseResult
from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate
from field_detection.mixin import FieldStructureMixin

ADAPTER_KEY = "cbe_api"
SOURCE_URL = "https://combanketh.et/cbeapi/daily-exchange-rates/"

class CBEAdapter(JSONAdapter, FieldStructureMixin):

    FIELD_CONFIG = {}

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def _process_data(self, data, **options) -> ParseResult:
        if not isinstance(data, list):
            raise ValueError(
                f"CBE: expected JSON array at top level, got {type(data).__name__}"
            )

        records = []
        for pub in data:
            records.extend(_parse_publication(pub))

        result = ParseResult()
        result.records = records
        return result

    def schema_fingerprint(self, raw_content: str) -> str:
        try:
            data = json.loads(raw_content)
            if isinstance(data, list) and data:
                pub = data[0]
                pub_keys = sorted(k for k in pub.keys() if k != "ExchangeRate")
                er_keys = []
                if isinstance(pub.get("ExchangeRate"), list) and pub["ExchangeRate"]:
                    er_keys = sorted(pub["ExchangeRate"][0].keys())
                payload = json.dumps({"pub": pub_keys, "er": er_keys}, separators=(",", ":"))
                return hashlib.sha256(payload.encode()).hexdigest()
        except Exception:
            pass
        return hashlib.sha256(b"cbe:empty_or_unparseable").hexdigest()

def parse(raw_json: str) -> list:
    adapter = CBEAdapter()
    result = adapter.parse(raw_json)

    if result.errors:
        raise ValueError(result.errors[0])

    return result.records

def _parse_publication(pub: dict) -> list:
    if not isinstance(pub, dict):
        return []

    pub_id = pub.get("id") or pub.get("_id")
    date_str = pub.get("Date", "")
    effective_date = _parse_date(date_str)

    er_items = pub.get("ExchangeRate")
    if not isinstance(er_items, list):
        raise ValueError(f"CBE: publication {pub_id!r} missing ExchangeRate array")

    records = []
    for item in er_items:
        records.extend(_parse_er_item(item, pub_id, effective_date))
    return records

def _parse_er_item(item: dict, pub_id: Optional[str], effective_date: Optional[date]) -> list:
    if not isinstance(item, dict):
        return []

    item_id = item.get("id") or item.get("_id")
    currency_obj = item.get("currency", {})
    if not isinstance(currency_obj, dict):
        return []

    currency_code = str(currency_obj.get("CurrencyCode", "")).strip()
    currency_name = str(currency_obj.get("CurrencyName", "")).strip() or None

    if not currency_code:
        return []

    adapter = CBEAdapter()
    records = adapter.detect_and_emit(
        item,
        currency=currency_code,
        currency_name=currency_name,
        effective_date=effective_date,
        effective_date_basis="source_published",
        source_record_id=item_id,
        source_publication_id=pub_id,
        mapping_notes=["zero_equals_not_offered:TO_VERIFY"]
    )

    return records

def _safe_rate(raw) -> Optional[Decimal]:
    try:
        return normalize_rate(raw)
    except ValueError:
        return None

def _parse_date(date_str: str) -> Optional[date]:
    try:
        return date.fromisoformat(date_str.strip())
    except (ValueError, AttributeError):
        return None

def schema_fingerprint(raw_json: str) -> str:
    return CBEAdapter().schema_fingerprint(raw_json)
