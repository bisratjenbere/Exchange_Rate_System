import html
import json
from datetime import date
from decimal import Decimal

from adapters.addis_fortune.adapter import AddisFortuneAdapter
from adapters.zemen.adapter import ZemenAdapter


def test_addis_fortune_anbesa_slug_inverts_field_mappings():
    adapter = AddisFortuneAdapter("anbesa-bank-1")
    assert adapter.FIELD_CONFIG.get("field_mappings") == {
        "cashBuying": "transactional",
        "cashSelling": "transactional",
        "transBuying": "cash",
        "transSelling": "cash",
    }


def test_addis_fortune_default_slug_retains_default_field_mappings():
    adapter = AddisFortuneAdapter("cbe")
    assert adapter.FIELD_CONFIG == {}


def test_addis_fortune_anbesa_parse_correctly_maps_categories():
    af_date_str = date.today().strftime("%b %d, %Y")
    snapshot_data = {
        "data": {
            "exchanges": [[
                {
                    "currency": "USD",
                    "applicable_date": af_date_str,
                    "cashBuying": 162.4721,
                    "cashSelling": 165.7215,
                    "transBuying": 163.7354,
                    "transSelling": 167.0101,
                }
            ]]
        }
    }
    raw_html = f'<div wire:snapshot="{html.escape(json.dumps(snapshot_data))}"></div>'
    adapter = AddisFortuneAdapter("anbesa-bank-1")
    result = adapter.parse(raw_html)

    assert result.is_success()
    assert len(result.records) == 2

    by_cat = {r.category: r for r in result.records}
    assert "cash" in by_cat
    assert "transactional" in by_cat

    assert by_cat["cash"].buying_rate == Decimal("163.7354")
    assert by_cat["cash"].selling_rate == Decimal("167.0101")

    assert by_cat["transactional"].buying_rate == Decimal("162.4721")
    assert by_cat["transactional"].selling_rate == Decimal("165.7215")


def test_zemen_adapter_parses_without_error():
    adapter = ZemenAdapter()
    payload = json.dumps({
        "status": "success",
        "date": "2026-11-06",
        "rates": {
            "day": [
                {
                    "currency_code": "USD",
                    "buying": "163.50",
                    "selling": "166.50",
                    "exchange_id": 1,
                }
            ]
        },
    })
    result = adapter.parse(payload)

    assert result.is_success()
    assert len(result.records) == 1
    assert result.records[0].source_currency_code == "USD"
    assert result.records[0].category == "transactional"
    assert result.records[0].buying_rate == Decimal("163.50")
    assert result.records[0].selling_rate == Decimal("166.50")


def test_zemen_adapter_parses_day_and_average():
    adapter = ZemenAdapter()
    payload = json.dumps({
        "status": "success",
        "date": "2026-11-06",
        "avg_date": "2026-11-05",
        "rates": {
            "day": [
                {
                    "currency_code": "USD",
                    "buying_rate": "161.0980",
                    "selling_rate": "164.3200",
                    "cash_buying_rate": "162.7090",
                    "cash_selling_rate": "165.9632",
                    "exchange_id": 101,
                    "post_date": "2026-11-06 08:30:00",
                }
            ],
            "average": [
                {
                    "currency_code": "USD",
                    "avg_buying_rate": "162.9642",
                    "avg_selling_rate": "166.4068",
                    "buying_rate": "160.5000",
                    "selling_rate": "163.7000",
                    "cash_buying_rate": "162.0000",
                    "cash_selling_rate": "165.2000",
                    "exchange_id": 100,
                    "post_date": "2026-11-05 16:30:00",
                }
            ]
        },
    })
    result = adapter.parse(payload)

    assert result.is_success()
    assert len(result.records) == 3

    by_cat = {r.category: r for r in result.records}
    assert "cash" in by_cat
    assert "transactional" in by_cat
    assert "weighted_average" in by_cat

    assert by_cat["cash"].buying_rate == Decimal("162.7090")
    assert by_cat["cash"].selling_rate == Decimal("165.9632")
    assert by_cat["cash"].effective_date == date(2026, 11, 6)

    assert by_cat["transactional"].buying_rate == Decimal("161.0980")
    assert by_cat["transactional"].selling_rate == Decimal("164.3200")
    assert by_cat["transactional"].effective_date == date(2026, 11, 6)

    assert by_cat["weighted_average"].buying_rate == Decimal("162.9642")
    assert by_cat["weighted_average"].selling_rate == Decimal("166.4068")
    assert by_cat["weighted_average"].effective_date == date(2026, 11, 5)
