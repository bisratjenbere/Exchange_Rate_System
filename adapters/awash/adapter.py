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

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "awash_ajax"
SOURCE_URL = "https://awashbank.com/wp-admin/admin-ajax.php"
_HOME_URL = "https://awashbank.com/"
_AJAX_URL = "https://awashbank.com/wp-admin/admin-ajax.php"


def fetch_raw(source_url: str, user_agent: str, ssl_verify: bool) -> tuple:
    """Two-step fetch: extract nonce from LiteSpeed JS, then POST AJAX."""
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    # Step 1: GET homepage to find LiteSpeed JS bundle URL
    resp = requests.get(_HOME_URL, headers=headers, timeout=15, verify=ssl_verify)
    if resp.status_code != 200:
        raise RuntimeError(f"Homepage HTTP {resp.status_code}")

    js_url = _extract_js_url(resp.text)
    if not js_url:
        raise ValueError("LiteSpeed JS bundle URL not found in homepage")

    time.sleep(1)

    # Step 2: GET JS bundle and extract nonce
    js_resp = requests.get(js_url, headers=headers, timeout=15, verify=ssl_verify)
    if js_resp.status_code != 200:
        raise RuntimeError(f"JS bundle HTTP {js_resp.status_code}")

    nonce = _extract_nonce(js_resp.text)
    if not nonce:
        raise ValueError("Nonce not found in JS bundle")

    time.sleep(1)

    # Step 3: POST AJAX
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
    # LiteSpeed bundles JS: <script ... src="https://awashbank.com/wp-content/litespeed/js/....js"
    m = re.search(
        r'src=["\']+(https://awashbank\.com/wp-content/litespeed/js/[^"\']+\.js)',
        html,
    )
    return m.group(1) if m else None


def _extract_nonce(js_text: str) -> Optional[str]:
    # exchangeRatesVars={"nonce":"55c098d874",...}
    m = re.search(r'exchangeRatesVars\s*=\s*\{[^}]*"nonce"\s*:\s*"([a-f0-9]+)"', js_text)
    return m.group(1) if m else None


def parse(raw_json: str) -> tuple:
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return [], [f"json_parse:{exc}"]

    if not data.get("success"):
        return [], [f"success_false:{data.get('data')}"]

    inner = data.get("data", {})
    rates = inner.get("rates", {})
    if not isinstance(rates, dict):
        return [], ["rates_not_dict"]

    effective_date = _parse_date(inner.get("date"))
    date_basis = "source_published" if effective_date else "collection_date_fallback"

    records, errors = [], []
    for currency, rate_data in rates.items():
        if not isinstance(rate_data, dict):
            continue
        try:
            records.extend(_parse_currency(currency, rate_data, effective_date, date_basis))
        except Exception as exc:
            errors.append(f"currency:{currency}:{exc}")
    return records, errors


def _parse_currency(currency: str, rate_data: dict, eff_date, date_basis: str) -> list:
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
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw).strip()[:10])
    except ValueError:
        return None


def _safe_rate(raw) -> Optional[Decimal]:
    if raw is None or str(raw).strip() in ("", "0", "0.0000"):
        return None
    try:
        return normalize_rate(raw)
    except ValueError:
        return None


def schema_fingerprint(raw_json: str) -> str:
    try:
        data = json.loads(raw_json)
        currencies = sorted(data["data"]["rates"].keys())
        rate_keys = sorted(next(iter(data["data"]["rates"].values())).keys())
        return hashlib.sha256(str({"currencies": currencies, "rate_keys": rate_keys}).encode()).hexdigest()
    except Exception:
        return hashlib.sha256(b"awash:unparseable").hexdigest()
