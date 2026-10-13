"""
pipeline/identity.py — build logical_observation_key and determine identity_status.
LOCKED rules:
- Fallback dates never participate in identity (gap review §5).
- Ambiguous identity is retained and flagged, never invented.
- Identity hierarchy: stable source ID > source_published date > derived > ambiguous.
- collection_date_fallback: use fetched_at date as derived effective_date so records
  get is_current=TRUE. Banks that don't publish dates still produce usable daily rates.
"""
from datetime import date as date_type
from typing import Optional
from domain.records import AdapterRecord
from domain.enums import IdentityStatus


def build_identity(record: AdapterRecord, source_id: int,
                   fetched_date: Optional[date_type] = None) -> tuple:
    """
    Returns (logical_observation_key: str | None, identity_status: IdentityStatus).

    Key structure (when identifiable):
        "<source_id>:<source_currency_code>:<category>:<effective_date>"
    or with stable source record key:
        "<source_id>:<source_record_key>:<category>"

    Fallback dates (collection_date_fallback / unknown) never enter the key.
    """
    currency = record.source_currency_code
    category = record.category

    # Strongest: stable source record key + source-published date
    # A row id alone (without a source-published date) is not a publication discriminator.
    if (record.source_record_key
            and record.effective_date is not None
            and record.effective_date_basis in ("source_published", "source_inferred")):
        key = f"{source_id}:{record.source_record_key}:{category}"
        return key, IdentityStatus.CONFIRMED

    # Strong: source-published date
    if (record.effective_date is not None
            and record.effective_date_basis == "source_published"):
        key = f"{source_id}:{currency}:{category}:{record.effective_date.isoformat()}"
        return key, IdentityStatus.CONFIRMED

    # Medium: source-inferred date
    if (record.effective_date is not None
            and record.effective_date_basis == "source_inferred"):
        key = f"{source_id}:{currency}:{category}:{record.effective_date.isoformat()}"
        return key, IdentityStatus.DERIVED

    # Weak-but-usable: collection_date_fallback with a known fetched_date
    # Use fetched_at date as derived effective_date — bank publishes daily but omits date stamp.
    if (record.effective_date_basis == "collection_date_fallback"
            and fetched_date is not None):
        key = f"{source_id}:{currency}:{category}:{fetched_date.isoformat()}"
        return key, IdentityStatus.DERIVED

    # No date at all — ambiguous, key is None
    return None, IdentityStatus.AMBIGUOUS
