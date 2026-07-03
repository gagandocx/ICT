"""
Shared pytest fixtures for ICT bot test suite.

Provides sample OHLC DataFrames with known patterns for testing
market structure, order blocks, FVGs, liquidity, and other modules.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


@pytest.fixture
def bullish_trend_df():
    """
    DataFrame with a clear bullish trend: higher highs and higher lows.

    Creates a 30-candle uptrend with clear swing points that can be
    identified with lookback=3.
    """
    n = 30
    times = [datetime(2024, 1, 1, 10, 0) + timedelta(minutes=i) for i in range(n)]
    # Base uptrend with periodic pullbacks to create swing points
    data = {
        "time": times,
        "open": [
            100, 101, 102, 101, 100, 99,   # pullback
            100, 101, 102, 103, 104, 103,   # move up, pullback
            102, 103, 104, 105, 106, 105,   # move up, pullback
            104, 105, 106, 107, 108, 107,   # move up, pullback
            106, 107, 108, 109, 110, 111,   # final push
        ],
        "high": [
            101, 102, 103, 102, 101, 100,   # swing high at idx 2
            101, 102, 103, 104, 105, 104,   # swing high at idx 10
            103, 104, 105, 106, 107, 106,   # swing high at idx 16
            105, 106, 107, 108, 109, 108,   # swing high at idx 22
            107, 108, 109, 110, 111, 112,   # final push
        ],
        "low": [
            99, 100, 101, 100, 99, 98,      # swing low at idx 5
            99, 100, 101, 102, 103, 102,    # swing low at idx 5 was lowest
            101, 102, 103, 104, 105, 104,   # swing low around idx 11
            103, 104, 105, 106, 107, 106,   # swing low around idx 17-18
            105, 106, 107, 108, 109, 110,   # final push
        ],
        "close": [
            101, 102, 102, 100, 99, 99,
            101, 102, 103, 104, 104, 102,
            103, 104, 105, 106, 106, 104,
            105, 106, 107, 108, 108, 106,
            107, 108, 109, 110, 111, 112,
        ],
    }
    return pd.DataFrame(data)


@pytest.fixture
def bearish_trend_df():
    """
    DataFrame with a clear bearish trend: lower highs and lower lows.

    Creates a 30-candle downtrend with clear swing points.
    """
    n = 30
    times = [datetime(2024, 1, 1, 10, 0) + timedelta(minutes=i) for i in range(n)]
    data = {
        "time": times,
        "open": [
            110, 109, 108, 109, 110, 111,   # pullback up
            110, 109, 108, 107, 106, 107,   # move down, pullback
            108, 107, 106, 105, 104, 105,   # move down, pullback
            106, 105, 104, 103, 102, 103,   # move down, pullback
            104, 103, 102, 101, 100, 99,    # final push down
        ],
        "high": [
            111, 110, 109, 110, 111, 112,   # swing high at idx 5
            111, 110, 109, 108, 107, 108,   # swing high at idx 5
            109, 108, 107, 106, 105, 106,   # swing high at idx 12
            107, 106, 105, 104, 103, 104,   # swing high at idx 18
            105, 104, 103, 102, 101, 100,   # final push
        ],
        "low": [
            109, 108, 107, 108, 109, 110,   # not the lowest
            109, 108, 107, 106, 105, 106,   # swing low at idx 10
            107, 106, 105, 104, 103, 104,   # swing low at idx 16
            105, 104, 103, 102, 101, 102,   # swing low at idx 22
            103, 102, 101, 100, 99, 98,     # final push
        ],
        "close": [
            109, 108, 108, 110, 111, 111,
            109, 108, 107, 106, 106, 108,
            107, 106, 105, 104, 104, 106,
            105, 104, 103, 102, 102, 104,
            103, 102, 101, 100, 99, 98,
        ],
    }
    return pd.DataFrame(data)


@pytest.fixture
def ranging_df():
    """
    DataFrame with ranging/sideways price action.

    Creates equal highs and lows suitable for liquidity detection.
    """
    n = 20
    times = [datetime(2024, 1, 1, 10, 0) + timedelta(minutes=i) for i in range(n)]
    # Price oscillates between 100 and 110 with equal touches
    data = {
        "time": times,
        "open": [105, 106, 108, 109, 108, 106, 104, 102, 101, 103,
                 105, 107, 109, 108, 106, 104, 102, 101, 103, 105],
        "high": [106, 108, 110, 110, 109, 107, 105, 103, 102, 105,
                 107, 109, 110, 110, 107, 105, 103, 102, 105, 107],
        "low":  [104, 105, 107, 108, 107, 105, 103, 100, 100, 102,
                 104, 106, 108, 107, 105, 103, 100, 100, 102, 104],
        "close": [106, 107, 109, 109, 107, 105, 103, 101, 101, 104,
                  106, 108, 109, 108, 106, 104, 101, 101, 104, 106],
    }
    return pd.DataFrame(data)


@pytest.fixture
def fvg_bullish_df():
    """
    DataFrame with a clear bullish FVG pattern.

    candle[0].high < candle[2].low creates a bullish FVG.
    """
    times = [datetime(2024, 1, 1, 10, 0) + timedelta(minutes=i) for i in range(5)]
    data = {
        "time": times,
        "open":  [100, 102, 106, 107, 108],
        "high":  [101, 104, 108, 109, 110],
        "low":   [99,  101, 105, 106, 107],
        "close": [100, 103, 107, 108, 109],
    }
    return pd.DataFrame(data)


@pytest.fixture
def fvg_bearish_df():
    """
    DataFrame with a clear bearish FVG pattern.

    candle[0].low > candle[2].high creates a bearish FVG.
    """
    times = [datetime(2024, 1, 1, 10, 0) + timedelta(minutes=i) for i in range(5)]
    data = {
        "time": times,
        "open":  [110, 108, 104, 103, 102],
        "high":  [111, 109, 105, 104, 103],
        "low":   [109, 107, 103, 102, 101],
        "close": [110, 108, 104, 103, 102],
    }
    return pd.DataFrame(data)


@pytest.fixture
def sample_config():
    """Sample configuration dictionary for testing."""
    return {
        "mt5": {
            "login": 12345,
            "password": "test_pass",
            "server": "TestServer",
            "symbol": "US100",
        },
        "risk": {
            "risk_percent": 0.01,
            "max_daily_loss": 0.03,
        },
        "telegram": {
            "bot_token": "test_token",
            "chat_id": "test_chat",
        },
    }
