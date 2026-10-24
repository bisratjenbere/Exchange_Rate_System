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

MIGRATION NOTE: Migrated to FieldStructureMixin for automatic category detection.
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
from field_detection.mixin import FieldStructureMixin
from pipeline.category_normalizer import normalize_category

ADAPTER_KEY = "tsedey_html"
SOURCE_URL = "https://www.tsedeybank.com.et/"

_RECORD_RE = re.compile(r'\{"id":\d+,"name":"[^"]+","code":"[A-Z]{3}"[^}]+\}')


# ============================================================================
# ADAPTER CLASS
# ============================================================================

class TsedeyAdapter(FieldStructureMixin, BankAdapter):
    """
    Tsedey Bank adapter - JSON records embedded in HTML.
    
    Uses field detection for automatic category discovery from JSON fields.
    """
    
    FIELD_CONFIG = {}
    
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
                category = normalize_category(category_raw)
                if not code or category == "UNKNOWN":
                    continue
                
                dedup_key = f"{code}:{category}"
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                
                # Parse ISO 8601 timestamp (extract date part only)
                updated_at_str = row.get("updated_at", "")
                effective_date = None
                if updated_at_str:
                    try:
                        # Extract YYYY-MM-DD from "2026-10-22T05:28:32.000000Z"
                        effective_date = self._parse_iso_date(updated_at_str.split("T")[0])
                    except (AttributeError, IndexError):
                        pass
                date_basis = "source_inferred" if effective_date else "collection_date_fallback"
                
                # Create dict with generic field names for main rates
                row_dict = {
                    "buying_rate": row.get("buying_rate"),
                    "selling_rate": row.get("selling_rate"),
                }
                
                # Use field detection
                detected_records = self.detect_and_emit(
                    data=row_dict,
                    currency=code,
                    effective_date=effective_date,
                    effective_date_basis=date_basis,
                    source_record_id=str(row.get("id")) if row.get("id") else None
                )
                
                # Context-based category override: JSON explicitly provides category
                for rec in detected_records:
                    if rec.category == 'UNKNOWN':
                        rec.category = normalize_category(category_raw)
                    rec.raw_excerpt = {"currency": code, "buying": row.get("buying_rate"), 
                                       "selling": row.get("selling_rate"), "category": row.get("category"), 
                                       "updated_at": row.get("updated_at")}
                
                result.records.extend(detected_records)
                
                # weighted average
                w_buy_text = row.get("weighted_average_buying")
                w_sell_text = row.get("weighted_average_selling")
                w_key = f"{code}:weighted_average"
                if (w_buy_text and w_sell_text) and w_key not in seen:
                    seen.add(w_key)
                    
                    row_dict_weighted = {
                        "weighted_average_buying": w_buy_text,
                        "weighted_average_selling": w_sell_text,
                    }
                    
                    detected_weighted = self.detect_and_emit(
                        data=row_dict_weighted,
                        currency=code,
                        effective_date=effective_date,
                        effective_date_basis=date_basis,
                        source_record_id=str(row.get("id")) if row.get("id") else None
                    )
                    
                    # Override to weighted_average category
                    for rec in detected_weighted:
                        rec.category = "weighted_average"
                        rec.raw_excerpt = {"currency": code, "buying": w_buy_text, 
                                           "selling": w_sell_text, "category": "weighted_average"}
                    
                    result.records.extend(detected_weighted)
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
