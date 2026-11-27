from __future__ import annotations
from typing import Protocol, runtime_checkable


@runtime_checkable
class FetchStrategy(Protocol):
    def fetch(self, url: str, ssl_verify: bool, user_agent: str) -> tuple[str, int]:
        ...


class BrowserFetchStrategy:
    def __init__(self, adapter):
        self._adapter = adapter

    def fetch(self, url: str, ssl_verify: bool, user_agent: str) -> tuple[str, int]:
        from scheduler.fetch_helpers import _fetch_browser
        return _fetch_browser(self._adapter, url, ssl_verify, user_agent)


class RawFetchStrategy:
    def __init__(self, adapter):
        self._adapter = adapter

    def fetch(self, url: str, ssl_verify: bool, user_agent: str) -> tuple[str, int]:
        from scheduler.fetch_helpers import _fetch_with_retry
        return _fetch_with_retry(
            lambda: self._adapter.fetch_raw(url, user_agent, ssl_verify)
        )


class HttpFetchStrategy:
    _CLOUDFLARE_ADAPTERS = frozenset({"adib_api", "awash_ajax"})

    def __init__(self, adapter, adapter_key: str, timeout_config: dict):
        self._adapter = adapter
        self._adapter_key = adapter_key
        self._timeout_config = timeout_config

    def fetch(self, url: str, ssl_verify: bool, user_agent: str) -> tuple[str, int]:
        from scheduler.fetch_helpers import _fetch_with_retry, _build_url
        from http_clients.http_client import RequestsHttpClient

        http_client = RequestsHttpClient(
            connect_timeout=self._timeout_config["connect_timeout"],
            read_timeout=self._timeout_config["read_timeout"],
            max_retries=self._timeout_config["max_retries"],
            user_agent=user_agent,
            use_cloudflare_bypass=self._adapter_key in self._CLOUDFLARE_ADAPTERS,
        )

        post_data = (
            getattr(self._adapter, "post_data", None)
            or getattr(self._adapter, "FETCH_POST_DATA", None)
        )
        extra_headers = (
            getattr(self._adapter, "headers", None)
            or getattr(self._adapter, "FETCH_HEADERS", None)
        )

        response = _fetch_with_retry(
            lambda: http_client.fetch(
                _build_url(url, self._adapter_key),
                ssl_verify=ssl_verify,
                post_data=post_data,
                headers=extra_headers,
            )
        )

        if not response.is_success():
            raise RuntimeError(f"HTTP fetch failed: {response.error}")

        return response.content, response.status_code
