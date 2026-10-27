import hashlib
import json
import re
import time
import logging
from datetime import date
from typing import Optional

import requests

from adapters.base import JSONAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin

try:
    from http_clients.cloudflare_bypass import fetch_with_cloudflare_bypass
    CLOUDFLARE_BYPASS_AVAILABLE = True
except ImportError:
    CLOUDFLARE_BYPASS_AVAILABLE = False

logger = logging.getLogger(__name__)

ADAPTER_KEY = "awash_ajax"
SOURCE_URL = "https://awashbank.com/wp-admin/admin-ajax.php"
_HOME_URL = "https://awashbank.com/"
_AJAX_URL = "https://awashbank.com/wp-admin/admin-ajax.php"

class AwashAdapter(FieldStructureMixin, JSONAdapter):

    FIELD_CONFIG = {
        "field_mappings": {
            "buying": "cash",
            "selling": "cash",
            "transaction_buying": "transactional",
            "transaction_selling": "transactional",
            "weighted_buying_average": "weighted_average",
            "weighted_selling_average": "weighted_average",
        },
        "default_category": "cash",
    }

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def _process_data(self, data, **options) -> ParseResult:
        result = ParseResult()

        if not data.get("success"):
            result.add_error(f"success_false:{data.get('data')}")
            return result

        inner = data.get("data", {})
        rates = inner.get("rates", {})
        if not isinstance(rates, dict):
            result.add_error("rates_not_dict")
            return result

        effective_date = _parse_date(inner.get("date"))
        date_basis = "source_published" if effective_date else "collection_date_fallback"

        for currency, rate_data in rates.items():
            if not isinstance(rate_data, dict):
                continue
            try:
                detected_records = self.detect_and_emit(
                    data=rate_data,
                    currency=currency,
                    effective_date=effective_date,
                    effective_date_basis=date_basis,
                    source_record_id=None,
                    source_publication_id=str(effective_date) if effective_date else None
                )

                filtered_records = [
                    rec for rec in detected_records
                    if rec.category != 'UNKNOWN'
                ]

                result.records.extend(filtered_records)

                unknown_count = len(detected_records) - len(filtered_records)
                if unknown_count > 0:
                    result.add_warning(f"{currency}: filtered {unknown_count} UNKNOWN category record(s)")

            except Exception as exc:
                result.add_error(f"currency:{currency}:{exc}")

        return result

    def schema_fingerprint(self, raw_content: str) -> str:
        try:
            data = json.loads(raw_content)
            currencies = sorted(data["data"]["rates"].keys())
            rate_keys = sorted(next(iter(data["data"]["rates"].values())).keys())
            payload = json.dumps({"currencies": currencies, "rate_keys": rate_keys}, separators=(",", ":"))
            return hashlib.sha256(payload.encode()).hexdigest()
        except Exception:
            pass
        return hashlib.sha256(b"awash:unparseable").hexdigest()

def fetch_raw(source_url: str, user_agent: str, ssl_verify: bool) -> tuple:
    if CLOUDFLARE_BYPASS_AVAILABLE:
        try:
            logger.info("Attempting to fetch Awash rates with Playwright (JS execution)")
            return _fetch_with_playwright_and_nonce(user_agent, ssl_verify)
        except Exception as e:
            logger.warning(f"Playwright method failed: {e}. Trying alternative...")

    try:
        logger.info("Falling back to traditional fetch method")
        return _fetch_traditional(user_agent, ssl_verify)
    except Exception as e:
        logger.error(f"All fetch strategies failed: {e}")
        raise

