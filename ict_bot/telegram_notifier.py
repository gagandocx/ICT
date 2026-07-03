"""
Telegram Notifier Module - Trade Alerts via Telegram Bot API

Sends trading alerts, entry/exit notifications, and daily summaries
using the Telegram Bot API via direct HTTP requests (no external
telegram library dependency required).
"""

import json
from datetime import datetime

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramNotifier:
    """
    Send trade notifications via Telegram Bot API.

    Uses direct HTTP requests to the Telegram Bot API for maximum
    portability (no python-telegram-bot dependency required).

    Parameters
    ----------
    bot_token : str or None
        Telegram bot token from BotFather. If None, notifications are disabled.
    chat_id : str or None
        Target chat/channel ID. If None, notifications are disabled.
    """

    def __init__(self, bot_token=None, chat_id=None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = bool(bot_token and chat_id and REQUESTS_AVAILABLE)

    def _send_message(self, text, parse_mode="HTML"):
        """
        Send a message via Telegram Bot API.

        Parameters
        ----------
        text : str
            Message text (supports HTML formatting).
        parse_mode : str
            Parse mode: 'HTML' or 'Markdown'.

        Returns
        -------
        dict
            Result with 'success' and 'message'.
        """
        if not self.enabled:
            return {
                "success": False,
                "message": "Telegram notifications not configured",
            }

        url = TELEGRAM_API_BASE.format(token=self.bot_token, method="sendMessage")
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            data = response.json()
            if data.get("ok"):
                return {"success": True, "message": "Message sent"}
            else:
                return {
                    "success": False,
                    "message": f"Telegram API error: {data.get('description', 'Unknown')}",
                }
        except requests.exceptions.RequestException as e:
            return {"success": False, "message": f"Request failed: {str(e)}"}

    def send_alert(self, message):
        """
        Send a general alert message.

        Parameters
        ----------
        message : str
            Alert message text.

        Returns
        -------
        dict
            Result with 'success' and 'message'.
        """
        text = f"<b>ICT Bot Alert</b>\n\n{message}"
        return self._send_message(text)

    def send_trade_entry(self, trade_details):
        """
        Send a trade entry notification with formatted details.

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
            - 'risk_reward': R:R ratio (optional)

        Returns
        -------
        dict
            Result with 'success' and 'message'.
        """
        direction = trade_details.get("direction", "unknown").upper()
        symbol = trade_details.get("symbol", "US100")
        entry = trade_details.get("entry_price", 0)
        sl = trade_details.get("stop_loss", 0)
        tp = trade_details.get("take_profit", 0)
        volume = trade_details.get("volume", 0)
        rr = trade_details.get("risk_reward", 0)

        emoji = "\u2b06\ufe0f" if direction == "LONG" else "\u2b07\ufe0f"

        text = (
            f"<b>{emoji} NEW TRADE - {direction}</b>\n\n"
            f"<b>Symbol:</b> {symbol}\n"
            f"<b>Entry:</b> {entry:.2f}\n"
            f"<b>Stop Loss:</b> {sl:.2f}\n"
            f"<b>Take Profit:</b> {tp:.2f}\n"
            f"<b>Volume:</b> {volume:.2f}\n"
            f"<b>R:R:</b> {rr:.2f}\n"
            f"\n<i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"
        )
        return self._send_message(text)

    def send_trade_exit(self, trade_result):
        """
        Send a trade exit notification.

        Parameters
        ----------
        trade_result : dict
            Trade result containing:
            - 'direction': 'long' or 'short'
            - 'symbol': trading symbol
            - 'entry_price': entry price
            - 'exit_price': exit price
            - 'profit': profit/loss amount
            - 'pips': pips gained/lost (optional)
            - 'result': 'win' or 'loss'

        Returns
        -------
        dict
            Result with 'success' and 'message'.
        """
        result_type = trade_result.get("result", "unknown").upper()
        symbol = trade_result.get("symbol", "US100")
        entry = trade_result.get("entry_price", 0)
        exit_price = trade_result.get("exit_price", 0)
        profit = trade_result.get("profit", 0)
        direction = trade_result.get("direction", "unknown").upper()

        emoji = "\u2705" if result_type == "WIN" else "\u274c"

        text = (
            f"<b>{emoji} TRADE CLOSED - {result_type}</b>\n\n"
            f"<b>Symbol:</b> {symbol}\n"
            f"<b>Direction:</b> {direction}\n"
            f"<b>Entry:</b> {entry:.2f}\n"
            f"<b>Exit:</b> {exit_price:.2f}\n"
            f"<b>P&L:</b> ${profit:.2f}\n"
            f"\n<i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"
        )
        return self._send_message(text)

    def send_daily_summary(self, daily_stats):
        """
        Send an end-of-day trading summary.

        Parameters
        ----------
        daily_stats : dict
            Daily statistics containing:
            - 'total_trades': number of trades taken
            - 'wins': number of winning trades
            - 'losses': number of losing trades
            - 'net_pnl': net profit/loss
            - 'win_rate': win percentage (optional)

        Returns
        -------
        dict
            Result with 'success' and 'message'.
        """
        total = daily_stats.get("total_trades", 0)
        wins = daily_stats.get("wins", 0)
        losses = daily_stats.get("losses", 0)
        pnl = daily_stats.get("net_pnl", 0)
        win_rate = daily_stats.get("win_rate", 0)

        if win_rate == 0 and total > 0:
            win_rate = (wins / total) * 100

        emoji = "\U0001f4ca"
        pnl_emoji = "\U0001f7e2" if pnl >= 0 else "\U0001f534"

        text = (
            f"<b>{emoji} DAILY SUMMARY</b>\n\n"
            f"<b>Total Trades:</b> {total}\n"
            f"<b>Wins:</b> {wins}\n"
            f"<b>Losses:</b> {losses}\n"
            f"<b>Win Rate:</b> {win_rate:.1f}%\n"
            f"{pnl_emoji} <b>Net P&L:</b> ${pnl:.2f}\n"
            f"\n<i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"
        )
        return self._send_message(text)
