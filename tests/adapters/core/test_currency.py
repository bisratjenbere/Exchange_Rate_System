"""Tests for adapters.core.currency"""

import pytest
from adapters.core.currency import normalize_currency


class TestNormalizeCurrency:
    """Test normalize_currency() function."""
    
    def test_usd_variants(self):
        """Normalize USD variations."""
        assert normalize_currency("USD") == "USD"
        assert normalize_currency("usd") == "USD"
        assert normalize_currency("US Dollar") == "USD"
        assert normalize_currency("US$") == "USD"
        assert normalize_currency("$") == "USD"
        assert normalize_currency("United States Dollar") == "USD"
    
    def test_eur_variants(self):
        """Normalize EUR variations."""
        assert normalize_currency("EUR") == "EUR"
        assert normalize_currency("Euro") == "EUR"
        assert normalize_currency("€") == "EUR"
    
    def test_gbp_variants(self):
        """Normalize GBP variations."""
        assert normalize_currency("GBP") == "GBP"
        assert normalize_currency("Pound Sterling") == "GBP"
        assert normalize_currency("British Pound") == "GBP"
        assert normalize_currency("£") == "GBP"
    
    def test_case_insensitive(self):
        """Normalization is case-insensitive."""
        assert normalize_currency("us dollar") == "USD"
        assert normalize_currency("US DOLLAR") == "USD"
        assert normalize_currency("Us DoLLaR") == "USD"
    
    def test_whitespace_normalized(self):
        """Whitespace is collapsed."""
        assert normalize_currency("  US  Dollar  ") == "USD"
        assert normalize_currency("US\t\nDollar") == "USD"
    
    def test_iso_code_passthrough(self):
        """3-letter codes accepted as-is."""
        assert normalize_currency("XXX") == "XXX"
        assert normalize_currency("ABC") == "ABC"
    
    def test_unknown_returns_none(self):
        """Unknown currency returns None."""
        assert normalize_currency("JUNK123") is None
        assert normalize_currency("Not A Currency") is None
        assert normalize_currency("12345") is None
    
    def test_empty_returns_none(self):
        """Empty string returns None."""
        assert normalize_currency("") is None
        assert normalize_currency("   ") is None
    
    def test_common_currencies(self):
        """Test common currencies from Ethiopian banks."""
        assert normalize_currency("Chinese Yuan") == "CNY"
        assert normalize_currency("Saudi Riyal") == "SAR"
        assert normalize_currency("UAE Dirham") == "AED"
        assert normalize_currency("Canadian Dollar") == "CAD"
        assert normalize_currency("Japanese Yen") == "JPY"
        assert normalize_currency("Swiss Franc") == "CHF"
