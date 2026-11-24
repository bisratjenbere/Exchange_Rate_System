import hashlib
import json
from decimal import Decimal
from datetime import date
from domain.records import AdapterRecord

FINGERPRINT_VERSION = 3

def _canonical_decimal(d) -> str | None:
    if d is None:
        return None
    return format(Decimal(d).normalize(), "f")

def compute_fingerprint(record: AdapterRecord, source_id: int, collection_date: date) -> str:
    payload = {
        "v": FINGERPRINT_VERSION,
        "source_id": source_id,
        "collection_date": collection_date.isoformat(),
        "source_currency_code": record.source_currency_code,
        "category": record.category,
        "effective_date": record.effective_date.isoformat() if record.effective_date else None,
        "buying_rate": _canonical_decimal(record.buying_rate),
        "selling_rate": _canonical_decimal(record.selling_rate),
        "source_publication_key": record.source_publication_key,
        "unit_multiplier": _canonical_decimal(record.unit_multiplier),
        "quote_currency_code": record.quote_currency_code,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
