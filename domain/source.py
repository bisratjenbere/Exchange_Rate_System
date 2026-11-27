from __future__ import annotations
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class RateSource:
    id: int
    adapter_key: str
    source_url: str
    ssl_verify: bool
    is_enabled: bool
    schema_fingerprint: Optional[str] = None
    default_category: Optional[str] = None
    consecutive_failures: int = 0
    last_failure_code: Optional[str] = None
    last_failure_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    adapter_config: Optional[dict] = None

    def __getitem__(self, key: str):
        return getattr(self, key)

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and hasattr(self, key)

    def get(self, key: str, default=None):
        return getattr(self, key, default)

    def with_schema_fingerprint(self, fingerprint: str) -> RateSource:
        return replace(self, schema_fingerprint=fingerprint)
