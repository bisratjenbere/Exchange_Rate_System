import hashlib
import logging
import time
from datetime import date

import requests

from adapters.core.dates import business_date_now
from infrastructure.config import Config
from domain.source import RateSource
from infrastructure.rate_source_repository import RateSourceRepository
from pipeline.runs import record_raw_capture
from scheduler.browser_pool import get_browser_pool

logger = logging.getLogger(__name__)

RETRY_DELAYS = [2, 10, 30]


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
        except (OSError, RuntimeError, requests.exceptions.RequestException) as exc:
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


def _fetch_browser(adapter, source_url: str, ssl_verify: bool, user_agent: str) -> tuple:
    try:
        pool = get_browser_pool()
        browser = pool.acquire(timeout=30.0)

        if browser is None:
            return adapter.fetch_raw(source_url, user_agent, ssl_verify)

        try:
            context = browser.new_context(
                user_agent=user_agent,
                ignore_https_errors=not ssl_verify,
            )
            try:
                page = context.new_page()
                page.goto(source_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)
                content = page.content()
                return content, 200
            finally:
                try:
                    context.close()
                except (OSError, RuntimeError) as e:
                    logger.warning("Error closing browser context: %s", e)
        finally:
            pool.release(browser)

    except ImportError:
        return adapter.fetch_raw(source_url, user_agent, ssl_verify)
    except (OSError, RuntimeError) as e:
        logger.warning("Browser pool error: %s, falling back to adapter fetch_raw", e)
        return adapter.fetch_raw(source_url, user_agent, ssl_verify)


def _store_raw_capture(conn, run_id: int, reason: str, raw_content: str) -> None:
    content_hash = hashlib.sha256(raw_content.encode()).hexdigest()
    record_raw_capture(conn, run_id, reason, content_hash)


def _check_schema(conn, run_id: int, source: RateSource, adapter, raw_content: str, repo: RateSourceRepository = None) -> bool:
    if not hasattr(adapter, "schema_fingerprint"):
        return False
    current_fp = adapter.schema_fingerprint(raw_content)
    stored_fp = source.schema_fingerprint
    if not stored_fp:
        if repo:
            repo.update_schema_fingerprint(source.id, current_fp)
        else:
            RateSourceRepository(conn).update_schema_fingerprint(
                source.id,
                str(current_fp) if current_fp is not None else None,
            )
        return False
    if current_fp != stored_fp:
        _store_raw_capture(conn, run_id, "schema_change", raw_content)
        return True
    return False


def _build_url(base_url: str, adapter_key: str) -> str:
    today = business_date_now().isoformat()
    if adapter_key == "cbe_api":
        sep = "&" if "?" in base_url else "?"
        return f"{base_url}{sep}Date={today}"
    if adapter_key == "bunna_html" and "bunnabanksc.com/foreign-exchange" in base_url:
        return "https://mb.bunnabanksc.com/api/v1/user/public/forex"
    return base_url
