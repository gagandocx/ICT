"""
Order Blocks Module - Bullish and Bearish OB Identification

An Order Block (OB) is the last opposing candle before a strong move:
- Bullish OB: the last bearish candle before a bullish BOS
- Bearish OB: the last bullish candle before a bearish BOS

Order Blocks represent institutional supply/demand zones.
"""

import pandas as pd
import numpy as np


def find_order_blocks(df, structure_events):
    """
    Identify Bullish and Bearish Order Blocks based on structure events.

    A Bullish OB is the last bearish candle before a bullish BOS/MSS.
    A Bearish OB is the last bullish candle before a bearish BOS/MSS.

    Parameters
    ----------
    df : pd.DataFrame
        OHLC DataFrame with columns: open, high, low, close, time
    structure_events : list of dict
        BOS/MSS events from market_structure module. Each dict must have:
        - 'type': contains 'bullish' or 'bearish'
        - 'break_index': index of the break candle
        - 'swing_index': index of the swing point that was broken

    Returns
    -------
    list of dict
        Each dict contains:
        - 'type': 'bullish_ob' or 'bearish_ob'
        - 'index': index of the OB candle
        - 'high': high of the OB candle
        - 'low': low of the OB candle
        - 'open': open of the OB candle
        - 'close': close of the OB candle
        - 'time': timestamp of the OB candle
        - 'mitigated': False (initially)
        - 'event_type': the structure event type that created this OB
    """
    order_blocks = []
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values

    for event in structure_events:
        break_idx = event["break_index"]
        event_type = event["type"]

        if "bullish" in event_type:
            # Bullish OB: find the last bearish candle before the break
            ob_idx = None
            for i in range(break_idx - 1, -1, -1):
                if closes[i] < opens[i]:  # Bearish candle
                    ob_idx = i
                    break

            if ob_idx is not None:
                order_blocks.append({
                    "type": "bullish_ob",
                    "index": ob_idx,
                    "high": highs[ob_idx],
                    "low": lows[ob_idx],
                    "open": opens[ob_idx],
                    "close": closes[ob_idx],
                    "time": df["time"].iloc[ob_idx] if "time" in df.columns else ob_idx,
                    "mitigated": False,
                    "event_type": event_type,
                })

        elif "bearish" in event_type:
            # Bearish OB: find the last bullish candle before the break
            ob_idx = None
            for i in range(break_idx - 1, -1, -1):
                if closes[i] > opens[i]:  # Bullish candle
                    ob_idx = i
                    break

            if ob_idx is not None:
                order_blocks.append({
                    "type": "bearish_ob",
                    "index": ob_idx,
                    "high": highs[ob_idx],
                    "low": lows[ob_idx],
                    "open": opens[ob_idx],
                    "close": closes[ob_idx],
                    "time": df["time"].iloc[ob_idx] if "time" in df.columns else ob_idx,
                    "mitigated": False,
                    "event_type": event_type,
                })

    return order_blocks


def is_ob_mitigated(ob, current_price):
    """
    Check if an Order Block has been mitigated (price has reached the OB zone).

    A bullish OB is mitigated when price trades down into its zone (reaches OB low).
    A bearish OB is mitigated when price trades up into its zone (reaches OB high).

    Parameters
    ----------
    ob : dict
        Order Block dictionary from find_order_blocks()
    current_price : float
        Current price to check against the OB zone

    Returns
    -------
    bool
        True if the OB has been mitigated
    """
    if ob["type"] == "bullish_ob":
        # Bullish OB is mitigated when price reaches into its zone
        return current_price <= ob["high"]
    elif ob["type"] == "bearish_ob":
        # Bearish OB is mitigated when price reaches into its zone
        return current_price >= ob["low"]
    return False
