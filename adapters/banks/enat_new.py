"""
Enat Bank adapter - Regex-based with duplication pattern.

Migration notes:
- Old adapter: 112 LOC (adapters/enat/adapter.py, regex-based)
- New adapter: Regex-based with duplication (Pattern B)
- Text format: "Currency Buying Selling USD 161.84 165.08 EUR 187.51 191.26 ..."
- Duplicates each record for cash + transactional categories
- Total: 12 records (6 currencies × 2 categories)

Pattern: Duplication (Pattern B) with regex parsing
"""

from adapters.core.html_table import HtmlTableAdapter, TableSpec
from adapters.core.contract import ParseContext, ParseOutcome, RowIssue, IssueCode, Severity
from adapters.transport.base import FetchKind
from adapters.core.numbers import parse_decimal
from adapters.core.currency import normalize_currency
from adapters.core.record_builder import build_record
import re


class EnatAdapter:
    """
    Enat Bank adapter with regex parsing and duplication quirk.
    
    HTML has no tables, uses text format:
      Currency Buying Selling
      USD 161.8495 165.0865
      EUR 187.5122 191.2624
      ...
      
    Each row creates 2 records: one cash, one transactional.
    """
    
    key = "enat_html"
    url = "https://www.enatbanksc.com/"
    fetch_kind = FetchKind.HTTP_GET
    
    # Regex patterns
    _BLOCK_START = re.compile(r"Currency\s+Buying\s+Selling", re.IGNORECASE)
    _RATE_RE = re.compile(r"([A-Z]{3})\s+([\d.]+)\s+([\d.]+)")
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        from bs4 import BeautifulSoup
        
        if not raw or not raw.strip():
            return ParseOutcome.failed(IssueCode.EMPTY_PAYLOAD, "Empty HTML")
        
        # Extract text from HTML
        soup = BeautifulSoup(raw, "html.parser")
        text = soup.get_text(" ", strip=True)
        
        # Find the "Currency Buying Selling" block
        m_start = self._BLOCK_START.search(text)
        if not m_start:
            return ParseOutcome.failed(IssueCode.NO_TABLE, "Currency rate block not found")
        
        # Extract the rate section
        rate_text = text[m_start.end():]
        
        records = []
        issues = []
        seen = set()
        
        for match in self._RATE_RE.finditer(rate_text):
            code = match.group(1).upper()
            
            # Stop if we see a repeated currency (indicates end of rate block)
            if code in seen:
                break
            seen.add(code)
            
            # Normalize currency code
            currency_code = normalize_currency(code)
            if not currency_code:
                currency_code = code
            
            # Parse buying and selling rates
            buy = None
            sell = None
            
            try:
                buy = parse_decimal(match.group(2))
            except ValueError:
                issues.append(RowIssue(
                    row_ref=currency_code,
                    code=IssueCode.BAD_NUMBER,
                    detail=f"Bad buying rate: {match.group(2)}",
                    severity=Severity.ERROR
                ))
            
            try:
                sell = parse_decimal(match.group(3))
            except ValueError:
                issues.append(RowIssue(
                    row_ref=currency_code,
                    code=IssueCode.BAD_NUMBER,
                    detail=f"Bad selling rate: {match.group(3)}",
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
        structure_text = f"enat_regex#{len(seen)}_currencies"
        structure_hash = hashlib.sha256(structure_text.encode()).hexdigest()[:16]
        
        return ParseOutcome(
            records=tuple(records),
            issues=tuple(issues),
            rows_seen=len(seen),
            structure_hash=structure_hash
        )


ADAPTER = EnatAdapter()
