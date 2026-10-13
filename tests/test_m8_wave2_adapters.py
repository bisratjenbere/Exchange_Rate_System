"""
Wave 2 adapter tests — Rammis (B1), Wegagen (C1), CBO (E), Hibret (E+SSL).
All tests use fixtures — no network calls (CLAUDE.md testing rules).
"""
import pytest
from decimal import Decimal
from datetime import date
from pathlib import Path

from domain.enums import IdentityStatus, ValidationStatus
from pipeline.identity import build_identity
from pipeline.fingerprint import compute_fingerprint
from pipeline.validate import validate

FIXTURE_DIR = Path("fixtures")


def _load(bank: str, name: str, ext: str = "json") -> str:
    return (FIXTURE_DIR / bank / f"{name}.{ext}").read_text()


# ═══════════════════════════════════════════════════════════════════════════════
# RAMMIS (Type B1 JSON API)
# ═══════════════════════════════════════════════════════════════════════════════

from adapters.rammis.adapter import parse as rammis_parse, schema_fingerprint as rammis_fp, ADAPTER_KEY as RAMMIS_KEY


def test_rammis_adapter_key():
    assert RAMMIS_KEY == "rammis_api"


def test_rammis_normal_returns_list():
    records = rammis_parse(_load("rammis", "normal"))
    assert isinstance(records, list)
    assert len(records) > 0


def test_rammis_normal_usd_values():
    records = rammis_parse(_load("rammis", "normal"))
    usd = [r for r in records if r.source_currency_code == "USD"]
    assert len(usd) == 1
    assert usd[0].buying_rate == Decimal("161.356300")
    assert usd[0].selling_rate == Decimal("164.583400")


def test_rammis_normal_category_unknown():
    """Single buying/selling pair — category not confirmed → UNKNOWN."""
    records = rammis_parse(_load("rammis", "normal"))
    for r in records:
        assert r.category == "UNKNOWN"


def test_rammis_normal_effective_date_source_published():
    records = rammis_parse(_load("rammis", "normal"))
    for r in records:
        assert r.effective_date == date(2026, 10, 10)
        assert r.effective_date_basis == "source_published"


def test_rammis_normal_source_record_key_is_id():
    records = rammis_parse(_load("rammis", "normal"))
    usd = [r for r in records if r.source_currency_code == "USD"][0]
    assert usd.source_record_key == "9"


def test_rammis_normal_identity_confirmed():
    """source_record_key + source_published date → CONFIRMED (stable id + date)."""
    records = rammis_parse(_load("rammis", "normal"))
    for r in records:
        _, istatus = build_identity(r, source_id=2)
        assert istatus == IdentityStatus.CONFIRMED


def test_rammis_normal_all_pass_validation():
    records = rammis_parse(_load("rammis", "normal"))
    for r in records:
        status, _ = validate(r)
        assert status != ValidationStatus.REJECTED


def test_rammis_normal_fingerprints_unique():
    records = rammis_parse(_load("rammis", "normal"))
    fps = [compute_fingerprint(r, source_id=2) for r in records]
    assert len(fps) == len(set(fps))


def test_rammis_normal_raw_excerpt_preserved():
    records = rammis_parse(_load("rammis", "normal"))
    usd = [r for r in records if r.source_currency_code == "USD"][0]
    assert usd.raw_excerpt is not None
    assert "buying" in usd.raw_excerpt


def test_rammis_empty_returns_empty_list():
    records = rammis_parse(_load("rammis", "empty"))
    assert records == []


def test_rammis_malformed_raises_value_error():
    """Top-level array (not object) → ValueError."""
    with pytest.raises(ValueError, match="expected JSON object"):
        rammis_parse(_load("rammis", "malformed"))


def test_rammis_schema_changed_raises_value_error():
    """Missing 'rates' key → ValueError."""
    with pytest.raises(ValueError, match="missing 'rates' key"):
        rammis_parse(_load("rammis", "schema_changed"))


def test_rammis_unknown_currency_passes_through():
    records = rammis_parse(_load("rammis", "unknown_currency"))
    xyz = [r for r in records if r.source_currency_code == "XYZ"]
    assert len(xyz) == 1


def test_rammis_duplicate_fetch_same_fingerprints():
    records1 = rammis_parse(_load("rammis", "normal"))
    records2 = rammis_parse(_load("rammis", "duplicate_fetch"))
    usd1 = [r for r in records1 if r.source_currency_code == "USD"][0]
    usd2 = [r for r in records2 if r.source_currency_code == "USD"][0]
    assert compute_fingerprint(usd1, 2) == compute_fingerprint(usd2, 2)


