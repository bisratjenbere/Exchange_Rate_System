"""
scheduler/runner.py — collection run orchestration.

run_source(conn, source_id):
  1. recover_stuck_run
  2. start_run
  3. fetch live data (polite: identified UA, timeout, rate limit)
  4. adapter.parse()
  5. ingest()
  6. finish_run with counts
  7. record_raw_capture for schema_change / suspicious_data
  8. update rate_source.last_success_at on success

run_all(conn):
  Iterates all enabled sources and calls run_source for each.
  One failure never stops the others.

LOCKED rules:
- One running run per source (enforced by DB index; UniqueViolation caught).
- A failed run never deletes or invalidates earlier observations.
- Polite fetching: identified user agent, timeout, bounded retries.
- No secrets in code — SOURCE_URL comes from rate_source table.
"""
import hashlib
import importlib
import time
import traceback
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import requests

from pipeline.runs import (
    start_run, finish_run, recover_stuck_run, record_raw_capture,
)
from pipeline.ingest import ingest

# Import infrastructure components
from infrastructure.config import Config
from infrastructure.adapter_registry import AdapterRegistry, default_registry
from infrastructure.rate_source_repository import RateSourceRepository
from infrastructure.error_classifier import ErrorClassifier, default_classifier
from http_clients.http_client import HttpClient, RequestsHttpClient

# Module-level constants (not in Config yet)
RETRY_DELAYS = [2, 10, 30]  # exponential backoff seconds between HTTP retries
ALERT_AFTER_CONSECUTIVE_FAILURES = 2  # alert after this many consecutive failures
FALLBACK_TTL_DAYS = 3  # retire fallback-date current records older than this


