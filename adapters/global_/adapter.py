"""
adapters/global/adapter.py — Global Bank Ethiopia (Type F two tables, UNKNOWN).

Parse rules:
- Two tables, both: Currency (code) | Buying | Selling. No category label → UNKNOWN.
- Table 0 = first pair, Table 1 = second pair (possibly weighted avg — TO VERIFY).
- "No Trade" → None.
- No date → collection_date_fallback → identity_status=ambiguous.
- Review signal: buying > selling (observed for USD in table 1).
- Partial failure: returns (records, errors). Never raises.
"""
from decimal import Decimal
from typing import Optional
from bs4 import BeautifulSoup

from domain.records import AdapterRecord
from pipeline.normalize import normalize_rate
from adapters.base import HTMLTableAdapter, ParseResult

ADAPTER_KEY = "global_html"
SOURCE_URL = "https://www.globalbankethiopia.com/remittance-forex/"


class GlobalAdapter(HTMLTableAdapter):
    """Global Bank Ethiopia adapter - parses 2 tables with category parameter."""
    
    def get_source_url(self) -> str:
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        return ADAPTER_KEY
    
    def _process_tables(self, soup: BeautifulSoup, tables: list, **kwargs) -> ParseResult:
        """Process two tables from Global Bank."""
        result = ParseResult()
        category = kwargs.get("category", "transactional")
        
        # Process first 2 tables only
        tables_to_process = list(tables)[:2] if len(tables) >= 2 else list(tables)
        
        for i, table in enumerate(tables_to_process):
            try:
                records = _parse_table(table, table_index=i, category=category)
                result.records.extend(records)
            except Exception as exc:
                result.add_error(f"table_{i}:{exc}")
        
        return result


def _parse_table(table, table_index: int, category: str = "transactional") -> list:
    """Parse a single table from Global Bank."""
    rows = [r for r in table.find_all("tr") if r.find("td")]
    records = []
    for row in rows:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        currency_code = cells[0].strip()
        if not currency_code:
            continue
        buying = _safe_rate(cells[1])
        selling = _safe_rate(cells[2])
        if buying is None and selling is None:
            continue
        notes = [f"category_unknown:table_{table_index}_unverified"]
        if buying is not None and selling is not None and buying > selling:
            notes.append("review_signal:buying_greater_than_selling")
        records.append(AdapterRecord(
            source_currency_code=currency_code,
            category=category,
            buying_rate=buying,
            selling_rate=selling,
            source_rate_text=f"{cells[1]}/{cells[2]}",
            effective_date=None,
            effective_date_basis="collection_date_fallback",
            source_record_key=None,
            source_publication_key=None,
            unit_multiplier=1,
            raw_excerpt={"currency": currency_code, "buying": cells[1], "selling": cells[2], "table": table_index},
            mapping_notes=notes,
        ))
    return records


def _safe_rate(raw) -> Optional[Decimal]:
    """Convert raw rate string to Decimal, returning None on failure."""
    try:
        return normalize_rate(raw)
    except ValueError:
        return None


# ============================================================================
# MODULE-LEVEL WRAPPER FUNCTIONS FOR BACKWARD COMPATIBILITY
# ============================================================================

_adapter_instance = GlobalAdapter()

def parse(raw_html: str, category: str = "transactional") -> tuple:
    """Parse Global Bank HTML into records. Module-level wrapper."""
    result = _adapter_instance.parse(raw_html, category=category)
    return result.records, result.errors

def schema_fingerprint(raw_html: str) -> str:
    """Generate schema fingerprint. Module-level wrapper."""
    return _adapter_instance.schema_fingerprint(raw_html)
