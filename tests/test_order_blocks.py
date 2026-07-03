"""
Tests for ict_bot/order_blocks.py

Tests Order Block identification and mitigation detection.
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta

from ict_bot.order_blocks import find_order_blocks, is_ob_mitigated


class TestFindOrderBlocks:
    """Tests for find_order_blocks()."""

    def test_bullish_ob_last_bearish_candle_before_bullish_event(self):
        """
        Bullish OB is the last bearish candle (close < open) before a bullish
        BOS/MSS event.
        """
        n = 10
        times = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n)]
        df = pd.DataFrame({
            "time": times,
            "open":  [100, 102, 105, 104, 103, 102, 101, 103, 105, 107],
            "high":  [103, 106, 106, 105, 104, 103, 102, 105, 107, 109],
            "low":   [99,  101, 104, 103, 102, 101, 100, 102, 104, 106],
            "close": [102, 105, 105, 103, 102, 101, 100, 104, 106, 108],
        })
        # Candle at idx 6 is bearish: open=101, close=100
        # Create a bullish structure event with break at idx 8
        structure_events = [{
            "type": "bullish_bos",
            "break_index": 8,
            "broken_level": 106,
            "swing_index": 2,
            "time": times[8],
        }]

        obs = find_order_blocks(df, structure_events)
        assert len(obs) == 1
        assert obs[0]["type"] == "bullish_ob"
        # Last bearish candle before idx 8: scanning backward from 7
        # idx 7: open=103, close=104 (bullish)
        # idx 6: open=101, close=100 (bearish) -> this is the OB
        assert obs[0]["index"] == 6

    def test_bearish_ob_last_bullish_candle_before_bearish_event(self):
        """
        Bearish OB is the last bullish candle (close > open) before a bearish
        BOS/MSS event.
        """
        n = 10
        times = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n)]
        df = pd.DataFrame({
            "time": times,
            "open":  [110, 108, 105, 106, 107, 108, 109, 107, 105, 103],
            "high":  [111, 109, 106, 107, 108, 109, 110, 108, 106, 104],
            "low":   [108, 106, 104, 105, 106, 107, 108, 106, 104, 102],
            "close": [108, 106, 104, 107, 108, 109, 110, 106, 104, 102],
        })
        # Candle at idx 6 is bullish: open=109, close=110
        # Create a bearish structure event with break at idx 8
        structure_events = [{
            "type": "bearish_bos",
            "break_index": 8,
            "broken_level": 104,
            "swing_index": 2,
            "time": times[8],
        }]

        obs = find_order_blocks(df, structure_events)
        assert len(obs) == 1
        assert obs[0]["type"] == "bearish_ob"
        # Last bullish candle before idx 8: scanning backward from 7
        # idx 7: open=107, close=106 (bearish)
        # idx 6: open=109, close=110 (bullish) -> this is the OB
        assert obs[0]["index"] == 6

    def test_ob_has_correct_ohlc_values(self):
        """Order block should contain OHLC values from the OB candle."""
        n = 5
        times = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n)]
        df = pd.DataFrame({
            "time": times,
            "open":  [100, 102, 101, 99, 98],
            "high":  [103, 104, 102, 100, 99],
            "low":   [99, 101, 99, 97, 96],
            "close": [102, 103, 99, 97, 96],  # idx 2 is bearish (open=101, close=99)
        })
        structure_events = [{
            "type": "bullish_mss",
            "break_index": 4,
            "broken_level": 103,
            "swing_index": 1,
            "time": times[4],
        }]

        obs = find_order_blocks(df, structure_events)
        assert len(obs) == 1
        ob = obs[0]
        # idx 3: open=99, close=97 (bearish) - last bearish before idx 4
        assert ob["open"] == 99
        assert ob["close"] == 97
        assert ob["high"] == 100
        assert ob["low"] == 97
        assert ob["mitigated"] is False

    def test_no_ob_when_no_opposing_candle_exists(self):
        """If there are no bearish candles before a bullish event, no OB is found."""
        n = 5
        times = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n)]
        # All candles are bullish (close > open)
        df = pd.DataFrame({
            "time": times,
            "open":  [100, 101, 102, 103, 104],
            "high":  [102, 103, 104, 105, 106],
            "low":   [99, 100, 101, 102, 103],
            "close": [101, 102, 103, 104, 105],
        })
        structure_events = [{
            "type": "bullish_bos",
            "break_index": 4,
            "broken_level": 105,
            "swing_index": 2,
            "time": times[4],
        }]

        obs = find_order_blocks(df, structure_events)
        assert len(obs) == 0


class TestIsOBMitigated:
    """Tests for is_ob_mitigated()."""

    def test_bullish_ob_mitigated_when_price_reaches_high(self):
        """Bullish OB is mitigated when price reaches into its zone (at/below high)."""
        ob = {"type": "bullish_ob", "high": 105.0, "low": 100.0}
        assert is_ob_mitigated(ob, 105.0) is True
        assert is_ob_mitigated(ob, 102.0) is True

    def test_bullish_ob_not_mitigated_above_zone(self):
        """Bullish OB is not mitigated when price is above its high."""
        ob = {"type": "bullish_ob", "high": 105.0, "low": 100.0}
        assert is_ob_mitigated(ob, 106.0) is False

    def test_bearish_ob_mitigated_when_price_reaches_low(self):
        """Bearish OB is mitigated when price reaches into its zone (at/above low)."""
        ob = {"type": "bearish_ob", "high": 110.0, "low": 105.0}
        assert is_ob_mitigated(ob, 105.0) is True
        assert is_ob_mitigated(ob, 107.0) is True

    def test_bearish_ob_not_mitigated_below_zone(self):
        """Bearish OB is not mitigated when price is below its low."""
        ob = {"type": "bearish_ob", "high": 110.0, "low": 105.0}
        assert is_ob_mitigated(ob, 104.0) is False
