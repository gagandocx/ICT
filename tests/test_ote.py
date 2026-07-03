"""
Tests for ict_bot/ote.py

Tests OTE (Optimal Trade Entry) zone calculation and price-in-zone checking.
"""

import pytest

from ict_bot.ote import calculate_ote_zone, is_price_in_ote


class TestCalculateOTEZone:
    """Tests for calculate_ote_zone()."""

    def test_bullish_ote_zone_calculation(self):
        """
        Bullish OTE zone:
        ote_low = swing_low + (1-0.79) * range = low + 0.21 * range
        ote_high = swing_low + (1-0.62) * range = low + 0.38 * range
        """
        swing_high = 200.0
        swing_low = 100.0
        price_range = 100.0

        ote_low, ote_high = calculate_ote_zone(swing_high, swing_low, "bullish")
        # ote_low = 100 + 0.21 * 100 = 121
        # ote_high = 100 + 0.38 * 100 = 138
        assert abs(ote_low - 121.0) < 0.01
        assert abs(ote_high - 138.0) < 0.01

    def test_bearish_ote_zone_calculation(self):
        """
        Bearish OTE zone:
        ote_low = swing_low + 0.62 * range
        ote_high = swing_low + 0.79 * range
        """
        swing_high = 200.0
        swing_low = 100.0
        price_range = 100.0

        ote_low, ote_high = calculate_ote_zone(swing_high, swing_low, "bearish")
        # ote_low = 100 + 0.62 * 100 = 162
        # ote_high = 100 + 0.79 * 100 = 179
        assert abs(ote_low - 162.0) < 0.01
        assert abs(ote_high - 179.0) < 0.01

    def test_ote_low_less_than_ote_high(self):
        """OTE low should always be less than OTE high."""
        for direction in ["bullish", "bearish"]:
            ote_low, ote_high = calculate_ote_zone(150.0, 100.0, direction)
            assert ote_low < ote_high

    def test_invalid_direction_raises_error(self):
        """Invalid direction should raise ValueError."""
        with pytest.raises(ValueError):
            calculate_ote_zone(200.0, 100.0, "invalid")


class TestIsPriceInOTE:
    """Tests for is_price_in_ote()."""

    def test_price_inside_ote_zone(self):
        """Price within the OTE bounds should return True."""
        ote_zone = (121.0, 138.0)
        assert is_price_in_ote(130.0, ote_zone) is True

    def test_price_at_ote_boundary_low(self):
        """Price exactly at OTE low should return True (inclusive)."""
        ote_zone = (121.0, 138.0)
        assert is_price_in_ote(121.0, ote_zone) is True

    def test_price_at_ote_boundary_high(self):
        """Price exactly at OTE high should return True (inclusive)."""
        ote_zone = (121.0, 138.0)
        assert is_price_in_ote(138.0, ote_zone) is True

    def test_price_below_ote_zone(self):
        """Price below OTE low should return False."""
        ote_zone = (121.0, 138.0)
        assert is_price_in_ote(120.0, ote_zone) is False

    def test_price_above_ote_zone(self):
        """Price above OTE high should return False."""
        ote_zone = (121.0, 138.0)
        assert is_price_in_ote(139.0, ote_zone) is False
