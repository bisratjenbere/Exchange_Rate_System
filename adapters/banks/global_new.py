"""
Global Bank adapter - TableSpec implementation.

Migration notes:
- Old adapter: 73 LOC with custom parsing
- New adapter: ~25 LOC TableSpec
- Simple table: Currency | Buying | Selling
- Single category (cash), no duplication needed
"""

from adapters.core.html_table import HtmlTableAdapter, TableSpec
from adapters.core.contract import ParseContext, ParseOutcome
from adapters.transport.base import FetchKind

SPEC = TableSpec(
    key="global_html",
    url="https://www.globalbankethiopia.com/remittance-forex/",
    headers={
        "currency": ("currency", "code"),
        "buy": ("buying",),
        "sell": ("selling",),
    },
    required=("currency", "buy", "sell"),
)

ADAPTER = HtmlTableAdapter(SPEC)
