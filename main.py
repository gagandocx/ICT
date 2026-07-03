"""
ICT Trading Bot - Main Entry Point

An automated trading bot implementing Inner Circle Trader (ICT) concepts
for NAS100 (US100) using MetaTrader 5.

Usage:
    python main.py --config config/settings.yaml
    python main.py --backtest --config config/settings.yaml
    python main.py --help
"""

import argparse
import os
import sys
import time
from datetime import datetime

import yaml

from ict_bot.mt5_connector import MT5Connector
from ict_bot.telegram_notifier import TelegramNotifier
from ict_bot.logger import TradeLogger
from ict_bot.entry_model import EntryModel
from ict_bot.backtester import Backtester
from ict_bot.kill_zones import is_in_kill_zone, get_active_kill_zone
from ict_bot.risk_management import (
    calculate_position_size,
    check_daily_loss_limit,
    can_take_trade,
)
from ict_bot import market_structure, fvg, liquidity


def load_config(config_path):
    """
    Load configuration from a YAML file with environment variable overrides.

    Sensitive credentials can be overridden via environment variables:
      - ICT_MT5_LOGIN: overrides mt5.login
      - ICT_MT5_PASSWORD: overrides mt5.password
      - ICT_MT5_SERVER: overrides mt5.server
      - ICT_TELEGRAM_BOT_TOKEN: overrides telegram.bot_token
      - ICT_TELEGRAM_CHAT_ID: overrides telegram.chat_id

    Parameters
    ----------
    config_path : str
        Path to the YAML configuration file.

    Returns
    -------
    dict
        Configuration dictionary.
    """
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error: Invalid YAML in config file: {e}")
        sys.exit(1)

    if config is None:
        config = {}

    # Store config file path for downstream path resolution
    config["_config_path"] = config_path

    # Apply environment variable overrides for sensitive credentials
    if "mt5" not in config:
        config["mt5"] = {}
    if os.environ.get("ICT_MT5_LOGIN"):
        config["mt5"]["login"] = os.environ["ICT_MT5_LOGIN"]
    if os.environ.get("ICT_MT5_PASSWORD"):
        config["mt5"]["password"] = os.environ["ICT_MT5_PASSWORD"]
    if os.environ.get("ICT_MT5_SERVER"):
        config["mt5"]["server"] = os.environ["ICT_MT5_SERVER"]

    if "telegram" not in config:
        config["telegram"] = {}
    if os.environ.get("ICT_TELEGRAM_BOT_TOKEN"):
        config["telegram"]["bot_token"] = os.environ["ICT_TELEGRAM_BOT_TOKEN"]
    if os.environ.get("ICT_TELEGRAM_CHAT_ID"):
        config["telegram"]["chat_id"] = os.environ["ICT_TELEGRAM_CHAT_ID"]

    return config


def run_backtest(config):
    """
    Run the backtesting engine.

    Parameters
    ----------
    config : dict
        Configuration dictionary with backtest settings.
    """
    logger = TradeLogger(log_dir="logs")
    logger.log_analysis("SYSTEM", "backtest_start", "Starting backtest")

    initial_balance = config.get("risk", {}).get("initial_balance", 10000)
    risk_percent = config.get("risk", {}).get("risk_per_trade", 0.01)
    max_daily_loss = config.get("risk", {}).get("max_daily_loss", 0.03)

    backtester = Backtester(
        initial_balance=initial_balance,
        risk_percent=risk_percent,
        max_daily_loss=max_daily_loss,
    )

    # Load data from config or default path
    data_path = config.get("backtest", {}).get("data_file", None)
    if data_path:
        # Determine config directory for relative path resolution
        config_path = config.get("_config_path", None)
        config_dir = None
        if config_path:
            config_dir = os.path.dirname(os.path.abspath(config_path))

        loaded = backtester.load_data(data_path, config_dir=config_dir)
        if not loaded:
            print(f"\nError: Could not load backtest data from '{data_path}'")
            errors = backtester.get_load_errors()
            if errors:
                print("Details:")
                for err in errors:
                    print(f"  - {err}")
            print(f"\nHint: Make sure the file exists at the specified path.")
            print(f"  The file can be a CSV with or without .csv extension.")
            print(f"  Supported formats:")
            print(f"    - OHLC: time,open,high,low,close")
            print(f"    - Tick: time_msc,bid,ask,last,volume,flags,flags_str,volume_real")
            sys.exit(1)
    else:
        print("No backtest data file specified in config.")
        print("Add 'backtest.data_file' to your config YAML with a path to CSV data.")
        print("\nExpected CSV format: time,open,high,low,close")
        print("Example config:")
        print("  backtest:")
        print("    data_file: data/US100_M1.csv")
        print("    start_date: '2024-01-01'")
        print("    end_date: '2024-03-01'")
        return

    start_date = config.get("backtest", {}).get("start_date", None)
    end_date = config.get("backtest", {}).get("end_date", None)

    print("Running backtest...")
    results = backtester.run(start_date=start_date, end_date=end_date)

    # Display results
    print("\n" + "=" * 50)
    print("BACKTEST RESULTS")
    print("=" * 50)
    print(f"Total Trades:   {results['total_trades']}")
    print(f"Wins:           {results['wins']}")
    print(f"Losses:         {results['losses']}")
    print(f"Win Rate:       {results['win_rate']:.1f}%")
    print(f"Profit Factor:  {results['profit_factor']:.2f}")
    print(f"Max Drawdown:   {results['max_drawdown']*100:.2f}%")
    print(f"Avg R:R:        {results['avg_rr']:.2f}")
    print(f"Net Profit:     ${results['net_profit']:.2f}")
    print(f"Final Balance:  ${results['final_balance']:.2f}")
    print("=" * 50)

    logger.log_analysis("SYSTEM", "backtest_complete", results)


