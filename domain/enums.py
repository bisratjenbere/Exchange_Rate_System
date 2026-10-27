from enum import Enum

class ValidationStatus(str, Enum):
    VALIDATED = "validated"
    WARNING = "warning"
    REJECTED = "rejected"

class IdentityStatus(str, Enum):
    CONFIRMED = "confirmed"
    DERIVED = "derived"
    AMBIGUOUS = "ambiguous"

class ChangeReviewStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING_REVIEW = "pending_review"
    CONFIRMED_CORRECTION = "confirmed_correction"
    NEW_PUBLICATION = "new_publication"
    MAPPING_ISSUE = "mapping_issue"
    DISMISSED = "dismissed"

class EffectiveDateBasis(str, Enum):
    SOURCE_PUBLISHED = "source_published"
    SOURCE_INFERRED = "source_inferred"
    COLLECTION_DATE_FALLBACK = "collection_date_fallback"
    UNKNOWN = "unknown"
