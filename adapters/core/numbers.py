"""
Number parsing - ONE implementation for all adapters.

Design: Decimal only (ADR-004), no float for monetary values.
"""

from decimal import Decimal, InvalidOperation


# Blank value placeholders (normalize to None)
_BLANK = {"", "-", "—", "\u2014", "n/a", "na", "null", "none", "nil", "0.0", "0.00"}


def parse_decimal(text: str | None) -> Decimal | None:
    """
    Parse text to Decimal, or None for blank/placeholder cells.
    
    Args:
        text: String from HTML cell or JSON field
    
    Returns:
        Decimal: Parsed positive rate
        None: For blank/placeholder cells (not an error)
    
    Raises:
        ValueError: For non-numeric junk (e.g., "xyz", "not a number")
        ValueError: For non-positive values (zero, negative)
    
    Examples:
        parse_decimal("3.5") → Decimal("3.5")
        parse_decimal("3,500.25") → Decimal("3500.25")
        parse_decimal("") → None
        parse_decimal("-") → None
        parse_decimal("N/A") → None
        parse_decimal("abc") → raises ValueError
        parse_decimal("-3.5") → raises ValueError (non-positive)
        parse_decimal("0") → raises ValueError (non-positive)
    
    Notes:
    - Removes commas, spaces, non-breaking spaces
    - Treats common placeholders as None (not error)
    - Rejects infinity, NaN, zero, negative
    """
    if text is None:
        return None
    
    # Normalize whitespace and remove formatting
    cleaned = text.replace("\u00a0", " ")  # Non-breaking space → regular space
    cleaned = cleaned.strip()
    cleaned = cleaned.replace(",", "")     # Remove thousand separators
    cleaned = cleaned.replace(" ", "")     # Remove all spaces
    
    # Check for blank placeholders
    if cleaned.lower() in _BLANK:
        return None
    
    # Attempt decimal conversion
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"not a number: {text!r}") from None
    
    # Validate: must be finite and positive
    if not value.is_finite():
        raise ValueError(f"not finite: {text!r}")
    
    if value <= 0:
        raise ValueError(f"not positive: {text!r}")
    
    return value


def scale_per_100_units(rate: Decimal | None, currency_code: str) -> Decimal | None:
    """
    Scale rate for currencies quoted per 100 units (JPY, KRW).
    
    Some banks publish "1 USD = 110.5 JPY", which should be "100 JPY = 0.906 USD".
    This function reverses and scales.
    
    Args:
        rate: Rate as published
        currency_code: Currency (e.g., "JPY", "USD")
    
    Returns:
        Scaled rate if currency in PER_100_UNITS, else unchanged
    
    Examples:
        scale_per_100_units(Decimal("110.5"), "JPY") → Decimal("0.9049...")
        scale_per_100_units(Decimal("3.5"), "USD") → Decimal("3.5")
    """
    PER_100_UNITS = {"JPY", "KRW"}  # Japanese Yen, Korean Won
    
    if rate is None:
        return None
    
    if currency_code not in PER_100_UNITS:
        return rate
    
    # Invert and scale: (1 / rate) * 100
    return (Decimal("100") / rate) if rate != 0 else None