class Scheduler:
    """
    Scheduler class with dependency injection for testability.
    
    Orchestrates collection runs for exchange rate sources, managing:
    - HTTP fetching via HttpClient abstraction
    - Adapter lookup via AdapterRegistry
    - Database operations via RateSourceRepository
    - Error classification via ErrorClassifier strategy pattern
    - Configuration via Config object
    
    All dependencies are injected for testing and extensibility.
    """
    
    def __init__(
        self,
        config: Config = None,
        http_client: HttpClient = None,
        adapter_registry: AdapterRegistry = None,
        error_classifier: ErrorClassifier = None
    ):
        """
        Initialize Scheduler with dependency injection.
        
        Args:
            config: Configuration object (defaults to Config())
            http_client: HTTP client implementation (defaults to RequestsHttpClient)
            adapter_registry: Adapter registry (defaults to default_registry)
            error_classifier: Error classifier (defaults to default_classifier)
        """
        self.config = config or Config()
        self.http_client = http_client or RequestsHttpClient(
            timeout=self.config.REQUEST_TIMEOUT,
            max_retries=self.config.MAX_RETRIES,
            retry_delay=self.config.RATE_LIMIT_DELAY,
            user_agent=self.config.USER_AGENT
        )
        self.adapter_registry = adapter_registry or default_registry
        self.error_classifier = error_classifier or default_classifier
    
    def run_source(self, conn, source_id: int) -> dict:
        """
        Run collection for one source. Returns a summary dict.
        Never raises — all errors are caught and recorded.
        """
        repo = RateSourceRepository(conn)
        source = repo.get_by_id(source_id)
        if source is None:
            return {"source_id": source_id, "status": "error", "detail": "source not found"}

        adapter_key = source["adapter_key"]
        source_url = source["source_url"]
        ssl_verify = source["ssl_verify"]

        # 1. Recover any stuck run first
        recover_stuck_run(conn, source_id)

        # 2. Start run (may raise UniqueViolation if already running)
        try:
            run_id = start_run(conn, source_id)
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            return {"source_id": source_id, "status": "skipped",
                    "detail": "run already in progress"}

        t0 = time.monotonic()
        raw_content: Optional[str] = None
        http_status: Optional[int] = None

        try:
            # 3. Fetch
            adapter = self.adapter_registry.get(adapter_key)
            fetch_method = getattr(adapter, "FETCH_METHOD", None)
            if fetch_method == "browser":
                raw_content, http_status = _fetch_browser(adapter, source_url, ssl_verify, self.config.USER_AGENT)
            elif hasattr(adapter, "fetch_raw"):
                raw_content, http_status = adapter.fetch_raw(
                    source_url, self.config.USER_AGENT, ssl_verify
                )
            else:
                post_data = getattr(adapter, "FETCH_POST_DATA", None)
                extra_headers = getattr(adapter, "FETCH_HEADERS", None)
                response = self.http_client.fetch(
                    _build_url(source_url, source["adapter_key"]),
                    ssl_verify=ssl_verify,
                    post_data=post_data,
                    headers=extra_headers
                )
                if not response.is_success():
                    raise RuntimeError(f"HTTP fetch failed: {response.error}")
                raw_content = response.content
                http_status = response.status_code

            # 4. Schema fingerprint check — try-parse-first approach:
            #    If fingerprint changed, capture raw but continue. If parse then
            #    succeeds, auto-accept the new fingerprint. Only hard-fail if
            #    parse itself raises.
            schema_changed = _check_schema(conn, run_id, source, adapter, raw_content, repo)

            # 5. Parse
            category = source.get("default_category") or "UNKNOWN"
            records = _parse(adapter, raw_content, category)

            # 6. Auto-accept new fingerprint now that parse succeeded
            if schema_changed:
                new_fp = adapter.schema_fingerprint(raw_content)
                repo.update_schema_fingerprint(source_id, new_fp)

            # 7. Ingest
            fetched_at = datetime.now(timezone.utc)
            result = ingest(conn, records, source_id, run_id, fetched_at=fetched_at)

            # 8. Raw capture for suspicious data
            if result.suspicious:
                _store_raw_capture(conn, run_id, "suspicious_data", raw_content)

            # 9. Finish run
            duration_ms = int((time.monotonic() - t0) * 1000)
            run_status = _run_status(result)
            finish_run(
                conn, run_id, run_status,
                http_status=http_status,
                records_found=len(records),
                records_accepted=result.accepted,
                records_flagged=result.flagged + result.duplicates,
                duration_ms=duration_ms,
            )

            # 10. Update last_success_at + reset failure counter
            if run_status in ("success", "partial_success"):
                repo.update_last_success(source_id)
                _reset_failure_counter(conn, source_id)
                # Expire stale fallback-date current records (no date on page —
                # if a currency vanishes for >2 days its old record stays current
                # forever without this TTL)
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
                )
                needs_alert = _increment_failure_counter(conn, source_id, error_code)
                if needs_alert:
                    _write_alert(conn, source_id, error_code, error_summary)
                conn.commit()
            except Exception:
                conn.rollback()

            # Try Addis Fortune fallback
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
        """
        Run collection for all enabled sources. Returns list of summary dicts.
        One failure never stops the others.
        """
        repo = RateSourceRepository(conn)
        sources = repo.get_enabled_sources()
        results = []
        for source in sources:
            result = self.run_source(conn, source["id"])
            results.append(result)
            time.sleep(self.config.RATE_LIMIT_DELAY)
        return results


# ── Backward compatibility wrappers ──────────────────────────────────────────
# These wrappers maintain the old function-based implementation to ensure
# existing tests pass without modification. New code should use the Scheduler
# class directly for dependency injection and testability.