def _fetch_with_playwright_and_nonce(user_agent: str, ssl_verify: bool) -> tuple:
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        raise RuntimeError("Playwright not available. Install with: pip install playwright")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=user_agent,
            viewport={'width': 1920, 'height': 1080},
        )

        page = context.new_page()

        try:
            logger.info(f"Loading {_HOME_URL}")
            page.goto(_HOME_URL, timeout=30000, wait_until='domcontentloaded')

            time.sleep(3)

            nonce = page.evaluate("""
                () => {
                    // Try common WordPress nonce locations
                    if (typeof exchangeRatesVars !== 'undefined' && exchangeRatesVars.nonce) {
                        return exchangeRatesVars.nonce;
                    }
                    if (typeof wpData !== 'undefined' && wpData.nonce) {
                        return wpData.nonce;
                    }
                    if (typeof ajaxData !== 'undefined' && ajaxData.nonce) {
                        return ajaxData.nonce;
                    }

                    // Try to find it in any global object
                    for (let key in window) {
                        try {
                            if (window[key] && typeof window[key] === 'object' && window[key].nonce) {
                                return window[key].nonce;
                            }
                        } catch(e) {}
                    }

                    // Try to extract from widget data attribute
                    const widget = document.querySelector('[data-nonce]');
                    if (widget) {
                        return widget.getAttribute('data-nonce');
                    }

                    return null;
                }
            """)

            if nonce:
                logger.info(f"✅ Nonce extracted from JavaScript: {nonce[:10]}...")
                browser.close()
                return _fetch_ajax_with_nonce(nonce, user_agent, ssl_verify)

            logger.warning("No nonce found in JavaScript runtime")

            rates_data = page.evaluate("""
                () => {
                    // Look for exchange rate data in the DOM
                    const widget = document.querySelector('.exchange-rates-ajax-container');
                    if (widget && widget.textContent) {
                        return widget.textContent;
                    }
                    return null;
                }
            """)

            if rates_data:
                logger.info("Found exchange rates in DOM, trying to parse...")
                browser.close()
                try:
                    data = json.loads(rates_data)
                    return json.dumps(data), 200
                except:
                    pass

            logger.warning("Attempting AJAX call without nonce...")
            browser.close()
            return _fetch_ajax_without_nonce(user_agent, ssl_verify)

        except Exception as e:
            logger.error(f"Playwright execution failed: {e}")
            browser.close()
            raise
        finally:
            if browser:
                try:
                    browser.close()
                except:
                    pass

def _fetch_traditional(user_agent: str, ssl_verify: bool) -> tuple:
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    homepage_html = None
    if CLOUDFLARE_BYPASS_AVAILABLE:
        try:
            logger.info("Attempting to fetch homepage with Cloudflare bypass")
            homepage_html = fetch_with_cloudflare_bypass(_HOME_URL, timeout=30)
            logger.info(f"Homepage fetched: {len(homepage_html)} bytes")
        except Exception as e:
            logger.warning(f"Cloudflare bypass failed: {e}. Trying standard request...")

    if not homepage_html:
        try:
            resp = requests.get(_HOME_URL, headers=headers, timeout=15, verify=ssl_verify)
            if resp.status_code != 200:
                raise RuntimeError(f"Homepage HTTP {resp.status_code}")
            homepage_html = resp.text
        except Exception as e:
            logger.error(f"Failed to fetch homepage: {e}")
            raise

    nonce = _extract_nonce_dynamic(homepage_html)

    if nonce:
        logger.info(f"Nonce extracted: {nonce[:10]}...")
        return _fetch_ajax_with_nonce(nonce, user_agent, ssl_verify)

    logger.warning("Nonce not found - attempting direct AJAX call without nonce")
    return _fetch_ajax_without_nonce(user_agent, ssl_verify)

def _extract_js_url(html: str) -> Optional[str]:
    m = re.search(
        r'src=["\']+(https://awashbank\.com/wp-content/litespeed/js/[^"\']+\.js)',
        html,
    )
    return m.group(1) if m else None

def _extract_nonce(js_text: str) -> Optional[str]:
    m = re.search(r'exchangeRatesVars\s*=\s*\{[^}]*"nonce"\s*:\s*"([a-f0-9]+)"', js_text)
    return m.group(1) if m else None

