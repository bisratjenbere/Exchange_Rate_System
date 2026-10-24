"""
pipeline/fingerprint.py — deterministic SHA-256 fingerprint of an AdapterRecord.
Includes collection_date for daily snapshot tracking.
Gap review §4: carries fingerprint_version so mapping changes don't flood the review queue.
"""
import hashlib
import json
from decimal import Decimal
from datetime import date, datetime
from domain.records import AdapterRecord

FINGERPRINT_VERSION = 2  # Incremented for daily snapshot change


def compute_fingerprint(record: AdapterRecord, source_id: int, collection_date: date = None) -> str:
    """
    Return a 64-char hex SHA-256 fingerprint.
    Inputs: source_id, source_currency_code, category, effective_date,
            buying_rate, selling_rate, source_publication_key, collection_date.
    
    The collection_date parameter enables daily snapshots: even if rate values
    don't change, we create a new observation for each calendar day.
    This supports "track all day rate" use case.
    
    Args:
        record: The adapter record to fingerprint
        source_id: The rate source ID
        collection_date: The date of collection (YYYY-MM-DD). If None, uses today.
    """
    if collection_date is None:
        collection_date = datetime.now().date()
    
    payload = {
        "v": FINGERPRINT_VERSION,
        "source_id": source_id,
        "collection_date": collection_date.isoformat(),  # NEW: Daily uniqueness
        "source_currency_code": record.source_currency_code,
        "category": record.category,
        "effective_date": record.effective_date.isoformat() if record.effective_date else None,
        "buying_rate": str(record.buying_rate) if record.buying_rate is not None else None,
        "selling_rate": str(record.selling_rate) if record.selling_rate is not None else None,
        "source_publication_key": record.source_publication_key,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
