import hashlib
import json
import requests
from datetime import date
from typing import Optional
from domain.records import AdapterRecord
from adapters.banks.addis_fortune_new import AddisFortuneAdapter as CleanAFAdapter
from adapters.core.contract import ParseContext, ParseOutcome, Severity

ADAPTER_KEY = "addis_fortune"
BASE_URL = "https://exchange.addisfortune.news/bank/{slug}"
STALENESS_DAYS = 2

AF_SLUG_MAP = {
    "abay_html": "abay-bank-sc",
    "adib_api": "addis-bank-sc-1",
    "ahadu_html": "ahadu-bank-sc",
    "amhara_html": "amhara-bank-sc",
    "anbesa_browser": "anbesa-bank-1",
    "anbesa_af": "anbesa-bank-1",
    "awash_ajax": "awash-bank-sc",
    "boa_html": "bank-of-abyssinia-sc",
    "berhan_html": "berhan-international-bank-sc",
    "bunna_html": "bunna-international-bank-sc",
    "cbe_api": "commercial-bank-of-ethiopia",
    "cbo_html": "cooperative-bank-of-oromia-sc",
    "dashen_html": "dashen-bank-sc",
    "dbe_html": "development-bank-of-ethiopia",
    "enat_html": "enat-bank-sc",
    "gadaa_api": "gadaa-bank-sc",
    "global_html": "global-bank-ethiopia-sc",
    "goh_betoch_html": "goh-betoch-bank-sc",
    "hibret_html": "hibret-bank-sc",
    "nib_html": "nib-international-bank-sc",
    "oromia_html": "oromia-international-bank-sc",
    "oromia_af": "oromia-international-bank-sc",
    "sidama_html": "sidama-bank-sc",
    "siinqee_html": "siinqee-bank-sc",
    "siket_html": "siket-bank",
    "tsedey_html": "tsedey-bank-sc-1",
    "tsehay_html": "tsehay-bank-sc",
    "wegagen_api": "wegagen-bank-sc",
    "zamzam_html": "zamzam-bank-sc",
    "zemen_ajax": "zemen-bank-sc",
    "hijra_af": "hijra-bank-sc",
    "nbe_af": "national-bank-of-ethiopia",
}

class ParseResult:
    def __init__(self, records=None, errors=None, warnings=None):
        self.records = records if records is not None else []
        self.errors = errors if errors is not None else []
        self.warnings = warnings if warnings is not None else []

    def add_error(self, err):
        self.errors.append(err)

    def add_warning(self, warn):
        self.warnings.append(warn)

class AddisFortuneAdapter:
    def __init__(self, slug: str):
        self.slug = slug
        self._url = BASE_URL.format(slug=slug)
        self._clean = CleanAFAdapter(slug=slug)

    def get_source_url(self) -> str:
        return self._url

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def fetch_raw(self, source_url: str, user_agent: str, ssl_verify: bool = True):
        headers = {"User-Agent": user_agent}
        resp = requests.get(source_url, headers=headers, timeout=15, verify=ssl_verify)
        return resp.text, resp.status_code

    def parse(self, raw_content: str, **options):
        ctx = ParseContext(category="cash", collection_date=date.today(), source_id=0)
        outcome = self._clean.parse(raw_content, ctx)
        records = list(outcome.records)
        errors = [i.detail for i in outcome.issues if i.severity == Severity.ERROR]
        warnings = [i.detail for i in outcome.issues if i.severity == Severity.WARNING]
        return ParseResult(records=records, errors=errors, warnings=warnings)

    def schema_fingerprint(self, raw_content: str) -> str:
        ctx = ParseContext(category="cash", collection_date=date.today(), source_id=0)
        outcome = self._clean.parse(raw_content, ctx)
        if outcome.structure_hash:
            return outcome.structure_hash
        return hashlib.sha256(raw_content.encode("utf-8", errors="ignore")).hexdigest()

def get_adapter_for_key(adapter_key: str) -> Optional[AddisFortuneAdapter]:
    slug = AF_SLUG_MAP.get(adapter_key)
    if not slug:
        return None
    return AddisFortuneAdapter(slug)

def parse(raw_content: str, slug: Optional[str] = None, **options) -> ParseResult:
    if not slug:
        raise ValueError("requires 'slug' parameter")
    adapter = AddisFortuneAdapter(slug)
    return adapter.parse(raw_content, **options)

def schema_fingerprint(raw_content: str, slug: Optional[str] = None) -> str:
    if not slug:
        raise ValueError("requires 'slug' parameter")
    adapter = AddisFortuneAdapter(slug)
    return adapter.schema_fingerprint(raw_content)
