"""
adapters/bunna/adapter.py — Bunna Bank (Type E wide HTML).

Parse rules:
- Single wide table. Header row 0: | CASH | TRANSACTION | AVERAGE
  Header row 1: Currency | Code | Buying | Selling | Buying | Selling | Buying | Selling
- Columns: col0=name, col1=code, col2=cash_buy, col3=cash_sell,
           col4=txn_buy, col5=txn_sell, col6=avg_buy, col7=avg_sell
- AVERAGE columns may contain "..." (JS-rendered) → treated as None.
- No date → collection_date_fallback → identity_status=ambiguous.
- Partial failure: returns (records, errors). Never raises.

MIGRATION NOTE: Migrated to FieldStructureMixin for automatic category detection.
"""
from bs4 import BeautifulSoup

from adapters.base import HTMLTableAdapter, ParseResult
from field_detection.mixin import FieldStructureMixin

ADAPTER_KEY = "bunna_html"
SOURCE_URL = "https://bunnabanksc.com/foreign-exchange/"


class BunnaAdapter(FieldStructureMixin, HTMLTableAdapter):
    """
    Bunna Bank adapter with field detection.
    
    Type E adapter with wide table containing all three categories.
    Field Structure: Columns → dict with category prefixes
    """
    
    FIELD_CONFIG = {}
    
    def get_source_url(self) -> str:
        """Return Bunna Bank website URL."""
        return SOURCE_URL
    
    def get_adapter_key(self) -> str:
        """Return unique adapter identifier."""
        return ADAPTER_KEY
    
    def _process_tables(self, soup: BeautifulSoup, tables: list, **options) -> ParseResult:
        """
        Extract AdapterRecords from Bunna HTML table using field detection.
        
        Args:
            soup: BeautifulSoup parsed HTML
            tables: List of table elements (expecting 1 table)
            **options: Not used by Bunna
            
        Returns:
            ParseResult with extracted records and any errors
        """
        result = ParseResult()
        
        if not tables:
            result.add_error("table_0:missing")
            return result
        
        try:
            records = self._parse_wide_table(tables[0])
            result.records.extend(records)
        except Exception as exc:
            result.add_error(f"table_0:{exc}")
        
        return result
    
    def _parse_wide_table(self, table) -> list:
        """Parse Bunna's wide table with all three categories in columns using field detection."""
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 6:
                continue
            currency_name = cells[0].strip()
            currency_code = cells[1].strip()
            if not currency_code:
                continue
            
            # Create dict with explicit category prefixes
            row_dict = {
                "cash_buying": cells[2],
                "cash_selling": cells[3],
                "transactional_buying": cells[4],
                "transactional_selling": cells[5],
            }
            if len(cells) > 7:
                row_dict["weighted_average_buying"] = cells[6]
                row_dict["weighted_average_selling"] = cells[7]
            
            # Use field detection
            detected_records = self.detect_and_emit(
                data=row_dict,
                currency=currency_code,
                currency_name=currency_name or None,
                effective_date=None,
                effective_date_basis="collection_date_fallback",
                mapping_notes=["date_ambiguous:no_source_published_date", "avg_cols_may_be_js_rendered:TO_VERIFY"]
            )
            
            records.extend(detected_records)
        return records


# ═══════════════════════════════════════════════════════════════════════════════
# Backward Compatibility Wrappers
# ═══════════════════════════════════════════════════════════════════════════════

def parse(raw_html: str) -> tuple:
    """
    Old function API (for backward compatibility).
    
    New code should use BunnaAdapter().parse().
    
    Args:
        raw_html: Raw HTML string from Bunna Bank
        
    Returns:
        Tuple of (records, errors) for backward compatibility
    """
    adapter = BunnaAdapter()
    result = adapter.parse(raw_html)
    return result.records, result.errors


def schema_fingerprint(raw_html: str) -> str:
    """
    Old function API (for backward compatibility).
    
    New code should use BunnaAdapter().schema_fingerprint().
    
    Args:
        raw_html: Raw HTML string
        
    Returns:
        SHA256 hash of table structure
    """
    return BunnaAdapter().schema_fingerprint(raw_html)
