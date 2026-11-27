from datetime import date
from decimal import Decimal

from adapters.banks.hijra_new import ADAPTER, HijraAdapter
from adapters.core.contract import IssueCode, ParseContext
from adapters.core.protocol import is_universal_adapter, validate_adapter
from adapters.transport.base import FetchKind
from infrastructure.adapter_registry_v2 import default_registry

SAMPLE_HTML = """
<div class="exchange-wrapper">
  <div class="exchange-title">Daily Exchange Rates and Weighted Rates</div>
  <div class="exchange-sub">Applicable on 03-Sep-26</div>
  <div id="daily">
    <table class="rate-table">
      <tr>
        <th>Currency</th>
        <th>Cash Buying</th>
        <th>Cash Selling</th>
        <th>Txn Buying</th>
        <th>Txn Selling</th>
      </tr>
      <tr>
        <td>US Dollar</td>
        <td>161.6620</td>
        <td>164.8952</td>
        <td>161.6620</td>
        <td>164.8952</td>
      </tr>
      <tr>
        <td>Euro</td>
        <td>188.6920</td>
        <td>192.4658</td>
        <td>188.6920</td>
        <td>192.4658</td>
      </tr>
      <tr>
        <td>Pound Sterling</td>
        <td>218.4280</td>
        <td>222.7966</td>
        <td>218.4280</td>
        <td>222.7966</td>
      </tr>
      <tr>
        <td>Saudi Riyal</td>
        <td>45.2526</td>
        <td>46.1577</td>
        <td>45.2526</td>
        <td>46.1577</td>
      </tr>
      <tr>
        <td>UAE Dirham</td>
        <td>47.1669</td>
        <td>48.1102</td>
        <td>47.1669</td>
        <td>48.1102</td>
      </tr>
    </table>
  </div>
</div>
"""

def test_protocol_compliance():
    adapter = HijraAdapter()
    assert is_universal_adapter(adapter)
    assert validate_adapter(adapter) == []
    assert adapter.key == "hijra_html"
    assert adapter.url == "https://hijra-bank.com"
    assert adapter.fetch_kind == FetchKind.HTTP_GET

def test_parse_valid_html():
    ctx = ParseContext(category="cash", collection_date=date(2026, 11, 27), source_id=62)
    outcome = ADAPTER.parse(SAMPLE_HTML, ctx)

    assert len(outcome.records) == 10
    assert outcome.rows_seen == 5
    assert outcome.structure_hash is not None

    usd_cash = next(r for r in outcome.records if r.source_currency_code == "USD" and r.category == "cash")
    assert usd_cash.buying_rate == Decimal("161.6620")
    assert usd_cash.selling_rate == Decimal("164.8952")
    assert usd_cash.effective_date == date(2026, 11, 27)
    assert usd_cash.effective_date_basis == "collection_date_fallback"

    usd_txn = next(r for r in outcome.records if r.source_currency_code == "USD" and r.category == "transactional")
    assert usd_txn.buying_rate == Decimal("161.6620")
    assert usd_txn.selling_rate == Decimal("164.8952")

    eur_cash = next(r for r in outcome.records if r.source_currency_code == "EUR" and r.category == "cash")
    assert eur_cash.buying_rate == Decimal("188.6920")
    assert eur_cash.selling_rate == Decimal("192.4658")

def test_parse_empty_payload():
    ctx = ParseContext(category="cash", collection_date=date(2026, 11, 27), source_id=62)
    outcome = ADAPTER.parse("", ctx)
    assert len(outcome.records) == 0
    assert any(i.code == IssueCode.EMPTY_PAYLOAD for i in outcome.issues)

def test_parse_no_table():
    ctx = ParseContext(category="cash", collection_date=date(2026, 11, 27), source_id=62)
    outcome = ADAPTER.parse("<html><body><div>No tables</div></body></html>", ctx)
    assert len(outcome.records) == 0
    assert any(i.code == IssueCode.NO_TABLE for i in outcome.issues)

def test_registry_integration():
    assert default_registry.is_registered("hijra_html")
    adapter = default_registry.get("hijra_html")
    assert adapter.key == "hijra_html"
