"""
pipeline/normalize.py — pure normalization of raw adapter values.
No network calls, no clock access.
Acceptance test 17: source currency/rate text retained.
"""
from decimal import Decimal, InvalidOperation
from typing import Optional


# All sentinel strings that mean "not offered" (ADR-006 §4.1)
_NOT_OFFERED_STRINGS = frozenset({
    "0", "0.0", "0.00", "0.000", "0.0000",
    "no trade", "no_trade", "notrade",
    "-", "--", "...", "n/a", "na",
})


def normalize_rate(raw: object) -> Optional[Decimal]:
    """
    Convert a raw rate value to Decimal or None.
    - None / empty string → None
    - Sentinel strings (zero, "No Trade", "-", …) → None
    - Numeric zero → None
    - Positive number → Decimal
    - Negative or unparseable → raises ValueError (caller must reject the record)
    Acceptance test 15: no silent coercion.
    Acceptance test 16: missing side is None, never zero.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text.lower() in _NOT_OFFERED_STRINGS:
        return None
    try:
        d = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"Cannot parse rate value: {raw!r}")
    if d == Decimal(0):
        return None
    if d < Decimal(0):
        raise ValueError(f"Negative rate value: {raw!r}")
    return d


def normalize_currency_code(raw: Optional[str]) -> Optional[str]:
    """Strip and upper-case a currency code; return None if empty."""
    if not raw:
        return None
    cleaned = raw.strip().upper()
    return cleaned if cleaned else None
