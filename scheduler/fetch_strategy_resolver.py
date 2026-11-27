from adapters.transport.base import FetchKind
from infrastructure.timeout_config import get_timeout_config
from scheduler.fetch_helpers import _has_fetch_raw
from scheduler.fetch_strategies import BrowserFetchStrategy, FetchStrategy, HttpFetchStrategy, RawFetchStrategy


def resolve_fetch_strategy(adapter, adapter_key: str) -> FetchStrategy:
    fetch_kind = getattr(adapter, "fetch_kind", None)

    if fetch_kind == FetchKind.BROWSER:
        return BrowserFetchStrategy(adapter)

    if _has_fetch_raw(adapter):
        return RawFetchStrategy(adapter)

    return HttpFetchStrategy(adapter, adapter_key, get_timeout_config(adapter_key))
