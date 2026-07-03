"""
Tests for ict_bot/premium_discount.py

Tests equilibrium calculation and premium/discount zone classification.
"""

import pytest

from ict_bot.premium_discount import calculate_equilibrium, is_premium, is_discount


class TestCalculateEquilibrium:
    """Tests for calculate_equilibrium()."""

    def test_equilibrium_is_midpoint(self):
        """Equilibrium should be (swing_high + swing_low) / 2."""
        assert calculate_equilibrium(200.0, 100.0) == 150.0

    def test_equilibrium_with_close_values(self):
        """Works with values that are close together."""
        assert calculate_equilibrium(100.5, 100.0) == 100.25

    def test_equilibrium_with_large_range(self):
        """Works correctly with large price ranges."""
        result = calculate_equilibrium(15500.0, 14500.0)
        assert result == 15000.0


class TestIsPremium:
    """Tests for is_premium()."""

    def test_price_above_equilibrium_is_premium(self):
        """Price above equilibrium should be in premium zone."""
        equilibrium = 150.0
        assert is_premium(160.0, equilibrium) is True

    def test_price_below_equilibrium_is_not_premium(self):
        """Price below equilibrium should NOT be in premium zone."""
        equilibrium = 150.0
        assert is_premium(140.0, equilibrium) is False

    def test_price_at_equilibrium_is_not_premium(self):
        """Price exactly at equilibrium is NOT premium (strict >)."""
        equilibrium = 150.0
        assert is_premium(150.0, equilibrium) is False


class TestIsDiscount:
    """Tests for is_discount()."""

    def test_price_below_equilibrium_is_discount(self):
        """Price below equilibrium should be in discount zone."""
        equilibrium = 150.0
        assert is_discount(140.0, equilibrium) is True

    def test_price_above_equilibrium_is_not_discount(self):
        """Price above equilibrium should NOT be in discount zone."""
        equilibrium = 150.0
        assert is_discount(160.0, equilibrium) is False

    def test_price_at_equilibrium_is_not_discount(self):
        """Price exactly at equilibrium is NOT discount (strict <)."""
        equilibrium = 150.0
        assert is_discount(150.0, equilibrium) is False

    def test_premium_and_discount_are_mutually_exclusive(self):
        """A price cannot be both premium and discount."""
        equilibrium = 150.0
        for price in [140.0, 145.0, 155.0, 160.0]:
            premium = is_premium(price, equilibrium)
            discount = is_discount(price, equilibrium)
            assert not (premium and discount)
