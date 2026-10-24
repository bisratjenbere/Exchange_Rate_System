"""
adapters/cbe/adapter.py — Commercial Bank of Ethiopia (Type A).

Parse rules (ADR-006 §6, mapping doc):
- Input: JSON array of publication records. Each record has Date + ExchangeRate array.
- One publication record per date. id (MongoDB ObjectID) = source_publication_key.
- Each ExchangeRate item has its own id = source_record_key.
- Emit 2 AdapterRecords per currency item: cash + transactional.
- cashBuying/cashSelling → category=cash.
- transactionalBuying/transactionalSelling → category=transactional.
- Zero → None (not offered). Confirmed pattern: 1205 zeros across 100 records.
- effective_date = Date field; effective_date_basis = source_published.
- identity_status = confirmed (stable ObjectID + source_published date).
- Never send _limit=1 (silently truncates). Use ?Date=YYYY-MM-DD for single-date fetch.

No network calls in parse(). fetch() is a thin wrapper kept separate.
"""
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
    """
    Commercial Bank of Ethiopia adapter using JSONAdapter base class.
    
    Parses JSON array of publication records with ExchangeRate arrays.
    Uses field-structure-based category detection to emit records.
    """
    
    # No explicit config needed - field names are self-describing
    FIELD_CONFIG = {}
    
    def get_source_url(self) -> str:
        """Return CBE API URL."""
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        """Return unique adapter identifier."""
        return ADAPTER_KEY
    
    def _process_data(self, data, **options) -> ParseResult:
        """
        Extract AdapterRecords from parsed JSON data.
        
        Args:
            data: Parsed JSON (should be list of publication records)
            **options: Additional options (unused)
        
        Returns:
            ParseResult with records and any errors
        
        Raises:
            ValueError: If data is not a JSON array
        """
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
        """
        Deterministic hash of the structural signature:
        top-level publication keys + ExchangeRate item keys.
        Triggers raw capture on schema change.
        """
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


# ── Backward Compatibility Wrappers ──────────────────────────────────────────

def parse(raw_json: str) -> list:
    """
    Parse the raw API JSON array into AdapterRecords.
    
    BACKWARD COMPATIBILITY WRAPPER: New code should use CBEAdapter().parse()
    
    Raises ValueError if top-level is not a JSON array.
    Returns empty list for empty array.
    """
    adapter = CBEAdapter()
    result = adapter.parse(raw_json)
    
    # Old API raised ValueError on errors, new API returns ParseResult with errors
    # Convert back to old behavior for backward compatibility
    if result.errors:
        raise ValueError(result.errors[0])
    
    return result.records


def _parse_publication(pub: dict) -> list:
    """Parse one publication record into AdapterRecords."""
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
    """Parse one ExchangeRate item using field detection."""
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

    # Use field detection to detect categories and emit records
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
    """Parse YYYY-MM-DD date string. Returns None if unparseable."""
    try:
        return date.fromisoformat(date_str.strip())
    except (ValueError, AttributeError):
        return None


def schema_fingerprint(raw_json: str) -> str:
    """
    Deterministic hash of the structural signature.
    
    BACKWARD COMPATIBILITY WRAPPER: New code should use CBEAdapter().schema_fingerprint()
    """
    return CBEAdapter().schema_fingerprint(raw_json)
