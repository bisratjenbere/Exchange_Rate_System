"""
Shabelle Bank adapter - Div block-based with cash/transactional.

Migration notes:
- Old adapter: 140 LOC (adapters/shabelle/adapter.py)
- New adapter: Div block parsing with Pattern B duplication
- Structure: exchange-block-one divs with upper-box (cash) and lower-box (transactional)
- Total: 12 records (6 currencies × 2 categories)

Pattern: Div block parsing (similar to Pattern B)
"""

from adapters.core.html_table import HtmlTableAdapter, TableSpec
from adapters.core.contract import ParseContext, ParseOutcome, RowIssue, IssueCode, Severity
from adapters.transport.base import FetchKind
from adapters.core.numbers import parse_decimal
from adapters.core.currency import normalize_currency
from adapters.core.record_builder import build_record
import hashlib
from bs4 import BeautifulSoup


class ShabelleAdapter:
    """
    Shabelle Bank adapter parsing div blocks.
    
    HTML structure:
      <div class="exchange-block-one">
        <div class="upper-box">  <!-- Cash -->
          <h4>usd</h4>
          <div class="buys-box">
            <p>161.84 165.08</p>
          </div>
        </div>
        <div class="lower-box">  <!-- Transactional -->
          <div class="buys-box">
            <p>161.84 165.08</p>
          </div>
        </div>
      </div>
      
    Each block creates 2 records: one cash, one transactional.
    """
    
    key = "shabelle_html"
    url = "https://shabellebank.com/"
    fetch_kind = FetchKind.HTTP_GET
    
    # Currency code mapping
    _CODE_MAP = {
        "usd": "USD",
        "euro": "EUR", 
        "eur": "EUR",
        "uae": "AED",
        "gbp": "GBP",
        "cad": "CAD",
        "aed": "AED",
        "sar": "SAR",
        "cny": "CNY",
        "chf": "CHF"
    }
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        if not raw or not raw.strip():
            return ParseOutcome.failed(IssueCode.EMPTY_PAYLOAD, "Empty HTML")
        
        soup = BeautifulSoup(raw, "html.parser")
        
        # Find all exchange blocks
        blocks = soup.find_all("div", class_="exchange-block-one")
        
        if not blocks:
            return ParseOutcome.failed(IssueCode.NO_TABLE, "No exchange-block-one divs found")
        
        records = []
        issues = []
        
        for block_idx, block in enumerate(blocks):
            # Parse upper-box (cash) and lower-box (transactional)
            for box_class, category in [("upper-box", "cash"), ("lower-box", "transactional")]:
                box = block.find("div", class_=box_class)
                if not box:
                    continue
                
                # Get currency code from h4 (only in upper-box usually)
                currency_code = None
                h4 = block.find("h4")  # Search in block, not just box
                if h4:
                    raw_code = h4.get_text(strip=True)
                    mapped_code = self._CODE_MAP.get(raw_code.lower(), raw_code.upper())
                    currency_code = normalize_currency(mapped_code)
                    if not currency_code:
                        currency_code = mapped_code
                
                if not currency_code:
                    continue
                
                buys_box = box.find("div", class_="buys-box")
                if not buys_box:
                    continue
                
                p = buys_box.find("p")
                if not p:
                    continue
                
                # Parse "161.84 165.08" format
                values = p.get_text(strip=True).split()
                if len(values) < 2:
                    continue
                
                buy = None
                sell = None
                
                try:
                    buy = parse_decimal(values[0])
                except ValueError:
                    pass
                
                try:
                    sell = parse_decimal(values[1])
                except ValueError:
                    pass
                
                if buy is not None or sell is not None:
                    rec = build_record(
                        currency_code=currency_code,
                        category=category,
                        buying_rate=buy,
                        selling_rate=sell,
                        ctx=ctx
                    )
                    records.append(rec)
        
        records.sort(key=lambda r: (r.source_currency_code, r.category))
        
        structure_text = f"shabelle_divblocks#{len(blocks)}"
        structure_hash = hashlib.sha256(structure_text.encode()).hexdigest()[:16]
        
        return ParseOutcome(
            records=tuple(records),
            issues=tuple(issues),
            rows_seen=len(blocks),
            structure_hash=structure_hash
        )


ADAPTER = ShabelleAdapter()
