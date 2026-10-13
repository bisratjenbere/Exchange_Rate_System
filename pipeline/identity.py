"""
pipeline/identity.py — build logical_observation_key and determine identity_status.
LOCKED rules:
- Fallback dates never participate in identity (gap review §5).
- Ambiguous identity is retained and flagged, never invented.
- Identity hierarchy: stable source ID > source_published date > derived > ambiguous.
"""
from typing import Optional
from domain.records import AdapterRecord
from domain.enums import IdentityStatus


def build_identity(record: AdapterRecord, source_id: int) -> tuple:
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

    # Weak: fallback date or no date — ambiguous, key is None
    # Gap review §5: fallback dates never participate in identity
    return None, IdentityStatus.AMBIGUOUS
