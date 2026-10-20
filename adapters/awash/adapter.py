"""
adapters/awash/adapter.py — Awash Bank (WordPress AJAX with nonce).

Two-step fetch (implemented in fetch_raw):
  1. GET https://awashbank.com/ → find LiteSpeed bundled JS URL
  2. GET <js_bundle_url> → extract nonce from exchangeRatesVars object
  3. POST https://awashbank.com/wp-admin/admin-ajax.php
       action=get_exchange_rates
       nonce=<extracted>
       shortcode_type=rates_widgest

Response: {"success":true,"data":{"rates":{
    "USD":{"buying":"160.92","selling":"164.14",
           "transaction_buying":"160.92","transaction_selling":"164.14",
           "weighted_buying_average":"163.71",...},
    ...
}}}

Parse rules:
- buying/selling → transactional category
- transaction_buying/transaction_selling → also transactional (same values, skip duplicate)
- weighted_buying_average / weighted_selling_average → weighted_average category
- Date from top-level data.date field (YYYY-MM-DD) → source_published
- Partial failure: returns (records, errors). Never raises.
"""
import hashlib
import json
import re
import time
from datetime import date
from decimal import Decimal
from typing import Optional

import requests

from adapters.base import JSONAdapter, ParseResult
from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "awash_ajax"
SOURCE_URL = "https://awashbank.com/wp-admin/admin-ajax.php"
_HOME_URL = "https://awashbank.com/"
_AJAX_URL = "https://awashbank.com/wp-admin/admin-ajax.php"


class AwashAdapter(JSONAdapter):
    """
    Awash Bank adapter using JSONAdapter base class.
    
    Parses JSON response from WordPress AJAX endpoint.
    Emits 0-2 records per currency (transactional + weighted_average).
    """
    
    def get_source_url(self) -> str:
        """Return Awash AJAX endpoint URL."""
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        """Return unique adapter identifier."""
        return ADAPTER_KEY
    
    def _process_data(self, data, **options) -> ParseResult:
        """
        Extract AdapterRecords from parsed JSON data.
        
        Args:
            data: Parsed JSON (should be WordPress AJAX response)
            **options: Additional options (unused)
        
        Returns:
            ParseResult with records and any errors
        """
        result = ParseResult()
        
        if not data.get("success"):
            result.add_error(f"success_false:{data.get('data')}")
            return result
        
        inner = data.get("data", {})
        rates = inner.get("rates", {})
        if not isinstance(rates, dict):
            result.add_error("rates_not_dict")
            return result
        
        effective_date = _parse_date(inner.get("date"))
        date_basis = "source_published" if effective_date else "collection_date_fallback"
        
        for currency, rate_data in rates.items():
            if not isinstance(rate_data, dict):
                continue
            try:
                records = _parse_currency(currency, rate_data, effective_date, date_basis)
                result.records.extend(records)
            except Exception as exc:
                result.add_error(f"currency:{currency}:{exc}")
        
        return result
    
    def schema_fingerprint(self, raw_content: str) -> str:
        """
        Deterministic hash of the structural signature.
        
        Hashes sorted currency codes and rate field keys.
        Triggers raw capture on schema change.
        """
        try:
            data = json.loads(raw_content)
            currencies = sorted(data["data"]["rates"].keys())
            rate_keys = sorted(next(iter(data["data"]["rates"].values())).keys())
            payload = json.dumps({"currencies": currencies, "rate_keys": rate_keys}, separators=(",", ":"))
            return hashlib.sha256(payload.encode()).hexdigest()
        except Exception:
            pass
        return hashlib.sha256(b"awash:unparseable").hexdigest()