def test_rammis_schema_fingerprint_deterministic():
    raw = _load("rammis", "normal")
    assert rammis_fp(raw) == rammis_fp(raw)


def test_rammis_schema_fingerprint_changes_on_new_key():
    import json
    raw = _load("rammis", "normal")
    data = json.loads(raw)
    data["rates"][0]["new_field"] = "x"
    assert rammis_fp(raw) != rammis_fp(json.dumps(data))


# ═══════════════════════════════════════════════════════════════════════════════
# WEGAGEN (Type C1 Strapi v4)
# ═══════════════════════════════════════════════════════════════════════════════

from adapters.wegagen.adapter import parse as weg_parse, schema_fingerprint as weg_fp, ADAPTER_KEY as WEG_KEY


def test_wegagen_adapter_key():
    assert WEG_KEY == "wegagen_api"


def test_wegagen_normal_returns_list():
    records = weg_parse(_load("wegagen", "normal"))
    assert isinstance(records, list)
    assert len(records) > 0


def test_wegagen_normal_usd_values():
    records = weg_parse(_load("wegagen", "normal"))
    usd = [r for r in records if r.source_currency_code == "USD"]
    assert len(usd) == 1
    assert usd[0].buying_rate == Decimal("161.7253")
    assert usd[0].selling_rate == Decimal("164.9598")


def test_wegagen_normal_category_unknown():
    """buying == tra_buying — category ambiguous → UNKNOWN."""
    records = weg_parse(_load("wegagen", "normal"))
    for r in records:
        assert r.category == "UNKNOWN"


def test_wegagen_normal_effective_date_source_published():
    records = weg_parse(_load("wegagen", "normal"))
    usd = [r for r in records if r.source_currency_code == "USD"][0]
    assert usd.effective_date == date(2026, 10, 8)
    assert usd.effective_date_basis == "source_published"


def test_wegagen_normal_per_row_dates_differ():
    """CHF has date 2026-10-07, USD has 2026-10-08 — rows updated independently."""
    records = weg_parse(_load("wegagen", "normal"))
    usd = [r for r in records if r.source_currency_code == "USD"][0]
    chf = [r for r in records if r.source_currency_code == "CHF"][0]
    assert usd.effective_date != chf.effective_date


def test_wegagen_normal_source_record_key_is_strapi_id():
    records = weg_parse(_load("wegagen", "normal"))
    usd = [r for r in records if r.source_currency_code == "USD"][0]
    assert usd.source_record_key == "1"


def test_wegagen_normal_unit_multiplier():
    records = weg_parse(_load("wegagen", "normal"))
    for r in records:
        assert r.unit_multiplier == 1


def test_wegagen_normal_identity_confirmed():
    """source_record_key + source_published date → CONFIRMED."""
    records = weg_parse(_load("wegagen", "normal"))
    for r in records:
        _, istatus = build_identity(r, source_id=3)
        assert istatus == IdentityStatus.CONFIRMED


def test_wegagen_normal_all_pass_validation():
    records = weg_parse(_load("wegagen", "normal"))
    for r in records:
        status, _ = validate(r)
        assert status != ValidationStatus.REJECTED


def test_wegagen_normal_fingerprints_unique():
    records = weg_parse(_load("wegagen", "normal"))
    fps = [compute_fingerprint(r, source_id=3) for r in records]
    assert len(fps) == len(set(fps))


def test_wegagen_normal_raw_excerpt_has_tra_fields():
    """raw_excerpt preserves tra_buying/tra_selling for category verification."""
    records = weg_parse(_load("wegagen", "normal"))
    usd = [r for r in records if r.source_currency_code == "USD"][0]
    assert "tra_buying" in usd.raw_excerpt
    assert "tra_selling" in usd.raw_excerpt


def test_wegagen_empty_returns_empty_list():
    records = weg_parse(_load("wegagen", "empty"))
    assert records == []


def test_wegagen_malformed_raises_value_error():
    """No 'data' key → ValueError."""
    with pytest.raises(ValueError, match="missing 'data' key"):
        weg_parse(_load("wegagen", "malformed"))


def test_wegagen_schema_changed_raises_value_error():
    """Required attributes keys missing → ValueError."""
    with pytest.raises(ValueError, match="missing required keys"):
        weg_parse(_load("wegagen", "schema_changed"))


