import hashlib
import json
from decimal import Decimal
from datetime import date, datetime
from domain.records import AdapterRecord

FINGERPRINT_VERSION = 2

def compute_fingerprint(record: AdapterRecord, source_id: int, collection_date: date = None) -> str:
    if collection_date is None:
        collection_date = datetime.now().date()

    payload = {
        "v": FINGERPRINT_VERSION,
        "source_id": source_id,
        "collection_date": collection_date.isoformat(),
        "source_currency_code": record.source_currency_code,
        "category": record.category,
        "effective_date": record.effective_date.isoformat() if record.effective_date else None,
        "buying_rate": str(record.buying_rate) if record.buying_rate is not None else None,
        "selling_rate": str(record.selling_rate) if record.selling_rate is not None else None,
        "source_publication_key": record.source_publication_key,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
