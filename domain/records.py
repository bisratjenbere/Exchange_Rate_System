from dataclasses import dataclass, field
from decimal import Decimal
from datetime import date
from typing import Optional

UNKNOWN_CATEGORY = "UNKNOWN"
VALID_CATEGORIES = frozenset(
    {"cash", "transactional", "weighted_average", "indicative_reference", UNKNOWN_CATEGORY}
)
VALID_DATE_BASES = frozenset(
    {"source_published", "source_inferred", "collection_date_fallback", "unknown"}
)

@dataclass
class AdapterRecord:
    source_currency_code: str
    effective_date_basis: str
    category: str
    currency_name: Optional[str] = None
    buying_rate: Optional[Decimal] = None
    selling_rate: Optional[Decimal] = None
    source_rate_text: Optional[str] = None
    effective_date: Optional[date] = None
    source_record_key: Optional[str] = None
    source_publication_key: Optional[str] = None
    quote_currency_code: Optional[str] = None
    unit_multiplier: int = 1
    raw_excerpt: Optional[dict] = None
    mapping_notes: list = field(default_factory=list)
