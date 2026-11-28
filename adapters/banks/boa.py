"""
Bank of Abyssinia adapter - TableSpec implementation.

Migration notes:
- Old adapter: 101 LOC HTMLTableAdapter
- New adapter: ~25 LOC TableSpec
- Simple table: Currency | Buying | Selling
- Single category (cash), no duplication needed
"""

from adapters.core.html_table import HtmlTableAdapter, TableSpec
from adapters.core.contract import ParseContext, ParseOutcome
from adapters.transport.base import FetchKind

SPEC = TableSpec(
    key="boa_html",
    url="https://www.bankofabyssinia.com/",
    headers={
        "currency": ("currency type", "currency", "code", "symbol"),
        "buy": ("cash buying rate", "buying", "cash buying", "we buy"),
        "sell": ("cash selling rate", "selling", "cash selling", "we sell"),
    },
    required=("currency", "buy", "sell"),
    header_row=2,
)

ADAPTER = HtmlTableAdapter(SPEC)
