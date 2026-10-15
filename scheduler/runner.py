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

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
REQUEST_TIMEOUT = 15       # seconds
RATE_LIMIT_DELAY = 2.0     # seconds between fetches
MAX_RETRIES = 2
RETRY_DELAYS = [2, 10, 30]  # exponential backoff seconds between HTTP retries
ALERT_AFTER_CONSECUTIVE_FAILURES = 2  # alert after this many consecutive failures
def run_source(conn, source_id: int) -> dict:
    """
    Run collection for one source. Returns a summary dict.
    Never raises — all errors are caught and recorded.
    """
    source = _load_source(conn, source_id)
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
        if fetch_method == "browser":
            raw_content, http_status = _fetch_browser(adapter, source_url, ssl_verify)
        elif hasattr(adapter, "fetch_raw"):
            raw_content, http_status = adapter.fetch_raw(
                source_url, USER_AGENT, ssl_verify
            )
        else:
            post_data = getattr(adapter, "FETCH_POST_DATA", None)
            extra_headers = getattr(adapter, "FETCH_HEADERS", None)
            raw_content, http_status = _fetch(
                _build_url(source_url, source["adapter_key"]), ssl_verify,
                post_data=post_data, extra_headers=extra_headers,
            )

        # 4. Schema fingerprint check — try-parse-first approach:
        #    If fingerprint changed, capture raw but continue. If parse then
        #    succeeds, auto-accept the new fingerprint. Only hard-fail if
        #    parse itself raises.
        schema_changed = _check_schema(conn, run_id, source, adapter, raw_content)

        # 5. Parse
        category = source.get("default_category") or "UNKNOWN"
        records = _parse(adapter, raw_content, category)

        # 6. Auto-accept new fingerprint now that parse succeeded
        if schema_changed:
            new_fp = adapter.schema_fingerprint(raw_content)
            _update_fingerprint(conn, source_id, new_fp)

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
            _update_last_success(conn, source_id)
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
            # Increment failure counter and check if alert needed
            needs_alert = _increment_failure_counter(conn, source_id, error_code)
            if needs_alert:
                _write_alert(conn, source_id, error_code, error_summary)
            conn.commit()
        except Exception:
            conn.rollback()

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
    """
    sources = _load_enabled_sources(conn)
    results = []
    for source in sources:
        result = run_source(conn, source["id"])
        results.append(result)
        time.sleep(RATE_LIMIT_DELAY)
    return results


# ── helpers ───────────────────────────────────────────────────────────────────

def _load_source(conn, source_id: int) -> Optional[dict]:
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


def _load_enabled_sources(conn) -> list:
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


def _fetch_browser(adapter, source_url: str, ssl_verify: bool) -> tuple:
    """Delegate fetch entirely to adapter.fetch_raw() which uses Playwright."""
    return adapter.fetch_raw(source_url, USER_AGENT, ssl_verify)


def _fetch(url: str, ssl_verify: bool, post_data: dict = None,
           extra_headers: dict = None) -> tuple:
    """Fetch URL with exponential backoff retries. Returns (text, http_status)."""
    last_exc = None
    headers = {"User-Agent": USER_AGENT}
    if extra_headers:
        headers.update(extra_headers)
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            if post_data is not None:
                resp = requests.post(
                    url, data=post_data, headers=headers,
                    timeout=REQUEST_TIMEOUT, verify=ssl_verify,
                )
            else:
                resp = requests.get(
                    url, headers=headers,
                    timeout=REQUEST_TIMEOUT, verify=ssl_verify,
                )
            if resp.status_code == 200:
                return resp.text, resp.status_code
            raise RuntimeError(f"HTTP {resp.status_code} from {url}")
        except Exception as exc:
            last_exc = exc
    raise last_exc


def _load_adapter(adapter_key: str):
    """
    Import adapters/<dir>/adapter.py by adapter_key.
    Tries progressively shorter suffixes:
      cbe_api       → adapters.cbe_api, adapters.cbe
      dashen_html   → adapters.dashen_html, adapters.dashen
      global_html   → adapters.global_html, adapters.global_, adapters.global
      goh_betoch_html → adapters.goh_betoch_html, adapters.goh_betoch
    """
    parts = adapter_key.split("_")
    candidates = [adapter_key]
    # drop last segment progressively: cbe_api→cbe, goh_betoch_html→goh_betoch
    for i in range(len(parts) - 1, 0, -1):
        candidates.append("_".join(parts[:i]))
    # also try with trailing underscore (global_ directory)
    candidates.append(adapter_key.rsplit("_", 1)[0] + "_")

    for name in dict.fromkeys(candidates):  # preserve order, deduplicate
        try:
            return importlib.import_module(f"adapters.{name}.adapter")
        except ModuleNotFoundError:
            continue
    raise ImportError(f"No adapter module found for adapter_key={adapter_key!r}")


def _parse(adapter, raw_content: str, category: str = "UNKNOWN") -> list:
    """Call adapter.parse(). Passes category if adapter accepts it.
    Handles both (records, errors) and plain list returns."""
    import inspect
    sig = inspect.signature(adapter.parse)
    if "category" in sig.parameters:
        result = adapter.parse(raw_content, category=category)
    else:
        result = adapter.parse(raw_content)
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


def _check_schema(conn, run_id: int, source: dict, adapter, raw_content: str) -> bool:
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
        _update_fingerprint(conn, source["id"], current_fp)
        return False
    if current_fp != stored_fp:
        # Capture raw for inspection but do NOT raise — let parse proceed
        _store_raw_capture(conn, run_id, "schema_change", raw_content)
        return True  # caller will auto-accept fingerprint if parse succeeds
    return False


def _update_fingerprint(conn, source_id: int, fingerprint: str):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE rate_source SET schema_fingerprint = %s WHERE id = %s",
            (fingerprint, source_id),
        )


def _store_raw_capture(conn, run_id: int, reason: str, raw_content: str):
    content_hash = hashlib.sha256(raw_content.encode()).hexdigest()
    record_raw_capture(conn, run_id, reason, content_hash)


def _run_status(result) -> str:
    if result.rejected > 0 and result.accepted == 0:
        return "failed"
    if result.rejected > 0 or result.errors:
        return "partial_success"
    return "success"


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


def _update_last_success(conn, source_id: int):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE rate_source SET last_success_at = now() WHERE id = %s",
            (source_id,),
        )


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


FALLBACK_TTL_DAYS = 3  # retire fallback-date current records older than this


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
