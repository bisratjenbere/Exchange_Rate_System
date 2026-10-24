"""
adapters/zemen/adapter.py — Zemen Bank (WordPress AJAX JSON).

Fetch: POST https://zemenbank.com/wp-admin/admin-ajax.php
       body: action=get_exchange_rates
       Referer: https://zemenbank.com/exchange-rates/

Response structure:
  {status, date, avg_date, rates: {day: [...], cash: [...], average: [...]}}
  Each item: {exchange_id, currency_code, buying_rate, selling_rate,
              cash_buying_rate, cash_selling_rate, post_date, avg_buying_rate, avg_selling_rate}

Parse rules:
- rates.day  → transactional (buying_rate / selling_rate), date from top-level "date"
- rates.cash → NOT USED (redundant with day array)
- rates.average → weighted_average (buying_rate / selling_rate), date from avg_date
- day array rows contain both transactional AND cash rates
- Field detection auto-discovers: buying_rate, cash_buying_rate patterns
- "date" field is YYYY-MM-DD → source_published
- Partial failure: returns (records, errors). Never raises.

MIGRATION NOTE: Migrated to use FieldStructureMixin for automatic category detection.
Empty config auto-detects all field pairs from field names.
"""
import hashlib
import json
from datetime import date
from typing import Optional

from adapters.base import JSONAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin

ADAPTER_KEY = "zemen_ajax"
SOURCE_URL = "https://zemenbank.com/wp-admin/admin-ajax.php"
COLLECTION_METHOD = "ajax_endpoint"
FETCH_POST_DATA = {"action": "get_exchange_rates"}
FETCH_HEADERS = {"Referer": "https://zemenbank.com/exchange-rates/"}


# ============================================================================
# ADAPTER CLASS
# ============================================================================

class ZemenAdapter(FieldStructureMixin, JSONAdapter):
    """
    Zemen Bank adapter using WordPress AJAX JSON endpoint with field detection.
    
    Field Structure: Auto-detected from field names
    - buying_rate/selling_rate → UNKNOWN (will be filtered or context-based)
    - cash_buying_rate/cash_selling_rate → cash
    - From average array: buying_rate/selling_rate → weighted_average (context-based)
    """
    
    # Empty config - field detection will find all pairs automatically
    FIELD_CONFIG = {}
    
    def get_source_url(self) -> str:
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        return ADAPTER_KEY
    
    def _process_data(self, data, **kwargs) -> ParseResult:
        """Process WordPress AJAX response and extract rate records using field detection."""
        result = ParseResult()
        
        if data.get("status") != "success":
            result.add_error(f"status:{data.get('status')}")
            return result
        
        effective_date = self._parse_iso_date(data.get("date", ""))
        avg_date = self._parse_iso_date(data.get("avg_date", ""))
        date_basis = "source_published" if effective_date else "collection_date_fallback"
        avg_basis = "source_published" if avg_date else "collection_date_fallback"
        
        rates = data.get("rates", {})
        
        # Process day array (transactional + cash rates)
        for row in rates.get("day", []):
            try:
                code = str(row.get("currency_code", "")).strip()
                if not code:
                    continue
                
                # Use field detection to automatically discover and emit records
                detected_records = self.detect_and_emit(
                    data=row,
                    currency=code,
                    effective_date=effective_date,
                    effective_date_basis=date_basis,
                    source_record_id=str(row.get("exchange_id")) if row.get("exchange_id") else None
                )
                
                # Post-process: buying_rate/selling_rate (UNKNOWN) should be transactional in day context
                for rec in detected_records:
                    if rec.category == 'UNKNOWN':
                        rec.category = 'transactional'
                    # Add post_date to raw_excerpt for traceability
                    if isinstance(rec.raw_excerpt, dict):
                        rec.raw_excerpt["post_date"] = row.get("post_date")
                
                result.records.extend(detected_records)
                
            except Exception as exc:
                result.add_error(f"day_row:{row.get('currency_code')}:{exc}")
        
        # Process average array (weighted_average rates)
        for row in rates.get("average", []):
            try:
                code = str(row.get("currency_code", "")).strip()
                if not code:
                    continue
                
                # Use field detection
                detected_records = self.detect_and_emit(
                    data=row,
                    currency=code,
                    effective_date=avg_date,
                    effective_date_basis=avg_basis,
                    source_record_id=str(row.get("exchange_id")) if row.get("exchange_id") else None
                )
                
                # Post-process: buying_rate/selling_rate (UNKNOWN) should be weighted_average in average context
                for rec in detected_records:
                    if rec.category == 'UNKNOWN':
                        rec.category = 'weighted_average'
                    if isinstance(rec.raw_excerpt, dict):
                        rec.raw_excerpt["post_date"] = row.get("post_date")
                
                result.records.extend(detected_records)
                
            except Exception as exc:
                result.add_error(f"avg_row:{row.get('currency_code')}:{exc}")
        
        return result
    
    def schema_fingerprint(self, raw_content: str) -> str:
        """Hash rate keys and first row structure."""
        try:
            data = json.loads(raw_content)
            keys = sorted(data.get("rates", {}).keys())
            row_keys = sorted(data["rates"]["day"][0].keys()) if data.get("rates", {}).get("day") else []
            return hashlib.sha256(str({"rate_keys": keys, "row_keys": row_keys}).encode()).hexdigest()
        except Exception:
            return hashlib.sha256(b"zemen:unparseable").hexdigest()


# ============================================================================
# MODULE-LEVEL FUNCTIONS (backward compatibility)
# ============================================================================

_adapter = ZemenAdapter()


def parse(raw_json: str) -> tuple:
    """
    Parse WordPress AJAX JSON response.
    Backward-compatible wrapper that returns (records, errors) tuple.
    """
    result = _adapter.parse(raw_json)
    return result.records, result.errors


def schema_fingerprint(raw_json: str) -> str:
    """Hash rate keys and first row structure."""
    return _adapter.schema_fingerprint(raw_json)

