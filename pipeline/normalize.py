from decimal import Decimal, InvalidOperation
from typing import Optional

_NOT_OFFERED_STRINGS = frozenset({
    "0", "0.0", "0.00", "0.000", "0.0000",
    "no trade", "no_trade", "notrade",
    "-", "--", "...", "n/a", "na",
})

def normalize_rate(raw: object) -> Optional[Decimal]:
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

_PAREN_CODE_RE = __import__('re').compile(r'\(\s*([A-Z]{3})\s*\)', __import__('re').IGNORECASE)

def normalize_currency_code(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    cleaned = raw.strip().upper()
    if not cleaned:
        return None
    if len(cleaned) == 3 and cleaned.isalpha():
        return cleaned
    m = _PAREN_CODE_RE.search(cleaned)
    if m:
        return m.group(1).upper()
    return None
