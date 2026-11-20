from datetime import date
from decimal import Decimal
from adapters.bunna.adapter import BunnaAdapter

SAMPLE_BUNNA_JSON = """{
  "content": [
    {
      "currencyCode": "USD",
      "currency": "US Dollar",
      "buying": 165.6015,
      "selling": 168.9135,
      "transactionBuying": 162.3065,
      "transactionSelling": 165.5526,
      "valueDate": "2026-11-20T16:15:01.319814"
    },
    {
      "currencyCode": "EUR",
      "currency": "Euro",
      "buying": 191.8096,
      "selling": 195.6458,
      "transactionBuying": 187.9995,
      "transactionSelling": 191.7595,
      "valueDate": "2026-11-20T16:15:01.298032"
    }
  ]
}"""

def test_bunna_adapter_parses_json_payload():
    adapter = BunnaAdapter()
    result = adapter.parse(SAMPLE_BUNNA_JSON)
    assert len(result.errors) == 0
    assert len(result.records) == 4

    usd_cash = next(r for r in result.records if r.source_currency_code == 'USD' and r.category == 'cash')
    assert usd_cash.buying_rate == Decimal('165.6015')
    assert usd_cash.selling_rate == Decimal('168.9135')
    assert usd_cash.effective_date == date(2026, 11, 20)
    assert usd_cash.effective_date_basis == 'source_published'

    usd_txn = next(r for r in result.records if r.source_currency_code == 'USD' and r.category == 'transactional')
    assert usd_txn.buying_rate == Decimal('162.3065')
    assert usd_txn.selling_rate == Decimal('165.5526')
    assert usd_txn.effective_date == date(2026, 11, 20)

def test_bunna_adapter_parses_legacy_html():
    html = """
    <table>
      <tr><th>Currency</th><th>Code</th><th>Cash Buying</th><th>Cash Selling</th><th>Txn Buying</th><th>Txn Selling</th></tr>
      <tr><td>US Dollar</td><td>USD</td><td>160.00</td><td>163.00</td><td>158.00</td><td>161.00</td></tr>
    </table>
    """
    adapter = BunnaAdapter()
    result = adapter.parse(html)
    assert len(result.errors) == 0
    assert len(result.records) == 2

def test_bunna_adapter_empty_json():
    adapter = BunnaAdapter()
    result = adapter.parse('{"content": []}')
    assert len(result.errors) == 1
    assert len(result.records) == 0
