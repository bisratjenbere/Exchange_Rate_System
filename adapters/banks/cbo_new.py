"""
CBO (Cooperative Bank of Oromia) adapter - Multi-table pattern.

Migration notes:
- Old adapter: 85 LOC (estimated, file not checked)
- New adapter: Multi-table wrapper (Pattern E)
- Table 0: Wide format (Cash Buy/Sell + Transaction Buy/Sell) → 5 currencies × 2 categories
- Table 1: Simple format (Weighted Average Buy/Sell) → 5 currencies × 1 category
- Total: 15 records (5 cash + 5 transactional + 5 weighted_average)

Pattern: Multi-table (Pattern E) - same as zamzam
"""

from adapters.core.html_table import HtmlTableAdapter, TableSpec
from adapters.core.contract import ParseContext, ParseOutcome, RowIssue, IssueCode, Severity
from adapters.transport.base import FetchKind
from adapters.core.numbers import parse_decimal
from adapters.core.currency import normalize_currency
from adapters.core.record_builder import build_record


class CBOAdapter:
    """
    Multi-table adapter for CBO Bank.
    
    Table 0: Wide format
      Currency | Cash Buy | Cash Sell | Txn Buy | Txn Sell
      
    Table 1: Simple format
      Currency | Weighted Avg Buy | Weighted Avg Sell
    """
    
    key = "cbo_html"
    url = "https://coopbankoromia.com.et/"
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
        
        # Parse table 0: Cash + Transactional (wide format)
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
        structure_text = f"cbo_multi_table#{len(tables)}"
        structure_hash = hashlib.sha256(structure_text.encode()).hexdigest()[:16]
        
        return ParseOutcome(
            records=tuple(records),
            issues=tuple(issues),
            rows_seen=rows_seen,
            structure_hash=structure_hash
        )
    
    def _parse_cash_txn_table(self, table, ctx: ParseContext):
        """
        Parse table 0: Wide format with Cash + Transaction rates.
        
        Columns: Currency | Cash Buy | Cash Sell | Txn Buy | Txn Sell
        """
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        issues = []
        
        for row_idx, row in enumerate(rows):
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            
            if len(cells) < 5:
                continue
            
            # Column 0: Currency (may include name like "USD - US Dollar")
            currency_text = cells[0]
            currency_code = self._parse_currency_code(currency_text)
            
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
        
        Columns: Currency | Weighted Avg Buy | Weighted Avg Sell
        """
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        issues = []
        
        for row_idx, row in enumerate(rows):
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            
            if len(cells) < 3:
                continue
            
            # Column 0: Currency
            currency_text = cells[0]
            currency_code = self._parse_currency_code(currency_text)
            
            if not currency_code:
                continue
            
            # Columns 1-2: Weighted avg buy/sell
            # Note: CBO has an extra empty column, so buy might be in col 1 or 2
            wavg_buy = None
            wavg_sell = None
            
            # Try column 1 first
            try:
                wavg_buy = parse_decimal(cells[1])
            except ValueError:
                # Try column 2 if column 1 failed
                if len(cells) > 2:
                    try:
                        wavg_buy = parse_decimal(cells[2])
                        # If col 2 worked, sell is in col 3
                        if len(cells) > 3:
                            try:
                                wavg_sell = parse_decimal(cells[3])
                            except ValueError:
                                pass
                    except ValueError:
                        pass
            else:
                # Column 1 worked, sell is in column 2
                try:
                    wavg_sell = parse_decimal(cells[2])
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
        
        return records, issues, len(rows)
    
    def _parse_currency_code(self, text: str) -> str:
        """
        Extract currency code from text like "USD - US Dollar".
        """
        # Try to extract 3-letter code at start
        parts = text.split()
        if parts and len(parts[0]) >= 3:
            code = parts[0][:3].upper()
            # Normalize
            normalized = normalize_currency(code)
            return normalized or code
        
        # Try splitting by dash or hyphen
        if '–' in text or '-' in text:
            code = text.split('–')[0].split('-')[0].strip()
            if len(code) >= 3:
                normalized = normalize_currency(code[:3].upper())
                return normalized or code[:3].upper()
        
        # Try normalize on full text
        normalized = normalize_currency(text)
        if normalized:
            return normalized
        
        # Fallback: take first 3 chars
        return text[:3].upper() if text else ""


ADAPTER = CBOAdapter()
