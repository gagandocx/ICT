"""
Liquidity Module - Equal Highs/Lows and Liquidity Sweep Detection

Liquidity pools form at equal highs and lows where stop losses cluster.
A liquidity sweep (raid) occurs when price pierces a level but closes back,
indicating institutional stop hunting before a reversal.
"""

import pandas as pd
import numpy as np


def detect_equal_levels(df, tolerance_pips=5):
    """
    Detect equal highs and equal lows that represent liquidity pools.

    Equal highs/lows are areas where price has tested the same level
    multiple times, indicating resting buy/sell stops above/below.

    Parameters
    ----------
    df : pd.DataFrame
        OHLC DataFrame with columns: open, high, low, close, time
    tolerance_pips : float
        Maximum difference (in pips/points) to consider two levels as "equal".
        For NAS100, 1 pip = 1 point.

    Returns
    -------
    list of dict
        Each dict contains:
        - 'type': 'equal_highs' or 'equal_lows'
        - 'level': the average price level
        - 'indices': list of bar indices that formed the level
        - 'count': number of touches
        - 'times': list of timestamps
    """
    levels = []
    highs = df["high"].values
    lows = df["low"].values

    # Detect equal highs
    high_groups = _group_equal_levels(highs, tolerance_pips)
    for group in high_groups:
        if len(group) >= 2:
            avg_level = np.mean([highs[i] for i in group])
            times = [
                df["time"].iloc[i] if "time" in df.columns else i
                for i in group
            ]
            levels.append({
                "type": "equal_highs",
                "level": avg_level,
                "indices": group,
                "count": len(group),
                "times": times,
            })

    # Detect equal lows
    low_groups = _group_equal_levels(lows, tolerance_pips)
    for group in low_groups:
        if len(group) >= 2:
            avg_level = np.mean([lows[i] for i in group])
            times = [
                df["time"].iloc[i] if "time" in df.columns else i
                for i in group
            ]
            levels.append({
                "type": "equal_lows",
                "level": avg_level,
                "indices": group,
                "count": len(group),
                "times": times,
            })

    return levels


def _group_equal_levels(prices, tolerance):
    """
    Group price levels that are within tolerance of each other.

    Parameters
    ----------
    prices : np.ndarray
        Array of prices (highs or lows)
    tolerance : float
        Maximum difference to consider levels equal

    Returns
    -------
    list of list
        Groups of indices with similar price levels
    """
    groups = []
    used = set()

    for i in range(len(prices)):
        if i in used:
            continue

        group = [i]
        for j in range(i + 1, len(prices)):
            if j in used:
                continue
            if abs(prices[i] - prices[j]) <= tolerance:
                group.append(j)
                used.add(j)

        if len(group) >= 2:
            groups.append(group)
            used.add(i)

    return groups


def detect_liquidity_sweep(df, levels, min_sweep_pips=2):
    """
    Detect liquidity sweeps (raids) where price pierces a level but closes back.

    A sweep above equal highs: price wicks above the level but closes below it.
    A sweep below equal lows: price wicks below the level but closes above it.

    Parameters
    ----------
    df : pd.DataFrame
        OHLC DataFrame with columns: open, high, low, close, time
    levels : list of dict
        Liquidity levels from detect_equal_levels()
    min_sweep_pips : float
        Minimum distance price must exceed the level to qualify as a sweep.

    Returns
    -------
    list of dict
        Each dict contains:
        - 'type': 'sweep_high' or 'sweep_low'
        - 'level': the liquidity level that was swept
        - 'sweep_index': index of the sweep candle
        - 'sweep_price': the extreme price during the sweep (wick)
        - 'close_price': close of the sweep candle
        - 'time': timestamp of the sweep candle
    """
    sweeps = []
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values

    for level_info in levels:
        level_price = level_info["level"]
        # Start looking after the last touch that formed the level
        start_idx = max(level_info["indices"]) + 1

        for bar_idx in range(start_idx, len(df)):
            if level_info["type"] == "equal_highs":
                # Sweep above: high exceeds level, but close is below level
                if (highs[bar_idx] > level_price + min_sweep_pips
                        and closes[bar_idx] < level_price):
                    sweeps.append({
                        "type": "sweep_high",
                        "level": level_price,
                        "sweep_index": bar_idx,
                        "sweep_price": highs[bar_idx],
                        "close_price": closes[bar_idx],
                        "time": df["time"].iloc[bar_idx] if "time" in df.columns else bar_idx,
                    })
                    break  # Only detect first sweep per level

            elif level_info["type"] == "equal_lows":
                # Sweep below: low exceeds level, but close is above level
                if (lows[bar_idx] < level_price - min_sweep_pips
                        and closes[bar_idx] > level_price):
                    sweeps.append({
                        "type": "sweep_low",
                        "level": level_price,
                        "sweep_index": bar_idx,
                        "sweep_price": lows[bar_idx],
                        "close_price": closes[bar_idx],
                        "time": df["time"].iloc[bar_idx] if "time" in df.columns else bar_idx,
                    })
                    break  # Only detect first sweep per level

    return sweeps
