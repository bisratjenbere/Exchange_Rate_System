"""
adapters/addis_fortune/adapter.py — Addis Fortune exchange rate aggregator.

Source: https://exchange.addisfortune.news/bank/<slug>
Method: Parse Livewire wire:snapshot JSON embedded in HTML.

Used two ways:
  1. Primary source  — for banks with no own adapter (Addis Bank, Hijra, NBE)
  2. Fallback source — called by runner when a bank's primary adapter fails

Parse rules:
  - Each row has cashBuying/cashSelling + transBuying/transSelling → 2 records/currency
  - applicable_date per row — skip if > STALENESS_DAYS old
  - cashBuying == 0 and cashSelling == 0 → skip cash record (bank doesn't publish cash)
  - source_record_key: "<currency>:cash" / "<currency>:transactional"
  - raw_excerpt includes fallback_source="addis_fortune" for traceability
"""
import json
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import requests
from bs4 import BeautifulSoup

from adapters.base import BankAdapter, ParseResult
from domain.records import AdapterRecord
from field_detection.mixin import FieldStructureMixin
from pipeline.category_normalizer import normalize_category
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "addis_fortune"
BASE_URL = "https://exchange.addisfortune.news/bank/{slug}"
STALENESS_DAYS = 2

# Maps our adapter_key → Addis Fortune bank slug
AF_SLUG_MAP = {
    "abay_html":        "abay-bank-sc",
    "adib_api":         "addis-bank-sc-1",       # Addis International Bank
    "ahadu_html":       "ahadu-bank-sc",
    "amhara_html":      "amhara-bank-sc",
    "anbesa_browser":   "anbesa-bank-1",
    "anbesa_af":         "anbesa-bank-1",
    "awash_ajax":       "awash-bank-sc",
    "boa_html":         "bank-of-abyssinia-sc",
    "berhan_html":      "berhan-international-bank-sc",
    "bunna_html":       "bunna-international-bank-sc",
    "cbe_api":          "commercial-bank-of-ethiopia",
    "cbo_html":         "cooperative-bank-of-oromia-sc",
    "dashen_html":      "dashen-bank-sc",
    "dbe_html":         "development-bank-of-ethiopia",
    "enat_html":        "enat-bank-sc",
    "gadaa_api":        "gadaa-bank-sc",
    "global_html":      "global-bank-ethiopia-sc",
    "goh_betoch_html":  "goh-betoch-bank-sc",
    "hibret_html":      "hibret-bank-sc",
    "nib_html":         "nib-international-bank-sc",
    "oromia_html":      "oromia-international-bank-sc",
    "oromia_af":         "oromia-international-bank-sc",
    "sidama_html":      "sidama-bank-sc",
    "siinqee_html":     "siinqee-bank-sc",
    "siket_html":       "siket-bank",
    "tsedey_html":      "tsedey-bank-sc-1",
    "tsehay_html":      "tsehay-bank-sc",
    "wegagen_api":      "wegagen-bank-sc",
    "zamzam_html":      "zamzam-bank-sc",
    "zemen_ajax":       "zemen-bank-sc",
    # Primary-only (no own adapter):
    "addis_bank_af":    "addis-bank-sc-1",
    "hijra_af":         "hijra-bank-sc",
    "nbe_af":           "national-bank-of-ethiopia",
}

_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_af_date(date_str: str) -> Optional[date]:
    """Parse 'Oct 20, 2026' → date(2026, 10, 20)."""
    try:
        parts = date_str.replace(",", "").split()
        month = _MONTH_MAP.get(parts[0].lower()[:3])
        if not month:
            return None
        return date(int(parts[2]), month, int(parts[1]))
    except (IndexError, ValueError):
        return None


def _safe_rate(val) -> Optional[Decimal]:
    try:
        return normalize_rate(val)
    except (ValueError, TypeError):
        return None


class AddisFortuneAdapter(FieldStructureMixin, BankAdapter):
    """
    Addis Fortune adapter for a specific bank slug.

    Usage:
        adapter = AddisFortuneAdapter("awash-bank-sc")
        raw = adapter.fetch_raw(adapter.get_source_url(), user_agent, ssl_verify=True)
        result = adapter.parse(raw[0])
    """

    # Pattern D: Empty config - field names are self-describing (cashBuying/transBuying)
    FIELD_CONFIG = {}

    def __init__(self, slug: str):
        super().__init__()
        self._slug = slug
        self._url = BASE_URL.format(slug=slug)

    def get_source_url(self) -> str:
        return self._url

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def fetch_raw(self, source_url: str, user_agent: str, ssl_verify: bool = True):
        """Fetch the AF bank page. Returns (html_text, http_status)."""
        headers = {"User-Agent": user_agent}
        resp = requests.get(source_url, headers=headers, timeout=15, verify=ssl_verify)
        return resp.text, resp.status_code

    def parse(self, raw_content: str, **options) -> ParseResult:
        result = ParseResult()
        soup = BeautifulSoup(raw_content, "html.parser")
        snaps = soup.find_all(attrs={"wire:snapshot": True})
        if not snaps:
            result.add_error("no wire:snapshot found")
            return result

        data = json.loads(snaps[0]["wire:snapshot"]).get("data", {})
        exchanges = data.get("exchanges", [])
        if not exchanges or not isinstance(exchanges[0], list):
            result.add_error("exchanges data missing or unexpected structure")
            return result

        rows = exchanges[0]  # list of [rate_dict, meta_dict]
        today = date.today()

        for row_pair in rows:
            row = row_pair[0] if isinstance(row_pair, list) else row_pair
            if not isinstance(row, dict):
                continue

            currency = row.get("currency", "").strip()
            if not currency:
                continue

            # Staleness check
            applicable_date = _parse_af_date(row.get("applicable_date", ""))
            if applicable_date is None or (today - applicable_date).days > STALENESS_DAYS:
                result.add_warning(f"{currency}: stale date {row.get('applicable_date')}, skipped")
                continue

            # Use field detection to emit records based on field structure
            mapping_notes = [
                f"af_slug={self._slug}",
                f"applicable_date={row.get('applicable_date')}"
            ]

            detected_records = self.detect_and_emit(
                data=row,
                currency=currency,
                source_record_id=currency,
                effective_date=applicable_date,
                effective_date_basis="source_published",  # AF publishes dates
                currency_name=row.get("currency_name"),
                mapping_notes=mapping_notes
            )

            result.records.extend(detected_records)

        return result


def get_adapter_for_key(adapter_key: str) -> Optional["AddisFortuneAdapter"]:
    """Return an AddisFortuneAdapter for the given adapter_key, or None if not mapped."""
    slug = AF_SLUG_MAP.get(adapter_key)
    if not slug:
        return None
    return AddisFortuneAdapter(slug)