def test_wegagen_unknown_currency_passes_through():
    records = weg_parse(_load("wegagen", "unknown_currency"))
    xyz = [r for r in records if r.source_currency_code == "XYZ"]
    assert len(xyz) == 1


def test_wegagen_schema_fingerprint_deterministic():
    raw = _load("wegagen", "normal")
    assert weg_fp(raw) == weg_fp(raw)


def test_wegagen_schema_fingerprint_changes_on_new_attr():
    import json
    raw = _load("wegagen", "normal")
    data = json.loads(raw)
    data["data"][0]["attributes"]["new_field"] = "x"
    assert weg_fp(raw) != weg_fp(json.dumps(data))


# ═══════════════════════════════════════════════════════════════════════════════
# CBO (Type E wide HTML)
# ═══════════════════════════════════════════════════════════════════════════════

from adapters.cbo.adapter import parse as cbo_parse, schema_fingerprint as cbo_fp, ADAPTER_KEY as CBO_KEY


def test_cbo_adapter_key():
    assert CBO_KEY == "cbo_html"


def test_cbo_normal_returns_tuple():
    result = cbo_parse(_load("cbo", "normal", "html"))
    assert isinstance(result, tuple)
    records, errors = result
    assert isinstance(records, list)
    assert isinstance(errors, list)


def test_cbo_normal_no_errors():
    _, errors = cbo_parse(_load("cbo", "normal", "html"))
    assert errors == []


def test_cbo_normal_usd_cash_values():
    records, _ = cbo_parse(_load("cbo", "normal", "html"))
    usd_cash = [r for r in records if r.source_currency_code == "USD" and r.category == "cash"]
    assert len(usd_cash) == 1
    assert usd_cash[0].buying_rate == Decimal("160.8853")
    assert usd_cash[0].selling_rate == Decimal("164.1030")


def test_cbo_normal_usd_txn_values():
    records, _ = cbo_parse(_load("cbo", "normal", "html"))
    usd_txn = [r for r in records if r.source_currency_code == "USD" and r.category == "transactional"]
    assert len(usd_txn) == 1
    assert usd_txn[0].buying_rate == Decimal("160.8853")


def test_cbo_normal_usd_weighted_values():
    records, _ = cbo_parse(_load("cbo", "normal", "html"))
    usd_w = [r for r in records if r.source_currency_code == "USD" and r.category == "weighted_average"]
    assert len(usd_w) == 1
    assert usd_w[0].buying_rate == Decimal("163.5992")


def test_cbo_normal_date_extracted():
    records, _ = cbo_parse(_load("cbo", "normal", "html"))
    for r in records:
        assert r.effective_date == date(2026, 10, 10)
        assert r.effective_date_basis == "source_published"


def test_cbo_normal_gbp_weighted_no_trade():
    """GBP weighted avg has '-' for both sides → no record emitted."""
    records, _ = cbo_parse(_load("cbo", "normal", "html"))
    gbp_w = [r for r in records if r.source_currency_code == "GBP" and r.category == "weighted_average"]
    assert len(gbp_w) == 0


def test_cbo_normal_currency_code_extracted():
    """'USD - US Dollar' → source_currency_code='USD', currency_name='US Dollar'."""
    records, _ = cbo_parse(_load("cbo", "normal", "html"))
    usd = [r for r in records if r.source_currency_code == "USD"][0]
    assert usd.currency_name == "US Dollar"


def test_cbo_normal_identity_confirmed():
    """source_published date, no source_record_key → CONFIRMED via date-only path."""
    records, _ = cbo_parse(_load("cbo", "normal", "html"))
    for r in records:
        _, istatus = build_identity(r, source_id=4)
        assert istatus == IdentityStatus.CONFIRMED


def test_cbo_normal_all_pass_validation():
    records, _ = cbo_parse(_load("cbo", "normal", "html"))
    for r in records:
        status, _ = validate(r)
        assert status != ValidationStatus.REJECTED


def test_cbo_empty_returns_empty_records():
    records, errors = cbo_parse(_load("cbo", "empty", "html"))
    assert records == []
    assert errors == []


def test_cbo_malformed_returns_errors():
    """No tables → errors list non-empty, records empty."""
    records, errors = cbo_parse(_load("cbo", "malformed", "html"))
    assert records == []
    assert len(errors) > 0


def test_cbo_no_date_fallback_basis():
    """Date missing from header → collection_date_fallback."""
    records, _ = cbo_parse(_load("cbo", "no_date", "html"))
    for r in records:
        assert r.effective_date_basis == "collection_date_fallback"
        assert r.effective_date is None


