"""
adapters/wegagen/adapter.py — Wegagen Bank (Type C1, Strapi v4).

Parse rules (ADR-006 §6, mapping doc):
- Input: Strapi v4 envelope {data: [{id, attributes: {...}}, ...], meta: {pagination}}.
- Each item attributes: {date, code, unit, buying, selling, tra_buying, tra_selling, ...}.
- buying == tra_buying for all observed records — normalized to 'transactional' category.
- Emit one AdapterRecord per row with category normalized from 'transactional'.
- Per-row date (YYYY-MM-DD) → effective_date_basis=source_published.
- source_record_key = str(id) — stable Strapi integer.
- identity_status = derived (source_published date, no stable publication ID).
- unit field present (= 1 for all observed records) — stored as unit_multiplier.
- Raises ValueError if envelope is not a JSON object or data key is missing.
- Schema change: raises ValueError if required attributes keys are absent.
"""
import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Optional

from adapters.base import JSONAdapter, ParseResult
from domain.records import AdapterRecord
from pipeline.category_normalizer import normalize_category
from field_detection.mixin import FieldStructureMixin

ADAPTER_KEY = "wegagen_api"
SOURCE_URL = "https://weg.back.strapi.wegagen.com/api/exchange-rates?populate=*"

_REQUIRED_ATTRS = {"date", "code"}  # buying/selling checked by field detection


# ============================================================================
# ADAPTER CLASS
# ============================================================================

class WegagenAdapter(JSONAdapter, FieldStructureMixin):
    """
    Wegagen Bank adapter using Strapi v4 JSON API.
    
    Uses field-structure-based category detection to emit multiple records
    per currency when both buying/tra_buying field pairs are present.
    """
    
    # Configure explicit field mappings for Wegagen's field structure
    FIELD_CONFIG = {
        "field_mappings": {
            "buying": "cash",
            "selling": "cash",
            "tra_buying": "transactional",
            "tra_selling": "transactional"
        },
        "default_category": "transactional"
    }
    
    def get_source_url(self) -> str:
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        return ADAPTER_KEY
    
    def _process_data(self, data, **kwargs) -> ParseResult:
        """Process Strapi v4 envelope and extract rate records."""
        result = ParseResult()
        
        if not isinstance(data, dict) or "data" not in data:
            result.add_error("missing 'data' key — not a Strapi v4 envelope")
            return result
        
        items = data["data"]
        if not isinstance(items, list):
            result.add_error(f"'data' must be an array, got {type(items).__name__}")
            return result
        
        for item in items:
            try:
                records = self._parse_item(item)
                result.records.extend(records)
            except ValueError as exc:
                result.add_error(str(exc))
            except Exception as exc:
                result.add_error(f"item:{item.get('id', '?')}:{exc}")
        
        return result
    
    def _parse_item(self, item: dict) -> list:
        """Parse one item using field detection to emit records per detected category."""
        if not isinstance(item, dict):
            return []
        
        item_id = item.get("id")
        attrs = item.get("attributes", {})
        if not isinstance(attrs, dict):
            return []
        
        missing = _REQUIRED_ATTRS - attrs.keys()
        if missing:
            raise ValueError(f"attributes missing required keys: {sorted(missing)}")
        
        currency = str(attrs.get("code", "")).strip()
        if not currency:
            return []
        
        effective_date = self._parse_iso_date(attrs.get("date", ""))
        date_basis = "source_published" if effective_date else "collection_date_fallback"
        unit = int(attrs.get("unit", 1) or 1)
        
        # Use field detection to detect and emit records
        records = self.detect_and_emit(
            attrs,
            currency=currency,
            effective_date=effective_date,
            effective_date_basis=date_basis,
            source_record_id=str(item_id) if item_id is not None else None,
            unit_multiplier=unit,
            mapping_notes=["strapi_v4:populate_star"]
        )
        
        return records
    
    def schema_fingerprint(self, raw_content: str) -> str:
        """Hash of Strapi envelope keys + first item's attributes keys."""
        try:
            data = json.loads(raw_content)
            if isinstance(data, dict) and isinstance(data.get("data"), list):
                items = data["data"]
                attr_keys = []
                if items and isinstance(items[0], dict):
                    attrs = items[0].get("attributes", {})
                    if isinstance(attrs, dict):
                        attr_keys = sorted(k for k in attrs.keys() if k != "flag")
                payload = json.dumps({"attrs": attr_keys}, separators=(",", ":"))
                return hashlib.sha256(payload.encode()).hexdigest()
        except Exception:
            pass
        return hashlib.sha256(b"wegagen:empty_or_unparseable").hexdigest()


# ============================================================================
# MODULE-LEVEL FUNCTIONS (backward compatibility)
# ============================================================================

_adapter = WegagenAdapter()


def parse(raw_json: str) -> list:
    """
    Parse the Strapi v4 JSON envelope into AdapterRecords.
    Backward-compatible wrapper that returns list.
    """
    result = _adapter.parse(raw_json)
    if result.errors:
        # Maintain backward compatibility: raise on first error
        raise ValueError(f"Wegagen: {result.errors[0]}")
    return result.records


def schema_fingerprint(raw_json: str) -> str:
    """Hash of Strapi envelope keys + first item's attributes keys."""
    return _adapter.schema_fingerprint(raw_json)
