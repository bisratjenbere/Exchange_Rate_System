"""
Omo Bank adapter - Multi-table pattern (3 tables).

Migration notes:
- Old adapter: 87 LOC
- New adapter: Multi-table wrapper (Pattern E)
- Table 0: Cash Buying/Selling → 7 currencies
- Table 1: Transaction Buying/Selling → 7 currencies
- Table 2: Weighted Average Buying/Selling → optional (often "No Trade")
- Total: 14 records (7 cash + 7 transactional, weighted if available)

Pattern: Multi-table (Pattern E) - 3 separate tables, same structure
"""

from adapters.core.html_table import HtmlTableAdapter, TableSpec
from adapters.core.contract import ParseContext, ParseOutcome, RowIssue, IssueCode, Severity
from adapters.transport.base import FetchKind
from adapters.core.numbers import parse_decimal
from adapters.core.currency import normalize_currency
from adapters.core.record_builder import build_record


class OmoAdapter:
    """
    Multi-table adapter for Omo Bank.
    
    Table 0: Cash | Currency | Buy | Sell
    Table 1: Transaction | Currency | Buy | Sell
    Table 2: Weighted Avg | Currency | Buy | Sell (optional)
    
    All tables have same structure, different categories.
    """
    
    key = "omo_html"
    url = "https://omobanksc.com/"
    fetch_kind = FetchKind.HTTP_GET
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        from bs4 import BeautifulSoup
        
        if not raw or not raw.strip():
            return ParseOutcome.failed(IssueCode.EMPTY_PAYLOAD, "Empty HTML")
        
        soup = BeautifulSoup(raw, "html.parser")
        tables = soup.find_all("table")
        
        if len(tables) < 2:
            return ParseOutcome.failed(IssueCode.NO_TABLE, 
                                       f"Expected 3 tables, found {len(tables)}")
        
        records = []
        issues = []
        rows_seen = 0
        
        # Parse table 0: Cash
        if len(tables) >= 1:
            table0_records, table0_issues, table0_rows = self._parse_simple_table(
                tables[0], "cash", ctx
            )
            records.extend(table0_records)
            issues.extend(table0_issues)
            rows_seen += table0_rows
        
        # Parse table 1: Transactional
        if len(tables) >= 2:
            table1_records, table1_issues, table1_rows = self._parse_simple_table(
                tables[1], "transactional", ctx
            )
            records.extend(table1_records)
            issues.extend(table1_issues)
            rows_seen += table1_rows
        
        # Parse table 2: Weighted Average (optional, often has "No Trade")
        if len(tables) >= 3:
            table2_records, table2_issues, table2_rows = self._parse_simple_table(
                tables[2], "weighted_average", ctx
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
        
        # Sort for determinism
        records.sort(key=lambda r: (r.source_currency_code, r.category))
        
        # Compute structure hash
        import hashlib
        structure_text = f"omo_multi_table#{len(tables)}"
        structure_hash = hashlib.sha256(structure_text.encode()).hexdigest()[:16]
        
        return ParseOutcome(
            records=tuple(records),
            issues=tuple(issues),
            rows_seen=rows_seen,
            structure_hash=structure_hash
        )
    
    def _parse_simple_table(self, table, category: str, ctx: ParseContext):
        """
        Parse a simple table with format: Currency | Buy | Sell
        
        Note: First column may be empty (row number), currency in column 1.
        """
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        issues = []
        
        for row_idx, row in enumerate(rows):
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            
            # Find currency column (may be column 0 or 1)
            currency_text = None
            buy_col = None
            sell_col = None
            
            # Try column 1 first (column 0 is often empty row number)
            if len(cells) >= 3:
                if cells[0] and not cells[0].replace('.', '').replace(',', '').isdigit():
                    # Column 0 has currency
                    currency_text = cells[0]
                    buy_col = 1
                    sell_col = 2
                else:
                    # Column 1 has currency (column 0 is row number)
                    currency_text = cells[1] if len(cells) > 1 else None
                    buy_col = 2
                    sell_col = 3
            
            if not currency_text:
                continue
            
            # Parse currency code from text like "USD – US Dollar"
            currency_code = self._parse_currency_code(currency_text)
            if not currency_code:
                continue
            
            # Parse buy rate
            buy_rate = None
            if buy_col is not None and buy_col < len(cells):
                try:
                    buy_rate = parse_decimal(cells[buy_col])
                except ValueError:
                    # "No Trade" or invalid - skip this record
                    continue
            
            # Parse sell rate
            sell_rate = None
            if sell_col is not None and sell_col < len(cells):
                try:
                    sell_rate = parse_decimal(cells[sell_col])
                except ValueError:
                    # "No Trade" or invalid - skip this record
                    continue
            
            if buy_rate is not None or sell_rate is not None:
                rec = build_record(
                    currency_code=currency_code,
                    category=category,
                    buying_rate=buy_rate,
                    selling_rate=sell_rate,
                    ctx=ctx
                )
                records.append(rec)
        
        return records, issues, len(rows)
    
    def _parse_currency_code(self, text: str) -> str:
        """
        Extract currency code from text like "USD – US Dollar".
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


ADAPTER = OmoAdapter()
