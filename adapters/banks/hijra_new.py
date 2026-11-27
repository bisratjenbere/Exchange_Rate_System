import hashlib

from bs4 import BeautifulSoup

from adapters.core.contract import IssueCode, ParseContext, ParseOutcome
from adapters.core.currency import normalize_currency
from adapters.core.numbers import parse_decimal
from adapters.core.record_builder import build_record
from adapters.transport.base import FetchKind


class HijraAdapter:
    key = "hijra_html"
    url = "https://hijra-bank.com"
    fetch_kind = FetchKind.HTTP_GET

    def parse(self, raw: str, ctx: ParseContext) -> ParseOutcome:
        if not raw or not raw.strip():
            return ParseOutcome.failed(IssueCode.EMPTY_PAYLOAD, "Empty HTML payload")

        soup = BeautifulSoup(raw, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            return ParseOutcome.failed(IssueCode.NO_TABLE, "No rate table found")

        table = soup.find("table", class_="rate-table") or tables[0]
        rows = [tr for tr in table.find_all("tr") if tr.find("td")]
        if not rows:
            return ParseOutcome.failed(IssueCode.NO_ROWS, "No rate rows found")

        records = []
        issues = []
        rows_seen = 0

        for tr in rows:
            cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) < 5:
                continue

            curr_code = normalize_currency(cells[0])
            if not curr_code:
                continue

            rows_seen += 1
            cash_buy = parse_decimal(cells[1])
            cash_sell = parse_decimal(cells[2])
            txn_buy = parse_decimal(cells[3])
            txn_sell = parse_decimal(cells[4])

            if cash_buy is not None or cash_sell is not None:
                records.append(build_record(
                    currency_code=curr_code,
                    category="cash",
                    buying_rate=cash_buy,
                    selling_rate=cash_sell,
                    ctx=ctx
                ))

            if txn_buy is not None or txn_sell is not None:
                records.append(build_record(
                    currency_code=curr_code,
                    category="transactional",
                    buying_rate=txn_buy,
                    selling_rate=txn_sell,
                    ctx=ctx
                ))

        records.sort(key=lambda r: (r.source_currency_code, r.category))
        structure_hash = hashlib.sha256(f"hijra_html_{rows_seen}".encode()).hexdigest()[:16]

        return ParseOutcome(
            records=tuple(records),
            issues=tuple(issues),
            rows_seen=rows_seen,
            structure_hash=structure_hash
        )

ADAPTER = HijraAdapter()