def test_cbo_no_date_identity_ambiguous():
    records, _ = cbo_parse(_load("cbo", "no_date", "html"))
    for r in records:
        _, istatus = build_identity(r, source_id=4)
        assert istatus == IdentityStatus.AMBIGUOUS


def test_cbo_schema_fingerprint_deterministic():
    raw = _load("cbo", "normal", "html")
    assert cbo_fp(raw) == cbo_fp(raw)


def test_cbo_schema_fingerprint_changes_on_table_change():
    raw = _load("cbo", "normal", "html")
    raw_malformed = _load("cbo", "malformed", "html")
    assert cbo_fp(raw) != cbo_fp(raw_malformed)


# ═══════════════════════════════════════════════════════════════════════════════
# HIBRET (Type E wide HTML + SSL)
# ═══════════════════════════════════════════════════════════════════════════════

from adapters.hibret.adapter import parse as hibret_parse, schema_fingerprint as hibret_fp, ADAPTER_KEY as HIBRET_KEY, SSL_VERIFY


def test_hibret_adapter_key():
    assert HIBRET_KEY == "hibret_html"


def test_hibret_ssl_verify_false():
    """SSL_VERIFY must be False — access finding recorded."""
    assert SSL_VERIFY is False


def test_hibret_normal_returns_tuple():
    result = hibret_parse(_load("hibret", "normal", "html"))
    assert isinstance(result, tuple)
    records, errors = result
    assert isinstance(records, list)
    assert isinstance(errors, list)


def test_hibret_normal_no_errors():
    _, errors = hibret_parse(_load("hibret", "normal", "html"))
    assert errors == []


def test_hibret_normal_usd_cash_values():
    records, _ = hibret_parse(_load("hibret", "normal", "html"))
    usd_cash = [r for r in records if r.source_currency_code == "USD" and r.category == "cash"]
    assert len(usd_cash) == 1
    assert usd_cash[0].buying_rate == Decimal("163.3499")
    assert usd_cash[0].selling_rate == Decimal("166.6169")


def test_hibret_normal_usd_txn_values():
    records, _ = hibret_parse(_load("hibret", "normal", "html"))
    usd_txn = [r for r in records if r.source_currency_code == "USD" and r.category == "transactional"]
    assert len(usd_txn) == 1
    assert usd_txn[0].buying_rate == Decimal("161.7326")
    assert usd_txn[0].selling_rate == Decimal("164.9673")


def test_hibret_normal_no_date():
    """No date in table → collection_date_fallback."""
    records, _ = hibret_parse(_load("hibret", "normal", "html"))
    for r in records:
        assert r.effective_date is None
        assert r.effective_date_basis == "collection_date_fallback"


def test_hibret_normal_identity_ambiguous():
    """No source-published date → identity ambiguous."""
    records, _ = hibret_parse(_load("hibret", "normal", "html"))
    for r in records:
        _, istatus = build_identity(r, source_id=5)
        assert istatus == IdentityStatus.AMBIGUOUS


def test_hibret_normal_ssl_note_in_mapping_notes():
    records, _ = hibret_parse(_load("hibret", "normal", "html"))
    for r in records:
        assert any("ssl_verify_false" in n for n in r.mapping_notes)


def test_hibret_normal_all_pass_validation():
    records, _ = hibret_parse(_load("hibret", "normal", "html"))
    for r in records:
        status, _ = validate(r)
        assert status != ValidationStatus.REJECTED


def test_hibret_normal_both_categories_emitted():
    records, _ = hibret_parse(_load("hibret", "normal", "html"))
    cats = {r.category for r in records}
    assert "cash" in cats
    assert "transactional" in cats


def test_hibret_empty_returns_empty_records():
    records, errors = hibret_parse(_load("hibret", "empty", "html"))
    assert records == []
    assert errors == []


def test_hibret_malformed_returns_errors():
    records, errors = hibret_parse(_load("hibret", "malformed", "html"))
    assert records == []
    assert len(errors) > 0


def test_hibret_schema_fingerprint_deterministic():
    raw = _load("hibret", "normal", "html")
    assert hibret_fp(raw) == hibret_fp(raw)


def test_hibret_schema_fingerprint_changes_on_table_change():
    raw = _load("hibret", "normal", "html")
    raw_malformed = _load("hibret", "malformed", "html")
    assert hibret_fp(raw) != hibret_fp(raw_malformed)
