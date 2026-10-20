"""
adapters/adib/adapter.py — Addis International Bank (Type B2).

Parse rules (ADR-006 §6, mapping doc, ADR-013):
- Input: flat JSON array, one wide row per currency.
- Skip ETB row (id=1) — quote currency.
- Skip plain buying/selling — category unconfirmed (TO VERIFY).
- Emit transactional record from transactionBuying/transactionSelling.
- Emit weighted_average record from weightedBuying/weightedSelling.
- "0.0000" and null → None (not offered).
- If both sides of a category are None → skip that record (no valid observation).
- ADR-013: updatedAt (date part only) → effective_date, basis=source_inferred → identity=derived.
- source_record_key = str(id) — row number, KNOWN not VERIFIED.

No network calls in parse(). fetch() is a thin wrapper kept separate.
"""
import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Optional

from adapters.base import JSONAdapter, ParseResult
from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "adib_api"
SOURCE_URL = "https://api.addisbanksc.com/api/exchange-rates"
ETB_ROW_ID = 1  # quote currency row — always skip


class ADIBAdapter(JSONAdapter):
    """
    Addis International Bank adapter using JSONAdapter base class.
    
    Parses JSON array with wide rows containing multiple rate categories.
    Emits 0-2 records per currency row (transactional + weighted_average).
    """
    
    def get_source_url(self) -> str:
        """Return ADIB API URL."""
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        """Return unique adapter identifier."""
        return ADAPTER_KEY
    
    def _process_data(self, data, **options) -> ParseResult:
        """
        Extract AdapterRecords from parsed JSON data.
        
        Args:
            data: Parsed JSON (should be list of currency rows)
            **options: Additional options (unused)
        
        Returns:
            ParseResult with records and any errors
        
        Raises:
            ValueError: If data is not a JSON array
        """
        if not isinstance(data, list):
            raise ValueError(
                f"ADIB: expected JSON array at top level, got {type(data).__name__}"
            )
        
        records = []
        for row in data:
            records.extend(_parse_row(row))
        
        result = ParseResult()
        result.records = records
        return result
    
    def schema_fingerprint(self, raw_content: str) -> str:
        """
        Deterministic hash of the structural signature (field names of first non-ETB row).
        Triggers raw capture on schema change.
        """
        try:
            data = json.loads(raw_content)
            if isinstance(data, list):
                for row in data:
                    if isinstance(row, dict) and row.get("id") != ETB_ROW_ID:
                        keys = sorted(row.keys())
                        payload = json.dumps(keys, separators=(",", ":"))
                        return hashlib.sha256(payload.encode()).hexdigest()
        except Exception:
            pass
        return hashlib.sha256(b"adib:empty_or_unparseable").hexdigest()


# ── Backward Compatibility Wrappers ──────────────────────────────────────────

def parse(raw_json: str) -> list:
    """
    Parse the raw JSON response string into a list of AdapterRecord.
    
    BACKWARD COMPATIBILITY WRAPPER: New code should use ADIBAdapter().parse()
    
    Raises ValueError if the top-level structure is not a JSON array.
    Returns an empty list for an empty array.
    """
    adapter = ADIBAdapter()
    result = adapter.parse(raw_json)
    
    # Old API raised ValueError on errors, new API returns ParseResult with errors
    # Convert back to old behavior for backward compatibility
    if result.errors:
        raise ValueError(result.errors[0])
    
    return result.records


def _parse_row(row: dict) -> list:
    """Convert one source row into 0–2 AdapterRecords."""
    if not isinstance(row, dict):
        return []

    row_id = row.get("id")
    if row_id == ETB_ROW_ID:
        return []  # quote currency — skip

    currency = str(row.get("currency", "")).strip()
    if not currency:
        return []

    # ADR-013: updatedAt date part → source_inferred effective_date
    effective_date = _parse_updated_at(row.get("updatedAt"))
    date_basis = "source_inferred" if effective_date else "collection_date_fallback"

    records = []

    # ── transactional ─────────────────────────────────────────────────────────
    txn_buy = _safe_rate(row.get("transactionBuying"))
    txn_sell = _safe_rate(row.get("transactionSelling"))
    if txn_buy is not None or txn_sell is not None:
        records.append(AdapterRecord(
            source_currency_code=currency,
            category="transactional",
            buying_rate=txn_buy,
            selling_rate=txn_sell,
            source_rate_text=_rate_text(row.get("transactionBuying"), row.get("transactionSelling")),
            effective_date=effective_date,
            effective_date_basis=date_basis,
            source_record_key=str(row_id) if row_id is not None else None,
            raw_excerpt={
                "id": row_id,
                "currency": currency,
                "transactionBuying": row.get("transactionBuying"),
                "transactionSelling": row.get("transactionSelling"),
                "updatedAt": row.get("updatedAt"),
            },
            mapping_notes=["plain_buying_selling_skipped:category_unconfirmed",
                           "updatedAt_as_source_inferred:ADR-013"],
        ))

    # ── weighted_average ──────────────────────────────────────────────────────
    w_buy = _safe_rate(row.get("weightedBuying"))
    w_sell = _safe_rate(row.get("weightedSelling"))
    if w_buy is not None or w_sell is not None:
        records.append(AdapterRecord(
            source_currency_code=currency,
            category="weighted_average",
            buying_rate=w_buy,
            selling_rate=w_sell,
            source_rate_text=_rate_text(row.get("weightedBuying"), row.get("weightedSelling")),
            effective_date=effective_date,
            effective_date_basis=date_basis,
            source_record_key=str(row_id) if row_id is not None else None,
            raw_excerpt={
                "id": row_id,
                "currency": currency,
                "weightedBuying": row.get("weightedBuying"),
                "weightedSelling": row.get("weightedSelling"),
                "updatedAt": row.get("updatedAt"),
            },
            mapping_notes=["plain_buying_selling_skipped:category_unconfirmed",
                           "updatedAt_as_source_inferred:ADR-013"],
        ))

    return records


def _parse_updated_at(raw: Optional[str]) -> Optional[date]:
    """
    Parse updatedAt ISO timestamp to date (date part only, per ADR-013).
    e.g. "2026-09-30T07:09:31.000Z" → date(2026, 9, 30)
    """
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw).strip()[:10])
    except (ValueError, AttributeError):
        return None


def _safe_rate(raw) -> Optional[Decimal]:
    """Return None for sentinel values; return Decimal for valid rates; return None on error."""
    try:
        return normalize_rate(raw)
    except ValueError:
        return None


def _rate_text(buying, selling) -> str:
    return f"{buying}/{selling}"


def schema_fingerprint(raw_json: str) -> str:
    """
    Deterministic hash of the structural signature.
    
    BACKWARD COMPATIBILITY WRAPPER: New code should use ADIBAdapter().schema_fingerprint()
    """
    return ADIBAdapter().schema_fingerprint(raw_json)
