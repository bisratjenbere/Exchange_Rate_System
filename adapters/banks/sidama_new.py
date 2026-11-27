"""
Sidama Bank adapter - Regex-based with multiple categories.

Migration notes:
- Old adapter: 105 LOC (adapters/sidama/adapter.py, regex-based)
- New adapter: Regex-based with structured parsing
- Text format: Currency blocks with Cash/Transactional/Prev Weighted rates
- Total: 13 records (6 cash + 6 transactional + 1 weighted_average)

Pattern: Regex with multi-category detection
"""

from adapters.core.html_table import HtmlTableAdapter, TableSpec
from adapters.core.contract import ParseContext, ParseOutcome, RowIssue, IssueCode, Severity
from adapters.transport.base import FetchKind
from adapters.core.numbers import parse_decimal
from adapters.core.currency import normalize_currency
from adapters.core.record_builder import build_record
import re
import hashlib
from bs4 import BeautifulSoup


class SidamaAdapter:
    """
    Sidama Bank adapter with complex regex parsing.
    
    Text format:
      USD US Dollar
      Cash Buying 162.22 Birr
      Cash Selling 165.47 Birr
      Transactional Buying 162.22 Birr
      Transactional Selling 165.47 Birr
      Prev Weighted Buying No Trade
      Prev Weighted Selling 167.83 Birr
    Each block creates up to 3 records: cash, transactional, weighted_average
    (only if rates are available)
    """
    
    key = "sidama_html"
    url = "https://sidamabanksc.com/exchange-rate/"
    fetch_kind = FetchKind.HTTP_GET
    
    # Regex pattern to match currency blocks
    _CURRENCY_BLOCK_RE = re.compile(
        r"(?<![A-Za-z])([A-Z]{3})(?![A-Za-z])\s+[A-Za-z ]+?"
        r"Cash Buying\s+([\d.]+|No Trade)(?:\s+Birr)?\s+"
        r"Cash Selling\s+([\d.]+|No Trade)(?:\s+Birr)?\s+"
        r"Transactional Buying\s+([\d.]+|No Trade)(?:\s+Birr)?\s+"
        r"Transactional Selling\s+([\d.]+|No Trade)(?:\s+Birr)?\s+"
        r"Prev Weighted Buying\s+([\d.]+|No Trade)(?:\s+Birr)?\s+"
        r"Prev Weighted Selling\s+([\d.]+|No Trade)(?:\s+Birr)?",
        re.IGNORECASE
    )
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        if not raw or not raw.strip():
            return ParseOutcome.failed(IssueCode.EMPTY_PAYLOAD, "Empty HTML")
        
        # Extract text from HTML
        soup = BeautifulSoup(raw, "html.parser")
        text = soup.get_text(" ", strip=True)
        
        # Find all currency blocks
        matches = list(self._CURRENCY_BLOCK_RE.finditer(text))
        
        if not matches:
            return ParseOutcome.failed(IssueCode.NO_TABLE, "No currency blocks found")
        
        records = []
        issues = []
        
        for match in matches:
            currency_code = match.group(1).upper()
            normalized = normalize_currency(currency_code)
            if not normalized:
                normalized = currency_code
            
            # Extract rates
            cash_buy_str = match.group(2)
            cash_sell_str = match.group(3)
            txn_buy_str = match.group(4)
            txn_sell_str = match.group(5)
            weighted_buy_str = match.group(6)
            weighted_sell_str = match.group(7)
            
            # Parse cash rates
            cash_buy = self._parse_rate(cash_buy_str)
            cash_sell = self._parse_rate(cash_sell_str)
            
            if cash_buy is not None or cash_sell is not None:
                rec = build_record(
                    currency_code=normalized,
                    category="cash",
                    buying_rate=cash_buy,
                    selling_rate=cash_sell,
                    ctx=ctx
                )
                records.append(rec)
            txn_buy = self._parse_rate(txn_buy_str)
            txn_sell = self._parse_rate(txn_sell_str)
            
            if txn_buy is not None or txn_sell is not None:
                rec = build_record(
                    currency_code=normalized,
                    category="transactional",
                    buying_rate=txn_buy,
                    selling_rate=txn_sell,
                    ctx=ctx
                )
                records.append(rec)
            
            # Parse weighted average rates
            weighted_buy = self._parse_rate(weighted_buy_str)
            weighted_sell = self._parse_rate(weighted_sell_str)
            
            if weighted_buy is not None or weighted_sell is not None:
                rec = build_record(
                    currency_code=normalized,
                    category="weighted_average",
                    buying_rate=weighted_buy,
                    selling_rate=weighted_sell,
                    ctx=ctx
                )
                records.append(rec)
        
        records.sort(key=lambda r: (r.source_currency_code, r.category))
        
        structure_text = f"sidama_regex#{len(matches)}_blocks"
        structure_hash = hashlib.sha256(structure_text.encode()).hexdigest()[:16]
        
        return ParseOutcome(
            records=tuple(records),
            issues=tuple(issues),
            rows_seen=len(matches),
            structure_hash=structure_hash
        )
    
    def _parse_rate(self, rate_str: str):
        """Parse a rate string, return None for 'No Trade' or invalid values."""
        if not rate_str or rate_str.strip().upper() in ['NO TRADE', 'N/A', '']:
            return None
        
        try:
            return parse_decimal(rate_str)
        except ValueError:
            return None


ADAPTER = SidamaAdapter()
