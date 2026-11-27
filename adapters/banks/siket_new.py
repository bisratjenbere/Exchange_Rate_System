"""
Siket Bank adapter - TableSpec with wide table format.

Migration notes:
- Old adapter: 78 LOC
- New adapter: TableSpec + wrapper for wide table
- Wide table: Currency | Cash Buy/Sell | Txn Buy/Sell | WAvg Buy/Sell
- Multi-row header (row 0: categories, row 1: buying/selling)
- Creates 2-3 records per row (cash, transactional, weighted_average if present)
"""

from adapters.core.html_table import HtmlTableAdapter, TableSpec
from adapters.core.contract import ParseContext, ParseOutcome, RowIssue, IssueCode, Severity
from adapters.transport.base import FetchKind
from adapters.core.numbers import parse_decimal
from adapters.core.currency import normalize_currency
from adapters.core.record_builder import build_record
import hashlib
from bs4 import BeautifulSoup

SPEC = TableSpec(
    key="siket_html",
    url="https://siketbank.com/exchange-rate",
    headers={
        "currency": ("currency",),
        # Can't use buying/selling directly due to multi-row header
        # Will parse positionally after finding table
    },
    required=("currency",),
)


class SiketAdapter:
    """
    Wrapper for siket's wide table with multi-row header.
    
    Table structure:
    Row 0: Currency | Cash | Transaction | Weighted Average
    Row 1:         | Buying | Selling | Buying | Selling | Buying | Selling
    Data:  US      | 161.73 | 164.96  | 161.73 | 164.96  | 161.72 | 164.95
    
    Columns: 0=Currency, 1=CashBuy, 2=CashSell, 3=TxnBuy, 4=TxnSell, 5=WAvgBuy, 6=WAvgSell
    """
    
    key = SPEC.key
    url = SPEC.url
    fetch_kind = FetchKind.HTTP_GET
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        if not raw or not raw.strip():
            return ParseOutcome.failed(IssueCode.EMPTY_PAYLOAD, "Empty HTML")
        
        soup = BeautifulSoup(raw, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            return ParseOutcome.failed(IssueCode.NO_TABLE, "No tables found")
        
        table = tables[0]
        
        # Skip first 2 rows (multi-row header)
        all_rows = table.find_all("tr")
        data_rows = all_rows[2:] if len(all_rows) > 2 else []
        
        records = []
        issues = []
        
        # Currency code fix (old adapter had this)
        code_fix = {"US": "USD"}
        
        for row_idx, row in enumerate(data_rows):
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            
            if len(cells) < 5:  # Need at least currency + cash buy/sell + txn buy/sell
                continue
            
            # Column 0: Currency
            raw_code = cells[0]
            currency_code = code_fix.get(raw_code, raw_code)
            
            # Normalize currency
            normalized = normalize_currency(currency_code)
            if normalized:
                currency_code = normalized
            else:
                # Try uppercase
                currency_code = currency_code.upper()
            
            # Columns 1-2: Cash buy/sell
            cash_buy = None
            cash_sell = None
            try:
                cash_buy = parse_decimal(cells[1]) if len(cells) > 1 else None
            except ValueError:
                issues.append(RowIssue(
                    row_ref=currency_code,
                    code=IssueCode.BAD_NUMBER,
                    detail=f"Bad cash buy: {cells[1]}",
                    severity=Severity.ERROR
                ))
            
            try:
                cash_sell = parse_decimal(cells[2]) if len(cells) > 2 else None
            except ValueError:
                issues.append(RowIssue(
                    row_ref=currency_code,
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
                txn_buy = parse_decimal(cells[3]) if len(cells) > 3 else None
            except ValueError:
                pass  # Don't error on txn rates
            
            try:
                txn_sell = parse_decimal(cells[4]) if len(cells) > 4 else None
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
            
            # Columns 5-6: Weighted average buy/sell (optional)
            if len(cells) > 5:
                wavg_buy = None
                wavg_sell = None
                try:
                    wavg_buy = parse_decimal(cells[5])
                except ValueError:
                    pass
                
                if len(cells) > 6:
                    try:
                        wavg_sell = parse_decimal(cells[6])
                    except ValueError:
                        pass
                
                if wavg_buy is not None or wavg_sell is not None:
                    rec = build_record(
                        currency_code=currency_code,
                        category="weighted_average",
                        buying_rate=wavg_buy,
                        selling_rate=wavg_sell,
                        ctx=ctx
                    )
                    records.append(rec)
        
        records.sort(key=lambda r: (r.source_currency_code, r.category))
        
        # Compute structure hash (use table header count)
        structure_text = f"siket_wide_table#{len(all_rows[0].find_all(['th', 'td']))}"
        structure_hash = hashlib.sha256(structure_text.encode()).hexdigest()[:16]
        
        return ParseOutcome(
            records=tuple(records),
            issues=tuple(issues),
            rows_seen=len(data_rows),
            structure_hash=structure_hash
        )


ADAPTER = SiketAdapter()
