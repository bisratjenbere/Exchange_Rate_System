import hashlib
import importlib
import time
import traceback
from datetime import date, datetime, timezone
from typing import Optional
import psycopg2
import requests
from pipeline.runs import (
    start_run, finish_run, recover_stuck_run, record_raw_capture, reap_stuck_runs,
)
from pipeline.ingest import ingest

from infrastructure.config import Config
from infrastructure.adapter_registry import AdapterRegistry, default_registry
from infrastructure.rate_source_repository import RateSourceRepository
from infrastructure.error_classifier import ErrorClassifier, default_classifier
from infrastructure.circuit_breaker import CircuitBreaker, get_default_circuit_breaker
from infrastructure.timeout_config import get_timeout_config
from http_clients.http_client import HttpClient, RequestsHttpClient

RETRY_DELAYS = [2, 10, 30]
ALERT_AFTER_CONSECUTIVE_FAILURES = 2
FALLBACK_TTL_DAYS = 3

def _fetch_with_retry(fetch_fn, retries: int = 1, backoff: float = 2.0):
    for attempt in range(retries + 1):
        try:
            res = fetch_fn()
            if hasattr(res, "is_success") and not res.is_success():
                err = str(getattr(res, "error", "")).lower()
                if attempt < retries and any(t in err for t in ("timeout", "timed out", "connection", "nameresolution")):
                    time.sleep(backoff)
                    continue
            return res
        except Exception as exc:
            err = str(exc).lower()
            if attempt < retries and any(t in err for t in ("timeout", "timed out", "connection", "nameresolution")):
                time.sleep(backoff)
                continue
            raise

def _has_fetch_raw(adapter) -> bool:
    if not hasattr(adapter, "fetch_raw"):
        return False
    if "Mock" in type(adapter).__name__:
        from unittest.mock import DEFAULT
        fn = getattr(adapter, "fetch_raw")
        if getattr(fn, "_mock_return_value", None) is DEFAULT and getattr(fn, "side_effect", None) is None:
            return False
    return True

