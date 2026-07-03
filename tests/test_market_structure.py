"""
Tests for ict_bot/market_structure.py

Tests swing point detection, BOS (Break of Structure), and MSS
(Market Structure Shift) detection with known OHLC data.
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta

from ict_bot.market_structure import detect_swing_points, detect_bos, detect_mss


class TestDetectSwingPoints:
    """Tests for detect_swing_points()."""

    def test_identifies_swing_high_with_lookback_3(self):
        """A candle whose high exceeds surrounding 3 candles on each side is a swing high."""
        # Build a sequence: lows then a peak then lows
        n = 11
        times = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n)]
        # The peak is at index 5 with lookback=3
        highs = [100, 101, 102, 103, 104, 110, 104, 103, 102, 101, 100]
        lows = [99, 100, 101, 102, 103, 108, 103, 102, 101, 100, 99]
        df = pd.DataFrame({
            "time": times,
            "open": highs,
            "high": highs,
            "low": lows,
            "close": lows,
        })
        swings = detect_swing_points(df, lookback=3)
        swing_highs = [s for s in swings if s["type"] == "swing_high"]
        assert len(swing_highs) >= 1
        assert swing_highs[0]["index"] == 5
        assert swing_highs[0]["price"] == 110

    def test_identifies_swing_low_with_lookback_3(self):
        """A candle whose low is below surrounding 3 candles on each side is a swing low."""
        n = 11
        times = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n)]
        # Valley at index 5 with lookback=3
        highs = [110, 109, 108, 107, 106, 102, 106, 107, 108, 109, 110]
        lows = [108, 107, 106, 105, 104, 100, 104, 105, 106, 107, 108]
        df = pd.DataFrame({
            "time": times,
            "open": highs,
            "high": highs,
            "low": lows,
            "close": lows,
        })
        swings = detect_swing_points(df, lookback=3)
        swing_lows = [s for s in swings if s["type"] == "swing_low"]
        assert len(swing_lows) >= 1
        assert swing_lows[0]["index"] == 5
        assert swing_lows[0]["price"] == 100

    def test_no_swing_points_in_flat_market(self):
        """Flat price action should yield no swing points."""
        n = 15
        times = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n)]
        df = pd.DataFrame({
            "time": times,
            "open": [100.0] * n,
            "high": [100.0] * n,
            "low": [100.0] * n,
            "close": [100.0] * n,
        })
        swings = detect_swing_points(df, lookback=5)
        assert swings == []

    def test_multiple_swings_in_trending_data(self, bullish_trend_df):
        """Multiple swing highs and lows should be found in trending data."""
        swings = detect_swing_points(bullish_trend_df, lookback=3)
        swing_highs = [s for s in swings if s["type"] == "swing_high"]
        swing_lows = [s for s in swings if s["type"] == "swing_low"]
        # Should find multiple swing points in a 30-bar trend
        assert len(swing_highs) >= 2
        assert len(swing_lows) >= 2


class TestDetectBOS:
    """Tests for detect_bos() - Break of Structure."""

    def test_bullish_bos_in_uptrend(self):
        """
        Bullish BOS: close above a swing high that is higher than the previous
        swing high (trend continuation).
        """
        # Create data with two swing highs where the second is higher,
        # then price breaks above the second swing high
        n = 25
        times = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n)]
        # First swing high at idx 5 (price=105), second at idx 12 (price=108)
        # Then at idx 18 price closes above 108
        highs = [100, 101, 102, 103, 104, 105, 104, 103, 104, 105, 106, 107, 108,
                 107, 106, 105, 106, 107, 109, 110, 111, 112, 113, 114, 115]
        lows =  [98, 99, 100, 101, 102, 103, 102, 101, 102, 103, 104, 105, 106,
                 105, 104, 103, 104, 105, 107, 108, 109, 110, 111, 112, 113]
        closes = [99, 100, 101, 102, 103, 104, 103, 102, 103, 104, 105, 106, 107,
                  106, 105, 104, 105, 106, 109, 110, 111, 112, 113, 114, 115]
        df = pd.DataFrame({
            "time": times,
            "open": [h - 1 for h in highs],
            "high": highs,
            "low": lows,
            "close": closes,
        })

        swings = detect_swing_points(df, lookback=3)
        bos_events = detect_bos(df, swings)

        bullish_bos = [e for e in bos_events if e["type"] == "bullish_bos"]
        assert len(bullish_bos) >= 1
        # The break should happen after the second swing high
        for bos in bullish_bos:
            assert bos["break_index"] > 5

    def test_bearish_bos_in_downtrend(self):
        """
        Bearish BOS: close below a swing low that is lower than the previous
        swing low (trend continuation).
        """
        n = 25
        times = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n)]
        # First swing low at idx 5 (price=95), second at idx 12 (price=92)
        # Then price breaks below 92
        highs = [102, 101, 100, 99, 98, 97, 98, 99, 98, 97, 96, 95, 94,
                 95, 96, 95, 94, 93, 91, 90, 89, 88, 87, 86, 85]
        lows =  [100, 99, 98, 97, 96, 95, 96, 97, 96, 95, 94, 93, 92,
                 93, 94, 93, 92, 91, 89, 88, 87, 86, 85, 84, 83]
        closes = [101, 100, 99, 98, 97, 96, 97, 98, 97, 96, 95, 94, 93,
                  94, 95, 94, 93, 92, 90, 89, 88, 87, 86, 85, 84]
        df = pd.DataFrame({
            "time": times,
            "open": [h - 1 for h in highs],
            "high": highs,
            "low": lows,
            "close": closes,
        })

        swings = detect_swing_points(df, lookback=3)
        bos_events = detect_bos(df, swings)
        bearish_bos = [e for e in bos_events if e["type"] == "bearish_bos"]
        assert len(bearish_bos) >= 1


class TestDetectMSS:
    """Tests for detect_mss() - Market Structure Shift."""

    def test_bullish_mss_reversal_from_bearish(self):
        """
        Bullish MSS: close above a swing high that is LOWER than the previous
        swing high (reversal from bearish trend).
        """
        # Create lower highs (bearish), then price breaks above one of them
        n = 25
        times = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n)]
        # Swing high at idx 4 = 112, swing high at idx 10 = 109 (lower)
        # Then close above 109 at some later index
        highs = [108, 109, 110, 111, 112, 111, 110, 109, 108, 109,
                 109, 108, 107, 106, 105, 106, 107, 108, 110, 111,
                 112, 113, 114, 115, 116]
        lows =  [106, 107, 108, 109, 110, 109, 108, 107, 106, 107,
                 107, 106, 105, 104, 103, 104, 105, 106, 108, 109,
                 110, 111, 112, 113, 114]
        closes = [107, 108, 109, 110, 111, 110, 109, 108, 107, 108,
                  108, 107, 106, 105, 104, 105, 106, 107, 110, 110,
                  111, 112, 113, 114, 115]
        df = pd.DataFrame({
            "time": times,
            "open": [h - 1 for h in highs],
            "high": highs,
            "low": lows,
            "close": closes,
        })

        swings = detect_swing_points(df, lookback=3)
        mss_events = detect_mss(df, swings)
        bullish_mss = [e for e in mss_events if e["type"] == "bullish_mss"]
        # Should detect at least one bullish MSS
        assert len(bullish_mss) >= 1

    def test_bearish_mss_reversal_from_bullish(self):
        """
        Bearish MSS: close below a swing low that is HIGHER than the previous
        swing low (reversal from bullish trend).
        """
        # Create higher lows (bullish), then price breaks below one of them
        n = 25
        times = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n)]
        # Swing low at idx 4 = 98, swing low at idx 11 = 101 (higher)
        # Then price closes below 101
        highs = [102, 101, 100, 99, 100, 101, 102, 103, 104, 105,
                 104, 103, 102, 103, 104, 103, 102, 101, 100, 99,
                 98, 97, 96, 95, 94]
        lows =  [100, 99, 98, 97, 98, 99, 100, 101, 102, 103,
                 102, 101, 100, 101, 102, 101, 100, 99, 98, 97,
                 96, 95, 94, 93, 92]
        closes = [101, 100, 99, 98, 99, 100, 101, 102, 103, 104,
                  103, 102, 101, 102, 103, 102, 101, 100, 99, 98,
                  97, 96, 95, 94, 93]
        df = pd.DataFrame({
            "time": times,
            "open": [h - 1 for h in highs],
            "high": highs,
            "low": lows,
            "close": closes,
        })

        swings = detect_swing_points(df, lookback=3)
        mss_events = detect_mss(df, swings)
        bearish_mss = [e for e in mss_events if e["type"] == "bearish_mss"]
        assert len(bearish_mss) >= 1

    def test_mss_returns_correct_keys(self, bullish_trend_df):
        """MSS events should have the required dictionary keys."""
        swings = detect_swing_points(bullish_trend_df, lookback=3)
        mss_events = detect_mss(bullish_trend_df, swings)
        for event in mss_events:
            assert "type" in event
            assert "break_index" in event
            assert "broken_level" in event
            assert "swing_index" in event
            assert "time" in event
