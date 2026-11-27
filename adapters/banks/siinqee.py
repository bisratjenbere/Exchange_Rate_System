from copy import copy
from dataclasses import replace

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
    key = SPEC.key
    url = SPEC.url
    fetch_kind = FetchKind.HTTP_GET

    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        outcome = _BASE_ADAPTER.parse(raw, ctx)

        if not outcome.records:
            return outcome

        duplicated = []
        for rec in outcome.records:
            duplicated.append(rec)
            txn_rec = copy(rec)
            txn_rec.category = "transactional"
            duplicated.append(txn_rec)

        return replace(outcome, records=duplicated)


ADAPTER = SiinqeeAdapter()
