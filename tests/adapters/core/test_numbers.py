"""Tests for adapters.core.numbers"""

import pytest
from decimal import Decimal
from adapters.core.numbers import parse_decimal, scale_per_100_units


class TestParseDecimal:
    """Test parse_decimal() function."""
    
    def test_simple_number(self):
        """Parse simple decimal number."""
        assert parse_decimal("3.5") == Decimal("3.5")
        assert parse_decimal("100") == Decimal("100")
        assert parse_decimal("0.5") == Decimal("0.5")
    
    def test_with_commas(self):
        """Remove thousand separators."""
        assert parse_decimal("1,000.50") == Decimal("1000.50")
        assert parse_decimal("10,000") == Decimal("10000")
        assert parse_decimal("1,000,000.00") == Decimal("1000000.00")
    
    def test_with_spaces(self):
        """Remove whitespace."""
        assert parse_decimal("  3.5  ") == Decimal("3.5")
        assert parse_decimal("1 000.50") == Decimal("1000.50")
        assert parse_decimal("1\u00a0000.50") == Decimal("1000.50")  # Non-breaking space
    
    def test_blank_placeholders(self):
        """Blank placeholders return None."""
        assert parse_decimal("") is None
        assert parse_decimal("-") is None
        assert parse_decimal("—") is None
        assert parse_decimal("N/A") is None
        assert parse_decimal("n/a") is None
        assert parse_decimal("null") is None
        assert parse_decimal("None") is None
        assert parse_decimal("0.0") is None
        assert parse_decimal("0.00") is None
    
    def test_none_input(self):
        """None input returns None."""
        assert parse_decimal(None) is None
    
    def test_junk_raises_value_error(self):
        """Non-numeric junk raises ValueError."""
        with pytest.raises(ValueError, match="not a number"):
            parse_decimal("xyz")
        
        with pytest.raises(ValueError, match="not a number"):
            parse_decimal("not a number")
        
        with pytest.raises(ValueError, match="not a number"):
            parse_decimal("3.5.7")
    
    def test_zero_raises_value_error(self):
        """Zero is non-positive, raises ValueError."""
        with pytest.raises(ValueError, match="not positive"):
            parse_decimal("0")
    
    def test_negative_raises_value_error(self):
        """Negative values raise ValueError."""
        with pytest.raises(ValueError, match="not positive"):
            parse_decimal("-3.5")
        
        with pytest.raises(ValueError, match="not positive"):
            parse_decimal("-100")
    
    def test_infinity_raises_value_error(self):
        """Infinity raises ValueError."""
        with pytest.raises(ValueError, match="not finite"):
            parse_decimal("inf")
        
        with pytest.raises(ValueError, match="not finite"):
            parse_decimal("-inf")


class TestScalePer100Units:
    """Test scale_per_100_units() function."""
    
    def test_jpy_scaled(self):
        """JPY rates are scaled (inverted and * 100)."""
        # If bank publishes "1 USD = 110 JPY"
        # We want "100 JPY = 0.909... USD"
        result = scale_per_100_units(Decimal("110"), "JPY")
        assert result == Decimal("100") / Decimal("110")
    
    def test_krw_scaled(self):
        """KRW rates are scaled."""
        result = scale_per_100_units(Decimal("1200"), "KRW")
        assert result == Decimal("100") / Decimal("1200")
    
    def test_usd_not_scaled(self):
        """USD rates pass through unchanged."""
        assert scale_per_100_units(Decimal("3.5"), "USD") == Decimal("3.5")
    
    def test_eur_not_scaled(self):
        """EUR rates pass through unchanged."""
        assert scale_per_100_units(Decimal("4.2"), "EUR") == Decimal("4.2")
    
    def test_none_rate(self):
        """None rate returns None."""
        assert scale_per_100_units(None, "JPY") is None
        assert scale_per_100_units(None, "USD") is None
