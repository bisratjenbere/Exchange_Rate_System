
import hashlib

from bs4 import BeautifulSoup
from adapters.core.html_table import HtmlTableAdapter, TableSpec
from adapters.core.contract import ParseContext, ParseOutcome, RowIssue, IssueCode, Severity
from adapters.transport.base import FetchKind
from adapters.core.numbers import parse_decimal
from adapters.core.currency import normalize_currency
from adapters.core.record_builder import build_record


class AbayAdapter:
    """
    Multi-table adapter for Abay Bank.
    
    Table 0: Weighted Average Rate
      CURRENCY | BUYING | SELLING
      
    Table 1: Cash Rate
      CURRENCY | BUYING | SELLING
      
    Table 2: Transaction Rate
      CURRENCY | BUYING | SELLING
    """
    
    key = "abay_html"
    url = "https://www.abaybanksc.com/"
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
        
        # Parse table 0: Weighted Average Rate
        if len(tables) >= 1:
            table0_records, table0_issues, table0_rows = self._parse_simple_table(
                tables[0], "weighted_average", ctx
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
        
        # Parse table 2: Transaction Rate
        if len(tables) >= 3:
            table2_records, table2_issues, table2_rows = self._parse_simple_table(
                tables[2], "transactional", ctx
            )
            records.extend(table2_records)
            issues.extend(table2_issues)
            rows_seen += table2_rows
        
        # Sort for determinism
        records.sort(key=lambda r: (r.source_currency_code, r.category))
        
        structure_text = f"abay_multi_table#{len(tables)}"
        structure_hash = hashlib.sha256(structure_text.encode()).hexdigest()[:16]
        
        return ParseOutcome(
            records=tuple(records),
            issues=tuple(issues),
            rows_seen=rows_seen,
            structure_hash=structure_hash
        )
    
    def _parse_simple_table(self, table, category: str, ctx: ParseContext):
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        issues = []

        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]

            if len(cells) < 3:
                continue

            currency_code = normalize_currency(cells[0])
            if not currency_code:
                continue

            buy = None
            try:
                buy = parse_decimal(cells[1])
            except ValueError:
                pass

            sell = None
            try:
                sell = parse_decimal(cells[2])
            except ValueError:
                pass

            if buy is not None or sell is not None:
                records.append(build_record(
                    currency_code=currency_code,
                    category=category,
                    buying_rate=buy,
                    selling_rate=sell,
                    ctx=ctx
                ))

        return records, issues, len(rows)


ADAPTER = AbayAdapter()
