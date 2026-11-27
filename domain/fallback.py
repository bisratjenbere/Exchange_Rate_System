from __future__ import annotations
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class FallbackPolicy(Protocol):
    def attempt(
        self,
        conn,
        source_id: int,
        adapter_key: str,
        user_agent: str,
    ) -> Optional[dict]:
        ...

    @property
    def adapter_name(self) -> str:
        ...