def _extract_nonce_dynamic(html: str) -> Optional[str]:
    patterns = [
        r'exchangeRatesVars\s*=\s*\{[^}]*"nonce"\s*:\s*"([a-f0-9]+)"',
        r'var\s+\w+\s*=\s*\{[^}]*["\']nonce["\']\s*:\s*["\']([a-f0-9]+)["\']',
        r'["\']nonce["\']\s*:\s*["\']([a-f0-9]+)["\']',
        r'nonce[\'"]?\s*[:=]\s*[\'"]([a-f0-9]+)[\'"]',
    ]

    for i, pattern in enumerate(patterns, 1):
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            nonce = match.group(1)
            logger.info(f"Nonce found with pattern #{i}: {nonce[:10]}...")
            return nonce

    data_pattern = r'data-[^=]*nonce[^=]*=["\']([a-f0-9]+)["\']'
    match = re.search(data_pattern, html, re.IGNORECASE)
    if match:
        nonce = match.group(1)
        logger.info(f"Nonce found in data attribute: {nonce[:10]}...")
        return nonce

    js_urls = re.findall(r'<script[^>]*src=["\']([^"\']*)["\']', html)
    for js_url in js_urls:
        if not js_url.startswith('http'):
            js_url = 'https://awashbank.com' + (js_url if js_url.startswith('/') else '/' + js_url)

        if 'awashbank.com' in js_url and any(kw in js_url.lower() for kw in ['exchange', 'widget', 'custom', 'theme', 'main']):
            try:
                logger.debug(f"Checking JS file for nonce: {js_url}")
                js_resp = requests.get(js_url, timeout=10)
                if js_resp.status_code == 200:
                    for pattern in patterns:
                        match = re.search(pattern, js_resp.text, re.IGNORECASE)
                        if match:
                            nonce = match.group(1)
                            logger.info(f"Nonce found in external JS: {nonce[:10]}...")
                            return nonce
            except Exception as e:
                logger.debug(f"Failed to check JS file: {e}")

    logger.warning("Nonce not found with any pattern")
    return None

def _fetch_ajax_with_nonce(nonce: str, user_agent: str, ssl_verify: bool) -> tuple:
    time.sleep(1)

    ajax_headers = {
        "User-Agent": user_agent,
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": _HOME_URL,
        "X-Requested-With": "XMLHttpRequest",
    }
    post_data = {
        "action": "get_exchange_rates",
        "nonce": nonce,
        "shortcode_type": "rates_widgest",
    }

    ajax_resp = requests.post(
        _AJAX_URL, data=post_data, headers=ajax_headers,
        timeout=15, verify=ssl_verify,
    )
    return ajax_resp.text, ajax_resp.status_code

def _fetch_ajax_without_nonce(user_agent: str, ssl_verify: bool) -> tuple:
    ajax_headers = {
        "User-Agent": user_agent,
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": _HOME_URL,
        "X-Requested-With": "XMLHttpRequest",
    }

    post_data = {
        "action": "get_exchange_rates",
    }

    try:
        ajax_resp = requests.post(
            _AJAX_URL, data=post_data, headers=ajax_headers,
            timeout=15, verify=ssl_verify,
        )

        try:
            data = json.loads(ajax_resp.text)
            if data.get('success'):
                logger.info("✅ AJAX call succeeded without nonce!")
                return ajax_resp.text, ajax_resp.status_code
        except json.JSONDecodeError:
            pass

        logger.error("AJAX call without nonce returned invalid response")
        return ajax_resp.text, ajax_resp.status_code

    except Exception as e:
        logger.error(f"AJAX call without nonce failed: {e}")
        raise RuntimeError(f"Failed to fetch exchange rates: {e}")

def _parse_date(raw) -> Optional[date]:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw).strip()[:10])
    except ValueError:
        return None

def parse(raw_json: str) -> tuple:
    adapter = AwashAdapter()
    result = adapter.parse(raw_json)
    return result.records, result.errors

def schema_fingerprint(raw_json: str) -> str:
    return AwashAdapter().schema_fingerprint(raw_json)