def fetch_raw(source_url: str, user_agent: str, ssl_verify: bool) -> tuple:
    """Two-step fetch: extract nonce from homepage HTML, then POST AJAX."""
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    # Step 1: GET homepage and extract nonce inline
    resp = requests.get(_HOME_URL, headers=headers, timeout=15, verify=ssl_verify)
    if resp.status_code != 200:
        raise RuntimeError(f"Homepage HTTP {resp.status_code}")

    nonce = _extract_nonce(resp.text)
    if not nonce:
        raise ValueError("Nonce not found in homepage")

    time.sleep(1)

    # Step 2: POST AJAX
    ajax_headers = {
        "User-Agent": user_agent,
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": _HOME_URL,
        "X-Requested-With": "XMLHttpRequest",
    }
    post_data = {
        "action": "get_exchange_rates",
        "nonce": nonce,
        "shortcode_type": "rates_widgest",
    }
    ajax_resp = requests.post(
        _AJAX_URL, data=post_data, headers=ajax_headers,
        timeout=15, verify=ssl_verify,
    )
    return ajax_resp.text, ajax_resp.status_code


def _extract_js_url(html: str) -> Optional[str]:
    """Extract LiteSpeed JS bundle URL from homepage HTML."""
    # LiteSpeed bundles JS: <script ... src="https://awashbank.com/wp-content/litespeed/js/....js"
    m = re.search(
        r'src=["\']+(https://awashbank\.com/wp-content/litespeed/js/[^"\']+\.js)',
        html,
    )
    return m.group(1) if m else None


def _extract_nonce(js_text: str) -> Optional[str]:
    """Extract nonce from exchangeRatesVars object in JS."""
    # exchangeRatesVars={"nonce":"55c098d874",...}
    m = re.search(r'exchangeRatesVars\s*=\s*\{[^}]*"nonce"\s*:\s*"([a-f0-9]+)"', js_text)
    return m.group(1) if m else None


def _parse_currency(currency: str, rate_data: dict, eff_date, date_basis: str) -> list:
    """Parse one currency's rate data into 0-2 AdapterRecords."""
    records = []

    # transactional: buying / selling
    buy = _safe_rate(rate_data.get("buying"))
    sell = _safe_rate(rate_data.get("selling"))
    if buy is not None or sell is not None:
        records.append(_make(currency, "transactional", buy, sell,
                             rate_data.get("buying"), rate_data.get("selling"),
                             eff_date, date_basis))

    # weighted_average
    w_buy = _safe_rate(rate_data.get("weighted_buying_average"))
    w_sell = _safe_rate(rate_data.get("weighted_selling_average"))
    if w_buy is not None or w_sell is not None:
        records.append(_make(currency, "weighted_average", w_buy, w_sell,
                             rate_data.get("weighted_buying_average"),
                             rate_data.get("weighted_selling_average"),
                             eff_date, date_basis))
    return records


def _make(currency, category, buying, selling, buy_text, sell_text, eff_date, date_basis):
    """Create AdapterRecord from extracted data."""
    return AdapterRecord(
        source_currency_code=currency,
        category=category,
        buying_rate=buying,
        selling_rate=selling,
        source_rate_text=f"{buy_text}/{sell_text}",
        effective_date=eff_date,
        effective_date_basis=date_basis,
        source_record_key=f"{eff_date}:{currency}:{category}",
        source_publication_key=str(eff_date) if eff_date else None,
        unit_multiplier=1,
        raw_excerpt={"currency": currency, "buying": buy_text, "selling": sell_text},
        mapping_notes=[],
    )


def _parse_date(raw) -> Optional[date]:
    """Parse YYYY-MM-DD date string."""
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw).strip()[:10])
    except ValueError:
        return None


def _safe_rate(raw) -> Optional[Decimal]:
    """Safely convert raw value to normalized Decimal rate."""
    if raw is None or str(raw).strip() in ("", "0", "0.0000"):
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
    
    New code should use AwashAdapter().parse().
    
    Args:
        raw_json: Raw JSON string from AJAX endpoint
        
    Returns:
        Tuple of (records, errors) for backward compatibility
    """
    adapter = AwashAdapter()
    result = adapter.parse(raw_json)
    return result.records, result.errors


def schema_fingerprint(raw_json: str) -> str:
    """
    Old function API (for backward compatibility).
    
    New code should use AwashAdapter().schema_fingerprint().
    
    Args:
        raw_json: Raw JSON string from AJAX endpoint
        
    Returns:
        SHA256 hash of structural signature
    """
    return AwashAdapter().schema_fingerprint(raw_json)
