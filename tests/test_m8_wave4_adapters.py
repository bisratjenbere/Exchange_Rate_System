"""
Wave 4 adapter tests — DBE, Siinqee, Global (Type F), Ahadu, Enat (Type G), Omo (Type D).
Abay (403), Gadaa (JS), Tsedey (JS-empty) are deferred — no adapters built.
All tests use fixtures — no network calls.
"""
import pytest
from decimal import Decimal
from datetime import date
from pathlib import Path

from domain.enums import IdentityStatus, ValidationStatus
from pipeline.identity import build_identity
from pipeline.validate import validate

FIXTURE_DIR = Path("fixtures")


def _load(bank: str, name: str) -> str:
    bank = "global_" if bank == "global" else bank
    return (FIXTURE_DIR / bank / f"{name}.html").read_text()


# ═══════════════════════════════════════════════════════════════════════════════
# DBE (Type F single table, UNKNOWN)
# ═══════════════════════════════════════════════════════════════════════════════

from adapters.dbe.adapter import parse as dbe_parse, schema_fingerprint as dbe_fp, ADAPTER_KEY as DBE_KEY


def test_dbe_adapter_key():
    assert DBE_KEY == "dbe_html"


def test_dbe_normal_usd_values():
    records, _ = dbe_parse(_load("dbe", "normal"))
    usd = [r for r in records if r.source_currency_code == "USD"]
    assert len(usd) == 1
    assert usd[0].buying_rate == Decimal("161.6278")
    assert usd[0].selling_rate == Decimal("164.8604")


def test_dbe_normal_category_unknown():
    records, _ = dbe_parse(_load("dbe", "normal"))
    for r in records:
        assert r.category == "UNKNOWN"


def test_dbe_normal_date_source_published():
    records, _ = dbe_parse(_load("dbe", "normal"))
    for r in records:
        assert r.effective_date is not None
        assert r.effective_date_basis == "source_published"


def test_dbe_normal_identity_confirmed():
    records, _ = dbe_parse(_load("dbe", "normal"))
    for r in records:
        _, istatus = build_identity(r, source_id=14)
        assert istatus == IdentityStatus.CONFIRMED


def test_dbe_normal_all_pass_validation():
    records, _ = dbe_parse(_load("dbe", "normal"))
    for r in records:
        status, _ = validate(r)
        assert status != ValidationStatus.REJECTED


def test_dbe_empty_returns_empty():
    records, errors = dbe_parse(_load("dbe", "empty"))
    assert records == []


def test_dbe_malformed_returns_errors():
    records, errors = dbe_parse(_load("dbe", "malformed"))
    assert records == []
    assert len(errors) > 0


def test_dbe_schema_fingerprint_deterministic():
    raw = _load("dbe", "normal")
    assert dbe_fp(raw) == dbe_fp(raw)



from adapters.siinqee.adapter import parse as siinqee_parse, schema_fingerprint as siinqee_fp, ADAPTER_KEY as SIINQEE_KEY


def test_siinqee_adapter_key():
    assert SIINQEE_KEY == "siinqee_html"


def test_siinqee_normal_usd_values():
    records, _ = siinqee_parse(_load("siinqee", "normal"))
    usd = [r for r in records if r.source_currency_code == "USD"]
    assert len(usd) == 1
    assert usd[0].buying_rate == Decimal("160.8993")
    assert usd[0].selling_rate == Decimal("164.1173")


def test_siinqee_normal_category_unknown():
    records, _ = siinqee_parse(_load("siinqee", "normal"))
    for r in records:
        assert r.category == "UNKNOWN"


def test_siinqee_normal_no_date_ambiguous():
    records, _ = siinqee_parse(_load("siinqee", "normal"))
    for r in records:
        _, istatus = build_identity(r, source_id=15)
        assert istatus == IdentityStatus.AMBIGUOUS


def test_siinqee_normal_all_pass_validation():
    records, _ = siinqee_parse(_load("siinqee", "normal"))
    for r in records:
        status, _ = validate(r)
        assert status != ValidationStatus.REJECTED


def test_siinqee_empty_returns_empty():
    records, errors = siinqee_parse(_load("siinqee", "empty"))
    assert records == []


def test_siinqee_malformed_returns_errors():
    records, errors = siinqee_parse(_load("siinqee", "malformed"))
    assert records == []
    assert len(errors) > 0


def test_siinqee_schema_fingerprint_deterministic():
    raw = _load("siinqee", "normal")
    assert siinqee_fp(raw) == siinqee_fp(raw)


# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL (Type F two tables, UNKNOWN, review signal)
# ═══════════════════════════════════════════════════════════════════════════════

