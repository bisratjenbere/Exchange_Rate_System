"""
adapters/siinqee/adapter.py — Siinqee Bank (Type F single table).

Parse rules:
- Single table: Currency (code) | Buying | Selling. No category label → UNKNOWN.
- No date → collection_date_fallback → identity_status=ambiguous.
- Partial failure: returns (records, errors). Never raises.

MIGRATION NOTE: Migrated to FieldStructureMixin for automatic category detection.
"""
from typing import Optional
from bs4 import BeautifulSoup

from adapters.base import HTMLTableAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin

ADAPTER_KEY = "siinqee_html"
SOURCE_URL = "https://siinqeebank.com/"


class SiinqeeAdapter(FieldStructureMixin, HTMLTableAdapter):
    """Siinqee Bank adapter with field detection - single table."""
    
    FIELD_CONFIG = {}
    
    def get_source_url(self) -> str:
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        return ADAPTER_KEY
    
    def _process_tables(self, soup: BeautifulSoup, tables: list, **kwargs) -> ParseResult:
        """Process single table from Siinqee Bank using field detection."""
        result = ParseResult()
        category = kwargs.get("category", "transactional")
        
        try:
            records = _parse_table(self, tables[0], category)
            result.records.extend(records)
        except Exception as exc:
            result.add_error(f"table_0:{exc}")
        
        return result


def _parse_table(adapter, table, category: str = "transactional") -> list:
    """Parse single table using field detection."""
    rows = [r for r in table.find_all("tr") if r.find("td")]
    records = []
    for row in rows:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        currency_code = cells[0].strip()
        if not currency_code:
            continue
        
        row_dict = {"buying": cells[1], "selling": cells[2]}
        detected_records = adapter.detect_and_emit(
            data=row_dict,
            currency=currency_code,
            effective_date=None,
            effective_date_basis="collection_date_fallback",
            mapping_notes=["category_unknown:single_pair_no_label"]
        )
        
        for rec in detected_records:
            if rec.category == 'UNKNOWN':
                rec.category = category
        
        records.extend(detected_records)
    return records


# ============================================================================
# MODULE-LEVEL WRAPPER FUNCTIONS FOR BACKWARD COMPATIBILITY
# ============================================================================

_adapter_instance = SiinqeeAdapter()

def parse(raw_html: str, category: str = "transactional") -> tuple:
    """Parse Siinqee Bank HTML into records. Module-level wrapper."""
    result = _adapter_instance.parse(raw_html, category=category)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    """Generate schema fingerprint. Module-level wrapper."""
    return _adapter_instance.schema_fingerprint(raw_html)
