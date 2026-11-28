"""
Currency normalization - ONE alias table for all adapters.

Built from actual currency strings found in 32 adapters during audit.
"""


# Consolidated currency alias table
# Maps: uppercase normalized text → ISO 4217 code
_ALIASES = {
    # USD
    "USD": "USD",
    "US DOLLAR": "USD",
    "US$": "USD",
    "$": "USD",
    "UNITED STATES DOLLAR": "USD",
    "U.S. DOLLAR": "USD",
    "AMERICAN DOLLAR": "USD",
    
    # EUR
    "EUR": "EUR",
    "EURO": "EUR",
    "€": "EUR",
    "EUROPEAN EURO": "EUR",
    
    # GBP
    "GBP": "GBP",
    "POUND STERLING": "GBP",
    "BRITISH POUND": "GBP",
    "£": "GBP",
    "STERLING": "GBP",
    "UK POUND": "GBP",
    
    # CNY
    "CNY": "CNY",
    "CHINESE YUAN": "CNY",
    "CHINESE (YUAN)": "CNY",
    "YUAN": "CNY",
    "¥": "CNY",
    "CHINA YUAN": "CNY",
    
    # SAR
    "SAR": "SAR",
    "SAUDI RIYAL": "SAR",
    "SAUDI ARABIAN RIYAL": "SAR",
    "RIYAL": "SAR",
    
    # AED
    "AED": "AED",
    "UAE DIRHAM": "AED",
    "DIRHAM": "AED",
    "EMIRATI DIRHAM": "AED",
    
    # CAD
    "CAD": "CAD",
    "CANADIAN DOLLAR": "CAD",
    "CAN DOLLAR": "CAD",
    "CA$": "CAD",
    
    # JPY
    "JPY": "JPY",
    "JAPANESE YEN": "JPY",
    "YEN": "JPY",
    "JP¥": "JPY",
    
    # KRW
    "KRW": "KRW",
    "SOUTH KOREAN WON": "KRW",
    "KOREAN WON": "KRW",
    "WON": "KRW",
    
    # CHF
    "CHF": "CHF",
    "SWISS FRANC": "CHF",
    "FRANC": "CHF",
    
    # SEK
    "SEK": "SEK",
    "SWEDISH KRONA": "SEK",
    "SWEDISH KRONOR": "SEK",
    
    # NOK
    "NOK": "NOK",
    "NORWEGIAN KRONE": "NOK",
    "NORWEGIAN KRONER": "NOK",
    
    # DKK
    "DKK": "DKK",
    "DANISH KRONE": "DKK",
    "DANISH KRONER": "DKK",
    
    # INR
    "INR": "INR",
    "INDIAN RUPEE": "INR",
    "RUPEE": "INR",
    
    # AUD
    "AUD": "AUD",
    "AUSTRALIAN DOLLAR": "AUD",
    "AUSSIE DOLLAR": "AUD",
    "A$": "AUD",
    
    # NZD
    "NZD": "NZD",
    "NEW ZEALAND DOLLAR": "NZD",
    "NZ$": "NZD",
    
    # ZAR
    "ZAR": "ZAR",
    "SOUTH AFRICAN RAND": "ZAR",
    "RAND": "ZAR",
    
    # KWD
    "KWD": "KWD",
    "KUWAITI DINAR": "KWD",
    "DINAR": "KWD",
    
    # QAR
    "QAR": "QAR",
    "QATARI RIYAL": "QAR",
    "QATARI RIAL": "QAR",
    
    # BHD
    "BHD": "BHD",
    "BAHRAINI DINAR": "BHD",
    
    # OMR
    "OMR": "OMR",
    "OMANI RIAL": "OMR",
    
    # TRY
    "TRY": "TRY",
    "TURKISH LIRA": "TRY",
    "LIRA": "TRY",
    
    # ETB (for reference, should not appear as quote currency)
    "ETB": "ETB",
    "ETHIOPIAN BIRR": "ETB",
    "BIRR": "ETB",
}


def normalize_currency(text: str) -> str | None:
    """
    Normalize currency text to ISO 4217 code.
    
    Args:
        text: Currency name or code from bank website
    
    Returns:
        str: ISO 4217 code (e.g., "USD", "EUR")
        None: If unrecognized and not 3-letter code
    
    Rules:
    - Uppercase, strip whitespace, collapse multiple spaces
    - Handle "CODE (Full Name)" format (e.g., "USD (US Dollar)" → "USD")
    - Check alias table first
    - If not in aliases and looks like ISO code (3 letters), accept as-is
    - Otherwise return None (unknown currency)
    
    Examples:
        normalize_currency("US Dollar") → "USD"
        normalize_currency("usd") → "USD"
        normalize_currency("USD (US Dollar)") → "USD"
        normalize_currency("XYZ") → "XYZ" (3 letters, assumed valid)
        normalize_currency("JUNK123") → None
        normalize_currency("") → None
    """
    if not text:
        return None
    
    # Normalize: uppercase, strip, collapse whitespace
    key = " ".join(text.upper().split())

    # Handle "CODE (Full Name)" format — e.g. "USD (US Dollar)"
    if "(" in key:
        prefix = key.split("(")[0].strip()
        if len(prefix) == 3 and prefix.isalpha():
            return prefix
    
    # Check alias table
    if key in _ALIASES:
        return _ALIASES[key]
    
    # Fallback: Accept 3-letter alphabetic strings as ISO codes
    if len(key) == 3 and key.isalpha():
        return key
    
    # Unknown
    return None
