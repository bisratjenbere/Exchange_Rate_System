"""
adapters/rammis/adapter.py — Rammis Bank (Type B1).

Parse rules (ADR-006 §6, mapping doc):
- Input: JSON object with envelope {base_currency, effective_date, rates: [...]}.
- Each rate row: {id, base_currency, currency, effective_date, buying, selling, created_at}.
- One AdapterRecord per row. Category UNKNOWN — single buying/selling pair, not labeled.
- Per-row effective_date (YYYY-MM-DD) → effective_date_basis=source_published.
- source_record_key = str(id) — stable integer per currency row (TO VERIFY across fetches).
- identity_status = derived (source_published date, no stable publication ID).
- Raises ValueError if envelope is not a JSON object or rates key is missing.
"""
import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Optional

from adapters.base import JSONAdapter, ParseResult
from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "rammis_api"
SOURCE_URL = "https://rammisbank.et/api/v1/exchange-rates/latest?base_currency=ETB"


class RammisAdapter(JSONAdapter):
    """
    Rammis Bank adapter using JSONAdapter base class.
    
    Parses JSON object with envelope containing rates array.
    Emits 1 record per currency row with category UNKNOWN.
    """
    
    def get_source_url(self) -> str:
        """Return Rammis API URL."""
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        """Return unique adapter identifier."""
        return ADAPTER_KEY
    
    def _process_data(self, data, **options) -> ParseResult:
        """
        Extract AdapterRecords from parsed JSON data.
        
        Args:
            data: Parsed JSON (should be dict with rates array)
            **options: Additional options (category defaults to "UNKNOWN")
        
        Returns:
            ParseResult with records and any errors
        
        Raises:
            ValueError: If data is not a JSON object or rates key is missing
        """
        if not isinstance(data, dict):
            raise ValueError(
                f"Rammis: expected JSON object at top level, got {type(data).__name__}"
            )
        
        rates = data.get("rates")
        if rates is None:
            raise ValueError("Rammis: missing 'rates' key — schema changed")
        if not isinstance(rates, list):
            raise ValueError(f"Rammis: 'rates' must be an array, got {type(rates).__name__}")
        
        category = options.get("category", "UNKNOWN")
        
        records = []
        for row in rates:
            record = _parse_row(row, category)
            if record is not None:
                records.append(record)
        
        result = ParseResult()
        result.records = records
        return result
    
    def schema_fingerprint(self, raw_content: str) -> str:
        """
        Deterministic hash of the structural signature:
        envelope keys (excluding rates) + rate item keys.
        Triggers raw capture on schema change.
        """
        try:
            data = json.loads(raw_content)
            if isinstance(data, dict):
                env_keys = sorted(k for k in data.keys() if k != "rates")
                rate_keys = []
                rates = data.get("rates", [])
                if isinstance(rates, list) and rates and isinstance(rates[0], dict):
                    rate_keys = sorted(rates[0].keys())
                payload = json.dumps({"env": env_keys, "rate": rate_keys}, separators=(",", ":"))
                return hashlib.sha256(payload.encode()).hexdigest()
        except Exception:
            pass
        return hashlib.sha256(b"rammis:empty_or_unparseable").hexdigest()


# ── Backward Compatibility Wrappers ──────────────────────────────────────────

def parse(raw_json: str, category: str = "UNKNOWN") -> list:
    """
    Parse the raw API JSON into AdapterRecords.
    
    BACKWARD COMPATIBILITY WRAPPER: New code should use RammisAdapter().parse()
    
    Args:
        raw_json: Raw JSON string from API
        category: Category value (defaults to "UNKNOWN")
    
    Raises:
        ValueError: If parsing fails or schema is invalid
    
    Returns:
        List of AdapterRecord objects
    """
    adapter = RammisAdapter()
    result = adapter.parse(raw_json, category=category)
    
    # Old API raised ValueError on errors, new API returns ParseResult with errors
    # Convert back to old behavior for backward compatibility
    if result.errors:
        raise ValueError(result.errors[0])
    
    return result.records


def _parse_row(row: dict, category: str = "UNKNOWN") -> Optional[AdapterRecord]:
    """Parse one rate row into AdapterRecord."""
    if not isinstance(row, dict):
        return None

    currency = str(row.get("currency", "")).strip()
    if not currency:
        return None

    row_id = row.get("id")
    effective_date = _parse_date(row.get("effective_date", ""))
    date_basis = "source_published" if effective_date else "collection_date_fallback"

    buying = _safe_rate(row.get("buying"))
    selling = _safe_rate(row.get("selling"))
    if buying is None and selling is None:
        return None

    return AdapterRecord(
        source_currency_code=currency,
        category=category,
        buying_rate=buying,
        selling_rate=selling,
        source_rate_text=f"{row.get('buying')}/{row.get('selling')}",
        effective_date=effective_date,
        effective_date_basis=date_basis,
        source_record_key=str(row_id) if row_id is not None else None,
        source_publication_key=None,
        quote_currency_code=None,  # base_currency=ETB implied
        unit_multiplier=1,
        raw_excerpt={
            "id": row_id,
            "currency": currency,
            "effective_date": row.get("effective_date"),
            "buying": row.get("buying"),
            "selling": row.get("selling"),
        },
        mapping_notes=["category_unknown:single_pair_unverified", "id_stability:TO_VERIFY"],
    )


def _safe_rate(raw) -> Optional[Decimal]:
    """Safely convert raw value to normalized Decimal rate."""
    try:
        return normalize_rate(raw)
    except ValueError:
        return None


def _parse_date(date_str: str) -> Optional[date]:
    """Parse YYYY-MM-DD date string. Returns None if unparseable."""
    try:
        return date.fromisoformat(str(date_str).strip())
    except (ValueError, AttributeError):
        return None


def schema_fingerprint(raw_json: str) -> str:
    """
    Deterministic hash of the structural signature.
    
    BACKWARD COMPATIBILITY WRAPPER: New code should use RammisAdapter().schema_fingerprint()
    """
    return RammisAdapter().schema_fingerprint(raw_json)
