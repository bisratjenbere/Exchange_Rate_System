"""
Fetcher module - Adapter loading, HTTP fetching, and schema checking.

Extracted from scheduler/runner.py lines 101-150.
Handles:
- Adapter loading from registry
- HTTP content fetching (browser, fetch_raw, or HTTP client)
- Schema fingerprint checking and raw capture
- Parsing adapter output

This module contains NO transaction logic (schema change stores raw but doesn't commit).
"""

import time
from dataclasses import dataclass

from domain.records import AdapterRecord
from http_clients.http_client import RequestsHttpClient
from infrastructure.adapter_registry import AdapterRegistry
from infrastructure.rate_source_repository import RateSourceRepository
from infrastructure.timeout_config import get_timeout_config


@dataclass(frozen=True)
class FetchResult:
    """Result of fetching and parsing adapter content."""
    records: list[AdapterRecord]
    raw_content: str
    http_status: int
    schema_changed: bool
    duration_ms: int
    adapter_key: str
    adapter: object  # Adapter instance for schema_fingerprint calls


def fetch_parse_and_check_schema(
    conn,
    run_id: int,
    source: dict,
    adapter_registry: AdapterRegistry,
    repo: RateSourceRepository,
    user_agent: str,
) -> FetchResult:
    """
    Fetch content from source, parse it, and check schema changes.

    Steps:
    1. Load adapter from registry
    2. Determine fetch method (browser/fetch_raw/http_client)
    3. Fetch content with retry logic
    4. Check schema fingerprint (stores raw capture if changed, but doesn't commit)
    5. Parse content into AdapterRecords

    Args:
        conn: Database connection
        run_id: ID of the current collection run
        source: Source record from database
        adapter_registry: Registry containing all adapters
        repo: Rate source repository for schema updates
        user_agent: User agent string for HTTP requests

    Returns:
        FetchResult containing parsed records, raw content, and metadata

    Transaction Behavior:
        - Read-only except _check_schema which may store raw_capture (no commit)
        - All database writes are deferred to caller
    """
    # Import helpers from runner.py (they're not extracted yet)
    from scheduler.runner import (
        _build_url,
        _check_schema,
        _fetch_browser,
        _fetch_with_retry,
        _has_fetch_raw,
        _parse,
    )

    adapter_key = source["adapter_key"]
    source_url = source["source_url"]
    ssl_verify = source["ssl_verify"]

    t0 = time.monotonic()

    # Step 1: Load adapter
    adapter = adapter_registry.get(adapter_key)
    fetch_method = getattr(adapter, "FETCH_METHOD", None)

    # Step 2: Get timeout configuration
    timeout_config = get_timeout_config(adapter_key)

    # Step 3: Fetch content based on adapter type
    if fetch_method == "browser":
        raw_content, http_status = _fetch_browser(
            adapter, source_url, ssl_verify, user_agent
        )
    elif _has_fetch_raw(adapter):
        raw_content, http_status = _fetch_with_retry(
            lambda: adapter.fetch_raw(source_url, user_agent, ssl_verify)
        )
    else:
        # Standard HTTP client fetch
        needs_cloudflare_bypass = adapter_key in ["adib_api", "awash_ajax"]

        http_client = RequestsHttpClient(
            connect_timeout=timeout_config["connect_timeout"],
            read_timeout=timeout_config["read_timeout"],
            max_retries=timeout_config["max_retries"],
            user_agent=user_agent,
            use_cloudflare_bypass=needs_cloudflare_bypass
        )

        post_data = getattr(adapter, "FETCH_POST_DATA", None)
        extra_headers = getattr(adapter, "FETCH_HEADERS", None)
        response = _fetch_with_retry(
            lambda: http_client.fetch(
                _build_url(source_url, source["adapter_key"]),
                ssl_verify=ssl_verify,
                post_data=post_data,
                headers=extra_headers
            )
        )
        if not response.is_success():
            raise RuntimeError(f"HTTP fetch failed: {response.error}")
        raw_content = response.content
        http_status = response.status_code

    # Step 4: Check schema (may store raw_capture as side effect, but doesn't commit)
    schema_changed = _check_schema(conn, run_id, source, adapter, raw_content, repo)

    # Step 5: Parse content
    category = source.get("default_category") or "UNKNOWN"
    records = _parse(adapter, raw_content, category)

    duration_ms = int((time.monotonic() - t0) * 1000)

    return FetchResult(
        records=records,
        raw_content=raw_content,
        http_status=http_status,
        schema_changed=schema_changed,
        duration_ms=duration_ms,
        adapter_key=adapter_key,
        adapter=adapter
    )
