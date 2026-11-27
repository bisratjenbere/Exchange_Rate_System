import hashlib
import importlib
import time
import logging
from datetime import date

import requests

from adapters.core.contract import ParseContext, Severity
from adapters.core.dates import business_date_now
from adapters.banks.addis_fortune import get_adapter_for_key
from pipeline.runs import (
    start_run, finish_run, recover_stuck_run, record_raw_capture, reap_stuck_runs,
)
from pipeline.ingest import ingest

from infrastructure.config import Config
from infrastructure.adapter_registry_v2 import AdapterRegistryV2, default_registry
from infrastructure.rate_source_repository import RateSourceRepository
from infrastructure.error_classifier import ErrorClassifier, default_classifier
from infrastructure.circuit_breaker import CircuitBreaker, get_default_circuit_breaker
from http_clients.http_client import HttpClient, RequestsHttpClient
from scheduler.fetch_helpers import (
    _build_url, _check_schema, _fetch_browser, _fetch_with_retry,
    _has_fetch_raw, _store_raw_capture,
)
from scheduler.extraction.orchestrator import run_source_orchestrated
from infrastructure.fallback_policy import AddisFortuneFallbackPolicy

logger = logging.getLogger(__name__)

RETRY_DELAYS = [2, 10, 30]

class Scheduler:

    def __init__(
        self,
        config: Config = None,
        http_client: HttpClient = None,
        adapter_registry: AdapterRegistryV2 = None,
        error_classifier: ErrorClassifier = None,
        circuit_breaker: CircuitBreaker = None,
        fallback_policy=None,
        dry_run: bool = False
    ):
        self.config = config or Config()
        self.http_client = http_client or RequestsHttpClient(
            read_timeout=self.config.REQUEST_TIMEOUT,
            max_retries=self.config.MAX_RETRIES,
            retry_delay=self.config.RATE_LIMIT_DELAY,
            user_agent=self.config.USER_AGENT
        )
        self.adapter_registry = adapter_registry or default_registry
        self.error_classifier = error_classifier or default_classifier
        self.circuit_breaker = circuit_breaker or get_default_circuit_breaker()
        self.fallback_policy = fallback_policy or AddisFortuneFallbackPolicy()
        self.dry_run = dry_run

    def run_source(self, conn, source_id: int) -> dict:
        return run_source_orchestrated(
            conn=conn,
            source_id=source_id,
            circuit_breaker=self.circuit_breaker,
            adapter_registry=self.adapter_registry,
            error_classifier=self.error_classifier,
            user_agent=self.config.USER_AGENT,
            fallback_policy=self.fallback_policy,
            dry_run=self.dry_run,
        )

    def run_all(self, conn) -> list:
        reap_stuck_runs(conn, threshold_minutes=5)
        repo = RateSourceRepository(conn)
        sources = repo.get_enabled_sources()
        results = []
        for source in sources:
            result = self.run_source(conn, source.id)
            results.append(result)
            time.sleep(self.config.RATE_LIMIT_DELAY)
        return results

def _load_adapter(adapter_key: str):
    af_only_keys = {"hijra_af", "nbe_af", "anbesa_af", "oromia_af"}
    if adapter_key in af_only_keys:
        af = get_adapter_for_key(adapter_key)
        if af is not None:
            return af

    parts = adapter_key.split("_")
    candidates = [adapter_key]
    for i in range(len(parts) - 1, 0, -1):
        candidates.append("_".join(parts[:i]))
    candidates.append(adapter_key.rsplit("_", 1)[0] + "_")

    for name in dict.fromkeys(candidates):
        for pkg in ("adapters", "adapters.banks"):
            try:
                mod = importlib.import_module(f"{pkg}.{name}.adapter")
                return getattr(mod, "ADAPTER", mod)
            except ModuleNotFoundError:
                pass
        base = name.rsplit("_", 1)[0] if name.endswith(("_api", "_html", "_ajax", "_browser")) else name
        try:
            mod = importlib.import_module(f"adapters.banks.{base}")
            return getattr(mod, "ADAPTER", mod)
        except ModuleNotFoundError:
            pass
    raise ImportError(f"No adapter module found for adapter_key={adapter_key!r}")

def _classify_error(exc: Exception) -> tuple:
    msg = str(exc)
    if "Schema fingerprint" in msg or "schema" in msg.lower():
        return "schema_change", msg
    if isinstance(exc, (ValueError, KeyError, AttributeError)):
        return "parse_failure", msg
    if isinstance(exc, (requests.exceptions.ConnectionError,
                        requests.exceptions.Timeout)):
        return "http_failure", msg
    return "parse_failure", f"{type(exc).__name__}: {msg}"

def _parse(adapter, raw_content: str, category: str = "UNKNOWN", adapter_config: dict = None) -> tuple[list, list, list]:
    ctx = ParseContext(
        category=category,
        collection_date=business_date_now(),
        source_id=0,
    )
    if adapter_config and hasattr(adapter, "slug"):
        adapter.slug = adapter_config.get("slug", adapter.slug)

    outcome = adapter.parse(raw_content, ctx)
    if isinstance(outcome, (list, tuple)) and not hasattr(outcome, "records"):
        # legacy adapter returning plain list or (records, errors) tuple
        if isinstance(outcome, list):
            return outcome, [], []
        records = list(outcome[0]) if outcome else []
        errors = list(outcome[1]) if len(outcome) > 1 else []
        warnings = list(outcome[2]) if len(outcome) > 2 else []
        return records, errors, warnings
    records = list(outcome.records) if hasattr(outcome, "records") else []
    errors = [i.detail for i in outcome.issues if i.severity == Severity.ERROR] if hasattr(outcome, "issues") else (outcome.errors if hasattr(outcome, "errors") else [])
    warnings = [i.detail for i in outcome.issues if i.severity == Severity.WARNING] if hasattr(outcome, "issues") else (outcome.warnings if hasattr(outcome, "warnings") else [])
    return records, errors, warnings

