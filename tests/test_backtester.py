"""
Tests for ict_bot/backtester.py

Tests the backtesting engine data loading, execution, and results calculation.
Includes tests for tick data auto-detection and conversion to OHLC candles.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from ict_bot.backtester import Backtester


class TestBacktesterLoadData:
    """Tests for Backtester.load_data()."""

    def test_load_from_dataframe(self):
        """Should successfully load data from a DataFrame."""
        n = 50
        times = [datetime(2024, 1, 1, 10, 0) + timedelta(minutes=i) for i in range(n)]
        df = pd.DataFrame({
            "time": times,
            "open": np.random.uniform(14900, 15100, n),
            "high": np.random.uniform(15000, 15200, n),
            "low": np.random.uniform(14800, 15000, n),
            "close": np.random.uniform(14900, 15100, n),
        })
        bt = Backtester()
        assert bt.load_data(df) is True
        assert bt.data is not None
        assert len(bt.data) == n

    def test_load_fails_with_missing_columns(self):
        """Should return False if required columns are missing."""
        df = pd.DataFrame({
            "time": [datetime(2024, 1, 1)],
            "open": [100],
            "high": [101],
            # missing 'low' and 'close'
        })
        bt = Backtester()
        assert bt.load_data(df) is False

    def test_load_fails_with_invalid_input(self):
        """Should return False for non-string, non-DataFrame input."""
        bt = Backtester()
        assert bt.load_data(12345) is False

    def test_load_fails_with_nonexistent_csv(self):
        """Should return False for a non-existent CSV path."""
        bt = Backtester()
        assert bt.load_data("/nonexistent/path.csv") is False


class TestBacktesterRun:
    """Tests for Backtester.run()."""

    def test_run_with_no_data_returns_empty_results(self):
        """Running without loaded data should return empty results."""
        bt = Backtester()
        results = bt.run()
        assert results["total_trades"] == 0
        assert results["final_balance"] == 10000.0

    def test_run_returns_expected_keys(self):
        """Results dict should contain all expected keys."""
        bt = Backtester()
        n = 100
        times = [datetime(2024, 1, 15, 15, 0) + timedelta(minutes=i) for i in range(n)]
        df = pd.DataFrame({
            "time": times,
            "open": [15000 + i for i in range(n)],
            "high": [15002 + i for i in range(n)],
            "low": [14998 + i for i in range(n)],
            "close": [15001 + i for i in range(n)],
        })
        bt.load_data(df)
        results = bt.run()

        expected_keys = [
            "win_rate", "profit_factor", "max_drawdown", "total_trades",
            "avg_rr", "equity_curve", "net_profit", "final_balance",
            "wins", "losses", "gross_profit", "gross_loss",
        ]
        for key in expected_keys:
            assert key in results

    def test_run_with_date_filter(self):
        """Should filter data by start_date and end_date."""
        bt = Backtester()
        n = 200
        times = [datetime(2024, 1, 1, 10, 0) + timedelta(minutes=i) for i in range(n)]
        df = pd.DataFrame({
            "time": times,
            "open": [15000.0] * n,
            "high": [15001.0] * n,
            "low": [14999.0] * n,
            "close": [15000.0] * n,
        })
        bt.load_data(df)
        results = bt.run(
            start_date="2024-01-01 11:00:00",
            end_date="2024-01-01 12:00:00",
        )
        # Should run without error; flat data means no trades
        assert results["total_trades"] == 0


class TestBacktesterResults:
    """Tests for Backtester.get_results()."""

    def test_get_results_before_run_returns_empty(self):
        """get_results() before run() should return empty results."""
        bt = Backtester(initial_balance=5000.0)
        results = bt.get_results()
        assert results["total_trades"] == 0
        assert results["final_balance"] == 5000.0
        assert results["win_rate"] == 0.0

    def test_initial_balance_is_configurable(self):
        """Backtester should use the configured initial balance."""
        bt = Backtester(initial_balance=25000.0)
        results = bt.get_results()
        assert results["final_balance"] == 25000.0

    def test_equity_curve_starts_with_initial_balance(self):
        """Equity curve should start with the initial balance."""
        bt = Backtester(initial_balance=10000.0)
        bt.load_data(pd.DataFrame({
            "time": [datetime(2024, 1, 1, 10, i) for i in range(10)],
            "open": [100.0] * 10,
            "high": [101.0] * 10,
            "low": [99.0] * 10,
            "close": [100.0] * 10,
        }))
        results = bt.run()
        assert results["equity_curve"][0] == 10000.0


class TestBacktesterTickData:
    """Tests for tick data auto-detection and conversion."""

    def _make_tick_df(self, n_ticks=120, start_ms=1780275617517):
        """Helper to create a tick DataFrame mimicking MT5 export."""
        # Spread ticks across 2 minutes (60s each) so we get 2 candles
        timestamps = [start_ms + i * 1000 for i in range(n_ticks)]
        bids = [30392.94 + (i % 10) * 0.1 for i in range(n_ticks)]
        asks = [b + 0.80 for b in bids]
        return pd.DataFrame({
            "time_msc": timestamps,
            "bid": bids,
            "ask": asks,
            "last": [0.0] * n_ticks,
            "volume": [0] * n_ticks,
            "flags": [134] * n_ticks,
            "flags_str": ["BID|ASK"] * n_ticks,
            "volume_real": [0.0] * n_ticks,
        })

    def test_load_tick_data_auto_detected(self):
        """Should auto-detect tick data format and load successfully."""
        bt = Backtester()
        df = self._make_tick_df()
        assert bt.load_data(df) is True
        assert bt.data is not None
        # After conversion, data should have OHLC columns
        assert "open" in bt.data.columns
        assert "high" in bt.data.columns
        assert "low" in bt.data.columns
        assert "close" in bt.data.columns
        assert "time" in bt.data.columns

    def test_tick_data_converted_to_1min_candles(self):
        """Tick data should be resampled into 1-minute OHLC candles."""
        bt = Backtester()
        # Use a start time exactly on a minute boundary to get predictable candles
        # 1780275600000 = 2026-06-01 01:00:00.000 UTC
        start_ms = 1780275600000
        # 60 ticks at 1-second intervals within a single minute -> 1 candle
        df = self._make_tick_df(n_ticks=59, start_ms=start_ms)
        bt.load_data(df)
        assert len(bt.data) == 1

        # 120 ticks at 1s intervals spanning 2 full minutes -> 2 candles
        bt2 = Backtester()
        df2 = self._make_tick_df(n_ticks=120, start_ms=start_ms)
        bt2.load_data(df2)
        assert len(bt2.data) == 2

    def test_tick_data_uses_mid_price(self):
        """OHLC candles from ticks should use mid price (bid+ask)/2."""
        bt = Backtester()
        # Create simple ticks: bid=100, ask=102 -> mid=101
        df = pd.DataFrame({
            "time_msc": [1780275617517, 1780275617517 + 1000],
            "bid": [100.0, 100.0],
            "ask": [102.0, 102.0],
            "last": [0.0, 0.0],
            "volume": [0, 0],
            "flags": [134, 134],
            "flags_str": ["BID|ASK", "BID|ASK"],
            "volume_real": [0.0, 0.0],
        })
        bt.load_data(df)
        # Mid price should be 101.0
        assert bt.data.iloc[0]["open"] == 101.0
        assert bt.data.iloc[0]["close"] == 101.0

    def test_time_msc_converted_to_datetime(self):
        """time_msc (millisecond epoch) should be properly converted to datetime."""
        bt = Backtester()
        # 1780275617517 ms -> known datetime
        df = self._make_tick_df(n_ticks=10)
        bt.load_data(df)
        assert pd.api.types.is_datetime64_any_dtype(bt.data["time"])

    def test_ohlc_data_still_works(self):
        """Standard OHLC format should still load correctly (backward compat)."""
        bt = Backtester()
        n = 30
        times = [datetime(2024, 1, 1, 10, 0) + timedelta(minutes=i) for i in range(n)]
        df = pd.DataFrame({
            "time": times,
            "open": [100.0] * n,
            "high": [101.0] * n,
            "low": [99.0] * n,
            "close": [100.0] * n,
        })
        assert bt.load_data(df) is True
        assert len(bt.data) == n

    def test_tick_data_run_produces_results(self):
        """Running backtest on tick-converted data should produce valid results."""
        bt = Backtester()
        # Create enough ticks for a meaningful backtest (5 minutes of ticks)
        df = self._make_tick_df(n_ticks=300, start_ms=1780275617517)
        bt.load_data(df)
        results = bt.run()
        assert "total_trades" in results
        assert "final_balance" in results
        assert results["equity_curve"][0] == 10000.0

    def test_load_fails_with_unknown_columns(self):
        """Should return False for data with unrecognized column format."""
        bt = Backtester()
        df = pd.DataFrame({
            "x": [1, 2, 3],
            "y": [4, 5, 6],
        })
        assert bt.load_data(df) is False

    def test_tick_data_with_csv_file(self, tmp_path):
        """Should auto-detect and convert tick data loaded from a CSV file."""
        bt = Backtester()
        # Write tick data to a temp CSV
        df = self._make_tick_df(n_ticks=60)
        csv_path = tmp_path / "ticks.csv"
        df.to_csv(csv_path, index=False)
        assert bt.load_data(str(csv_path)) is True
        assert bt.data is not None
        assert "open" in bt.data.columns
