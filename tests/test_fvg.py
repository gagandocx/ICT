"""
Tests for ict_bot/fvg.py

Tests Fair Value Gap detection, Inverse FVG detection, and midpoint calculation.
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta

from ict_bot.fvg import detect_fvg, detect_ifvg, get_fvg_midpoint


class TestDetectFVG:
    """Tests for detect_fvg()."""

    def test_bullish_fvg_detected(self, fvg_bullish_df):
        """
        Bullish FVG: candle[i-2].high < candle[i].low.
        In the fixture: candle[0].high=101 < candle[2].low=105.
        """
        fvgs = detect_fvg(fvg_bullish_df)
        bullish = [f for f in fvgs if f["type"] == "bullish_fvg"]
        assert len(bullish) >= 1
        # The FVG gap is between candle[0].high (101) and candle[2].low (105)
        fvg = bullish[0]
        assert fvg["low"] == 101.0
        assert fvg["high"] == 105.0
        assert fvg["filled"] is False

    def test_bearish_fvg_detected(self, fvg_bearish_df):
        """
        Bearish FVG: candle[i-2].low > candle[i].high.
        In the fixture: candle[0].low=109 > candle[2].high=105.
        """
        fvgs = detect_fvg(fvg_bearish_df)
        bearish = [f for f in fvgs if f["type"] == "bearish_fvg"]
        assert len(bearish) >= 1
        fvg = bearish[0]
        # gap between candle[0].low=109 and candle[2].high=105
        assert fvg["high"] == 109.0
        assert fvg["low"] == 105.0

    def test_no_fvg_in_overlapping_candles(self):
        """Candles with overlapping ranges should not produce FVGs."""
        times = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(5)]
        df = pd.DataFrame({
            "time": times,
            "open":  [100, 101, 102, 103, 104],
            "high":  [103, 104, 105, 106, 107],
            "low":   [99,  100, 101, 102, 103],
            "close": [101, 102, 103, 104, 105],
        })
        fvgs = detect_fvg(df)
        assert len(fvgs) == 0

    def test_fvg_midpoint_is_correct(self, fvg_bullish_df):
        """FVG midpoint should be (high + low) / 2."""
        fvgs = detect_fvg(fvg_bullish_df)
        bullish = [f for f in fvgs if f["type"] == "bullish_fvg"]
        assert len(bullish) >= 1
        fvg = bullish[0]
        expected_midpoint = (fvg["high"] + fvg["low"]) / 2.0
        assert fvg["midpoint"] == expected_midpoint

    def test_fvg_index_is_middle_candle(self, fvg_bullish_df):
        """FVG index should be the middle candle (i-1) of the 3-candle pattern."""
        fvgs = detect_fvg(fvg_bullish_df)
        bullish = [f for f in fvgs if f["type"] == "bullish_fvg"]
        # Pattern uses candles at 0, 1, 2 -> index = 1
        assert bullish[0]["index"] == 1


class TestDetectIFVG:
    """Tests for detect_ifvg()."""

    def test_bullish_fvg_filled_becomes_bearish_ifvg(self):
        """
        A bullish FVG that gets filled (price trades down through it)
        becomes a bearish iFVG.
        """
        times = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(8)]
        # Candles 0-2: create bullish FVG (candle0.high=101 < candle2.low=105)
        # Candles 5+: price drops below FVG low (101), filling it
        df = pd.DataFrame({
            "time": times,
            "open":  [100, 103, 106, 107, 106, 104, 102, 100],
            "high":  [101, 105, 108, 109, 108, 106, 104, 102],
            "low":   [99,  102, 105, 106, 105, 103, 100, 98],
            "close": [100, 104, 107, 108, 107, 104, 101, 99],
        })
        fvgs = detect_fvg(df)
        bullish_fvgs = [f for f in fvgs if f["type"] == "bullish_fvg"]
        assert len(bullish_fvgs) >= 1

        ifvgs = detect_ifvg(df, fvgs)
        bearish_ifvgs = [f for f in ifvgs if f["type"] == "bearish_ifvg"]
        assert len(bearish_ifvgs) >= 1
        assert bearish_ifvgs[0]["high"] == bullish_fvgs[0]["high"]
        assert bearish_ifvgs[0]["low"] == bullish_fvgs[0]["low"]

    def test_bearish_fvg_filled_becomes_bullish_ifvg(self):
        """
        A bearish FVG that gets filled (price trades up through it)
        becomes a bullish iFVG.
        """
        times = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(8)]
        # Candles 0-2: create bearish FVG (candle0.low=109 > candle2.high=105)
        # Candles 5+: price rises above FVG high (109), filling it
        df = pd.DataFrame({
            "time": times,
            "open":  [110, 107, 104, 103, 104, 106, 108, 111],
            "high":  [111, 108, 105, 104, 105, 107, 110, 112],
            "low":   [109, 106, 103, 102, 103, 105, 107, 109],
            "close": [110, 107, 104, 103, 104, 106, 109, 111],
        })
        fvgs = detect_fvg(df)
        bearish_fvgs = [f for f in fvgs if f["type"] == "bearish_fvg"]
        assert len(bearish_fvgs) >= 1

        ifvgs = detect_ifvg(df, fvgs)
        bullish_ifvgs = [f for f in ifvgs if f["type"] == "bullish_ifvg"]
        assert len(bullish_ifvgs) >= 1

    def test_unfilled_fvg_does_not_produce_ifvg(self, fvg_bullish_df):
        """An FVG that is never filled should not create an iFVG."""
        fvgs = detect_fvg(fvg_bullish_df)
        ifvgs = detect_ifvg(fvg_bullish_df, fvgs)
        assert len(ifvgs) == 0


class TestGetFVGMidpoint:
    """Tests for get_fvg_midpoint()."""

    def test_midpoint_calculation(self):
        """Midpoint should be (high + low) / 2."""
        fvg = {"high": 110.0, "low": 100.0}
        assert get_fvg_midpoint(fvg) == 105.0

    def test_midpoint_with_odd_values(self):
        """Midpoint works with non-round numbers."""
        fvg = {"high": 15234.5, "low": 15230.3}
        expected = (15234.5 + 15230.3) / 2.0
        assert abs(get_fvg_midpoint(fvg) - expected) < 1e-10
