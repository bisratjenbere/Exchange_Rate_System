import re
from datetime import datetime, date
from typing import Optional

from bs4 import BeautifulSoup

from adapters.base import HTMLTableAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin
from pipeline.category_normalizer import normalize_category

ADAPTER_KEY = "amhara_html"
SOURCE_URL = "https://www.amharabank.com/daily-exchange-rate/"
SSL_VERIFY = False

_CODE_RE = re.compile(r"\(\s*([A-Z]{3})\s*\)", re.IGNORECASE)

class AmharaAdapter(FieldStructureMixin, HTMLTableAdapter):

    FIELD_CONFIG = {}

    def get_source_url(self) -> str:
        return SOURCE_URL

    def get_adapter_key(self) -> str:
        return ADAPTER_KEY

    def _process_tables(self, soup: BeautifulSoup, tables: list, **options) -> ParseResult:
        result = ParseResult()

        effective_date = _parse_date(soup)
        date_basis = "source_published" if effective_date else "collection_date_fallback"

        if not tables:
            result.add_error("table_0_cash_txn:missing")
            result.add_error("table_1_weighted_avg:missing")
            return result

        try:
            records = self._parse_cash_txn(tables[0], effective_date, date_basis)
            result.records.extend(records)
        except Exception as exc:
            result.add_error(f"table_0_cash_txn:{exc}")

        if len(tables) < 2:
            result.add_error("table_1_weighted_avg:missing")
        else:
            try:
                records = self._parse_weighted(tables[1], effective_date, date_basis, **options)
                result.records.extend(records)
            except Exception as exc:
                result.add_error(f"table_1_weighted_avg:{exc}")

        return result

    def _parse_cash_txn(self, table, effective_date, date_basis) -> list:
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 6:
                continue
            currency_code, currency_name = _parse_name_code(cells[1])
            if not currency_code:
                continue

            row_dict = {
                "cash_buying": cells[2],
                "cash_selling": cells[3],
                "transactional_buying": cells[4],
                "transactional_selling": cells[5],
            }

            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=currency_code,
                currency_name=currency_name,
                effective_date=effective_date,
                effective_date_basis=date_basis,
                mapping_notes=["ssl_verify_false:access_finding_recorded"]
            )

            records.extend(detected_records)
        return records

    def _parse_weighted(self, table, effective_date, date_basis, **options) -> list:
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        table_category = self.extract_table_category(table)
        if table_category == "UNKNOWN":
            table_category = normalize_category(options.get("category", "weighted_average"))

        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 4:
                continue
            currency_code, currency_name = _parse_name_code(cells[1])
            if not currency_code:
                continue

            row_dict = {
                "buying": cells[2],
                "selling": cells[3],
            }

            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=currency_code,
                currency_name=currency_name,
                effective_date=effective_date,
                effective_date_basis=date_basis,
                mapping_notes=["ssl_verify_false:access_finding_recorded"]
            )

            for rec in detected_records:
                if rec.category == 'UNKNOWN':
                    rec.category = table_category

            records.extend(detected_records)
        return records

def _parse_date(soup) -> Optional[date]:
    text = re.sub(r'\s+', ' ', soup.get_text(" "))
    m = re.search(r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s*\d{4}', text)
    if m:
        raw = re.sub(r'\s+', ' ', m.group(0).strip())
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                pass
    return None

def _parse_name_code(text: str) -> tuple:
    m = _CODE_RE.search(text)
    if m:
        code = m.group(1).upper()
        name = text[:m.start()].strip()
        return code, name or None
    text = text.strip()
    return (text, None) if text else ("", None)

def parse(raw_html: str) -> tuple:
    adapter = AmharaAdapter()
    result = adapter.parse(raw_html)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    return AmharaAdapter().schema_fingerprint(raw_html)
