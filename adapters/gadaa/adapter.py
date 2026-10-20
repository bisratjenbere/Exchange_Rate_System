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

from adapters.base import JSONAdapter, ParseResult
from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "gadaa_api"
SOURCE_URL = "https://gadaabank.com.et/api/v1/exchange-rates"


class GadaaAdapter(JSONAdapter):
    """
    Gadaa Bank adapter using JSONAdapter base class.
    
    Parses JSON from REST API with market_type field determining category.
    Emits up to 2 records per currency (market_type + weighted_average).
    """
    
    def get_source_url(self) -> str:
        """Return Gadaa API URL."""
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        """Return unique adapter identifier."""
        return ADAPTER_KEY
    
    def _process_data(self, data, **options) -> ParseResult:
        """
        Extract AdapterRecords from parsed JSON data.
        
        Args:
            data: Parsed JSON (should be dict with 'data' array)
            **options: Additional options (unused)
        
        Returns:
            ParseResult with records and any errors
        """
        result = ParseResult()
        
        rows = data.get("data", [])
        if not isinstance(rows, list):
            result.add_error("data_not_array")
            return result
        
        for row in rows:
            try:
                records = _parse_row(row)
                result.records.extend(records)
            except Exception as exc:
                result.add_error(f"row:{row.get('currency')}:{exc}")
        
        return result
    
    def schema_fingerprint(self, raw_content: str) -> str:
        """
        Generate schema fingerprint based on data array keys.
        
        Args:
            raw_content: Raw JSON string
            
        Returns:
            SHA256 hex digest of structural signature
        """
        try:
            data = json.loads(raw_content)
            rows = data.get("data", [])
            keys = sorted(rows[0].keys()) if rows else []
            return hashlib.sha256(str({"keys": keys}).encode()).hexdigest()
        except Exception:
            return hashlib.sha256(b"gadaa:unparseable").hexdigest()


def _parse_row(row: dict) -> list:
    """Parse one data row into up to 2 AdapterRecords."""
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
    """Create AdapterRecord from extracted data."""
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
    """Parse ISO date from timestamp string."""
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw).strip()[:10])
    except ValueError:
        return None


def _safe_rate(raw) -> Optional[Decimal]:
    """Safely convert raw value to normalized Decimal rate."""
    if raw is None or raw == 0:
        return None
    try:
        return normalize_rate(raw)
    except ValueError:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Backward Compatibility Wrappers
# ═══════════════════════════════════════════════════════════════════════════════

def parse(raw_json: str) -> tuple:
    """
    Old function API (for backward compatibility).
    
    New code should use GadaaAdapter().parse().
    
    Args:
        raw_json: Raw JSON string from Gadaa API
        
    Returns:
        Tuple of (records, errors) for backward compatibility
    """
    adapter = GadaaAdapter()
    result = adapter.parse(raw_json)
    return result.records, result.errors


def schema_fingerprint(raw_json: str) -> str:
    """
    Old function API (for backward compatibility).
    
    New code should use GadaaAdapter().schema_fingerprint().
    
    Args:
        raw_json: Raw JSON string
        
    Returns:
        SHA256 hash of structural signature
    """
    return GadaaAdapter().schema_fingerprint(raw_json)
