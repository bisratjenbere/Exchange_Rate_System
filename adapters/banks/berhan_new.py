"""
Berhan Bank adapter - Duplication pattern (cash + transactional).

Migration notes:
- Old adapter: 101 LOC (adapters/berhan/adapter.py, regex-based)
- New adapter: Table-based with duplication (Pattern B)
- Table format: "1 USD ($)" | Buying | Selling
- Duplicates each record for cash + transactional categories
- Total: 14 records (7 currencies × 2 categories)

Pattern: Duplication (Pattern B) - similar to siinqee
"""

from adapters.core.html_table import HtmlTableAdapter, TableSpec
from adapters.core.contract import ParseContext, ParseOutcome, RowIssue, IssueCode, Severity
from adapters.transport.base import FetchKind
from adapters.core.numbers import parse_decimal
from adapters.core.currency import normalize_currency
from adapters.core.record_builder import build_record


class BerhanAdapter:
    """
    Berhan Bank adapter with duplication quirk.
    
    HTML has changed from regex parsing to table format:
      Currency | Buying | Selling
      1 USD ($) | 162.37 | 165.62
      
    Each row creates 2 records: one cash, one transactional.
    """
    
    key = "berhan_html"
    url = "https://berhanbanksc.com/exchange-rates/"
    fetch_kind = FetchKind.HTTP_GET
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        from bs4 import BeautifulSoup
        
        if not raw or not raw.strip():
            return ParseOutcome.failed(IssueCode.EMPTY_PAYLOAD, "Empty HTML")
        
        soup = BeautifulSoup(raw, "html.parser")
        tables = soup.find_all("table")
        
        if len(tables) < 1:
            return ParseOutcome.failed(IssueCode.NO_TABLE, "No tables found")
        
        # Use first table (second table is usually a duplicate or empty)
        table = tables[0]
        rows = [r for r in table.find_all("tr") if r.find("td")]
        
        records = []
        issues = []
        
        for row_idx, row in enumerate(rows):
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            
            if len(cells) < 3:
                continue
            
            # Column 0: Currency (format: "1 USD ($)" or "1 EUR (€)")
            currency_text = cells[0]
            currency_code = self._extract_currency_code(currency_text)
            
            if not currency_code:
                continue
            
            # Column 1: Buying rate
            buy = None
            try:
                buy = parse_decimal(cells[1])
            except ValueError:
                issues.append(RowIssue(
                    row_ref=f"{currency_code}",
                    code=IssueCode.BAD_NUMBER,
                    detail=f"Bad buying rate: {cells[1]}",
                    severity=Severity.ERROR
                ))
            
            # Column 2: Selling rate
            sell = None
            try:
                sell = parse_decimal(cells[2])
            except ValueError:
                issues.append(RowIssue(
                    row_ref=f"{currency_code}",
                    code=IssueCode.BAD_NUMBER,
                    detail=f"Bad selling rate: {cells[2]}",
                    severity=Severity.ERROR
                ))
            
            if buy is not None or sell is not None:
                rec_cash = build_record(
                    currency_code=currency_code,
                    category="cash",
                    buying_rate=buy,
                    selling_rate=sell,
                    ctx=ctx
                )
                records.append(rec_cash)
                
                rec_txn = build_record(
                    currency_code=currency_code,
                    category="transactional",
                    buying_rate=buy,
                    selling_rate=sell,
                    ctx=ctx
                )
                records.append(rec_txn)
        
        # Sort for determinism
        records.sort(key=lambda r: (r.source_currency_code, r.category))
        
        # Compute structure hash
        import hashlib
        structure_text = f"berhan_duplication#{len(tables)}"
        structure_hash = hashlib.sha256(structure_text.encode()).hexdigest()[:16]
        
        return ParseOutcome(
            records=tuple(records),
            issues=tuple(issues),
            rows_seen=len(rows),
            structure_hash=structure_hash
        )
    
    def _extract_currency_code(self, text: str) -> str:
        """
        Extract currency code from text like "1 USD ($)" or "1 EUR (€)".
        """
        import re
        
        # Try to find 3-letter currency code
        match = re.search(r'\b([A-Z]{3})\b', text)
        if match:
            code = match.group(1)
            normalized = normalize_currency(code)
            return normalized or code
        
        # Fallback: try normalize on full text
        normalized = normalize_currency(text)
        if normalized:
            return normalized
        
        return ""


ADAPTER = BerhanAdapter()