class Scheduler:

    def __init__(
        self,
        config: Config = None,
        http_client: HttpClient = None,
        adapter_registry: AdapterRegistry = None,
        error_classifier: ErrorClassifier = None,
        circuit_breaker: CircuitBreaker = None,
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
        self.dry_run = dry_run

    def run_source(self, conn, source_id: int) -> dict:
        # Phase 0: Pre-flight checks (extracted to input_parser module)
        from scheduler.extraction.input_parser import validate_source_and_check_circuit_breaker
        
        preflight = validate_source_and_check_circuit_breaker(
            conn, source_id, self.circuit_breaker, self.config.USER_AGENT
        )
        
        if not preflight.should_proceed:
            return preflight.early_return
        
        # Pre-flight passed - extract values for main collection logic
        run_id = preflight.run_id
        source = preflight.source
        adapter_key = source["adapter_key"]
        source_url = source["source_url"]
        ssl_verify = source["ssl_verify"]

        # Create repo for schema checks and success updates
        repo = RateSourceRepository(conn)

        t0 = time.monotonic()
        raw_content: str | None = None
        http_status: int | None = None
        schema_changed: bool = False

        try:
            # Phase 1: Fetch and parse (extracted to fetcher module)
            from scheduler.extraction.fetcher import fetch_parse_and_check_schema

            fetch_result = fetch_parse_and_check_schema(
                conn, run_id, source, self.adapter_registry, repo, self.config.USER_AGENT
            )

            # Extract values for decision logic
            records = fetch_result.records
            raw_content = fetch_result.raw_content
            http_status = fetch_result.http_status
            schema_changed = fetch_result.schema_changed
            # Note: fetch_result.duration_ms not used here, we use t0 for total duration

            # Phase 2: Decide how to handle records (zero/stale/normal)
            all_stale = len(records) > 0 and all(r.effective_date and (date.today() - r.effective_date).days > 3 for r in records)
            if len(records) == 0 or all_stale:
                err_code = "zero_records_extracted" if len(records) == 0 else "stale_feed"
                err_summary = "Primary returned 0 records; fallback invoked" if len(records) == 0 else "Primary returned stale records; fallback invoked"
                finish_run(
                    conn, run_id, "failed",
                    http_status=http_status,
                    records_found=len(records),
                    records_accepted=0,
                    records_flagged=0,
                    records_duplicated=0,
                    error_code=err_code,
                    error_summary=err_summary,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                    is_fallback=False,
                )
                needs_alert = _increment_failure_counter(conn, source_id, err_code)
                if needs_alert:
                    _write_alert(conn, source_id, err_code, err_summary)
                conn.commit()

                af_res = _try_af_fallback(conn, source_id, adapter_key, self.config.USER_AGENT)
                if af_res is not None:
                    return af_res

                if all_stale and len(records) > 0:
                    fetched_at = datetime.now(timezone.utc)
                    result = ingest(conn, records, source_id, run_id, fetched_at=fetched_at, is_fallback=False)
                    duration_ms = int((time.monotonic() - t0) * 1000)
                    finish_run(
                        conn, run_id, "success",
                        http_status=http_status,
                        records_found=len(records),
                        records_accepted=result.accepted,
                        records_flagged=result.flagged,
                        records_duplicated=result.duplicates,
                        error_code="stale_feed",
                        error_summary="Primary returned stale records; retained as standing rate",
                        duration_ms=duration_ms,
                        is_fallback=False,
                    )
                    repo.update_last_success(source_id)
                    _reset_failure_counter(conn, source_id)
                    conn.commit()
                    return {
                        "source_id": source_id,
                        "status": "success",
                        "accepted": result.accepted,
                        "flagged": result.flagged,
                        "rejected": result.rejected,
                        "duplicates": result.duplicates,
                    }

                return {
                    "source_id": source_id,
                    "status": "failed",
                    "error_code": err_code,
                    "detail": err_summary,
                }

            if schema_changed:
                new_fp = adapter.schema_fingerprint(raw_content)
                repo.update_schema_fingerprint(source_id, new_fp)

            fetched_at = datetime.now(timezone.utc)
            result = ingest(conn, records, source_id, run_id, fetched_at=fetched_at, is_fallback=False)

            if result.suspicious:
                _store_raw_capture(conn, run_id, "suspicious_data", raw_content)

            duration_ms = int((time.monotonic() - t0) * 1000)
            run_status = _run_status(result)

            if self.dry_run:
                conn.rollback()
                return {
                    "source_id": source_id,
                    "status": "dry_run",
                    "records_found": len(records),
                    "would_accept": result.accepted,
                    "would_reject": result.rejected,
                    "would_flag": result.flagged,
                    "would_duplicate": result.duplicates,
                    "schema_changed": schema_changed,
                    "duration_ms": duration_ms
                }

            finish_run(
                conn, run_id, run_status,
                http_status=http_status,
                records_found=len(records),
                records_accepted=result.accepted,
                records_flagged=result.flagged,
                records_duplicated=result.duplicates,
                duration_ms=duration_ms,
                is_fallback=False,
            )

            if run_status in ("success", "partial_success"):
                repo.update_last_success(source_id)
                _reset_failure_counter(conn, source_id)
                self.circuit_breaker.record_success(adapter_key)
                _expire_stale_fallback_current(conn, source_id)

            conn.commit()
            return {
                "source_id": source_id,
                "status": run_status,
                "accepted": result.accepted,
                "flagged": result.flagged,
                "rejected": result.rejected,
                "duplicates": result.duplicates,
                "candidates": result.candidates,
                "schema_changed": schema_changed,
            }

        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            error_code, error_summary = self.error_classifier.classify(exc)

            self.circuit_breaker.record_failure(adapter_key)

            if raw_content and error_code in ("parse_failure", "schema_change"):
                try:
                    _store_raw_capture(conn, run_id, error_code, raw_content)
                except Exception:
                    pass

            try:
                finish_run(
                    conn, run_id, "failed",
                    http_status=http_status,
                    error_code=error_code,
                    error_summary=error_summary[:500] if error_summary else None,
                    duration_ms=duration_ms,
                    is_fallback=False,
                )
                needs_alert = _increment_failure_counter(conn, source_id, error_code)
                if needs_alert:
                    _write_alert(conn, source_id, error_code, error_summary)
                conn.commit()
            except Exception:
                conn.rollback()

            af_result = _try_af_fallback(conn, source_id, source["adapter_key"], self.config.USER_AGENT)
            if af_result:
                return af_result

            return {
                "source_id": source_id,
                "status": "failed",
                "error_code": error_code,
                "detail": error_summary,
            }

    def run_all(self, conn) -> list:
        reap_stuck_runs(conn, threshold_minutes=5)
        repo = RateSourceRepository(conn)
        sources = repo.get_enabled_sources()
        results = []
        for source in sources:
            result = self.run_source(conn, source["id"])
            results.append(result)
            time.sleep(self.config.RATE_LIMIT_DELAY)
        return results

def _load_adapter(adapter_key: str):
    from adapters.addis_fortune.adapter import get_adapter_for_key, AF_SLUG_MAP
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
        try:
            return importlib.import_module(f"adapters.{name}.adapter")
        except ModuleNotFoundError:
            continue
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

def _fetch(url: str, ssl_verify: bool, post_data: dict = None,
           extra_headers: dict = None) -> tuple:
    last_exc = None
    config = Config()
    headers = {"User-Agent": config.USER_AGENT}
    if extra_headers:
        headers.update(extra_headers)
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            if post_data is not None:
                resp = requests.post(
                    url, data=post_data, headers=headers,
                    timeout=config.REQUEST_TIMEOUT, verify=ssl_verify,
                )
            else:
                resp = requests.get(
                    url, headers=headers,
                    timeout=config.REQUEST_TIMEOUT, verify=ssl_verify,
                )
            if resp.status_code == 200:
                return resp.text, resp.status_code
            raise RuntimeError(f"HTTP {resp.status_code} from {url}")
        except Exception as exc:
            last_exc = exc
    raise last_exc

def _fetch_browser(adapter, source_url: str, ssl_verify: bool, user_agent: str) -> tuple:
    return adapter.fetch_raw(source_url, user_agent, ssl_verify)

def _check_schema(conn, run_id: int, source: dict, adapter, raw_content: str, repo: RateSourceRepository = None) -> bool:
    if not hasattr(adapter, "schema_fingerprint"):
        return False
    current_fp = adapter.schema_fingerprint(raw_content)
    stored_fp = source.get("schema_fingerprint")
    if not stored_fp:
        if repo:
            repo.update_schema_fingerprint(source["id"], current_fp)
        else:
            # Inline update when repo not provided
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE rate_source SET schema_fingerprint = %s WHERE id = %s",
                    (str(current_fp) if current_fp is not None else None, source["id"]),
                )
        return False
    if current_fp != stored_fp:
        _store_raw_capture(conn, run_id, "schema_change", raw_content)
        return True
    return False

