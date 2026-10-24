"""
adapters/anbesa/adapter.py — Anbesa International Bank (Playwright browser).

The exchange rate data is in two Hustle popups, rendered only after JS executes:
  - #exchangerate click → module 15 popup → cash + transactional rates
  - #exchange click     → module 10 popup → weighted average rates

fetch_raw() uses Playwright to:
  1. Load https://anbesabank.com/
  2. Click #exchangerate, wait for popup content, extract HTML
  3. Click #exchange, wait for popup content, extract HTML
  4. Return combined HTML of both popups as raw_content

parse() extracts rates from the combined HTML.

Rate structure inside popups (table rows):
  Currency | Cash Buying | Cash Selling | Trans Buying | Trans Selling
  Currency | Weighted Buying | Weighted Selling

Date: extracted from page text near "Applicable" or "Date" heading.

Parse rules:
- Partial failure: returns (records, errors). Never raises.

MIGRATION NOTE: Migrated to FieldStructureMixin for automatic category detection.
"""
import hashlib
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from bs4 import BeautifulSoup

from adapters.base import HTMLTextAdapter, ParseResult
from domain.records import AdapterRecord
from field_detection.mixin import FieldStructureMixin
from pipeline.category_normalizer import normalize_category

ADAPTER_KEY = "anbesa_browser"
SOURCE_URL = "https://anbesabank.com/"
FETCH_METHOD = "browser"

_HOME_URL = "https://anbesabank.com/"
_POPUP_TIMEOUT = 15000   # ms to wait for popup content


# ============================================================================
# CUSTOM FETCH FUNCTION (browser-based)
# ============================================================================

def fetch_raw(source_url: str, user_agent: str, ssl_verify: bool) -> tuple:
    """Launch Playwright, click both exchange rate triggers, return combined HTML."""
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=user_agent)
        page = ctx.new_page()

        page.goto(_HOME_URL, wait_until="commit", timeout=30000)
        page.wait_for_timeout(5000)  # let JS render popups

        html_parts = []

        # Popup 1: cash + transactional rates
        try:
            page.click("#exchangerate", timeout=5000)
            page.wait_for_selector(
                "#hustle-popup-id-15 .hustle-layout table, "
                "#hustle-popup-id-15 .hustle-layout .rate",
                timeout=_POPUP_TIMEOUT,
            )
            html_parts.append(page.inner_html("#hustle-popup-id-15"))
        except PWTimeout:
            # Try the slidein as fallback
            try:
                page.click("#waighted", timeout=5000)
                page.wait_for_selector(
                    "#hustle-slidein-id-18 .hustle-layout",
                    timeout=_POPUP_TIMEOUT,
                )
                html_parts.append(page.inner_html("#hustle-slidein-id-18"))
            except PWTimeout:
                html_parts.append("")

        # Close popup before opening next
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass

        # Popup 2: weighted average rates
        try:
            page.click("#exchange", timeout=5000)
            page.wait_for_selector(
                "#hustle-popup-id-10 .hustle-layout table, "
                "#hustle-popup-id-10 .hustle-layout .rate",
                timeout=_POPUP_TIMEOUT,
            )
            html_parts.append(page.inner_html("#hustle-popup-id-10"))
        except PWTimeout:
            html_parts.append("")

        # Also grab full page text for date extraction
        page_text = page.inner_text("body")
        html_parts.append(f"<div id='_page_text'>{page_text}</div>")

        browser.close()

    combined = "\n".join(html_parts)
    return combined, 200


# ============================================================================
# ADAPTER CLASS
# ============================================================================

