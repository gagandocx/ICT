"""
Market Structure Module - BOS and MSS Detection

Identifies Break of Structure (BOS) and Market Structure Shift (MSS)
using swing high/low analysis on OHLC data.

BOS = price breaks a swing point in the same direction as the trend (continuation)
MSS = price breaks a swing point against the trend (reversal signal)
"""

import pandas as pd
import numpy as np


def detect_swing_points(df, lookback=5):
    """
    Identify swing highs and swing lows on an OHLC DataFrame.

    A swing high is a candle whose high is higher than the highs of the
    surrounding `lookback` candles on each side.
    A swing low is a candle whose low is lower than the lows of the
    surrounding `lookback` candles on each side.

    Parameters
    ----------
    df : pd.DataFrame
        OHLC DataFrame with columns: open, high, low, close, time
    lookback : int
        Number of candles to look on each side for swing detection.

    Returns
    -------
    list of dict
        Each dict contains:
        - 'type': 'swing_high' or 'swing_low'
        - 'index': integer index in the DataFrame
        - 'price': the high or low price at that point
        - 'time': timestamp of the candle
    """
    swings = []
    highs = df["high"].values
    lows = df["low"].values

    for i in range(lookback, len(df) - lookback):
        # Check for swing high
        is_swing_high = True
        for j in range(1, lookback + 1):
            if highs[i] <= highs[i - j] or highs[i] <= highs[i + j]:
                is_swing_high = False
                break

        if is_swing_high:
            swings.append({
                "type": "swing_high",
                "index": i,
                "price": highs[i],
                "time": df["time"].iloc[i] if "time" in df.columns else i,
            })

        # Check for swing low
        is_swing_low = True
        for j in range(1, lookback + 1):
            if lows[i] >= lows[i - j] or lows[i] >= lows[i + j]:
                is_swing_low = False
                break

        if is_swing_low:
            swings.append({
                "type": "swing_low",
                "index": i,
                "price": lows[i],
                "time": df["time"].iloc[i] if "time" in df.columns else i,
            })

    return swings


def detect_bos(df, swings):
    """
    Detect Break of Structure (BOS) - continuation signals.

    A bullish BOS occurs when price closes above a previous swing high
    while the trend is already bullish (higher highs/higher lows).
    A bearish BOS occurs when price closes below a previous swing low
    while the trend is already bearish (lower highs/lower lows).

    Parameters
    ----------
    df : pd.DataFrame
        OHLC DataFrame with columns: open, high, low, close, time
    swings : list of dict
        Output from detect_swing_points()

    Returns
    -------
    list of dict
        Each dict contains:
        - 'type': 'bullish_bos' or 'bearish_bos'
        - 'break_index': index where the break occurred
        - 'broken_level': price level that was broken
        - 'swing_index': index of the swing point that was broken
        - 'time': timestamp of the break candle
    """
    bos_events = []
    closes = df["close"].values

    # Separate swing highs and lows
    swing_highs = [s for s in swings if s["type"] == "swing_high"]
    swing_lows = [s for s in swings if s["type"] == "swing_low"]

    # Detect bullish BOS: price breaks above a previous swing high
    for i, sh in enumerate(swing_highs):
        # Look for the next swing high to determine trend
        if i > 0:
            prev_sh = swing_highs[i - 1]
            # Only count as BOS if we have higher highs (bullish trend)
            if sh["price"] <= prev_sh["price"]:
                continue

        # Find the first candle after the swing high that closes above it
        for bar_idx in range(sh["index"] + 1, len(df)):
            if closes[bar_idx] > sh["price"]:
                bos_events.append({
                    "type": "bullish_bos",
                    "break_index": bar_idx,
                    "broken_level": sh["price"],
                    "swing_index": sh["index"],
                    "time": df["time"].iloc[bar_idx] if "time" in df.columns else bar_idx,
                })
                break

    # Detect bearish BOS: price breaks below a previous swing low
    for i, sl in enumerate(swing_lows):
        # Only count as BOS if we have lower lows (bearish trend)
        if i > 0:
            prev_sl = swing_lows[i - 1]
            if sl["price"] >= prev_sl["price"]:
                continue

        # Find the first candle after the swing low that closes below it
        for bar_idx in range(sl["index"] + 1, len(df)):
            if closes[bar_idx] < sl["price"]:
                bos_events.append({
                    "type": "bearish_bos",
                    "break_index": bar_idx,
                    "broken_level": sl["price"],
                    "swing_index": sl["index"],
                    "time": df["time"].iloc[bar_idx] if "time" in df.columns else bar_idx,
                })
                break

    # Sort by break_index
    bos_events.sort(key=lambda x: x["break_index"])
    return bos_events


def detect_mss(df, swings):
    """
    Detect Market Structure Shift (MSS) - reversal signals.

    A bullish MSS occurs when price closes above a swing high after
    a series of lower lows (bearish trend broken to the upside).
    A bearish MSS occurs when price closes below a swing low after
    a series of higher highs (bullish trend broken to the downside).

    Parameters
    ----------
    df : pd.DataFrame
        OHLC DataFrame with columns: open, high, low, close, time
    swings : list of dict
        Output from detect_swing_points()

    Returns
    -------
    list of dict
        Each dict contains:
        - 'type': 'bullish_mss' or 'bearish_mss'
        - 'break_index': index where the break occurred
        - 'broken_level': price level that was broken
        - 'swing_index': index of the swing point that was broken
        - 'time': timestamp of the break candle
    """
    mss_events = []
    closes = df["close"].values

    # Separate swing highs and lows
    swing_highs = [s for s in swings if s["type"] == "swing_high"]
    swing_lows = [s for s in swings if s["type"] == "swing_low"]

    # Detect bullish MSS: price breaks above a swing high after bearish trend
    # (lower highs pattern broken)
    for i, sh in enumerate(swing_highs):
        if i > 0:
            prev_sh = swing_highs[i - 1]
            # MSS requires the current swing high to be LOWER than previous
            # (bearish trend), and then price breaks above it
            if sh["price"] >= prev_sh["price"]:
                continue

        # Find the first candle after the swing high that closes above it
        for bar_idx in range(sh["index"] + 1, len(df)):
            if closes[bar_idx] > sh["price"]:
                mss_events.append({
                    "type": "bullish_mss",
                    "break_index": bar_idx,
                    "broken_level": sh["price"],
                    "swing_index": sh["index"],
                    "time": df["time"].iloc[bar_idx] if "time" in df.columns else bar_idx,
                })
                break

    # Detect bearish MSS: price breaks below a swing low after bullish trend
    # (higher lows pattern broken)
    for i, sl in enumerate(swing_lows):
        if i > 0:
            prev_sl = swing_lows[i - 1]
            # MSS requires the current swing low to be HIGHER than previous
            # (bullish trend), and then price breaks below it
            if sl["price"] <= prev_sl["price"]:
                continue

        # Find the first candle after the swing low that closes below it
        for bar_idx in range(sl["index"] + 1, len(df)):
            if closes[bar_idx] < sl["price"]:
                mss_events.append({
                    "type": "bearish_mss",
                    "break_index": bar_idx,
                    "broken_level": sl["price"],
                    "swing_index": sl["index"],
                    "time": df["time"].iloc[bar_idx] if "time" in df.columns else bar_idx,
                })
                break

    # Sort by break_index
    mss_events.sort(key=lambda x: x["break_index"])
    return mss_events