def run_source(conn, source_id: int) -> dict:
    """
    Run collection for one source. Returns a summary dict.
    Never raises — all errors are caught and recorded.
    
    This is the original implementation kept for backward compatibility.
    New code should use Scheduler class directly.
    """
    source = _load_source_old(conn, source_id)
    if source is None:
        return {"source_id": source_id, "status": "error", "detail": "source not found"}

    adapter_key = source["adapter_key"]
    source_url = source["source_url"]
    ssl_verify = source["ssl_verify"]

    # 1. Recover any stuck run first
    recover_stuck_run(conn, source_id)

    # 2. Start run (may raise UniqueViolation if already running)
    try:
        run_id = start_run(conn, source_id)
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return {"source_id": source_id, "status": "skipped",
                "detail": "run already in progress"}

    t0 = time.monotonic()
    raw_content: Optional[str] = None
    http_status: Optional[int] = None

    try:
        # 3. Fetch
        adapter = _load_adapter(adapter_key)
        fetch_method = getattr(adapter, "FETCH_METHOD", None)
        config = Config()
        if fetch_method == "browser":
            raw_content, http_status = _fetch_browser(adapter, source_url, ssl_verify, config.USER_AGENT)
        elif hasattr(adapter, "fetch_raw"):
            raw_content, http_status = adapter.fetch_raw(
                source_url, config.USER_AGENT, ssl_verify
            )
        else:
            post_data = getattr(adapter, "FETCH_POST_DATA", None)
            extra_headers = getattr(adapter, "FETCH_HEADERS", None)
            raw_content, http_status = _fetch(
                _build_url(source_url, source["adapter_key"]), ssl_verify,
                post_data=post_data, extra_headers=extra_headers,
            )

        # 4. Schema fingerprint check
        schema_changed = _check_schema(conn, run_id, source, adapter, raw_content, repo=None)

        # 5. Parse
        category = source.get("default_category") or "UNKNOWN"
        records = _parse(adapter, raw_content, category)

        # 6. Auto-accept new fingerprint now that parse succeeded
        if schema_changed:
            new_fp = adapter.schema_fingerprint(raw_content)
            _update_fingerprint_old(conn, source_id, new_fp)

        # 7. Ingest
        fetched_at = datetime.now(timezone.utc)
        result = ingest(conn, records, source_id, run_id, fetched_at=fetched_at)

        # 8. Raw capture for suspicious data
        if result.suspicious:
            _store_raw_capture(conn, run_id, "suspicious_data", raw_content)

        # 9. Finish run
        duration_ms = int((time.monotonic() - t0) * 1000)
        run_status = _run_status(result)
        finish_run(
            conn, run_id, run_status,
            http_status=http_status,
            records_found=len(records),
            records_accepted=result.accepted,
            records_flagged=result.flagged + result.duplicates,
            duration_ms=duration_ms,
        )

        # 10. Update last_success_at + reset failure counter
        if run_status in ("success", "partial_success"):
            _update_last_success_old(conn, source_id)
            _reset_failure_counter(conn, source_id)
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
        error_code, error_summary = _classify_error(exc)

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
            )
            needs_alert = _increment_failure_counter(conn, source_id, error_code)
            if needs_alert:
                _write_alert(conn, source_id, error_code, error_summary)
            conn.commit()
        except Exception:
            conn.rollback()

        # Try Addis Fortune fallback
        config = Config()
        af_result = _try_af_fallback_old(conn, source_id, source["adapter_key"], config.USER_AGENT)
        if af_result:
            return af_result

        return {
            "source_id": source_id,
            "status": "failed",
            "error_code": error_code,
            "detail": error_summary,
        }


def run_all(conn) -> list:
    """
    Run collection for all enabled sources. Returns list of summary dicts.
    One failure never stops the others.
    
    This is the original implementation kept for backward compatibility.
    New code should use Scheduler class directly.
    """
    sources = _load_enabled_sources_old(conn)
    results = []
    config = Config()
    for source in sources:
        result = run_source(conn, source["id"])
        results.append(result)
        time.sleep(config.RATE_LIMIT_DELAY)
    return results


# ── helpers ───────────────────────────────────────────────────────────────────

# NOTE: Some helper functions are kept for backward compatibility with tests.
# New code should use the Scheduler class with dependency injection instead.

# Deprecated functions - kept for test compatibility only:
# - _load_adapter() - use AdapterRegistry.get() instead
# - _classify_error() - use ErrorClassifier.classify() instead
# These functions from the original code are kept for tests that import them directly.


def _load_adapter(adapter_key: str):
    """
    Import adapters/<dir>/adapter.py by adapter_key.
    
    DEPRECATED: Use AdapterRegistry.get() instead.
    Kept for backward compatibility with existing tests.
    
    Tries progressively shorter suffixes:
      cbe_api       → adapters.cbe_api, adapters.cbe
      dashen_html   → adapters.dashen_html, adapters.dashen
      global_html   → adapters.global_html, adapters.global_, adapters.global
      goh_betoch_html → adapters.goh_betoch_html, adapters.goh_betoch
    AF-primary keys (addis_bank_af, hijra_af, nbe_af) return an
    AddisFortuneAdapter instance directly.
    """
    from adapters.addis_fortune.adapter import get_adapter_for_key, AF_SLUG_MAP
    if adapter_key in AF_SLUG_MAP:
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
    """
    Classify exception into (error_code, error_summary).
    
    DEPRECATED: Use ErrorClassifier.classify() instead.
    Kept for backward compatibility with existing tests.
    """
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
    """
    Fetch URL with exponential backoff retries.
    
    DEPRECATED: HttpClient.fetch() is used in the Scheduler class instead.
    Kept for backward compatibility with existing tests that mock this function.
    
    Returns (text, http_status)
    """
    last_exc = None
    # Use Config defaults for backward compatibility
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
    """Delegate fetch entirely to adapter.fetch_raw() which uses Playwright."""
    return adapter.fetch_raw(source_url, user_agent, ssl_verify)