class AnbesaAdapter(FieldStructureMixin, HTMLTextAdapter):
    """
    Anbesa Bank adapter using Playwright browser automation.
    
    Uses field detection for automatic category discovery from table headers.
    """
    
    FIELD_CONFIG = {}
    
    def get_source_url(self) -> str:
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        return ADAPTER_KEY
    
    def _extract_from_text(self, text: str, soup: BeautifulSoup, **kwargs) -> ParseResult:
        """Extract rates from combined popup HTML."""
        result = ParseResult()
        
        effective_date = _parse_date(soup)
        date_basis = "source_published" if effective_date else "collection_date_fallback"
        
        # Find all tables in the combined HTML
        tables = soup.find_all("table")
        for table in tables:
            try:
                records = _parse_table(table, effective_date, date_basis, self)
                result.records.extend(records)
            except Exception as exc:
                result.add_error(f"table:{exc}")
        
        # If no tables, try div-based layout (same pattern as Shabelle)
        if not result.records:
            for block in soup.find_all("div", class_=re.compile(r"rate|exchange|currency", re.I)):
                try:
                    records = _parse_div_block(block, effective_date, date_basis, self)
                    result.records.extend(records)
                except Exception as exc:
                    result.add_error(f"div:{exc}")
        
        return result
    
    def schema_fingerprint(self, raw_content: str) -> str:
        """Hash table count and headers."""
        soup = BeautifulSoup(raw_content, "html.parser")
        tables = soup.find_all("table")
        headers = []
        for t in tables:
            rows = t.find_all("tr")
            if rows:
                headers.append([th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])])
        return hashlib.sha256(str({"tables": len(tables), "headers": headers}).encode()).hexdigest()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _parse_table(table, effective_date, date_basis, adapter_instance) -> list:
    """Parse a table element to extract rate records using field detection."""
    rows = table.find_all("tr")
    if len(rows) < 2:
        return []

    # Detect header to understand column layout
    header = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]
    if not any(kw in " ".join(header) for kw in ["currency", "buying", "selling", "usd"]):
        return []

    # Determine category from header
    has_cash = any("cash" in h for h in header)
    has_trans = any("trans" in h for h in header)
    has_weighted = any("weight" in h for h in header)

    records = []
    for row in rows[1:]:
        cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
        if len(cells) < 3:
            continue

        # Extract currency code — first cell, strip name
        raw_code = cells[0].strip()
        code = _extract_code(raw_code)
        if not code:
            continue

        if has_cash and has_trans and len(cells) >= 5:
            # Cash Buying | Cash Selling | Trans Buying | Trans Selling
            _add_with_detection(records, code, "cash", cells[1], cells[2], effective_date, date_basis, adapter_instance)
            _add_with_detection(records, code, "transactional", cells[3], cells[4], effective_date, date_basis, adapter_instance)
        elif has_weighted and len(cells) >= 3:
            _add_with_detection(records, code, "weighted_average", cells[1], cells[2], effective_date, date_basis, adapter_instance)
        elif len(cells) >= 3:
            _add_with_detection(records, code, "transactional", cells[1], cells[2], effective_date, date_basis, adapter_instance)

    return records


def _parse_div_block(block, effective_date, date_basis, adapter_instance) -> list:
    """Fallback: parse div-based rate layout using field detection."""
    text = block.get_text(" ", strip=True)
    # Look for pattern: CODE Name buy sell
    matches = re.findall(
        r'\b([A-Z]{3})\b[^0-9]{0,30}(\d{2,3}\.\d{2,4})[^\d]{1,10}(\d{2,3}\.\d{2,4})',
        text
    )
    records = []
    for code, buy_text, sell_text in matches:
        _add_with_detection(records, code, "transactional", buy_text, sell_text, effective_date, date_basis, adapter_instance)
    return records


def _add_with_detection(records, code, expected_category, buy_text, sell_text, eff_date, date_basis, adapter_instance):
    """Helper to add a record using field detection."""
    # Create dict with generic field names
    row_dict = {
        "buying": buy_text,
        "selling": sell_text,
    }
    
    # Use field detection
    detected_records = adapter_instance.detect_and_emit(
        data=row_dict,
        currency=code,
        effective_date=eff_date,
        effective_date_basis=date_basis
    )
    
    # Context-based category override: table header/position determines category
    for rec in detected_records:
        if rec.category == 'UNKNOWN':
            rec.category = normalize_category(expected_category)
        rec.source_record_key = f"{eff_date}:{code}:{rec.category}"
        rec.source_publication_key = str(eff_date) if eff_date else None
    
    records.extend(detected_records)


def _extract_code(raw: str) -> Optional[str]:
    """Extract ISO code from strings like 'United States DollarUSD' or 'USD'."""
    # Try trailing uppercase code first
    m = re.search(r'\b([A-Z]{3})\s*$', raw.strip())
    if m:
        return m.group(1)
    # Try leading uppercase code
    m2 = re.match(r'^([A-Z]{3})\b', raw.strip())
    if m2:
        return m2.group(1)
    return None


def _parse_date(soup) -> Optional[date]:
    """Extract date from page text."""
    text = soup.get_text(" ")
    for pattern in [
        r'(\d{1,2})[/-](\w+)[/-]\s*(\d{4})',
        r'(\w+)\s+(\d{1,2}),?\s+(\d{4})',
        r'(\d{4}-\d{2}-\d{2})',
    ]:
        m = re.search(pattern, text)
        if m:
            raw = m.group(0).strip()
            for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y",
                        "%d-%B-%Y", "%d-%b-%Y"):
                try:
                    return datetime.strptime(raw, fmt).date()
                except ValueError:
                    continue
    return None


def _safe_rate(raw) -> Optional[Decimal]:
    """Safely parse rate value."""
    if not raw or str(raw).strip().lower() in ("", "-", "n/a", "no trade"):
        return None
    # Strip currency symbols / "Birr"
    cleaned = re.sub(r'[^\d.]', '', str(raw))
    try:
        from pipeline.normalize import normalize_rate
        return normalize_rate(cleaned)
    except ValueError:
        return None


# ============================================================================
# MODULE-LEVEL FUNCTIONS (backward compatibility)
# ============================================================================

_adapter = AnbesaAdapter()


def parse(raw_html: str) -> tuple:
    """
    Parse combined popup HTML.
    Backward-compatible wrapper that returns (records, errors) tuple.
    """
    result = _adapter.parse(raw_html)
    return result.records, result.errors


def schema_fingerprint(raw_html: str) -> str:
    """Hash table count and headers."""
    return _adapter.schema_fingerprint(raw_html)
