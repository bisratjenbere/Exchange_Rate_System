from datetime import date as date_type
from typing import Optional
from domain.records import AdapterRecord
from domain.enums import IdentityStatus

def build_identity(record: AdapterRecord, source_id: int,
                   fetched_date: Optional[date_type] = None) -> tuple:
    currency = record.source_currency_code
    category = record.category

    if (record.source_record_key
            and record.effective_date is not None
            and record.effective_date_basis in ("source_published", "source_inferred")):
        key = f"{source_id}:{record.source_record_key}:{category}"
        return key, IdentityStatus.CONFIRMED

    if (record.effective_date is not None
            and record.effective_date_basis == "source_published"):
        key = f"{source_id}:{currency}:{category}:{record.effective_date.isoformat()}"
        return key, IdentityStatus.CONFIRMED

    if (record.effective_date is not None
            and record.effective_date_basis == "source_inferred"):
        key = f"{source_id}:{currency}:{category}:{record.effective_date.isoformat()}"
        return key, IdentityStatus.DERIVED

    if (record.effective_date_basis == "collection_date_fallback"
            and fetched_date is not None):
        key = f"{source_id}:{currency}:{category}:{fetched_date.isoformat()}"
        return key, IdentityStatus.DERIVED

    return None, IdentityStatus.AMBIGUOUS
