"""
Dashen Bank adapter - Multi-table pattern.

Migration notes:
- Old adapter: 201 LOC (adapters/dashen/adapter.py)
- New adapter: Multi-table wrapper (Pattern E)
- Table 0: Transaction Rate → 9 currencies
- Table 1: Cash Rate → 7 currencies
- Table 2: Weighted Average Rate → 6 currencies
- Total: 22 records (9 transactional + 7 cash + 6 weighted_average)

Pattern: Multi-table (Pattern E)
"""

from adapters.core.html_table import HtmlTableAdapter, TableSpec
from adapters.core.contract import ParseContext, ParseOutcome, RowIssue, IssueCode, Severity
from adapters.transport.base import FetchKind
from adapters.core.numbers import parse_decimal
from adapters.core.currency import normalize_currency
from adapters.core.record_builder import build_record
import hashlib
from bs4 import BeautifulSoup


class DashenAdapter:
    """
    Multi-table adapter for Dashen Bank.
    
    Table 0: Transaction Rate
      Currency Code | Currency Name | Transaction Buying | Transaction Selling | Spread
      
    Table 1: Cash Rate
      Currency Code | Currency Name | Cash Buying | Cash Selling | Spread
      
    Table 2: Weighted Average Rate
      Currency Code | Currency Name | Weighted Average Rate on [Date]
      (Multi-row header with Buying/Selling in row 2)
    """
    
    key = "dashen_html"
    url = "https://dashenbanksc.com/daily-exchange-rate/"
    fetch_kind = FetchKind.HTTP_GET
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        if not raw or not raw.strip():
            return ParseOutcome.failed(IssueCode.EMPTY_PAYLOAD, "Empty HTML")
        
        soup = BeautifulSoup(raw, "html.parser")
        tables = soup.find_all("table")
        
        if len(tables) < 3:
            return ParseOutcome.failed(IssueCode.NO_TABLE, f"Expected 3 tables, found {len(tables)}")
        
        records = []
        issues = []
        rows_seen = 0
        
        # Parse table 0: Transaction Rate
        if len(tables) >= 1:
            table0_records, table0_issues, table0_rows = self._parse_simple_table(
                tables[0], "transactional", ctx
            )
            records.extend(table0_records)
            issues.extend(table0_issues)
            rows_seen += table0_rows
        
        # Parse table 1: Cash Rate
        if len(tables) >= 2:
            table1_records, table1_issues, table1_rows = self._parse_simple_table(
                tables[1], "cash", ctx
            )
            records.extend(table1_records)
            issues.extend(table1_issues)
            rows_seen += table1_rows
        
        # Parse table 2: Weighted Average Rate (multi-row header)
        if len(tables) >= 3:
            table2_records, table2_issues, table2_rows = self._parse_weighted_table(
                tables[2], ctx
            )
            records.extend(table2_records)
            issues.extend(table2_issues)
            rows_seen += table2_rows
        
        records.sort(key=lambda r: (r.source_currency_code, r.category))
        
        structure_text = f"dashen_multi_table#{len(tables)}"
        structure_hash = hashlib.sha256(structure_text.encode()).hexdigest()[:16]
        
        return ParseOutcome(
            records=tuple(records),
            issues=tuple(issues),
            rows_seen=rows_seen,
            structure_hash=structure_hash
        )
    
    def _parse_simple_table(self, table, category: str, ctx: ParseContext):
        """
        Parse a simple table: Currency Code | Currency Name | Buying | Selling | Spread
        
        Args:
            table: BeautifulSoup table element
            category: "transactional" or "cash"
            ctx: ParseContext
        """
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        issues = []
        
        for row_idx, row in enumerate(rows):
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            
            if len(cells) < 4:
                continue
            
            # Column 0: Currency code
            currency_code = normalize_currency(cells[0])
            
            if not currency_code:
                continue
            
            # Column 2: Buying rate (column 1 is currency name)
            buy = None
            try:
                buy = parse_decimal(cells[2])
            except ValueError:
                pass
            
            # Column 3: Selling rate
            sell = None
            try:
                sell = parse_decimal(cells[3])
            except ValueError:
                pass
            
            if buy is not None or sell is not None:
                rec = build_record(
                    currency_code=currency_code,
                    category=category,
                    buying_rate=buy,
                    selling_rate=sell,
                    ctx=ctx
                )
                records.append(rec)
        
        return records, issues, len(rows)
    
    def _parse_weighted_table(self, table, ctx: ParseContext):
        """
        Parse weighted average table with multi-row header.
        
        Row 0: Currency Code | Currency Name | Weighted Average Rate on [Date]
        Row 1:                                | Buying | Selling
        Row 2+: USD | US Dollar | 163.5148 | 165.8775
        """
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        issues = []
        
        for row_idx, row in enumerate(rows):
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            
            if len(cells) < 4:
                continue
            
            # Column 0: Currency code
            currency_code = normalize_currency(cells[0])
            
            if not currency_code:
                continue
            
            # Column 2: Buying rate (column 1 is currency name)
            buy = None
            try:
                buy = parse_decimal(cells[2])
            except ValueError:
                pass
            
            # Column 3: Selling rate
            sell = None
            try:
                sell = parse_decimal(cells[3])
            except ValueError:
                pass
            
            if buy is not None or sell is not None:
                rec = build_record(
                    currency_code=currency_code,
                    category="weighted_average",
                    buying_rate=buy,
                    selling_rate=sell,
                    ctx=ctx
                )
                records.append(rec)
        
        return records, issues, len(rows)


ADAPTER = DashenAdapter()
