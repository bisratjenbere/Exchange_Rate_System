import re
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from bs4 import BeautifulSoup

from adapters.base import HTMLTableAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin
from pipeline.normalize import normalize_rate

ADAPTER_KEY = "siket_html"
SOURCE_URL = "https://siketbank.com/exchange-rate"

_CODE_FIX = {"US": "USD"}

class SiketAdapter(FieldStructureMixin, HTMLTableAdapter):

    FIELD_CONFIG = {}

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def _process_tables(self, soup: BeautifulSoup, tables: list, **kwargs) -> ParseResult:
        result = ParseResult()

        effective_date = _parse_date(soup)
        date_basis = "source_published" if effective_date else "collection_date_fallback"

        try:
            records = _parse_table(self, tables[0], effective_date, date_basis)
            result.records.extend(records)
        except Exception as exc:
            result.add_error(f"table_0:{exc}")

        return result

def _parse_table(adapter, table, effective_date, date_basis) -> list:
    rows = [r for r in table.find_all("tr") if r.find("td")]
    records = []
    for row in rows:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 5:
            continue
        raw_code = cells[0].strip()
        code = _CODE_FIX.get(raw_code, raw_code)
        if not code:
            continue

        row_dict = {
            "cash_buying": cells[1],
            "cash_selling": cells[2],
            "transactional_buying": cells[3],
            "transactional_selling": cells[4],
        }
        if len(cells) > 6:
            row_dict["weighted_buying"] = cells[5]
            row_dict["weighted_selling"] = cells[6]

        detected_records = adapter.detect_and_emit(
            data=row_dict,
            currency=code,
            effective_date=effective_date,
            effective_date_basis=date_basis,
            source_publication_id=str(effective_date) if effective_date else None
        )

        records.extend(detected_records)
    return records

def _parse_date(soup) -> Optional[date]:
    text = soup.get_text(" ")
    m = re.search(r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s*\d{4}', text)
    if m:
        raw = re.sub(r'\s+', ' ', m.group(0).strip())
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                pass
    return None

def _safe_rate(raw) -> Optional[Decimal]:
    try:
        return normalize_rate(raw)
    except ValueError:
        return None

_adapter_instance = SiketAdapter()

def parse(raw_html: str) -> tuple:
    result = _adapter_instance.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    return _adapter_instance.schema_fingerprint(raw_html)
