"""
Siinqee Bank adapter - TableSpec implementation.

Migration notes:
- Old adapter: 54 LOC with custom parsing
- New adapter: ~30 LOC TableSpec
- Quirk: Bank publishes single rate pair, we emit as both cash + transactional
"""

from adapters.core.html_table import HtmlTableAdapter, TableSpec
from adapters.core.contract import ParseContext, ParseOutcome
from adapters.transport.base import FetchKind

SPEC = TableSpec(
    key="siinqee_html",
    url="https://siinqeebank.com/",
    headers={
        "currency": ("currency", "code"),
        "buy": ("buying",),
        "sell": ("selling",),
    },
    required=("currency", "buy", "sell"),
)

_BASE_ADAPTER = HtmlTableAdapter(SPEC)


class SiinqeeAdapter:
    """
    Wrapper to handle siinqee's quirk: duplicate records for cash + transactional.
    
    Bank publishes single rate pair per currency, but old adapter emits 2 records
    (cash + transactional) for backward compatibility with consumers.
    """
    
    key = SPEC.key
    url = SPEC.url
    fetch_kind = FetchKind.HTTP_GET
    
    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        # Parse once with base adapter
        outcome = _BASE_ADAPTER.parse(raw, ctx)
        
        # If failed, return as-is
        if not outcome.records:
            return outcome
        
        # Duplicate each record for cash + transactional
        duplicated = []
        for rec in outcome.records:
            # Cash record
            cash_rec = rec  # Already has category from ctx
            duplicated.append(cash_rec)
            
            # Transactional record (copy with changed category)
            from copy import copy
            txn_rec = copy(cash_rec)
            txn_rec.category = "transactional"
            duplicated.append(txn_rec)
        
        # Return with duplicated records
        from dataclasses import replace
        return replace(outcome, records=duplicated)


ADAPTER = SiinqeeAdapter()