def run_live(config):
    """
    Run the live trading loop.

    Parameters
    ----------
    config : dict
        Configuration dictionary.
    """
    # Initialize components
    mt5_config = config.get("mt5", {})
    telegram_config = config.get("telegram", {})
    risk_config = config.get("risk", {})

    # MT5 Connector
    connector = MT5Connector()
    result = connector.connect(
        login=mt5_config.get("login"),
        password=mt5_config.get("password"),
        server=mt5_config.get("server"),
    )

    if not result["success"]:
        print(f"MT5 Connection failed: {result['message']}")
        print("Cannot run live trading without MT5 connection. Exiting.")
        return

    # Telegram Notifier
    notifier = TelegramNotifier(
        bot_token=telegram_config.get("bot_token"),
        chat_id=telegram_config.get("chat_id"),
    )

    # Logger
    logger = TradeLogger(log_dir="logs")

    # Entry Model
    entry_model = EntryModel()

    # Trading parameters
    symbol = mt5_config.get("symbol", "US100")
    risk_percent = risk_config.get("risk_per_trade", 0.01)
    max_daily_loss_pct = risk_config.get("max_daily_loss", 0.03)

    # Reconnection settings
    max_reconnect_attempts = 5
    reconnect_delay = 30  # seconds

    logger.log_analysis("SYSTEM", "startup", f"ICT Bot started for {symbol}")
    notifier.send_alert(f"ICT Bot started for {symbol}")

    daily_pnl = 0.0
    current_day = datetime.now().date()
    day_start_balance = None

    # --- Fetch HTF (D1) candles at startup for premium/discount filter ---
    def refresh_htf_range(connector_, symbol_, entry_model_):
        """Fetch D1 candles and set the HTF swing range on the entry model."""
        htf_candles = connector_.get_candles(symbol_, "D1", 20)
        if htf_candles is not None and not htf_candles.empty:
            swings = market_structure.detect_swing_points(htf_candles, lookback=3)
            swing_highs = [s for s in swings if s["type"] == "swing_high"]
            swing_lows = [s for s in swings if s["type"] == "swing_low"]
            if swing_highs and swing_lows:
                htf_high = max(s["price"] for s in swing_highs)
                htf_low = min(s["price"] for s in swing_lows)
                entry_model_.set_htf_range(htf_high, htf_low)
                logger.log_analysis(
                    "D1", "htf_range",
                    f"HTF range set: high={htf_high}, low={htf_low}"
                )

    refresh_htf_range(connector, symbol, entry_model)

    print(f"ICT Trading Bot running for {symbol}")
    print("Press Ctrl+C to stop")
    print("-" * 40)

    try:
        while True:
            now = datetime.now()

            # Reset daily stats at start of new day
            if now.date() != current_day:
                summary = logger.log_daily_summary()
                notifier.send_daily_summary(summary)
                logger.reset_daily()
                daily_pnl = 0.0
                day_start_balance = None
                current_day = now.date()
                # Refresh HTF range at the start of each new day
                refresh_htf_range(connector, symbol, entry_model)

            # Gate on connection - attempt reconnection if disconnected
            if not connector.connected:
                reconnected = False
                for attempt in range(1, max_reconnect_attempts + 1):
                    logger.log_analysis(
                        "SYSTEM", "reconnect",
                        f"Attempting reconnection ({attempt}/{max_reconnect_attempts})"
                    )
                    result = connector.connect(
                        login=mt5_config.get("login"),
                        password=mt5_config.get("password"),
                        server=mt5_config.get("server"),
                    )
                    if result["success"]:
                        reconnected = True
                        logger.log_analysis("SYSTEM", "reconnect", "Reconnected")
                        break
                    time.sleep(reconnect_delay)

                if not reconnected:
                    logger.log_analysis(
                        "SYSTEM", "reconnect_failed",
                        "All reconnection attempts failed. Exiting."
                    )
                    notifier.send_alert(
                        "ICT Bot: MT5 connection lost. Reconnection failed. Exiting."
                    )
                    break

            # --- Update daily P&L from account balance delta ---
            account_info = connector.get_account_info()
            if account_info is not None:
                balance = account_info["balance"]
                # Initialize day_start_balance on first successful fetch of the day
                if day_start_balance is None:
                    day_start_balance = balance
                daily_pnl = balance - day_start_balance
            else:
                balance = 10000

            # Check if we are in a kill zone
            active_kz = get_active_kill_zone(now)
            if active_kz is None:
                entry_model.reset()
                time.sleep(60)  # Check every minute outside kill zones
                continue

            # Check daily loss limit
            if not can_take_trade(daily_pnl, balance, max_daily_loss_pct):
                logger.log_analysis("M1", "risk_check",
                                    "Daily loss limit reached, pausing")
                time.sleep(60)
                continue

            # Fetch 1m candles for entry model
            candles = connector.get_candles(symbol, "M1", 1)
            if candles is not None and not candles.empty:
                latest = candles.iloc[-1]
                candle_data = {
                    "time": latest["time"],
                    "open": latest["open"],
                    "high": latest["high"],
                    "low": latest["low"],
                    "close": latest["close"],
                }

                signal = entry_model.update(candle_data)

                if signal is not None:
                    logger.log_analysis("M1", "entry_signal", signal)

                    # Calculate position size
                    symbol_info = connector.get_symbol_info(symbol)
                    pos_size = calculate_position_size(
                        balance, risk_percent,
                        signal["entry_price"],
                        signal["stop_loss"],
                        symbol_info,
                    )

                    if pos_size["valid"]:
                        # Determine order type
                        order_type = ("buy_limit" if signal["direction"] == "long"
                                      else "sell_limit")

                        # Place order
                        order_result = connector.place_order(
                            symbol=symbol,
                            order_type=order_type,
                            volume=pos_size["volume"],
                            price=signal["entry_price"],
                            sl=signal["stop_loss"],
                            tp=signal["take_profit"],
                            comment=f"ICT_{active_kz}",
                        )

                        trade_details = {
                            "direction": signal["direction"],
                            "symbol": symbol,
                            "entry_price": signal["entry_price"],
                            "stop_loss": signal["stop_loss"],
                            "take_profit": signal["take_profit"],
                            "volume": pos_size["volume"],
                            "risk_reward": signal["risk_reward"],
                            "rationale": {
                                "sweep": signal["sweep_info"]["type"],
                                "mss": signal["mss_info"]["type"],
                                "fvg": signal["fvg_info"]["type"],
                                "kill_zone": active_kz,
                            },
                        }

                        if order_result["success"]:
                            logger.log_trade_entry(trade_details)
                            notifier.send_trade_entry(trade_details)
                        else:
                            logger.log_analysis(
                                "M1", "order_failed", order_result["message"]
                            )

                    entry_model.reset()

            # Wait for next candle (poll every 10 seconds)
            time.sleep(10)

    except KeyboardInterrupt:
        print("\nShutting down...")
        summary = logger.log_daily_summary()
        notifier.send_daily_summary(summary)
        connector.disconnect()
        print("ICT Trading Bot stopped.")


def main():
    """Main entry point with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description="ICT Trading Bot - NAS100 automated trading using ICT concepts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py --config config/settings.yaml\n"
            "  python main.py --backtest --config config/settings.yaml\n"
        ),
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/settings.yaml",
        help="Path to YAML configuration file (default: config/settings.yaml)",
    )
    parser.add_argument(
        "--backtest",
        action="store_true",
        help="Run in backtest mode instead of live trading",
    )

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    if args.backtest:
        run_backtest(config)
    else:
        run_live(config)


if __name__ == "__main__":
    main()
