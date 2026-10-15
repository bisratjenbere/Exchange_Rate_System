"""
adapters/gadaa/adapter.py — Gadaa Bank (REST API JSON).

Fetch: GET https://gadaabank.com.et/api/v1/exchange-rates

Response: {data: [{id, currency, buy_rate, sell_rate, market_type,
                   weighted_buy_rate, weighted_sell_rate, updated_at, ...}],
           last_updated}

Parse rules:
- market_type = "transaction" → transactional
- market_type = "cash"        → cash
- weighted_buy_rate / weighted_sell_rate (non-null, non-zero) → weighted_average record
- updated_at ISO timestamp date part → source_inferred effective_date
- 0 / null → None
- Partial failure: returns (records, errors). Never raises.
"""
import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Optional

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "gadaa_api"
SOURCE_URL = "https://gadaabank.com.et/api/v1/exchange-rates"


def parse(raw_json: str) -> tuple:
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return [], [f"json_parse:{exc}"]

    rows = data.get("data", [])
    if not isinstance(rows, list):
        return [], ["data_not_array"]

    records, errors = [], []
    for row in rows:
        try:
            records.extend(_parse_row(row))
        except Exception as exc:
            errors.append(f"row:{row.get('currency')}:{exc}")
    return records, errors


def _parse_row(row: dict) -> list:
    code = str(row.get("currency", "")).strip()
    if not code or not row.get("is_active", True):
        return []

    effective_date = _parse_date(row.get("updated_at"))
    date_basis = "source_inferred" if effective_date else "collection_date_fallback"
    market_type = str(row.get("market_type", "")).lower()
    category = "transactional" if market_type == "transaction" else "cash" if market_type == "cash" else "transactional"

    records = []
    buy = _safe_rate(row.get("buy_rate"))
    sell = _safe_rate(row.get("sell_rate"))
    if buy is not None or sell is not None:
        records.append(_make(code, category, buy, sell,
                             row.get("buy_rate"), row.get("sell_rate"),
                             effective_date, date_basis, row))

    w_buy = _safe_rate(row.get("weighted_buy_rate"))
    w_sell = _safe_rate(row.get("weighted_sell_rate"))
    if w_buy is not None or w_sell is not None:
        records.append(_make(code, "weighted_average", w_buy, w_sell,
                             row.get("weighted_buy_rate"), row.get("weighted_sell_rate"),
                             effective_date, date_basis, row))
    return records


def _make(code, category, buying, selling, buy_text, sell_text, eff_date, date_basis, row):
    return AdapterRecord(
        source_currency_code=code,
        category=category,
        buying_rate=buying,
        selling_rate=selling,
        source_rate_text=f"{buy_text}/{sell_text}",
        effective_date=eff_date,
        effective_date_basis=date_basis,
        source_record_key=str(row.get("id")) if row.get("id") else None,
        source_publication_key=None,
        unit_multiplier=1,
        raw_excerpt={"currency": code, "buy_rate": buy_text, "sell_rate": sell_text,
                     "market_type": row.get("market_type"), "updated_at": row.get("updated_at")},
        mapping_notes=[],
    )


def _parse_date(raw) -> Optional[date]:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw).strip()[:10])
    except ValueError:
        return None


def _safe_rate(raw) -> Optional[Decimal]:
    if raw is None or raw == 0:
        return None
    try:
        return normalize_rate(raw)
    except ValueError:
        return None


def schema_fingerprint(raw_json: str) -> str:
    try:
        data = json.loads(raw_json)
        rows = data.get("data", [])
        keys = sorted(rows[0].keys()) if rows else []
        return hashlib.sha256(str({"keys": keys}).encode()).hexdigest()
    except Exception:
        return hashlib.sha256(b"gadaa:unparseable").hexdigest()
