"""
Fair Value Gap (FVG) Module - FVG and Inverse FVG Detection

A Fair Value Gap is a 3-candle pattern representing inefficiency in price delivery:
- Bullish FVG: candle 1 high < candle 3 low (gap between candle 1 high and candle 3 low)
- Bearish FVG: candle 1 low > candle 3 high (gap between candle 1 low and candle 3 high)

Inverse FVG (iFVG) occurs when price fills an existing FVG, turning that
filled gap into a zone of interest in the opposite direction.
"""

import pandas as pd
import numpy as np


def detect_fvg(df):
    """
    Detect Fair Value Gaps in OHLC data.

    A bullish FVG forms when candle 1's high is below candle 3's low,
    creating an unfilled gap that price may revisit.
    A bearish FVG forms when candle 1's low is above candle 3's high.

    Parameters
    ----------
    df : pd.DataFrame
        OHLC DataFrame with columns: open, high, low, close, time

    Returns
    -------
    list of dict
        Each dict contains:
        - 'type': 'bullish_fvg' or 'bearish_fvg'
        - 'high': upper boundary of the gap
        - 'low': lower boundary of the gap
        - 'midpoint': 50% level of the gap (for limit order entry)
        - 'index': index of the middle candle (candle 2)
        - 'time': timestamp of the middle candle
        - 'filled': False (initially)
    """
    fvgs = []
    highs = df["high"].values
    lows = df["low"].values

    for i in range(2, len(df)):
        candle1_high = highs[i - 2]
        candle1_low = lows[i - 2]
        candle3_high = highs[i]
        candle3_low = lows[i]

        # Bullish FVG: gap between candle 1 high and candle 3 low
        if candle1_high < candle3_low:
            fvg_low = candle1_high
            fvg_high = candle3_low
            midpoint = (fvg_high + fvg_low) / 2.0
            fvgs.append({
                "type": "bullish_fvg",
                "high": fvg_high,
                "low": fvg_low,
                "midpoint": midpoint,
                "index": i - 1,
                "time": df["time"].iloc[i - 1] if "time" in df.columns else i - 1,
                "filled": False,
            })

        # Bearish FVG: gap between candle 1 low and candle 3 high
        if candle1_low > candle3_high:
            fvg_high = candle1_low
            fvg_low = candle3_high
            midpoint = (fvg_high + fvg_low) / 2.0
            fvgs.append({
                "type": "bearish_fvg",
                "high": fvg_high,
                "low": fvg_low,
                "midpoint": midpoint,
                "index": i - 1,
                "time": df["time"].iloc[i - 1] if "time" in df.columns else i - 1,
                "filled": False,
            })

    return fvgs


def detect_ifvg(df, existing_fvgs):
    """
    Detect Inverse Fair Value Gaps (iFVG).

    An Inverse FVG occurs when price fills an existing FVG. The filled gap
    then becomes a zone of interest in the opposite direction.

    Parameters
    ----------
    df : pd.DataFrame
        OHLC DataFrame with columns: open, high, low, close, time
    existing_fvgs : list of dict
        List of FVGs from detect_fvg()

    Returns
    -------
    list of dict
        Each dict contains:
        - 'type': 'bullish_ifvg' or 'bearish_ifvg'
        - 'high': upper boundary of the inverse gap zone
        - 'low': lower boundary of the inverse gap zone
        - 'midpoint': 50% level
        - 'original_fvg_index': index of the original FVG
        - 'fill_index': index where the FVG was filled
        - 'time': timestamp of the fill candle
    """
    ifvgs = []
    highs = df["high"].values
    lows = df["low"].values

    for fvg_item in existing_fvgs:
        if fvg_item["filled"]:
            continue

        fvg_idx = fvg_item["index"]

        # Check subsequent candles to see if the FVG gets filled
        for bar_idx in range(fvg_idx + 2, len(df)):
            filled = False

            if fvg_item["type"] == "bullish_fvg":
                # Bullish FVG is filled when price trades down through it
                if lows[bar_idx] <= fvg_item["low"]:
                    filled = True
                    # The filled bullish FVG becomes a bearish iFVG
                    ifvg_type = "bearish_ifvg"
            elif fvg_item["type"] == "bearish_fvg":
                # Bearish FVG is filled when price trades up through it
                if highs[bar_idx] >= fvg_item["high"]:
                    filled = True
                    # The filled bearish FVG becomes a bullish iFVG
                    ifvg_type = "bullish_ifvg"

            if filled:
                fvg_item["filled"] = True
                midpoint = (fvg_item["high"] + fvg_item["low"]) / 2.0
                ifvgs.append({
                    "type": ifvg_type,
                    "high": fvg_item["high"],
                    "low": fvg_item["low"],
                    "midpoint": midpoint,
                    "original_fvg_index": fvg_idx,
                    "fill_index": bar_idx,
                    "time": df["time"].iloc[bar_idx] if "time" in df.columns else bar_idx,
                })
                break

    return ifvgs


def get_fvg_midpoint(fvg_item):
    """
    Get the 50% (midpoint) level of an FVG for limit order entry.

    Parameters
    ----------
    fvg_item : dict
        FVG dictionary from detect_fvg() or detect_ifvg()

    Returns
    -------
    float
        The midpoint (mean threshold) price level
    """
    return (fvg_item["high"] + fvg_item["low"]) / 2.0