def _load_source_old(conn, source_id: int) -> Optional[dict]:
    """Load source by ID - old implementation for backward compatibility."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, adapter_key, source_url, ssl_verify, schema_fingerprint,
                      default_category, consecutive_failures, last_failure_code
               FROM rate_source WHERE id = %s""",
            (source_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return dict(zip(["id", "adapter_key", "source_url", "ssl_verify",
                     "schema_fingerprint", "default_category",
                     "consecutive_failures", "last_failure_code"], row))


def _load_enabled_sources_old(conn) -> list:
    """Load all enabled sources - old implementation for backward compatibility."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, adapter_key, source_url, ssl_verify, schema_fingerprint,
                      default_category, consecutive_failures, last_failure_code
               FROM rate_source WHERE is_enabled = TRUE
               ORDER BY id"""
        )
        cols = ["id", "adapter_key", "source_url", "ssl_verify",
                "schema_fingerprint", "default_category",
                "consecutive_failures", "last_failure_code"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _check_schema_old(conn, run_id: int, source: dict, adapter, raw_content: str) -> bool:
    """Check schema fingerprint - old implementation without repo parameter."""
    if not hasattr(adapter, "schema_fingerprint"):
        return False
    current_fp = adapter.schema_fingerprint(raw_content)
    stored_fp = source.get("schema_fingerprint")
    if not stored_fp:
        _update_fingerprint_old(conn, source["id"], current_fp)
        return False
    if current_fp != stored_fp:
        _store_raw_capture(conn, run_id, "schema_change", raw_content)
        return True
    return False


def _check_schema(conn, run_id: int, source: dict, adapter, raw_content: str, repo: RateSourceRepository = None) -> bool:
    """
    Compare current schema fingerprint against stored one.
    
    Can be called with or without repo parameter for backward compatibility.
    When repo is provided, uses repo.update_schema_fingerprint().
    When repo is None, uses direct SQL (old behavior).
    
    Returns True if schema changed (so caller can auto-accept after successful parse).
    """
    if not hasattr(adapter, "schema_fingerprint"):
        return False
    current_fp = adapter.schema_fingerprint(raw_content)
    stored_fp = source.get("schema_fingerprint")
    if not stored_fp:
        if repo:
            repo.update_schema_fingerprint(source["id"], current_fp)
        else:
            _update_fingerprint_old(conn, source["id"], current_fp)
        return False
    if current_fp != stored_fp:
        _store_raw_capture(conn, run_id, "schema_change", raw_content)
        return True
    return False


def _update_fingerprint_old(conn, source_id: int, fingerprint: str):
    """Update fingerprint - old implementation."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE rate_source SET schema_fingerprint = %s WHERE id = %s",
            (fingerprint, source_id),
        )


def _update_last_success_old(conn, source_id: int):
    """Update last_success - old implementation."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE rate_source SET last_success_at = now() WHERE id = %s",
            (source_id,),
        )


def _try_af_fallback_old(conn, source_id: int, adapter_key: str, user_agent: str) -> Optional[dict]:
    """AF fallback - old implementation."""
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
        ingest_result = ingest(conn, records, source_id, run_id, fetched_at=fetched_at)

        duration_ms = int((time.monotonic() - t0) * 1000)
        run_status = _run_status(ingest_result)
        finish_run(
            conn, run_id, run_status,
            http_status=http_status,
            records_found=len(records),
            records_accepted=ingest_result.accepted,
            records_flagged=ingest_result.flagged + ingest_result.duplicates,
            duration_ms=duration_ms,
        )
        if run_status in ("success", "partial_success"):
            _update_last_success_old(conn, source_id)
            _reset_failure_counter(conn, source_id)
        conn.commit()
        return {
            "source_id": source_id,
            "status": run_status,
            "accepted": ingest_result.accepted,
            "flagged": ingest_result.flagged,
            "rejected": ingest_result.duplicates,
            "duplicates": ingest_result.duplicates,
            "fallback": "addis_fortune",
        }
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        error_code, error_summary = _classify_error(exc)
        try:
            finish_run(conn, run_id, "failed",
                       error_code=error_code,
                       error_summary=error_summary[:500],
                       duration_ms=duration_ms)
            conn.commit()
        except Exception:
            conn.rollback()
        return None


