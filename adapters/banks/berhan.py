import hashlib
import re

from bs4 import BeautifulSoup
from adapters.core.contract import ParseContext, ParseOutcome, RowIssue, IssueCode, Severity
from adapters.transport.base import FetchKind
from adapters.core.numbers import parse_decimal
from adapters.core.currency import normalize_currency
from adapters.core.record_builder import build_record


class BerhanAdapter:
    key = "berhan_html"
    url = "https://berhanbanksc.com/exchange-rates/"
    fetch_kind = FetchKind.HTTP_GET

    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        if not raw or not raw.strip():
            return ParseOutcome.failed(IssueCode.EMPTY_PAYLOAD, "Empty HTML")

        soup = BeautifulSoup(raw, "html.parser")
        tables = soup.find_all("table")

        if len(tables) < 1:
            return ParseOutcome.failed(IssueCode.NO_TABLE, "No tables found")

        table = tables[0]
        rows = [r for r in table.find_all("tr") if r.find("td")]

        records = []
        issues = []

        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]

            if len(cells) < 3:
                continue

            currency_code = self._extract_currency_code(cells[0])
            if not currency_code:
                continue

            buy = None
            try:
                buy = parse_decimal(cells[1])
            except ValueError:
                issues.append(RowIssue(
                    row_ref=currency_code,
                    code=IssueCode.BAD_NUMBER,
                    detail=f"Bad buying rate: {cells[1]}",
                    severity=Severity.ERROR
                ))

            sell = None
            try:
                sell = parse_decimal(cells[2])
            except ValueError:
                issues.append(RowIssue(
                    row_ref=currency_code,
                    code=IssueCode.BAD_NUMBER,
                    detail=f"Bad selling rate: {cells[2]}",
                    severity=Severity.ERROR
                ))

            if buy is not None or sell is not None:
                records.append(build_record(
                    currency_code=currency_code,
                    category="cash",
                    buying_rate=buy,
                    selling_rate=sell,
                    ctx=ctx
                ))
                records.append(build_record(
                    currency_code=currency_code,
                    category="transactional",
                    buying_rate=buy,
                    selling_rate=sell,
                    ctx=ctx
                ))

        records.sort(key=lambda r: (r.source_currency_code, r.category))

        structure_hash = hashlib.sha256(
            f"berhan_duplication#{len(tables)}".encode()
        ).hexdigest()[:16]

        return ParseOutcome(
            records=tuple(records),
            issues=tuple(issues),
            rows_seen=len(rows),
            structure_hash=structure_hash
        )

    def _extract_currency_code(self, text: str) -> str:
        match = re.search(r'\b([A-Z]{3})\b', text)
        if match:
            return normalize_currency(match.group(1)) or match.group(1)
        return normalize_currency(text) or ""


ADAPTER = BerhanAdapter()
