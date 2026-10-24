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

MIGRATION NOTE: Migrated to use FieldStructureMixin for automatic category detection.
Special handling: market_type field provides explicit category for buy_rate/sell_rate.
"""
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
    """
    Gadaa Bank adapter using JSONAdapter base class with field detection.
    
    Parses JSON from REST API. Uses market_type field for primary category,
    and field detection for weighted_average records.
    
    Field Structure: Mixed approach
    - buy_rate/sell_rate → category from market_type field
    - weighted_buy_rate/weighted_sell_rate → weighted_average (auto-detected)
    """
    
    # Empty config - field detection will find weighted_buy_rate/weighted_sell_rate
    FIELD_CONFIG = {}
    
    def get_source_url(self) -> str:
        """Return Gadaa API URL."""
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        """Return unique adapter identifier."""
        return ADAPTER_KEY
    
    def _process_data(self, data, **options) -> ParseResult:
        """
        Extract AdapterRecords from parsed JSON data using field detection.
        
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
                code = str(row.get("currency", "")).strip()
                if not code or not row.get("is_active", True):
                    continue

                effective_date = _parse_date(row.get("updated_at"))
                date_basis = "source_inferred" if effective_date else "collection_date_fallback"
                
                # Use field detection to automatically discover and emit records
                # This will find weighted_buy_rate/weighted_sell_rate and buy_rate/sell_rate
                detected_records = self.detect_and_emit(
                    data=row,
                    currency=code,
                    source_record_id=str(row.get("id")) if row.get("id") else None,
                    effective_date=effective_date,
                    effective_date_basis=date_basis
                )
                
                # Post-process: Override category for buy_rate/sell_rate using market_type field
                market_type = str(row.get("market_type", "")).lower()
                explicit_category = normalize_category(market_type) if market_type else normalize_category("transactional")
                
                for rec in detected_records:
                    # If this is buy_rate/sell_rate (not weighted), use market_type category
                    # We can identify this by checking if it's NOT weighted_average
                    if rec.category != 'weighted_average' and rec.category != 'UNKNOWN':
                        # This is likely buy_rate/sell_rate - use market_type
                        rec.category = explicit_category
                    elif rec.category == 'UNKNOWN':
                        # Generic buy_rate/sell_rate detected - use market_type
                        rec.category = explicit_category
                    # else: weighted_average stays as is
                    
                    # Add market_type to raw_excerpt for traceability
                    if isinstance(rec.raw_excerpt, dict):
                        rec.raw_excerpt["market_type"] = row.get("market_type")
                        rec.raw_excerpt["updated_at"] = row.get("updated_at")
                
                result.records.extend(detected_records)
                
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


def _parse_date(raw) -> Optional[date]:
    """Parse ISO date from timestamp string."""
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw).strip()[:10])
    except ValueError:
        return None


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