def _parse(adapter, raw_content: str, category: str = "UNKNOWN") -> list:
    """Call adapter.parse(). Passes category if adapter accepts it.
    Handles ParseResult objects, (records, errors) tuples, and plain lists."""
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
    """Append today's date parameter for sources that require it."""
    from datetime import date
    today = date.today().isoformat()
    # CBE requires ?Date=YYYY-MM-DD
    if adapter_key == "cbe_api":
        sep = "&" if "?" in base_url else "?"
        return f"{base_url}{sep}Date={today}"
    return base_url


def _check_schema(conn, run_id: int, source: dict, adapter, raw_content: str, repo: RateSourceRepository) -> bool:
    """
    Compare current schema fingerprint against stored one.
    Returns True if schema changed (so caller can auto-accept after successful parse).
    No longer raises on change — captures raw and lets parse proceed.
    Only stores fingerprint on first run.
    """
    if not hasattr(adapter, "schema_fingerprint"):
        return False
    current_fp = adapter.schema_fingerprint(raw_content)
    stored_fp = source.get("schema_fingerprint")
    if not stored_fp:
        repo.update_schema_fingerprint(source["id"], current_fp)
        return False
    if current_fp != stored_fp:
        # Capture raw for inspection but do NOT raise — let parse proceed
        _store_raw_capture(conn, run_id, "schema_change", raw_content)
        return True  # caller will auto-accept fingerprint if parse succeeds
    return False


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
    """Increment consecutive_failures. Returns True if alert threshold reached."""
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
        # Alert if threshold reached and we haven't alerted in the last 24h
        if consecutive >= ALERT_AFTER_CONSECUTIVE_FAILURES:
            if alert_sent_at is None or (
                datetime.now(timezone.utc) - alert_sent_at
            ).total_seconds() > 86400:
                return True
    return False


def _write_alert(conn, source_id: int, error_code: str, error_summary: str):
    """Write alert to source_alert table and update alert_sent_at."""
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


def _try_af_fallback(conn, source_id: int, adapter_key: str, user_agent: str) -> Optional[dict]:
    """
    Attempt to collect from Addis Fortune when the primary adapter fails.
    Returns a summary dict on success, None if AF also fails or not mapped.
    """
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
        ingest_result = ingest(conn, records, source_id, run_id, fetched_at=fetched_at)

        duration_ms = int((time.monotonic() - t0) * 1000)
        run_status = _run_status(ingest_result)
        finish_run(
            conn, run_id, run_status,
            http_status=http_status,
            records_found=len(records),
            records_accepted=ingest_result.accepted,
            records_flagged=ingest_result.flagged + ingest_result.duplicates,
            duration_ms=duration_ms,
        )
        if run_status in ("success", "partial_success"):
            # Use repository for consistency
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
        # Use default classifier for consistency
        error_classifier = default_classifier
        error_code, error_summary = error_classifier.classify(exc)
        try:
            finish_run(conn, run_id, "failed",
                       error_code=error_code,
                       error_summary=error_summary[:500],
                       duration_ms=duration_ms)
            conn.commit()
        except Exception:
            conn.rollback()
        return None


def _expire_stale_fallback_current(conn, source_id: int):
    """Retire is_current=TRUE records for collection_date_fallback sources
    whose effective_date is older than FALLBACK_TTL_DAYS. These accumulate
    when a currency disappears from the page for multiple days."""
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE rate_observation
               SET is_current = FALSE
               WHERE source_id = %s
                 AND effective_date_basis = 'collection_date_fallback'
                 AND is_current = TRUE
                 AND effective_date < CURRENT_DATE - %s""",
            (source_id, FALLBACK_TTL_DAYS),
        )
