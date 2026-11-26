"""
Oromia Bank adapter - TableSpec implementation.

Migration notes:
- Old adapter: 96 LOC HTMLTableAdapter
- New adapter: ~25 LOC TableSpec
- Simple table: Currency | Buying | Selling
- Single category (cash), no duplication needed
- Note: No golden file exists for this adapter
"""

from adapters.core.html_table import HtmlTableAdapter, TableSpec
from adapters.core.contract import ParseContext, ParseOutcome
from adapters.transport.base import FetchKind

SPEC = TableSpec(
    key="oromia_html",
    url="https://orointbank.com/exchange-rate/",
    headers={
        "currency": ("currency", "code", "symbol"),
        "buy": ("buying", "cash buying", "we buy"),
        "sell": ("selling", "cash selling", "we sell"),
    },
    required=("currency", "buy", "sell"),
)

ADAPTER = HtmlTableAdapter(SPEC)
