"""
Backtesting Engine Module - Historical Data Replay

Replays historical 1m OHLC data through the entry model to simulate
trading performance. Operates only during kill zone windows and
tracks comprehensive performance metrics.

Supports two input formats:
  1. Standard OHLC: columns time, open, high, low, close
  2. MT5 tick data: columns time_msc, bid, ask, last, volume, flags, flags_str, volume_real
     - time_msc is a millisecond epoch timestamp
     - Tick data is automatically converted to 1-minute OHLC candles using mid price (bid+ask)/2
"""

import pandas as pd
import numpy as np
from datetime import datetime

from ict_bot.entry_model import EntryModel
from ict_bot.kill_zones import is_in_kill_zone, get_active_kill_zone
from ict_bot.risk_management import calculate_position_size
from ict_bot.market_structure import detect_swing_points


# Column sets used for auto-detection of data format
_TICK_COLUMNS = {"time_msc", "bid", "ask"}
_OHLC_COLUMNS = {"time", "open", "high", "low", "close"}


class Backtester:
    """
    Backtesting engine for the ICT entry model.

    Replays historical OHLC data through the sequential entry model,
    simulating trades during kill zone windows and tracking performance.

    Parameters
    ----------
    initial_balance : float
        Starting account balance. Default 10000.
    risk_percent : float
        Risk per trade as a fraction (e.g., 0.01 for 1%). Default 0.01.
    max_daily_loss : float
        Maximum daily loss as a fraction. Default 0.03.
    """

    def __init__(self, initial_balance=10000.0, risk_percent=0.01,
                 max_daily_loss=0.03):
        self.initial_balance = initial_balance
        self.risk_percent = risk_percent
        self.max_daily_loss = max_daily_loss

        self.data = None
        self.trades = []
        self.equity_curve = []
        self.results = None

    def load_data(self, csv_file_or_dataframe):
        """
        Load historical data for backtesting.

        Accepts either standard OHLC data or MT5 tick data.  The format is
        auto-detected based on column headers:
          - If columns include 'time_msc', 'bid', 'ask' -> tick data
          - If columns include 'time', 'open', 'high', 'low', 'close' -> OHLC data

        For tick data, ticks are aggregated into 1-minute OHLC candles using
        the mid price ((bid + ask) / 2).

        Parameters
        ----------
        csv_file_or_dataframe : str or pd.DataFrame
            Either a path to a CSV file or a pandas DataFrame.

        Returns
        -------
        bool
            True if data loaded successfully, False otherwise.
        """
        if isinstance(csv_file_or_dataframe, pd.DataFrame):
            raw = csv_file_or_dataframe.copy()
        elif isinstance(csv_file_or_dataframe, str):
            try:
                raw = pd.read_csv(csv_file_or_dataframe)
            except (FileNotFoundError, pd.errors.EmptyDataError):
                return False
        else:
            return False

        # Auto-detect format based on column headers
        columns = set(raw.columns)

        if _TICK_COLUMNS.issubset(columns):
            # Tick data format
            raw = self._convert_ticks_to_ohlc(raw)
            if raw is None or raw.empty:
                self.data = None
                return False
        elif _OHLC_COLUMNS.issubset(columns):
            # Standard OHLC format -- ensure required columns
            pass
        else:
            self.data = None
            return False

        # Ensure required OHLC columns exist after any conversion
        required_cols = ["time", "open", "high", "low", "close"]
        for col in required_cols:
            if col not in raw.columns:
                self.data = None
                return False

        # Parse time column
        if not pd.api.types.is_datetime64_any_dtype(raw["time"]):
            raw["time"] = pd.to_datetime(raw["time"])

        self.data = raw.sort_values("time").reset_index(drop=True)
        return True

    @staticmethod
    def _convert_ticks_to_ohlc(tick_df):
        """
        Convert tick data to 1-minute OHLC candles.

        Uses the mid price ((bid + ask) / 2) for aggregation.  The time_msc
        column (millisecond epoch timestamp) is converted to a datetime index
        before resampling.

        Parameters
        ----------
        tick_df : pd.DataFrame
            DataFrame with at least columns: time_msc, bid, ask.

        Returns
        -------
        pd.DataFrame or None
            DataFrame with columns: time, open, high, low, close.
            Returns None if conversion fails.
        """
        try:
            df = tick_df.copy()

            # Convert millisecond epoch to datetime
            df["time"] = pd.to_datetime(df["time_msc"], unit="ms", utc=True)

            # Compute mid price
            df["mid"] = (df["bid"].astype(float) + df["ask"].astype(float)) / 2.0

            # Resample to 1-minute candles
            df = df.set_index("time")
            ohlc = df["mid"].resample("1min").agg(
                open="first",
                high="max",
                low="min",
                close="last",
            ).dropna().reset_index()

            # Remove timezone info so downstream code works uniformly
            ohlc["time"] = ohlc["time"].dt.tz_localize(None)

            return ohlc
        except (KeyError, ValueError, TypeError):
            return None

    def run(self, start_date=None, end_date=None):
        """
        Run the backtest over the loaded data.

        Parameters
        ----------
        start_date : str or datetime or None
            Start date filter. If None, uses all data from beginning.
        end_date : str or datetime or None
            End date filter. If None, uses all data until end.

        Returns
        -------
        dict
            Backtest results (same as get_results()).
        """
        if self.data is None or self.data.empty:
            self.results = self._empty_results()
            return self.results

        # Filter by date range
        df = self.data.copy()
        if start_date is not None:
            start_date = pd.to_datetime(start_date)
            df = df[df["time"] >= start_date]
        if end_date is not None:
            end_date = pd.to_datetime(end_date)
            df = df[df["time"] <= end_date]

        if df.empty:
            self.results = self._empty_results()
            return self.results

        # Reset state
        self.trades = []
        self.equity_curve = [self.initial_balance]
        balance = self.initial_balance
        daily_pnl = 0.0
        current_day = None
        entry_model = EntryModel()
        active_trade = None

        # --- HTF range derivation for premium/discount filter ---
        # Build a daily OHLC summary from the 1m data to derive swing points.
        # We use a 20-day lookback to compute HTF swing high/low, updating
        # at the start of each new day in the main loop.
        daily_ohlc = self._build_daily_ohlc(df)
        htf_lookback = 20

        def update_htf_range(entry_model_, daily_ohlc_, candle_day_):
            """Update entry model's HTF range from daily OHLC up to candle_day."""
            if daily_ohlc_ is None or daily_ohlc_.empty:
                return
            past_days = daily_ohlc_[daily_ohlc_["time"] < pd.Timestamp(candle_day_)]
            if len(past_days) < 3:
                return
            recent = past_days.tail(htf_lookback)
            swings = detect_swing_points(recent.reset_index(drop=True), lookback=2)
            swing_highs = [s for s in swings if s["type"] == "swing_high"]
            swing_lows = [s for s in swings if s["type"] == "swing_low"]
            if swing_highs and swing_lows:
                htf_high = max(s["price"] for s in swing_highs)
                htf_low = min(s["price"] for s in swing_lows)
                entry_model_.set_htf_range(htf_high, htf_low)

        for idx, row in df.iterrows():
            candle = {
                "time": row["time"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
            }

            # Track daily reset
            candle_day = row["time"].date() if hasattr(row["time"], "date") else None
            if candle_day and candle_day != current_day:
                current_day = candle_day
                daily_pnl = 0.0
                # Update HTF swing range for premium/discount filter
                update_htf_range(entry_model, daily_ohlc, candle_day)

            # Check if we have an active trade - simulate SL/TP hit
            if active_trade is not None:
                trade_result = self._check_trade_exit(active_trade, candle)
                if trade_result is not None:
                    profit = trade_result["profit"]
                    balance += profit
                    daily_pnl += profit
                    self.trades.append(trade_result)
                    self.equity_curve.append(balance)
                    active_trade = None

            # Only look for new entries during kill zones and if no active trade
            if active_trade is None:
                in_kz = is_in_kill_zone(row["time"])
                if in_kz:
                    # Check daily loss limit
                    max_loss = balance * self.max_daily_loss
                    if abs(min(daily_pnl, 0)) >= max_loss:
                        entry_model.reset()
                        continue

                    signal = entry_model.update(candle)
                    if signal is not None:
                        # Calculate position size
                        pos_result = calculate_position_size(
                            balance, self.risk_percent,
                            signal["entry_price"], signal["stop_loss"]
                        )
                        if pos_result["valid"]:
                            active_trade = {
                                "direction": signal["direction"],
                                "entry_price": signal["entry_price"],
                                "stop_loss": signal["stop_loss"],
                                "take_profit": signal["take_profit"],
                                "volume": pos_result["volume"],
                                "entry_time": row["time"],
                                "risk_amount": pos_result["risk_amount"],
                            }
                        entry_model.reset()
                else:
                    # Kill zone ended, reset
                    entry_model.reset()

        # Close any remaining active trade at last close
        if active_trade is not None and not df.empty:
            last_row = df.iloc[-1]
            profit = self._calculate_profit(
                active_trade, last_row["close"]
            )
            balance += profit
            self.trades.append({
                **active_trade,
                "exit_price": last_row["close"],
                "exit_time": last_row["time"],
                "profit": profit,
                "result": "win" if profit > 0 else "loss",
            })
            self.equity_curve.append(balance)

        self.results = self._calculate_results()
        return self.results

    def get_results(self):
        """
        Return backtest results.

        Returns
        -------
        dict
            Results with:
            - 'win_rate': percentage of winning trades
            - 'profit_factor': gross profit / gross loss
            - 'max_drawdown': maximum peak-to-trough decline
            - 'total_trades': number of trades taken
            - 'avg_rr': average realized risk/reward
            - 'equity_curve': list of equity values
            - 'net_profit': total profit/loss
            - 'final_balance': ending balance
        """
        if self.results is None:
            return self._empty_results()
        return self.results

    def _check_trade_exit(self, trade, candle):
        """
        Check if a trade hits SL or TP on the current candle.

        NOTE: Same-candle SL/TP priority assumption
        When both stop loss and take profit are within a single candle's range,
        this method checks SL first and records a loss. In real markets, the
        fill order is ambiguous when both levels are breached in one candle.
        This conservative (SL-first) approach biases backtest results slightly
        pessimistically. For NAS100 on 1-minute data during volatile sessions,
        same-candle SL/TP breach is plausible. A future enhancement could offer
        configurable modes (conservative SL-first vs optimistic TP-first).

        Parameters
        ----------
        trade : dict
            Active trade info.
        candle : dict
            Current candle OHLC.

        Returns
        -------
        dict or None
            Trade result if exited, None otherwise.
        """
        if trade["direction"] == "long":
            # Check stop loss hit (price went below SL)
            if candle["low"] <= trade["stop_loss"]:
                profit = self._calculate_profit(trade, trade["stop_loss"])
                return {
                    **trade,
                    "exit_price": trade["stop_loss"],
                    "exit_time": candle["time"],
                    "profit": profit,
                    "result": "loss",
                }
            # Check take profit hit (price went above TP)
            if candle["high"] >= trade["take_profit"]:
                profit = self._calculate_profit(trade, trade["take_profit"])
                return {
                    **trade,
                    "exit_price": trade["take_profit"],
                    "exit_time": candle["time"],
                    "profit": profit,
                    "result": "win",
                }
        elif trade["direction"] == "short":
            # Check stop loss hit (price went above SL)
            if candle["high"] >= trade["stop_loss"]:
                profit = self._calculate_profit(trade, trade["stop_loss"])
                return {
                    **trade,
                    "exit_price": trade["stop_loss"],
                    "exit_time": candle["time"],
                    "profit": profit,
                    "result": "loss",
                }
            # Check take profit hit (price went below TP)
            if candle["low"] <= trade["take_profit"]:
                profit = self._calculate_profit(trade, trade["take_profit"])
                return {
                    **trade,
                    "exit_price": trade["take_profit"],
                    "exit_time": candle["time"],
                    "profit": profit,
                    "result": "win",
                }

        return None

    def _calculate_profit(self, trade, exit_price):
        """
        Calculate profit/loss for a trade.

        Parameters
        ----------
        trade : dict
            Trade info with direction, entry_price, volume.
        exit_price : float
            Exit price.

        Returns
        -------
        float
            Profit (positive) or loss (negative).
        """
        volume = trade.get("volume", 1.0)
        if trade["direction"] == "long":
            return (exit_price - trade["entry_price"]) * volume
        else:
            return (trade["entry_price"] - exit_price) * volume

    def _calculate_results(self):
        """Calculate comprehensive backtest results."""
        if not self.trades:
            return self._empty_results()

        wins = [t for t in self.trades if t.get("result") == "win"]
        losses = [t for t in self.trades if t.get("result") == "loss"]

        total_trades = len(self.trades)
        win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0.0

        gross_profit = sum(t["profit"] for t in wins) if wins else 0.0
        gross_loss = abs(sum(t["profit"] for t in losses)) if losses else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

        # Calculate max drawdown from equity curve
        max_drawdown = self._calculate_max_drawdown()

        # Average R:R (realized)
        rr_ratios = []
        for trade in self.trades:
            risk = abs(trade["entry_price"] - trade["stop_loss"])
            reward = abs(trade.get("exit_price", trade["entry_price"]) - trade["entry_price"])
            if risk > 0:
                rr_ratios.append(reward / risk)
        avg_rr = np.mean(rr_ratios) if rr_ratios else 0.0

        net_profit = sum(t["profit"] for t in self.trades)
        final_balance = self.initial_balance + net_profit

        return {
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown": max_drawdown,
            "total_trades": total_trades,
            "avg_rr": avg_rr,
            "equity_curve": self.equity_curve,
            "net_profit": net_profit,
            "final_balance": final_balance,
            "wins": len(wins),
            "losses": len(losses),
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
        }

    def _calculate_max_drawdown(self):
        """Calculate maximum drawdown from equity curve."""
        if not self.equity_curve:
            return 0.0

        peak = self.equity_curve[0]
        max_dd = 0.0

        for equity in self.equity_curve:
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak if peak > 0 else 0.0
            if drawdown > max_dd:
                max_dd = drawdown

        return max_dd

    def _empty_results(self):
        """Return empty results structure."""
        return {
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
            "total_trades": 0,
            "avg_rr": 0.0,
            "equity_curve": [self.initial_balance],
            "net_profit": 0.0,
            "final_balance": self.initial_balance,
            "wins": 0,
            "losses": 0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
        }

    def _build_daily_ohlc(self, df):
        """
        Aggregate 1-minute OHLC data into daily bars.

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame with 'time', 'open', 'high', 'low', 'close' columns.

        Returns
        -------
        pd.DataFrame or None
            Daily OHLC DataFrame, or None if aggregation fails.
        """
        if df is None or df.empty:
            return None
        daily = df.set_index("time").resample("D").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
        }).dropna().reset_index()
        daily.rename(columns={"time": "time"}, inplace=True)
        return daily
