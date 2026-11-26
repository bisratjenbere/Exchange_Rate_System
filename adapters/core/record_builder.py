"""
RecordBuilder - ONE place to construct AdapterRecord.

Centralizes effective_date logic and field mapping.
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from domain.records import AdapterRecord
from adapters.core.contract import ParseContext


def build_record(
    currency_code: str,
    category: str,
    buying_rate: Optional[Decimal],
    selling_rate: Optional[Decimal],
    ctx: ParseContext,
    effective_date: Optional[date] = None,
    effective_date_basis: Optional[str] = None,
    currency_name: Optional[str] = None,
    source_rate_text: Optional[str] = None,
    per_units: int = 1,
    mapping_notes: list = None,
) -> AdapterRecord:
    """
    Build AdapterRecord with consistent field mapping.
    
    Args:
        currency_code: ISO 4217 code (e.g., "USD")
        category: "cash", "transactional", "weighted", etc.
        buying_rate: Bank buys foreign currency (customer sells)
        selling_rate: Bank sells foreign currency (customer buys)
        ctx: Parse context (source_id, collection_date)
        effective_date: When rates became effective (from bank data)
        effective_date_basis: How date was determined
        currency_name: Full name (e.g., "US Dollar")
        source_rate_text: Original rate text for debugging
        per_units: Unit multiplier (1 for most, 100 for JPY/KRW)
        mapping_notes: List of notes for debugging
    
    Returns:
        AdapterRecord: Populated record
    
    Effective date logic:
    - If effective_date provided by adapter: use it, basis = "source_published"
    - Else: use ctx.collection_date, basis = "collection_date_fallback"
    """
    # Effective date fallback
    if effective_date is None:
        effective_date = ctx.collection_date
        effective_date_basis = "collection_date_fallback"
    elif effective_date_basis is None:
        effective_date_basis = "source_published"
    
    # Build record
    return AdapterRecord(
        source_currency_code=currency_code,
        quote_currency_code="ETB",  # Always ETB for Ethiopian banks
        category=category,
        buying_rate=buying_rate,
        selling_rate=selling_rate,
        effective_date=effective_date,
        effective_date_basis=effective_date_basis,
        currency_name=currency_name,
        source_rate_text=source_rate_text,
        unit_multiplier=per_units,
        source_record_key=None,  # Set by adapter if available
        source_publication_key=None,
        raw_excerpt=None,
        mapping_notes=mapping_notes or [],
    )