from adapters.global_.adapter import parse as global_parse, schema_fingerprint as global_fp, ADAPTER_KEY as GLOBAL_KEY


def test_global_adapter_key():
    assert GLOBAL_KEY == "global_html"


def test_global_normal_usd_table0():
    records, _ = global_parse(_load("global", "normal"))
    usd_t0 = [r for r in records if r.source_currency_code == "USD"
               and "table_0" in " ".join(r.mapping_notes)]
    assert len(usd_t0) == 1
    assert usd_t0[0].buying_rate == Decimal("161.5581")


def test_global_normal_review_signal_on_table1_usd():
    """USD table 1: buying=164.9606 > selling=164.7893 → review signal in notes."""
    records, _ = global_parse(_load("global", "normal"))
    usd_t1 = [r for r in records if r.source_currency_code == "USD"
               and "table_1" in " ".join(r.mapping_notes)]
    assert len(usd_t1) == 1
    assert any("review_signal" in n for n in usd_t1[0].mapping_notes)


def test_global_normal_no_trade_skipped():
    records, _ = global_parse(_load("global", "normal"))
    eur_t1 = [r for r in records if r.source_currency_code == "EUR"
               and "table_1" in " ".join(r.mapping_notes)]
    assert len(eur_t1) == 0


def test_global_normal_no_date_ambiguous():
    records, _ = global_parse(_load("global", "normal"))
    for r in records:
        _, istatus = build_identity(r, source_id=16)
        assert istatus == IdentityStatus.AMBIGUOUS


def test_global_malformed_returns_errors():
    records, errors = global_parse(_load("global", "malformed"))
    assert records == []
    assert len(errors) > 0


def test_global_schema_fingerprint_deterministic():
    raw = _load("global", "normal")
    assert global_fp(raw) == global_fp(raw)


# ═══════════════════════════════════════════════════════════════════════════════
# AHADU (Type G text, DD/MM/YYYY date)
# ═══════════════════════════════════════════════════════════════════════════════

from adapters.ahadu.adapter import parse as ahadu_parse, schema_fingerprint as ahadu_fp, ADAPTER_KEY as AHADU_KEY


def test_ahadu_adapter_key():
    assert AHADU_KEY == "ahadu_html"


def test_ahadu_normal_aed_values():
    """AED has actual values; USD/EUR/GBP are No Trade."""
    records, _ = ahadu_parse(_load("ahadu", "normal"))
    aed = [r for r in records if r.source_currency_code == "AED"]
    assert len(aed) == 1
    assert aed[0].buying_rate == Decimal("44.0325")
    assert aed[0].selling_rate == Decimal("44.9131")


def test_ahadu_normal_usd_selling_only():
    """USD: buying=No Trade, selling=166.4579."""
    records, _ = ahadu_parse(_load("ahadu", "normal"))
    usd = [r for r in records if r.source_currency_code == "USD"]
    assert len(usd) == 1
    assert usd[0].buying_rate is None
    assert usd[0].selling_rate == Decimal("166.4579")


def test_ahadu_normal_eur_gbp_both_no_trade_skipped():
    records, _ = ahadu_parse(_load("ahadu", "normal"))
    eur = [r for r in records if r.source_currency_code == "EUR"]
    gbp = [r for r in records if r.source_currency_code == "GBP"]
    assert len(eur) == 0
    assert len(gbp) == 0


def test_ahadu_normal_date_extracted():
    records, _ = ahadu_parse(_load("ahadu", "normal"))
    for r in records:
        assert r.effective_date == date(2026, 10, 12)
        assert r.effective_date_basis == "source_published"


def test_ahadu_normal_identity_confirmed():
    records, _ = ahadu_parse(_load("ahadu", "normal"))
    for r in records:
        _, istatus = build_identity(r, source_id=17)
        assert istatus == IdentityStatus.CONFIRMED


def test_ahadu_normal_category_unknown():
    records, _ = ahadu_parse(_load("ahadu", "normal"))
    for r in records:
        assert r.category == "UNKNOWN"


def test_ahadu_normal_all_pass_validation():
    records, _ = ahadu_parse(_load("ahadu", "normal"))
    for r in records:
        status, _ = validate(r)
        assert status != ValidationStatus.REJECTED


def test_ahadu_empty_returns_empty():
    records, errors = ahadu_parse(_load("ahadu", "empty"))
    assert records == []


def test_ahadu_malformed_returns_empty():
    records, errors = ahadu_parse(_load("ahadu", "malformed"))
    assert records == []


def test_ahadu_schema_fingerprint_deterministic():
    raw = _load("ahadu", "normal")
    assert ahadu_fp(raw) == ahadu_fp(raw)


