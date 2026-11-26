"""
Tsehay Bank adapter - Multi-table pattern.

Migration notes:
- Old adapter: 134 LOC (adapters/tsehay/adapter.py)
- New adapter: Multi-table wrapper (Pattern E)
- Table 0: Wide format with multi-row headers (Cash/Transaction) → 6 currencies × 2 categories
- Table 1: Simple format (Weighted Average) → 1 currency (USD only)
- Total: 13 records (6×2 cash+txn + 1 weighted_average)

Pattern: Multi-table (Pattern E) - similar to zamzam/cbo
"""

from adapters.core.html_table import HtmlTableAdapter, TableSpec
from adapters.core.contract import ParseContext, ParseOutcome, RowIssue, IssueCode, Severity
from adapters.transport.base import FetchKind
from adapters.core.numbers import parse_decimal
from adapters.core.currency import normalize_currency
from adapters.core.record_builder import build_record


class TsehayAdapter:
    """
    Multi-table adapter for Tsehay Bank.
    
    Table 0: Wide format with multi-row headers
      Row 0: CURRENCY | CASH | TRANSACTION
      Row 1:          | BUYING | SELLING | BUYING | SELLING
      Row 2+: USD | 161.60 | 164.83 | 161.60 | 164.83
      
    Table 1: Simple format (Weighted Average)
      Currency Name | Code | Buying | Selling
    """
    
    key = "tsehay_html"
    url = "https://tsehaybank.com.et/exchange-rate/"
    fetch_kind = FetchKind.HTTP_GET
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        from bs4 import BeautifulSoup
        
        if not raw or not raw.strip():
            return ParseOutcome.failed(IssueCode.EMPTY_PAYLOAD, "Empty HTML")
        
        soup = BeautifulSoup(raw, "html.parser")
        tables = soup.find_all("table")
        
        if len(tables) < 1:
            return ParseOutcome.failed(IssueCode.NO_TABLE, "No tables found")
        
        records = []
        issues = []
        rows_seen = 0
        
        # Parse table 0: Cash + Transactional (wide format with multi-row headers)
        if len(tables) >= 1:
            table0_records, table0_issues, table0_rows = self._parse_cash_txn_table(
                tables[0], ctx
            )
            records.extend(table0_records)
            issues.extend(table0_issues)
            rows_seen += table0_rows
        
        # Parse table 1: Weighted average (simple format)
        if len(tables) >= 2:
            table1_records, table1_issues, table1_rows = self._parse_weighted_table(
                tables[1], ctx
            )
            records.extend(table1_records)
            issues.extend(table1_issues)
            rows_seen += table1_rows
        else:
            issues.append(RowIssue(
                row_ref="table_1",
                code=IssueCode.NO_TABLE,
                detail="Weighted average table missing",
                severity=Severity.WARNING
            ))
        
        # Sort for determinism
        records.sort(key=lambda r: (r.source_currency_code, r.category))
        
        # Compute structure hash
        import hashlib
        structure_text = f"tsehay_multi_table#{len(tables)}"
        structure_hash = hashlib.sha256(structure_text.encode()).hexdigest()[:16]
        
        return ParseOutcome(
            records=tuple(records),
            issues=tuple(issues),
            rows_seen=rows_seen,
            structure_hash=structure_hash
        )
    
    def _parse_cash_txn_table(self, table, ctx: ParseContext):
        """
        Parse table 0: Wide format with multi-row headers.
        
        Row 0: CURRENCY | CASH | TRANSACTION
        Row 1:          | BUYING | SELLING | BUYING | SELLING
        Row 2+: Currency | Cash Buy | Cash Sell | Txn Buy | Txn Sell
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
        Parse table 1: Simple format with Weighted Average rates.
        
        Columns: Currency Name | Code | Buying | Selling
        """
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        issues = []
        
        for row_idx, row in enumerate(rows):
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            
            if len(cells) < 4:
                continue
            
            # Column 1: Currency code (column 0 is currency name)
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


ADAPTER = TsehayAdapter()
