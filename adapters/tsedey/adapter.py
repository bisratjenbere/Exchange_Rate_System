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

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "tsedey_html"
SOURCE_URL = "https://www.tsedeybank.com.et/"

_RECORD_RE = re.compile(r'\{"id":\d+,"name":"[^"]+","code":"[A-Z]{3}"[^}]+\}')


def parse(raw_html: str) -> tuple:
    records, errors = [], []
    seen = set()

    for m in _RECORD_RE.finditer(raw_html):
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

            effective_date = _parse_date(row.get("updated_at"))
            date_basis = "source_inferred" if effective_date else "collection_date_fallback"

            buying = _safe_rate(row.get("buying_rate"))
            selling = _safe_rate(row.get("selling_rate"))
            if buying is not None or selling is not None:
                records.append(_make(code, category, buying, selling,
                                     row.get("buying_rate"), row.get("selling_rate"),
                                     effective_date, date_basis, row))

            # weighted average
            w_buy = _safe_rate(row.get("weighted_average_buying"))
            w_sell = _safe_rate(row.get("weighted_average_selling"))
            w_key = f"{code}:weighted_average"
            if (w_buy is not None or w_sell is not None) and w_key not in seen:
                seen.add(w_key)
                records.append(_make(code, "weighted_average", w_buy, w_sell,
                                     row.get("weighted_average_buying"),
                                     row.get("weighted_average_selling"),
                                     effective_date, date_basis, row))
        except Exception as exc:
            errors.append(f"record:{m.group()[:40]}:{exc}")

    return records, errors


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
        raw_excerpt={"currency": code, "buying": buy_text, "selling": sell_text,
                     "category": row.get("category"), "updated_at": row.get("updated_at")},
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
    if not raw or str(raw).upper() in ("NO TRADE", "N/A", ""):
        return None
    try:
        return normalize_rate(raw)
    except ValueError:
        return None


def schema_fingerprint(raw_html: str) -> str:
    try:
        matches = _RECORD_RE.findall(raw_html)
        if matches:
            first = json.loads(matches[0])
            keys = sorted(first.keys())
            return hashlib.sha256(str({"keys": keys, "count": len(matches)}).encode()).hexdigest()
    except Exception:
        pass
    return hashlib.sha256(b"tsedey:unparseable").hexdigest()
