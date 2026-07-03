"""
MT5 Connector Module - MetaTrader 5 Broker Integration

Provides a wrapper around the MetaTrader5 Python package for:
- Connecting to the trading server
- Fetching OHLC candle data
- Placing and managing orders
- Retrieving account and symbol information

The MT5 package is only available on Windows. This module handles
graceful import failure on Linux/macOS.
"""

import pandas as pd
from datetime import datetime

# Graceful import handling - MT5 is only available on Windows
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    mt5 = None
    MT5_AVAILABLE = False


# Timeframe mapping from string to MT5 constants
TIMEFRAME_MAP = {}
if MT5_AVAILABLE:
    TIMEFRAME_MAP = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
        "W1": mt5.TIMEFRAME_W1,
        "MN1": mt5.TIMEFRAME_MN1,
    }
else:
    # Placeholder values for testing without MT5
    TIMEFRAME_MAP = {
        "M1": 1,
        "M5": 5,
        "M15": 15,
        "M30": 30,
        "H1": 60,
        "H4": 240,
        "D1": 1440,
        "W1": 10080,
        "MN1": 43200,
    }


class MT5Connector:
    """
    Wrapper around the MetaTrader5 Python package.

    Provides methods for connecting to the broker, fetching market data,
    and executing trades. Handles graceful degradation when MT5 is not
    available (e.g., on Linux).

    Parameters
    ----------
    None

    Attributes
    ----------
    connected : bool
        Whether the connector is currently connected to MT5.
    """

    def __init__(self):
        self.connected = False
        self._login = None
        self._server = None

    def connect(self, login, password, server):
        """
        Connect to the MetaTrader 5 terminal.

        Parameters
        ----------
        login : int
            MT5 account login number.
        password : str
            Account password.
        server : str
            Broker server name (e.g., 'FusionMarkets-Live').

        Returns
        -------
        dict
            Connection result with:
            - 'success': bool
            - 'message': str with details
        """
        if not MT5_AVAILABLE:
            return {
                "success": False,
                "message": "MetaTrader5 package is not available on this platform",
            }

        if not mt5.initialize():
            return {
                "success": False,
                "message": f"MT5 initialization failed: {mt5.last_error()}",
            }

        authorized = mt5.login(login=int(login), password=password, server=server)
        if not authorized:
            error = mt5.last_error()
            mt5.shutdown()
            return {
                "success": False,
                "message": f"Login failed: {error}",
            }

        self.connected = True
        self._login = login
        self._server = server
        return {
            "success": True,
            "message": f"Connected to {server} (account {login})",
        }

    def disconnect(self):
        """
        Disconnect from the MetaTrader 5 terminal.

        Returns
        -------
        dict
            Result with 'success' and 'message'.
        """
        if not MT5_AVAILABLE:
            return {"success": True, "message": "MT5 not available, nothing to disconnect"}

        if self.connected:
            mt5.shutdown()
            self.connected = False
            return {"success": True, "message": "Disconnected from MT5"}

        return {"success": True, "message": "Was not connected"}

    def get_candles(self, symbol, timeframe, count):
        """
        Fetch OHLC candle data from MT5.

        Parameters
        ----------
        symbol : str
            Trading symbol (e.g., 'US100').
        timeframe : str
            Timeframe string: M1, M5, M15, M30, H1, H4, D1, W1, MN1.
        count : int
            Number of candles to fetch.

        Returns
        -------
        pd.DataFrame or None
            DataFrame with columns: time, open, high, low, close, tick_volume,
            spread, real_volume. Returns None on error.
        """
        if not MT5_AVAILABLE:
            return None

        if not self.connected:
            return None

        tf = TIMEFRAME_MAP.get(timeframe)
        if tf is None:
            return None

        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None or len(rates) == 0:
            return None

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df

    def get_account_info(self):
        """
        Get current account information.

        Returns
        -------
        dict or None
            Account info with keys: balance, equity, margin, free_margin,
            profit, leverage. Returns None if not connected or MT5 unavailable.
        """
        if not MT5_AVAILABLE or not self.connected:
            return None

        info = mt5.account_info()
        if info is None:
            return None

        return {
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "free_margin": info.margin_free,
            "profit": info.profit,
            "leverage": info.leverage,
        }

    def place_order(self, symbol, order_type, volume, price, sl, tp, comment=""):
        """
        Place a trading order via MT5.

        Parameters
        ----------
        symbol : str
            Trading symbol (e.g., 'US100').
        order_type : str
            Order type: 'buy', 'sell', 'buy_limit', 'sell_limit',
            'buy_stop', 'sell_stop'.
        volume : float
            Lot size.
        price : float
            Order price (for limit/stop orders).
        sl : float
            Stop loss price.
        tp : float
            Take profit price.
        comment : str
            Order comment for identification.

        Returns
        -------
        dict
            Order result with:
            - 'success': bool
            - 'ticket': order ticket number (if success)
            - 'message': descriptive message
        """
        if not MT5_AVAILABLE:
            return {
                "success": False,
                "ticket": None,
                "message": "MetaTrader5 package is not available",
            }

        if not self.connected:
            return {
                "success": False,
                "ticket": None,
                "message": "Not connected to MT5",
            }

        # Map order type strings to MT5 constants
        order_type_map = {
            "buy": mt5.ORDER_TYPE_BUY,
            "sell": mt5.ORDER_TYPE_SELL,
            "buy_limit": mt5.ORDER_TYPE_BUY_LIMIT,
            "sell_limit": mt5.ORDER_TYPE_SELL_LIMIT,
            "buy_stop": mt5.ORDER_TYPE_BUY_STOP,
            "sell_stop": mt5.ORDER_TYPE_SELL_STOP,
        }

        mt5_order_type = order_type_map.get(order_type)
        if mt5_order_type is None:
            return {
                "success": False,
                "ticket": None,
                "message": f"Invalid order type: {order_type}",
            }

        # Build the trade request
        request = {
            "action": mt5.TRADE_ACTION_DEAL if order_type in ("buy", "sell")
                      else mt5.TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": volume,
            "type": mt5_order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            return {
                "success": False,
                "ticket": None,
                "message": f"Order send failed: {mt5.last_error()}",
            }

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return {
                "success": False,
                "ticket": None,
                "message": f"Order rejected: {result.comment} (code {result.retcode})",
            }

        return {
            "success": True,
            "ticket": result.order,
            "message": f"Order placed successfully: ticket {result.order}",
        }

    def close_position(self, ticket):
        """
        Close an open position by ticket number.

        Parameters
        ----------
        ticket : int
            Position ticket number to close.

        Returns
        -------
        dict
            Result with 'success', 'message'.
        """
        if not MT5_AVAILABLE:
            return {"success": False, "message": "MetaTrader5 package is not available"}

        if not self.connected:
            return {"success": False, "message": "Not connected to MT5"}

        positions = mt5.positions_get(ticket=ticket)
        if positions is None or len(positions) == 0:
            return {"success": False, "message": f"Position {ticket} not found"}

        position = positions[0]
        close_type = (mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY
                      else mt5.ORDER_TYPE_BUY)

        # Get current price
        symbol_info = mt5.symbol_info_tick(position.symbol)
        if symbol_info is None:
            return {"success": False, "message": "Failed to get symbol tick info"}

        price = (symbol_info.bid if close_type == mt5.ORDER_TYPE_SELL
                 else symbol_info.ask)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "comment": "Close position",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            return {"success": False, "message": f"Close failed: {mt5.last_error()}"}

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return {
                "success": False,
                "message": f"Close rejected: {result.comment} (code {result.retcode})",
            }

        return {"success": True, "message": f"Position {ticket} closed successfully"}

    def get_open_positions(self):
        """
        Get all currently open positions.

        Returns
        -------
        list of dict or None
            List of position dictionaries, or None if unavailable.
            Each dict contains: ticket, symbol, type, volume, price_open,
            sl, tp, profit, time.
        """
        if not MT5_AVAILABLE or not self.connected:
            return None

        positions = mt5.positions_get()
        if positions is None:
            return []

        result = []
        for pos in positions:
            result.append({
                "ticket": pos.ticket,
                "symbol": pos.symbol,
                "type": "buy" if pos.type == mt5.ORDER_TYPE_BUY else "sell",
                "volume": pos.volume,
                "price_open": pos.price_open,
                "sl": pos.sl,
                "tp": pos.tp,
                "profit": pos.profit,
                "time": datetime.fromtimestamp(pos.time),
            })

        return result

    def get_symbol_info(self, symbol):
        """
        Get symbol information for position sizing.

        Parameters
        ----------
        symbol : str
            Trading symbol (e.g., 'US100').

        Returns
        -------
        dict or None
            Symbol info with: contract_size, volume_min, volume_max,
            volume_step, point, digits, spread. Returns None if unavailable.
        """
        if not MT5_AVAILABLE or not self.connected:
            return None

        info = mt5.symbol_info(symbol)
        if info is None:
            return None

        return {
            "contract_size": info.trade_contract_size,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "point": info.point,
            "digits": info.digits,
            "spread": info.spread,
        }