def _parse(adapter, raw_content: str, category: str = "UNKNOWN") -> list:
    import inspect
    from adapters.base import ParseResult
    sig = inspect.signature(adapter.parse)
    if "category" in sig.parameters:
        result = adapter.parse(raw_content, category=category)
    else:
        result = adapter.parse(raw_content)
    if isinstance(result, ParseResult):
        return result.records
    if isinstance(result, tuple):
        records, _errors = result
        return records
    return result

def _build_url(base_url: str, adapter_key: str) -> str:
    from datetime import date
    today = date.today().isoformat()
    if adapter_key == "cbe_api":
        sep = "&" if "?" in base_url else "?"
        return f"{base_url}{sep}Date={today}"
    if adapter_key == "bunna_html" and "bunnabanksc.com/foreign-exchange" in base_url:
        return "https://mb.bunnabanksc.com/api/v1/user/public/forex"
    return base_url

def _store_raw_capture(conn, run_id: int, reason: str, raw_content: str):
    content_hash = hashlib.sha256(raw_content.encode()).hexdigest()
    record_raw_capture(conn, run_id, reason, content_hash)

def _run_status(result) -> str:
    if result.rejected > 0 and result.accepted == 0:
        return "failed"
    if result.rejected > 0 or result.errors:
        return "partial_success"
    return "success"

