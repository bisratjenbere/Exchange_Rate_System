"""
adapters/tsedey/adapter.py — Tsedey Bank (JSON embedded in HTML).

Parse rules:
- Page HTML contains inline JSON records matching:
  {"id":N,"name":"...","code":"USD","category":"non-cash"|"cash",
   "buying_rate":"161.72","selling_rate":"164.95",
   "weighted_average_buying":"...","weighted_average_selling":"...",
   "updated_at":"2026-10-13T05:25:13.000000Z",...}
- category "non-cash" → transactional
- category "cash"     → cash
- weighted_average_buying/selling emitted as weighted_average if non-null and not "NO TRADE"
- updated_at date part → source_inferred effective_date
- Partial failure: returns (records, errors). Never raises.
"""
import hashlib
import json
import re
from datetime import date
from decimal import Decimal
from typing import Optional

from bs4 import BeautifulSoup

from adapters.base import BankAdapter, ParseResult
from domain.records import AdapterRecord

ADAPTER_KEY = "tsedey_html"
SOURCE_URL = "https://www.tsedeybank.com.et/"

_RECORD_RE = re.compile(r'\{"id":\d+,"name":"[^"]+","code":"[A-Z]{3}"[^}]+\}')


# ============================================================================
# ADAPTER CLASS
# ============================================================================

class TsedeyAdapter(BankAdapter):
    """Tsedey Bank adapter - JSON records embedded in HTML."""
    
    def get_source_url(self) -> str:
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        return ADAPTER_KEY
    
    def parse(self, raw_content: str, **options) -> ParseResult:
        """
        Extract JSON records from HTML using regex.
        Custom implementation that doesn't use HTMLTableAdapter or JSONAdapter.
        """
        result = ParseResult()
        seen = set()
        
        for m in _RECORD_RE.finditer(raw_content):
            try:
                row = json.loads(m.group())
                code = str(row.get("code", "")).strip()
                category_raw = str(row.get("category", "")).lower()
                category = "transactional" if category_raw == "non-cash" else "cash" if category_raw == "cash" else None
                if not code or not category:
                    continue
                
                dedup_key = f"{code}:{category}"
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                
                effective_date = self._parse_iso_date(row.get("updated_at", ""))
                date_basis = "source_inferred" if effective_date else "collection_date_fallback"
                
                buying = self._safe_rate(row.get("buying_rate"))
                selling = self._safe_rate(row.get("selling_rate"))
                if buying is not None or selling is not None:
                    result.records.append(_make_record(
                        code, category, buying, selling,
                        row.get("buying_rate"), row.get("selling_rate"),
                        effective_date, date_basis, row
                    ))
                
                # weighted average
                w_buy = self._safe_rate(row.get("weighted_average_buying"))
                w_sell = self._safe_rate(row.get("weighted_average_selling"))
                w_key = f"{code}:weighted_average"
                if (w_buy is not None or w_sell is not None) and w_key not in seen:
                    seen.add(w_key)
                    result.records.append(_make_record(
                        code, "weighted_average", w_buy, w_sell,
                        row.get("weighted_average_buying"),
                        row.get("weighted_average_selling"),
                        effective_date, date_basis, row
                    ))
            except Exception as exc:
                result.add_error(f"record:{m.group()[:40]}:{exc}")
        
        return result
    
    def schema_fingerprint(self, raw_content: str) -> str:
        """Hash first record keys and count."""
        try:
            matches = _RECORD_RE.findall(raw_content)
            if matches:
                first = json.loads(matches[0])
                keys = sorted(first.keys())
                return hashlib.sha256(str({"keys": keys, "count": len(matches)}).encode()).hexdigest()
        except Exception:
            pass
        return hashlib.sha256(b"tsedey:unparseable").hexdigest()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _make_record(code, category, buying, selling, buy_text, sell_text, eff_date, date_basis, row):
    """Helper to create AdapterRecord."""
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
        raw_excerpt={"currency": code, "buying": buy_text, "selling": sell_text,
                     "category": row.get("category"), "updated_at": row.get("updated_at")},
        mapping_notes=[],
    )


# ============================================================================
# MODULE-LEVEL FUNCTIONS (backward compatibility)
# ============================================================================

_adapter = TsedeyAdapter()


def parse(raw_html: str) -> tuple:
    """
    Parse HTML with embedded JSON records.
    Backward-compatible wrapper that returns (records, errors) tuple.
    """
    result = _adapter.parse(raw_html)
    return result.records, result.errors


def schema_fingerprint(raw_html: str) -> str:
    """Hash first record keys and count."""
    return _adapter.schema_fingerprint(raw_html)
