from typing import Optional
from db.repositories.rate_observation_repository import RateObservationRepository


def classify_observation(
    fingerprint: str,
    logical_key: Optional[str],
    conn,
) -> tuple:
    repo = RateObservationRepository(conn)

    existing_id = repo.find_by_fingerprint(fingerprint)
    if existing_id is not None:
        return "duplicate", existing_id

    if logical_key is None:
        return "new", None

    current_id = repo.find_current_by_logical_key(logical_key)
    if current_id is not None:
        return "changed", current_id

    return "new", None


def classify_ambiguous_observation(
    fingerprint: str,
    source_id: int,
    source_currency_code: str,
    category: str,
    conn,
) -> tuple:
    repo = RateObservationRepository(conn)
    existing_id = repo.find_by_fingerprint_and_source(
        fingerprint, source_id, source_currency_code
    )
    if existing_id is not None:
        return "duplicate", existing_id
    return "new", None
