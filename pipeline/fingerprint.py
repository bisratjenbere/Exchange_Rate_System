"""
pipeline/fingerprint.py — deterministic SHA-256 fingerprint of an AdapterRecord.
Excludes fetched_at (LOCKED rule).
Gap review §4: carries fingerprint_version so mapping changes don't flood the review queue.
"""
import hashlib
import json
from decimal import Decimal
from datetime import date
from domain.records import AdapterRecord

FINGERPRINT_VERSION = 1


def compute_fingerprint(record: AdapterRecord, source_id: int) -> str:
    """
    Return a 64-char hex SHA-256 fingerprint.
    Inputs: source_id, source_currency_code, category, effective_date,
            buying_rate, selling_rate, source_publication_key.
    fetched_at is intentionally excluded.
    """
    payload = {
        "v": FINGERPRINT_VERSION,
        "source_id": source_id,
        "source_currency_code": record.source_currency_code,
        "category": record.category,
        "effective_date": record.effective_date.isoformat() if record.effective_date else None,
        "buying_rate": str(record.buying_rate) if record.buying_rate is not None else None,
        "selling_rate": str(record.selling_rate) if record.selling_rate is not None else None,
        "source_publication_key": record.source_publication_key,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
