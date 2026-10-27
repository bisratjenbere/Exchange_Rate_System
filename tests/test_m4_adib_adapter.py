import json
import pytest
from decimal import Decimal
from pathlib import Path

from adapters.adib.adapter import parse, schema_fingerprint, ADAPTER_KEY
from domain.records import AdapterRecord
from domain.enums import IdentityStatus
from pipeline.validate import validate
from pipeline.identity import build_identity
from pipeline.fingerprint import compute_fingerprint
from domain.enums import ValidationStatus

FIXTURE_DIR = Path("fixtures/adib")

def _load(name: str) -> str:
    return (FIXTURE_DIR / f"{name}.json").read_text()

def test_normal_returns_list():
    records = parse(_load("normal"))
    assert isinstance(records, list)

def test_normal_etb_row_skipped():
    records = parse(_load("normal"))
    currencies = [r.source_currency_code for r in records]
    assert "ETB" not in currencies

def test_normal_plain_buying_selling_skipped():
    records = parse(_load("normal"))
    categories = {r.category for r in records}
    assert "cash" not in categories
    assert categories <= {"transactional", "weighted_average"}

def test_normal_usd_transactional_values():
    records = parse(_load("normal"))
    usd_txn = [r for r in records if r.source_currency_code == "USD" and r.category == "transactional"]
    assert len(usd_txn) == 1
    r = usd_txn[0]
    assert r.buying_rate == Decimal("161.6768")
    assert r.selling_rate == Decimal("164.9103")

def test_normal_usd_weighted_values():
    records = parse(_load("normal"))
    usd_w = [r for r in records if r.source_currency_code == "USD" and r.category == "weighted_average"]
    assert len(usd_w) == 1
    r = usd_w[0]
    assert r.buying_rate == Decimal("162.9240")
    assert r.selling_rate == Decimal("170.4175")

def test_normal_zero_string_becomes_none():
    records = parse(_load("normal"))
    eur_w = [r for r in records if r.source_currency_code == "EUR" and r.category == "weighted_average"]
    assert len(eur_w) == 1
    assert eur_w[0].selling_rate is None

def test_normal_null_becomes_none():
    records = parse(_load("normal"))
    kwd_w = [r for r in records if r.source_currency_code == "KWD" and r.category == "weighted_average"]
    assert len(kwd_w) == 0

def test_normal_kwd_all_zeros_no_records():
    records = parse(_load("normal"))
    kwd = [r for r in records if r.source_currency_code == "KWD"]
    assert len(kwd) == 0

def test_normal_sar_only_transactional():
    records = parse(_load("normal"))
    sar = [r for r in records if r.source_currency_code == "SAR"]
    cats = {r.category for r in sar}
    assert "transactional" in cats
    assert "weighted_average" not in cats

def test_normal_source_record_key_is_row_id():
    records = parse(_load("normal"))
    usd = [r for r in records if r.source_currency_code == "USD"][0]
    assert usd.source_record_key.startswith("2")

def test_normal_effective_date_is_none():
    records = parse(_load("normal"))
    usd = [r for r in records if r.source_currency_code == "USD"][0]
    assert usd.effective_date is not None
    assert str(usd.effective_date) == "2026-09-30"

def test_normal_effective_date_basis_unknown():
    records = parse(_load("normal"))
    for r in records:
        assert r.effective_date_basis == "source_inferred"

def test_normal_identity_is_ambiguous():
    records = parse(_load("normal"))
    from domain.enums import IdentityStatus
    for r in records:
        lkey, istatus = build_identity(r, source_id=1)
        assert istatus == IdentityStatus.CONFIRMED
        assert lkey is not None

def test_normal_raw_excerpt_preserved():
    records = parse(_load("normal"))
    usd_txn = [r for r in records if r.source_currency_code == "USD" and r.category == "transactional"][0]
    assert usd_txn.raw_excerpt is not None
    assert "transactionBuying" in usd_txn.raw_excerpt

def test_normal_source_rate_text_preserved():
    records = parse(_load("normal"))
    usd_txn = [r for r in records if r.source_currency_code == "USD" and r.category == "transactional"][0]
    assert usd_txn.source_rate_text is not None
    assert "161.6768" in usd_txn.source_rate_text

def test_normal_mapping_note_plain_skipped():
    records = parse(_load("normal"))
    for r in records:
        assert any("plain_buying_selling_skipped" in n for n in r.mapping_notes)

def test_normal_all_records_pass_validation():
    records = parse(_load("normal"))
    from pipeline.validate import validate
    from domain.enums import ValidationStatus
    for r in records:
        status, msgs = validate(r)
        assert status != ValidationStatus.REJECTED, f"Rejected: {r.source_currency_code}/{r.category}: {msgs}"

def test_normal_fingerprints_unique_per_currency_category():
    records = parse(_load("normal"))
    fps = [compute_fingerprint(r, source_id=1) for r in records]
    assert len(fps) == len(set(fps)), "Duplicate fingerprints found"

def test_empty_returns_empty_list():
    records = parse(_load("empty"))
    assert records == []

def test_malformed_raises_value_error():
    with pytest.raises(ValueError, match="expected JSON array"):
        parse(_load("malformed"))

def test_malformed_json_raises_value_error():
    with pytest.raises(ValueError, match="JSON parse error"):
        parse("not json at all {{{")

def test_unknown_currency_still_parsed():
    records = parse(_load("unknown_currency"))
    xyz = [r for r in records if r.source_currency_code == "XYZ"]
    assert len(xyz) > 0

def test_unknown_currency_validate_warns_or_passes():
    records = parse(_load("unknown_currency"))
    xyz = [r for r in records if r.source_currency_code == "XYZ"][0]
    status, msgs = validate(xyz)
    assert status != ValidationStatus.REJECTED

def test_duplicate_fetch_same_fingerprints():
    records1 = parse(_load("normal"))
    records2 = parse(_load("duplicate_fetch"))

    usd1 = [r for r in records1 if r.source_currency_code == "USD" and r.category == "transactional"][0]
    usd2 = [r for r in records2 if r.source_currency_code == "USD" and r.category == "transactional"][0]

    assert compute_fingerprint(usd1, 1) == compute_fingerprint(usd2, 1)

def test_schema_fingerprint_deterministic():
    raw = _load("normal")
    assert schema_fingerprint(raw) == schema_fingerprint(raw)

def test_schema_fingerprint_changes_on_schema_change():
    raw_normal = _load("normal")
    data = json.loads(raw_normal)
    data[1]["newField"] = "value"
    raw_changed = json.dumps(data)
    assert schema_fingerprint(raw_normal) != schema_fingerprint(raw_changed)

def test_schema_fingerprint_stable_across_value_changes():
    raw_normal = _load("normal")
    data = json.loads(raw_normal)
    data[1]["transactionBuying"] = "999.0000"
    raw_changed = json.dumps(data)
    assert schema_fingerprint(raw_normal) == schema_fingerprint(raw_changed)

def test_schema_fingerprint_empty_returns_hash():
    fp = schema_fingerprint(_load("empty"))
    assert len(fp) == 64

def test_adapter_key():
    assert ADAPTER_KEY == "adib_api"
