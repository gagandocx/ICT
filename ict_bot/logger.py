"""
Trade Logger Module - Structured Trade Journal Logging

Provides logging for all trading decisions, entries, exits, and analysis
results. Writes to both console and log files for trade journaling.
"""

import os
import logging
from datetime import datetime


class TradeLogger:
    """
    Trade journal logging system.

    Logs all trade decisions, entries, exits, and analysis results to
    both console and file. Includes timestamps, trade rationale,
    and ICT concepts triggered.

    Parameters
    ----------
    log_dir : str
        Directory for log files. Default 'logs'.
    log_level : int
        Logging level (e.g., logging.INFO). Default logging.INFO.
    """

    def __init__(self, log_dir="logs", log_level=logging.INFO):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)

        self.logger = logging.getLogger("ict_bot")
        self.logger.setLevel(log_level)

        # Avoid adding duplicate handlers
        if not self.logger.handlers:
            # Console handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(log_level)
            console_fmt = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            console_handler.setFormatter(console_fmt)
            self.logger.addHandler(console_handler)

            # File handler - daily log file
            today = datetime.now().strftime("%Y-%m-%d")
            log_file = os.path.join(log_dir, f"trades_{today}.log")
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(log_level)
            file_fmt = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            file_handler.setFormatter(file_fmt)
            self.logger.addHandler(file_handler)

        self.trades_today = []
        self.daily_pnl = 0.0

    def log_analysis(self, timeframe, analysis_type, result):
        """
        Log a market analysis result.

        Parameters
        ----------
        timeframe : str
            Timeframe analyzed (e.g., 'D1', 'H4', 'M15', 'M1').
        analysis_type : str
            Type of analysis (e.g., 'market_structure', 'fvg', 'liquidity').
        result : dict or str
            Analysis result or description.
        """
        msg = f"[ANALYSIS] [{timeframe}] {analysis_type}: {result}"
        self.logger.info(msg)

    def log_trade_entry(self, trade_details):
        """
        Log a trade entry with full details.

        Parameters
        ----------
        trade_details : dict
            Trade details containing:
            - 'direction': 'long' or 'short'
            - 'symbol': trading symbol
            - 'entry_price': entry price
            - 'stop_loss': stop loss price
            - 'take_profit': take profit price
            - 'volume': position size
            - 'risk_reward': R:R ratio
            - 'rationale': dict with ICT concepts triggered (optional)
        """
        direction = trade_details.get("direction", "unknown").upper()
        symbol = trade_details.get("symbol", "US100")
        entry = trade_details.get("entry_price", 0)
        sl = trade_details.get("stop_loss", 0)
        tp = trade_details.get("take_profit", 0)
        volume = trade_details.get("volume", 0)
        rr = trade_details.get("risk_reward", 0)
        rationale = trade_details.get("rationale", {})

        msg = (
            f"[ENTRY] {direction} {symbol} | "
            f"Entry: {entry:.2f} | SL: {sl:.2f} | TP: {tp:.2f} | "
            f"Vol: {volume:.2f} | R:R: {rr:.2f}"
        )
        self.logger.info(msg)

        if rationale:
            concepts = ", ".join(f"{k}: {v}" for k, v in rationale.items())
            self.logger.info(f"[RATIONALE] ICT Concepts: {concepts}")

        self.trades_today.append({
            "type": "entry",
            "time": datetime.now(),
            **trade_details,
        })

    def log_trade_exit(self, trade_result):
        """
        Log a trade exit with results.

        Parameters
        ----------
        trade_result : dict
            Trade result containing:
            - 'direction': 'long' or 'short'
            - 'symbol': trading symbol
            - 'entry_price': entry price
            - 'exit_price': exit price
            - 'profit': profit/loss amount
            - 'result': 'win' or 'loss'
            - 'ticket': order ticket (optional)
        """
        result_type = trade_result.get("result", "unknown").upper()
        symbol = trade_result.get("symbol", "US100")
        entry = trade_result.get("entry_price", 0)
        exit_price = trade_result.get("exit_price", 0)
        profit = trade_result.get("profit", 0)
        direction = trade_result.get("direction", "unknown").upper()

        msg = (
            f"[EXIT] {result_type} | {direction} {symbol} | "
            f"Entry: {entry:.2f} | Exit: {exit_price:.2f} | "
            f"P&L: ${profit:.2f}"
        )
        self.logger.info(msg)

        self.daily_pnl += profit
        self.trades_today.append({
            "type": "exit",
            "time": datetime.now(),
            **trade_result,
        })

    def log_daily_summary(self):
        """
        Log an end-of-day summary of all trades.

        Returns
        -------
        dict
            Summary statistics for the day.
        """
        entries = [t for t in self.trades_today if t["type"] == "entry"]
        exits = [t for t in self.trades_today if t["type"] == "exit"]
        wins = [t for t in exits if t.get("result") == "win"]
        losses = [t for t in exits if t.get("result") == "loss"]

        total_trades = len(entries)
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / len(exits) * 100) if exits else 0.0

        summary = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "total_trades": total_trades,
            "wins": win_count,
            "losses": loss_count,
            "win_rate": win_rate,
            "net_pnl": self.daily_pnl,
        }

        self.logger.info(
            f"[DAILY SUMMARY] Trades: {total_trades} | "
            f"Wins: {win_count} | Losses: {loss_count} | "
            f"Win Rate: {win_rate:.1f}% | Net P&L: ${self.daily_pnl:.2f}"
        )

        return summary

    def reset_daily(self):
        """Reset daily tracking for a new trading day."""
        self.trades_today = []
        self.daily_pnl = 0.0
        self.logger.info("[SYSTEM] Daily stats reset for new trading day")
