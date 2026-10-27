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
_POPUP_TIMEOUT = 15000

def fetch_raw(source_url: str, user_agent: str, ssl_verify: bool) -> tuple:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=user_agent)
        page = ctx.new_page()

        page.goto(_HOME_URL, wait_until="commit", timeout=30000)
        page.wait_for_timeout(5000)

        html_parts = []

        try:
            page.click("#exchangerate", timeout=5000)
            page.wait_for_selector(
                "#hustle-popup-id-15 .hustle-layout table, "
                "#hustle-popup-id-15 .hustle-layout .rate",
                timeout=_POPUP_TIMEOUT,
            )
            html_parts.append(page.inner_html("#hustle-popup-id-15"))
        except PWTimeout:
            try:
                page.click("#waighted", timeout=5000)
                page.wait_for_selector(
                    "#hustle-slidein-id-18 .hustle-layout",
                    timeout=_POPUP_TIMEOUT,
                )
                html_parts.append(page.inner_html("#hustle-slidein-id-18"))
            except PWTimeout:
                html_parts.append("")

        try:
            page.keyboard.press("Escape")
        except Exception:
            pass

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

        page_text = page.inner_text("body")
        html_parts.append(f"<div id='_page_text'>{page_text}</div>")

        browser.close()

    combined = "\n".join(html_parts)
    return combined, 200

class AnbesaAdapter(FieldStructureMixin, HTMLTextAdapter):

    FIELD_CONFIG = {}

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def _extract_from_text(self, text: str, soup: BeautifulSoup, **kwargs) -> ParseResult:
        result = ParseResult()

        effective_date = _parse_date(soup)
        date_basis = "source_published" if effective_date else "collection_date_fallback"

        tables = soup.find_all("table")
        for table in tables:
            try:
                records = _parse_table(table, effective_date, date_basis, self)
                result.records.extend(records)
            except Exception as exc:
                result.add_error(f"table:{exc}")

        if not result.records:
            for block in soup.find_all("div", class_=re.compile(r"rate|exchange|currency", re.I)):
                try:
                    records = _parse_div_block(block, effective_date, date_basis, self)
                    result.records.extend(records)
                except Exception as exc:
                    result.add_error(f"div:{exc}")

        return result

    def schema_fingerprint(self, raw_content: str) -> str:
        soup = BeautifulSoup(raw_content, "html.parser")
        tables = soup.find_all("table")
        headers = []
        for t in tables:
            rows = t.find_all("tr")
            if rows:
                headers.append([th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])])
        return hashlib.sha256(str({"tables": len(tables), "headers": headers}).encode()).hexdigest()

def _parse_table(table, effective_date, date_basis, adapter_instance) -> list:
    rows = table.find_all("tr")
    if len(rows) < 2:
        return []

    header = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]
    if not any(kw in " ".join(header) for kw in ["currency", "buying", "selling", "usd"]):
        return []

    has_cash = any("cash" in h for h in header)
    has_trans = any("trans" in h for h in header)
    has_weighted = any("weight" in h for h in header)

    records = []
    for row in rows[1:]:
        cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
        if len(cells) < 3:
            continue

        raw_code = cells[0].strip()
        code = _extract_code(raw_code)
        if not code:
            continue

        if has_cash and has_trans and len(cells) >= 5:
            _add_with_detection(records, code, "cash", cells[1], cells[2], effective_date, date_basis, adapter_instance)
            _add_with_detection(records, code, "transactional", cells[3], cells[4], effective_date, date_basis, adapter_instance)
        elif has_weighted and len(cells) >= 3:
            _add_with_detection(records, code, "weighted_average", cells[1], cells[2], effective_date, date_basis, adapter_instance)
        elif len(cells) >= 3:
            _add_with_detection(records, code, "transactional", cells[1], cells[2], effective_date, date_basis, adapter_instance)

    return records

def _parse_div_block(block, effective_date, date_basis, adapter_instance) -> list:
    text = block.get_text(" ", strip=True)
    matches = re.findall(
        r'\b([A-Z]{3})\b[^0-9]{0,30}(\d{2,3}\.\d{2,4})[^\d]{1,10}(\d{2,3}\.\d{2,4})',
        text
    )
    records = []
    for code, buy_text, sell_text in matches:
        _add_with_detection(records, code, "transactional", buy_text, sell_text, effective_date, date_basis, adapter_instance)
    return records

def _add_with_detection(records, code, expected_category, buy_text, sell_text, eff_date, date_basis, adapter_instance):
    row_dict = {
        "buying": buy_text,
        "selling": sell_text,
    }

    detected_records = adapter_instance.detect_and_emit(
        data=row_dict,
        currency=code,
        effective_date=eff_date,
        effective_date_basis=date_basis
    )

    for rec in detected_records:
        if rec.category == 'UNKNOWN':
            rec.category = normalize_category(expected_category)
        rec.source_record_key = f"{eff_date}:{code}:{rec.category}"
        rec.source_publication_key = str(eff_date) if eff_date else None

    records.extend(detected_records)

def _extract_code(raw: str) -> Optional[str]:
    m = re.search(r'\b([A-Z]{3})\s*$', raw.strip())
    if m:
        return m.group(1)
    m2 = re.match(r'^([A-Z]{3})\b', raw.strip())
    if m2:
        return m2.group(1)
    return None

def _parse_date(soup) -> Optional[date]:
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
    if not raw or str(raw).strip().lower() in ("", "-", "n/a", "no trade"):
        return None
    cleaned = re.sub(r'[^\d.]', '', str(raw))
    try:
        from pipeline.normalize import normalize_rate
        return normalize_rate(cleaned)
    except ValueError:
        return None

_adapter = AnbesaAdapter()

def parse(raw_html: str) -> tuple:
    result = _adapter.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    return _adapter.schema_fingerprint(raw_html)
