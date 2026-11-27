"""
NIB (Nib International Bank) adapter - Multi-table pattern.

Migration notes:
- Old adapter: 156 LOC (adapters/nib/adapter.py)
- New adapter: Multi-table wrapper (Pattern E)
- Table 0: Date extraction (single row, single cell)
- Table 1: Wide format (Cash + Transaction) → 7 currencies × 2 categories
- Table 2: Simple format (Weighted Average) → 2 currencies (USD, EUR)
- Total: 16 records (7×2 cash+txn + 2 weighted_average)

Pattern: Multi-table (Pattern E) - similar to tsehay
"""

from adapters.core.html_table import HtmlTableAdapter, TableSpec
from adapters.core.contract import ParseContext, ParseOutcome, RowIssue, IssueCode, Severity
from adapters.transport.base import FetchKind
from adapters.core.numbers import parse_decimal
from adapters.core.currency import normalize_currency
from adapters.core.record_builder import build_record
import hashlib
from bs4 import BeautifulSoup


class NIBAdapter:
    """
    Multi-table adapter for Nib International Bank.
    
    Table 0: Date (single row: "Nov 25, 2026")
    Table 1: Wide format (Cash + Transaction)
      Currency | Buying | Selling | Buying | Selling
      
    Table 2: Simple format (Weighted Average)
      Country | Currency | Buying | Selling
    """
    
    key = "nib_html"
    url = "https://www.nibbanksc.com/exchange-rate/"
    fetch_kind = FetchKind.HTTP_GET
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        if not raw or not raw.strip():
            return ParseOutcome.failed(IssueCode.EMPTY_PAYLOAD, "Empty HTML")
        
        soup = BeautifulSoup(raw, "html.parser")
        tables = soup.find_all("table")
        
        if len(tables) < 2:
            return ParseOutcome.failed(IssueCode.NO_TABLE, "Expected at least 2 tables")
        
        records = []
        issues = []
        rows_seen = 0
        
        # Table 0 is date (ignored for now, would need effective_date support)
        
        # Parse table 1: Cash + Transactional (wide format)
        if len(tables) >= 2:
            table1_records, table1_issues, table1_rows = self._parse_cash_txn_table(
                tables[1], ctx
            )
            records.extend(table1_records)
            issues.extend(table1_issues)
            rows_seen += table1_rows
        
        # Parse table 2: Weighted average (simple format)
        if len(tables) >= 3:
            table2_records, table2_issues, table2_rows = self._parse_weighted_table(
                tables[2], ctx
            )
            records.extend(table2_records)
            issues.extend(table2_issues)
            rows_seen += table2_rows
        else:
            issues.append(RowIssue(
                row_ref="table_2",
                code=IssueCode.NO_TABLE,
                detail="Weighted average table missing",
                severity=Severity.WARNING
            ))
        
        records.sort(key=lambda r: (r.source_currency_code, r.category))
        
        structure_text = f"nib_multi_table#{len(tables)}"
        structure_hash = hashlib.sha256(structure_text.encode()).hexdigest()[:16]
        
        return ParseOutcome(
            records=tuple(records),
            issues=tuple(issues),
            rows_seen=rows_seen,
            structure_hash=structure_hash
        )
    
    def _parse_cash_txn_table(self, table, ctx: ParseContext):
        """
        Parse table 1: Wide format with Cash + Transaction rates.
        
        Columns: Currency | Cash Buy | Cash Sell | Txn Buy | Txn Sell
        """
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        issues = []
        
        for row_idx, row in enumerate(rows):
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            
            if len(cells) < 5:
                continue
            
            # Column 0: Currency code
            currency_text = cells[0]
            currency_code = normalize_currency(currency_text)
            
            if not currency_code:
                continue
            
            # Columns 1-2: Cash buy/sell
            cash_buy = None
            cash_sell = None
            try:
                cash_buy = parse_decimal(cells[1])
            except ValueError:
                issues.append(RowIssue(
                    row_ref=f"{currency_code}_cash",
                    code=IssueCode.BAD_NUMBER,
                    detail=f"Bad cash buy: {cells[1]}",
                    severity=Severity.ERROR
                ))
            
            try:
                cash_sell = parse_decimal(cells[2])
            except ValueError:
                issues.append(RowIssue(
                    row_ref=f"{currency_code}_cash",
                    code=IssueCode.BAD_NUMBER,
                    detail=f"Bad cash sell: {cells[2]}",
                    severity=Severity.ERROR
                ))
            
            if cash_buy is not None or cash_sell is not None:
                rec = build_record(
                    currency_code=currency_code,
                    category="cash",
                    buying_rate=cash_buy,
                    selling_rate=cash_sell,
                    ctx=ctx
                )
                records.append(rec)
            
            # Columns 3-4: Transactional buy/sell
            txn_buy = None
            txn_sell = None
            try:
                txn_buy = parse_decimal(cells[3])
            except ValueError:
                pass
            
            try:
                txn_sell = parse_decimal(cells[4])
            except ValueError:
                pass
            
            if txn_buy is not None or txn_sell is not None:
                rec = build_record(
                    currency_code=currency_code,
                    category="transactional",
                    buying_rate=txn_buy,
                    selling_rate=txn_sell,
                    ctx=ctx
                )
                records.append(rec)
        
        return records, issues, len(rows)
    
    def _parse_weighted_table(self, table, ctx: ParseContext):
        """
        Parse table 2: Simple format with Weighted Average rates.
        
        Columns: Country | Currency | Buying | Selling
        """
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        issues = []
        
        for row_idx, row in enumerate(rows):
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            
            if len(cells) < 4:
                continue
            
            # Column 1: Currency code (column 0 is country name)
            currency_text = cells[1]
            currency_code = normalize_currency(currency_text)
            
            if not currency_code:
                continue
            
            # Columns 2-3: Weighted avg buy/sell
            wavg_buy = None
            wavg_sell = None
            
            try:
                wavg_buy = parse_decimal(cells[2])
            except ValueError:
                # "No Trade" is acceptable, skip quietly
                pass
            
            try:
                wavg_sell = parse_decimal(cells[3])
            except ValueError:
                # "No Trade" is acceptable, skip quietly
                pass
            
            # Create weighted_average record (only if at least one rate exists)
            if wavg_buy is not None or wavg_sell is not None:
                rec = build_record(
                    currency_code=currency_code,
                    category="weighted_average",
                    buying_rate=wavg_buy,
                    selling_rate=wavg_sell,
                    ctx=ctx
                )
                records.append(rec)
        
        return records, issues, len(rows)


ADAPTER = NIBAdapter()
