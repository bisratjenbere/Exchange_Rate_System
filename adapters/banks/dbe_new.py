"""
DBE (Development Bank of Ethiopia) adapter - TableSpec implementation.

Migration notes:
- Old adapter: 91 LOC with custom parsing + date extraction
- New adapter: ~25 LOC TableSpec
- Simple table: Code | Buying | Selling
- Single category (cash), 19 currencies
- Pure TableSpec, no wrapper needed
"""

from adapters.core.html_table import HtmlTableAdapter, TableSpec
from adapters.core.contract import ParseContext, ParseOutcome
from adapters.transport.base import FetchKind
from datetime import date
    
SPEC = TableSpec(
    key="dbe_html",
    url="https://dbe.com.et/",
    headers={
        "currency": ("code", "currency"),
        "buy": ("buying",),
        "sell": ("selling",),
    },
    required=("currency", "buy", "sell"),
)

ADAPTER = HtmlTableAdapter(SPEC)
