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
- rates.cash → cash (cash_buying_rate / cash_selling_rate), same date
- rates.average → weighted_average (buying_rate / selling_rate), date from avg_date
- day and cash arrays share the same rows — emit both categories per row from day array
- "date" field is YYYY-MM-DD → source_published
- Partial failure: returns (records, errors). Never raises.
"""
import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Optional

from adapters.base import JSONAdapter, ParseResult
from domain.records import AdapterRecord

ADAPTER_KEY = "zemen_ajax"
SOURCE_URL = "https://zemenbank.com/wp-admin/admin-ajax.php"
COLLECTION_METHOD = "ajax_endpoint"
FETCH_POST_DATA = {"action": "get_exchange_rates"}
FETCH_HEADERS = {"Referer": "https://zemenbank.com/exchange-rates/"}


# ============================================================================
# ADAPTER CLASS
# ============================================================================

class ZemenAdapter(JSONAdapter):
    """Zemen Bank adapter using WordPress AJAX JSON endpoint."""
    
    def get_source_url(self) -> str:
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        return ADAPTER_KEY
    
    def _process_data(self, data, **kwargs) -> ParseResult:
        """Process WordPress AJAX response and extract rate records."""
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
                txn_buy = self._safe_rate(row.get("buying_rate"))
                txn_sell = self._safe_rate(row.get("selling_rate"))
                cash_buy = self._safe_rate(row.get("cash_buying_rate"))
                cash_sell = self._safe_rate(row.get("cash_selling_rate"))
                
                if txn_buy is not None or txn_sell is not None:
                    result.records.append(self._make_record(
                        code, "transactional", txn_buy, txn_sell,
                        row.get("buying_rate"), row.get("selling_rate"),
                        effective_date, date_basis, row
                    ))
                if cash_buy is not None or cash_sell is not None:
                    result.records.append(self._make_record(
                        code, "cash", cash_buy, cash_sell,
                        row.get("cash_buying_rate"), row.get("cash_selling_rate"),
                        effective_date, date_basis, row
                    ))
            except Exception as exc:
                result.add_error(f"day_row:{row.get('currency_code')}:{exc}")
        
        # Process average array (weighted_average rates)
        for row in rates.get("average", []):
            try:
                code = str(row.get("currency_code", "")).strip()
                if not code:
                    continue
                buy = self._safe_rate(row.get("buying_rate"))
                sell = self._safe_rate(row.get("selling_rate"))
                if buy is None and sell is None:
                    continue
                result.records.append(self._make_record(
                    code, "weighted_average", buy, sell,
                    row.get("buying_rate"), row.get("selling_rate"),
                    avg_date, avg_basis, row
                ))
            except Exception as exc:
                result.add_error(f"avg_row:{row.get('currency_code')}:{exc}")
        
        return result
    
    def _make_record(self, code, category, buying, selling, buy_text, sell_text, eff_date, date_basis, row):
        """Helper to create AdapterRecord with consistent structure."""
        return AdapterRecord(
            source_currency_code=code,
            category=category,
            buying_rate=buying,
            selling_rate=selling,
            source_rate_text=self._rate_text(buy_text, sell_text),
            effective_date=eff_date,
            effective_date_basis=date_basis,
            source_record_key=str(row.get("exchange_id")) if row.get("exchange_id") else None,
            source_publication_key=None,
            unit_multiplier=1,
            raw_excerpt={"currency": code, "buying": buy_text, "selling": sell_text,
                         "post_date": row.get("post_date")},
            mapping_notes=[],
        )
    
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
