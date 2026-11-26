"""
Goh-Betoch Bank adapter - TableSpec with multi-category wrapper.

Migration notes:
- Old adapter: 81 LOC with custom parsing
- New adapter: TableSpec + wrapper for wide table format
- Wide table: Code | Name | Buying | Selling | WAvgBuying | WAvgSelling
- Creates 3 records per row: transactional, cash (from buying/selling), weighted_average (from WAvg columns)
"""

from adapters.core.html_table import HtmlTableAdapter, TableSpec
from adapters.core.contract import ParseContext, ParseOutcome, RowIssue, IssueCode, Severity
from adapters.transport.base import FetchKind
from adapters.core.numbers import parse_decimal
from adapters.core.currency import normalize_currency
from adapters.core.record_builder import build_record

SPEC = TableSpec(
    key="goh_betoch_html",
    url="https://www.gohbetbank.com/todays-exchange-rate/",
    headers={
        "currency": ("currency code", "code"),
        "buy": ("buying",),
        "sell": ("selling",),
        "wavg_buy": ("weighted average buying", "weighted averagebuying"),
        "wavg_sell": ("weighted average selling", "weighted averageselling"),
    },
    required=("currency", "buy", "sell"),
)


class GohBetochAdapter:
    """
    Wrapper to handle goh_betoch's wide table format.
    
    Bank publishes wide table with 3 rate pairs per row:
    - buying/selling → transactional + cash
    - weighted_average_buying/selling → weighted_average
    """
    
    key = SPEC.key
    url = SPEC.url
    fetch_kind = FetchKind.HTTP_GET
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        from bs4 import BeautifulSoup
        from adapters.core.html_table import find_table_by_headers, _compute_structure_hash
        
        # Parse HTML
        if not raw or not raw.strip():
            return ParseOutcome.failed(IssueCode.EMPTY_PAYLOAD, "Empty HTML")
        
        soup = BeautifulSoup(raw, "html.parser")
        
        # Find table with required headers
        table_match = find_table_by_headers(
            soup,
            SPEC.headers,
            SPEC.required
        )
        
        if not table_match:
            return ParseOutcome.failed(IssueCode.NO_TABLE, 
                                       f"No table with required headers: {SPEC.required}")
        
        table, header_map, header_cells = table_match
        
        # Parse rows
        rows = [r for r in table.find_all("tr") if r.find("td")]
        records = []
        issues = []
        
        for row_idx, row in enumerate(rows):
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            
            # Extract currency
            currency_col = header_map.get("currency")
            if currency_col is None or currency_col >= len(cells):
                continue
            
            currency_text = cells[currency_col]
            currency_code = normalize_currency(currency_text)
            if not currency_code:
                issues.append(RowIssue(
                    row_ref=f"row_{row_idx}",
                    code=IssueCode.UNKNOWN_CURRENCY,
                    detail=f"Unknown currency: {currency_text}",
                    severity=Severity.WARNING
                ))
                currency_code = currency_text.upper()[:3]  # Use first 3 chars as fallback
            
            # Parse transactional/cash rates (from buy/sell columns)
            buy_col = header_map.get("buy")
            sell_col = header_map.get("sell")
            
            buy_rate = None
            sell_rate = None
            
            if buy_col is not None and buy_col < len(cells):
                try:
                    buy_rate = parse_decimal(cells[buy_col])
                except ValueError as e:
                    issues.append(RowIssue(
                        row_ref=currency_code,
                        code=IssueCode.BAD_NUMBER,
                        detail=f"Bad buy rate: {cells[buy_col]}",
                        severity=Severity.ERROR
                    ))
            
            if sell_col is not None and sell_col < len(cells):
                try:
                    sell_rate = parse_decimal(cells[sell_col])
                except ValueError as e:
                    issues.append(RowIssue(
                        row_ref=currency_code,
                        code=IssueCode.BAD_NUMBER,
                        detail=f"Bad sell rate: {cells[sell_col]}",
                        severity=Severity.ERROR
                    ))
            
            if buy_rate is not None or sell_rate is not None:
                for category in ["transactional", "cash"]:
                    rec = build_record(
                        currency_code=currency_code,
                        category=category,
                        buying_rate=buy_rate,
                        selling_rate=sell_rate,
                        ctx=ctx
                    )
                    records.append(rec)
            
            # Parse weighted_average rates (from wavg columns)
            wavg_buy_col = header_map.get("wavg_buy")
            wavg_sell_col = header_map.get("wavg_sell")
            
            wavg_buy_rate = None
            wavg_sell_rate = None
            
            if wavg_buy_col is not None and wavg_buy_col < len(cells):
                try:
                    wavg_buy_rate = parse_decimal(cells[wavg_buy_col])
                except ValueError:
                    pass  # Weighted avg might be missing, don't error
            
            if wavg_sell_col is not None and wavg_sell_col < len(cells):
                try:
                    wavg_sell_rate = parse_decimal(cells[wavg_sell_col])
                except ValueError:
                    pass
            
            if wavg_buy_rate is not None or wavg_sell_rate is not None:
                rec = build_record(
                    currency_code=currency_code,
                    category="weighted_average",
                    buying_rate=wavg_buy_rate,
                    selling_rate=wavg_sell_rate,
                    ctx=ctx
                )
                records.append(rec)
        
        # Sort for determinism
        records.sort(key=lambda r: (r.source_currency_code, r.category))
        
        # Compute structure hash
        structure_hash = _compute_structure_hash(header_cells)
        
        return ParseOutcome(
            records=tuple(records),
            issues=tuple(issues),
            rows_seen=len(rows),
            structure_hash=structure_hash
        )


ADAPTER = GohBetochAdapter()
