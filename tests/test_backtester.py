"""
Tests for ict_bot/backtester.py

Tests the backtesting engine data loading, execution, and results calculation.
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
