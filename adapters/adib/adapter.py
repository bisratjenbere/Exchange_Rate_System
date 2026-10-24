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

MIGRATION NOTE: Migrated to use FieldStructureMixin for automatic category detection.
Field pattern: Prefix-based (transactionBuying/Selling, weightedBuying/Selling).

No network calls in parse(). fetch() is a thin wrapper kept separate.
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

ADAPTER_KEY = "adib_api"
SOURCE_URL = "https://api.addisbanksc.com/api/exchange-rates"
ETB_ROW_ID = 1  # quote currency row — always skip


class ADIBAdapter(FieldStructureMixin, JSONAdapter):
    """
    Addis International Bank adapter using JSONAdapter base class with field detection.
    
    Parses JSON array with wide rows containing multiple rate categories.
    Uses FieldStructureMixin to automatically detect and emit records based on field structure.
    
    Field Structure: Suffix-based pattern (e.g., transactionBuying, weightedSelling, etc.)
    The detector automatically discovers ANY category with Buying/Selling suffixes,
    making the adapter future-proof if the bank adds new categories.
    
    Known categories: transactional, weighted_average
    Future categories: Will be detected automatically if they follow the pattern
    """
    
    # Empty config - let field detector discover all categories automatically
    # This makes the adapter resilient to new categories (e.g., if bank adds cashBuying/cashSelling)
    FIELD_CONFIG = {}
    
    def get_source_url(self) -> str:
        """Return ADIB API URL."""
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        """Return unique adapter identifier."""
        return ADAPTER_KEY
    
    def _process_data(self, data, **options) -> ParseResult:
        """
        Extract AdapterRecords from parsed JSON data using field detection.
        
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
        
        result = ParseResult()
        
        for row in data:
            # Skip ETB row (quote currency)
            if not isinstance(row, dict) or row.get("id") == ETB_ROW_ID:
                continue
            
            currency = str(row.get("currency", "")).strip()
            if not currency:
                continue
            
            # ADR-013: updatedAt date part → source_inferred effective_date
            effective_date = _parse_updated_at(row.get("updatedAt"))
            date_basis = "source_inferred" if effective_date else "collection_date_fallback"
            
            # Use field detection to automatically emit records based on field structure
            detected_records = self.detect_and_emit(
                data=row,
                currency=currency,
                source_record_id=str(row.get("id")) if row.get("id") is not None else None,
                effective_date=effective_date,
                effective_date_basis=date_basis,
                mapping_notes=[
                    "plain_buying_selling_skipped:category_unconfirmed",
                    "updatedAt_as_source_inferred:ADR-013"
                ]
            )
            
            # Filter out UNKNOWN categories (plain buying/selling - category unconfirmed per ADR-006)
            # These are detected but skipped per original adapter behavior
            confirmed_records = [r for r in detected_records if r.category != 'UNKNOWN']
            result.records.extend(confirmed_records)
            
            # Log if we skipped any UNKNOWN records (for observability)
            skipped = len(detected_records) - len(confirmed_records)
            if skipped > 0:
                result.add_warning(f"{currency}: skipped {skipped} UNKNOWN category record(s)")
        
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
