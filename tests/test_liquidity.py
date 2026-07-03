"""
Tests for ict_bot/liquidity.py

Tests equal level detection and liquidity sweep detection.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from ict_bot.liquidity import detect_equal_levels, detect_liquidity_sweep


class TestDetectEqualLevels:
    """Tests for detect_equal_levels()."""

    def test_detects_equal_highs_within_tolerance(self):
        """Two or more highs within tolerance_pips should be grouped as equal highs."""
        n = 10
        times = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n)]
        # Highs at idx 2 and idx 7 are both ~110 (within 2 pips)
        df = pd.DataFrame({
            "time": times,
            "open":  [100, 102, 105, 103, 101, 103, 105, 108, 105, 103],
            "high":  [102, 104, 110, 105, 103, 105, 107, 111, 106, 104],
            "low":   [99, 101, 104, 102, 100, 102, 104, 106, 104, 102],
            "close": [101, 103, 108, 104, 102, 104, 106, 109, 105, 103],
        })
        levels = detect_equal_levels(df, tolerance_pips=2)
        equal_highs = [l for l in levels if l["type"] == "equal_highs"]
        assert len(equal_highs) >= 1
        # Check the level is approximately 110
        for eh in equal_highs:
            if 2 in eh["indices"] or 7 in eh["indices"]:
                assert abs(eh["level"] - 110.5) < 2.0
                assert eh["count"] >= 2

    def test_detects_equal_lows_within_tolerance(self):
        """Two or more lows within tolerance_pips should be grouped as equal lows."""
        n = 10
        times = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n)]
        # Lows at idx 3 and idx 8 are both ~95 (within 2 pips)
        df = pd.DataFrame({
            "time": times,
            "open":  [100, 99, 98, 97, 99, 100, 99, 98, 96, 98],
            "high":  [101, 100, 99, 98, 100, 101, 100, 99, 97, 99],
            "low":   [98, 97, 96, 95, 97, 98, 97, 96, 94, 97],
            "close": [99, 98, 97, 96, 98, 99, 98, 97, 95, 98],
        })
        levels = detect_equal_levels(df, tolerance_pips=2)
        equal_lows = [l for l in levels if l["type"] == "equal_lows"]
        assert len(equal_lows) >= 1

    def test_no_equal_levels_with_tight_tolerance(self):
        """With very tight tolerance, distinct levels should not group."""
        n = 5
        times = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n)]
        # All highs are 10 apart
        df = pd.DataFrame({
            "time": times,
            "open":  [100, 110, 120, 130, 140],
            "high":  [105, 115, 125, 135, 145],
            "low":   [95, 105, 115, 125, 135],
            "close": [102, 112, 122, 132, 142],
        })
        levels = detect_equal_levels(df, tolerance_pips=1)
        assert len(levels) == 0


class TestDetectLiquiditySweep:
    """Tests for detect_liquidity_sweep()."""

    def test_sweep_high_detected(self):
        """
        Sweep high: high exceeds equal_highs level + min_sweep_pips,
        but close is below the level.
        """
        n = 12
        times = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n)]
        # Equal highs at idx 2 and 5 around 110
        # Sweep candle at idx 9: high=113 (above 110+2), close=108 (below 110)
        df = pd.DataFrame({
            "time": times,
            "open":  [100, 105, 108, 105, 103, 107, 105, 103, 106, 109, 105, 103],
            "high":  [103, 107, 110, 107, 105, 110, 107, 105, 108, 113, 107, 105],
            "low":   [99, 103, 106, 103, 101, 105, 103, 101, 104, 107, 103, 101],
            "close": [102, 106, 109, 104, 102, 108, 104, 102, 107, 108, 104, 102],
        })
        levels = detect_equal_levels(df, tolerance_pips=2)
        equal_highs = [l for l in levels if l["type"] == "equal_highs"]
        assert len(equal_highs) >= 1

        sweeps = detect_liquidity_sweep(df, levels, min_sweep_pips=2)
        sweep_highs = [s for s in sweeps if s["type"] == "sweep_high"]
        assert len(sweep_highs) >= 1
        assert sweep_highs[0]["sweep_index"] == 9
        assert sweep_highs[0]["close_price"] < sweep_highs[0]["level"]

    def test_sweep_low_detected(self):
        """
        Sweep low: low exceeds equal_lows level - min_sweep_pips,
        but close is above the level.
        """
        n = 12
        times = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n)]
        # Equal lows at idx 2 and 5 around 100
        # Sweep candle at idx 9: low=97 (below 100-2), close=102 (above 100)
        df = pd.DataFrame({
            "time": times,
            "open":  [105, 103, 101, 103, 105, 102, 104, 105, 103, 101, 103, 105],
            "high":  [107, 105, 103, 105, 107, 104, 106, 107, 105, 104, 105, 107],
            "low":   [103, 101, 100, 101, 103, 100, 102, 103, 101, 97, 101, 103],
            "close": [104, 102, 101, 104, 106, 101, 103, 106, 102, 102, 104, 106],
        })
        levels = detect_equal_levels(df, tolerance_pips=2)
        equal_lows = [l for l in levels if l["type"] == "equal_lows"]
        assert len(equal_lows) >= 1

        sweeps = detect_liquidity_sweep(df, levels, min_sweep_pips=2)
        sweep_lows = [s for s in sweeps if s["type"] == "sweep_low"]
        assert len(sweep_lows) >= 1
        assert sweep_lows[0]["close_price"] > sweep_lows[0]["level"]

    def test_clean_breakout_not_marked_as_sweep(self):
        """
        If price breaks above equal highs AND closes above the level,
        it is NOT a sweep.
        """
        n = 10
        times = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n)]
        # Equal highs at idx 1 and 3 around 110
        # At idx 7: high=115 AND close=114 (close ABOVE 110) -> not a sweep
        df = pd.DataFrame({
            "time": times,
            "open":  [105, 108, 106, 109, 107, 108, 110, 112, 113, 114],
            "high":  [108, 110, 108, 110, 109, 110, 112, 115, 116, 117],
            "low":   [103, 106, 104, 107, 105, 106, 108, 110, 111, 112],
            "close": [107, 109, 107, 109, 108, 109, 111, 114, 115, 116],
        })
        levels = detect_equal_levels(df, tolerance_pips=2)
        sweeps = detect_liquidity_sweep(df, levels, min_sweep_pips=2)
        sweep_highs = [s for s in sweeps if s["type"] == "sweep_high"]
        # No sweep since close > level
        assert len(sweep_highs) == 0
