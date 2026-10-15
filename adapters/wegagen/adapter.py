"""
adapters/wegagen/adapter.py — Wegagen Bank (Type C1, Strapi v4).

Parse rules (ADR-006 §6, mapping doc):
- Input: Strapi v4 envelope {data: [{id, attributes: {...}}, ...], meta: {pagination}}.
- Each item attributes: {date, code, unit, buying, selling, tra_buying, tra_selling, ...}.
- buying == tra_buying for all observed records — category ambiguity (TO VERIFY).
- Emit one AdapterRecord per row with category UNKNOWN until category is confirmed.
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

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "wegagen_api"
SOURCE_URL = "https://weg.back.strapi.wegagen.com/api/exchange-rates?populate=*"

_REQUIRED_ATTRS = {"date", "code", "buying", "selling"}


def parse(raw_json: str) -> list:
    """
    Parse the Strapi v4 JSON envelope into AdapterRecords.
    Emits two records per row: one cash (buying/selling), one transactional (tra_buying/tra_selling).
    Raises ValueError if envelope is malformed or required keys are missing.
    Returns empty list if data array is empty.
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Wegagen: JSON parse error: {exc}") from exc

    if not isinstance(data, dict) or "data" not in data:
        raise ValueError("Wegagen: missing 'data' key — not a Strapi v4 envelope")

    items = data["data"]
    if not isinstance(items, list):
        raise ValueError(f"Wegagen: 'data' must be an array, got {type(items).__name__}")

    return [r for item in items for r in _parse_item(item) if r is not None]


def _parse_item(item: dict) -> list:
    """Emit up to two records per item: one cash, one transactional."""
    if not isinstance(item, dict):
        return []

    item_id = item.get("id")
    attrs = item.get("attributes", {})
    if not isinstance(attrs, dict):
        return []

    missing = _REQUIRED_ATTRS - attrs.keys()
    if missing:
        raise ValueError(f"Wegagen: attributes missing required keys: {sorted(missing)}")

    currency = str(attrs.get("code", "")).strip()
    if not currency:
        return []

    effective_date = _parse_date(attrs.get("date", ""))
    date_basis = "source_published" if effective_date else "collection_date_fallback"
    unit = int(attrs.get("unit", 1) or 1)

    records = []

    # cash rate
    cash_buy = _safe_rate(attrs.get("buying"))
    cash_sell = _safe_rate(attrs.get("selling"))
    if cash_buy is not None or cash_sell is not None:
        records.append(AdapterRecord(
            source_currency_code=currency,
            category="cash",
            buying_rate=cash_buy,
            selling_rate=cash_sell,
            source_rate_text=f"{attrs.get('buying')}/{attrs.get('selling')}",
            effective_date=effective_date,
            effective_date_basis=date_basis,
            source_record_key=f"{item_id}:cash" if item_id is not None else None,
            source_publication_key=None,
            quote_currency_code=None,
            unit_multiplier=unit,
            raw_excerpt={"id": item_id, "code": currency, "date": attrs.get("date"),
                         "buying": attrs.get("buying"), "selling": attrs.get("selling")},
            mapping_notes=["strapi_v4:populate_star"],
        ))

    # transactional rate
    tra_buy = _safe_rate(attrs.get("tra_buying"))
    tra_sell = _safe_rate(attrs.get("tra_selling"))
    if tra_buy is not None or tra_sell is not None:
        records.append(AdapterRecord(
            source_currency_code=currency,
            category="transactional",
            buying_rate=tra_buy,
            selling_rate=tra_sell,
            source_rate_text=f"{attrs.get('tra_buying')}/{attrs.get('tra_selling')}",
            effective_date=effective_date,
            effective_date_basis=date_basis,
            source_record_key=f"{item_id}:transactional" if item_id is not None else None,
            source_publication_key=None,
            quote_currency_code=None,
            unit_multiplier=unit,
            raw_excerpt={"id": item_id, "code": currency, "date": attrs.get("date"),
                         "tra_buying": attrs.get("tra_buying"), "tra_selling": attrs.get("tra_selling")},
            mapping_notes=["strapi_v4:populate_star"],
        ))

    return records


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
    """Hash of Strapi envelope keys + first item's attributes keys."""
    try:
        data = json.loads(raw_json)
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
