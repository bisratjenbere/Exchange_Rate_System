from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY
from typing import Optional

collections_total = Counter(
    'exchange_rate_collections_total',
    'Total collection attempts by source and status',
    ['source_id', 'adapter_key', 'status']
)

collection_duration = Histogram(
    'exchange_rate_collection_duration_seconds',
    'Collection duration by source',
    ['adapter_key'],
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, float('inf'))
)

active_collections = Gauge(
    'exchange_rate_active_collections',
    'Currently running collections'
)

records_accepted = Counter(
    'exchange_rate_records_accepted_total',
    'Total records accepted by source',
    ['adapter_key']
)

records_rejected = Counter(
    'exchange_rate_records_rejected_total',
    'Total records rejected by source',
    ['adapter_key', 'reason']
)

collection_errors = Counter(
    'exchange_rate_collection_errors_total',
    'Collection errors by source and error code',
    ['adapter_key', 'error_code']
)

circuit_breaker_open = Gauge(
    'exchange_rate_circuit_breaker_open',
    'Circuit breaker state (1=open, 0=closed)',
    ['adapter_key']
)

consecutive_failures = Gauge(
    'exchange_rate_consecutive_failures',
    'Consecutive failure count by source',
    ['adapter_key']
)

http_response_time = Histogram(
    'exchange_rate_http_response_seconds',
    'HTTP fetch response time',
    ['adapter_key'],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float('inf'))
)

parse_duration = Histogram(
    'exchange_rate_parse_duration_seconds',
    'Parse operation duration',
    ['adapter_key'],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, float('inf'))
)

ingest_duration = Histogram(
    'exchange_rate_ingest_duration_seconds',
    'Ingest operation duration',
    ['adapter_key'],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float('inf'))
)

schema_changes = Counter(
    'exchange_rate_schema_changes_total',
    'Schema fingerprint changes detected',
    ['adapter_key']
)

fallback_attempts = Counter(
    'exchange_rate_fallback_attempts_total',
    'Addis Fortune fallback attempts',
    ['adapter_key', 'status']
)

last_success_timestamp = Gauge(
    'exchange_rate_last_success_timestamp',
    'Timestamp of last successful collection',
    ['adapter_key']
)

def record_collection_attempt(source_id: int, adapter_key: str, status: str):
    collections_total.labels(
        source_id=str(source_id),
        adapter_key=adapter_key,
        status=status
    ).inc()

def record_collection_success(adapter_key: str, accepted: int, rejected: int):
    records_accepted.labels(adapter_key=adapter_key).inc(accepted)
    if rejected > 0:
        records_rejected.labels(
            adapter_key=adapter_key,
            reason='validation_failed'
        ).inc(rejected)

    import time
    last_success_timestamp.labels(adapter_key=adapter_key).set(time.time())

def record_collection_error(adapter_key: str, error_code: str):
    collection_errors.labels(
        adapter_key=adapter_key,
        error_code=error_code
    ).inc()

def record_schema_change(adapter_key: str):
    schema_changes.labels(adapter_key=adapter_key).inc()

def record_fallback(adapter_key: str, status: str):
    fallback_attempts.labels(
        adapter_key=adapter_key,
        status=status
    ).inc()

def update_circuit_breaker_state(adapter_key: str, is_open: bool):
    circuit_breaker_open.labels(adapter_key=adapter_key).set(1 if is_open else 0)

def update_consecutive_failures(adapter_key: str, count: int):
    consecutive_failures.labels(adapter_key=adapter_key).set(count)

def get_metrics_text() -> str:
    return generate_latest(REGISTRY).decode('utf-8')

class CollectionMetricsContext:

    def __init__(self, adapter_key: str):
        self.adapter_key = adapter_key
        self.timer = collection_duration.labels(adapter_key=adapter_key).time()

    def __enter__(self):
        active_collections.inc()
        self.timer.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        active_collections.dec()
        self.timer.__exit__(exc_type, exc_val, exc_tb)
        return False

    def record_success(self, accepted: int, rejected: int):
        record_collection_success(self.adapter_key, accepted, rejected)

    def record_error(self, error_code: str):
        record_collection_error(self.adapter_key, error_code)
