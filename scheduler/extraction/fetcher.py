import time
from dataclasses import dataclass

from adapters.core.contract import ParseOutcome
from domain.records import AdapterRecord
from domain.source import RateSource
from infrastructure.adapter_registry_v2 import AdapterRegistryV2
from infrastructure.rate_source_repository import RateSourceRepository
from scheduler.fetch_helpers import _check_schema
from scheduler.fetch_strategy_resolver import resolve_fetch_strategy
from scheduler.parsing import parse_with_adapter, extract_errors_and_warnings


@dataclass(frozen=True)
class FetchResult:
    records: list[AdapterRecord]
    raw_content: str
    http_status: int
    schema_changed: bool
    duration_ms: int
    adapter_key: str
    adapter: object
    errors: list = ()        
    warnings: list = ()      
    parse_outcome: ParseOutcome = None 


def fetch_parse_and_check_schema(
    conn,
    run_id: int,
    source: RateSource,
    adapter_registry: AdapterRegistryV2,
    repo: RateSourceRepository,
    user_agent: str,
) -> FetchResult:
    adapter_key = source.adapter_key
    source_url = source.source_url
    ssl_verify = source.ssl_verify

    t0 = time.monotonic()

    adapter = adapter_registry.get(adapter_key)
    strategy = resolve_fetch_strategy(adapter, adapter_key)
    raw_content, http_status = strategy.fetch(source_url, ssl_verify, user_agent)

    schema_changed = _check_schema(conn, run_id, source, adapter, raw_content, repo)

    outcome = parse_with_adapter(
        adapter=adapter,
        raw_content=raw_content,
        source=source,
        collection_date=None,
        adapter_config=source.adapter_config,
    )
    
    # Extract records and errors/warnings for FetchResult
    records = list(outcome.records)
    errors, warnings = extract_errors_and_warnings(outcome)

    duration_ms = int((time.monotonic() - t0) * 1000)

    return FetchResult(
        records=records,
        raw_content=raw_content,
        http_status=http_status,
        schema_changed=schema_changed,
        duration_ms=duration_ms,
        adapter_key=adapter_key,
        adapter=adapter,
        errors=errors,
        warnings=warnings,
        parse_outcome=outcome,
    )