# ═══════════════════════════════════════════════════════════════════════════════
# ENAT (Type G text, date in text)
# ═══════════════════════════════════════════════════════════════════════════════

from adapters.enat.adapter import parse as enat_parse, schema_fingerprint as enat_fp, ADAPTER_KEY as ENAT_KEY


def test_enat_adapter_key():
    assert ENAT_KEY == "enat_html"


def test_enat_normal_usd_values():
    records, _ = enat_parse(_load("enat", "normal"))
    usd = [r for r in records if r.source_currency_code == "USD"]
    assert len(usd) == 1
    assert usd[0].buying_rate == Decimal("161.3750")
    assert usd[0].selling_rate == Decimal("164.6025")


def test_enat_normal_date_extracted():
    records, _ = enat_parse(_load("enat", "normal"))
    for r in records:
        assert r.effective_date == date(2026, 10, 12)
        assert r.effective_date_basis == "source_published"


def test_enat_normal_identity_confirmed():
    records, _ = enat_parse(_load("enat", "normal"))
    for r in records:
        _, istatus = build_identity(r, source_id=18)
        assert istatus == IdentityStatus.CONFIRMED


def test_enat_normal_category_unknown():
    records, _ = enat_parse(_load("enat", "normal"))
    for r in records:
        assert r.category == "UNKNOWN"


def test_enat_normal_all_pass_validation():
    records, _ = enat_parse(_load("enat", "normal"))
    for r in records:
        status, _ = validate(r)
        assert status != ValidationStatus.REJECTED


def test_enat_normal_no_duplicates():
    records, _ = enat_parse(_load("enat", "normal"))
    codes = [r.source_currency_code for r in records]
    assert len(codes) == len(set(codes))


def test_enat_empty_returns_empty():
    records, errors = enat_parse(_load("enat", "empty"))
    assert records == []


def test_enat_malformed_returns_empty():
    records, errors = enat_parse(_load("enat", "malformed"))
    assert records == []


def test_enat_schema_fingerprint_deterministic():
    raw = _load("enat", "normal")
    assert enat_fp(raw) == enat_fp(raw)


# ═══════════════════════════════════════════════════════════════════════════════
# OMO (Type D multi-table, DD/MM/YYYY dates)
# ═══════════════════════════════════════════════════════════════════════════════

from adapters.omo.adapter import parse as omo_parse, schema_fingerprint as omo_fp, ADAPTER_KEY as OMO_KEY


def test_omo_adapter_key():
    assert OMO_KEY == "omo_html"


def test_omo_normal_usd_cash():
    records, _ = omo_parse(_load("omo", "normal"))
    usd_cash = [r for r in records if r.source_currency_code == "USD" and r.category == "cash"]
    assert len(usd_cash) == 1
    assert usd_cash[0].buying_rate == Decimal("160.3720")
    assert usd_cash[0].effective_date == date(2026, 10, 12)


def test_omo_normal_usd_txn():
    records, _ = omo_parse(_load("omo", "normal"))
    usd_txn = [r for r in records if r.source_currency_code == "USD" and r.category == "transactional"]
    assert len(usd_txn) == 1
    assert usd_txn[0].buying_rate == Decimal("159.7662")


def test_omo_normal_weighted_no_trade_skipped():
    records, _ = omo_parse(_load("omo", "normal"))
    weighted = [r for r in records if r.category == "weighted_average"]
    assert len(weighted) == 0


def test_omo_normal_per_table_dates():
    """Cash/txn = 12/10/2026, weighted = 10/10/2026 (different dates per table)."""
    records, _ = omo_parse(_load("omo", "normal"))
    cash = [r for r in records if r.category == "cash"]
    for r in cash:
        assert r.effective_date == date(2026, 10, 12)


def test_omo_normal_currency_code_extracted():
    """'USD – US Dollar' → source_currency_code='USD'."""
    records, _ = omo_parse(_load("omo", "normal"))
    codes = {r.source_currency_code for r in records}
    assert "USD" in codes
    assert "EUR" in codes


def test_omo_normal_identity_confirmed():
    records, _ = omo_parse(_load("omo", "normal"))
    for r in records:
        _, istatus = build_identity(r, source_id=19)
        assert istatus == IdentityStatus.CONFIRMED


def test_omo_normal_all_pass_validation():
    records, _ = omo_parse(_load("omo", "normal"))
    for r in records:
        status, _ = validate(r)
        assert status != ValidationStatus.REJECTED


def test_omo_malformed_returns_errors():
    records, errors = omo_parse(_load("omo", "malformed"))
    assert records == []
    assert len(errors) > 0


def test_omo_schema_fingerprint_deterministic():
    raw = _load("omo", "normal")
    assert omo_fp(raw) == omo_fp(raw)