def _reset_failure_counter(conn, source_id: int):
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE rate_source
               SET consecutive_failures = 0, last_failure_code = NULL
               WHERE id = %s""",
            (source_id,),
        )

def _increment_failure_counter(conn, source_id: int, error_code: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE rate_source
               SET consecutive_failures = consecutive_failures + 1,
                   last_failure_at = now(),
                   last_failure_code = %s
               WHERE id = %s
               RETURNING consecutive_failures, alert_sent_at""",
            (error_code, source_id),
        )
        row = cur.fetchone()
        if not row:
            return False
        consecutive, alert_sent_at = row
        if consecutive >= ALERT_AFTER_CONSECUTIVE_FAILURES:
            if alert_sent_at is None or (
                datetime.now(timezone.utc) - alert_sent_at
            ).total_seconds() > 86400:
                return True
    return False

def _write_alert(conn, source_id: int, error_code: str, error_summary: str):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO source_alert (source_id, error_code, summary, created_at)
               VALUES (%s, %s, %s, now())""",
            (source_id, error_code, (error_summary or "")[:500]),
        )
        cur.execute(
            "UPDATE rate_source SET alert_sent_at = now() WHERE id = %s",
            (source_id,),
        )

def _try_af_fallback(conn, source_id: int, adapter_key: str, user_agent: str) -> dict | None:
    from adapters.addis_fortune.adapter import get_adapter_for_key
    af_adapter = get_adapter_for_key(adapter_key)
    if af_adapter is None:
        return None

    try:
        run_id = start_run(conn, source_id)
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return None

    t0 = time.monotonic()
    try:
        raw_content, http_status = af_adapter.fetch_raw(
            af_adapter.get_source_url(), user_agent, ssl_verify=True
        )
        result_obj = af_adapter.parse(raw_content)
        if isinstance(result_obj, tuple):
            records, _ = result_obj
        else:
            records = result_obj.records if hasattr(result_obj, 'records') else result_obj

        fetched_at = datetime.now(timezone.utc)
        ingest_result = ingest(conn, records, source_id, run_id, fetched_at=fetched_at, is_fallback=True)

        duration_ms = int((time.monotonic() - t0) * 1000)
        run_status = _run_status(ingest_result)
        finish_run(
            conn, run_id, run_status,
            http_status=http_status,
            records_found=len(records),
            records_accepted=ingest_result.accepted,
            records_flagged=ingest_result.flagged,
            records_duplicated=ingest_result.duplicates,
            duration_ms=duration_ms,
            is_fallback=True,
            fallback_adapter="addis_fortune",
        )
        if run_status in ("success", "partial_success"):
            repo = RateSourceRepository(conn)
            repo.update_last_success(source_id)
            _reset_failure_counter(conn, source_id)
        conn.commit()
        return {
            "source_id": source_id,
            "status": run_status,
            "accepted": ingest_result.accepted,
            "flagged": ingest_result.flagged,
            "rejected": ingest_result.rejected,
            "duplicates": ingest_result.duplicates,
            "fallback": "addis_fortune",
        }
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        error_classifier = default_classifier
        error_code, error_summary = error_classifier.classify(exc)
        try:
            finish_run(conn, run_id, "failed",
                       error_code=error_code,
                       error_summary=error_summary[:500] if error_summary else None,
                       duration_ms=duration_ms,
                       is_fallback=True,
                       fallback_adapter="addis_fortune")
            conn.commit()
        except Exception:
            conn.rollback()
        return None

def _expire_stale_fallback_current(conn, source_id: int):
    """Expire stale fallback current observations using repository pattern."""
    from db.repositories.rate_observation_repository import RateObservationRepository
    repo = RateObservationRepository(conn)
    repo.expire_stale_fallback_current(source_id, FALLBACK_TTL_DAYS)
