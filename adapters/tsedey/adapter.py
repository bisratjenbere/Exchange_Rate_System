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

class TsedeyAdapter(FieldStructureMixin, BankAdapter):

    FIELD_CONFIG = {}

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def parse(self, raw_content: str, **options) -> ParseResult:
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

                updated_at_str = row.get("updated_at", "")
                effective_date = None
                if updated_at_str:
                    try:
                        effective_date = self._parse_iso_date(updated_at_str.split("T")[0])
                    except (AttributeError, IndexError):
                        pass
                date_basis = "source_inferred" if effective_date else "collection_date_fallback"

                row_dict = {
                    "buying_rate": row.get("buying_rate"),
                    "selling_rate": row.get("selling_rate"),
                }

                detected_records = self.detect_and_emit(
                    data=row_dict,
                    currency=code,
                    effective_date=effective_date,
                    effective_date_basis=date_basis,
                    source_record_id=str(row.get("id")) if row.get("id") else None
                )

                for rec in detected_records:
                    if rec.category == 'UNKNOWN':
                        rec.category = normalize_category(category_raw)
                    rec.raw_excerpt = {"currency": code, "buying": row.get("buying_rate"),
                                       "selling": row.get("selling_rate"), "category": row.get("category"),
                                       "updated_at": row.get("updated_at")}

                result.records.extend(detected_records)

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

                    for rec in detected_weighted:
                        rec.raw_excerpt = {"currency": code, "buying": w_buy_text,
                                           "selling": w_sell_text, "category": rec.category}

                    result.records.extend(detected_weighted)
            except Exception as exc:
                result.add_error(f"record:{m.group()[:40]}:{exc}")

        return result

    def schema_fingerprint(self, raw_content: str) -> str:
        try:
            matches = _RECORD_RE.findall(raw_content)
            if matches:
                first = json.loads(matches[0])
                keys = sorted(first.keys())
                return hashlib.sha256(str({"keys": keys, "count": len(matches)}).encode()).hexdigest()
        except Exception:
            pass
        return hashlib.sha256(b"tsedey:unparseable").hexdigest()

def _make_record(code, category, buying, selling, buy_text, sell_text, eff_date, date_basis, row):
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

_adapter = TsedeyAdapter()

def parse(raw_html: str) -> tuple:
    result = _adapter.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    return _adapter.schema_fingerprint(raw_html)
